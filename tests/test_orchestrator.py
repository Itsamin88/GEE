"""Many communities at once: the queue, the scheduler and surviving workers.

Every test here runs REAL spawned processes. Mocking the process boundary would
test the thing that is not hard: what makes multi-community running difficult is
that a worker can die in ways Python cannot catch, and that is only observable
with an actual operating-system process and an actual exit code.
"""

from __future__ import annotations

import json
import multiprocessing
import time
from pathlib import Path

import pytest

from dcr.orchestrator.governor import (CPU_GROW_PCT, Decision, ResourceGovernor,
                                       ResourceSample)
from dcr.orchestrator.hosts import BrokerClient, HostBroker, is_shared_host
from dcr.orchestrator.plan import (CommunityJob, RunPlan, build_plan,
                                   classify_address, estimate_workload, value_score)
from dcr.orchestrator.pool import WorkerPool
from dcr.orchestrator.scheduler import RunScheduler
from dcr.orchestrator.store import (AGE_CAP, CANCELLED, COMPLETED, FAILED,
                                    PAUSED_MANUAL,
                                    QUEUED, RUNNING, RunStore)

from fixtures.fake_worker import (counting_worker, fake_worker,
                                  host_pressure_worker)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def store(tmp_path) -> RunStore:
    with RunStore(tmp_path / "run.sqlite3") as opened:
        yield opened


def make_entries(count: int, *, urls_each: int = 2, prefix: str = "Community"):
    return [
        {"name": f"{prefix} {index:03d}",
         "urls": [f"https://c{index}-{n}.example" for n in range(urls_each)],
         "country": "Portugal"}
        for index in range(1, count + 1)
    ]


def queue_run(store: RunStore, tmp_path, entries, *, run_id="R1", behaviour="ok",
              work_s=0.05, extra=None) -> RunPlan:
    plan = build_plan(entries, run_id=run_id, output_root=tmp_path / "out")
    store.create_run(run_id, mode="FULL", output_root=tmp_path / "out")
    for job in plan.jobs:
        store.add_job(run_id, job.as_dict())
    return plan


def run_scheduler(store, plan, tmp_path, *, target, payload_extra,
                  workers=4, max_ticks=600, tick_s=0.02, governor=None):
    pool = WorkerPool(target=target, heartbeat_timeout_s=3.0, shutdown_grace_s=2.0)
    scheduler = RunScheduler(
        store, plan, output_root=tmp_path / "out", pool=pool,
        governor=governor or ResourceGovernor(minimum=1, maximum=workers,
                                              start=workers, settle_s=0.0),
        config={"tick_seconds": tick_s, "sample_seconds": 0.05, "max_attempts": 2},
        payload_extra=payload_extra,
    )
    scheduler.run(max_ticks=max_ticks)
    return scheduler


# ---------------------------------------------------------------------------
# §2 — the number of communities is not hard-coded
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("count", [1, 5, 20, 212])
def test_any_number_of_communities_can_be_queued(store, tmp_path, count):
    plan = queue_run(store, tmp_path, make_entries(count))
    assert len(plan.jobs) == count
    assert store.counts("R1")["TOTAL"] == count
    assert len({job.site_id for job in plan.jobs}) == count, (
        "site_ids must be unique: they are the workbook's key")
    assert len({job.database_path for job in plan.jobs}) == count, (
        "each community must have its own database, or a failure in one can "
        "reach another")


def test_each_community_gets_its_own_directory_and_database(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(3))
    for job in plan.jobs:
        assert job.site_id in job.output_dir
        assert Path(job.database_path).parent == Path(job.output_dir)
        assert Path(job.database_path).name == "research.sqlite3"


# ---------------------------------------------------------------------------
# §45, §48 — sizing before anything is fetched
# ---------------------------------------------------------------------------
def test_a_bigger_source_set_is_estimated_as_more_work():
    small, *_ = estimate_workload(["https://a.example"])
    large, *_ = estimate_workload([f"https://a{i}.example" for i in range(6)])
    assert large > small


def test_the_estimate_is_a_range_and_says_what_it_was_based_on():
    units, low, high, basis = estimate_workload(
        ["https://a.example", "https://doi.org/10.1/x"], country="Portugal")
    assert low < high
    assert "2 supplied address" in basis
    assert "Portugal" in basis


@pytest.mark.parametrize("url,expected", [
    ("https://tamera.org", "website"),
    ("https://www.facebook.com/tamera", "social"),
    ("https://youtube.com/@tamera", "video"),
    ("https://doi.org/10.1234/abc", "academic"),
    ("https://ecovillage.org/projects/x", "directory"),
    ("https://web.archive.org/web/2009/x.org", "archive"),
    ("https://x.org/report-2019.pdf", "document"),
])
def test_addresses_are_classified_for_sizing(url, expected):
    assert classify_address(url) == expected


