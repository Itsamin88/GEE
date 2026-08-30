"""The active-processing clock. It measures; it no longer decides.

The version this replaces was a thirty-minute cap dressed as a budget. It
divided a constant into fixed per-stage shares and truncated each stage at its
share whatever that stage was finding, so a community whose archive was handing
over a dated project report every forty seconds was cut off at four minutes by
the same rule as one whose archive held nothing. That is why evidence was lost
(brief §1, §62, and `docs/BASELINE_AUDIT.md`).

**There is no research-runtime cap here any more.** A community runs while it is
still producing evidence, and stops when it stops producing — a decision made in
`yieldmeter.py` from what the crawl is actually finding, not from a clock.

What survives, and why each earns its place:

**The clock itself.** Yield is evidence *per active minute*, so something has to
count active minutes. Time spent paused by the researcher or waiting for the
network is not active time and is excluded, which is what stops an outage
silently eating the research (brief §32). The count is persisted, so a resumed
run continues one account of the community rather than starting a fresh one.

**A finalisation reserve.** Not a research cap: the guarantee that
reconciliation, export and verification always happen (brief §12). It bites only
once the run is winding down.

**Soft per-stage allocations.** A *starting* allocation, not a ceiling. A stage
that is producing extends past it for as long as it keeps producing; a stage
that is not hands the rest back. They also give the estimator something to
predict from before any evidence exists (brief §45).

**An optional safety ceiling, off by default.** Configuration only, for an
operator who must bound an unattended overnight run. `active_minutes: 0` — the
default — means no ceiling at all, and the phase machine below then moves only
when the yield governor or the researcher moves it.

    unbounded (default)                       ceiling set (opt-in)
    ───────────────────                       ────────────────────
    RETRIEVAL                                 |<──── ceiling ────>|
      │ yield governor says the community     |<─ retrieval ─>|w|f|
      │ is exhausted, or the researcher asks                  ^ ^
      ▼                                                       │ └ reconcile,
    WIND_DOWN   nothing new starts                            │   export, verify
      │                                                       └ finish what is
      ▼                                                         already in flight
    FINALISATION  reconcile, export, verify
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from .db import Database, utcnow
from .logging_setup import event, get_logger

log = get_logger("budget")

#: No research-runtime cap. A community runs while it is producing evidence.
#: An operator may set one in configuration; nothing in the code assumes it.
DEFAULT_CEILING_S = 0.0

#: Held back for reconciliation, export, verification and manifests. This is
#: the one time-shaped guarantee the design keeps, and it is a guarantee that
#: the research reaches a workbook rather than a limit on the research.
DEFAULT_FINALISATION_RESERVE_S = 3 * 60

#: Once winding down, how long work already in flight may take to finish before
#: finalisation begins regardless.
DEFAULT_WIND_DOWN_S = 2 * 60

#: The *starting* allocation for each stage, as a share of a nominal community's
#: retrieval time. A stage that is yielding runs past its share; one that is not
#: gives the rest back. Stage 9 is paid for out of the finalisation reserve.
DEFAULT_STAGE_SHARES: dict[int, float] = {
    0: 0.04,    # build the source set
    1: 0.04,    # confirm the sources belong to this community
    2: 0.24,    # enumerate pages — the discovery everything else feeds on
    3: 0.20,    # open the documents: the richest evidence per second
    4: 0.16,    # the archive, prioritised rather than enumerated
    5: 0.14,    # academic literature
    6: 0.10,    # grey literature
    7: 0.04,    # other web sources
    8: 0.04,    # local-language sweep
    9: 0.00,    # reconciliation comes out of the finalisation reserve
}

#: The retrieval time a "nominal" community is assumed to want, used to turn the
#: shares above into seconds when no ceiling is set. It is a starting point for
#: estimation and for the soft allocations — never a limit.
DEFAULT_NOMINAL_RETRIEVAL_S = 40 * 60

#: How far past its starting allocation a stage may be carried by its own yield.
#: A stage producing at the floor gets its allocation; one producing at eight
#: times the floor gets eight times. Nothing here stops a productive stage: the
#: multiple only bounds how far *one* extension reaches before the yield
#: governor is consulted again.
DEFAULT_MAX_STAGE_MULTIPLE = 8.0

PHASE_RETRIEVAL = "retrieval"
PHASE_WIND_DOWN = "wind_down"
PHASE_FINALISATION = "finalisation"
PHASE_OVER = "over"


@dataclass
class BudgetSnapshot:
    """What the clock says, in the terms the report needs."""

    active_s: float = 0.0
    wall_s: float = 0.0
    offline_s: float = 0.0
    paused_manual_s: float = 0.0
    ceiling_s: float = 0.0
    phase: str = PHASE_RETRIEVAL
    exhausted: bool = False
    stop_reason: str = ""

    @property
    def bounded(self) -> bool:
        return self.ceiling_s > 0

    @property
    def remaining_s(self) -> float:
        if not self.bounded:
            return float("inf")
        return max(0.0, self.ceiling_s - self.active_s)

    def as_dict(self) -> dict[str, Any]:
        remaining = self.remaining_s
        return {
            "active_s": round(self.active_s, 1),
            "wall_clock_s": round(self.wall_s, 1),
            "offline_s": round(self.offline_s, 1),
            "paused_manual_s": round(self.paused_manual_s, 1),
            "ceiling_s": round(self.ceiling_s, 1) if self.bounded else None,
            "safety_ceiling_set": self.bounded,
            "remaining_s": round(remaining, 1) if self.bounded else None,
            "phase": self.phase,
            "retrieval_stopped": self.exhausted,
            "stop_reason": self.stop_reason,
        }


class WorkBudget:
    """The active-processing clock for one community run.

    ``clock`` is injectable so tests drive time forward deterministically
    instead of sleeping.
    """

    def __init__(
        self,
        *,
        ceiling_s: float = DEFAULT_CEILING_S,
        finalisation_reserve_s: float = DEFAULT_FINALISATION_RESERVE_S,
        wind_down_s: float = DEFAULT_WIND_DOWN_S,
        stage_shares: Mapping[int, float] | None = None,
        nominal_retrieval_s: float = DEFAULT_NOMINAL_RETRIEVAL_S,
        max_stage_multiple: float = DEFAULT_MAX_STAGE_MULTIPLE,
        clock: Any = None,
        carried_active_s: float = 0.0,
    ):
        self.ceiling_s = max(0.0, float(ceiling_s or 0.0))
        if self.bounded:
            self.finalisation_reserve_s = min(float(finalisation_reserve_s),
                                              self.ceiling_s * 0.5)
            self.wind_down_s = min(
                float(wind_down_s),
                max(0.0, self.ceiling_s - self.finalisation_reserve_s) * 0.5)
        else:
            self.finalisation_reserve_s = max(0.0, float(finalisation_reserve_s))
            self.wind_down_s = max(0.0, float(wind_down_s))
        self.stage_shares = dict(stage_shares or DEFAULT_STAGE_SHARES)
        self.nominal_retrieval_s = max(60.0, float(nominal_retrieval_s))
        self.max_stage_multiple = max(1.0, float(max_stage_multiple))
        self._clock = clock or time.monotonic
        self._started = self._clock()
        #: Active seconds already spent by earlier sessions of this run.
        self.carried_active_s = max(0.0, float(carried_active_s))
        self._paused_since: float | None = None
        self._pause_kind = ""
        self.offline_s = 0.0
        self.paused_manual_s = 0.0
        #: Active seconds charged to each stage, for the profile report.
        self.stage_spend: dict[int, float] = {}
        self._stage_started: float | None = None
        self._stage_no: int | None = None
        self._announced: set[str] = set()
        #: Set when retrieval is ended by something other than the ceiling —
        #: the yield governor, or the researcher.
        self._wind_down_started_at: float | None = None
        self._finalisation_forced = False
        self.stop_reason = ""

    # -- the clock ---------------------------------------------------------
    @property
    def bounded(self) -> bool:
        """True only when an operator has opted into a safety ceiling."""
        return self.ceiling_s > 0

    @property
    def wall_s(self) -> float:
        return self._clock() - self._started

    @property
    def active_s(self) -> float:
        """Wall-clock minus everything nobody was working through."""
        paused = self.offline_s + self.paused_manual_s
        if self._paused_since is not None:
            paused += self._clock() - self._paused_since
        return self.carried_active_s + max(0.0, self.wall_s - paused)

    @property
    def remaining_s(self) -> float:
        if not self.bounded:
            return float("inf")
        return max(0.0, self.ceiling_s - self.active_s)

    # -- pausing -----------------------------------------------------------
    def pause(self, kind: str) -> None:
        """Stop the active clock. A paused crawl is not spending active time."""
        if self._paused_since is None:
            self._paused_since = self._clock()
            self._pause_kind = kind

    def resume(self) -> float:
        """Restart the clock, charging the gap to the right bucket."""
        if self._paused_since is None:
            return 0.0
        elapsed = self._clock() - self._paused_since
        if self._pause_kind == "manual":
            self.paused_manual_s += elapsed
        else:
            self.offline_s += elapsed
        self._paused_since = None
        self._pause_kind = ""
        return elapsed

    @property
    def paused(self) -> bool:
        return self._paused_since is not None

    # -- ending retrieval on purpose ---------------------------------------
    def begin_wind_down(self, reason: str) -> None:
        """Stop starting new expensive work; let what is in flight finish.

        Called by the supervisor when the yield governor judges the community
        exhausted, or when the researcher asks for the run to be wrapped up.
        This is how an unbounded run ends: by having found everything there was,
        not by running out of clock.
        """
        if self._wind_down_started_at is None and not self._finalisation_forced:
            self._wind_down_started_at = self.active_s
            self.stop_reason = reason
            event(log, "BUDGET", f"winding down — {reason}")

    def begin_finalisation(self, reason: str) -> None:
        """Stop everything and reconcile, export and verify now."""
        if not self._finalisation_forced:
            self._finalisation_forced = True
            if self._wind_down_started_at is None:
                self._wind_down_started_at = self.active_s
            self.stop_reason = reason or self.stop_reason
            event(log, "BUDGET", f"finalising — {self.stop_reason}")

    @property
    def retrieval_stopped(self) -> bool:
        return self._wind_down_started_at is not None or self._finalisation_forced

    # -- phases ------------------------------------------------------------
    @property
    def phase(self) -> str:
        if self._finalisation_forced:
            return PHASE_FINALISATION
        if self._wind_down_started_at is not None:
            since = self.active_s - self._wind_down_started_at
            if since >= self.wind_down_s:
                return PHASE_FINALISATION
            return PHASE_WIND_DOWN
        if self.bounded:
            remaining = self.remaining_s
            if remaining <= 0:
                return PHASE_OVER
            if remaining <= self.finalisation_reserve_s:
                return PHASE_FINALISATION
            if remaining <= self.finalisation_reserve_s + self.wind_down_s:
                return PHASE_WIND_DOWN
        return PHASE_RETRIEVAL

    @property
    def may_start_expensive_work(self) -> bool:
        """May a new page fetch, document parse or archive query begin?"""
        return self.phase == PHASE_RETRIEVAL

    @property
    def may_start_cheap_work(self) -> bool:
        """May a small, bounded piece of work begin (finishing a batch)?"""
        return self.phase in (PHASE_RETRIEVAL, PHASE_WIND_DOWN)

    @property
    def must_finalise(self) -> bool:
        return self.phase in (PHASE_FINALISATION, PHASE_OVER)

    @property
    def exhausted(self) -> bool:
        """The ceiling was reached. Only possible when one was set."""
        return self.phase == PHASE_OVER

    def affords(self, estimated_s: float) -> bool:
        """Is there room for a task of this expected cost, and still finalise?

        Never begin a long operation likely to prevent finalisation (brief §12).
        With no ceiling the only thing that can refuse is the phase.
        """
        if not self.may_start_expensive_work:
            return False
        if not self.bounded:
            return True
        return (self.remaining_s - self.finalisation_reserve_s) >= max(0.0, estimated_s)

    # -- per-stage allocations ---------------------------------------------
    @property
    def retrieval_pool_s(self) -> float:
        """The seconds the stage shares are shares *of*."""
        if self.bounded:
            return max(0.0, self.ceiling_s - self.finalisation_reserve_s
                       - self.wind_down_s)
        return self.nominal_retrieval_s

    def stage_base_s(self, stage_no: int) -> float:
        """This stage's starting allocation. Not a ceiling."""
        return self.retrieval_pool_s * float(self.stage_shares.get(stage_no, 0.05))

    #: Kept as the old name because the runner, the estimator and the report all
    #: ask this question; what changed is that the answer is a starting point.
    stage_ceiling_s = stage_base_s

    def begin_stage(self, stage_no: int) -> None:
        self.end_stage()
        self._stage_no = stage_no
        self._stage_started = self.active_s

    def end_stage(self) -> None:
        if self._stage_no is not None and self._stage_started is not None:
            spent = max(0.0, self.active_s - self._stage_started)
            self.stage_spend[self._stage_no] = (
                self.stage_spend.get(self._stage_no, 0.0) + spent)
        self._stage_no = None
        self._stage_started = None

    def stage_spent_s(self, stage_no: int | None = None) -> float:
        number = self._stage_no if stage_no is None else stage_no
        if number is None:
            return 0.0
        spent = self.stage_spend.get(number, 0.0)
        if number == self._stage_no and self._stage_started is not None:
            spent += max(0.0, self.active_s - self._stage_started)
        return spent

    def stage_past_allocation(self, stage_no: int | None = None,
                              *, multiple: float = 1.0) -> bool:
        """Has this stage spent more than `multiple` times its allocation?

        On its own this is not a reason to stop. The runner asks the yield
        governor first and only treats this as decisive when yield has also
        fallen away — the pair together is "it has had a fair share *and* it has
        stopped producing", which is a defensible place to stop and a bare clock
        comparison is not.
        """
        number = self._stage_no if stage_no is None else stage_no
        if number is None:
            return False
        allowance = self.stage_base_s(number) * max(1.0, float(multiple))
        return self.stage_spent_s(number) >= allowance

    def stage_over_budget(self, stage_no: int | None = None) -> bool:
        """Only ever true against a ceiling an operator opted into.

        With no ceiling this is always false: a stage is ended by its yield, or
        not at all. Kept so the runner can ask one question in both worlds.
        """
        if not self.bounded:
            return False
        number = self._stage_no if stage_no is None else stage_no
        if number is None:
            return False
        return self.stage_spent_s(number) >= self.stage_base_s(number) * self.max_stage_multiple

    def stage_remaining_s(self, stage_no: int | None = None) -> float:
        """Seconds this stage can still plan around.

        Used where an allocation genuinely has to be divided ahead of time — the
        archive splitting its allowance between domains. Unbounded runs get the
        stage's allocation extended by what it has earned, which the caller
        supplies as `earned_multiple`.
        """
        number = self._stage_no if stage_no is None else stage_no
        if number is None:
            return self.remaining_s if self.bounded else self.nominal_retrieval_s
        headroom = self.stage_base_s(number) - self.stage_spent_s(number)
        if not self.bounded:
            return max(0.0, headroom)
        return max(0.0, min(headroom, self.remaining_s - self.finalisation_reserve_s))

    def stage_allowance_s(self, stage_no: int, *, earned_multiple: float = 1.0) -> float:
        """The stage's allocation, stretched by what its yield has earned."""
        multiple = max(1.0, min(self.max_stage_multiple, float(earned_multiple)))
        spent = self.stage_spent_s(stage_no)
        allowance = max(0.0, self.stage_base_s(stage_no) * multiple - spent)
        if self.bounded:
            allowance = min(allowance, max(0.0, self.remaining_s - self.finalisation_reserve_s))
        return allowance

    # -- reporting ---------------------------------------------------------
    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            active_s=self.active_s, wall_s=self.wall_s, offline_s=self.offline_s,
            paused_manual_s=self.paused_manual_s, ceiling_s=self.ceiling_s,
            phase=self.phase, exhausted=self.retrieval_stopped or self.exhausted,
            stop_reason=self.stop_reason,
        )

    def announce(self, phase: str) -> bool:
        """True the first time a phase is reached, so it is logged once."""
        if phase in self._announced:
            return False
        self._announced.add(phase)
        return True

    def profile(self) -> dict[str, Any]:
        """Where the active time went, as a share of the whole (brief §93)."""
        spend = dict(self.stage_spend)
        if self._stage_no is not None:
            spend[self._stage_no] = self.stage_spent_s(self._stage_no)
        total = sum(spend.values()) or 1.0
        return {
            "active_s": round(self.active_s, 1),
            "by_stage_s": {str(k): round(v, 1) for k, v in sorted(spend.items())},
            "by_stage_pct": {str(k): round(100.0 * v / total, 1)
                             for k, v in sorted(spend.items())},
        }

    # -- persistence -------------------------------------------------------
    def persist(self, db: Database, run_id: str) -> None:
        """Write the clock down so a resumed run continues the same account."""
        try:
            db.update("run_control", {
                "active_elapsed_s": round(self.active_s, 2),
                "wall_elapsed_s": round(self.wall_s, 2),
                "offline_elapsed_s": round(self.offline_s, 2),
                "paused_manual_elapsed_s": round(self.paused_manual_s, 2),
                "budget_s": round(self.ceiling_s, 2),
                "budget_phase": self.phase,
                "updated_utc": utcnow(),
            }, {"run_id": run_id})
        except Exception as exc:              # the clock must never stop the run
            log.debug("could not persist the clock: %s", exc)

    @classmethod
    def carried_for(cls, db: Database, community_id: str) -> float:
        """Active seconds already spent on this community by earlier sessions.

        Reported, and used as the denominator of the lifetime yield rate, so a
        run resumed four times reports one honest total rather than four short
        ones (brief §107).
        """
        try:
            row = db.query_one(
                "SELECT SUM(COALESCE(c.active_elapsed_s, 0)) AS spent "
                "FROM run_control c JOIN runs r ON r.run_id = c.run_id "
                "WHERE c.community_id = ? AND r.status != 'complete'",
                (community_id,))
        except Exception:
            return 0.0
        return float(row["spent"] or 0.0) if row else 0.0


