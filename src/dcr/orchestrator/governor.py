"""How many communities this machine can actually carry, right now.

The brief asks for eight to sixteen communities at once and then says the real
instruction plainly: *do not create a system where increasing workers makes
total processing slower* (§3). Those two are in tension, and the second one wins
— sixteen workers on a four-core laptop with a slow connection is not sixteen
times the research, it is sixteen processes taking turns and a machine the
researcher cannot use.

So the worker count is not configuration. It is a measurement, taken every few
seconds, of whether the last change helped.

## The signals, and what each one means

**Memory** is the hard one. A worker holding a 200 MB PDF and a browser page can
want a gigabyte, and the failure mode when memory runs out on Windows is not a
slow run but a killed process and a half-written database. Memory pressure
therefore reduces the count immediately and is never traded against throughput.

**CPU** is the soft one. High CPU with work still queued is a healthy saturated
machine, not a problem — this workload is dominated by waiting on the network,
so CPU near the ceiling means the parsing side is keeping up. It stops growth;
it does not force a cut until it is high enough to make the machine unusable.

**Idle waiting** is the signal to grow. Low CPU, low memory and workers blocked
on sockets is exactly the case the whole design exists for: the machine has
capacity and the network is the constraint, so another community costs almost
nothing and gets its own independent waiting.

**Throughput** is the arbiter. Everything above is a proxy; this is the thing
itself. The governor remembers the completion rate observed at each worker
count, and if raising the count did not raise throughput it goes back down and
stays there. That is what makes "eight performs better than sixteen" a finding
the software can act on rather than a guess a person has to make (brief §97).

## Deliberately conservative about growing

Growth is one worker at a time with a settling period between, because a new
worker's cost arrives immediately and its benefit arrives a minute later. Cuts
can be more than one at a time, because the failures they prevent are worse than
the throughput they lose.

`psutil` is used where available and the governor works without it: on a machine
with no `psutil` it falls back to a fixed, conservative count and says so, which
is better than pretending to measurements it does not have.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..logging_setup import event, get_logger

log = get_logger("orchestrator.governor")

try:                                    # optional, and the code says so
    import psutil                       # type: ignore
except Exception:                       # pragma: no cover - depends on the machine
    psutil = None                       # type: ignore


#: Memory above this share means cut workers now, whatever throughput says. A
#: killed worker costs a community; a slow run costs minutes.
MEMORY_CUT_PCT = 88.0

#: And above this, cut hard: two at a time.
MEMORY_EMERGENCY_PCT = 94.0

#: CPU above this stops growth. It does not force a cut: this workload waits on
#: the network, so a busy CPU usually means parsing is keeping up.
CPU_HOLD_PCT = 85.0

#: CPU above this for a sustained period does force a cut — at this point the
#: machine is no longer usable for anything else.
CPU_CUT_PCT = 96.0

#: Below this, with work queued, there is room for another community.
CPU_GROW_PCT = 62.0

#: Memory must be below this before growing.
MEMORY_GROW_PCT = 72.0

#: Seconds between decisions. Long enough for a new worker's effect to appear.
DEFAULT_SETTLE_S = 20.0

#: How many completions to remember per worker count when comparing throughput.
THROUGHPUT_WINDOW = 12


@dataclass
class ResourceSample:
    """What the machine looked like at one moment."""

    cpu_pct: float = 0.0
    memory_pct: float = 0.0
    memory_available_mb: float = 0.0
    load_avg: float = 0.0
    disk_busy_pct: float = 0.0
    measured: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "cpu_pct": round(self.cpu_pct, 1),
            "memory_pct": round(self.memory_pct, 1),
            "memory_available_mb": round(self.memory_available_mb, 1),
            "load_avg": round(self.load_avg, 2),
            "measured": self.measured,
        }


@dataclass
class Decision:
    """What the governor decided, and the sentence explaining it."""

    target: int
    previous: int
    reason: str
    sample: ResourceSample = field(default_factory=ResourceSample)

    @property
    def changed(self) -> bool:
        return self.target != self.previous


def detect_cpu_count() -> int:
    try:
        if psutil is not None:
            return int(psutil.cpu_count(logical=True) or os.cpu_count() or 4)
    except Exception:
        pass
    return int(os.cpu_count() or 4)


def sample_resources() -> ResourceSample:
    """One reading of the machine. Never raises: a governor that throws is worse
    than one that guesses."""
    if psutil is None:
        return ResourceSample(measured=False)
    try:
        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        try:
            load = os.getloadavg()[0]
        except (AttributeError, OSError):    # Windows has no load average
            load = cpu / 100.0 * detect_cpu_count()
        return ResourceSample(
            cpu_pct=float(cpu),
            memory_pct=float(memory.percent),
            memory_available_mb=float(memory.available) / (1024 * 1024),
            load_avg=float(load),
            measured=True,
        )
    except Exception as exc:                 # pragma: no cover
        log.debug("could not sample resources: %s", exc)
        return ResourceSample(measured=False)


class ResourceGovernor:
    """Decides how many communities may run at once, and revises it.

    The caller asks `decide()` every few seconds and moves toward the target it
    returns. Nothing here starts or stops a worker; that belongs to the pool.
    """

    def __init__(
        self,
        *,
        minimum: int = 1,
        maximum: int = 16,
        start: int | None = None,
        settle_s: float = DEFAULT_SETTLE_S,
        memory_reserve_mb: float = 1200.0,
        memory_per_worker_mb: float = 550.0,
        config: Mapping[str, Any] | None = None,
        clock: Any = None,
    ):
        config = dict(config or {})
        self.minimum = max(1, int(config.get("min_workers", minimum)))
        self.maximum = max(self.minimum, int(config.get("max_workers", maximum)))
        self.settle_s = float(config.get("settle_seconds", settle_s))
        self.memory_reserve_mb = float(
            config.get("memory_reserve_mb", memory_reserve_mb))
        self.memory_per_worker_mb = float(
            config.get("memory_per_worker_mb", memory_per_worker_mb))
        self.cpu_count = detect_cpu_count()
        self._clock = clock or time.monotonic
        #: Lowered when a higher count is MEASURED to be worse than a lower one.
        #: Never raised: the governor does not go looking again for a count it
        #: has already shown does not pay.
        self.effective_maximum = self.maximum
        self.target = self._starting_target(
            start if start is not None else config.get("start_workers"))
        self._last_decision_at = self._clock() - self.settle_s
        #: Completion rates observed at each worker count (brief §96, §97).
        self._throughput: dict[int, deque] = {}
        self._completions: list[tuple[float, int]] = []
        self.samples: list[ResourceSample] = []
        self.decisions: list[Decision] = []
        #: Set once a count has been shown not to pay for itself.
        self._proven_ceiling: int | None = None

    # -- starting point ----------------------------------------------------
    def _starting_target(self, requested: Any) -> int:
        """Where to begin, before anything has been observed.

        Eight where the machine can carry eight, fewer where it plainly cannot.
        Starting at the maximum would mean the first minutes of every run are
        spent recovering from a bad guess.
        """
        if requested:
            return max(self.minimum, min(self.maximum, int(requested)))
        sample = sample_resources()
        by_cpu = max(self.minimum, min(self.maximum, self.cpu_count * 2))
        if not sample.measured:
            # No measurements: be conservative and say so.
            return max(self.minimum, min(self.maximum, min(8, by_cpu)))
        usable_mb = max(0.0, sample.memory_available_mb - self.memory_reserve_mb)
        by_memory = int(usable_mb // max(64.0, self.memory_per_worker_mb))
        return max(self.minimum, min(self.maximum, min(8, by_cpu, max(1, by_memory))))

    # -- observations ------------------------------------------------------
    def note_completion(self, *, workers: int, active_s: float) -> None:
        """A community finished. Throughput is completions per worker-minute.

        Dividing by worker-minutes rather than wall-clock is what makes the
        comparison fair: sixteen workers completing more per hour than eight is
        expected, and says nothing about whether the sixteenth was worth having.
        """
        if active_s <= 0:
            return
        rate = 60.0 / active_s
        history = self._throughput.setdefault(max(1, int(workers)), deque(
            maxlen=THROUGHPUT_WINDOW))
        history.append(rate)
        self._completions.append((self._clock(), int(workers)))

    def throughput_at(self, workers: int) -> float:
        history = self._throughput.get(int(workers))
        if not history:
            return 0.0
        return sum(history) / len(history)

    def observed_throughput(self) -> dict[int, float]:
        return {count: round(self.throughput_at(count), 4)
                for count in sorted(self._throughput)}

    # -- the decision ------------------------------------------------------
    def decide(self, *, running: int, queued: int,
               sample: ResourceSample | None = None) -> Decision:
        """Revise the target worker count. Cheap enough to call every second."""
        now = self._clock()
        reading = sample if sample is not None else sample_resources()
        self.samples.append(reading)
        previous = self.target

        # Pressure is acted on immediately: waiting for the settling period
        # while memory fills is how a worker gets killed.
        urgent = self._pressure(reading)
        if urgent is not None:
            self.target = urgent.target
            self._last_decision_at = now
            urgent.sample = reading
            self.decisions.append(urgent)
            if urgent.changed:
                event(log, "SCHEDULER", urgent.reason)
            return urgent

        if now - self._last_decision_at < self.settle_s:
            return Decision(self.target, previous,
                            "settling after the last change", reading)

        decision = self._consider_growth(running=running, queued=queued,
                                         sample=reading)
        self.target = decision.target
        self._last_decision_at = now
        decision.sample = reading
        self.decisions.append(decision)
        if decision.changed:
            event(log, "SCHEDULER", decision.reason)
        return decision

    def _pressure(self, sample: ResourceSample) -> Decision | None:
        """Anything that means cut now, regardless of throughput."""
        if not sample.measured:
            return None
        previous = self.target
        if sample.memory_pct >= MEMORY_EMERGENCY_PCT:
            target = max(self.minimum, self.target - 2)
            return Decision(target, previous,
                            f"memory at {sample.memory_pct:.0f}% — cutting to {target} "
                            "workers before one is killed mid-write", sample)
        if sample.memory_pct >= MEMORY_CUT_PCT:
            target = max(self.minimum, self.target - 1)
            return Decision(target, previous,
                            f"memory at {sample.memory_pct:.0f}% — down to {target} "
                            "workers", sample)
        if sample.cpu_pct >= CPU_CUT_PCT and self.target > self.minimum:
            recent = [s for s in self.samples[-4:] if s.measured]
            if len(recent) >= 3 and all(s.cpu_pct >= CPU_CUT_PCT for s in recent):
                target = max(self.minimum, self.target - 1)
                return Decision(target, previous,
                                f"CPU pinned at {sample.cpu_pct:.0f}% — down to "
                                f"{target} workers to keep the machine usable", sample)
        return None

    def _consider_growth(self, *, running: int, queued: int,
                         sample: ResourceSample) -> Decision:
        previous = self.target

        if queued <= 0:
            return Decision(self.target, previous,
                            "nothing queued; the count stands", sample)

        # Did the last increase actually help? This is the arbiter (brief §97).
        regression = self._throughput_regression()
        if regression is not None and self._proven_ceiling is None:
            better, worse, gain = regression
            # The measurement is acted on, not merely noted: the governor lowers
            # its OWN ceiling to the count that performed best. The objective is
            # the shortest reliable wall-clock time, not the largest worker
            # count, so having measured that more workers is worse it does not
            # go looking for that again (brief §3, §97).
            self._proven_ceiling = worse
            self.effective_maximum = max(self.minimum, better)
            target = max(self.minimum, better)
            return Decision(
                target, previous,
                f"{worse} workers completed {abs(gain):.0%} less per worker-minute "
                f"than {better}; the ceiling for this run is now {better}", sample)

        ceiling = min(self.maximum, self.effective_maximum)
        if self.target >= ceiling:
            reason = (f"at the configured maximum of {self.maximum}"
                      if ceiling == self.maximum else
                      f"at {ceiling}, the count measured to be best on this machine")
            return Decision(self.target, previous, reason, sample)

        # Only grow when the workers we have are all busy: adding a worker while
        # one is idle adds contention and no work.
        if running < self.target:
            return Decision(self.target, previous,
                            f"{running} of {self.target} workers busy; no need for "
                            "another", sample)

        if not sample.measured:
            # Without measurements, grow very cautiously and only to eight.
            if self.target < min(8, ceiling):
                target = self.target + 1
                return Decision(target, previous,
                                f"no resource measurements available (psutil not "
                                f"installed); growing cautiously to {target}", sample)
            return Decision(self.target, previous,
                            "no resource measurements available; holding at "
                            f"{self.target}", sample)

        usable_mb = sample.memory_available_mb - self.memory_reserve_mb
        if usable_mb < self.memory_per_worker_mb:
            return Decision(self.target, previous,
                            f"only {max(0.0, usable_mb):.0f} MB free above the reserve; "
                            "not enough for another worker", sample)
        if sample.memory_pct > MEMORY_GROW_PCT:
            return Decision(self.target, previous,
                            f"memory at {sample.memory_pct:.0f}%; holding at "
                            f"{self.target} workers", sample)
        if sample.cpu_pct > CPU_HOLD_PCT:
            return Decision(self.target, previous,
                            f"CPU at {sample.cpu_pct:.0f}%; holding at {self.target} "
                            "workers", sample)
        if sample.cpu_pct < CPU_GROW_PCT:
            target = min(ceiling, self.target + 1)
            return Decision(target, previous,
                            f"CPU {sample.cpu_pct:.0f}%, memory {sample.memory_pct:.0f}%, "
                            f"{queued} communities queued and every worker busy — "
                            f"the machine is waiting on the network, so up to {target}",
                            sample)
        return Decision(self.target, previous,
                        f"CPU {sample.cpu_pct:.0f}% is neither idle nor saturated; "
                        f"holding at {self.target}", sample)

    def _throughput_regression(self) -> tuple[int, int, float] | None:
        """Has a higher worker count been measured to be worse than a lower one?

        Returns (better_count, worse_count, relative_gain) or None. Both counts
        must have completed enough communities for the comparison to mean
        anything — three is few, but a run of eight communities will not produce
        twenty, and refusing to decide until it does would mean never deciding.
        """
        counts = sorted(c for c in self._throughput if len(self._throughput[c]) >= 3)
        if len(counts) < 2:
            return None
        best_count = max(counts, key=self.throughput_at)
        highest = max(counts)
        if best_count >= highest:
            return None
        best = self.throughput_at(best_count)
        worst = self.throughput_at(highest)
        if best <= 0:
            return None
        gain = (worst - best) / best
        # A 10% difference on a handful of samples is noise, not a finding.
        if gain > -0.10:
            return None
        return best_count, highest, gain

    # -- reporting ---------------------------------------------------------
    def report(self) -> dict[str, Any]:
        measured = [s for s in self.samples if s.measured]
        return {
            "target_workers": self.target,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "effective_maximum": self.effective_maximum,
            "cpu_count": self.cpu_count,
            "resource_measurements_available": psutil is not None,
            "samples": len(self.samples),
            "mean_cpu_pct": round(
                sum(s.cpu_pct for s in measured) / len(measured), 1) if measured else None,
            "peak_cpu_pct": round(max((s.cpu_pct for s in measured), default=0.0), 1),
            "mean_memory_pct": round(
                sum(s.memory_pct for s in measured) / len(measured), 1) if measured else None,
            "peak_memory_pct": round(max((s.memory_pct for s in measured), default=0.0), 1),
            "throughput_per_worker_minute": self.observed_throughput(),
            "proven_ceiling": self._proven_ceiling,
            "decisions": [
                {"target": d.target, "from": d.previous, "reason": d.reason}
                for d in self.decisions if d.changed
            ][-40:],
        }


__all__ = ["Decision", "ResourceGovernor", "ResourceSample", "detect_cpu_count",
           "sample_resources"]
