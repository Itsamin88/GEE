"""What the crawl is actually finding, measured, so that value can buy time.

The version this replaces answered "should I keep working?" with a clock. It
gave stage 4 sixteen per cent of twenty-five minutes and cut the archive off at
four, whether the archive was handing over a dated project report every forty
seconds or nothing at all. A crawl steered that way cannot tell a rich community
from a poor one, so it truncates the rich and idles on the poor, and the
research loses exactly the evidence it most wanted (brief §1, §62).

The objective the brief actually states is a rate (§25):

        useful independent evidence
        ---------------------------
           active processing time

This module measures the numerator and divides by the denominator. Nothing else
in the program decides how long to keep going; everything asks here.

## Not everything found is worth the same

A hundred repetitions of "we are a community in Portugal" is not a hundred
pieces of evidence. So each thing found is credited **once**, by an identity
key, and weighted by what it does for the research (§67):

    a workbook field covered for the first time          10
    dated onset evidence                                  9
    an academic record that verified                      9
    a genuinely new independence group                    8
    land-area evidence with a resolved semantic role      7
    an existing field corroborated from a NEW group       6
    a grey-literature record                              6
    practice evidence at documented or evidenced level    5
    a document nobody has seen before, by content hash    4
    a map, site plan or dated intervention photograph     4
    an ordinary supporting passage                        1
    anything already credited                             0

The weights are configuration, not constants in the code, so a methodologist
can change what the crawler values without touching Python.

## Two stopping rules, and neither is a clock

A scope — the whole run, one stage, one source, one archive domain — is asked to
stop when **both** of these hold, and never before its warm-up is over:

**Absolute.** Its recent yield rate has fallen below `absolute_floor` units per
active minute. Something producing almost nothing is not worth a worker.

**Relative.** Its recent rate has fallen below `decay_fraction` of its own best
sustained rate. This is the diminishing-return detector the brief asks for in
§66: a source that was producing 40 units/min and is now producing 3 has been
exhausted, even though 3 is not nothing in absolute terms. Judging each scope
against *itself* is what stops a rich source being held to a poor one's standard.

Both are measured over a sliding window of recent active time, so a slow patch
in the middle of a productive source does not end it, and a source that comes
back to life re-earns its time immediately.

## What this deliberately does not do

It does not stop a source that is still producing, for any reason other than an
operator asking or the machine failing. There is no ceiling here that a
productive crawl can hit. The one time-shaped thing that survives is the
**finalisation reserve** — work held back so that reconciliation, export and
verification always happen — and that is not a research cap: it is the guarantee
that the research reaches a workbook (§12).
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .logging_setup import get_logger

log = get_logger("yield")

# ---------------------------------------------------------------------------
# What a find is worth
# ---------------------------------------------------------------------------
#: Weights in "yield units". The scale is arbitrary; only the ratios matter,
#: and the floors below are expressed in the same units so they move together.
DEFAULT_WEIGHTS: dict[str, float] = {
    "field_first": 10.0,
    "onset_evidence": 9.0,
    "academic_verified": 9.0,
    "independence_group": 8.0,
    "land_area": 7.0,
    "field_corroborated": 6.0,
    "grey_record": 6.0,
    "practice": 5.0,
    "document_unique": 4.0,
    "map_image": 4.0,
    "alternative_name": 3.0,
    "dated_item": 2.0,
    "passage": 1.0,
    "page": 0.25,
    "duplicate": 0.0,
}

#: Kinds that count as *independent* research value rather than more of the
#: same. The report separates the two so "evidence yield" cannot be inflated by
#: crawling a site that repeats itself.
INDEPENDENT_KINDS = frozenset({
    "field_first", "field_corroborated", "independence_group", "onset_evidence",
    "land_area", "practice", "academic_verified", "grey_record", "map_image",
    "document_unique",
})

#: Below this many units per active minute, a scope is not paying for itself.
DEFAULT_ABSOLUTE_FLOOR = 2.0

#: A scope that has fallen to this fraction of its own best sustained rate is
#: in diminishing returns, however good that best rate was.
DEFAULT_DECAY_FRACTION = 0.15

#: The sliding window over which "recent" is measured, in active seconds.
DEFAULT_WINDOW_S = 120.0

#: Wider windows for the accounts whose quiet spells mean least. A source going
#: quiet for two minutes has probably been read; a whole community going quiet
#: for two minutes has probably just changed stage.
DEFAULT_SCOPE_WINDOWS: dict[str, float] = {
    "run": 600.0,
    "stage:": 300.0,
    "archive:": 180.0,
    "source:": 120.0,
}

#: No scope is judged before it has had this much active time. A source that
#: spent its first twenty seconds on robots.txt and a redirect has not yet had
#: the chance to produce anything.
DEFAULT_WARMUP_S = 45.0

#: Nor before this much has been attempted, so a stall on one slow request
#: cannot be read as exhaustion.
DEFAULT_WARMUP_ATTEMPTS = 8


@dataclass
class YieldEvent:
    """One credited find: what it was, what it was worth, when it landed."""

    kind: str
    weight: float
    at_active_s: float
    key: str = ""
    detail: str = ""


@dataclass
class ScopeState:
    """The running account for one scope."""

    name: str
    units: float = 0.0
    independent_units: float = 0.0
    credited: int = 0
    duplicates: int = 0
    attempts: int = 0
    active_s: float = 0.0
    peak_rate: float = 0.0
    #: How much recent active time "recent" means for THIS scope. A run is the
    #: least twitchy account and a source the most: a two-minute lull inside one
    #: source is ordinary, while two quiet minutes across a whole community is
    #: not yet evidence of anything.
    window_s: float = DEFAULT_WINDOW_S
    #: (active_s, weight) pairs inside the sliding window.
    window: deque = field(default_factory=deque)
    window_units: float = 0.0
    by_kind: dict[str, int] = field(default_factory=dict)
    #: Lifetime totals include what earlier sessions did, because the report
    #: wants one honest account of the community. These do not: a verdict is
    #: about what is happening NOW, and a resumed scope must earn a fresh
    #: reading rather than inherit last week's.
    session_active_s: float = 0.0
    session_attempts: int = 0
    #: Set once, so a scope's stop is reported with the reason that produced it.
    stop_reason: str = ""
    #: True while the scope is being given extra time it earned.
    extended: int = 0

    @property
    def rate(self) -> float:
        """Units per active minute over the sliding window.

        Divided by how much active time the window actually covers, not by the
        span between the first and last find in it. The difference matters: a
        window holding one find would otherwise read as an enormous rate,
        because the span between one event and itself is zero — which would make
        a source that produced one passage in ten minutes look like the most
        productive thing in the run.
        """
        covered = min(self.window_s, self.session_active_s)
        if covered < 1.0:
            return 0.0
        return self.window_units * 60.0 / covered

    @property
    def lifetime_rate(self) -> float:
        if self.active_s <= 0:
            return 0.0
        return self.units * 60.0 / self.active_s

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.name,
            "units": round(self.units, 2),
            "independent_units": round(self.independent_units, 2),
            "credited": self.credited,
            "duplicates": self.duplicates,
            "attempts": self.attempts,
            "active_s": round(self.active_s, 1),
            "rate_per_min": round(self.rate, 2),
            "lifetime_rate_per_min": round(self.lifetime_rate, 2),
            "peak_rate_per_min": round(self.peak_rate, 2),
            "by_kind": dict(sorted(self.by_kind.items())),
            "stop_reason": self.stop_reason,
            "extensions": self.extended,
        }


@dataclass
class Verdict:
    """The answer to 'should this scope keep working?', with its reasoning."""

    keep_going: bool
    reason: str
    rate: float = 0.0
    peak: float = 0.0
    floor: float = 0.0
    warming_up: bool = False

    def __bool__(self) -> bool:                       # `if meter.verdict(...):`
        return self.keep_going


class YieldMeter:
    """Evidence yield per unit of active time, for as many scopes as asked.

    One meter belongs to one community run. Scopes are named strings — `"run"`,
    `"stage:4"`, `"source:IC001-S002"`, `"archive:example.org"` — and are
    created on first use. The meter owns no clock of its own: active seconds
    come from the caller, which is what keeps paused and offline time out of the
    denominator (brief §32).
    """

    def __init__(
        self,
        *,
        weights: Mapping[str, float] | None = None,
        absolute_floor: float = DEFAULT_ABSOLUTE_FLOOR,
        decay_fraction: float = DEFAULT_DECAY_FRACTION,
        window_s: float = DEFAULT_WINDOW_S,
        warmup_s: float = DEFAULT_WARMUP_S,
        warmup_attempts: int = DEFAULT_WARMUP_ATTEMPTS,
        scope_windows: Mapping[str, float] | None = None,
    ):
        self.weights = {**DEFAULT_WEIGHTS, **dict(weights or {})}
        self.absolute_floor = float(absolute_floor)
        self.decay_fraction = float(decay_fraction)
        self.window_s = max(10.0, float(window_s))
        self.warmup_s = max(0.0, float(warmup_s))
        self.warmup_attempts = max(0, int(warmup_attempts))
        self.scope_windows: dict[str, float] = {
            **DEFAULT_SCOPE_WINDOWS, **dict(scope_windows or {})}
        self.scopes: dict[str, ScopeState] = {}
        #: Identity keys already credited, so nothing is paid for twice.
        self._seen: set[str] = set()
        self.events: list[YieldEvent] = []
        #: Kept small: the report wants the shape of the run, not every find.
        self.max_events = 4000

    # -- scopes ------------------------------------------------------------
    def scope(self, name: str) -> ScopeState:
        state = self.scopes.get(name)
        if state is None:
            state = ScopeState(name=name, window_s=self.window_for(name))
            self.scopes[name] = state
        return state

    def window_for(self, name: str) -> float:
        """How much recent active time this scope's verdict is based on.

        Wider for the accounts whose quiet spells are least meaningful. A run
        crossing between stages goes quiet for a minute as a matter of course;
        judging it on a two-minute window would end healthy runs at every
        stage boundary.
        """
        for prefix, seconds in self.scope_windows.items():
            if name == prefix or name.startswith(prefix):
                return float(seconds)
        return self.window_s

    def spend(self, active_s: float, scopes: Sequence[str]) -> None:
        """Charge active seconds to every scope the work belonged to.

        The same second is charged to the run, to its stage and to its source:
        they are nested views of one crawl, not competing accounts.
        """
        delta = max(0.0, float(active_s))
        if not delta:
            return
        for name in scopes:
            state = self.scope(name)
            state.active_s += delta
            state.session_active_s += delta
            self._trim(state)

    def attempt(self, scopes: Sequence[str], count: int = 1) -> None:
        """Note that work was tried, whether or not it produced anything."""
        for name in scopes:
            state = self.scope(name)
            state.attempts += int(count)
            state.session_attempts += int(count)

    # -- crediting ---------------------------------------------------------
    def credit(
        self,
        kind: str,
        *,
        key: str,
        scopes: Sequence[str],
        detail: str = "",
        weight: float | None = None,
    ) -> float:
        """Credit one find to every scope it belongs to. Returns what it earned.

        ``key`` is the identity of the thing found — a content hash, a field
        name, an independence-group id. A key already credited earns nothing,
        which is how repetition is kept out of the numerator (§25).
        """
        earned = float(self.weights.get(kind, 0.0)) if weight is None else float(weight)
        identity = f"{kind}:{key}"
        if identity in self._seen:
            for name in scopes:
                self.scope(name).duplicates += 1
            return 0.0
        self._seen.add(identity)
        if earned <= 0:
            for name in scopes:
                self.scope(name).duplicates += 1
            return 0.0

        independent = kind in INDEPENDENT_KINDS
        for name in scopes:
            state = self.scope(name)
            state.units += earned
            if independent:
                state.independent_units += earned
            state.credited += 1
            state.by_kind[kind] = state.by_kind.get(kind, 0) + 1
            state.window.append((state.session_active_s, earned))
            state.window_units += earned
            self._trim(state)
            rate = state.rate
            if rate > state.peak_rate:
                state.peak_rate = rate

        if len(self.events) < self.max_events:
            run = self.scope(scopes[0]) if scopes else self.scope("run")
            self.events.append(YieldEvent(kind=kind, weight=earned,
                                          at_active_s=run.active_s,
                                          key=key[:120], detail=detail[:200]))
        return earned

    def already_credited(self, kind: str, key: str) -> bool:
        return f"{kind}:{key}" in self._seen

    # -- the decision ------------------------------------------------------
    def verdict(
        self,
        name: str,
        *,
        absolute_floor: float | None = None,
        decay_fraction: float | None = None,
        warmup_s: float | None = None,
        warmup_attempts: int | None = None,
    ) -> Verdict:
        """Should this scope keep working? The whole stopping rule is here."""
        state = self.scope(name)
        floor = self.absolute_floor if absolute_floor is None else float(absolute_floor)
        decay = self.decay_fraction if decay_fraction is None else float(decay_fraction)
        warm_s = self.warmup_s if warmup_s is None else float(warmup_s)
        warm_n = self.warmup_attempts if warmup_attempts is None else int(warmup_attempts)

        if state.session_active_s < warm_s or state.session_attempts < warm_n:
            return Verdict(True, "still warming up: not yet judged", rate=state.rate,
                           peak=state.peak_rate, floor=floor, warming_up=True)


        rate = state.rate
        relative_floor = state.peak_rate * decay
        below_absolute = rate < floor
        below_relative = state.peak_rate > 0 and rate < relative_floor

        if below_absolute:
            # Which of the two descriptions is true matters to the reader of the
            # report. A scope whose best rate never reached the floor was never
            # productive; one that fell away from a high peak was exhausted.
            # They call for different follow-up, so they are not merged.
            if state.peak_rate < floor:
                reason = (
                    f"yield never rose above the {floor:.1f} units/min floor "
                    f"(best {state.peak_rate:.1f}/min over "
                    f"{state.session_active_s / 60:.1f} min)"
                )
                state.stop_reason = reason
                return Verdict(False, reason, rate=rate, peak=state.peak_rate,
                               floor=floor)
            if below_relative:
                reason = (
                    f"yield fell to {rate:.1f} units/min — below the {floor:.1f} floor "
                    f"and below {decay:.0%} of its own best ({state.peak_rate:.1f}/min) "
                    f"after {state.session_active_s / 60:.1f} min of work"
                )
                state.stop_reason = reason
                return Verdict(False, reason, rate=rate, peak=state.peak_rate,
                               floor=floor)

        if rate >= floor:
            state.extended += 1
        return Verdict(
            True,
            f"still yielding {rate:.1f} units/min "
            f"(floor {floor:.1f}, own best {state.peak_rate:.1f})",
            rate=rate, peak=state.peak_rate, floor=floor,
        )

    def worth_continuing(self, name: str, **kwargs: Any) -> bool:
        return self.verdict(name, **kwargs).keep_going

    # -- how much more time a scope has earned ------------------------------
    def earned_extension_s(self, name: str, *, base_s: float,
                           max_multiple: float = 8.0) -> float:
        """Extra active seconds this scope's yield justifies.

        Used where a bounded allocation is genuinely needed — the archive's
        snapshot allowance, a source's page budget — so the allocation grows
        with what the source is producing instead of being a constant. A scope
        producing at twice the floor earns twice its base; one producing at
        eight times earns the cap.
        """
        state = self.scope(name)
        if self.absolute_floor <= 0:
            return base_s * max_multiple
        multiple = state.rate / self.absolute_floor
        multiple = max(0.0, min(float(max_multiple), multiple))
        return float(base_s) * multiple

    # -- reporting ---------------------------------------------------------
    def snapshot(self, *, top: int = 20) -> dict[str, Any]:
        run = self.scope("run")
        ordered = sorted(self.scopes.values(), key=lambda s: -s.units)[:top]
        return {
            "units": round(run.units, 2),
            "independent_units": round(run.independent_units, 2),
            "credited": run.credited,
            "duplicates_rejected": run.duplicates,
            "active_s": round(run.active_s, 1),
            "evidence_yield_per_min": round(run.lifetime_rate, 2),
            "independent_yield_per_min": round(
                run.independent_units * 60.0 / run.active_s if run.active_s else 0.0, 2),
            "recent_rate_per_min": round(run.rate, 2),
            "peak_rate_per_min": round(run.peak_rate, 2),
            "by_kind": dict(sorted(run.by_kind.items())),
            "scopes": [s.as_dict() for s in ordered],
        }

    def curve(self, buckets: int = 12) -> list[dict[str, float]]:
        """Yield against active time, for the profile report (brief §93).

        Shows the shape the stopping rule is reacting to: whether the run was
        still climbing when it ended, or had flattened out long before.
        """
        run = self.scope("run")
        if not self.events or run.active_s <= 0:
            return []
        width = run.active_s / max(1, buckets)
        out: list[dict[str, float]] = []
        for index in range(buckets):
            low, high = index * width, (index + 1) * width
            units = sum(e.weight for e in self.events if low <= e.at_active_s < high)
            out.append({
                "from_min": round(low / 60.0, 2),
                "to_min": round(high / 60.0, 2),
                "units": round(units, 2),
                "per_min": round(units * 60.0 / width, 2) if width else 0.0,
            })
        return out

    # -- persistence -------------------------------------------------------
    def state_for_resume(self) -> dict[str, Any]:
        """Everything a resumed run needs to continue the same accounting.

        The identity keys matter most: without them a resumed crawl would
        re-credit every document it already has and conclude, wrongly, that the
        source it had exhausted is productive again.
        """
        return {
            "seen": sorted(self._seen),
            "scopes": {
                name: {
                    "units": state.units,
                    "independent_units": state.independent_units,
                    "credited": state.credited,
                    "duplicates": state.duplicates,
                    "attempts": state.attempts,
                    "active_s": state.active_s,
                    "peak_rate": state.peak_rate,
                    "by_kind": dict(state.by_kind),
                }
                for name, state in self.scopes.items()
            },
        }

    def restore(self, payload: Mapping[str, Any] | None) -> None:
        if not payload:
            return
        self._seen |= set(payload.get("seen") or ())
        for name, values in (payload.get("scopes") or {}).items():
            state = self.scope(name)
            state.units = float(values.get("units", 0.0))
            state.independent_units = float(values.get("independent_units", 0.0))
            state.credited = int(values.get("credited", 0))
            state.duplicates = int(values.get("duplicates", 0))
            state.attempts = int(values.get("attempts", 0))
            state.active_s = float(values.get("active_s", 0.0))
            state.peak_rate = float(values.get("peak_rate", 0.0))
            state.by_kind = dict(values.get("by_kind") or {})
            # session_active_s, session_attempts and the window are deliberately
            # NOT restored: a verdict is about what is happening now, so a
            # resumed scope starts its warm-up again rather than inheriting a
            # stale reading from a previous session.
            # The window is deliberately not restored: "recent" means recent in
            # this session. A resumed source starts its warm-up again rather
            # than inheriting a stale verdict from last week.

    # -- internals ---------------------------------------------------------
    def _trim(self, state: ScopeState) -> None:
        cutoff = state.session_active_s - state.window_s
        while state.window and state.window[0][0] < cutoff:
            _, weight = state.window.popleft()
            state.window_units -= weight
        if state.window_units < 0:
            state.window_units = 0.0


def meter_from_settings(settings: Any) -> YieldMeter:
    """Build the meter from configuration, so every number is visible."""
    config: Mapping[str, Any] = {}
    if settings is not None:
        try:
            config = dict(settings.get("yield", default={}) or {})
        except Exception:                       # a meter must never stop a run
            config = {}
    return YieldMeter(
        weights=config.get("weights") or None,
        absolute_floor=float(config.get("absolute_floor_per_min", DEFAULT_ABSOLUTE_FLOOR)),
        decay_fraction=float(config.get("decay_fraction", DEFAULT_DECAY_FRACTION)),
        window_s=float(config.get("window_minutes", DEFAULT_WINDOW_S / 60.0)) * 60.0,
        warmup_s=float(config.get("warmup_minutes", DEFAULT_WARMUP_S / 60.0)) * 60.0,
        warmup_attempts=int(config.get("warmup_attempts", DEFAULT_WARMUP_ATTEMPTS)),
        scope_windows={k: float(v) * 60.0
                       for k, v in (config.get("scope_window_minutes") or {}).items()}
        or None,
    )


__all__ = [
    "DEFAULT_SCOPE_WINDOWS", "DEFAULT_WEIGHTS", "INDEPENDENT_KINDS", "ScopeState", "Verdict", "YieldEvent",
    "YieldMeter", "meter_from_settings",
]
