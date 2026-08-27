"""The active-processing budget, and the reserve that guarantees a workbook.

The reported run spent hours on one community and then produced nothing. The
budget is not a timeout — a timeout would only have stopped the work sooner and
still produced nothing. It reserves the finalisation it must reach (brief §6,
§7, §28).
"""

from __future__ import annotations

import asyncio

import pytest

from dcr.budget import (DEFAULT_BUDGET_S, PHASE_FINALISATION, PHASE_OVER,
                        PHASE_RETRIEVAL, PHASE_WIND_DOWN, TimeBudget,
                        budget_from_settings)
from dcr.control import RunControl
from dcr.db import Database, utcnow
from dcr.supervisor import BudgetExhausted, Supervisor

from test_control import make_run


class FakeClock:
    """Time under the test's control, so nothing has to sleep."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def budget(**kwargs) -> tuple[TimeBudget, FakeClock]:
    clock = FakeClock()
    kwargs.setdefault("budget_s", 30 * 60)
    kwargs.setdefault("finalisation_reserve_s", 3 * 60)
    kwargs.setdefault("wind_down_s", 2 * 60)
    return TimeBudget(clock=clock, **kwargs), clock


# ---------------------------------------------------------------------------
# §11-13 — what happens at 25, 29 and 30 minutes
# ---------------------------------------------------------------------------
def test_at_the_start_the_crawl_may_do_anything():
    clock_budget, _ = budget()
    assert clock_budget.phase == PHASE_RETRIEVAL
    assert clock_budget.may_start_expensive_work
    assert not clock_budget.must_finalise


def test_at_twenty_five_minutes_expensive_work_stops_starting():
    """The wind-down: finish what is in flight, start nothing new."""
    clock_budget, clock = budget()
    clock.advance(25 * 60 + 1)
    assert clock_budget.phase == PHASE_WIND_DOWN
    assert not clock_budget.may_start_expensive_work
    assert clock_budget.may_start_cheap_work, "work in flight must be allowed to finish"
    assert not clock_budget.must_finalise


def test_at_twenty_seven_minutes_finalisation_begins():
    clock_budget, clock = budget()
    clock.advance(27 * 60 + 1)
    assert clock_budget.phase == PHASE_FINALISATION
    assert clock_budget.must_finalise
    assert not clock_budget.may_start_cheap_work


def test_at_thirty_minutes_the_budget_is_over():
    clock_budget, clock = budget()
    clock.advance(30 * 60 + 1)
    assert clock_budget.phase == PHASE_OVER
    assert clock_budget.exhausted
    assert clock_budget.remaining_s == 0


def test_the_reserve_is_never_spent_on_retrieval():
    """The whole point: finalisation time cannot be borrowed."""
    clock_budget, clock = budget()
    clock.advance(26 * 60)
    assert not clock_budget.affords(1.0), (
        "no new expensive task may start once the wind-down has begun")


@pytest.mark.parametrize("cost_s,expected", [(5, True), (60, True), (2000, False)])
def test_a_task_that_would_eat_the_reserve_is_refused(cost_s, expected):
    """Never begin a long operation likely to prevent finalisation (brief §6)."""
    clock_budget, clock = budget()
    clock.advance(3 * 60)
    assert clock_budget.affords(cost_s) is expected


# ---------------------------------------------------------------------------
# §6, §26 — a pause is not spent budget
# ---------------------------------------------------------------------------
def test_time_spent_paused_by_the_researcher_does_not_count():
    clock_budget, clock = budget()
    clock.advance(10 * 60)
    clock_budget.pause("manual")
    clock.advance(60 * 60)               # lunch, a meeting, overnight
    clock_budget.resume()
    assert clock_budget.active_s == pytest.approx(10 * 60, abs=1)
    assert clock_budget.paused_manual_s == pytest.approx(60 * 60, abs=1)
    assert clock_budget.phase == PHASE_RETRIEVAL


def test_time_spent_offline_does_not_count():
    """An outage must not be able to eat the research budget."""
    clock_budget, clock = budget()
    clock.advance(5 * 60)
    clock_budget.pause("network")
    clock.advance(45 * 60)
    clock_budget.resume()
    assert clock_budget.active_s == pytest.approx(5 * 60, abs=1)
    assert clock_budget.offline_s == pytest.approx(45 * 60, abs=1)
    assert not clock_budget.exhausted


def test_wall_clock_and_active_time_are_reported_separately():
    clock_budget, clock = budget()
    clock.advance(10 * 60)
    clock_budget.pause("network")
    clock.advance(20 * 60)
    clock_budget.resume()
    clock.advance(5 * 60)
    snapshot = clock_budget.snapshot()
    assert snapshot.active_s == pytest.approx(15 * 60, abs=1)
    assert snapshot.wall_s == pytest.approx(35 * 60, abs=1)
    assert snapshot.offline_s == pytest.approx(20 * 60, abs=1)


# ---------------------------------------------------------------------------
# §27 — a resume must not restart the budget
# ---------------------------------------------------------------------------
def test_a_resumed_run_continues_the_same_budget():
    resumed, clock = budget(carried_active_s=22 * 60)
    assert resumed.active_s == pytest.approx(22 * 60, abs=1)
    clock.advance(4 * 60)
    assert resumed.phase == PHASE_WIND_DOWN, (
        "26 minutes of a 30-minute budget are gone; this session cannot have a fresh 30")


def test_four_sessions_cannot_quietly_consume_two_hours():
    spent = 0.0
    for _ in range(4):
        session, clock = budget(carried_active_s=spent)
        while session.may_start_expensive_work:
            clock.advance(60)
        spent = session.active_s
    assert spent <= 30 * 60, f"the budget leaked across sessions: {spent / 60:.1f} min"


def test_the_carried_time_is_read_back_from_the_database(db, community):
    run_id = make_run(db, community)
    db.insert("run_control", {
        "run_id": run_id, "community_id": community, "state": "PAUSED_MANUAL",
        "active_elapsed_s": 900.0, "updated_utc": utcnow(),
    }, replace=True)
    assert TimeBudget.carried_for(db, community) == pytest.approx(900.0)


def test_a_completed_run_does_not_charge_the_next_one(db, community):
    run_id = make_run(db, community)
    db.update("runs", {"status": "complete"}, {"run_id": run_id})
    db.insert("run_control", {
        "run_id": run_id, "community_id": community, "state": "COMPLETED",
        "active_elapsed_s": 1500.0, "updated_utc": utcnow(),
    }, replace=True)
    assert TimeBudget.carried_for(db, community) == 0.0


# ---------------------------------------------------------------------------
# per-stage ceilings
# ---------------------------------------------------------------------------
def test_each_stage_gets_a_share_of_retrieval_not_of_the_whole_budget():
    clock_budget, _ = budget()
    retrieval = 30 * 60 - 3 * 60 - 2 * 60
    assert clock_budget.stage_ceiling_s(2) == pytest.approx(retrieval * 0.24)
    assert sum(clock_budget.stage_ceiling_s(n) for n in range(10)) <= retrieval + 1


def test_a_stage_that_overruns_its_share_is_noticed():
    clock_budget, clock = budget()
    clock_budget.begin_stage(4)
    clock.advance(clock_budget.stage_ceiling_s(4) + 1)
    assert clock_budget.stage_over_budget(4)
    assert clock_budget.stage_remaining_s(4) == 0


def test_a_stage_that_finishes_early_hands_the_rest_back():
    clock_budget, clock = budget()
    clock_budget.begin_stage(2)
    clock.advance(30)
    clock_budget.end_stage()
    assert clock_budget.stage_spent_s(2) == pytest.approx(30, abs=1)
    assert clock_budget.remaining_s > 29 * 60 - 60


def test_the_profile_says_where_the_time_went():
    clock_budget, clock = budget()
    for stage, seconds in ((2, 300), (3, 200), (4, 100)):
        clock_budget.begin_stage(stage)
        clock.advance(seconds)
    clock_budget.end_stage()
    profile = clock_budget.profile()
    assert profile["by_stage_s"]["2"] == pytest.approx(300, abs=1)
    assert profile["by_stage_pct"]["2"] == pytest.approx(50.0, abs=1)


# ---------------------------------------------------------------------------
# the gate enforces it
# ---------------------------------------------------------------------------
@pytest.fixture()
def control(db, community, tmp_path):
    run_id = make_run(db, community)
    return RunControl(db, run_id=run_id, community_id=community,
                      control_dir=tmp_path / "control", poll_interval_s=0.0)


def test_the_gate_stops_the_run_when_the_budget_is_spent(control):
    clock_budget, clock = budget()
    supervisor = Supervisor(control, None, budget=clock_budget)
    asyncio.run(supervisor.gate(stage_no=2))          # fine
    clock.advance(28 * 60)
    with pytest.raises(BudgetExhausted) as caught:
        asyncio.run(supervisor.gate(stage_no=2))
    assert "budget" in str(caught.value).lower()
    assert caught.value.snapshot.exhausted or caught.value.snapshot.phase == PHASE_FINALISATION


def test_the_gate_reports_winding_down_before_it_stops(control):
    clock_budget, clock = budget()
    supervisor = Supervisor(control, None, budget=clock_budget)
    clock.advance(25 * 60 + 30)
    asyncio.run(supervisor.gate(stage_no=2))          # still allowed through
    assert supervisor.winding_down
    assert not supervisor.affords(10.0)


def test_a_supervisor_without_a_budget_behaves_exactly_as_before(control):
    supervisor = Supervisor(control, None)
    asyncio.run(supervisor.gate(stage_no=2))
    assert supervisor.affords(10_000)
    assert not supervisor.winding_down


def test_a_pause_at_the_gate_stops_the_budget_clock(control, tmp_path):
    from dcr.control import request_pause, request_resume

    clock_budget, clock = budget()

    async def instant(_s: float) -> None:
        await asyncio.sleep(0)

    supervisor = Supervisor(control, None, config={"manual_pause_behavior": "wait",
                                                   "resume_poll_interval_s": 0.0},
                            sleep=instant, budget=clock_budget)
    request_pause(tmp_path, "stopping for lunch")

    async def scenario():
        async def researcher_returns():
            await asyncio.sleep(0.05)
            clock.advance(45 * 60)        # a long lunch
            request_resume(tmp_path, "back")

        await asyncio.gather(supervisor.gate(stage_no=2), researcher_returns())

    asyncio.run(scenario())
    assert clock_budget.active_s < 60, "the lunch was charged to the research budget"
    assert clock_budget.paused_manual_s == pytest.approx(45 * 60, abs=2)


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------
def test_the_budget_comes_from_configuration(settings):
    configured = budget_from_settings(settings)
    assert configured.budget_s == 30 * 60
    assert configured.finalisation_reserve_s > 0
    assert configured.stage_shares


def test_the_reserve_can_never_exceed_half_the_budget():
    """A misconfiguration must not leave no time to crawl in."""
    guarded = TimeBudget(budget_s=600, finalisation_reserve_s=10_000)
    assert guarded.finalisation_reserve_s <= 300
