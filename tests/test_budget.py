"""The clock, and what replaced it as the reason a community stops.

The previous version of this file asserted that a run ends at thirty minutes.
That behaviour was the defect: it truncated communities that were still
producing evidence and idled on communities that were not, because the only
thing it measured was time (brief §1, §62, and `docs/BASELINE_AUDIT.md`).

So the assertions here are inverted. A community with evidence still coming in
must NOT be stopped, however long it has been running; a community that has gone
quiet must be stopped promptly, however briefly it has run. The clock is kept
only to measure — the yield rate needs a denominator, an outage must not be
counted as work, and finalisation must always be reachable.
"""

from __future__ import annotations

import asyncio

import pytest

from dcr.budget import (DEFAULT_CEILING_S, DEFAULT_NOMINAL_RETRIEVAL_S,
                        PHASE_FINALISATION, PHASE_OVER, PHASE_RETRIEVAL,
                        PHASE_WIND_DOWN, WorkBudget, budget_from_settings)
from dcr.control import RunControl
from dcr.db import Database, utcnow
from dcr.supervisor import RetrievalFinished, Supervisor
from dcr.yieldmeter import YieldMeter

from test_control import make_run


class FakeClock:
    """Time under the test's control, so nothing has to sleep."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def budget(**kwargs) -> tuple[WorkBudget, FakeClock]:
    clock = FakeClock()
    return WorkBudget(clock=clock, **kwargs), clock


def capped(**kwargs) -> tuple[WorkBudget, FakeClock]:
    """A budget with the opt-in safety ceiling an operator may set."""
    kwargs.setdefault("ceiling_s", 30 * 60)
    kwargs.setdefault("finalisation_reserve_s", 3 * 60)
    kwargs.setdefault("wind_down_s", 2 * 60)
    return budget(**kwargs)


# ---------------------------------------------------------------------------
# §1, §62 — the thirty-minute cutoff is gone
# ---------------------------------------------------------------------------
def test_by_default_there_is_no_research_runtime_cap():
    clock_budget, _ = budget()
    assert not clock_budget.bounded
    assert clock_budget.remaining_s == float("inf")
    assert DEFAULT_CEILING_S == 0.0


@pytest.mark.parametrize("minutes", [30, 45, 90, 240, 600])
def test_a_productive_community_is_never_stopped_by_the_clock(minutes):
    """The regression this rewrite exists to remove."""
    clock_budget, clock = budget()
    clock.advance(minutes * 60)
    assert clock_budget.phase == PHASE_RETRIEVAL
    assert clock_budget.may_start_expensive_work
    assert not clock_budget.must_finalise
    assert clock_budget.affords(120.0), (
        f"a community still producing evidence was refused work at {minutes} min")


def test_the_default_configuration_sets_no_ceiling(settings):
    configured = budget_from_settings(settings)
    assert not configured.bounded, (
        "shipping a ceiling by default would reintroduce the defect")
    assert configured.finalisation_reserve_s > 0
    assert configured.stage_shares


# ---------------------------------------------------------------------------
# §66 — what DOES end retrieval
# ---------------------------------------------------------------------------
def test_retrieval_ends_when_something_asks_it_to():
    clock_budget, clock = budget(wind_down_s=60)
    clock.advance(3 * 3600)
    assert clock_budget.phase == PHASE_RETRIEVAL

    clock_budget.begin_wind_down("the community is worked out")
    assert clock_budget.phase == PHASE_WIND_DOWN
    assert not clock_budget.may_start_expensive_work
    assert clock_budget.may_start_cheap_work, "work in flight must be allowed to finish"

    clock.advance(61)
    assert clock_budget.phase == PHASE_FINALISATION
    assert clock_budget.must_finalise
    assert clock_budget.stop_reason == "the community is worked out"


def test_finalisation_can_be_demanded_immediately():
    clock_budget, _ = budget()
    clock_budget.begin_finalisation("the researcher asked for the workbook now")
    assert clock_budget.must_finalise
    assert not clock_budget.may_start_cheap_work


def test_the_first_reason_for_stopping_is_the_one_recorded():
    clock_budget, _ = budget()
    clock_budget.begin_wind_down("worked out")
    clock_budget.begin_wind_down("something else entirely")
    assert clock_budget.stop_reason == "worked out"


# ---------------------------------------------------------------------------
# §98 — the ceiling is available to an operator who wants one
# ---------------------------------------------------------------------------
def test_an_operator_may_opt_into_a_safety_ceiling():
    clock_budget, clock = capped()
    assert clock_budget.bounded
    clock.advance(25 * 60 + 1)
    assert clock_budget.phase == PHASE_WIND_DOWN
    clock.advance(2 * 60)
    assert clock_budget.phase == PHASE_FINALISATION
    clock.advance(3 * 60)
    assert clock_budget.phase == PHASE_OVER
    assert clock_budget.exhausted


def test_the_reserve_is_never_spent_on_retrieval():
    """With a ceiling set, finalisation time still cannot be borrowed."""
    clock_budget, clock = capped()
    clock.advance(26 * 60)
    assert not clock_budget.affords(1.0)


@pytest.mark.parametrize("cost_s,expected", [(5, True), (60, True), (2000, False)])
def test_a_task_that_would_eat_the_reserve_is_refused(cost_s, expected):
    clock_budget, clock = capped()
    clock.advance(3 * 60)
    assert clock_budget.affords(cost_s) is expected


def test_without_a_ceiling_nothing_is_unaffordable():
    clock_budget, clock = budget()
    clock.advance(8 * 3600)
    assert clock_budget.affords(10_000)


def test_the_reserve_can_never_exceed_half_the_ceiling():
    """A misconfiguration must not leave no time to crawl in."""
    guarded = WorkBudget(ceiling_s=600, finalisation_reserve_s=10_000)
    assert guarded.finalisation_reserve_s <= 300


# ---------------------------------------------------------------------------
# §32 — a pause is not active time
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
    """An outage must not be able to eat the research (brief §32)."""
    clock_budget, clock = capped()
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
# §38, §107 — one honest account of a community across sessions
# ---------------------------------------------------------------------------
def test_a_resumed_run_continues_the_same_account():
    resumed, clock = budget(carried_active_s=22 * 60)
    assert resumed.active_s == pytest.approx(22 * 60, abs=1)
    clock.advance(4 * 60)
    assert resumed.active_s == pytest.approx(26 * 60, abs=1)


def test_carrying_time_forward_no_longer_shortens_the_next_session():
    """The old behaviour: a fourth session got almost no time. Not any more."""
    resumed, clock = budget(carried_active_s=110 * 60)
    clock.advance(30 * 60)
    assert resumed.phase == PHASE_RETRIEVAL
    assert resumed.may_start_expensive_work, (
        "carried time must be an accounting fact, not a punishment")


def test_the_carried_time_is_read_back_from_the_database(db, community):
    run_id = make_run(db, community)
    db.insert("run_control", {
        "run_id": run_id, "community_id": community, "state": "PAUSED_MANUAL",
        "active_elapsed_s": 900.0, "updated_utc": utcnow(),
    }, replace=True)
    assert WorkBudget.carried_for(db, community) == pytest.approx(900.0)


def test_a_completed_run_does_not_charge_the_next_one(db, community):
    run_id = make_run(db, community)
    db.update("runs", {"status": "complete"}, {"run_id": run_id})
    db.insert("run_control", {
        "run_id": run_id, "community_id": community, "state": "COMPLETED",
        "active_elapsed_s": 1500.0, "updated_utc": utcnow(),
    }, replace=True)
    assert WorkBudget.carried_for(db, community) == 0.0


# ---------------------------------------------------------------------------
# per-stage allocations: a starting point, not a ceiling
# ---------------------------------------------------------------------------
def test_each_stage_gets_a_share_of_a_nominal_retrieval_pool():
    clock_budget, _ = budget()
    assert clock_budget.retrieval_pool_s == DEFAULT_NOMINAL_RETRIEVAL_S
    assert clock_budget.stage_base_s(2) == pytest.approx(
        DEFAULT_NOMINAL_RETRIEVAL_S * 0.24)
    assert sum(clock_budget.stage_base_s(n) for n in range(10)) <= (
        DEFAULT_NOMINAL_RETRIEVAL_S + 1)


def test_a_stage_past_its_allocation_is_not_thereby_stopped():
    """The heart of the change: overrunning is noticed, not punished."""
    clock_budget, clock = budget()
    clock_budget.begin_stage(4)
    clock.advance(clock_budget.stage_base_s(4) * 5)
    assert clock_budget.stage_past_allocation(4)
    assert not clock_budget.stage_over_budget(4), (
        "with no ceiling set, a stage is ended by its yield or not at all")


def test_yield_stretches_a_stage_allocation():
    clock_budget, clock = budget()
    clock_budget.begin_stage(4)
    base = clock_budget.stage_base_s(4)
    clock.advance(base)
    assert clock_budget.stage_allowance_s(4, earned_multiple=1.0) == pytest.approx(0, abs=1)
    assert clock_budget.stage_allowance_s(4, earned_multiple=4.0) == pytest.approx(
        base * 3, abs=2)


def test_a_ceiling_still_bounds_a_runaway_stage():
    clock_budget, clock = capped()
    clock_budget.begin_stage(4)
    clock.advance(clock_budget.stage_base_s(4) * 9)
    assert clock_budget.stage_over_budget(4)


def test_a_stage_that_finishes_early_hands_the_rest_back():
    clock_budget, clock = budget()
    clock_budget.begin_stage(2)
    clock.advance(30)
    clock_budget.end_stage()
    assert clock_budget.stage_spent_s(2) == pytest.approx(30, abs=1)


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
# the gate: the yield governor is what stops a run
# ---------------------------------------------------------------------------
@pytest.fixture()
def control(db, community, tmp_path):
    run_id = make_run(db, community)
    return RunControl(db, run_id=run_id, community_id=community,
                      control_dir=tmp_path / "control", poll_interval_s=0.0)


def _productive(meter: YieldMeter, seconds: float, finds: int) -> None:
    """Drive a meter as a community that keeps finding things."""
    for index in range(finds):
        meter.spend(seconds / max(1, finds), ("run",))
        meter.attempt(("run",))
        meter.credit("field_first", key=f"f{meter.scope('run').credited}-{index}",
                     scopes=("run",))


def test_the_gate_does_not_stop_a_community_that_is_still_producing(control):
    clock_budget, clock = budget()
    meter = YieldMeter()
    supervisor = Supervisor(control, None, budget=clock_budget, meter=meter)
    for _ in range(6):
        clock.advance(10 * 60)
        _productive(meter, 10 * 60, 90)
        asyncio.run(supervisor.gate(stage_no=2))
    assert clock_budget.phase == PHASE_RETRIEVAL, (
        "an hour of high-yield crawling was stopped; that is the old defect")


def test_the_gate_stops_a_community_that_has_gone_quiet(control):
    clock_budget, clock = budget(wind_down_s=0)
    meter = YieldMeter(absolute_floor=2.0, warmup_s=60, warmup_attempts=10)
    supervisor = Supervisor(control, None, budget=clock_budget, meter=meter,
                            config={"run_yield_warmup_minutes": 1.0,
                                    "run_yield_warmup_attempts": 10,
                                    "run_yield_floor_per_min": 2.0})
    # A productive opening...
    clock.advance(5 * 60)
    _productive(meter, 5 * 60, 200)
    asyncio.run(supervisor.gate(stage_no=2))
    assert clock_budget.phase == PHASE_RETRIEVAL

    # ...then twenty minutes of nothing.
    for _ in range(20):
        clock.advance(60)
        meter.spend(60, ("run",))
        meter.attempt(("run",), 20)
    with pytest.raises(RetrievalFinished) as caught:
        asyncio.run(supervisor.gate(stage_no=2))
    assert caught.value.cause == "exhausted"
    assert not caught.value.truncated, (
        "a community that ran out of evidence is COMPLETE, not truncated")


def test_a_ceiling_reached_is_reported_as_a_truncation(control):
    clock_budget, clock = capped()
    supervisor = Supervisor(control, None, budget=clock_budget)
    asyncio.run(supervisor.gate(stage_no=2))
    clock.advance(28 * 60)
    with pytest.raises(RetrievalFinished) as caught:
        asyncio.run(supervisor.gate(stage_no=2))
    assert caught.value.cause == "ceiling"
    assert caught.value.truncated


def test_the_researcher_can_ask_for_a_wrap_up(control):
    clock_budget, clock = budget(wind_down_s=0)
    supervisor = Supervisor(control, None, budget=clock_budget)
    supervisor.request_wind_down("the researcher asked for the workbook")
    with pytest.raises(RetrievalFinished) as caught:
        asyncio.run(supervisor.gate(stage_no=2))
    assert caught.value.cause == "requested"
    assert caught.value.truncated


def test_a_supervisor_without_a_budget_behaves_exactly_as_before(control):
    supervisor = Supervisor(control, None)
    asyncio.run(supervisor.gate(stage_no=2))
    assert supervisor.affords(10_000)
    assert not supervisor.winding_down


def test_a_pause_at_the_gate_stops_the_clock(control, tmp_path):
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
    assert clock_budget.active_s < 60, "the lunch was charged to the research"
    assert clock_budget.paused_manual_s == pytest.approx(45 * 60, abs=2)