def test_independent_hosts_are_worth_more_than_more_pages_of_one():
    spread = value_score(["https://a.example", "https://b.example", "https://c.example"])
    concentrated = value_score(["https://a.example/1", "https://a.example/2",
                                "https://a.example/3"])
    assert spread > concentrated, (
        "the protocol wants independent sources, not more pages of one")


def test_wall_clock_is_never_claimed_to_be_linear_in_workers(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(40))
    low_1, high_1 = plan.wall_clock_estimate_s(workers_low=1, workers_high=1)
    low_16, high_16 = plan.wall_clock_estimate_s(workers_low=16, workers_high=16)
    speedup = high_1 / high_16
    assert 1 < speedup < 16, (
        f"claimed a {speedup:.1f}x speed-up from 16 workers; parallel speed-up "
        "is never linear and the estimate must not pretend otherwise")


def test_the_estimate_never_beats_the_longest_single_community(store, tmp_path):
    entries = make_entries(2, urls_each=1)
    entries[0]["urls"] = [f"https://big-{n}.example" for n in range(9)]
    plan = build_plan(entries, run_id="R1", output_root=tmp_path / "out")
    longest = max(job.estimate_high_s for job in plan.jobs)
    _, high = plan.wall_clock_estimate_s(workers_low=16, workers_high=16)
    assert high >= longest


def test_the_queue_table_is_what_the_researcher_sees(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(3))
    table = plan.table()
    assert "Estimated workload" in table
    assert "C001" in table and "QUEUED" in table


# ---------------------------------------------------------------------------
# §5 — fairness: one huge community must not starve the rest
# ---------------------------------------------------------------------------
def test_large_communities_are_started_first(store, tmp_path):
    entries = [
        {"name": "Small", "urls": ["https://small.example"]},
        {"name": "Huge", "urls": [f"https://huge-{n}.example" for n in range(8)]},
        {"name": "Medium", "urls": ["https://m1.example", "https://m2.example"]},
    ]
    plan = build_plan(entries, run_id="R1", output_root=tmp_path / "out")
    assert plan.jobs[0].name == "Huge", (
        "the longest job must start early or it runs alone at the end")


def test_waiting_raises_a_communitys_priority(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(3))
    small = min(plan.jobs, key=lambda j: j.priority)
    # Backdate it an hour.
    store.execute(
        "UPDATE jobs SET queued_utc = datetime('now', '-60 minutes') WHERE job_id = ?",
        (small.job_id,))
    store.age_priorities("R1")
    aged = store.job(small.job_id)
    assert aged.aged_priority > aged.priority
    assert aged.aged_priority == pytest.approx(aged.priority + 60.0, abs=2.0)


def test_ageing_is_capped_so_it_cannot_outrank_everything_for_ever(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(2))
    store.execute("UPDATE jobs SET queued_utc = datetime('now', '-40 days')")
    store.age_priorities("R1")
    for job in store.jobs("R1"):
        assert job.aged_priority <= job.priority + AGE_CAP + 0.01


def test_an_aged_community_is_claimed_before_a_fresh_bigger_one(store, tmp_path):
    entries = [
        {"name": "Small", "urls": ["https://small.example"]},
        {"name": "Huge", "urls": [f"https://huge-{n}.example" for n in range(8)]},
    ]
    plan = build_plan(entries, run_id="R1", output_root=tmp_path / "out")
    store.create_run("R1", mode="FULL", output_root=tmp_path / "out")
    for job in plan.jobs:
        store.add_job("R1", job.as_dict())
    small = next(j for j in plan.jobs if j.name == "Small")
    store.execute(
        "UPDATE jobs SET queued_utc = datetime('now', '-120 minutes') WHERE job_id = ?",
        (small.job_id,))
    store.age_priorities("R1")
    claimed = store.claim_next("R1", worker="w1")
    assert claimed.name == "Small", "the community that has waited longest was skipped"


def test_two_workers_cannot_claim_the_same_community(store, tmp_path):
    queue_run(store, tmp_path, make_entries(1))
    first = store.claim_next("R1", worker="w1")
    second = store.claim_next("R1", worker="w2")
    assert first is not None and second is None


# ---------------------------------------------------------------------------
# real processes: the queue actually runs
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_a_whole_queue_runs_to_completion_in_real_processes(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(6))
    scheduler = run_scheduler(store, plan, tmp_path, target=fake_worker,
                              payload_extra={"behaviour": "ok", "work_s": 0.1},
                              workers=3)
    counts = store.counts("R1")
    assert counts[COMPLETED] == 6, counts
    assert counts[QUEUED] == 0
    totals = store.totals("R1")
    assert totals["pages"] > 0
    assert scheduler.stats.dispatched == 6


