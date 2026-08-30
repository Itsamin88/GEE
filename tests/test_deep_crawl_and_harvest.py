"""The two capabilities the master file's crawl policy is supposed to buy.

**Walking a site in full.** A directory listing is one page about a community
and the right thing to do with it is read it and follow what it points at. The
community's own site is a different object: the gallery, the newsletter archive
going back fifteen years, the annual reports as PDFs, the land-use plan nobody
linked from the front page. Sampling the second the way you sample the first
loses exactly the material a documentary study exists to find. So an address
the master file names in `deep_crawl_urls` gets a different budget, a deeper
depth ceiling and a larger image allowance - and these tests check that the
difference is real, not decorative.

**Harvesting the whole literature.** Every academic database used to be asked
once, for fifty rows. For a community with six papers that is the literature;
for Tamera, Damanhur or Cloughjordan, each discussed in hundreds of works, it
returned whichever fifty an API ranked first and looked exactly like a complete
answer. That is the failure register v2.4 field I12 exists to name: absence of
effort presented as absence of evidence. These tests check the harvest pages
until a database runs out, and stops for the right reason when it does.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from dcr.crawl.crawler import SourceContext
from dcr.crawl.frontier import SourceBudget
from dcr.discovery import academic, grey


def _budget(scope: str, **kw) -> SourceBudget:
    return SourceBudget("S1", base=kw.pop("base", 40), maximum=kw.pop("maximum", 400),
                        scope=scope, **kw)


def _context(scope: str, **kw) -> SourceContext:
    kw.setdefault("follow_links", scope == "site")
    return SourceContext(
        source_id="S1", url="https://example.org/", platform_type="own website",
        source_class="S4", retrieval_priority="B", independence_group="G1",
        login_walled=False, budget=_budget(scope), crawl_scope=scope, **kw)


# ---------------------------------------------------------------------------
# Walking a site in full
# ---------------------------------------------------------------------------
def test_an_exhaustive_source_is_not_abandoned_for_a_quiet_stretch():
    """A barren run of pages is not proof a community site is finished.

    A newsletter archive can be forty pages of links before the first PDF. The
    targeted window would call that exhausted and walk away from the archive.
    """
    targeted = _budget("page")
    exhaustive = _budget("site")
    assert exhaustive.exhaustion_window > targeted.exhaustion_window * 5
    assert exhaustive.dead_source_window > targeted.dead_source_window


def test_an_exhaustive_source_still_stops():
    """Widened, not removed: coverage is the goal, not an unbounded crawl."""
    exhaustive = _budget("site")
    assert exhaustive.exhaustion_window < 10_000
    assert exhaustive.maximum > 0


def test_the_scope_is_recorded_on_the_source_not_inferred():
    """The researcher's file decides which sites are the community's own.

    Not the platform type: a community may hold three domains, and a directory
    listing can sit on the same host as something unrelated.
    """
    assert _context("site").exhaustive is True
    assert _context("page").exhaustive is False
    assert _context("file").exhaustive is False


def test_only_the_communitys_own_site_follows_links():
    """The rule that keeps 212 communities inside two days.

    A news article about a community is one useful page on a site with fifty
    thousand useless ones. Following its links would spend hours to learn
    nothing, so `page` and `file` take what is on the page and stop.
    """
    assert _context("site").follow_links is True
    assert _context("page").follow_links is False
    assert _context("file").follow_links is False


def test_the_three_scopes_differ_in_the_way_that_matters():
    """Naming three scopes buys nothing unless they behave differently."""
    import yaml
    from pathlib import Path

    scopes = yaml.safe_load(
        Path("config/config.yaml").read_text(encoding="utf-8"))["crawl"]["scopes"]
    site, page, one_file = scopes["site"], scopes["page"], scopes["file"]

    # The community's own site is walked; nobody else's is.
    assert site["follow_links"] is True
    assert page["follow_links"] is False
    assert one_file["follow_links"] is False

    # Exactly one page is fetched from somebody else's site.
    assert page["max_pages_per_source"] == 1
    assert one_file["max_pages_per_source"] == 1
    assert page["max_depth"] == 0

    assert site["max_pages_per_source"] > page["max_pages_per_source"] * 100
    assert site["max_depth"] > page["max_depth"]

    # But every scope still takes the assets on the page it did fetch - a
    # directory listing's linked annual report is exactly what is wanted.
    assert all(s["asset_download"] == "all" for s in (site, page, one_file))


def test_the_run_wide_page_ceiling_can_hold_an_exhaustive_walk():
    """A large per-source budget is a lie if the run-wide ceiling is smaller."""
    import yaml
    from pathlib import Path

    cfg = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))["crawl"]
    assert cfg["max_pages_per_run"] >= cfg["scopes"]["site"]["max_pages_per_source"]


# ---------------------------------------------------------------------------
# Harvesting the whole literature
# ---------------------------------------------------------------------------
OPENALEX = {"id": "openalex", "access": "api",
            "endpoint": "https://api.openalex.org/works"}
CROSSREF = {"id": "crossref", "access": "api",
            "endpoint": "https://api.crossref.org/works"}
SCIELO = {"id": "scielo", "access": "html", "endpoint": "https://search.scielo.org/"}


def test_page_zero_is_the_request_that_was_always_made():
    """Paging is additive: the first window is unchanged, so nothing regresses."""
    before = academic.request_for(OPENALEX, "Tamera", rows=100, api_key=None)
    after = academic.request_for(OPENALEX, "Tamera", rows=100, api_key=None, page=0)
    assert before == after
    # Checked on the parsed keys, not as a substring: OpenAlex's own page-size
    # parameter is spelled "per-page", and a substring test matches that.
    assert "page" not in parse_qs(urlsplit(after[0]).query)


@pytest.mark.parametrize("db,param,page,expected", [
    (OPENALEX, "page", 1, "2"),           # 1-based page number
    (OPENALEX, "page", 4, "5"),
    (CROSSREF, "offset", 1, "100"),       # 0-based record offset
    (CROSSREF, "offset", 3, "300"),
])
def test_each_database_is_paged_in_its_own_units(db, param, page, expected):
    """Page numbers and record offsets are not interchangeable.

    Sending a page number where an API wants an offset silently returns the
    first hundred records over and over, which reads as "the database is
    exhausted" when nothing has been read at all.
    """
    url, _ = academic.request_for(db, "Tamera", rows=100, api_key=None, page=page)
    assert parse_qs(urlsplit(url).query)[param] == [expected]


def test_a_database_that_cannot_be_paged_says_so():
    """The caller asks first, so it does not fetch the same page twenty times."""
    assert academic.supports_paging(OPENALEX) is True
    assert academic.supports_paging(SCIELO) is False
    assert academic.request_for(SCIELO, "Tamera", rows=50, api_key=None, page=2) is None


def test_every_api_database_in_the_configured_set_can_be_paged():
    """A database that cannot page is a hole in 'every paper that mentions it'.

    This is the test that fails when someone adds an API to sources.yaml and
    forgets the paging entry - the harvest would silently cap at one window for
    that database and report nothing missing.
    """
    import yaml
    from pathlib import Path

    sources = yaml.safe_load(Path("config/sources.yaml").read_text(encoding="utf-8"))
    # BOTH lists the runner actually searches: the core databases, and the
    # national thesis portals it adds for the community's own country. The
    # second is where a country-specific thesis actually lives, so leaving it
    # out of this check would miss exactly the databases that matter most for a
    # non-English community.
    apis = [d for d in sources["academic_databases"] if d.get("access") == "api"]
    apis += [d for portals in sources["national_thesis_portals"].values()
             for d in portals if d.get("access") == "api"]
    assert len(apis) >= 15, "the fixture is meaningless if the set has shrunk"
    unpaged = sorted({d["id"] for d in apis if not academic.supports_paging(d)})
    assert not unpaged, f"academic APIs with no paging rule: {unpaged}"


def test_grey_paging_matches_the_same_shape():
    assert grey.supports_paging({"id": "openaire_projects"}) is True
    assert grey.supports_paging({"id": "openstreetmap_nominatim"}) is False
    url, _ = grey.request_for(
        {"id": "openaire_projects", "access": "api",
         "endpoint": "https://api.openaire.eu/search/projects"},
        "Tamera", rows=100, api_key=None, page=2)
    assert parse_qs(urlsplit(url).query)["page"] == ["3"]


def test_a_registry_is_not_paged():
    """A company register returns one match for one name.

    Paging it is noise, not coverage, and it costs requests that the literature
    databases need.
    """
    for db_id in ("openstreetmap_nominatim",):
        assert not grey.supports_paging({"id": db_id})


def test_the_harvest_is_configured_to_go_deeper_than_one_window():
    import yaml
    from pathlib import Path

    cfg = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))
    assert cfg["academic"]["max_pages_per_database"] > 1
    assert cfg["academic"]["stop_after_barren_pages"] >= 1
    reachable = (cfg["academic"]["max_results_per_database"]
                 * cfg["academic"]["max_pages_per_database"])
    assert reachable >= 1000, "Tamera and Findhorn have hundreds of papers each"


# ---------------------------------------------------------------------------
# Shared politeness across worker processes
# ---------------------------------------------------------------------------
def test_the_host_broker_class_can_survive_spawn():
    """The manager class must be importable by name, or Windows loses politeness.

    `multiprocessing` on Windows starts its manager with `spawn`, which
    re-imports the module and looks the class up by qualified name. A class
    defined inside a method is `RunSession._start_broker.<locals>._BrokerManager`
    and no import can resolve that, so the manager failed to start and every run
    fell back to per-worker politeness — silently, because that fallback is
    deliberately non-fatal.

    It matters most where it is least visible: `https://ecovillage.org` is a
    seed on all 212 rows of the cohort, so with no shared broker sixteen workers
    hit one host at once.
    """
    import pickle

    from dcr.orchestrator.session import _BrokerManager

    assert "<locals>" not in _BrokerManager.__qualname__
    assert pickle.loads(pickle.dumps(_BrokerManager)) is _BrokerManager


def test_the_shared_broker_actually_starts():
    """Not just picklable — it has to serve a working proxy."""
    from dcr.orchestrator.hosts import HostBroker
    from dcr.orchestrator.session import _BrokerManager

    _BrokerManager.register(
        "HostBroker", HostBroker,
        exposed=("acquire", "release", "defer", "shared", "snapshot", "stats"))
    manager = _BrokerManager()
    manager.start()
    try:
        broker = manager.HostBroker(config={})
        assert isinstance(broker.snapshot(), list)
    finally:
        manager.shutdown()
