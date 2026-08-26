"""Losing the internet, and getting it back.

Brief §39. The point every one of these defends: an outage is an operational
state, not a research finding. A page nobody could reach is not a page that
holds nothing, and a run that stopped early is not a run that finished.
"""

from __future__ import annotations

import asyncio

import pytest

from dcr.control import (PAUSED_NETWORK, RUNNING, RunControl, request_cancel,
                         request_pause, request_resume)
from dcr.db import Database, utcnow
from dcr.net.connectivity import (FULL, OFFLINE, PARTIAL, UNKNOWN,
                                  ConnectivityMonitor, classify_failures)
from dcr.supervisor import RunPaused, Supervisor

from test_control import make_run


# ---------------------------------------------------------------------------
# a network that can be switched off
# ---------------------------------------------------------------------------
class FakeNetwork:
    """A simulated internet, with a switch and a per-host failure list."""

    def __init__(self, *, online: bool = True):
        self.online = online
        self.dead_hosts: set[str] = set()
        self.probes: list[str] = []
        #: Flip back on after this many probes, for restoration scenarios.
        self.restore_after: int | None = None

    async def probe(self, url: str) -> bool:
        self.probes.append(url)
        if self.restore_after is not None and len(self.probes) >= self.restore_after:
            self.online = True
        if not self.online:
            return False
        return not any(host in url for host in self.dead_hosts)


def monitor_for(network: FakeNetwork, **kwargs) -> ConnectivityMonitor:
    return ConnectivityMonitor(
        probes=("https://a.example/", "https://b.example/",
                "https://c.example/", "https://d.example/"),
        prober=network.probe, check_interval_s=0.0,
        offline_retry_s=0.0, offline_retry_max_s=0.0, **kwargs)


@pytest.fixture()
def control(db, community, tmp_path):
    run_id = make_run(db, community)
    return RunControl(db, run_id=run_id, community_id=community,
                      control_dir=tmp_path / "control", poll_interval_s=0.0)


def supervisor_for(control, monitor, **config):
    async def instant(_seconds: float) -> None:
        await asyncio.sleep(0)

    return Supervisor(control, monitor, config=config, sleep=instant)


# ---------------------------------------------------------------------------
# telling one dead server apart from a dead network (§14)
# ---------------------------------------------------------------------------
def test_all_endpoints_answering_is_full_connectivity():
    network = FakeNetwork(online=True)
    report = asyncio.run(monitor_for(network).check(force=True))
    assert report.status == FULL
    assert report.online


def test_no_endpoint_answering_is_offline():
    network = FakeNetwork(online=False)
    report = asyncio.run(monitor_for(network).check(force=True))
    assert report.status == OFFLINE
    assert report.offline
    assert "no internet connection" in report.detail


def test_one_dead_service_is_partial_connectivity_not_an_outage():
    """A single server refusing must never be read as the laptop being off."""
    network = FakeNetwork(online=True)
    network.dead_hosts.add("b.example")
    report = asyncio.run(monitor_for(network).check(force=True))
    assert report.status == PARTIAL
    assert report.online is True


def test_partial_connectivity_does_not_pause_the_run(control):
    network = FakeNetwork(online=True)
    network.dead_hosts.add("c.example")
    supervisor = supervisor_for(control, monitor_for(network))
    asyncio.run(supervisor.gate(stage_no=2, probe=True))
    assert control.state == RUNNING
    assert supervisor.stats.network_pauses == 0


def test_failures_are_classified_before_a_probe_is_spent():
    assert classify_failures(["connection_error"] * 3) == OFFLINE
    assert classify_failures(["http_404", "connection_error"]) == PARTIAL
    assert classify_failures(["http_403", "http_404"]) == FULL
    assert classify_failures([]) == UNKNOWN


