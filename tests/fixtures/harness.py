"""Wire the application to the local fixture web.

Only the *endpoints* are redirected. The crawler, the extractors, the evidence
model, the exporter and the quality checks are the production ones, so a fixture
run exercises the real pipeline end to end.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from dcr.config import Settings, load_settings


def fixture_settings(port: int, output_root: Path, *, root: Path | None = None) -> Settings:
    settings = load_settings(root)
    settings.app = copy.deepcopy(settings.app)
    settings.sources = copy.deepcopy(settings.sources)

    settings.app["paths"]["output_root"] = str(output_root)
    settings.app["paths"]["database"] = str(output_root / "dcr.sqlite3")
    # A fixture on localhost needs no politeness delay, and the run should be quick.
    settings.app["network"]["default_delay_per_host_s"] = 0.0
    settings.app["network"]["max_concurrency_per_host"] = 4
    settings.app["retry"]["max_attempts"] = 2
    settings.app["retry"]["backoff_base_s"] = 0.05
    settings.app["crawl"]["base_pages_per_source"] = 60
    settings.app["crawl"]["max_pages_per_run"] = 400
    settings.app["browser"]["enabled"] = "never"
    settings.app["llm"]["enabled"] = "never"
    settings.app["quality"]["min_pages_opened"] = 10

    base = f"http://archive.test:{port}"
    settings.sources["archive"] = {
        "cdx_endpoint": f"{base}/cdx",
        "cdx_params": {"fl": "original,timestamp,mimetype,statuscode,digest",
                       "collapse": "urlkey", "limit": 500},
        "snapshot_url_template": base + "/web/{timestamp}/{url}",
        "priority_snapshot_paths": ["/", "/histoire", "/about", "/geschiedenis"],
    }
    settings.sources["academic_databases"] = [
        {"id": "openalex", "name": "OpenAlex (fixture)", "access": "api",
         "endpoint": f"http://theses.test:{port}/api/works", "type": "academic",
         "needs_key": False},
        {"id": "google_scholar", "name": "Google Scholar", "access": "manual",
         "type": "academic", "needs_key": False,
         "note": "blocks automated access; recorded as unreachable, never as zero hits"},
        {"id": "core", "name": "CORE", "access": "api", "endpoint": "http://theses.test/none",
         "type": "academic", "needs_key": True, "key_env": "CORE_API_KEY"},
    ]
    settings.sources["national_thesis_portals"] = {
        "France": [{"id": "theses_fr", "name": "theses.fr (fixture)", "access": "api",
                    "endpoint": f"http://theses.test:{port}/api/works"}],
        "default": [{"id": "theses_fr", "name": "theses.fr (fixture)", "access": "api",
                     "endpoint": f"http://theses.test:{port}/api/works"}],
    }
    settings.sources["grey_databases"] = [
        {"id": "cordis", "name": "CORDIS (EU research projects)", "access": "html",
         "type": "grey - funding", "endpoint": "http://unavailable.test/"},
    ]
    patterns = settings.sources.setdefault("platform_patterns", {})
    patterns.setdefault("Facebook", []).append("facebook.test")
    patterns.setdefault("directory listing", []).append("annuaire.test")
    patterns.setdefault("secondary or former website", []).extend(
        ["ancien-pourgues.test", "oud-boekel.test"])

    settings.sources["search_engines"] = [
        {"id": "duckduckgo_html", "name": "DuckDuckGo HTML (fixture)", "access": "html",
         "endpoint": f"http://theses.test:{port}/api/search", "needs_key": False},
    ]
    return settings


def fixture_urls(port: int, community: str) -> list[str]:
    if community == "pourgues":
        return [
            f"http://pourgues.test:{port}/",
            f"http://facebook.test:{port}/pourgues",
        ]
    return [f"http://boekel.test:{port}/"]
