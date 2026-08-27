"""Platform detection and per-platform enumeration rules.

`sitemap.xml` and forty URL paths are *website* instructions and do nothing on
Instagram (register v2.4). Each platform gets its own method, and a platform
that refuses automated reading is recorded as blocked rather than guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .normalize import normalize, registrable_domain

# Platforms known to refuse automated reading. They are still ATTEMPTED — the
# refusal has to be observed, not assumed — but a refusal is expected and is
# recorded as `blocked`, never as "no content".
LOGIN_WALLED = {"Facebook", "Instagram", "LinkedIn"}

# Which source class each platform maps onto (register's S1-S8).
PLATFORM_SOURCE_CLASS = {
    "own website": "S4",
    "secondary or former website": "S4",
    "Facebook": "S7",
    "Instagram": "S7",
    "YouTube": "S7",
    "Vimeo": "S7",
    "blog platform": "S4",
    "directory listing": "S3",
    "crowdfunding": "S3",
    "LinkedIn": "S7",
    "booking or hosting": "S3",
    "news outlet": "S6",
    "other": "S4",
}

# Retrieval priority (brief §53) — how much crawl effort a source earns.
# This is NOT the research evidence rank (brief §54).
RETRIEVAL_PRIORITY = {
    "secondary or former website": "A",   # old domains hold the oldest material
    "crowdfunding": "A",                  # dated, specific, with budgets and photographs
    "own website": "B",
    "blog platform": "B",
    "news outlet": "B",
    "booking or hosting": "B",
    "directory listing": "C",
    "YouTube": "C",
    "Vimeo": "C",
    "Facebook": "C",
    "Instagram": "C",
    "LinkedIn": "C",
    "other": "C",
}


@dataclass
class PlatformProfile:
    platform_type: str
    source_class: str
    retrieval_priority: str
    login_walled: bool
    seed_paths: list[str] = field(default_factory=list)
    notes: str = ""


def detect_platform(url: str, patterns: dict[str, list[str]]) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return "other"
    for platform, needles in patterns.items():
        for needle in needles:
            if needle.lower() in host:
                return platform
    return "own website"


def profile_for(url: str, platform_type: str, endpoints: dict[str, list[str]]) -> PlatformProfile:
    """The enumeration plan for one address."""
    parts = urlsplit(url)
    root = f"{parts.scheme}://{parts.netloc}"
    seeds: list[str] = []
    notes = ""

    if platform_type == "YouTube":
        channel = _youtube_channel_root(url) or root
        seeds = [f"{channel}{p}" for p in endpoints.get("youtube_channel_paths", [])]
        notes = "Channel videos sorted oldest first; upload dates are dated records."
    elif platform_type == "Vimeo":
        seeds = [url, url.rstrip("/") + "/videos"]
        notes = "Upload dates are dated records; descriptions carry project names."
    elif platform_type == "Facebook":
        base = url.rstrip("/")
        seeds = [base] + [base + p for p in endpoints.get("facebook_public_paths", [])]
        notes = "About tab, albums and events are the dated parts. Expect a login wall."
    elif platform_type == "Instagram":
        seeds = [url]
        notes = "Bio and bio link only. Feed position is never a date (rule 12)."
    elif platform_type == "LinkedIn":
        base = url.rstrip("/")
        seeds = [base] + [base + p for p in endpoints.get("linkedin_public_paths", [])]
        notes = "Organisation page carries a founded year."
    elif platform_type in ("directory listing", "crowdfunding", "booking or hosting", "news outlet"):
        seeds = [url]
        notes = "Structured fields; self-submitted text shares the community's independence group."
    else:
        seeds = [url]

    return PlatformProfile(
        platform_type=platform_type,
        source_class=PLATFORM_SOURCE_CLASS.get(platform_type, "S4"),
        retrieval_priority=RETRIEVAL_PRIORITY.get(platform_type, "C"),
        login_walled=platform_type in LOGIN_WALLED,
        seed_paths=[s for s in (normalize(x) for x in seeds) if s],
        notes=notes,
    )


def _youtube_channel_root(url: str) -> str | None:
    match = re.search(r"(https?://[^/]+/(?:@[\w.-]+|channel/[\w-]+|c/[\w.-]+|user/[\w.-]+))", url)
    return match.group(1) if match else None


def is_website_like(platform_type: str) -> bool:
    """Whether the full website protocol (sitemap, paths, deep crawl) applies."""
    return platform_type in {
        "own website", "secondary or former website", "blog platform", "other",
    }


def default_source_class(url: str, platform_type: str) -> str:
    """Refine the class where the URL itself says more than the platform does."""
    host = (urlsplit(url).hostname or "").lower()
    domain = registrable_domain(host)
    academic_markers = (".edu", "ac.uk", "univ-", "university", "repositor", "thesis", "theses",
                        "dspace", "eprints", "hal.", "arxiv", "doi.org", "scielo", "core.ac.uk",
                        "openaire", "dart-europe", "oatd", "diva-portal", "rcaap", "dialnet")
    institutional_markers = (".gov", "gouv.", "gov.", "europa.eu", "cordis", ".int",
                             "overheid.nl", "rijksoverheid", "prefecture", "municipal",
                             "commune", "gemeente", "ayuntamiento", "camara", "registre",
                             "kvk.nl", "cadastre", "kadaster")
    if any(marker in host for marker in academic_markers):
        return "S1"
    if any(marker in host or marker in domain for marker in institutional_markers):
        return "S2"
    return PLATFORM_SOURCE_CLASS.get(platform_type, "S4")