@pytest.mark.slow
def test_the_researcher_does_not_have_to_move_between_communities(store, tmp_path):
    """Six communities, two workers, one START (brief §7)."""
    plan = queue_run(store, tmp_path, make_entries(6))
    run_scheduler(store, plan, tmp_path, target=fake_worker,
                  payload_extra={"behaviour": "ok", "work_s": 0.05}, workers=2)
    assert store.counts("R1")[COMPLETED] == 6


# ---------------------------------------------------------------------------
# §39 — one failure must not kill the run
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_a_worker_that_segfaults_costs_one_community(store, tmp_path):
    entries = make_entries(5)
    plan = queue_run(store, tmp_path, entries)
    doomed = plan.jobs[2].job_id

    def target(payload, events, broker, results):
        if payload["job_id"] == doomed:
            payload = {**payload, "behaviour": "crash"}
        fake_worker(payload, events, broker, results)

    # A closure cannot be pickled for spawn, so the choice is made in the child
    # from the payload instead.
    for job in plan.jobs:
        store.update_job(job.job_id, {})
    pool = WorkerPool(target=fake_worker, heartbeat_timeout_s=3.0,
                      shutdown_grace_s=2.0)
    scheduler = RunScheduler(
        store, plan, output_root=tmp_path / "out", pool=pool,
        governor=ResourceGovernor(minimum=1, maximum=2, start=2, settle_s=0.0),
        config={"tick_seconds": 0.02, "sample_seconds": 0.05, "max_attempts": 2},
        payload_extra={"behaviour": "ok", "work_s": 0.05},
    )
    # Make exactly one community crash, by giving it its own behaviour.
    store.update_job(doomed, {"detail": "will crash"})
    scheduler._payload_extra = {"behaviour": "ok", "work_s": 0.05}
    original = scheduler._dispatch

    def dispatch(job):
        if job.job_id == doomed:
            scheduler._payload_extra = {"behaviour": "crash", "work_s": 0.05}
        else:
            scheduler._payload_extra = {"behaviour": "ok", "work_s": 0.05}
        original(job)

    scheduler._dispatch = dispatch
    scheduler.run(max_ticks=800)

    counts = store.counts("R1")
    assert counts[COMPLETED] == 4, f"the crash took other communities with it: {counts}"
    assert counts[FAILED] == 1
    failed = store.job(doomed)
    assert failed.final_status == "FAILED_TECHNICALLY"
    assert failed.attempts >= 2, "a crash should be retried once before giving up"
    errors = [dict(row) for row in store.errors("R1")]
    assert any(row["error_class"] == "WORKER_CRASH" for row in errors)


@pytest.mark.slow
def test_a_community_that_fails_cleanly_is_recorded_not_retried_for_ever(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(3))
    run_scheduler(store, plan, tmp_path, target=fake_worker,
                  payload_extra={"behaviour": "fail", "work_s": 0.05}, workers=2)
    counts = store.counts("R1")
    assert counts[FAILED] == 3
    for job in store.jobs("R1"):
        assert job.attempts == 1, (
            "a clean failure is a result, not a crash; retrying it wastes the run")


@pytest.mark.slow
def test_a_blocked_community_is_a_result_not_a_failure(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(2))
    run_scheduler(store, plan, tmp_path, target=fake_worker,
                  payload_extra={"behaviour": "blocked", "work_s": 0.05}, workers=2)
    for job in store.jobs("R1"):
        assert job.final_status == "PARTIAL_BLOCKED"


@pytest.mark.slow
def test_a_hung_worker_is_terminated_and_the_slot_reused(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(3))
    pool = WorkerPool(target=fake_worker, heartbeat_timeout_s=0.6,
                      shutdown_grace_s=1.0)
    scheduler = RunScheduler(
        store, plan, output_root=tmp_path / "out", pool=pool,
        governor=ResourceGovernor(minimum=1, maximum=1, start=1, settle_s=0.0),
        config={"tick_seconds": 0.05, "sample_seconds": 1.0, "max_attempts": 1},
        payload_extra={"behaviour": "hang"},
    )
    scheduler.run(max_ticks=400)
    assert scheduler.stats.hung >= 1
    assert not pool.running
    assert any(dict(row)["error_class"] == "WORKER_HUNG" for row in store.errors("R1"))