# ---------------------------------------------------------------------------
# §39.1-4 — losing the connection during each kind of work
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("where", [
    {"stage_no": 2, "task_detail": "retrieving a page"},
    {"stage_no": 3, "task_detail": "retrieving a PDF"},
    {"stage_no": 2, "task_detail": "downloading an image"},
    {"stage_no": 2, "source_id": "IC001-02", "task_detail": "between sources"},
])
def test_the_run_pauses_rather_than_recording_the_web_as_empty(control, where):
    network = FakeNetwork(online=False)
    supervisor = supervisor_for(control, monitor_for(network), max_offline_wait_s=0.001)

    with pytest.raises(RunPaused) as caught:
        asyncio.run(supervisor.gate(probe=True, **where))

    assert caught.value.state == PAUSED_NETWORK
    assert control.state == PAUSED_NETWORK
    assert control.last_checkpoint.stage_no == where["stage_no"]


def test_a_run_stopped_by_an_outage_is_not_recorded_as_complete(control, db):
    network = FakeNetwork(online=False)
    supervisor = supervisor_for(control, monitor_for(network), max_offline_wait_s=0.001)
    with pytest.raises(RunPaused):
        asyncio.run(supervisor.gate(stage_no=2, probe=True))
    status = db.scalar("SELECT status FROM runs WHERE run_id=?", (control.run_id,))
    assert status == "paused_network"


def test_the_outage_is_written_down_before_the_run_stops(control, db):
    """The checkpoint must exist even if the machine dies during the pause."""
    network = FakeNetwork(online=False)
    supervisor = supervisor_for(control, monitor_for(network), max_offline_wait_s=0.001)
    with pytest.raises(RunPaused):
        asyncio.run(supervisor.gate(stage_no=4, source_id="IC001-03",
                                    tasks_done=73, tasks_total=141, probe=True))
    row = db.query_one("SELECT * FROM run_control WHERE run_id=?", (control.run_id,))
    assert row["state"] == PAUSED_NETWORK
    assert (row["stage_no"], row["source_id"]) == (4, "IC001-03")
    assert (row["tasks_done"], row["tasks_total"]) == (73, 141)
    events = db.query("SELECT event FROM pause_events WHERE run_id=?", (control.run_id,))
    assert "connectivity_lost" in {e["event"] for e in events}


# ---------------------------------------------------------------------------
# §39.5-6 — restoration, and repeated loss
# ---------------------------------------------------------------------------
def test_the_run_resumes_by_itself_when_the_connection_returns(control):
    network = FakeNetwork(online=False)
    network.restore_after = 6          # a few failed rechecks, then back
    supervisor = supervisor_for(control, monitor_for(network))

    asyncio.run(supervisor.gate(stage_no=3, source_id="IC001-02", probe=True))

    assert control.state == RUNNING
    assert supervisor.stats.network_pauses == 1
    assert control.connectivity in (FULL, PARTIAL)


def test_a_connection_that_flickers_is_not_trusted_immediately(control):
    """The interface can come up before the network really works.

    A crawler that resumes on the first success burns a batch of live URLs on
    failures that look exactly like dead sources (brief §16.2), so the
    restoration is verified, and a connection that drops again pauses again.
    """
    class FlickeringNetwork(FakeNetwork):
        def __init__(self):
            super().__init__(online=False)
            self.checks = 0

        async def probe(self, url: str) -> bool:
            self.probes.append(url)
            # Four probes make one check. Check 2 says "back!", check 3 — the
            # verification — says "no, still gone", and only check 4 is real.
            self.checks = (len(self.probes) - 1) // 4
            return self.checks in (1, 3, 4, 5)

    network = FlickeringNetwork()
    supervisor = supervisor_for(control, monitor_for(network))

    asyncio.run(supervisor.gate(stage_no=2, probe=True))

    # It did not accept the false start: it went round again and paused twice.
    assert supervisor.stats.network_pauses == 2
    assert control.state == RUNNING


