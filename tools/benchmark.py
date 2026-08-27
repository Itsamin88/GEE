#!/usr/bin/env python3
"""Measure what the parallelism is actually worth on this machine.

    python3 tools/benchmark.py                 1, 4, 8 and 16 workers
    python3 tools/benchmark.py --workers 1,8   only those two
    python3 tools/benchmark.py --communities 24

The brief is explicit (§96): *do not claim "16x faster" without evidence*. So
this runs the same set of communities at several worker counts against the local
fixture web and reports what happened, including when a higher count was worse.

## What is measured, and what each number means

**Wall-clock** — the thing the researcher waits for. The only number that
matters on its own.

**Speed-up** — wall-clock at one worker divided by wall-clock at N. Never
reported without the one-worker baseline it is relative to.

**Throughput per worker-minute** — completions divided by (workers × minutes).
This is what says whether the sixteenth worker was worth having: more per hour
at sixteen workers than at eight is expected and proves nothing.

**Efficiency** — speed-up divided by N. 1.0 would be perfect and never happens.

**CPU and memory** — sampled every second, so "it saturated the machine" is an
observation rather than a guess.

**Fairness** — the spread between the first and last community to finish, and
how long the longest wait was. A run that is fast because it starved half the
queue is not fast.

## Fitting the curve

From the observed speed-ups the script fits the Universal Scalability Law that
`plan.py` uses for its estimates:

    speed-up(N) = N / (1 + σ(N-1) + κN(N-1))

σ is the share that cannot overlap; κ is interference between workers, and it is
what lets the curve bend DOWN — which is why sixteen workers can be slower than
twelve. The fitted values are printed in a form that can be pasted into
`config/config.yaml`, so the estimate the researcher sees before pressing START
reflects their machine rather than a model's assumptions.

## Honesty

A fixture on loopback has no network latency, so the absolute times mean nothing
about a real crawl. What it measures faithfully is the SHAPE — where the curve
flattens, and where more workers stop paying — because that comes from process
startup, database contention, the scheduler and the host broker, all of which
are the real ones. Every number printed is labelled with what produced it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import psutil
except Exception:                                  # pragma: no cover
    psutil = None


@dataclass
class Sample:
    at: float
    cpu_pct: float
    memory_pct: float
    memory_used_mb: float


@dataclass
class Measurement:
    """One run of the whole queue at one worker count."""

    workers: int
    communities: int
    wall_s: float
    completed: int
    failed: int
    evidence: int
    documents: int
    pages: int
    active_s: float
    samples: list[Sample] = field(default_factory=list)
    completion_times: list[float] = field(default_factory=list)
    peak_workers: int = 0

    @property
    def throughput_per_hour(self) -> float:
        return self.finished * 3600.0 / self.wall_s if self.wall_s else 0.0

    @property
    def finished(self) -> int:
        """Communities that reached a final status, whatever it was.

        Throughput is about work done. A community that finished
        COMPLETE_WITH_TRUNCATION cost the same as one that finished COMPLETE,
        and counting only the latter would make the benchmark's throughput
        depend on the fixture's quality thresholds rather than on the
        scheduler.
        """
        return self.completed + self.failed

    @property
    def per_worker_minute(self) -> float:
        worker_minutes = self.workers * self.wall_s / 60.0
        return self.finished / worker_minutes if worker_minutes else 0.0

    @property
    def mean_cpu(self) -> float:
        return statistics.mean([s.cpu_pct for s in self.samples]) if self.samples else 0.0

    @property
    def peak_cpu(self) -> float:
        return max((s.cpu_pct for s in self.samples), default=0.0)

    @property
    def peak_memory_mb(self) -> float:
        return max((s.memory_used_mb for s in self.samples), default=0.0)

    @property
    def mean_memory_pct(self) -> float:
        return statistics.mean([s.memory_pct for s in self.samples]) if self.samples else 0.0

    @property
    def fairness_spread_s(self) -> float:
        """First finish to last finish. A run that starved half the queue is
        not fast, however good its wall-clock looks."""
        if len(self.completion_times) < 2:
            return 0.0
        return max(self.completion_times) - min(self.completion_times)

    def as_dict(self) -> dict[str, Any]:
        return {
            "workers": self.workers,
            "communities": self.communities,
            "wall_s": round(self.wall_s, 2),
            "completed": self.completed,
            "failed": self.failed,
            "finished": self.finished,
            "evidence": self.evidence,
            "documents": self.documents,
            "pages": self.pages,
            "total_active_s": round(self.active_s, 1),
            "throughput_per_hour": round(self.throughput_per_hour, 1),
            "completions_per_worker_minute": round(self.per_worker_minute, 3),
            "mean_cpu_pct": round(self.mean_cpu, 1),
            "peak_cpu_pct": round(self.peak_cpu, 1),
            "mean_memory_pct": round(self.mean_memory_pct, 1),
            "peak_memory_mb": round(self.peak_memory_mb, 1),
            "fairness_spread_s": round(self.fairness_spread_s, 2),
            "peak_concurrent_workers": self.peak_workers,
        }


class ResourceWatcher(threading.Thread):
    """Samples the machine once a second while a measurement runs."""

    def __init__(self, interval_s: float = 1.0):
        super().__init__(daemon=True)
        self.interval_s = interval_s
        self.samples: list[Sample] = []
        self._halt = threading.Event()

    def run(self) -> None:
        if psutil is None:
            return
        psutil.cpu_percent(interval=None)
        started = time.monotonic()
        while not self._halt.wait(self.interval_s):
            try:
                memory = psutil.virtual_memory()
                self.samples.append(Sample(
                    at=time.monotonic() - started,
                    cpu_pct=psutil.cpu_percent(interval=None),
                    memory_pct=memory.percent,
                    memory_used_mb=(memory.total - memory.available) / (1024 * 1024),
                ))
            except Exception:
                return

    def stop(self) -> list[Sample]:
        self._halt.set()
        self.join(timeout=3.0)
        return self.samples


# ---------------------------------------------------------------------------
# fitting the scalability law
# ---------------------------------------------------------------------------
def fit_scalability(points: Sequence[tuple[int, float]]) -> tuple[float, float, float]:
    """Least-squares fit of (contention, coherency) to observed speed-ups.

    A coarse grid rather than a solver: two parameters, a bounded range, and no
    dependency worth adding for it. Returns (contention, coherency, error).
    """
    usable = [(n, s) for n, s in points if n >= 1 and s > 0]
    if len(usable) < 2:
        return 0.05, 0.0008, float("inf")

    best = (0.05, 0.0008, float("inf"))
    # Wide enough to contain a hard saturation. A grid whose optimum sits on
    # its own boundary has not fitted anything; it has run out of room.
    contention_values = [i / 400.0 for i in range(0, 361)]        # 0 .. 0.90
    coherency_values = [i / 100000.0 for i in range(0, 1001)]     # 0 .. 0.010
    for contention in contention_values:
        for coherency in coherency_values:
            error = 0.0
            for count, observed in usable:
                denominator = (1.0 + contention * (count - 1)
                               + coherency * count * (count - 1))
                predicted = count / max(1e-9, denominator)
                error += (predicted - observed) ** 2
            if error < best[2]:
                best = (contention, coherency, error)
    return best


# ---------------------------------------------------------------------------
# one measurement
# ---------------------------------------------------------------------------
def measure(workers: int, communities: int, *, output_root: Path,
            server: Any, root: Path) -> Measurement:
    from dcr.orchestrator.session import RunSession
    from dcr.orchestrator.store import COMPLETED, FAILED
    from fixtures.harness import fixture_settings, fixture_urls

    settings = fixture_settings(server.port, output_root, root=root)
    # Keep every community small and identical, so the only variable is the
    # worker count. A benchmark whose communities differ measures the
    # communities, not the parallelism.
    settings.app["crawl"]["base_pages_per_source"] = 25
    settings.app["crawl"]["max_pages_per_run"] = 120
    # Every stage stays ON. A community with stages switched off is truncated
    # by definition and would never reach COMPLETE, so a benchmark that
    # disabled them would measure zero completions per hour however fast it
    # ran. Keeping them also means the benchmark exercises the shared-host
    # broker, which is where cross-community contention actually lives.
    settings.app["estimation"] = {"enabled": False}
    settings.app["quality"] = dict(settings.app.get("quality") or {})
    settings.app["quality"]["min_pages_opened"] = 1
    # Sample the scheduler often enough for a short run to be measured at all.
    settings.app.setdefault("orchestrator", {})
    settings.app["orchestrator"] = dict(settings.app.get("orchestrator") or {})
    settings.app["orchestrator"]["sample_seconds"] = 0.5
    settings.app["orchestrator"]["tick_seconds"] = 0.1
    # The benchmark measures the scheduler, not the researcher's reading: one
    # completion summary per community times sixteen communities times four
    # worker counts is a thousand lines of noise around the numbers.
    settings.app["logging"] = dict(settings.app.get("logging") or {})
    settings.app["logging"]["console_level"] = "ERROR"
    settings.app["logging"]["quiet_summary"] = True

    session = RunSession(settings=settings)
    session.settings_overrides = dict(settings.app)
    session.sources_overrides = dict(settings.sources)
    entries = [
        {"name": f"Benchmark {index:03d}",
         "country": "France" if index % 2 else "Netherlands",
         "coder_id": "BENCH",
         "urls": fixture_urls(server.port, "pourgues" if index % 2 else "boekel")}
        for index in range(1, communities + 1)
    ]
    plan = session.create(entries, mode="FULL")
    for job in plan.jobs:
        session.store.update_job(job.job_id, {"fixture": 1})

    watcher = ResourceWatcher()
    watcher.start()
    started = time.monotonic()
    try:
        session.start(workers_max=workers, show_dashboard=False)
    finally:
        samples = watcher.stop()
    wall_s = time.monotonic() - started

    counts = session.store.counts(session.run_id)
    totals = session.store.totals(session.run_id)
    jobs = session.store.jobs(session.run_id)
    scheduler_samples = session.store.samples(session.run_id)
    peak = max((int(row["workers"] or 0) for row in scheduler_samples), default=workers)

    completion_times: list[float] = []
    for job in jobs:
        if job.wall_s:
            completion_times.append(float(job.wall_s))

    measurement = Measurement(
        workers=workers,
        communities=communities,
        wall_s=wall_s,
        completed=int(counts.get(COMPLETED, 0)),
        failed=int(counts.get(FAILED, 0)),
        evidence=int(totals.get("evidence", 0) or 0),
        documents=int(totals.get("documents", 0) or 0),
        pages=int(totals.get("pages", 0) or 0),
        active_s=float(totals.get("active_s", 0) or 0),
        samples=samples,
        completion_times=completion_times,
        peak_workers=peak,
    )
    session.close()
    return measurement


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def report(measurements: Sequence[Measurement], *,
           latency_ms: float = 0.0) -> str:
    if not measurements:
        return "nothing measured"
    baseline = next((m for m in measurements if m.workers == 1), measurements[0])
    lines: list[str] = []
    lines.append("")
    lines.append("=" * 96)
    lines.append("  MULTI-COMMUNITY BENCHMARK — measured, on this machine, "
                 "against the local fixture web")
    lines.append("=" * 96)
    if psutil is not None:
        lines.append(f"  {psutil.cpu_count(logical=True)} logical CPUs, "
                     f"{psutil.virtual_memory().total / (1024 ** 3):.1f} GB RAM")
    lines.append(f"  {measurements[0].communities} identical communities per run")
    if latency_ms:
        lines.append(f"  fixture latency {latency_ms:.0f} ms per request — a real "
                     "server's waiting, which is what parallel communities overlap")
    else:
        lines.append("  fixture latency 0 ms (loopback) — this is the FLOOR: all of "
                     "parallelism's overhead and none of its benefit")
    lines.append("")
    header = (f"  {'Workers':>7} {'Peak':>5} {'Wall':>8} {'Speed-up':>9} "
              f"{'Effic.':>7} {'Per hour':>9} {'Per w-min':>10} "
              f"{'CPU mean':>9} {'CPU peak':>9} {'RAM peak':>10} {'Spread':>8}")
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for measurement in measurements:
        speedup = baseline.wall_s / measurement.wall_s if measurement.wall_s else 0.0
        efficiency = speedup / measurement.workers if measurement.workers else 0.0
        lines.append(
            f"  {measurement.workers:>7} {measurement.peak_workers:>5} "
            f"{measurement.wall_s:>7.1f}s {speedup:>8.2f}x {efficiency:>6.0%} "
            f"{measurement.throughput_per_hour:>9.0f} "
            f"{measurement.per_worker_minute:>10.2f} "
            f"{measurement.mean_cpu:>8.0f}% {measurement.peak_cpu:>8.0f}% "
            f"{measurement.peak_memory_mb:>9.0f}M "
            f"{measurement.fairness_spread_s:>7.1f}s")
    lines.append("")

    points = [(m.workers, baseline.wall_s / m.wall_s if m.wall_s else 0.0)
              for m in measurements]
    contention, coherency, error = fit_scalability(points)
    lines.append("  FITTED SCALABILITY  speed-up(N) = N / (1 + σ(N-1) + κN(N-1))")
    lines.append(f"    σ (contention, cannot overlap) ... {contention:.4f}")
    lines.append(f"    κ (interference between workers)  {coherency:.6f}")
    lines.append(f"    residual sum of squares ......... {error:.4f}")

    from dcr.orchestrator.plan import best_worker_count, scalability

    peak_n = best_worker_count(32, contention=contention, coherency=coherency)
    lines.append(f"    predicted best worker count ..... {peak_n} "
                 f"({scalability(peak_n, contention=contention, coherency=coherency):.1f}x)")
    lines.append("")
    lines.append("  Paste into config/config.yaml under `orchestrator:` to make the")
    lines.append("  estimate the researcher sees reflect this machine:")
    lines.append(f"    scalability_contention: {contention:.4f}")
    lines.append(f"    scalability_coherency: {coherency:.6f}")
    lines.append("")

    best = max(measurements, key=lambda m: m.per_worker_minute)
    fastest = min(measurements, key=lambda m: m.wall_s)
    lines.append(f"  Shortest wall-clock: {fastest.workers} workers "
                 f"({fastest.wall_s:.1f}s)")
    lines.append(f"  Best per worker-minute: {best.workers} workers "
                 f"({best.per_worker_minute:.2f} completions/worker-minute)")
    if fastest.workers != best.workers:
        lines.append("  These differ: past the second number, extra workers shorten the")
        lines.append("  run by less than they cost. That is the point the governor")
        lines.append("  detects at run time and stops growing at.")
    lines.append("")
    if latency_ms:
        lines.append("  With latency injected, this is what the parallelism is FOR:")
        lines.append("  sixteen communities waiting on sixteen different servers, which")
        lines.append("  is the case the whole design exists to exploit.")
    else:
        lines.append("  A fixture on loopback has no network latency, so nothing here is")
        lines.append("  waiting on anything — and waiting is the ONLY thing parallel")
        lines.append("  communities overlap. These numbers are therefore the FLOOR: all")
        lines.append("  of parallelism's overhead and none of its benefit. Re-run with")
        lines.append("  --latency-ms 200 to see the case the design is actually for.")
    lines.append("  Either way, process startup, database contention, the scheduler and")
    lines.append("  the host broker are all the production ones.")
    lines.append("=" * 96)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--workers", default="1,4,8,16",
                        help="Comma-separated worker counts to measure.")
    parser.add_argument("--communities", type=int, default=16,
                        help="How many identical communities per run.")
    parser.add_argument("--latency-ms", type=float, default=0.0,
                        help="Milliseconds the fixture waits before answering. "
                             "Waiting on the network is the ONLY thing parallel "
                             "communities exist to overlap, so a loopback run at "
                             "0 ms measures the overhead of parallelism without "
                             "any of its benefit — that is the FLOOR. A real "
                             "server answers in 100-800 ms; measure both.")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs" / "benchmark_results.json")
    args = parser.parse_args(argv)

    from fixtures.server import FixtureServer
    from tools_hosts import ensure_hosts            # type: ignore

    if not ensure_hosts():
        return 1

    counts = [int(value) for value in args.workers.split(",") if value.strip()]
    server = FixtureServer()
    server.latency_s = max(0.0, args.latency_ms / 1000.0)
    server.start()
    if server.latency_s:
        print(f"  fixture answering after {args.latency_ms:.0f} ms, simulating a "
              "real server")
    measurements: list[Measurement] = []
    try:
        import tempfile

        for workers in counts:
            print(f"  measuring {workers} worker(s) over {args.communities} "
                  "communities...", flush=True)
            with tempfile.TemporaryDirectory() as directory:
                measurements.append(measure(
                    workers, args.communities, output_root=Path(directory),
                    server=server, root=ROOT))
    finally:
        server.stop()

    text = report(measurements, latency_ms=args.latency_ms)
    print(text)
    baseline = next((m for m in measurements if m.workers == 1), measurements[0])
    points = [(m.workers, baseline.wall_s / m.wall_s if m.wall_s else 0.0)
              for m in measurements]
    contention, coherency, error = fit_scalability(points)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "measurements": [m.as_dict() for m in measurements],
        "fitted": {"contention": contention, "coherency": coherency,
                   "residual": error},
        "fixture_latency_ms": args.latency_ms,
        "report": text,
    }, indent=2), encoding="utf-8")
    print(f"\n  Written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