# ---------------------------------------------------------------------------
# §3, §96 — concurrency is measured, not asserted
# ---------------------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.parametrize("workers", [2, 4])
def test_communities_really_do_overlap(store, tmp_path, workers):
    trace = tmp_path / "trace.tsv"
    plan = queue_run(store, tmp_path, make_entries(workers * 3))
    run_scheduler(store, plan, tmp_path, target=counting_worker,
                  payload_extra={"work_s": 0.4, "trace_path": str(trace)},
                  workers=workers, max_ticks=2000, tick_s=0.02)
    rows = [line.split("\t") for line in trace.read_text().splitlines() if line]
    assert len(rows) == workers * 3
    intervals = sorted((float(r[1]), float(r[2])) for r in rows)
    peak = 0
    for start, _ in intervals:
        overlapping = sum(1 for s, e in intervals if s <= start < e)
        peak = max(peak, overlapping)
    assert peak >= 2, f"nothing overlapped: peak concurrency was {peak}"
    assert peak <= workers, f"more workers ran than allowed: {peak} > {workers}"
    assert len({r[3] for r in rows}) > 1, "every community ran in the same process"


# ---------------------------------------------------------------------------
# §33-§36 — the researcher's controls
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_cancel_all_stops_starting_and_keeps_what_is_done(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(8))
    pool = WorkerPool(target=fake_worker, heartbeat_timeout_s=5.0,
                      shutdown_grace_s=1.0)
    scheduler = RunScheduler(
        store, plan, output_root=tmp_path / "out", pool=pool,
        governor=ResourceGovernor(minimum=1, maximum=2, start=2, settle_s=0.0),
        config={"tick_seconds": 0.02, "sample_seconds": 1.0},
        payload_extra={"behaviour": "ok", "work_s": 0.2},
    )
    # Let two finish, then cancel.
    for _ in range(40):
        scheduler.tick()
        time.sleep(0.02)
        if store.counts("R1")[COMPLETED] >= 2:
            break
    completed_before = store.counts("R1")[COMPLETED]
    scheduler.cancel_all("enough for today")
    for _ in range(60):
        scheduler.tick()
        if scheduler.finished():
            break
        time.sleep(0.02)
    scheduler._shutdown()

    counts = store.counts("R1")
    assert counts[COMPLETED] >= completed_before, "completed work was lost"
    assert counts[CANCELLED] > 0
    assert counts[QUEUED] == 0, "cancelled communities were left queued"
    assert store.run_status("R1") == "CANCELLED"


@pytest.mark.slow
def test_pause_all_stops_starting_new_communities(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(6))
    pool = WorkerPool(target=fake_worker, heartbeat_timeout_s=5.0,
                      shutdown_grace_s=1.0)
    scheduler = RunScheduler(
        store, plan, output_root=tmp_path / "out", pool=pool,
        governor=ResourceGovernor(minimum=1, maximum=2, start=2, settle_s=0.0),
        config={"tick_seconds": 0.02, "sample_seconds": 1.0},
        payload_extra={"behaviour": "ok", "work_s": 0.05},
    )
    scheduler.pause_all("lunch")
    for _ in range(20):
        scheduler.tick()
        time.sleep(0.01)
    assert scheduler.snapshot()["paused"]
    assert store.counts("R1")[QUEUED] >= 4, "PAUSE ALL did not stop the queue"

    scheduler.resume_all("back")
    scheduler.run(max_ticks=600)
    assert store.counts("R1")[COMPLETED] == 6, "RESUME ALL did not restart the queue"


def test_pausing_one_community_leaves_the_others_alone(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(4))
    pool = WorkerPool(target=fake_worker)
    scheduler = RunScheduler(store, plan, output_root=tmp_path / "out", pool=pool)
    victim = plan.jobs[1].job_id
    assert scheduler.pause_community(victim, "inspecting this one")
    from dcr.control import PAUSE_FILE, control_dir_for

    assert (control_dir_for(Path(plan.jobs[1].output_dir)) / PAUSE_FILE).exists()
    for other in plan.jobs:
        if other.job_id == victim:
            continue
        assert not (control_dir_for(Path(other.output_dir)) / PAUSE_FILE).exists(), (
            "pausing one community reached another")
    pool.close()


# ---------------------------------------------------------------------------
# §3, §49, §97 — adaptive concurrency
# ---------------------------------------------------------------------------
def test_the_governor_starts_at_a_defensible_number():
    governor = ResourceGovernor(minimum=1, maximum=16)
    assert 1 <= governor.target <= 8, (
        "starting at the maximum means the first minutes are spent recovering "
        "from a bad guess")


def test_memory_pressure_reduces_workers_immediately():
    governor = ResourceGovernor(minimum=1, maximum=16, start=10, settle_s=999)
    decision = governor.decide(running=10, queued=50,
                               sample=ResourceSample(cpu_pct=40, memory_pct=95,
                                                     memory_available_mb=200,
                                                     measured=True))
    assert decision.target < 10
    assert "memory" in decision.reason