def test_repeated_loss_and_restoration_is_counted_each_time(control, db):
    network = FakeNetwork(online=False)
    network.restore_after = 5
    supervisor = supervisor_for(control, monitor_for(network))
    asyncio.run(supervisor.gate(stage_no=2, probe=True))
    assert control.state == RUNNING

    network.online = False
    network.restore_after = len(network.probes) + 5
    asyncio.run(supervisor.gate(stage_no=3, probe=True))

    assert supervisor.stats.network_pauses == 2
    assert control.pauses_network == 2
    events = [e["event"] for e in db.query(
        "SELECT event FROM pause_events WHERE run_id=? ORDER BY event_id",
        (control.run_id,))]
    assert events.count("connectivity_lost") == 2
    assert events.count("connectivity_restored") == 2


def test_cancelling_during_an_outage_ends_the_run(control, tmp_path):
    from dcr.control import RunCancelled

    network = FakeNetwork(online=False)
    supervisor = supervisor_for(control, monitor_for(network))
    request_cancel(tmp_path, "not waiting for the wifi")
    with pytest.raises(RunCancelled):
        asyncio.run(supervisor.gate(stage_no=2, probe=True))


# ---------------------------------------------------------------------------
# §39.7-8 — starting, and restarting, with no network at all
# ---------------------------------------------------------------------------
def test_starting_offline_pauses_instead_of_reporting_nothing_found(control):
    network = FakeNetwork(online=False)
    supervisor = supervisor_for(control, monitor_for(network), max_offline_wait_s=0.001)
    with pytest.raises(RunPaused) as caught:
        asyncio.run(supervisor.gate(stage_no=0, task_detail="the run is starting",
                                    probe=True))
    assert caught.value.state == PAUSED_NETWORK


def test_restarting_while_still_offline_finds_the_paused_run(db, community, tmp_path):
    from dcr.control import find_interrupted_runs

    run_id = make_run(db, community)
    control = RunControl(db, run_id=run_id, community_id=community,
                         control_dir=tmp_path / "control", poll_interval_s=0.0)
    network = FakeNetwork(online=False)
    supervisor = supervisor_for(control, monitor_for(network), max_offline_wait_s=0.001)
    with pytest.raises(RunPaused):
        asyncio.run(supervisor.gate(stage_no=2, tasks_done=40, tasks_total=90, probe=True))
    db.close()

    reopened = Database(db.path)
    try:
        found = find_interrupted_runs(reopened)
        assert len(found) == 1
        assert found[0].state == PAUSED_NETWORK
        assert found[0].tasks_done == 40
    finally:
        reopened.close()


# ---------------------------------------------------------------------------
# the fetcher must not condemn hosts during an outage (§13, §16)
# ---------------------------------------------------------------------------
def test_the_circuit_breaker_is_suspended_while_the_machine_is_offline(settings):
    from dcr.net.fetcher import Fetcher

    class FakeControl:
        connectivity = OFFLINE

    class FakeSupervisor:
        control = FakeControl()
        suspended = True

        def note_failure(self, error_type):
            pass

        def note_success(self):
            pass

    fetcher = Fetcher(user_agent="test", config=settings.app,
                      supervisor=FakeSupervisor())
    try:
        for _ in range(10):
            fetcher._note_host_failure("example.org", "connection refused")
        assert fetcher.unreachable_hosts() == {}, (
            "an outage must not be recorded as a finding about a live host")
    finally:
        asyncio.run(fetcher.aclose())


def test_circuits_opened_during_an_outage_are_cleared_on_reconnect(settings):
    from dcr.net.fetcher import Fetcher

    fetcher = Fetcher(user_agent="test", config=settings.app)
    try:
        for _ in range(10):
            fetcher._note_host_failure("example.org", "connection refused")
        assert "example.org" in fetcher.unreachable_hosts()
        cleared = fetcher.reset_host_failures()
        assert cleared == 1
        assert fetcher.unreachable_hosts() == {}
    finally:
        asyncio.run(fetcher.aclose())
