"""A community as rich and as awkward as the one that broke the crawler.

Modelled on the reported Tamera run: hundreds of pages, thousands of archived
URLs, dozens of PDFs including the same report in three languages, hundreds of
embedded images, and extracted text carrying the control bytes that killed the
export.

Everything here is a SOFTWARE TEST FIXTURE. It is served from localhost, its
identifiers are prefixed TEST-, and none of its content is research evidence.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import content as C

HOST = "stress.test"

#: Roughly the shape the reported run met.
PAGE_COUNT = 420
ARCHIVE_URL_COUNT = 5000
IMAGES_PER_GALLERY_PAGE = 24
EMBEDDED_IMAGES_PER_PDF = 60

#: Text that used to take the export down. Control bytes in the middle of
#: otherwise perfectly good extracted sentences, exactly as a broken PDF gives
#: them.
DIRTY_SENTENCES = [
    "We manage 134\x00 hectares of land at the site.",
    "In 2007 we built the first water\x0bretention basin.",
    "The community had 170 residents in 2019.\x0c",
    "Reforestation began in\x1b 2010 across the southern slopes.",
    "Our food forest covers 12 hectares.\x07",
]

RESEARCH_PATHS = [
    "/history", "/ecology", "/water-retention-landscape", "/restoration",
    "/land", "/projects", "/reports", "/research", "/permaculture",
]
NOISE_PATHS = [
    "/basket", "/checkout", "/contact", "/newsletter-signup", "/privacy",
    "/terms", "/events", "/donate", "/shop", "/press",
]


def _page(title: str, body: str, links: list[str], images: int = 0) -> str:
    link_html = "".join(f'<li><a href="{href}">{href.strip("/") or "home"}</a></li>'
                        for href in links)
    image_html = "".join(
        f'<figure><img src="/img/gallery-{i}.png" alt="gallery photo {i}" '
        f'width="900" height="600"><figcaption>Community life, photo {i}'
        f'</figcaption></figure>'
        for i in range(images)
    )
    return (f"<html><head><title>{title}</title></head><body>"
            f"<h1>{title}</h1><p>{body}</p><ul>{link_html}</ul>{image_html}"
            f"</body></html>")


def _research_figure() -> str:
    """One genuinely evidence-bearing image among the gallery noise."""
    return ('<figure><img src="/img/site-plan-2011.png" alt="Site plan" '
            'width="1600" height="1200">'
            "<figcaption>Site plan of the water retention landscape, 2011. "
            "We dug the first retention basin in 2007.</figcaption></figure>")


def build_stress_site() -> dict[str, Any]:
    """host -> path -> (status, content-type, body), for one very rich site."""
    from .server import _binary, _html, _xml

    gallery_png = C.make_png(900, 600, (80, 130, 80))
    plan_png = C.make_png(1600, 1200, (205, 200, 185))

    # A report published in three languages: one report, three files.
    report_lines = [
        "Tamera Test Site — Annual Report 2019",
        "",
        DIRTY_SENTENCES[0],
        DIRTY_SENTENCES[2],
        "The water retention landscape was extended in 2011.",
    ]
    annual_en = C.make_pdf(report_lines, title="Annual Report 2019")
    annual_de = C.make_pdf(["Jahresbericht 2019"] + report_lines[2:],
                           title="Jahresbericht 2019")
    annual_pt = C.make_pdf(["Relatorio Anual 2019"] + report_lines[2:],
                           title="Relatorio Anual 2019")
    thesis = C.make_pdf(
        ["Water retention landscapes: a thesis", "",
         DIRTY_SENTENCES[1], DIRTY_SENTENCES[3], DIRTY_SENTENCES[4]],
        title="Thesis on water retention")
    flyer = C.make_pdf(["Summer Festival 2019", "Music, food and workshops."],
                       title="Summer festival flyer")

    site: dict[str, Any] = {}
    all_paths = []
    for index in range(PAGE_COUNT):
        if index < len(RESEARCH_PATHS):
            path = RESEARCH_PATHS[index]
        elif index < len(RESEARCH_PATHS) + len(NOISE_PATHS):
            path = NOISE_PATHS[index - len(RESEARCH_PATHS)]
        else:
            path = f"/tag/page-{index}"
        all_paths.append(path)

    for index, path in enumerate(all_paths):
        research = path in RESEARCH_PATHS
        body = (DIRTY_SENTENCES[index % len(DIRTY_SENTENCES)] if research
                else "Upcoming events and general information.")
        links = all_paths[max(0, index - 3): index + 4]
        if research:
            links = links + ["/docs/annual-report-2019-en.pdf",
                             "/docs/jahresbericht-2019-de.pdf",
                             "/docs/relatorio-anual-2019-pt.pdf",
                             "/docs/water-thesis-2014.pdf",
                             "/docs/summer-festival-flyer.pdf"]
        page_html = _page(path.strip("/") or "Home", body, links,
                          images=IMAGES_PER_GALLERY_PAGE if research else 2)
        if research:
            # A site plan, sitting where it usually sits: in the middle of a
            # gallery of photographs that are not evidence of anything.
            page_html = page_html.replace("</body>", _research_figure() + "</body>")
        site[path] = _html(page_html)

    site["/"] = site.get("/history", _html(_page("Home", "Welcome", all_paths[:20])))
    site["/robots.txt"] = (200, "text/plain", b"User-agent: *\nAllow: /\n"
                                              b"Sitemap: http://stress.test/sitemap.xml\n")
    urls = "".join(f"<url><loc>http://stress.test{p}</loc></url>" for p in all_paths)
    site["/sitemap.xml"] = _xml(
        f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>")

    site["/docs/annual-report-2019-en.pdf"] = _binary(annual_en, "application/pdf")
    site["/docs/jahresbericht-2019-de.pdf"] = _binary(annual_de, "application/pdf")
    site["/docs/relatorio-anual-2019-pt.pdf"] = _binary(annual_pt, "application/pdf")
    site["/docs/water-thesis-2014.pdf"] = _binary(thesis, "application/pdf")
    site["/docs/summer-festival-flyer.pdf"] = _binary(flyer, "application/pdf")
    for i in range(IMAGES_PER_GALLERY_PAGE + 4):
        site[f"/img/gallery-{i}.png"] = _binary(gallery_png, "image/png")
    site["/img/site-plan-2011.png"] = _binary(plan_png, "image/png")
    return {HOST: site}


def build_stress_archive() -> list[list[str]]:
    """A CDX listing the size of the one the reported run met."""
    rows: list[list[str]] = [
        ["original", "timestamp", "mimetype", "statuscode", "digest"]
    ]
    paths = RESEARCH_PATHS + NOISE_PATHS + [f"/tag/page-{i}" for i in range(80)]
    for index in range(ARCHIVE_URL_COUNT):
        path = paths[index % len(paths)]
        year = 2004 + (index % 20)
        rows.append([
            f"http://{HOST}{path}",
            f"{year}{(index % 12) + 1:02d}15120000",
            "text/html", "200", f"D{index:06d}",
        ])
    return rows


def stress_urls(port: int) -> list[str]:
    return [f"http://{HOST}:{port}/"]