def test_idle_waiting_grows_the_worker_count():
    governor = ResourceGovernor(minimum=1, maximum=16, start=8, settle_s=0.0)
    decision = governor.decide(running=8, queued=40,
                               sample=ResourceSample(cpu_pct=20, memory_pct=40,
                                                     memory_available_mb=8000,
                                                     measured=True))
    assert decision.target == 9
    assert "waiting on the network" in decision.reason


def test_an_idle_worker_means_no_more_are_needed():
    governor = ResourceGovernor(minimum=1, maximum=16, start=8, settle_s=0.0)
    decision = governor.decide(running=3, queued=40,
                               sample=ResourceSample(cpu_pct=10, memory_pct=30,
                                                     memory_available_mb=8000,
                                                     measured=True))
    assert decision.target == 8


def test_a_worker_count_measured_to_be_worse_is_not_returned_to():
    """The brief's actual instruction: never make more workers make it slower."""
    governor = ResourceGovernor(minimum=1, maximum=16, start=12, settle_s=0.0)
    for _ in range(5):
        governor.note_completion(workers=8, active_s=60)      # 1.0 per worker-min
    for _ in range(5):
        governor.note_completion(workers=12, active_s=200)    # 0.3 per worker-min
    decision = governor.decide(running=12, queued=40,
                               sample=ResourceSample(cpu_pct=20, memory_pct=30,
                                                     memory_available_mb=8000,
                                                     measured=True))
    assert decision.target == 8
    assert "per worker-minute" in decision.reason

    # And it does not creep back up.
    for _ in range(3):
        decision = governor.decide(running=8, queued=40,
                                   sample=ResourceSample(cpu_pct=20, memory_pct=30,
                                                         memory_available_mb=8000,
                                                         measured=True))
    assert decision.target <= 8


def test_without_psutil_the_governor_is_conservative_and_says_so():
    governor = ResourceGovernor(minimum=1, maximum=16, start=4, settle_s=0.0)
    decision = governor.decide(running=4, queued=20, sample=ResourceSample(measured=False))
    assert decision.target == 5
    assert "no resource measurements" in decision.reason
    assert governor.report()["resource_measurements_available"] in (True, False)


def test_nothing_queued_means_no_change():
    governor = ResourceGovernor(minimum=1, maximum=16, start=6, settle_s=0.0)
    decision = governor.decide(running=2, queued=0,
                               sample=ResourceSample(cpu_pct=5, memory_pct=20,
                                                     memory_available_mb=9000,
                                                     measured=True))
    assert decision.target == 6


# ---------------------------------------------------------------------------
# §4, §40 — sixteen communities is not sixteen requests to one host
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("host,shared", [
    ("web.archive.org", True),
    ("api.crossref.org", True),
    ("scholar.google.com", True),
    ("tamera.org", False),
    ("www.pourgues.org", False),
    ("notweb.archive.org.evil.example", False),
])
def test_only_the_hosts_every_community_reaches_are_brokered(host, shared):
    assert is_shared_host(host) is shared


def test_a_rate_limited_host_is_slowed_for_every_community():
    broker = HostBroker()
    broker.acquire("web.archive.org", community="C001")
    before = broker._state("web.archive.org").delay_s
    broker.release("web.archive.org", status=429)
    after = broker._state("web.archive.org").delay_s
    assert after > before, (
        "a 429 for C001 must slow C002 as well, or the run gets banned")


def test_a_missing_broker_never_stops_a_crawl():
    client = BrokerClient(None, community="C001")
    assert client.acquire("https://web.archive.org/web/2009/x") is True
    client.release("https://web.archive.org/web/2009/x", status=200)
    assert client.stats()["broker_available"] is False


class _BrokenBroker:
    def shared(self, host):
        raise RuntimeError("the parent has gone away")

    def acquire(self, *a, **k):
        raise RuntimeError("gone")

    def release(self, *a, **k):
        raise RuntimeError("gone")


def test_a_broken_broker_degrades_to_crawling_alone():
    client = BrokerClient(_BrokenBroker(), community="C001")
    assert client.acquire("web.archive.org") is True
    client.release("web.archive.org", status=200)
    assert client.broker_failures >= 1


def test_a_jammed_host_defers_rather_than_holding_a_worker():
    broker = HostBroker()
    broker.acquire("scholar.google.com", community="C001")
    # Concurrency for scholar is 1, so a second asker with no patience is told
    # to come back rather than made to wait.
    waited = broker.acquire("scholar.google.com", community="C002", timeout_s=0.05)
    assert waited < 0
    assert broker._state("scholar.google.com").deferred == 1