#: The clock was called `TimeBudget` while it was also the thing that decided
#: when to stop. It no longer decides, but the name is load-bearing in the
#: runner, the supervisor and the tests, so it stays as an alias.
TimeBudget = WorkBudget


def budget_from_settings(settings: Any, *, carried_active_s: float = 0.0,
                         clock: Any = None) -> WorkBudget:
    """Build the clock from configuration, so every number is visible."""
    config = dict(settings.get("budget", default={}) or {}) if settings else {}
    shares = config.get("stage_shares") or {}

    # HARVEST MODE SETS A CEILING, AND MEANS IT.
    #
    # The default is no ceiling, because a fixed cap is what cost this program
    # evidence before. But a 212-community run has to land inside a stated
    # window, and "no ceiling" plus one community with a fifty-thousand-page
    # site is how a two-day run becomes a two-week one. `budget.active_minutes`
    # still wins if an operator sets it explicitly; otherwise harvest mode's
    # per-community figure applies, and a community stopped by it is reported
    # COMPLETE_WITH_TRUNCATION rather than as though it had finished.
    ceiling_minutes = float(config.get("active_minutes", 0) or 0)
    if not ceiling_minutes and settings is not None:
        ceiling_minutes = float(
            settings.get("harvest", "max_minutes_per_community", default=0) or 0)

    return WorkBudget(
        ceiling_s=ceiling_minutes * 60.0,
        finalisation_reserve_s=float(config.get("finalisation_reserve_minutes", 3)) * 60.0,
        wind_down_s=float(config.get("wind_down_minutes", 2)) * 60.0,
        stage_shares={int(k): float(v) for k, v in shares.items()} or None,
        nominal_retrieval_s=float(
            config.get("nominal_retrieval_minutes",
                       DEFAULT_NOMINAL_RETRIEVAL_S / 60.0)) * 60.0,
        max_stage_multiple=float(config.get("max_stage_multiple",
                                            DEFAULT_MAX_STAGE_MULTIPLE)),
        carried_active_s=carried_active_s,
        clock=clock,
    )


__all__ = [
    "BudgetSnapshot", "DEFAULT_CEILING_S", "DEFAULT_FINALISATION_RESERVE_S",
    "DEFAULT_NOMINAL_RETRIEVAL_S", "DEFAULT_STAGE_SHARES", "DEFAULT_WIND_DOWN_S",
    "PHASE_FINALISATION", "PHASE_OVER", "PHASE_RETRIEVAL", "PHASE_WIND_DOWN",
    "TimeBudget", "WorkBudget", "budget_from_settings",
]
