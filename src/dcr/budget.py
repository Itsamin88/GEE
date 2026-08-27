"""The time budget: thirty minutes of work, and a workbook at the end of it.

The failure this exists to prevent is not "the crawl was slow". It is a crawl
that spent hours reaching a 400-page ceiling on one source, enumerating five
thousand archive URLs and extracting hundreds of images, and then had nothing to
show for it. Time spent is only worth anything if the run reaches finalisation.

So the budget is not a timeout. A timeout stops work; this reserves work.

    |<------------------ active budget, default 30 min ------------------>|
    |<---------- retrieval ---------->|<- wind-down ->|<- finalisation ->|
                                      ^               ^
                                      |               |
                        stop starting expensive     stop everything;
                        work; finish what is safe   reconcile and export

Three things follow from that shape.

**Active time is not wall-clock time.** A crawl paused by the researcher, or
waiting for the network to come back, is not working. Those seconds do not count
against the budget — otherwise an outage would silently eat the research
(brief §6, §26).

**The clock survives a restart.** A resumed run continues the same budget rather
than starting a fresh thirty minutes, so an interrupted community cannot quietly
consume three hours across four sessions (brief §27).

**Running out of budget is a normal ending, not a failure.** The run stops
starting new work, reconciles what it has, exports, and reports
COMPLETE_WITH_TRUNCATION with an honest account of what it did not reach. That
is a usable research record. Silence about the truncation would not be
(brief §28, §29, §30).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from .db import Database, utcnow
from .logging_setup import event, get_logger

log = get_logger("budget")

#: The whole active-processing allowance for one community.
DEFAULT_BUDGET_S = 30 * 60

#: Reserved at the end for reconciliation, export, verification and manifests.
#: Finalisation on a rich community takes well under this; the margin is there
#: so that a slow last document cannot eat the workbook.
DEFAULT_FINALISATION_RESERVE_S = 3 * 60

#: Before the reserve, a wind-down in which no NEW expensive work starts but
#: work already in flight may finish.
DEFAULT_WIND_DOWN_S = 2 * 60

#: What each stage may take, as a share of the retrieval budget. These are
#: ceilings, not allocations: a stage that finishes early hands the rest back,
#: and a community with one excellent website never touches most of them.
DEFAULT_STAGE_SHARES: dict[int, float] = {
    0: 0.04,    # build the source set
    1: 0.04,    # confirm the sources belong to this community
    2: 0.24,    # enumerate pages — the discovery that everything else feeds on
    3: 0.20,    # open the documents: the richest evidence per second
    4: 0.16,    # the archive, prioritised rather than enumerated
    5: 0.14,    # academic literature
    6: 0.10,    # grey literature
    7: 0.04,    # other web sources
    8: 0.04,    # local-language sweep
    9: 0.00,    # reconciliation is paid for out of the finalisation reserve
}

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
    budget_s: float = DEFAULT_BUDGET_S
    phase: str = PHASE_RETRIEVAL
    exhausted: bool = False

    @property
    def remaining_s(self) -> float:
        return max(0.0, self.budget_s - self.active_s)

    def as_dict(self) -> dict[str, Any]:
        return {
            "active_s": round(self.active_s, 1),
            "wall_clock_s": round(self.wall_s, 1),
            "offline_s": round(self.offline_s, 1),
            "paused_manual_s": round(self.paused_manual_s, 1),
            "budget_s": round(self.budget_s, 1),
            "remaining_s": round(self.remaining_s, 1),
            "phase": self.phase,
            "budget_exhausted": self.exhausted,
        }


class TimeBudget:
    """The active-processing clock for one community run.

    ``clock`` is injectable so tests can drive time forward deterministically
    instead of sleeping.
    """

    def __init__(
        self,
        *,
        budget_s: float = DEFAULT_BUDGET_S,
        finalisation_reserve_s: float = DEFAULT_FINALISATION_RESERVE_S,
        wind_down_s: float = DEFAULT_WIND_DOWN_S,
        stage_shares: Mapping[int, float] | None = None,
        clock: Any = None,
        carried_active_s: float = 0.0,
    ):
        self.budget_s = float(budget_s)
        self.finalisation_reserve_s = min(float(finalisation_reserve_s),
                                          self.budget_s * 0.5)
        self.wind_down_s = min(float(wind_down_s),
                               max(0.0, self.budget_s - self.finalisation_reserve_s) * 0.5)
        self.stage_shares = dict(stage_shares or DEFAULT_STAGE_SHARES)
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

    # -- the clock ---------------------------------------------------------
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
        return max(0.0, self.budget_s - self.active_s)

    # -- pausing -----------------------------------------------------------
    def pause(self, kind: str) -> None:
        """Stop the active clock. A paused crawl is not spending its budget."""
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

    # -- phases ------------------------------------------------------------
    @property
    def phase(self) -> str:
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
        return self.phase == PHASE_OVER

    def affords(self, estimated_s: float) -> bool:
        """Is there room for a task of this expected cost, and still finalise?

        The question the brief asks at §6: never begin a long operation likely
        to prevent finalisation.
        """
        if not self.may_start_expensive_work:
            return False
        return (self.remaining_s - self.finalisation_reserve_s) >= max(0.0, estimated_s)

    # -- per-stage ceilings -----------------------------------------------
    def stage_ceiling_s(self, stage_no: int) -> float:
        """The most this stage may spend, from its share of retrieval time."""
        retrieval = max(0.0, self.budget_s - self.finalisation_reserve_s
                        - self.wind_down_s)
        return retrieval * float(self.stage_shares.get(stage_no, 0.05))

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

    def stage_over_budget(self, stage_no: int | None = None) -> bool:
        """Has this stage used its share? A stage that has is asked to wrap up."""
        number = self._stage_no if stage_no is None else stage_no
        if number is None:
            return False
        return self.stage_spent_s(number) >= self.stage_ceiling_s(number)

    def stage_remaining_s(self, stage_no: int | None = None) -> float:
        number = self._stage_no if stage_no is None else stage_no
        if number is None:
            return self.remaining_s
        return max(0.0, min(self.stage_ceiling_s(number) - self.stage_spent_s(number),
                            self.remaining_s - self.finalisation_reserve_s))

    # -- reporting ---------------------------------------------------------
    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            active_s=self.active_s, wall_s=self.wall_s, offline_s=self.offline_s,
            paused_manual_s=self.paused_manual_s, budget_s=self.budget_s,
            phase=self.phase, exhausted=self.exhausted,
        )

    def announce(self, phase: str) -> bool:
        """True the first time a phase is reached, so it is logged once."""
        if phase in self._announced:
            return False
        self._announced.add(phase)
        return True

    def profile(self) -> dict[str, Any]:
        """Where the active time went, as a share of the whole (brief §49)."""
        self_spend = dict(self.stage_spend)
        if self._stage_no is not None:
            self_spend[self._stage_no] = self.stage_spent_s(self._stage_no)
        total = sum(self_spend.values()) or 1.0
        return {
            "active_s": round(self.active_s, 1),
            "by_stage_s": {str(k): round(v, 1) for k, v in sorted(self_spend.items())},
            "by_stage_pct": {str(k): round(100.0 * v / total, 1)
                             for k, v in sorted(self_spend.items())},
        }

    # -- persistence -------------------------------------------------------
    def persist(self, db: Database, run_id: str) -> None:
        """Write the clock down so a resumed run continues the same budget."""
        try:
            db.update("run_control", {
                "active_elapsed_s": round(self.active_s, 2),
                "wall_elapsed_s": round(self.wall_s, 2),
                "offline_elapsed_s": round(self.offline_s, 2),
                "paused_manual_elapsed_s": round(self.paused_manual_s, 2),
                "budget_s": round(self.budget_s, 2),
                "budget_phase": self.phase,
                "updated_utc": utcnow(),
            }, {"run_id": run_id})
        except Exception as exc:              # the clock must never stop the run
            log.debug("could not persist the budget: %s", exc)

    @classmethod
    def carried_for(cls, db: Database, community_id: str) -> float:
        """Active seconds already spent on this community by earlier sessions.

        Without this a resumed run would start a fresh thirty minutes, and an
        interrupted community could quietly consume hours across four sessions
        (brief §27).
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


def budget_from_settings(settings: Any, *, carried_active_s: float = 0.0,
                         clock: Any = None) -> TimeBudget:
    """Build the budget from configuration, so every number is visible."""
    config = dict(settings.get("budget", default={}) or {}) if settings else {}
    shares = config.get("stage_shares") or {}
    return TimeBudget(
        budget_s=float(config.get("active_minutes", 30)) * 60.0,
        finalisation_reserve_s=float(config.get("finalisation_reserve_minutes", 3)) * 60.0,
        wind_down_s=float(config.get("wind_down_minutes", 2)) * 60.0,
        stage_shares={int(k): float(v) for k, v in shares.items()} or None,
        carried_active_s=carried_active_s,
        clock=clock,
    )