@pytest.mark.slow
def test_many_communities_do_not_become_many_concurrent_requests(tmp_path):
    """The whole point of §4, measured across real processes."""
    trace = tmp_path / "hosts.tsv"
    manager = multiprocessing.Manager()
    # A Manager proxy is how a worker reaches the parent's broker on Windows as
    # well as on POSIX, so the test uses the real mechanism.
    from dcr.orchestrator import hosts as hosts_mod

    manager.register  # noqa: B018 - documents that we are using the real Manager
    ctx = multiprocessing.get_context("spawn")
    processes = []
    shared = _ManagedBroker(manager)
    for index in range(6):
        payload = {"job_id": f"C{index:03d}", "worker": f"w{index}",
                   "host": "web.archive.org", "requests": 3,
                   "trace_path": str(trace)}
        process = ctx.Process(target=host_pressure_worker,
                              args=(payload, None, shared.proxy, None))
        process.start()
        processes.append(process)
    for process in processes:
        process.join(timeout=60)

    rows = [line.split("\t") for line in trace.read_text().splitlines() if line]
    assert len(rows) >= 12
    intervals = sorted((float(r[1]), float(r[2])) for r in rows)
    peak = max(sum(1 for s, e in intervals if s <= start < e)
               for start, _ in intervals)
    assert peak <= 2, (
        f"{peak} concurrent requests reached web.archive.org from 6 communities; "
        "the broker is meant to hold it to 2")
    manager.shutdown()


class _ManagedBroker:
    """Exposes a real HostBroker to spawned children through a Manager."""

    def __init__(self, manager):
        from multiprocessing.managers import BaseManager

        from dcr.orchestrator.hosts import HostBroker

        class _Manager(BaseManager):
            pass

        _Manager.register("HostBroker", HostBroker,
                          exposed=("acquire", "release", "defer", "shared",
                                   "snapshot", "stats"))
        self._manager = _Manager()
        self._manager.start()
        self.proxy = self._manager.HostBroker()


# ---------------------------------------------------------------------------
# §8 — isolation
# ---------------------------------------------------------------------------
def test_a_communitys_failure_leaves_no_trace_on_another(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(3))
    store.add_error("R1", job_id=plan.jobs[0].job_id, error_class="PARSER_ERROR",
                    message="a corrupt PDF")
    store.update_job(plan.jobs[0].job_id, {"state": FAILED,
                                           "final_status": "FAILED_TECHNICALLY"})
    for job in plan.jobs[1:]:
        row = store.job(job.job_id)
        assert row.state == QUEUED
        assert not row.last_error


def test_the_queue_survives_being_closed_and_reopened(tmp_path):
    path = tmp_path / "run.sqlite3"
    with RunStore(path) as first:
        first.create_run("R1", mode="FULL", output_root=tmp_path)
        plan = build_plan(make_entries(4), run_id="R1", output_root=tmp_path / "out")
        for job in plan.jobs:
            first.add_job("R1", job.as_dict())
        first.update_job(plan.jobs[0].job_id, {"state": COMPLETED,
                                               "final_status": "COMPLETE"})
    with RunStore(path) as second:
        counts = second.counts("R1")
        assert counts[COMPLETED] == 1 and counts[QUEUED] == 3
        assert second.unfinished_runs(), "the interrupted run must be findable"


# ---------------------------------------------------------------------------
# §50 — what the researcher sees
# ---------------------------------------------------------------------------
def test_the_snapshot_carries_everything_the_dashboard_needs(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(5))
    pool = WorkerPool(target=fake_worker)
    scheduler = RunScheduler(store, plan, output_root=tmp_path / "out", pool=pool)
    snapshot = scheduler.snapshot()
    for key in ("counts", "workers", "wall_s", "remaining_low_s", "remaining_high_s",
                "totals", "live"):
        assert key in snapshot
    assert snapshot["counts"][QUEUED] == 5
    assert snapshot["workers"]["target"] >= 1
    pool.close()


def test_the_remaining_estimate_uses_real_durations_once_it_has_them(store, tmp_path):
    plan = queue_run(store, tmp_path, make_entries(10))
    pool = WorkerPool(target=fake_worker)
    scheduler = RunScheduler(store, plan, output_root=tmp_path / "out", pool=pool)
    before_low, before_high = scheduler._remaining_estimate(store.counts("R1"))
    for job in plan.jobs[:4]:
        store.update_job(job.job_id, {"state": COMPLETED, "final_status": "COMPLETE",
                                      "active_s": 30.0})
    after_low, after_high = scheduler._remaining_estimate(store.counts("R1"))
    assert after_high < before_high, (
        "observed durations must replace the guess made from typed addresses")
    pool.close()


