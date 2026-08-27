"""The run state machine: manual pause, restart survival, cancel.

These cover brief §38 — pausing at each kind of boundary, resuming, and
surviving the application being closed and reopened — and the parts of §22 and
§29 that keep manual pause, network pause and cancel three different things.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from dcr.control import (CANCELLED, COMPLETED, PAUSED_MANUAL, PAUSED_NETWORK,
                         PAUSING, RESUMING, RUNNING, RunCancelled, RunControl,
                         clear_requests, find_interrupted_runs, read_status,
                         request_cancel, request_pause, request_resume)
from dcr.db import Database, utcnow
from dcr.net.connectivity import (FULL, OFFLINE, PARTIAL, ConnectivityMonitor,
                                  classify_failures)
from dcr.supervisor import RunPaused, Supervisor


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def make_run(db: Database, community_id: str, run_id: str = "IC001-RUN001") -> str:
    db.insert("runs", {
        "run_id": run_id, "community_id": community_id, "mode": "FULL",
        "status": "running", "app_version": "test", "config_hash": "x",
        "started_utc": utcnow(),
    })
    return run_id


@pytest.fixture()
def control(db, community, tmp_path):
    run_id = make_run(db, community)
    return RunControl(db, run_id=run_id, community_id=community,
                      control_dir=tmp_path / "control", poll_interval_s=0.0)


def supervisor_for(control, monitor=None, **config):
    async def instant(_seconds: float) -> None:
        await asyncio.sleep(0)

    return Supervisor(control, monitor, config=config, sleep=instant)


# ---------------------------------------------------------------------------
# the state itself
# ---------------------------------------------------------------------------
def test_a_new_run_starts_running_and_says_so_in_the_database(control, db):
    assert control.state == RUNNING
    row = db.query_one("SELECT * FROM run_control WHERE run_id=?", (control.run_id,))
    assert row["state"] == RUNNING
    assert db.scalar("SELECT status FROM runs WHERE run_id=?", (control.run_id,)) == "running"


def test_manual_and_network_pause_are_never_the_same_state(control, db):
    control.enter_paused("manual", "the researcher needs the laptop")
    assert control.state == PAUSED_MANUAL
    assert db.scalar("SELECT status FROM runs WHERE run_id=?",
                     (control.run_id,)) == "paused_manual"

    control.enter_resuming("manual", "")
    control.enter_running()
    control.enter_paused("network", "no internet")
    assert control.state == PAUSED_NETWORK
    assert db.scalar("SELECT status FROM runs WHERE run_id=?",
                     (control.run_id,)) == "paused_network"

    events = db.query("SELECT * FROM pause_events WHERE run_id=? ORDER BY event_id",
                      (control.run_id,))
    kinds = {(e["event"], e["kind"]) for e in events}
    assert ("paused", "manual") in kinds
    assert ("paused", "network") in kinds


def test_a_paused_run_is_never_recorded_as_complete(control, db):
    """The distinction the whole design exists for (brief §13)."""
    control.enter_paused("network", "the connection dropped")
    status = db.scalar("SELECT status FROM runs WHERE run_id=?", (control.run_id,))
    assert status == "paused_network"
    assert status != "complete"


def test_cancel_is_not_a_pause_and_is_not_resumable(control, db):
    control.enter_cancelled("the researcher ended the run")
    assert control.state == CANCELLED
    row = db.query_one("SELECT * FROM run_control WHERE run_id=?", (control.run_id,))
    assert row["resumable"] == 0
    assert find_interrupted_runs(db) == []


def test_the_checkpoint_records_where_the_run_had_got_to(control, db):
    control.checkpoint(stage_no=3, stage_name="documents", source_id="IC001-02",
                       task_ref="abc123", tasks_done=73, tasks_total=141)
    row = db.query_one("SELECT * FROM run_control WHERE run_id=?", (control.run_id,))
    assert (row["stage_no"], row["source_id"], row["task_ref"]) == (3, "IC001-02", "abc123")
    assert (row["tasks_done"], row["tasks_total"]) == (73, 141)
    assert control.progress_line() == "73/141 tasks complete."


def test_the_status_file_is_readable_by_another_process(control, tmp_path):
    control.checkpoint(stage_no=4, tasks_done=10, tasks_total=20)
    status = read_status(tmp_path)
    assert status is not None
    assert status["state"] == RUNNING
    assert status["tasks_done"] == 10


# ---------------------------------------------------------------------------
# requests from outside the process
# ---------------------------------------------------------------------------
def test_a_pause_request_from_another_process_is_seen(control, tmp_path):
    request_pause(tmp_path, "please stop")
    request = control.poll_request(force=True)
    assert request is not None
    assert request.state == PAUSED_MANUAL
    assert request.reason == "please stop"


def test_a_resume_request_clears_a_pending_pause(tmp_path):
    request_pause(tmp_path, "stop")
    request_resume(tmp_path, "go")
    directory = tmp_path / "control"
    assert not (directory / "pause.request").exists()
    assert (directory / "resume.request").exists()


def test_cancel_outranks_a_pause_left_lying_around(control, tmp_path):
    request_pause(tmp_path, "stop")
    request_cancel(tmp_path, "actually, end it")
    request = control.poll_request(force=True)
    assert request.state == CANCELLED


def test_clearing_a_request_stops_it_pausing_the_run_twice(control, tmp_path):
    request_pause(tmp_path, "stop")
    assert control.poll_request(force=True) is not None
    control.clear_request()
    assert control.poll_request(force=True) is None


# ---------------------------------------------------------------------------
# §38 — pausing at each kind of boundary, and resuming
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("boundary", [
    {"stage_no": 2, "task_detail": "between pages"},
    {"stage_no": 2, "source_id": "IC001-01", "task_detail": "while a page crawl is running"},
    {"stage_no": 3, "task_detail": "during document processing"},
    {"stage_no": 2, "task_detail": "during image processing"},
    {"stage_no": 2, "source_id": "IC001-03", "task_detail": "before a new source"},
])
def test_pause_is_taken_at_any_boundary_and_records_where(control, tmp_path, boundary):
    supervisor = supervisor_for(control, manual_pause_behavior="exit")
    request_pause(tmp_path, "researcher pressed PAUSE")

    with pytest.raises(RunPaused) as caught:
        asyncio.run(supervisor.gate(**boundary))

    assert caught.value.state == PAUSED_MANUAL
    assert control.state == PAUSED_MANUAL
    checkpoint = control.last_checkpoint
    assert checkpoint.stage_no == boundary["stage_no"]
    if "source_id" in boundary:
        assert checkpoint.source_id == boundary["source_id"]


def test_resume_after_a_manual_pause_continues_in_place(control, tmp_path):
    """`wait` behaviour: the process stays alive and picks the work back up."""
    supervisor = supervisor_for(control, manual_pause_behavior="wait",
                                resume_poll_interval_s=0.0)
    request_pause(tmp_path, "back in five minutes")

    async def scenario():
        async def researcher_returns():
            await asyncio.sleep(0.05)
            request_resume(tmp_path, "back now")

        await asyncio.gather(supervisor.gate(stage_no=2, tasks_done=7, tasks_total=20),
                             researcher_returns())

    asyncio.run(scenario())
    assert control.state == RUNNING
    assert supervisor.stats.manual_pauses == 1


def test_cancelling_while_paused_ends_the_run(control, tmp_path):
    supervisor = supervisor_for(control, manual_pause_behavior="wait",
                                resume_poll_interval_s=0.0)
    request_pause(tmp_path, "stop")

    async def scenario():
        async def researcher_cancels():
            await asyncio.sleep(0.05)
            request_cancel(tmp_path, "changed my mind")

        await asyncio.gather(supervisor.gate(stage_no=2), researcher_cancels())

    with pytest.raises(RunCancelled):
        asyncio.run(scenario())
    assert control.state == CANCELLED


def test_cancel_at_a_gate_raises_and_does_not_pause(control, tmp_path):
    supervisor = supervisor_for(control)
    request_cancel(tmp_path, "end it")
    with pytest.raises(RunCancelled):
        asyncio.run(supervisor.gate(stage_no=1))
    assert control.state == CANCELLED


# ---------------------------------------------------------------------------
# §21, §25 — surviving the application being closed
# ---------------------------------------------------------------------------
def test_a_manual_pause_survives_the_application_closing(db, community, tmp_path):
    """Press PAUSE, close PyCharm, come back on Monday (brief §21)."""
    run_id = make_run(db, community)
    control = RunControl(db, run_id=run_id, community_id=community,
                         control_dir=tmp_path / "control", poll_interval_s=0.0)
    control.checkpoint(stage_no=4, stage_name="archive", source_id="IC001-02",
                       tasks_done=73, tasks_total=141)
    control.enter_paused("manual", "the researcher needed the laptop")
    db.close()

    # A completely new process, opening the same database file.
    reopened = Database(db.path)
    try:
        found = find_interrupted_runs(reopened)
        assert len(found) == 1
        run = found[0]
        assert run.state == PAUSED_MANUAL
        assert run.was_manual
        assert run.stage_no == 4
        assert run.source_id == "IC001-02"
        assert run.tasks_done == 73
        assert "needed the laptop" in run.pause_reason
    finally:
        reopened.close()


def test_a_network_pause_also_survives_a_restart(db, community, tmp_path):
    run_id = make_run(db, community)
    control = RunControl(db, run_id=run_id, community_id=community,
                         control_dir=tmp_path / "control", poll_interval_s=0.0)
    control.enter_paused("network", "no internet connection")
    db.close()

    reopened = Database(db.path)
    try:
        found = find_interrupted_runs(reopened)
        assert len(found) == 1
        assert found[0].state == PAUSED_NETWORK
        assert not found[0].was_manual
    finally:
        reopened.close()


def test_a_run_left_running_by_a_power_cut_is_offered_for_resume(db, community, tmp_path):
    """RUNNING must never be read as finished (brief §25)."""
    run_id = make_run(db, community)
    RunControl(db, run_id=run_id, community_id=community,
               control_dir=tmp_path / "control", poll_interval_s=0.0)
    # No clean shutdown: the state is still RUNNING.
    found = find_interrupted_runs(db)
    assert [r.state for r in found] == [RUNNING]


def test_a_completed_run_is_not_offered_for_resume(control, db):
    control.finish(COMPLETED)
    assert find_interrupted_runs(db) == []


def test_the_unfinished_run_can_describe_itself_to_the_researcher(db, community, tmp_path):
    run_id = make_run(db, community)
    control = RunControl(db, run_id=run_id, community_id=community,
                         control_dir=tmp_path / "control", poll_interval_s=0.0)
    control.checkpoint(stage_no=3, stage_name="documents", source_id="IC001-02",
                       tasks_done=12, tasks_total=40)
    control.enter_paused("manual", "lunch")
    description = find_interrupted_runs(db)[0].describe()
    assert "PAUSED_MANUAL" in description
    assert "Stage 3" in description
    assert "12/40" in description


# ---------------------------------------------------------------------------
# Where the crawl can be stopped
# ---------------------------------------------------------------------------
def test_every_long_stage_offers_a_pause_boundary():
    """A pause must not have to wait out a whole academic sweep.

    The crawler gates between batches, which covers stages 2, 3 and 7. Stages
    4, 5, 6 and 8 spend their time in loops of their own — one archive domain,
    one database, one portal at a time — so each of those loops has to offer a
    boundary too, or PAUSE would appear to do nothing for minutes.
    """
    import inspect

    from dcr import runner as runner_module

    source = inspect.getsource(runner_module)
    for stage_no in (4, 5, 6, 8):
        assert f"stage_no={stage_no}, stage_name=STAGE_NAMES[{stage_no}]" in source, (
            f"stage {stage_no} has no pause boundary inside its own loop")


def test_the_crawler_gates_between_batches():
    import inspect

    from dcr.crawl import crawler as crawler_module

    source = inspect.getsource(crawler_module.Crawler.run)
    assert "await self.supervisor.gate(" in source
    assert source.index("await self.supervisor.gate(") < source.index("next_batch"), (
        "the gate must come before the next batch is claimed, or a pause would "
        "leave URLs in_flight")
