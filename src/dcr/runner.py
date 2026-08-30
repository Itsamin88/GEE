"""The ten-stage documentary protocol, as a resumable pipeline.

    Stage 0  build the source set
    Stage 1  rank and confirm it
    Stage 2  enumerate every page on every address
    Stage 3  open the documents, not just the pages
    Stage 4  archived versions
    Stage 5  academic literature
    Stage 6  grey literature
    Stage 7  other web sources
    Stage 8  local-language sweep
    Stage 9  cross-source reconciliation

Every stage records its own status (complete / partial / blocked / not_reached)
so ``stages_completed`` and ``crawl_truncated`` are generated from what actually
happened rather than asserted (decisions DCR-D009, DCR-D011).
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from .config import Settings
from .crawl.crawler import Crawler, SourceContext
from .crawl.frontier import Frontier, SourceBudget
from .crawl.normalize import normalize, registrable_domain
from .crawl.platform import (
    LOGIN_WALLED, default_source_class, detect_platform, is_website_like, profile_for,
)
from .db import Database, utcnow
from .discovery import academic as academic_mod
from .discovery import grey as grey_mod
from .discovery import search as search_mod
from .discovery import wayback as wayback_mod
from .discovery.sitemap import (
    candidate_sitemap_urls, maybe_gunzip, parse_feed, parse_sitemap,
)
from .evidence.conflict import ClaimView, ReviewQueue, resolve_field
from .evidence.extractors import TextMiner, haversine_km
from .evidence.independence import IndependenceResolver, editorial_signals_present
from .evidence.llm import SemanticExtractor, to_claims
from .evidence.model import ClaimItem, EvidenceItem, EvidenceRecorder
from .evidence.onset import DateCandidate, resolve_onset
from .evidence.practices import code_practices
from .ids import address_id as make_address_id
from .ids import source_id as make_source_id
from .language import guess_language, language_for_country
from .logging_setup import event, get_logger
from .net.browser import BrowserPool
from .net.fetcher import Fetcher
from . import profiling
from .budget import WorkBudget, budget_from_settings
from .yieldmeter import YieldMeter, meter_from_settings
from .control import (COMPLETED as CONTROL_COMPLETED, FAILED as CONTROL_FAILED,
                      CANCELLED as CONTROL_CANCELLED, RunCancelled, RunControl,
                      control_dir_for)
from .storage import CommunityStorage
from .supervisor import (NullSupervisor, RetrievalFinished, RunPaused,
                         Supervisor)

log = get_logger("run")

STAGE_NAMES = {
    0: "build the source set",
    1: "rank and confirm the source set",
    2: "enumerate every page on every address",
    3: "open the documents",
    4: "archived versions",
    5: "academic literature",
    6: "grey literature",
    7: "other web sources",
    8: "local-language sweep",
    9: "cross-source reconciliation",
}

MODE_STAGES = {
    "FULL": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    "SOURCE": [0, 1, 2, 3, 4, 7],
    "ACADEMIC": [0, 5, 6, 8, 9],
    "RESUME": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    "RETRY_FAILED": [0, 2, 3, 4, 9],
    "RECONCILE": [9],
    "AUDIT": [9],
    "EXPORT": [],
}


@dataclass
class CommunityInput:
    name: str
    latitude: float | None = None
    longitude: float | None = None
    urls: list[str] = field(default_factory=list)
    country: str | None = None
    mode: str = "SETTLEMENT"
    coder_id: str = ""
    fixture: bool = False
    #: Domains to walk in full rather than sample. The community's own site,
    #: any former domain, its blog: the places where the gallery, the newsletter
    #: archive and the buried report all belong to the community itself, and
    #: where sampling loses precisely the material a documentary study needs.
    deep_crawl_urls: list[str] = field(default_factory=list)
    #: Exact query strings for the exhaustive academic harvest. Supplied by the
    #: master file so the harvest is reproducible and auditable rather than
    #: re-derived differently on every run.
    academic_search_terms: list[str] = field(default_factory=list)
    crawl_policy: str | None = None
    #: The site_id the run orchestrator has already allocated for this
    #: community. With one database per community — which is what makes a
    #: failure in C007 unable to touch C001 — each database would otherwise
    #: number its single community IC001, and 212 workbooks would all claim
    #: to be site IC001 (brief §8, §53).
    assigned_id: str | None = None


@dataclass
class StageStatus:
    number: int
    name: str
    status: str = "not_reached"
    detail: str = ""
    started: str | None = None
    finished: str | None = None


@dataclass
class RunOutcome:
    run_id: str
    community_id: str
    stages: dict[int, StageStatus] = field(default_factory=dict)
    truncated: bool = False
    truncation_reasons: list[str] = field(default_factory=list)
    completion_status: str = "FAILED_TECHNICALLY"
    stats: dict[str, Any] = field(default_factory=dict)
    review_items: int = 0
    #: How the run ended: COMPLETED, PAUSED_MANUAL, PAUSED_NETWORK, CANCELLED
    #: or FAILED. A paused run is unfinished, never complete (brief §13).
    final_state: str = "COMPLETED"
    pause_reason: str = ""
    pauses_manual: int = 0
    pauses_network: int = 0
    offline_s: float = 0.0
    paused_manual_s: float = 0.0
    queue: dict[str, int] = field(default_factory=dict)
    estimate: dict[str, Any] = field(default_factory=dict)
    #: True when the run stopped because the active budget was spent. The
    #: result is a usable record with its limits stated, not a failure.
    budget_exhausted: bool = False
    budget: dict[str, Any] = field(default_factory=dict)
    profile: dict[str, Any] = field(default_factory=dict)
    #: What the crawl found, per unit of active time, and the shape of the
    #: curve behind the stopping decision (brief §25, §93).
    yield_summary: dict[str, Any] = field(default_factory=dict)
    #: exhausted | ceiling | requested — why retrieval ended, if it did.
    retrieval_stop_cause: str = ""
    #: Archive tiers deliberately not retrieved, and why (brief §61).
    archive_truncated: list[str] = field(default_factory=list)

    @property
    def paused(self) -> bool:
        return self.final_state in ("PAUSED_MANUAL", "PAUSED_NETWORK")


class CommunityRunner:
    """Runs one community through the protocol, resumably."""

    def __init__(self, settings: Settings, db: Database, *, run_mode: str = "FULL",
                 target: str | None = None, monitor: Any = None,
                 on_status: Any = None, estimate: Any = None,
                 on_progress: Any = None, host_broker: Any = None):
        self.settings = settings
        #: Supplied by the application; a test may pass a simulated one.
        self.monitor = monitor
        self.on_status = on_status
        #: The estimate made before the crawl, carried through so the
        #: completion report can compare it with what actually happened.
        self.estimate = estimate
        self.control: Any = None
        self.supervisor: Any = NullSupervisor()
        self.final_state = CONTROL_COMPLETED
        self.pause_reason = ""
        self.budget: WorkBudget | None = None
        #: What the crawl is finding, measured. The stopping rule (brief §25).
        self.meter: YieldMeter = meter_from_settings(self.settings)
        self.budget_exhausted = False
        #: exhausted | ceiling | requested — why retrieval ended, if it did.
        self.retrieval_stop_cause = ""
        #: Which stage and source the work in flight belongs to, so yield can
        #: be charged to the right accounts without threading them everywhere.
        self._current_stage: int | None = None
        self._current_source: str = ""
        self._last_charged_active_s = 0.0
        #: Archive tiers deliberately not retrieved, and why.
        self.archive_truncated: list[str] = []
        #: What grouping translations and re-issues saved (brief §20).
        self.document_families: dict[str, int] = {}
        self.db = db
        self.run_mode = run_mode.upper()
        self.target = target
        self.review = ReviewQueue()
        self.independence = IndependenceResolver({
            **dict(settings.get("independence", default={}) or {}),
            "promotion_max_jaccard": _decision_parameter(
                settings.decisions, "DCR-D010", "promotion_max_jaccard", 0.35
            ),
        })
        self.miner = TextMiner(settings.lexicon, settings.schema)
        self.stages: dict[int, StageStatus] = {
            n: StageStatus(number=n, name=name) for n, name in STAGE_NAMES.items()
        }
        self.truncation_reasons: list[str] = []
        self.community_domains: set[str] = set()
        self.names: set[str] = set()
        self.founders: set[str] = set()
        self.entities: set[str] = set()
        self.networks: set[str] = set()
        self.languages: set[str] = set()
        self.date_candidates: list[DateCandidate] = []
        self.practice_hits: list[Any] = []
        self.published_coordinates: list[tuple[float, float, str]] = []
        self.certifiers: set[str] = set()
        self._search_counter = 0
        #: Archive URLs the index listed, versus the ones actually retrieved.
        self.archive_discovered = 0
        self.archive_fetched = 0
        #: Where the crawl reports stage changes to, when it is one worker of
        #: many. None for a single run, and nothing below depends on it.
        self.on_progress = on_progress
        #: Run-wide per-host politeness, shared with the other communities.
        self.host_broker = host_broker

    # =====================================================================
    # entry point
    # =====================================================================
    def _scope_for(self, url: str) -> str:
        """`exhaustive` for the community's own domains, `targeted` otherwise.

        The master file decides this, not a guess from the platform type: a
        community may hold three domains and a directory listing may sit on the
        same host as something unrelated. `deep_crawl_urls` is the researcher's
        statement of which sites are the community's own.
        """
        domain = registrable_domain(url)
        return "exhaustive" if domain and domain in getattr(
            self, "deep_domains", set()) else "targeted"

    async def run(self, community: CommunityInput) -> RunOutcome:
        record = self._ensure_community(community)
        self.community_id = record["community_id"]
        self.community = community
        # Which registrable domains the master file marked for a full walk.
        # Matching on the domain rather than the exact URL is deliberate: the
        # master file names the site root, but discovery, the sitemap and the
        # archive all queue deeper pages on the same host, and every one of them
        # belongs to the same exhaustive job.
        self.deep_domains = {
            registrable_domain(url) for url in (community.deep_crawl_urls or [])
            if registrable_domain(url)
        }
        self.storage = CommunityStorage.create(
            self.settings.output_root, self.community_id, community.name
        )
        self.recorder = EvidenceRecorder(self.db, self.community_id, self.settings.schema,
                                         meter=self.meter, scopes=self._yield_scopes)
        self.names = {community.name}
        self.languages = set()
        if community.country:
            self.languages.add(language_for_country(community.country))

        run_id = self._start_run(community)
        self.run_id = run_id
        profiling.reset()
        stages = MODE_STAGES.get(self.run_mode, MODE_STAGES["FULL"])

        # Run control first: from here on, every stop has a recorded reason and
        # a checkpoint behind it.
        # This community's own control directory, so PAUSE C007 reaches C007
        # and nothing else. The run-level directory is watched as well, which is
        # what makes PAUSE ALL one file rather than two hundred (brief §34, §35).
        self.control = RunControl(
            self.db, run_id=run_id, community_id=self.community_id,
            control_dir=control_dir_for(self.storage.root),
            shared_control_dirs=[control_dir_for(self.settings.output_root)],
            poll_interval_s=float(self.settings.get(
                "run_control", "poll_interval_s", default=1.0) or 1.0),
        )
        if bool(self.settings.get("budget", "enabled", default=True)):
            carried = WorkBudget.carried_for(self.db, self.community_id)
            self.budget = budget_from_settings(self.settings, carried_active_s=carried)
            if carried > 0:
                event(log, "BUDGET",
                      f"{carried / 60:.1f} min of active time was already spent on this "
                      "community; this session continues the same account of it")
            if self.budget.bounded:
                event(log, "BUDGET",
                      f"a safety ceiling of {self.budget.ceiling_s / 60:.0f} min of active "
                      "work is set in configuration; retrieval will be truncated there "
                      "if the community is still yielding")
        # Anything credited in an earlier session must not be credited again:
        # otherwise a resumed crawl re-counts every document it already has and
        # concludes that an exhausted source has come back to life.
        self.meter.restore(self._stored_yield_state())
        self.supervisor = Supervisor(
            self.control, self.monitor,
            config=dict(self.settings.get("run_control", default={}) or {}),
            on_status=self.on_status,
            on_resume=self._after_resume,
            budget=self.budget,
            meter=self.meter,
            on_gate=self._charge_active_time,
        )
        self.supervisor.bind_scopes(self._yield_scopes)

        fetcher = Fetcher(
            user_agent=self.settings.user_agent,
            config=self.settings.app,
            error_sink=self._error_sink,
            supervisor=self.supervisor,
            host_broker=self.host_broker,
        )
        browser_cfg = dict(self.settings.get("browser", default={}) or {})
        browser = BrowserPool(
            enabled=str(browser_cfg.get("enabled", "auto")) != "never",
            pool_size=int(browser_cfg.get("pool_size", 2)),
            timeout_s=float(browser_cfg.get("timeout_s", 45)),
            user_agent=self.settings.user_agent,
        )
        await browser.start()

        self.frontier = Frontier(self.db, self.community_id)
        reclaimed = self.frontier.reclaim_in_flight()
        if reclaimed:
            event(log, "RESUME", f"{reclaimed} URLs were mid-flight and have been re-queued")
        if self.run_mode == "RETRY_FAILED":
            requeued = self.frontier.requeue_failed()
            event(log, "RESUME", f"{requeued} previously failed URLs re-queued")

        self.crawler = Crawler(
            db=self.db, storage=self.storage, fetcher=fetcher, frontier=self.frontier,
            community_id=self.community_id, config=self.settings.app,
            lexicon=self.settings.lexicon, browser=browser,
            on_page=self._on_page, on_document=self._on_document,
            supervisor=self.supervisor,
        )
        self.crawler._platform_patterns = self.settings.sources.get("platform_patterns", {})
        self.crawler._archive_template = self.settings.sources.get("archive", {}).get(
            "snapshot_url_template")
        self.fetcher = fetcher
        self.browser = browser
        self.llm = self._build_llm()

        self.control.checkpoint(
            tasks_total=self.frontier.pending_count(),
            task_detail=f"{self.run_mode} run starting",
        )
        skip = self._stages_already_complete() if self.run_mode == "RESUME" else set()
        try:
            for number in stages:
                if number in skip:
                    stage = self.stages[number]
                    stage.status = "complete"
                    stage.detail = ("carried forward: this stage completed in an earlier "
                                    "run and was not repeated")
                    event(log, f"Stage {number}/9",
                          f"{STAGE_NAMES[number].capitalize()} — already complete, skipped")
                    continue
                await self._run_stage(number)
        except RetrievalFinished as finished:
            # Not a failure. Everything gathered is committed, and finalisation
            # happens next with the reserve held back exactly for it.
            #
            # Whether it is a TRUNCATION depends on why retrieval ended. A run
            # the yield governor stopped found everything there was to find and
            # is complete; only a ceiling or a researcher's request leaves work
            # undone (brief §61, §92).
            self.budget_exhausted = True
            self.retrieval_stop_cause = finished.cause
            self.final_state = CONTROL_COMPLETED
            self.pause_reason = finished.reason
            if finished.truncated:
                self._mark_truncated(
                    "retrieval ended before the protocol finished: "
                    f"{finished.reason}")
            else:
                event(log, "YIELD",
                      "the protocol finished on the evidence rather than on a clock: "
                      f"{finished.reason}")
            event(log, "BUDGET", finished.reason)
        except RunPaused as paused:
            # Not a failure and not a completion: the run is unfinished on
            # purpose, and everything retrieved so far is committed.
            self.final_state = paused.state
            self.pause_reason = paused.reason
            self._mark_truncated(
                f"the run was paused before the protocol finished ({paused.state}): "
                f"{paused.reason}")
        except RunCancelled as cancelled:
            self.final_state = CONTROL_CANCELLED
            self.pause_reason = str(cancelled)
            self._mark_truncated(f"the run was cancelled by the researcher: {cancelled}")
        except asyncio.CancelledError:
            self.final_state = CONTROL_FAILED
            self.pause_reason = "the process was interrupted"
            self._mark_truncated("the run was interrupted before the protocol finished")
            self.control.finish(CONTROL_FAILED, self.pause_reason)
            raise
        except Exception as exc:  # a bug must still produce a recorded run
            log.error("run failed: %s", exc, exc_info=True)
            self.final_state = CONTROL_FAILED
            self.pause_reason = str(exc)
            self._mark_truncated(f"the run stopped on an unexpected error: {exc}")
        finally:
            await fetcher.aclose()
            await browser.close()

        outcome = self._finish_run(run_id)
        return outcome

    def _after_resume(self, kind: str) -> None:
        """Undo the damage an outage did to the crawler's bookkeeping.

        Hosts that "failed" while the machine had no network were never really
        tested, so their circuits must not outlive the outage, and anything
        left mid-flight goes back in the queue (brief §16.6, §25).
        """
        if kind == "network" and self.fetcher is not None:
            cleared = self.fetcher.reset_host_failures()
            if cleared:
                event(log, "RESUME",
                      f"{cleared} host(s) marked unreachable during the outage have been "
                      "given another attempt")
        if self.frontier is not None:
            reclaimed = self.frontier.reclaim_in_flight()
            if reclaimed:
                event(log, "RESUME", f"{reclaimed} URLs were mid-flight and are re-queued")

    def _stages_already_complete(self) -> set[int]:
        """Stages a previous run finished, so a RESUME does not repeat them.

        Stage 9 is never carried forward: reconciliation has to see everything
        the resumed run added, or the workbook would be built from a stale view.
        """
        rows = self.db.query(
            "SELECT s.stage_no FROM run_stages s JOIN runs r ON r.run_id = s.run_id "
            "WHERE r.community_id = ? AND s.status = 'complete' AND s.run_id != ?",
            (self.community_id, self.run_id))
        return {int(r["stage_no"]) for r in rows} - {9}

    # =====================================================================
    # stage dispatch
    # =====================================================================
    async def _run_stage(self, number: int) -> None:
        stage = self.stages[number]
        # A stage boundary is the coarsest safe boundary there is: nothing is
        # part-written, so it is the cheapest place to stop.
        await self.supervisor.gate(
            stage_no=number, stage_name=STAGE_NAMES[number],
            task_detail=f"about to begin stage {number}",
            tasks_total=self._task_total(),
        )
        self._charge_active_time()
        self._current_stage = number
        self._current_source = ""
        if self.budget is not None:
            self.budget.begin_stage(number)
        stage.started = utcnow()
        stage.status = "running"
        self._persist_stage(stage)
        event(log, f"Stage {number}/9", STAGE_NAMES[number].capitalize())
        self._report_progress("stage", stage_no=number,
                              stage_name=STAGE_NAMES[number],
                              progress=number / 9.0)
        handler = getattr(self, f"_stage_{number}")
        try:
            await handler()
        except (RunPaused, RunCancelled):
            # The stage did not fail; it was stopped part-way. Recording it as
            # `partial` is what stops the report claiming this stage found
            # nothing, when in truth it was never allowed to finish.
            stage.status = "partial" if stage.status in ("running", "not_reached") else stage.status
            stage.detail = (stage.detail or "") + (
                "; " if stage.detail else "") + "stopped part-way by a pause or cancel"
            stage.finished = utcnow()
            self._persist_stage(stage)
            raise
        except Exception as exc:
            stage.status = "failed"
            stage.detail = f"{type(exc).__name__}: {exc}"
            log.error("stage %d failed: %s", number, exc, exc_info=True)
            self._mark_truncated(f"stage {number} ({STAGE_NAMES[number]}) failed: {exc}")
        self._charge_active_time()
        self._current_stage = None
        self._current_source = ""
        if self.budget is not None:
            self.budget.end_stage()
            self.budget.persist(self.db, self.run_id)
            self._persist_yield()
            if stage.status == "running" and self.budget.stage_over_budget(number):
                # Only reachable when an operator opted into a safety ceiling.
                stage.status = "partial"
                stage.detail = (stage.detail or "") + (
                    "; " if stage.detail else "") + (
                    "stopped at the safety ceiling set in configuration")
                self._mark_truncated(
                    f"stage {number} ({STAGE_NAMES[number]}) reached the configured "
                    "safety ceiling and did not finish")
        if stage.status == "running":
            stage.status = "complete"
        stage.finished = utcnow()
        self._persist_stage(stage)
        self.control.checkpoint(
            stage_no=number, stage_name=STAGE_NAMES[number],
            task_detail=f"stage {number} finished as {stage.status}",
            tasks_total=self._task_total(), record_event=True,
        )

    def _persist_stage(self, stage: StageStatus) -> None:
        self.db.upsert(
            "run_stages",
            {"run_id": self.run_id, "stage_no": stage.number,
             "stage_name": STAGE_NAMES[stage.number], "status": stage.status,
             "detail": (stage.detail or "")[:2000],
             "started_utc": stage.started, "finished_utc": stage.finished},
            ["run_id", "stage_no"],
        )

    # -- measuring yield ---------------------------------------------------
    def _report_progress(self, kind: str, **kwargs: Any) -> None:
        """Tell the run orchestrator what this community is doing.

        Best-effort by design: a crawl must never stop because a dashboard is
        slow or a parent process has gone away (brief §51).
        """
        if self.on_progress is None:
            return
        try:
            self.on_progress(kind, **kwargs)
        except Exception:
            pass

    def _yield_scopes(self) -> tuple[str, ...]:
        """Which accounts the work happening right now belongs to.

        Nested views of one crawl, not competing budgets: a document opened
        while stage 3 works on source IC001-S002 is charged to the run, to the
        stage and to the source, and each can be judged on its own.
        """
        scopes = ["run"]
        if self._current_stage is not None:
            scopes.append(f"stage:{self._current_stage}")
        if self._current_source:
            scopes.append(f"source:{self._current_source}")
        return tuple(scopes)

    def _archive_tier_verdict(self, scope: str, tier: int, domain: str) -> Any:
        """Is the archive still worth another tier of retrieval?

        Tier 1 is never asked: a deleted document is unrecoverable anywhere
        else, so it is fetched whatever the yield has been. Tiers 2 and 3 are
        judged on what tier 1 actually produced for this domain, which is the
        marginal-yield rule the brief asks for in §15 — "only continue deeper
        when the marginal research yield justifies the cost".
        """
        from .yieldmeter import Verdict

        state = self.meter.scope(scope)
        if state.attempts == 0:
            # Nothing has been tried here yet, so there is no evidence either
            # way; the tier goes ahead and will be judged next time.
            return Verdict(True, "the archive has not been sampled yet", warming_up=True)
        floor = float(self.settings.get(
            "archive", "tier_yield_floor_per_min", default=2.5) or 2.5)
        # Tier 3 is held to a higher standard than tier 2: by then the good
        # material has already been taken.
        if tier >= 3:
            floor *= 2.0
        return self.meter.verdict(scope, absolute_floor=floor,
                                  warmup_s=20.0, warmup_attempts=5)

    def _charge_active_time(self) -> None:
        """Give the yield meter the seconds since it was last told.

        Called at every safe boundary. The clock excludes pause and outage time
        already, so what arrives here is genuinely active work (brief §32).
        """
        if self.budget is None:
            return
        now = self.budget.active_s
        delta = now - self._last_charged_active_s
        if delta <= 0:
            return
        self._last_charged_active_s = now
        self.meter.spend(delta, self._yield_scopes())

    def _stored_yield_state(self) -> dict[str, Any] | None:
        """The yield account this community carried out of an earlier session."""
        try:
            row = self.db.query_one(
                "SELECT yield_state FROM run_control WHERE community_id = ? "
                "AND yield_state IS NOT NULL ORDER BY updated_utc DESC LIMIT 1",
                (self.community_id,))
        except Exception:
            return None
        if not row or not row["yield_state"]:
            return None
        try:
            return json.loads(row["yield_state"])
        except (TypeError, ValueError):
            return None

    def _persist_yield(self) -> None:
        try:
            self.db.update("run_control",
                           {"yield_state": json.dumps(self.meter.state_for_resume()),
                            "yield_units": round(self.meter.scope("run").units, 2),
                            "updated_utc": utcnow()},
                           {"run_id": self.run_id})
        except Exception as exc:
            log.debug("could not persist the yield account: %s", exc)

    def _task_total(self) -> int:
        """Tasks done plus tasks still queued — the denominator the user sees."""
        try:
            done = int(self.db.scalar(
                "SELECT COUNT(*) FROM frontier WHERE community_id = ? AND status = 'done'",
                (self.community_id,)) or 0)
            return done + self.frontier.pending_count()
        except Exception:
            return 0

    # ---------------------------------------------------------------------
    # Stage 0 — build the source set
    # ---------------------------------------------------------------------
    async def _stage_0(self) -> None:
        stage = self.stages[0]
        supplied = [u for u in (normalize(u) for u in self.community.urls) if u]
        existing = {row["url"] for row in self.db.query(
            "SELECT url FROM sources WHERE community_id = ?", (self.community_id,))}

        for url in supplied:
            if url not in existing and not self._existing_source_for(url):
                self._create_source(url, supplied_or_discovered="supplied",
                                    discovery_method="researcher")
        for url in supplied:
            self.community_domains.add(registrable_domain(url))

        if not supplied and not existing:
            event(log, "DISCOVER", "no addresses supplied — searching for the community")
            await self._discover_from_nothing()

        await self._discover_additional_addresses()

        sources = self._sources()
        if not sources:
            stage.status = "failed"
            stage.detail = "no addresses could be established for this community"
            self._mark_truncated("no source address could be established")
            self.review.add(
                "identity", "No address found",
                "Neither a supplied address nor a discovered one could be established. "
                "Supply at least one URL, or check the community name spelling.",
                severity="blocking",
            )
            return

        self._assign_independence_groups()
        supplied_count = sum(1 for s in sources if s["supplied_or_discovered"] == "supplied")
        stage.status = "complete"
        stage.detail = (f"{supplied_count} supplied, {len(sources) - supplied_count} discovered, "
                        f"{self.independence.group_count()} independence groups")
        event(log, "SOURCES",
              f"{len(sources)} addresses ({supplied_count} supplied, "
              f"{len(sources) - supplied_count} discovered) in "
              f"{self.independence.group_count()} independence groups")

    async def _discover_from_nothing(self) -> None:
        """Stage 1's fallback: find the community's own addresses by search."""
        slug = re.sub(r"[^a-z0-9]+", "", self.community.name.lower())[:40]
        country_code = _country_code(self.community.country)
        queries = [f'"{self.community.name}"']
        if self.community.country:
            queries.append(f'"{self.community.name}" {self.community.country}')
        for term in ("ecovillage", "intentional community", "permaculture"):
            queries.append(f'"{self.community.name}" {term}')

        for query in queries[:6]:
            for hit in await self._search_web(query, stage=0, purpose="source discovery"):
                self._consider_candidate(hit.url, "search", query)
        for guess in search_mod.domain_guesses(slug, country_code)[:4]:
            result = await self.fetcher.fetch(guess, kind="page", community_id=self.community_id,
                                              stage=0)
            if result.ok and result.text and self._looks_like_community(result.text):
                self._create_source(guess, supplied_or_discovered="discovered",
                                    discovery_method="domain_guess", discovery_query=guess)

    # Words that appear in half the community names in this population and so
    # identify nothing on their own.
    _GENERIC_NAME_WORDS = {
        "ecovillage", "eco", "village", "ecolieu", "ecodorp", "ecoaldea", "ecoaldeia",
        "community", "communaute", "gemeenschap", "farm", "ferme", "boerderij", "quinta",
        "project", "projet", "centre", "center", "the", "les", "des", "van", "de", "du",
    }

    def _looks_like_community(self, text: str) -> bool:
        """Does this page plausibly belong to THIS community?

        A former domain rarely repeats the full official name — 'Pourgues' will
        appear where 'EcoVillage de Pourgues' does not — so the test is the
        DISTINCTIVE part of the name, not every word of it.
        """
        lowered = text.lower()
        parts = [p for p in re.split(r"\W+", self.community.name.lower()) if len(p) > 3]
        distinctive = [p for p in parts if p not in self._GENERIC_NAME_WORDS]
        if distinctive:
            return any(part in lowered for part in distinctive)
        return bool(parts) and all(part in lowered for part in parts[:2])

    async def _discover_additional_addresses(self) -> None:
        """Register 0.2 — the addresses nobody supplied are usually the valuable ones."""
        templates = self.settings.sources.get("discovery_queries", {})
        name = self.community.name
        queries: list[tuple[str, str]] = []
        for group in ("platform_accounts", "former_domain", "directories"):
            for template in templates.get(group, []):
                query = (template.replace("{name}", name)
                         .replace("{country}", self.community.country or "")).strip()
                if "{" not in query:
                    queries.append((query, group))
        for entity in list(self.entities)[:3]:
            queries.append((f'"{entity}"', "entity"))

        for query, group in queries[:18]:
            for hit in await self._search_web(query, stage=0, purpose=f"source discovery ({group})"):
                self._consider_candidate(hit.url, "search", query)

        # Anything the crawl found linked off-site is a candidate address.
        for domain, entry in list(getattr(self.crawler, "external_candidates", {}).items()):
            trusted = self._footer_link_is_own_account(entry)
            for url in entry["urls"][:2]:
                self._consider_candidate(url, "link", entry.get("first_seen_on", ""),
                                         from_confirmed_source=trusted)

    def _consider_candidate(self, url: str, method: str, query: str,
                            *, from_confirmed_source: bool = False) -> str | None:
        """Adopt a discovered address only if it plausibly belongs to THIS community.

        A wrong attribution here contaminates every field that follows
        (register Stage 1), so a platform profile is not enough on its own: the
        community's name must appear in the host or the path, or the link must
        come from a page already confirmed as this community's.
        """
        normalized = normalize(url)
        if not normalized:
            return None
        domain = registrable_domain(normalized)
        platform = detect_platform(normalized, self.settings.sources.get("platform_patterns", {}))

        name_slug = re.sub(r"[^a-z0-9]", "", self.community.name.lower())
        domain_slug = re.sub(r"[^a-z0-9]", "", domain)
        path_slug = re.sub(r"[^a-z0-9]", "", urlsplit(normalized).path.lower())
        name_parts = [
            part for part in re.split(r"\W+", self.community.name.lower())
            if len(part) > 3 and part not in self._GENERIC_NAME_WORDS
        ]
        if not name_parts:
            name_parts = [part for part in re.split(r"\W+", self.community.name.lower())
                          if len(part) > 3]

        on_community_domain = domain in self.community_domains
        name_in_host = bool(domain_slug) and (
            domain_slug in name_slug or any(part in domain_slug for part in name_parts)
        )
        name_in_path = any(part in path_slug for part in name_parts)

        if not (on_community_domain or name_in_host or name_in_path or from_confirmed_source):
            self._log_discovery(
                0, method, normalized, "out_of_scope",
                f"neither the host nor the path carries any distinctive part of "
                f"{self.community.name!r}, and the link was not found on a confirmed page",
            )
            return None

        existing = self._existing_source_for(normalized)
        if existing:
            # The same address reached twice — http and https, or a link and a
            # search hit — is one address. Counting it twice would inflate
            # source_set_discovered and could inflate the independence count.
            self._log_discovery(0, method, normalized, "duplicate", existing)
            return None

        # A deeper page of a domain already established as a source is a PAGE of
        # that source, not a second address.
        owner = self.db.query_one(
            "SELECT source_id FROM sources WHERE community_id=? AND registrable_domain=? "
            "ORDER BY source_id LIMIT 1", (self.community_id, domain))
        if owner:
            self.frontier.add(normalized, source_id=owner["source_id"], depth=1, stage=7,
                              discovery_method=method)
            self._log_discovery(0, method, normalized, "duplicate",
                                f"a page of {owner['source_id']}, queued rather than "
                                "registered as a second address")
            return None

        source_id = self._create_source(normalized, supplied_or_discovered="discovered",
                                        discovery_method=method, discovery_query=query)
        reason = ("on a community domain" if on_community_domain else
                  "the host carries the community name" if name_in_host else
                  "the URL path carries the community name" if name_in_path else
                  "linked from a page confirmed as this community's")
        self._log_discovery(0, method, normalized, "new_source", f"{source_id}: {reason}")
        return source_id

    # Footers carry the community's own dormant accounts — and also its
    # funders, its web designer and its partner organisations. Only the first
    # kind is adopted without a name match.
    _OWN_ACCOUNT_PLATFORMS = {"Facebook", "Instagram", "YouTube", "Vimeo", "LinkedIn",
                            "blog platform", "directory listing", "crowdfunding",
                            "booking or hosting", "secondary or former website"}

    def _footer_link_is_own_account(self, entry: Mapping[str, Any]) -> bool:
        if not ({"footer", "nav"} & set(entry.get("methods", set()))):
            return False
        platforms = set(entry.get("platforms", set()))
        return bool(platforms & self._OWN_ACCOUNT_PLATFORMS)

    def _create_source(self, url: str, *, supplied_or_discovered: str,
                       discovery_method: str, discovery_query: str = "") -> str:
        count = int(self.db.scalar(
            "SELECT COUNT(*) FROM sources WHERE community_id = ?", (self.community_id,)) or 0)
        source_id = make_source_id(self.community_id, count + 1)
        address = make_address_id(self.community_id, count + 1)
        platform = detect_platform(url, self.settings.sources.get("platform_patterns", {}))
        profile = profile_for(url, platform, self.settings.sources.get("platform_endpoints", {}))
        self.db.insert(
            "sources",
            {
                "source_id": source_id,
                "community_id": self.community_id,
                "address_id": address,
                "url": url,
                "domain": (urlsplit(url).hostname or ""),
                "registrable_domain": registrable_domain(url),
                "platform_type": platform,
                "source_class": default_source_class(url, platform),
                "supplied_or_discovered": supplied_or_discovered,
                "discovery_method": discovery_method,
                "discovery_query": discovery_query[:500],
                "access_status": "not_attempted",
                "crawl_status": "not attempted",
                "retrieval_priority": profile.retrieval_priority,
                "first_discovered_utc": utcnow(),
                "notes": profile.notes,
            },
            replace=True,
        )
        if supplied_or_discovered == "supplied":
            self.community_domains.add(registrable_domain(url))
        event(log, "SOURCE", f"{source_id} {platform}: {url} ({supplied_or_discovered})")
        return source_id

    def _assign_independence_groups(self) -> None:
        for row in self._sources():
            if row["independence_group"]:
                continue
            text = self._source_text_sample(row["source_id"])
            profile = self.independence.profile(row["source_id"], row["source_id"], text) if text else None
            assignment = self.independence.assign(
                source_id=row["source_id"],
                platform_type=row["platform_type"] or "other",
                source_class=row["source_class"] or "S4",
                registrable=row["registrable_domain"] or "",
                profile=profile,
                community_domains=self.community_domains,
                text=text,
                editorial_signals=editorial_signals_present(text),
            )
            self.db.update("sources",
                           {"independence_group": assignment.group,
                            "independence_reason": assignment.reason[:600]},
                           {"source_id": row["source_id"]})

    def _reassess_independence(self) -> None:
        """Re-check the groups now that the pages have actually been read.

        Stage 0 assigns groups before anything is crawled, so it can only use
        the platform and the domain. By stage 9 the text exists, and that is what
        the register's test actually turns on: could this source be wrong in the
        same way as that one, for the same reason?
        """
        for row in self._sources():
            text = self._source_text_sample(row["source_id"])
            if len(text) < self.independence.min_chars:
                continue
            profile = self.independence.profile(row["source_id"], row["source_id"], text)
            previous = row["independence_group"]
            assignment = self.independence.assign(
                source_id=row["source_id"],
                platform_type=row["platform_type"] or "other",
                source_class=row["source_class"] or "S4",
                registrable=row["registrable_domain"] or "",
                profile=profile,
                community_domains=self.community_domains,
                text=text,
                editorial_signals=editorial_signals_present(text),
            )
            if assignment.group == previous:
                continue
            self.db.update(
                "sources",
                {"independence_group": assignment.group,
                 "independence_reason": f"{assignment.reason} (reassessed after crawling; "
                                        f"was {previous})"[:600]},
                {"source_id": row["source_id"]},
            )
            if assignment.similarity:
                self.db.insert(
                    "source_relations",
                    {"source_a": row["source_id"], "source_b": assignment.related_to or "",
                     "relation": "copy_of", "similarity": assignment.similarity,
                     "evidence": assignment.reason[:600], "created_utc": utcnow()},
                    replace=True,
                )
            event(log, "INDEPENDENCE",
                  f"{row['source_id']} moved from {previous} to {assignment.group}: "
                  f"{assignment.reason[:80]}")

    def _source_text_sample(self, source_id: str) -> str:
        rows = self.db.query(
            "SELECT text_path FROM pages WHERE source_id = ? AND text_chars > 200 "
            "ORDER BY text_chars DESC LIMIT 3", (source_id,))
        pieces: list[str] = []
        for row in rows:
            path = self.storage.root / str(row["text_path"])
            if path.exists():
                pieces.append(path.read_text(encoding="utf-8", errors="replace")[:20000])
        return "\n".join(pieces)

    # ---------------------------------------------------------------------
    # Stage 1 — rank and confirm
    # ---------------------------------------------------------------------
    async def _stage_1(self) -> None:
        stage = self.stages[1]
        sources = self._sources()
        confirmed = 0
        for row in sources:
            if self.target and row["address_id"] != self.target and row["source_id"] != self.target:
                continue
            result = await self.fetcher.fetch(
                row["url"], kind="page", community_id=self.community_id,
                source_id=row["source_id"], stage=1,
            )
            values: dict[str, Any] = {
                "http_status": result.status,
                "access_status": result.access_status,
                "last_crawled_utc": utcnow(),
            }
            if result.ok and result.text:
                belongs = self._looks_like_community(result.text) or \
                          registrable_domain(row["url"]) in self.community_domains
                values["belongs_confirmed"] = int(belongs)
                values["belongs_evidence"] = (
                    "the page carries the community name"
                    if self._looks_like_community(result.text)
                    else "supplied by the researcher as this community's address"
                )
                values["language"] = guess_language(result.text, url=row["url"],
                                                    country=self.community.country)
                self.languages.add(values["language"])
                if not belongs:
                    self.review.add(
                        "identity", f"Uncertain ownership: {row['source_id']}",
                        f"{row['url']} does not carry the community name. It may belong to a "
                        "similarly named project elsewhere; a wrong attribution here "
                        "contaminates every field that follows.",
                        severity="blocking", related_ids=row["source_id"],
                    )
                else:
                    confirmed += 1
            else:
                values["crawl_status"] = (
                    "blocked" if result.access_status in ("blocked", "login_required")
                    else "dead link" if result.access_status == "dead" else "not attempted"
                )
                if row["platform_type"] in LOGIN_WALLED:
                    event(log, "BLOCKED",
                          f"{row['platform_type']} ({row['source_id']}) — "
                          f"{result.error_detail or 'refused automated reading'}")
            self.db.update("sources", values, {"source_id": row["source_id"]})

        stage.status = "complete" if confirmed else "partial"
        stage.detail = f"{confirmed} of {len(sources)} addresses confirmed as this community's"
        if not confirmed:
            self._mark_truncated("no address could be confirmed as belonging to this community")

    # ---------------------------------------------------------------------
    # Stage 2 — enumerate every page on every address
    # ---------------------------------------------------------------------
    async def _stage_2(self) -> None:
        stage = self.stages[2]
        crawl_cfg = dict(self.settings.get("crawl", default={}) or {})
        sources = self._sources()
        targets = [s for s in sources
                   if not self.target or s["address_id"] == self.target or s["source_id"] == self.target]
        if not targets:
            stage.status = "not_reached"
            stage.detail = f"no address matches the requested target {self.target!r}"
            return

        seeded = 0
        for row in targets:
            if row["access_status"] in ("blocked", "dead", "login_required"):
                continue
            scope = self._scope_for(row["url"])
            scope_cfg = (crawl_cfg.get("scopes") or {}).get(scope) or {}
            context = SourceContext(
                source_id=row["source_id"],
                url=row["url"],
                platform_type=row["platform_type"] or "other",
                source_class=row["source_class"] or "S4",
                retrieval_priority=row["retrieval_priority"] or "B",
                independence_group=row["independence_group"],
                login_walled=(row["platform_type"] in LOGIN_WALLED),
                budget=SourceBudget(
                    row["source_id"],
                    base=int(scope_cfg.get("base_pages_per_source",
                                           crawl_cfg.get("base_pages_per_source", 40))),
                    maximum=int(scope_cfg.get("max_pages_per_source",
                                              crawl_cfg.get("max_pages_per_source", 400))),
                    yield_window=int(crawl_cfg.get("yield_window", 10)),
                    yield_threshold=float(crawl_cfg.get("yield_threshold", 0.15)),
                    increment=int(crawl_cfg.get("budget_increment", 25)),
                    exhaustion_window=int(crawl_cfg.get("exhaustion_window", 20)),
                    scope=scope,
                ),
                scope_domains={registrable_domain(row["url"])},
                language=row["language"],
                crawl_scope=scope,
                max_depth=int(scope_cfg.get("max_depth",
                                            crawl_cfg.get("max_depth", 6))),
            )
            self.crawler.register_source(context)
            seeded += await self._seed_source(row, context)

        if not seeded:
            stage.status = "blocked"
            stage.detail = "every address was blocked, dead, or refused automated reading"
            self._mark_truncated("no address could be enumerated")
            return

        await self.crawler.run(stage=2)
        pending = self.frontier.pending()
        exhausted = [c.source_id for c in self.crawler.sources.values() if c.budget.exhausted]
        if pending:
            stage.status = "partial"
            stage.detail = f"{pending} URLs still queued when the page cap was reached"
            self._mark_truncated(f"stage 2 stopped with {pending} URLs still queued")
        else:
            stage.status = "complete"
            stage.detail = (f"{self.crawler.stats.pages_opened} pages opened; "
                            f"{len(exhausted)} sources exhausted")
        for context in self.crawler.sources.values():
            self.db.update(
                "sources",
                {"crawl_status": "crawled" if context.budget.exhausted or not
                 self.frontier.pending_for_source(context.source_id) else "partial",
                 "exhausted": int(context.budget.exhausted),
                 "budget_pages": context.budget.limit,
                 "budget_spent": context.budget.spent},
                {"source_id": context.source_id},
            )

    async def _seed_source(self, row: Mapping[str, Any], context: SourceContext) -> int:
        """Queue the right starting points for this platform (register Stage 2A-2H)."""
        source_id = row["source_id"]
        url = row["url"]
        platform = context.platform_type
        added = 0

        added += 1 if self.frontier.add(url, source_id=source_id, depth=0, stage=2,
                                        discovery_method="seed",
                                        source_priority=context.retrieval_priority) else 0

        profile = profile_for(url, platform, self.settings.sources.get("platform_endpoints", {}))
        for seed in profile.seed_paths:
            if self.frontier.add(seed, source_id=source_id, depth=0, stage=2,
                                 discovery_method="seed",
                                 source_priority=context.retrieval_priority):
                added += 1

        if not is_website_like(platform):
            return added

        # robots.txt, then sitemaps, then feeds, then the well-known path list.
        policy = await self.fetcher.robots_for(url)
        self.db.upsert("domains",
                       {"domain": registrable_domain(url), "robots_status": policy.status,
                        "crawl_delay_s": policy.crawl_delay,
                        "sitemaps": policy.sitemaps, "checked_utc": utcnow()},
                       ["domain"])
        if policy.status == "unreachable":
            self._log_discovery(2, "path_probe", f"{url}/robots.txt", "failed",
                                "robots.txt unreachable; proceeding politely")

        sitemap_urls = candidate_sitemap_urls(
            url, self.settings.sources.get("sitemap_paths", []), policy.sitemaps)
        found_sitemap = False
        for sitemap_url in sitemap_urls[:12]:
            result = await self.fetcher.fetch(sitemap_url, kind="page",
                                              community_id=self.community_id,
                                              source_id=source_id, stage=2)
            if not result.ok or not result.content:
                continue
            body = maybe_gunzip(result.content).decode("utf-8", "replace")
            entries, nested = parse_sitemap(body, sitemap_url)
            for nested_url in nested[:40]:
                nested_result = await self.fetcher.fetch(
                    nested_url, kind="page", community_id=self.community_id,
                    source_id=source_id, stage=2)
                if nested_result.ok and nested_result.content:
                    nested_body = maybe_gunzip(nested_result.content).decode("utf-8", "replace")
                    more, _ = parse_sitemap(nested_body, nested_url)
                    entries.extend(more)
            if entries:
                found_sitemap = True
                event(log, "SITEMAP", f"{len(entries)} URLs from {sitemap_url}")
                for entry in entries[:3000]:
                    if self.frontier.add(entry.url, source_id=source_id, depth=1, stage=2,
                                         kind=entry.kind if entry.kind != "sitemap" else "page",
                                         discovery_method="sitemap",
                                         source_priority=context.retrieval_priority):
                        added += 1
                    for image in entry.images[:5]:
                        self.frontier.add(image, source_id=source_id, depth=2, stage=2,
                                          kind="image", discovery_method="sitemap")
                break

        for feed_path in self.settings.sources.get("feed_paths", [])[:8]:
            feed_url = normalize(feed_path, url)
            if not feed_url:
                continue
            result = await self.fetcher.fetch(feed_url, kind="page",
                                              community_id=self.community_id,
                                              source_id=source_id, stage=2)
            if not result.ok or not result.text:
                continue
            entries = parse_feed(result.text, feed_url)
            if entries:
                event(log, "FEED", f"{len(entries)} dated posts from {feed_url}")
                self.db.upsert("domains", {"domain": registrable_domain(url),
                                           "feeds": [feed_url], "checked_utc": utcnow()},
                               ["domain"])
                # Oldest first: the earliest posts carry the dating evidence.
                for entry in sorted(entries, key=lambda e: e.published or "")[:400]:
                    if self.frontier.add(entry.url, source_id=source_id, depth=1, stage=2,
                                         discovery_method="feed",
                                         source_priority=context.retrieval_priority):
                        added += 1
                    for enclosure in entry.enclosures[:5]:
                        self.frontier.add(enclosure, source_id=source_id, depth=2, stage=2,
                                          discovery_method="feed")
                break

        language = row["language"] or language_for_country(self.community.country)
        paths = list(self.settings.sources.get("well_known_paths", {}).get("en", []))
        if language and language != "en":
            paths += list(self.settings.sources.get("well_known_paths", {}).get(language, []))
        for path in paths:
            candidate = normalize(path, url)
            if candidate and self.frontier.add(candidate, source_id=source_id, depth=1, stage=2,
                                               discovery_method="path_probe",
                                               source_priority=context.retrieval_priority):
                added += 1

        if not found_sitemap:
            self._log_discovery(2, "sitemap", url, "failed",
                                "no sitemap found; relying on navigation, feeds and path probes")

        # site: enumeration catches pages linked from nowhere.
        domain = registrable_domain(url)
        for query in search_mod.site_queries(domain, years=[2010, 2013, 2016])[:4]:
            for hit in await self._search_web(query, stage=2, purpose="indexed page enumeration"):
                if registrable_domain(hit.url) == domain:
                    if self.frontier.add(hit.url, source_id=source_id, depth=1, stage=2,
                                         discovery_method="search",
                                         source_priority=context.retrieval_priority):
                        added += 1
        return added

    # ---------------------------------------------------------------------
    # Stage 3 — documents
    # ---------------------------------------------------------------------
    async def _stage_3(self) -> None:
        stage = self.stages[3]
        extensions = self.settings.sources.get("filetype_search_extensions", ["pdf"])
        queued = 0
        for name in list(self.names)[:3]:
            for query in search_mod.filetype_queries(name, extensions[:6]):
                for hit in await self._search_web(query, stage=3, purpose="document discovery"):
                    if self.frontier.add(hit.url, source_id=self._source_for_url(hit.url),
                                         depth=1, stage=3, kind="document",
                                         discovery_method="search"):
                        queued += 1
        await self.crawler.run(stage=3)
        documents = int(self.db.scalar(
            "SELECT COUNT(*) FROM documents WHERE community_id = ?", (self.community_id,)) or 0)
        grouped = self._reconcile_document_families()
        stage.status = "complete"
        stage.detail = (f"{documents} documents stored ({queued} queued by file-type "
                        f"search)"
                        + (f"; {grouped['grouped']} of them are translations or "
                           f"re-issues of {grouped['families']} underlying documents"
                           if grouped.get("grouped") else ""))
        event(log, "DOCS", f"{documents} documents stored")

    def _reconcile_document_families(self) -> dict[str, int]:
        """Group translations and re-issues, now that the files are in hand.

        The download-time triage in `extract/triage.py` decides what to parse
        from a filename alone, which is all it has. This runs afterwards, with
        the page counts, byte sizes and content hashes that only exist once the
        documents have been retrieved, and it is where two things are settled
        that the earlier pass cannot settle:

        **One independence group per family.** Three translations of one report
        are one source. Left ungrouped they would corroborate each other, which
        would breach the rule the whole protocol rests on (brief §28).

        **A record of what was grouped, and how confidently.** A family formed
        on weak evidence goes to the review queue rather than being acted on
        silently (brief §80, §81).
        """
        from .evidence import families as families_mod

        try:
            rows = self.db.query(
                "SELECT d.document_id, d.filename, d.title, d.sha256, d.bytes, "
                "       d.page_count, d.language, "
                "       (SELECT original_url FROM document_sources s "
                "         WHERE s.document_id = d.document_id LIMIT 1) AS url, "
                "       (SELECT source_id FROM document_sources s "
                "         WHERE s.document_id = d.document_id LIMIT 1) AS source_id "
                "FROM documents d WHERE d.community_id = ?", (self.community_id,))
        except Exception as exc:
            log.debug("could not read documents for family grouping: %s", exc)
            return {}
        if len(rows) < 2:
            return {}

        refs = [
            families_mod.DocumentRef(
                document_id=row["document_id"],
                url=row["url"] or "",
                filename=row["filename"] or "",
                title=row["title"] or "",
                content_hash=row["sha256"] or "",
                bytes_len=int(row["bytes"] or 0),
                pages=row["page_count"],
                language=row["language"] or "",
                source_id=row["source_id"] or "",
                discovered_index=index,
            )
            for index, row in enumerate(rows)
        ]
        groups = families_mod.group(refs, prefix=f"{self.community_id}-FAM")
        for family in groups:
            if family.size < 2:
                continue
            primary = family.primary()
            for member in family.members:
                role = "primary" if member.document_id == family.primary_id else "version"
                try:
                    self.db.update("documents",
                                   {"family_id": family.family_id, "family_role": role},
                                   {"document_id": member.document_id})
                except Exception:
                    pass
            # Everything in the family shares the primary's independence group,
            # so the copies cannot corroborate one another.
            if primary is not None and primary.source_id:
                group_id = self.db.scalar(
                    "SELECT independence_group FROM sources WHERE source_id = ?",
                    (primary.source_id,))
                if group_id:
                    for member in family.others():
                        if member.source_id and member.source_id != primary.source_id:
                            try:
                                self.db.update(
                                    "sources", {"independence_group": group_id},
                                    {"source_id": member.source_id})
                            except Exception:
                                pass
            event(log, "DOCS",
                  f"{family.size} documents grouped as {family.family_id} "
                  f"(primary {family.primary_id}); "
                  f"{'; '.join(family.reasons[:2])}")
        for case in families_mod.review_cases(groups):
            self.review.add(**case)
        numbers = families_mod.savings(groups)
        self.document_families = numbers
        return numbers

    # ---------------------------------------------------------------------
    # Stage 4 — archived versions
    # ---------------------------------------------------------------------
    async def _stage_4(self) -> None:
        stage = self.stages[4]
        archive_cfg = dict(self.settings.sources.get("archive", {}))
        run_cfg = dict(self.settings.get("archive", default={}) or {})
        if not run_cfg.get("enabled", True):
            stage.status = "not_reached"
            stage.detail = "archive stage disabled in configuration"
            return

        domains: dict[str, str] = {}
        for row in self._sources():
            domain = row["registrable_domain"]
            if domain:
                domains.setdefault(domain, row["source_id"])

        reachable = 0
        unreachable: list[str] = []
        snapshots_fetched = 0
        #: Discovered is not fetched, and the report must show both (brief §63).
        archive_discovered = 0
        #: Tiers not retrieved because the archive stopped paying for itself.
        archive_truncated: list[str] = []
        for domain, source_id in list(domains.items())[:12]:
            # Enumerating the archive for one domain is a long single request;
            # between domains is the safe boundary (brief §24).
            await self.supervisor.gate(stage_no=4, stage_name=STAGE_NAMES[4],
                                       source_id=source_id, task_ref=domain,
                                       task_detail=f"about to query the archive for {domain}")
            query_url = wayback_mod.build_cdx_query(
                archive_cfg.get("cdx_endpoint", "http://web.archive.org/cdx/search/cdx"),
                domain,
                {**archive_cfg.get("cdx_params", {}),
                 "limit": int(run_cfg.get("cdx_limit", 5000))},
            )
            result = await self.fetcher.fetch(query_url, kind="page",
                                              community_id=self.community_id,
                                              source_id=source_id, stage=4, obey_robots=False)
            self._log_search(
                database_id="wayback_cdx", database_name="Wayback CDX index",
                database_type="archive", query=f"{domain}*", language="n/a",
                result="hits found" if result.ok else "unreachable",
                hits=0, stage=4, http_status=result.status,
                detail=result.error_detail or "",
            )
            if not result.ok or not result.content:
                unreachable.append(domain)
                event(log, "ARCHIVE", f"CDX index unreachable for {domain} — "
                                      f"{result.error_detail or 'no response'}")
                self.db.update("sources", {"archive_checked": 0}, {"source_id": source_id})
                continue

            parsed = wayback_mod.parse_cdx(result.content)
            if not parsed.ok:
                unreachable.append(domain)
                continue
            reachable += 1
            event(log, "ARCHIVE",
                  f"{len(parsed.entries)} archived URLs listed for {domain}")
            self.db.update(
                "sources",
                {"archive_checked": 1,
                 "archive_snapshot_count": len(parsed.entries),
                 "archive_earliest_snapshot": (
                     min((e.iso_date for e in parsed.entries), default=None))},
                {"source_id": source_id},
            )
            archive_discovered += len(parsed.entries)
            # ENUMERATION IS NOT RETRIEVAL (brief §14). Five thousand CDX rows
            # cost one request; fetching them would cost four hours. So the
            # index is sorted into three tiers by what each snapshot IS, and
            # each tier is retrieved only while the archive is still repaying
            # the time (brief §15).
            #
            #   tier 1  deleted documents, named priority pages, strongly
            #           historical paths — always retrieved
            #   tier 2  a strategic sample across the years of relevant pages
            #   tier 3  everything else — only while yield stays high
            #
            # The enumeration cap below bounds how much of a huge index is even
            # considered; it is not a retrieval budget, and tier 1 is never
            # withheld to satisfy a clock.
            enumeration_cap = int(run_cfg.get("max_snapshots_considered_per_domain", 400))
            tiers = wayback_mod.select_snapshots_by_tier(
                parsed.entries,
                priority_paths=archive_cfg.get("priority_snapshot_paths", ["/"]),
                max_per_url=int(run_cfg.get("max_snapshots_per_url", 20)),
                max_total=enumeration_cap,
                max_low_relevance_share=float(
                    run_cfg.get("low_relevance_snapshot_share", 0.25)),
            )
            template = archive_cfg.get("snapshot_url_template",
                                       "https://web.archive.org/web/{timestamp}id_/{url}")
            archive_scope = f"archive:{domain}"
            event(log, "ARCHIVE",
                  f"{domain}: {len(parsed.entries)} archived URLs listed — "
                  f"{len(tiers[wayback_mod.TIER_HIGH_VALUE])} high-value, "
                  f"{len(tiers[wayback_mod.TIER_STRATEGIC])} strategic, "
                  f"{len(tiers[wayback_mod.TIER_ADDITIONAL])} additional")

            for tier in (wayback_mod.TIER_HIGH_VALUE, wayback_mod.TIER_STRATEGIC,
                         wayback_mod.TIER_ADDITIONAL):
                batch = tiers.get(tier) or []
                if not batch:
                    continue
                if tier > wayback_mod.TIER_HIGH_VALUE:
                    verdict = self._archive_tier_verdict(archive_scope, tier, domain)
                    if not verdict.keep_going:
                        archive_truncated.append(
                            f"{domain} tier {tier}: {verdict.reason}")
                        event(log, "ARCHIVE",
                              f"{domain}: stopping before tier {tier} — {verdict.reason}")
                        break
                queued = 0
                for snapshot in batch[:int(run_cfg.get(
                        "max_snapshot_fetches_per_domain_per_tier", 120))]:
                    if snapshot.kind == "image":
                        continue
                    snapshot_url = snapshot.snapshot_url(template)
                    if self.frontier.add(snapshot_url, source_id=source_id, depth=1,
                                         stage=4, kind=snapshot.kind,
                                         discovery_method=f"cdx-tier{tier}",
                                         source_priority="A",
                                         priority=14.0 - tier):
                        queued += 1
                        snapshots_fetched += 1
                        self._log_discovery(4, "cdx", snapshot.original, "new_url",
                                            f"snapshot {snapshot.iso_date} "
                                            f"(tier {tier}: {snapshot.reason})")
                if not queued:
                    continue
                self._current_source = source_id
                before = self.meter.scope(archive_scope).units
                await self.crawler.run(stage=4)
                self._charge_active_time()
                gained = self.meter.scope(archive_scope).units - before
                event(log, "ARCHIVE",
                      f"{domain} tier {tier}: {queued} snapshots retrieved, "
                      f"{gained:.0f} yield units")
                self._current_source = ""

        await self.crawler.run(stage=4)

        if unreachable and not reachable:
            stage.status = "blocked"
            stage.detail = ("the archive index was unreachable for every domain: "
                            + ", ".join(unreachable))
            self._mark_truncated("the web archive was unreachable, so stage 4 could not be completed")
        elif unreachable:
            stage.status = "partial"
            stage.detail = (f"{reachable} domains listed; unreachable for "
                            + ", ".join(unreachable))
            self._mark_truncated(
                "the web archive was unreachable for " + ", ".join(unreachable))
        elif archive_truncated:
            # Deliberate, evidence-driven, and never mislabelled as exhaustive
            # (brief §61).
            stage.status = "complete"
            stage.detail = ("deeper archive tiers were not retrieved because their "
                            "marginal yield had fallen away: "
                            + "; ".join(archive_truncated[:6]))
            self._mark_truncated(
                "TRUNCATED_LOW_YIELD: " + "; ".join(archive_truncated[:6]))
        else:
            stage.status = "complete"
        self.archive_truncated = archive_truncated
        # Discovered is not fetched, and both belong in the record: the archive
        # is sampled by relevance, never enumerated (brief §19, §63).
        self.archive_discovered = archive_discovered
        self.archive_fetched = snapshots_fetched
        if archive_discovered:
            event(log, "ARCHIVE",
                  f"{archive_discovered} archived URLs discovered, {snapshots_fetched} "
                  f"queued for retrieval "
                  f"({snapshots_fetched / archive_discovered:.1%}); the rest are "
                  "recorded as discovered but not fetched")
        if stage.status == "complete":
            stage.detail = (f"{reachable} domain(s) listed; {archive_discovered} archived "
                            f"URLs discovered, {snapshots_fetched} queued for retrieval")

    # ---------------------------------------------------------------------
    # Stage 5 — academic literature
    # ---------------------------------------------------------------------
    async def _stage_5(self) -> None:
        stage = self.stages[5]
        cfg = dict(self.settings.get("academic", default={}) or {})
        if not cfg.get("enabled", True):
            stage.status = "not_reached"
            return

        databases = list(self.settings.sources.get("academic_databases", []))
        databases += self._national_portals()
        queries = academic_mod.build_queries(
            names=self.names,
            locality=None,
            region=None,
            country=self.community.country,
            founders=self.founders,
            networks=self.networks,
            terms_by_language=self.settings.sources.get("academic_query_terms", {}),
            languages=self.languages,
        )
        if not queries:
            queries = [(f'"{self.community.name}"', "en")]

        searched = 0
        unreachable = 0
        records: dict[str, academic_mod.AcademicRecord] = {}
        for database in databases:
            await self.supervisor.gate(
                stage_no=5, stage_name=STAGE_NAMES[5],
                task_ref=str(database.get("id")),
                task_detail=f"about to search {database.get('name', database.get('id'))}")
            outcome = await self._search_academic_database(database, queries[:8])
            searched += 1
            if outcome.result == "unreachable":
                unreachable += 1
            for record in outcome.records:
                score, reason = academic_mod.score_relevance(
                    record, names=self.names, locality=None, region=None,
                    country=self.community.country)
                if score < float(cfg.get("relevance_min_score", 0.35)):
                    continue
                record.relevance_score = score
                record.relevance_reason = reason
                records.setdefault(record.identity_key, record)

        verified = 0
        full_text = 0
        for record in records.values():
            if await self._verify_academic_record(record):
                verified += 1
            if cfg.get("fetch_full_text", True) and record.pdf_url:
                # Register the record as a source before fetching it. Without
                # this its full text would be mined under the default community
                # class, and a thesis coded as S4 can never upgrade a practice
                # to `evidenced` or supply a rank-1 onset — which is the whole
                # reason stages 5 and 6 exist.
                source_id = self._register_evidence_source(
                    url=record.pdf_url or record.url,
                    source_class="S1",
                    platform_type="other",
                    title=record.title,
                    verified=(record.verified_resolves == "yes"),
                    discovery_method="academic_api",
                    discovery_query=record.database_id,
                )
                queued = self.frontier.add(record.pdf_url, source_id=source_id, depth=1, stage=5,
                                           kind="document", discovery_method="api",
                                           priority=13.0)
                if queued:
                    full_text += 1
                    record.full_text_status = "full text"
                record.source_id = source_id
            self._store_academic_record(record)

        await self.crawler.run(stage=5)

        if records:
            event(log, "ACADEMIC",
                  f"{len(records)} candidate records, {verified} verified, "
                  f"{full_text} full texts queued")
        else:
            event(log, "ACADEMIC",
                  f"no relevant records in {searched} databases — the expected result "
                  "for most communities; recorded as a negative consultation")

        if unreachable == searched and searched:
            stage.status = "blocked"
            stage.detail = f"all {searched} academic databases were unreachable"
            self._mark_truncated("every academic database was unreachable")
        elif unreachable:
            stage.status = "partial"
            stage.detail = (f"{searched - unreachable} of {searched} databases searched; "
                            f"{unreachable} unreachable; {len(records)} relevant records")
            self._mark_truncated(f"{unreachable} academic databases were unreachable")
        else:
            stage.status = "complete"
            stage.detail = (f"{searched} databases searched, {len(records)} relevant records, "
                            f"{verified} verified")

    def _register_evidence_source(self, *, url: str, source_class: str, platform_type: str,
                                  title: str, verified: bool, discovery_method: str,
                                  discovery_query: str = "") -> str | None:
        """Give a non-web-address source (a thesis, a grant record) a source row.

        It gets its own independence group: an outside researcher or a funder
        could have found something different, which is exactly what makes
        corroboration across groups worth something.
        """
        normalized = normalize(url or "")
        if not normalized:
            return None
        existing = self._existing_source_for(normalized)
        if existing:
            return existing
        source_id = self._create_source(normalized, supplied_or_discovered="discovered",
                                        discovery_method=discovery_method,
                                        discovery_query=discovery_query)
        group = self.independence.new_group()
        self.db.update(
            "sources",
            {
                "source_class": source_class,
                "platform_type": platform_type,
                "independence_group": group,
                "independence_reason": (
                    f"independent origin ({source_class}); "
                    + ("the record was independently verified in this run"
                       if verified else "the record is stored but NOT verified, so it is barred "
                                        "from supporting a workbook value")
                ),
                "belongs_confirmed": int(verified),
                "belongs_evidence": title[:400],
                "retrieval_priority": "A",
                "access_status": "ok",
                "crawl_status": "crawled",
            },
            {"source_id": source_id},
        )
        self.independence.assignments[source_id] = type(
            "Assignment", (), {"source_id": source_id, "group": group,
                               "reason": f"independent {source_class} record"},
        )()
        return source_id

    def _national_portals(self) -> list[dict[str, Any]]:
        portals = self.settings.sources.get("national_thesis_portals", {})
        country = self.community.country or ""
        return list(portals.get(country) or portals.get("default") or [])

    async def _search_academic_database(self, database: Mapping[str, Any],
                                        queries: Sequence[tuple[str, str]]) -> academic_mod.SearchOutcome:
        db_id = str(database.get("id"))
        name = str(database.get("name", db_id))
        db_type = str(database.get("type", "academic"))
        access = str(database.get("access", "manual"))
        combined = "; ".join(q for q, _ in queries)
        languages = "; ".join(sorted({lang for _, lang in queries}))

        if access == "manual":
            detail = str(database.get("note", "blocks automated access"))
            self._log_search(database_id=db_id, database_name=name, database_type=db_type,
                             query=combined, language=languages, result="unreachable",
                             hits=0, stage=5, detail=detail)
            return academic_mod.SearchOutcome(db_id, name, db_type, combined, languages,
                                              "unreachable", detail=detail)

        api_key = self.settings.env.get(str(database.get("key_env", "")), "")
        if database.get("needs_key") and not api_key:
            detail = f"not configured: {database.get('key_env')} is absent"
            self._log_search(database_id=db_id, database_name=name, database_type=db_type,
                             query=combined, language=languages, result="unreachable",
                             hits=0, stage=5, detail=detail)
            return academic_mod.SearchOutcome(db_id, name, db_type, combined, languages,
                                              "unreachable", detail=detail)

        found: list[academic_mod.AcademicRecord] = []
        errors: list[str] = []
        rows_per_page = int(self.settings.get(
            "academic", "max_results_per_database", default=100))
        max_pages = int(self.settings.get(
            "academic", "max_pages_per_database", default=20))
        barren_limit = int(self.settings.get(
            "academic", "stop_after_barren_pages", default=2))
        if not academic_mod.supports_paging(dict(database)):
            max_pages = 1

        for query, language in queries:
            # PAGE UNTIL THE DATABASE RUNS OUT, not until an arbitrary fifty.
            # The brief asks for every paper and thesis that mentions the
            # community, and the communities that matter most here - Tamera,
            # Damanhur, Cloughjordan, Findhorn - are each discussed in hundreds
            # of works. One window of fifty silently returned whichever the API
            # ranked first and looked identical to a complete answer.
            seen_here: set[str] = set()
            barren = 0
            for page in range(max_pages):
                request = academic_mod.request_for(
                    dict(database), query, rows=rows_per_page,
                    api_key=api_key or None, page=page)
                if request is None:
                    break
                url, headers = request
                result = await self.fetcher.fetch(url, kind="page", headers=headers,
                                                  community_id=self.community_id, stage=5,
                                                  obey_robots=False)
                if not result.ok or not result.text:
                    if page == 0:
                        errors.append(result.error_detail or "no response")
                    break
                page_records = academic_mod.parse_response(db_id, result.text)
                if not page_records:
                    break
                fresh = [r for r in page_records if r.identity_key() not in seen_here]
                seen_here.update(r.identity_key() for r in page_records)
                found.extend(fresh)
                # A page that adds nothing new is the end of the result set. Some
                # APIs clamp an out-of-range page to the last one rather than
                # returning empty, so repeats - not emptiness - are the signal.
                barren = barren + 1 if not fresh else 0
                if barren >= barren_limit or len(page_records) < rows_per_page:
                    break
                await self.supervisor.gate()

        if errors and not found:
            detail = "; ".join(errors[:3])
            self._log_search(database_id=db_id, database_name=name, database_type=db_type,
                             query=combined, language=languages, result="unreachable",
                             hits=0, stage=5, detail=detail)
            return academic_mod.SearchOutcome(db_id, name, db_type, combined, languages,
                                              "unreachable", detail=detail)

        result_label = "hits found" if found else "none found"
        self._log_search(database_id=db_id, database_name=name, database_type=db_type,
                         query=combined, language=languages, result=result_label,
                         hits=len(found), stage=5)
        return academic_mod.SearchOutcome(db_id, name, db_type, combined, languages,
                                          result_label, hits=len(found), records=found)

    async def _verify_academic_record(self, record: academic_mod.AcademicRecord) -> bool:
        """A record may support a value only once its existence is confirmed."""
        for kind, url in academic_mod.verification_targets(record):
            result = await self.fetcher.fetch(url, kind="page", community_id=self.community_id,
                                              stage=5, obey_robots=False)
            if not result.ok:
                continue
            body = (result.text or "")[:200000]
            if kind == "doi" and body:
                try:
                    payload = json.loads(body)
                    titles = payload.get("message", {}).get("title") or []
                    if titles and academic_mod.titles_match(record.title, str(titles[0])):
                        record.verified_resolves = "yes"
                        record.verification_detail = f"DOI record retrieved and the title matches ({url})"
                        return True
                except json.JSONDecodeError:
                    pass
            if body and academic_mod.titles_match(record.title, body[:6000]):
                record.verified_resolves = "yes"
                record.verification_detail = f"{kind} retrieved and the title appears in it ({url})"
                return True
            if result.mime == "application/pdf":
                record.verified_resolves = "yes"
                record.verification_detail = f"full text retrieved from {url}"
                record.full_text_status = "full text"
                return True
        record.verified_resolves = "no"
        record.verification_detail = (
            "the record could not be independently retrieved in this run; it is stored but "
            "barred from supporting any workbook value"
        )
        self.review.add(
            "academic", f"Unverified academic record: {record.title[:60]}",
            f"{record.title} ({record.year or 'undated'}) from {record.database_id} could not be "
            "verified. A fabricated or mis-indexed citation looks like the strongest evidence in "
            "the record, so it is excluded from coding until a human confirms it.",
            severity="normal",
        )
        return False

    def _store_academic_record(self, record: academic_mod.AcademicRecord) -> None:
        record_id = self.db.next_id("academic_records", "record_id", self.community_id, "AC", width=3)
        self.db.insert(
            "academic_records",
            {
                "record_id": record_id,
                "community_id": self.community_id,
                "database_id": record.database_id,
                "title": record.title[:1000],
                "authors": record.authors[:1000],
                "year": record.year,
                "venue": record.venue[:500],
                "doi": record.doi[:300],
                "url": record.url[:1000],
                "repository": record.repository[:300],
                "record_type": record.record_type[:100],
                "abstract": record.abstract[:8000],
                "full_text_status": record.full_text_status,
                "verified_resolves": record.verified_resolves,
                "verification_detail": record.verification_detail[:1000],
                "verified_utc": utcnow(),
                "relevance_score": record.relevance_score,
                "relevance_reason": record.relevance_reason[:600],
                "created_utc": utcnow(),
            },
            replace=True,
        )

    # ---------------------------------------------------------------------
    # Stage 6 — grey literature
    # ---------------------------------------------------------------------
    async def _stage_6(self) -> None:
        stage = self.stages[6]
        if not self.settings.get("grey", "enabled", default=True):
            stage.status = "not_reached"
            return

        databases = [
            db for db in self.settings.sources.get("grey_databases", [])
            if not db.get("countries") or self.community.country in db.get("countries", [])
        ]
        queries = grey_mod.build_queries(
            names=self.names, entity_names=self.entities,
            locality=None, country=self.community.country,
            templates=self.settings.sources.get("grey_query_templates", []),
        )
        searched = 0
        unreachable = 0
        found_types: set[str] = set()

        for database in databases:
            db_id = str(database.get("id"))
            name = str(database.get("name", db_id))
            db_type = str(database.get("type", "grey - funding"))
            await self.supervisor.gate(stage_no=6, stage_name=STAGE_NAMES[6],
                                       task_ref=db_id,
                                       task_detail=f"about to search {name}")
            api_key = self.settings.env.get(str(database.get("key_env", "")), "")
            searched += 1

            if database.get("access") != "api" or (database.get("needs_key") and not api_key):
                detail = ("no automatable endpoint; this database must be consulted by hand"
                          if database.get("access") != "api"
                          else f"not configured: {database.get('key_env')} is absent")
                self._log_search(database_id=db_id, database_name=name, database_type=db_type,
                                 query="; ".join(queries[:5]), language="n/a",
                                 result="unreachable", hits=0, stage=6, detail=detail)
                unreachable += 1
                continue

            records: list[grey_mod.GreyRecord] = []
            errors: list[str] = []
            for query in queries[:6]:
                rows_per_page = int(self.settings.get(
                    "grey", "max_results_per_database", default=100))
                grey_pages = int(self.settings.get(
                    "grey", "max_pages_per_database", default=10))
                if not grey_mod.supports_paging(dict(database)):
                    grey_pages = 1
                seen_here: set[str] = set()
                for page in range(grey_pages):
                    request = grey_mod.request_for(
                        dict(database), query, rows=rows_per_page,
                        api_key=api_key or None, page=page)
                    if request is None:
                        break
                    url, headers = request
                    result = await self.fetcher.fetch(url, kind="page", headers=headers,
                                                      community_id=self.community_id, stage=6,
                                                      obey_robots=False)
                    if not result.ok or not result.text:
                        if page == 0:
                            errors.append(result.error_detail or "no response")
                        break
                    page_records = grey_mod.parse_response(dict(database), result.text)
                    if not page_records:
                        break
                    fresh = [r for r in page_records
                             if (r.url or r.title) not in seen_here]
                    seen_here.update((r.url or r.title) for r in page_records)
                    records.extend(fresh)
                    if not fresh or len(page_records) < rows_per_page:
                        break
                    await self.supervisor.gate()

            if errors and not records:
                unreachable += 1
                self._log_search(database_id=db_id, database_name=name, database_type=db_type,
                                 query="; ".join(queries[:5]), language="n/a",
                                 result="unreachable", hits=0, stage=6,
                                 detail="; ".join(errors[:3]))
                continue

            for record in records:
                if not self._grey_record_matches(record):
                    continue
                grey_type = record.grey_type or grey_mod.classify_grey_type(
                    record.title, record.summary, record.organisation)
                found_types.add(grey_type)
                grey_source = None
                if record.url:
                    grey_source = self._register_evidence_source(
                        url=record.url, source_class="S2", platform_type="other",
                        title=record.title, verified=True,
                        discovery_method="grey_api", discovery_query=record.database_id,
                    )
                    self.frontier.add(record.url, source_id=grey_source, depth=1, stage=6,
                                      discovery_method="api", priority=11.0)
                self._record_grey_evidence(record, grey_type, source_id=grey_source)

            self._log_search(database_id=db_id, database_name=name, database_type=db_type,
                             query="; ".join(queries[:5]), language="n/a",
                             result="hits found" if records else "none found",
                             hits=len(records), stage=6)

        # File-type search reaches reports that are linked from nowhere.
        for name in list(self.names)[:2]:
            for query in search_mod.filetype_queries(name, ["pdf"])[:2]:
                for hit in await self._search_web(query, stage=6, purpose="grey literature"):
                    self.frontier.add(hit.url, source_id=self._source_for_url(hit.url),
                                      depth=1, stage=6, kind="document",
                                      discovery_method="search")

        await self.crawler.run(stage=6)

        if unreachable == searched and searched:
            stage.status = "blocked"
            stage.detail = f"all {searched} grey-literature sources were unreachable or manual"
            self._mark_truncated("every grey-literature database was unreachable")
        elif unreachable:
            stage.status = "partial"
            stage.detail = (f"{searched - unreachable} of {searched} searched; "
                            f"types found: {', '.join(sorted(found_types)) or 'none'}")
        else:
            stage.status = "complete"
            stage.detail = f"{searched} searched; types found: {', '.join(sorted(found_types)) or 'none'}"

    def _grey_record_matches(self, record: grey_mod.GreyRecord) -> bool:
        haystack = " ".join([record.title, record.summary, record.organisation]).lower()
        for name in self.names | self.entities:
            if len(name) > 3 and name.lower() in haystack:
                return True
        return False

    def _record_grey_evidence(self, record: grey_mod.GreyRecord, grey_type: str,
                              *, source_id: str | None = None) -> None:
        """A dated grant record is rank-1 onset evidence — record it as such."""
        if not record.title:
            return
        quote = "; ".join(part for part in (
            record.title, record.organisation, record.summary[:400],
            f"start {record.start_date}" if record.start_date else "",
            f"amount {record.amount}" if record.amount else "",
        ) if part)
        evidence = EvidenceItem(
            evidence_type="metadata",
            quote=quote[:2000],
            locator=f"{record.database_name} record {record.identifier or 'unnumbered'}",
            source_class="S2",
            publication_date=record.start_date or (str(record.year) if record.year else None),
            retrieval_date=utcnow()[:10],
        )
        claims: list[ClaimItem] = [
            ClaimItem(
                field_name="external_funding_or_programme",
                value=f"{record.title} ({record.database_name}"
                      + (f", {record.year}" if record.year else "") + ")",
                value_type="text", original_value=record.title,
                exact_wording=quote[:1000], reference_year=record.year, confidence=0.75,
                rationale=f"a {grey_type} naming the community, retrieved from "
                          f"{record.database_name}",
                extractor="rule:grey/1.0.0",
            )
        ]
        evidence.source_id = source_id
        evidence_id, _ = self.recorder.record(
            evidence, claims,
            {"source_id": source_id, "source_class": "S2",
             "independence_group": self._group_of(source_id)},
        )
        if record.year:
            self.date_candidates.append(
                DateCandidate(
                    field_name="date_intervention_onset" if _funding_is_environmental(record)
                    else "date_formal_founding",
                    year=record.year,
                    sentence=quote[:1200],
                    source_id=source_id,
                    source_class="S2",
                    evidence_rank=1,
                    rank_reason=f"a dated independent {grey_type} from {record.database_name}",
                    independence_group=self._group_of(source_id),
                )
            )

    # ---------------------------------------------------------------------
    # Stage 7 — other web sources
    # ---------------------------------------------------------------------
    async def _stage_7(self) -> None:
        stage = self.stages[7]
        promoted = 0
        for domain, entry in list(self.crawler.external_candidates.items()):
            if domain in self.community_domains:
                continue
            trusted = self._footer_link_is_own_account(entry)
            for url in entry["urls"][:2]:
                if self._consider_candidate(url, "link", entry.get("first_seen_on", ""),
                                            from_confirmed_source=trusted):
                    promoted += 1

        self._assign_independence_groups()
        crawl_cfg = dict(self.settings.get("crawl", default={}) or {})
        newly = [row for row in self._sources() if row["crawl_status"] == "not attempted"]
        for row in newly:
            if row["access_status"] in ("blocked", "dead"):
                continue
            context = SourceContext(
                source_id=row["source_id"], url=row["url"],
                platform_type=row["platform_type"] or "other",
                source_class=row["source_class"] or "S4",
                retrieval_priority=row["retrieval_priority"] or "C",
                independence_group=row["independence_group"],
                login_walled=(row["platform_type"] in LOGIN_WALLED),
                budget=SourceBudget(row["source_id"],
                                    base=max(8, int(crawl_cfg.get("base_pages_per_source", 40)) // 3),
                                    maximum=int(crawl_cfg.get("max_pages_per_source", 400))),
                scope_domains={registrable_domain(row["url"])},
                language=row["language"],
            )
            self.crawler.register_source(context)
            await self._seed_source(row, context)

        await self.crawler.run(stage=7)
        for context in self.crawler.sources.values():
            pending = self.frontier.pending_for_source(context.source_id)
            self.db.update("sources",
                           {"crawl_status": "partial" if pending else "crawled",
                            "exhausted": int(context.budget.exhausted)},
                           {"source_id": context.source_id})
        stage.status = "complete"
        stage.detail = f"{promoted} additional addresses promoted and crawled"

    # ---------------------------------------------------------------------
    # Stage 8 — local-language sweep
    # ---------------------------------------------------------------------
    async def _stage_8(self) -> None:
        stage = self.stages[8]
        local = {lang for lang in self.languages if lang and lang != "en"}
        if not local:
            stage.status = "complete"
            stage.detail = "no local language other than English was established for this community"
            return

        terms = self.settings.sources.get("academic_query_terms", {})
        queries: list[tuple[str, str]] = []
        for language in local:
            for name in list(self.names)[:2]:
                for term in terms.get(language, [])[:5]:
                    queries.append((f'"{name}" {term}', language))
        searched = 0
        for query, language in queries[:14]:
            hits = await self._search_web(query, stage=8, purpose="local-language sweep",
                                          language=language)
            searched += 1
            for hit in hits[:8]:
                source_id = self._source_for_url(hit.url)
                if source_id:
                    self.frontier.add(hit.url, source_id=source_id, depth=1, stage=8,
                                      discovery_method="search")
                else:
                    self._consider_candidate(hit.url, "search", query)

        # National thesis portals are almost always local-language only.
        for database in self._national_portals():
            await self.supervisor.gate(stage_no=8, stage_name=STAGE_NAMES[8],
                                       task_ref=str(database.get("id")),
                                       task_detail="about to search a national thesis portal")
            outcome = await self._search_academic_database(
                database, [(f'"{n}"', lang) for n in list(self.names)[:2] for lang in local][:4])
            for record in outcome.records[:20]:
                score, reason = academic_mod.score_relevance(
                    record, names=self.names, locality=None, region=None,
                    country=self.community.country)
                if score >= 0.35:
                    record.relevance_score, record.relevance_reason = score, reason
                    await self._verify_academic_record(record)
                    self._store_academic_record(record)

        await self.crawler.run(stage=8)
        stage.status = "complete"
        stage.detail = f"{searched} local-language searches in {', '.join(sorted(local))}"

    # ---------------------------------------------------------------------
    # Stage 9 — reconciliation
    # ---------------------------------------------------------------------
    async def _stage_9(self) -> None:
        """Reconciliation. Timed as one block: it is paid for from the reserve."""
        from .resolve import FieldResolver

        stage = self.stages[9]
        self._reassess_independence()
        resolver = FieldResolver(
            db=self.db, settings=self.settings, community_id=self.community_id,
            review=self.review, independence=self.independence,
        )
        summary = resolver.resolve(
            community=self.community,
            date_candidates=self.date_candidates + resolver.stored_date_candidates(),
            practice_hits=self.practice_hits,
            published_coordinates=self.published_coordinates,
            names=self.names, networks=self.networks, certifiers=self.certifiers,
            stages=self.stages, truncation_reasons=self.truncation_reasons,
            languages=self.languages,
        )
        stage.status = "complete"
        stage.detail = (f"{summary['coded']} fields coded, {summary['not_found']} NOT FOUND, "
                        f"{summary['review']} for review, {summary['conflicts']} conflicts")
        event(log, "RECONCILE", stage.detail)

    # =====================================================================
    # crawler callbacks
    # =====================================================================
    def _on_page(self, page_id: str, parsed: Any, context: Mapping[str, Any]) -> int:
        text_path = self.storage.text / f"{page_id}.txt"
        text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() \
            else parsed.text
        return self._mine_and_record(
            text=text,
            source_id=context.get("source_id"),
            source_class=context.get("source_class", "S4"),
            page_id=page_id,
            document_id=None,
            locator=context.get("url"),
            publication_date=context.get("published_date"),
            retrieval_date=context.get("retrieval_date"),
            language=parsed.html_lang,
            independence_group=context.get("independence_group"),
            is_archive_snapshot=bool(context.get("archive_timestamp")),
            archive_timestamp=context.get("archive_timestamp"),
            title=parsed.title,
        )

    def _on_document(self, document_id: str, extraction: Any, context: Mapping[str, Any]) -> int:
        count = self._mine_and_record(
            text=extraction.text,
            source_id=context.get("source_id"),
            source_class=context.get("source_class", "S4"),
            page_id=None,
            document_id=document_id,
            locator=context.get("url"),
            publication_date=context.get("publication_date"),
            retrieval_date=context.get("retrieval_date"),
            language=None,
            independence_group=context.get("independence_group"),
            is_archive_snapshot=bool(context.get("archive_timestamp")),
            archive_timestamp=context.get("archive_timestamp"),
            title=context.get("title", ""),
        )
        # Spreadsheet cells keep their coordinates so a figure can be cited as
        # Sheet1!B7 rather than "somewhere in the file" (brief §21).
        for table in extraction.tables[:40]:
            count += self._mine_table(document_id, table, context)
        return count

    def _mine_table(self, document_id: str, table: Any, context: Mapping[str, Any]) -> int:
        units = self.settings.lexicon.get("quantities", {}).get("area_units", {})
        found = 0
        header = [h.lower() for h in (table.header or [])]
        for row_index, row in enumerate(table.rows[:400]):
            for col_index, cell in enumerate(row):
                if not cell or len(cell) > 60:
                    continue
                label = header[col_index] if col_index < len(header) else ""
                blob = f"{label} {cell}".strip()
                if not re.search(r"\d", blob):
                    continue
                if not any(unit in blob.lower() for unit in ("ha", "hectare", "acre", "m2", "m²")):
                    continue
                reference = (f"{table.sheet_name}!{_cell_ref(table, row_index, col_index)}"
                             if table.sheet_name else f"page {table.page_number}, row {row_index + 1}")
                evidence = EvidenceItem(
                    evidence_type="table_cell",
                    quote=f"{label}: {cell}" if label else cell,
                    document_id=document_id,
                    source_id=context.get("source_id"),
                    locator=reference,
                    context=" | ".join(row)[:1000],
                    source_class=context.get("source_class", "S4"),
                    publication_date=context.get("publication_date"),
                    retrieval_date=context.get("retrieval_date"),
                )
                self.recorder.add_evidence(evidence)
                found += 1
        return found

    def _mine_and_record(self, *, text: str, **kwargs: Any) -> int:
        with profiling.timing("text_mining"):
            mined = self.miner.mine(text, **kwargs)
        context = {
            "source_id": kwargs.get("source_id"),
            "document_id": kwargs.get("document_id"),
            "source_class": kwargs.get("source_class"),
            "independence_group": kwargs.get("independence_group"),
            "publication_date": kwargs.get("publication_date"),
            "retrieval_date": kwargs.get("retrieval_date"),
        }
        recorded = 0
        for evidence, claims in mined.evidence:
            _, claim_ids = self.recorder.record(evidence, claims, context)
            recorded += 1 if claim_ids else 0
        self.date_candidates.extend(mined.date_candidates)
        self.practice_hits.extend(mined.practice_hits)
        self.names.update(n for n in mined.networks if False)   # networks are not names
        self.networks.update(mined.networks)
        self.founders.update(mined.founders)
        self.entities.update(mined.legal_entities)
        self.certifiers.update(mined.certifiers)
        self.published_coordinates.extend(mined.published_coordinates)
        if kwargs.get("language"):
            self.languages.add(kwargs["language"])

        recorded += self._llm_pass(text, kwargs, context)
        return recorded

    def _llm_pass(self, text: str, kwargs: Mapping[str, Any], context: dict[str, Any]) -> int:
        if self.llm is None or not self.llm.available or len(text) < 500:
            return 0
        fields = [name for name in self.recorder.known_fields
                  if not name.startswith(("v1_", "v2_", "v3_", "v4_", "v5_"))]
        outcome = self.llm.extract(text, fields=sorted(fields)[:60], context={
            "source_id": kwargs.get("source_id"),
            "source_class": kwargs.get("source_class"),
            "title": kwargs.get("title", ""),
            "publication_date": kwargs.get("publication_date"),
        })
        claims = to_claims(outcome)
        if not claims:
            return 0
        evidence = EvidenceItem(
            evidence_type="passage",
            quote=claims[0].exact_wording or text[:400],
            source_id=kwargs.get("source_id"),
            document_id=kwargs.get("document_id"),
            page_id=kwargs.get("page_id"),
            locator=kwargs.get("locator"),
            source_class=kwargs.get("source_class"),
            publication_date=kwargs.get("publication_date"),
            retrieval_date=kwargs.get("retrieval_date"),
        )
        self.recorder.record(evidence, claims, context)
        return len(claims)

    # =====================================================================
    # helpers
    # =====================================================================
    def _build_llm(self) -> SemanticExtractor | None:
        cfg = dict(self.settings.get("llm", default={}) or {})
        if str(cfg.get("enabled", "auto")) == "never":
            return None
        forbidden = set(self.settings.schema.get("satellite_only_quantities", []))
        for columns in self.settings.schema.get("researcher_only_columns", {}).values():
            forbidden.update(columns)
        extractor = SemanticExtractor(
            api_key=self.settings.env.get("ANTHROPIC_API_KEY"),
            model=str(cfg.get("model", "claude-sonnet-5")),
            config=cfg,
            allowed_fields=self.recorder.known_fields,
            forbidden_fields=forbidden,
        )
        if not extractor.available:
            event(log, "LLM",
                  f"semantic extraction unavailable ({extractor.unavailable_reason}); "
                  "running deterministic extraction and enlarging the review queue")
        return extractor

    async def _search_web(self, query: str, *, stage: int, purpose: str,
                          language: str | None = None) -> list[search_mod.SearchHit]:
        """Run one query across the configured engines, logging every consultation."""
        hits: list[search_mod.SearchHit] = []
        for engine in self.settings.sources.get("search_engines", []):
            engine_id = str(engine.get("id"))
            api_key = self.settings.env.get(str(engine.get("key_env", "")), "")
            extra_key = self.settings.env.get(str(engine.get("extra_env", "")), "")
            request = search_mod.build_request(dict(engine), query, api_key=api_key or None,
                                               extra_key=extra_key or None, language=language)
            if request is None:
                self._log_search(database_id=engine_id, database_name=str(engine.get("name")),
                                 database_type="directory", query=query,
                                 language=language or "en", result="unreachable", hits=0,
                                 stage=stage,
                                 detail=f"not configured ({engine.get('key_env', 'no endpoint')})")
                continue
            url, headers = request
            result = await self.fetcher.fetch(url, kind="page", headers=headers,
                                              community_id=self.community_id, stage=stage,
                                              obey_robots=False)
            if not result.ok or not result.text:
                self._log_search(database_id=engine_id, database_name=str(engine.get("name")),
                                 database_type="directory", query=query,
                                 language=language or "en", result="unreachable", hits=0,
                                 stage=stage, http_status=result.status,
                                 detail=result.error_detail or "no response")
                continue
            parsed = search_mod.parse_results(engine_id, result.text)
            self._log_search(database_id=engine_id, database_name=str(engine.get("name")),
                             database_type="directory", query=query, language=language or "en",
                             result="hits found" if parsed else "none found",
                             hits=len(parsed), stage=stage, detail=purpose)
            hits.extend(parsed)
            if parsed:
                break     # one working engine per query is enough
        self.languages.add(language or "en")
        return hits[:25]

    @staticmethod
    def _address_key(url: str) -> str:
        """One address, whatever scheme was used to reach it."""
        return re.sub(r"^https?://", "", url or "").rstrip("/").lower()

    def _existing_source_for(self, url: str) -> str | None:
        key = self._address_key(url)
        for row in self.db.query(
            "SELECT source_id, url FROM sources WHERE community_id=?", (self.community_id,)
        ):
            if self._address_key(row["url"]) == key:
                return row["source_id"]
        return None

    def _group_of(self, source_id: str | None) -> str | None:
        if not source_id:
            return None
        row = self.db.query_one(
            "SELECT independence_group FROM sources WHERE source_id=?", (source_id,))
        return row["independence_group"] if row else None

    def _source_for_url(self, url: str) -> str | None:
        domain = registrable_domain(url)
        row = self.db.query_one(
            "SELECT source_id FROM sources WHERE community_id=? AND registrable_domain=? LIMIT 1",
            (self.community_id, domain))
        return row["source_id"] if row else None

    def _sources(self) -> list[Any]:
        return self.db.query(
            "SELECT * FROM sources WHERE community_id = ? ORDER BY source_id",
            (self.community_id,))

    def _mark_truncated(self, reason: str) -> None:
        if reason not in self.truncation_reasons:
            self.truncation_reasons.append(reason)
            event(log, "TRUNCATED", reason)

    def _error_sink(self, **kwargs: Any) -> None:
        error_id = self.db.next_id("errors", "error_id", getattr(self, "community_id", "IC000"), "ERR")
        self.db.insert(
            "errors",
            {
                "error_id": error_id,
                "run_id": getattr(self, "run_id", None),
                "community_id": getattr(self, "community_id", None),
                "stage": kwargs.get("stage"),
                "source_id": kwargs.get("source_id"),
                "url": kwargs.get("url"),
                "error_type": kwargs.get("error_type", "unknown"),
                "http_status": kwargs.get("http_status"),
                "retry_count": kwargs.get("retry_count", 0),
                "detail": (kwargs.get("detail") or "")[:4000],
                "unresolved": int(kwargs.get("unresolved", True)),
                "resolution": kwargs.get("resolution"),
                "ts_utc": utcnow(),
            },
            replace=True,
        )

    def _log_search(self, *, database_id: str, database_name: str, database_type: str,
                    query: str, language: str, result: str, hits: int, stage: int,
                    http_status: int | None = None, detail: str = "",
                    full_text_opened: int = 0, abstract_only: int = 0) -> None:
        self._search_counter += 1
        search_id = f"{self.community_id}-Q{self._search_counter:04d}"
        self.db.insert(
            "searches",
            {
                "search_id": search_id,
                "community_id": self.community_id,
                "run_id": getattr(self, "run_id", None),
                "stage": stage,
                "database_id": database_id,
                "database_name": database_name,
                "database_type": database_type,
                "query": query[:2000],
                "language": language,
                "hits_returned": hits,
                "full_text_opened": full_text_opened,
                "abstract_only": abstract_only,
                "result": result,
                "http_status": http_status,
                "detail": detail[:1000],
                "searched_utc": utcnow(),
            },
            replace=True,
        )

    def _log_discovery(self, stage: int, method: str, url: str, outcome: str,
                       detail: str = "") -> None:
        discovery_id = self.db.next_id("discovery_log", "discovery_id", self.community_id, "DSC")
        self.db.insert(
            "discovery_log",
            {
                "discovery_id": discovery_id,
                "community_id": self.community_id,
                "run_id": getattr(self, "run_id", None),
                "stage": stage,
                "method": method,
                "found_url": url,
                "outcome": outcome,
                "detail": detail[:1000],
                "ts_utc": utcnow(),
            },
            replace=True,
        )

    # -- lifecycle ---------------------------------------------------------
    def _ensure_community(self, community: CommunityInput) -> Mapping[str, Any]:
        from .ids import community_id as make_community_id
        from .ids import safe_name

        existing = self.db.query_one(
            "SELECT * FROM communities WHERE name_input = ? AND provenance_mode = ?",
            (community.name, "FIXTURE" if community.fixture else "LIVE"))
        if existing:
            self.db.update("communities",
                           {"updated_utc": utcnow(),
                            "latitude": community.latitude, "longitude": community.longitude},
                           {"community_id": existing["community_id"]})
            return existing

        if community.assigned_id:
            identifier = community.assigned_id
        else:
            count = int(self.db.scalar("SELECT COUNT(*) FROM communities") or 0)
            identifier = make_community_id(count + 1, fixture=community.fixture)
        self.db.insert(
            "communities",
            {
                "community_id": identifier,
                "site_id": identifier,
                "name_input": community.name,
                "safe_name": safe_name(community.name),
                "latitude": community.latitude,
                "longitude": community.longitude,
                "country_hint": community.country,
                "mode": community.mode,
                "provenance_mode": "FIXTURE" if community.fixture else "LIVE",
                "created_utc": utcnow(),
                "updated_utc": utcnow(),
            },
        )
        return dict(self.db.query_one(
            "SELECT * FROM communities WHERE community_id = ?", (identifier,)))

    def _start_run(self, community: CommunityInput) -> str:
        count = int(self.db.scalar(
            "SELECT COUNT(*) FROM runs WHERE community_id = ?", (self.community_id,)) or 0)
        run_id = f"{self.community_id}-RUN{count + 1:03d}"
        from . import __version__
        from .config import sha256_file

        config_hash = sha256_file(self.settings.root / "config" / "config.yaml")
        self.db.insert(
            "runs",
            {
                "run_id": run_id,
                "community_id": self.community_id,
                "mode": self.run_mode,
                "target": self.target,
                "status": "running",
                "app_version": __version__,
                "config_hash": config_hash,
                "started_utc": utcnow(),
            },
        )
        self.db.update("communities", {"output_dir": str(self.storage.root)},
                       {"community_id": self.community_id})
        return run_id

    def _finish_run(self, run_id: str) -> RunOutcome:
        paused = self.final_state in ("PAUSED_MANUAL", "PAUSED_NETWORK")
        for stage in self.stages.values():
            if stage.status == "not_reached" and stage.number in MODE_STAGES.get(
                    self.run_mode, []):
                if paused or self.final_state == CONTROL_CANCELLED:
                    # The stage was not empty of evidence; it was never begun.
                    # Saying so is the difference between an honest partial run
                    # and a fabricated absence (brief §13, §37).
                    stage.detail = (f"never begun: the run stopped in "
                                    f"{self.final_state} before reaching this stage")
                    self._persist_stage(stage)
                    self._mark_truncated(
                        f"stage {stage.number} ({stage.name}) was never reached because "
                        f"the run stopped in {self.final_state}")
                else:
                    self._mark_truncated(
                        f"stage {stage.number} ({stage.name}) was never reached")

        truncated = bool(self.truncation_reasons)
        supervisor_stats = getattr(self.supervisor, "stats", None)
        control = self.control
        queue = self.frontier.counts_by_status() if self.frontier else {}
        outcome = RunOutcome(
            run_id=run_id,
            community_id=self.community_id,
            stages=self.stages,
            truncated=truncated,
            truncation_reasons=list(self.truncation_reasons),
            stats={
                **self.crawler.stats.as_dict(),
                "fetch": dict(self.fetcher.stats),
                "browser_renders": self.browser.pages_rendered,
                "llm_calls": getattr(self.llm, "calls", 0) if self.llm else 0,
                "image_triage": self.crawler.triage.summary(),
                "archive_urls_discovered": self.archive_discovered,
                "archive_urls_fetched": self.archive_fetched,
                "document_families": dict(self.document_families),
                "queue": queue,
            },
            review_items=len(self.review),
            final_state=self.final_state,
            pause_reason=self.pause_reason,
            pauses_manual=getattr(control, "pauses_manual", 0),
            pauses_network=getattr(control, "pauses_network", 0),
            offline_s=getattr(supervisor_stats, "offline_s", 0.0),
            paused_manual_s=getattr(supervisor_stats, "paused_manual_s", 0.0),
            queue=queue,
            budget_exhausted=self.budget_exhausted,
            budget=self.budget.snapshot().as_dict() if self.budget else {},
            profile={**(self.budget.profile() if self.budget else {}),
                     "activities": profiling.current().report()},
            yield_summary={**self.meter.snapshot(),
                           "curve": self.meter.curve()},
            retrieval_stop_cause=self.retrieval_stop_cause,
            archive_truncated=list(self.archive_truncated),
        )
        self.db.update(
            "runs",
            {"status": _RUN_STATUS[self.final_state],
             "final_state": self.final_state,
             "budget_exhausted": int(self.budget_exhausted),
             "retrieval_stop_cause": self.retrieval_stop_cause or None,
             "yield_units": round(self.meter.scope("run").units, 2),
             "active_elapsed_s": round(self.budget.active_s, 2) if self.budget else None,
             "truncated": int(truncated),
             "truncation_reason": "; ".join(self.truncation_reasons)[:2000],
             "finished_utc": utcnow(),
             "manifest_json": json.dumps(outcome.stats, ensure_ascii=False)},
            {"run_id": run_id},
        )
        if control is not None and self.final_state not in ("PAUSED_MANUAL",
                                                            "PAUSED_NETWORK",
                                                            CONTROL_CANCELLED):
            # A paused run keeps its pause state so it can be found and
            # resumed; only a run that truly ended is closed here.
            control.finish(self.final_state, self.pause_reason)
        return outcome


#: `runs.status` for each way a run can end. An interrupted run is never
#: `complete`: that distinction is the point of the state machine (brief §22).
_RUN_STATUS = {
    "COMPLETED": "complete",
    "PAUSED_MANUAL": "paused_manual",
    "PAUSED_NETWORK": "paused_network",
    "CANCELLED": "cancelled",
    "FAILED": "failed",
}


def _cell_ref(table: Any, row_index: int, col_index: int) -> str:
    letters = ""
    index = col_index + 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row_index + 1}"


#: Country name -> ccTLD, for domain guessing and the local-language sweep.
#: Keyed on the canonical English short names the master input file uses
#: (ISO 3166 English short name), so every country in the 212-community cohort
#: resolves rather than eighteen of them. An ISO alpha-2 code passed straight
#: through also works, because the master file carries `country_iso2` too.
_COUNTRY_CODES = {
    "france": "fr", "netherlands": "nl", "germany": "de", "spain": "es",
    "portugal": "pt", "italy": "it", "belgium": "be", "sweden": "se",
    "denmark": "dk", "norway": "no", "finland": "fi", "poland": "pl",
    "austria": "at", "switzerland": "ch", "united kingdom": "uk",
    "ireland": "ie", "iceland": "is", "greece": "gr", "slovenia": "si",
    "czechia": "cz", "czech republic": "cz", "romania": "ro", "hungary": "hu",
    "north macedonia": "mk", "ukraine": "ua", "russia": "ru",
    "russian federation": "ru", "turkey": "tr", "türkiye": "tr",
    "estonia": "ee", "latvia": "lv", "lithuania": "lt", "croatia": "hr",
    "serbia": "rs", "bulgaria": "bg", "slovakia": "sk", "luxembourg": "lu",
    "brazil": "br", "argentina": "ar", "chile": "cl", "colombia": "co",
    "peru": "pe", "ecuador": "ec", "bolivia": "bo", "uruguay": "uy",
    "paraguay": "py", "venezuela": "ve", "mexico": "mx", "guatemala": "gt",
    "belize": "bz", "costa rica": "cr", "panama": "pa", "nicaragua": "ni",
    "honduras": "hn", "el salvador": "sv", "cuba": "cu", "haiti": "ht",
    "dominican republic": "do", "trinidad and tobago": "tt", "jamaica": "jm",
    "united states": "us", "canada": "ca",
    "australia": "au", "new zealand": "nz",
    "india": "in", "nepal": "np", "sri lanka": "lk", "bangladesh": "bd",
    "pakistan": "pk", "bhutan": "bt", "china": "cn", "japan": "jp",
    "south korea": "kr", "thailand": "th", "vietnam": "vn", "cambodia": "kh",
    "laos": "la", "malaysia": "my", "singapore": "sg", "indonesia": "id",
    "philippines": "ph", "myanmar": "mm", "mongolia": "mn",
    "israel": "il", "palestine": "ps", "jordan": "jo", "lebanon": "lb",
    "iran": "ir", "iraq": "iq", "egypt": "eg", "morocco": "ma",
    "tunisia": "tn", "algeria": "dz", "united arab emirates": "ae",
    "saudi arabia": "sa", "georgia": "ge", "armenia": "am",
    "south africa": "za", "kenya": "ke", "tanzania": "tz", "uganda": "ug",
    "zimbabwe": "zw", "zambia": "zm", "malawi": "mw", "mozambique": "mz",
    "botswana": "bw", "namibia": "na", "eswatini": "sz", "lesotho": "ls",
    "ghana": "gh", "nigeria": "ng", "senegal": "sn", "gambia": "gm",
    "mali": "ml", "burkina faso": "bf", "benin": "bj", "togo": "tg",
    "ivory coast": "ci", "côte d'ivoire": "ci", "cameroon": "cm",
    "ethiopia": "et", "rwanda": "rw", "burundi": "bi", "madagascar": "mg",
    "sierra leone": "sl", "liberia": "lr", "guinea": "gn",
    "democratic republic of the congo": "cd", "sudan": "sd",
}


def _country_code(country: str | None) -> str | None:
    """ccTLD for a country name, or for an ISO alpha-2 code passed straight in."""
    text = (country or "").strip().lower()
    if not text:
        return None
    if len(text) == 2 and text.isalpha():
        return text
    return _COUNTRY_CODES.get(text)


def _funding_is_environmental(record: Any) -> bool:
    haystack = " ".join([
        getattr(record, "title", ""), getattr(record, "summary", ""),
    ]).lower()
    markers = ("restor", "planting", "reforest", "biodivers", "agroecolog", "wetland",
               "erosion", "soil", "water", "habitat", "landscape", "afforest", "riparian")
    return any(marker in haystack for marker in markers)


def _decision_parameter(decisions: Mapping[str, Any], decision_id: str, key: str,
                        default: Any) -> Any:
    for entry in decisions.get("decisions", []):
        if entry.get("id") == decision_id:
            return (entry.get("parameters") or {}).get(key, default)
    return default