# ---------------------------------------------------------------------------
# §109 — parallelism cases the brief names explicitly
# ---------------------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.parametrize("workers", [8, 16])
def test_the_named_worker_counts_run_a_queue_to_completion(store, tmp_path, workers):
    """§109 asks for 8 and 16 by name. Both must simply work."""
    plan = queue_run(store, tmp_path, make_entries(workers + 4))
    run_scheduler(store, plan, tmp_path, target=fake_worker,
                  payload_extra={"behaviour": "ok", "work_s": 0.05},
                  workers=workers, max_ticks=3000, tick_s=0.02)
    assert store.counts("R1")[COMPLETED] == workers + 4


@pytest.mark.slow
def test_one_very_large_community_does_not_hold_the_others(store, tmp_path):
    """C001 with five thousand URLs must not stop C002 finishing (brief §5)."""
    trace = tmp_path / "trace.tsv"
    entries = [
        {"name": "Enormous", "urls": [f"https://big-{n}.example" for n in range(9)]},
        *make_entries(5, prefix="Small"),
    ]
    plan = build_plan(entries, run_id="R1", output_root=tmp_path / "out")
    store.create_run("R1", mode="FULL", output_root=tmp_path / "out")
    for job in plan.jobs:
        store.add_job("R1", job.as_dict())

    pool = WorkerPool(target=counting_worker, heartbeat_timeout_s=20.0,
                      shutdown_grace_s=2.0)
    scheduler = RunScheduler(
        store, plan, output_root=tmp_path / "out", pool=pool,
        governor=ResourceGovernor(minimum=1, maximum=2, start=2, settle_s=0.0),
        config={"tick_seconds": 0.02, "sample_seconds": 1.0},
        payload_extra={"work_s": 0.15, "trace_path": str(trace)},
    )
    huge = next(j for j in plan.jobs if j.name == "Enormous")
    original = scheduler._dispatch

    def dispatch(job):
        scheduler._payload_extra = {
            "work_s": 2.0 if job.job_id == huge.job_id else 0.15,
            "trace_path": str(trace)}
        original(job)

    scheduler._dispatch = dispatch
    scheduler.run(max_ticks=3000)

    rows = [line.split("\t") for line in trace.read_text().splitlines() if line]
    finished = {row[0]: float(row[2]) for row in rows}
    assert len(finished) == 6, "not every community finished"
    small_ids = [j.job_id for j in plan.jobs if j.job_id != huge.job_id]
    # Every small community finished; most of them before the large one did.
    assert all(job_id in finished for job_id in small_ids)
    ahead = sum(1 for job_id in small_ids
                if finished[job_id] < finished.get(huge.job_id, float("inf")))
    assert ahead >= 3, (
        f"only {ahead} of 5 small communities finished before the large one; "
        "one enormous community is monopolising the run")


@pytest.mark.slow
def test_a_blocked_community_and_a_crash_in_the_same_run(store, tmp_path):
    """§39's list, in one run: a crash, a block, and four that are fine."""
    plan = queue_run(store, tmp_path, make_entries(6))
    behaviours = {plan.jobs[0].job_id: "crash", plan.jobs[1].job_id: "blocked"}
    pool = WorkerPool(target=fake_worker, heartbeat_timeout_s=10.0,
                      shutdown_grace_s=2.0)
    scheduler = RunScheduler(
        store, plan, output_root=tmp_path / "out", pool=pool,
        governor=ResourceGovernor(minimum=1, maximum=3, start=3, settle_s=0.0),
        config={"tick_seconds": 0.02, "sample_seconds": 1.0, "max_attempts": 2},
        payload_extra={"behaviour": "ok", "work_s": 0.05},
    )
    original = scheduler._dispatch

    def dispatch(job):
        scheduler._payload_extra = {
            "behaviour": behaviours.get(job.job_id, "ok"), "work_s": 0.05}
        original(job)

    scheduler._dispatch = dispatch
    scheduler.run(max_ticks=3000)

    jobs = {job.job_id: job for job in store.jobs("R1")}
    assert jobs[plan.jobs[0].job_id].final_status == "FAILED_TECHNICALLY"
    assert jobs[plan.jobs[1].job_id].final_status == "PARTIAL_BLOCKED"
    fine = [job for job_id, job in jobs.items() if job_id not in behaviours]
    assert all(job.final_status == "COMPLETE" for job in fine), (
        "a crash and a block took healthy communities with them")


@pytest.mark.slow
def test_adaptive_scaling_over_a_real_queue(store, tmp_path):
    """The governor moves the count while the queue is running, and the
    scheduler follows it."""
    plan = queue_run(store, tmp_path, make_entries(12))
    governor = ResourceGovernor(minimum=1, maximum=6, start=1, settle_s=0.0)
    run_scheduler(store, plan, tmp_path, target=fake_worker,
                  payload_extra={"behaviour": "ok", "work_s": 0.1},
                  governor=governor, max_ticks=3000, tick_s=0.02)
    assert store.counts("R1")[COMPLETED] == 12
    samples = store.samples("R1")
    targets = {int(row["target"]) for row in samples}
    assert len(targets) > 1, (
        f"the worker count never changed: {targets}. Adaptive concurrency that "
        "never adapts is a constant with extra steps")


def test_repeated_interruption_does_not_lose_work(store, tmp_path):
    """Interrupt, resume, interrupt, resume. Nothing completed is re-run and
    nothing outstanding is forgotten (brief §37, §109)."""
    from dcr.orchestrator.recovery import apply_resume, plan_resume, repair

    plan = queue_run(store, tmp_path, make_entries(8))
    done: set[str] = set()
    for cycle in range(3):
        # Two communities complete, one is left mid-flight, and the machine dies.
        remaining = [job for job in store.jobs("R1") if job.state == QUEUED]
        for job in remaining[:2]:
            store.update_job(job.job_id, {"state": COMPLETED,
                                          "final_status": "COMPLETE",
                                          "active_s": 30.0})
            done.add(job.job_id)
        if len(remaining) > 2:
            store.update_job(remaining[2].job_id, {"state": RUNNING, "worker": "w1"})

        repair(store, "R1")
        recovery = plan_resume(store, "R1")
        assert all(job_id in recovery.keep_complete for job_id in done), (
            f"cycle {cycle}: a completed community was offered for re-running")
        apply_resume(store, recovery)

    counts = store.counts("R1")
    assert counts[COMPLETED] == len(done)
    assert counts[COMPLETED] + counts[QUEUED] == 8, (
        "communities went missing across three interruptions")


def test_a_job_row_says_whether_its_workbook_verified(store, tmp_path):
    """The path and the verification are different facts (brief §12, §92).

    A workbook that exists is not a workbook that reopens, and anything reading
    the queue has to be able to tell them apart — otherwise "37 workbooks" in a
    summary means "37 files", which is not the claim being made.
    """
    plan = queue_run(store, tmp_path, make_entries(2))
    first, second = plan.jobs
    store.update_job(first.job_id, {"workbook_path": "/tmp/a.xlsx",
                                    "workbook_verified": 1})
    store.update_job(second.job_id, {"workbook_path": "/tmp/b.xlsx",
                                     "workbook_verified": 0})
    assert store.job(first.job_id).workbook_verified is True
    assert store.job(second.job_id).workbook_verified is False
    assert store.totals("R1")["workbooks"] == 1


def test_putting_work_back_in_the_queue_reopens_the_run(store, tmp_path):
    """`dcr export` tells the researcher to run the program again. If the run
    is still marked COMPLETED, the next launch offers to start something new
    instead of carrying on — which is not what they were just told."""
    from dcr.orchestrator.recovery import (apply_resume, find_interrupted,
                                           plan_resume, queue_offline_pass)
    from dcr.orchestrator.store import RUN_COMPLETED

    plan = queue_run(store, tmp_path, make_entries(2))
    for job in plan.jobs:
        directory = tmp_path / "out" / job.site_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "research.sqlite3").write_bytes(b"")
        store.update_job(job.job_id, {"state": COMPLETED,
                                      "final_status": "COMPLETE",
                                      "database_path": str(directory / "research.sqlite3")})
    store.set_run_status("R1", RUN_COMPLETED)
    assert not find_interrupted(store), "a finished run should not be offered"

    queued = queue_offline_pass(store, "R1", "EXPORT")
    assert len(queued) == 2
    found = find_interrupted(store)
    assert found and found[0].run_id == "R1", (
        "EXPORT was queued but the next launch would not have found the run")
    assert found[0].queued == 2


def test_a_repaired_run_is_findable_again(store, tmp_path):
    from dcr.orchestrator.recovery import find_interrupted, repair
    from dcr.orchestrator.store import RUN_COMPLETED

    plan = queue_run(store, tmp_path, make_entries(2))
    store.update_job(plan.jobs[0].job_id, {"state": RUNNING, "worker": "w1"})
    store.update_job(plan.jobs[1].job_id, {"state": COMPLETED,
                                           "final_status": "COMPLETE"})
    store.set_run_status("R1", RUN_COMPLETED)
    assert repair(store, "R1")["requeued"] == 1
    assert find_interrupted(store), "a repaired run must be offered on the next launch"
