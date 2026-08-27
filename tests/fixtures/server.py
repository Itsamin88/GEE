"""A local multi-host web fixture.

It serves the two pilot communities as a small realistic web: a current site
with a sitemap and a feed, an abandoned domain, a directory listing that copied
the site's text, a login-walled social platform, an archive CDX index with
snapshots, and an academic API with a verifiable DOI record.

Every host resolves to 127.0.0.1 (see the hosts entries the pilot script adds),
so the crawler's scope, independence and archive logic are all exercised for
real without touching the live web.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from . import content as C

Route = tuple[int, str, bytes]      # status, content-type, body

# The fixture binds an ephemeral port, but the content is written port-free so
# it stays readable. Every textual body is rewritten on the way out so that
# `pourgues.test/x` becomes `pourgues.test:PORT/x` — otherwise every sitemap
# entry, feed link and API URL would point at port 80 and the crawl would
# collapse to the seed pages alone.
_HOSTNAME = re.compile(r"\b([a-z][a-z0-9-]*\.test)(?=[/\"'\\s<>?]|$)")
_REWRITABLE = ("text/", "application/xml", "application/json", "application/rss")


def _with_port(body: bytes, mime: str, port: int) -> bytes:
    if not any(mime.startswith(prefix) for prefix in _REWRITABLE):
        return body
    text = body.decode("utf-8", "replace")
    text = _HOSTNAME.sub(lambda m: f"{m.group(1)}:{port}", text)
    return text.encode("utf-8")


def _html(body: str, status: int = 200) -> Route:
    return status, "text/html; charset=utf-8", body.encode("utf-8")


def _xml(body: str) -> Route:
    return 200, "application/xml; charset=utf-8", body.encode("utf-8")


def _json(payload: Any) -> Route:
    return 200, "application/json", json.dumps(payload).encode("utf-8")


def _binary(data: bytes, mime: str) -> Route:
    return 200, mime, data


def build_sites() -> dict[str, dict[str, Route]]:
    """host -> path -> (status, content-type, body)."""
    plan_png = C.make_png(1400, 1000, (200, 195, 180))
    forest_png = C.make_png(1400, 1000, (70, 130, 70))
    landuse_png = C.make_png(1200, 900, (190, 180, 160))
    logo_png = C.make_png(180, 60, (30, 30, 30))
    boekel_plan = C.make_png(1300, 950, (205, 200, 185))

    annual_report = C.make_pdf(
        [
            "EcoVillage de Pourgues — Rapport annuel 2019",
            "",
            "Surface: nous cultivons 4,2 hectares en maraichage biologique.",
            "Le domaine total est de 55 hectares.",
            "La foret-jardin plantee en 2016 couvre 1,8 hectare.",
            "En 2017 nous avons creuse 400 metres de baissieres sur courbe de niveau.",
            "Le paillage permanent est applique sur toutes les planches depuis 2018.",
            "Nous sommes 34 habitants permanents en 2019.",
            "Certification Ecocert obtenue en 2018.",
        ],
        title="Rapport annuel 2019",
    )
    bulletin_2016 = C.make_pdf(
        [
            "Pourgues — Bulletin 2016",
            "",
            "Nous avons plante 3000 arbres en mars 2016 sur 1,8 hectare.",
            "Nous cultivons 2 hectares en maraichage.",
            "Le terrain de 55 hectares a ete achete en 2015.",
        ],
        title="Bulletin 2016",
    )
    thesis_pdf = C.make_pdf(
        [
            "Agroecological transition at EcoVillage de Pourgues",
            "Master's thesis, Universite de Toulouse, 2020",
            "",
            "Site description. The community manages 4.2 hectares of cultivated land",
            "within a 55 hectare holding in the Ariege department.",
            "Methods. The author observed no-till cultivation across the entire cropped",
            "area during two field seasons in 2019 and 2020.",
            "The food forest was established in 2016 and now covers 1.8 hectares.",
            "Swales were constructed in 2017 on the southern slope.",
            "Results. Permanent mulching is applied on all beds.",
        ],
        title="Agroecological transition at EcoVillage de Pourgues",
    )
    permit_pdf = C.make_pdf(
        [
            "Gemeente Boekel — Omgevingsvergunning 2016",
            "",
            "Aanvrager: Stichting Ecodorp Boekel",
            "De wadi voor waterberging is in 2016 aangelegd.",
            "Het terrein beslaat 1,5 hectare, waarvan 0,8 hectare in cultuur.",
        ],
        title="Omgevingsvergunning 2016",
    )
    inventory_xlsx = C.make_xlsx({
        "Plantations": [
            ["annee", "espece", "nombre", "surface_ha"],
            [2016, "pommier", 400, 0.6],
            [2016, "noisetier", 1200, 0.7],
            [2019, "chataignier", 500, 0.5],
        ],
        "Interne": [["note", "surface_totale_ha"], ["foret-jardin", 1.8]],
    })
    management_docx = C.make_docx(
        [
            "Le plan de gestion couvre 4 hectares en culture et 55 hectares au total.",
            "Les haies bocageres sont plantees depuis 2018 en bordure des parcelles.",
            "La restauration de la prairie humide a commence en 2017.",
        ],
        headings=["Plan de gestion 2018"],
    )
    project_zip = C.make_zip({
        "note-projet-2017.txt":
            "Projet 2017: creation d'une mare et restauration de la prairie humide.\n"
            "Financement LEADER accorde en 2017.".encode("utf-8"),
    })

    pourgues_pages = {
        "/": _html(C.POURGUES_HOME),
        "/histoire": _html(C.POURGUES_HISTORY),
        "/le-lieu": _html(C.POURGUES_LAND),
        "/projets": _html(C.POURGUES_PROJECTS),
        "/documents": _html(C.POURGUES_DOCUMENTS),
        "/blog": _html(C.POURGUES_BLOG),
        "/blog/2016/plantation": _html(C.POURGUES_BLOG_2016),
        "/blog/2017/baissieres": _html(C.POURGUES_BLOG_2017),
        "/blog/2021/bilan": _html(C.POURGUES_BLOG_2021),
        "/robots.txt": (200, "text/plain",
                        b"User-agent: *\nDisallow: /prive/\nCrawl-delay: 0\n"
                        b"Sitemap: http://pourgues.test/sitemap.xml\n"),
        "/sitemap.xml": _xml(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(
                f"<url><loc>http://pourgues.test{path}</loc><lastmod>{mod}</lastmod></url>"
                for path, mod in (
                    ("/", "2023-05-04"), ("/histoire", "2021-03-11"), ("/le-lieu", "2022-09-01"),
                    ("/projets", "2020-06-15"), ("/documents", "2020-01-20"),
                    ("/blog/2016/plantation", "2016-03-22"),
                    ("/blog/2017/baissieres", "2017-10-02"),
                    ("/blog/2021/bilan", "2021-11-30"),
                    ("/docs/rapport-annuel-2019.pdf", "2020-02-01"),
                    ("/pages-orphelines/chantier-eau-2017", "2017-11-01"),
                )
            )
            + "</urlset>"
        ),
        # Linked from nowhere: only the sitemap reaches it.
        "/pages-orphelines/chantier-eau-2017": _html(C.page(
            "Chantier eau 2017",
            "<h1>Chantier eau 2017</h1><p>En 2017 nous avons construit une mare de 300 m2 "
            "et restaure la prairie humide attenante.</p>",
            published="2017-11-01")),
        "/feed": _xml(
            "<rss version='2.0'><channel><title>Pourgues</title>"
            "<item><title>Plantation de la foret-jardin</title>"
            "<link>http://pourgues.test/blog/2016/plantation</link>"
            "<pubDate>Tue, 22 Mar 2016 09:00:00 +0000</pubDate>"
            "<description>3000 arbres plantes</description></item>"
            "<item><title>Chantier baissieres</title>"
            "<link>http://pourgues.test/blog/2017/baissieres</link>"
            "<pubDate>Mon, 02 Oct 2017 09:00:00 +0000</pubDate>"
            "<description>400 metres de baissieres</description></item>"
            "</channel></rss>"),
        "/prive/secret": _html("<html><body>private</body></html>"),
        "/docs/rapport-annuel-2019.pdf": _binary(annual_report, "application/pdf"),
        "/docs/inventaire-plantations.xlsx": _binary(
            inventory_xlsx,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "/docs/plan-de-gestion-2018.docx": _binary(
            management_docx,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "/docs/dossier-2017.zip": _binary(project_zip, "application/zip"),
        # A PDF served with a lying Content-Type, to exercise MIME sniffing.
        "/docs/mystere": _binary(annual_report, "text/html"),
        "/img/logo-header.png": _binary(logo_png, "image/png"),
        "/img/plan-de-masse-2016.png": _binary(plan_png, "image/png"),
        "/img/foret-jardin-2019.png": _binary(forest_png, "image/png"),
        "/img/carte-usage-des-sols.png": _binary(landuse_png, "image/png"),
        # A corrupt PDF, to prove a bad file is recorded rather than crashing a run.
        "/docs/corrompu.pdf": _binary(b"%PDF-1.4\nthis file is truncated", "application/pdf"),
    }

    ancien_pages = {
        "/": _html(C.ANCIEN_HOME),
        "/robots.txt": (200, "text/plain", b"User-agent: *\nAllow: /\n"),
        "/docs/bulletin-2016.pdf": _binary(bulletin_2016, "application/pdf"),
    }

    annuaire_pages = {
        "/lieux/pourgues": _html(C.ANNUAIRE_LISTING),
        "/robots.txt": (200, "text/plain", b"User-agent: *\nAllow: /\n"),
    }

    boekel_pages = {
        "/": _html(C.BOEKEL_HOME),
        "/geschiedenis": _html(C.BOEKEL_HISTORY),
        "/robots.txt": (200, "text/plain",
                        b"User-agent: *\nAllow: /\nSitemap: http://boekel.test/sitemap.xml\n"),
        "/sitemap.xml": _xml(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>http://boekel.test/</loc><lastmod>2022-04-12</lastmod></url>'
            '<url><loc>http://boekel.test/geschiedenis</loc><lastmod>2021-07-08</lastmod></url>'
            '<url><loc>http://boekel.test/docs/omgevingsvergunning-2016.pdf</loc></url>'
            "</urlset>"),
        "/docs/omgevingsvergunning-2016.pdf": _binary(permit_pdf, "application/pdf"),
        "/img/inrichtingsplan-2016.png": _binary(boekel_plan, "image/png"),
    }

    # A login wall. The crawler must record BLOCKED, never describe the content.
    facebook_pages = {
        "/pourgues": (403, "text/html",
                      b"<html><body>You must log in to continue. Log in to Facebook"
                      b"</body></html>"),
        "/robots.txt": (200, "text/plain", b"User-agent: *\nAllow: /\n"),
    }

    theses_pages = {
        "/robots.txt": (200, "text/plain", b"User-agent: *\nAllow: /\n"),
        "/pdf/2020TOU30099.pdf": _binary(thesis_pdf, "application/pdf"),
        "/record/2020TOU30099": _html(
            "<html><body><h1>Agroecological transition at EcoVillage de Pourgues</h1>"
            "<p>Master's thesis, Universite de Toulouse, 2020</p></body></html>", ),
    }

    oud_boekel_pages = {
        "/": _html(C.OUD_BOEKEL_HOME),
        "/robots.txt": (200, "text/plain", b"User-agent: *\nAllow: /\n"),
    }

    return {
        "oud-boekel.test": oud_boekel_pages,
        "pourgues.test": pourgues_pages,
        "ancien-pourgues.test": ancien_pages,
        "annuaire.test": annuaire_pages,
        "boekel.test": boekel_pages,
        "facebook.test": facebook_pages,
        "theses.test": theses_pages,
    }


# --------------------------------------------------------------------------
# API stubs: archive CDX, academic search, DOI verification, web search
# --------------------------------------------------------------------------
ARCHIVE_RECORDS = [
    ["original", "timestamp", "mimetype", "statuscode", "digest"],
    ["http://pourgues.test/", "20160901000000", "text/html", "200", "A1"],
    ["http://pourgues.test/histoire", "20170601000000", "text/html", "200", "A2"],
    ["http://ancien-pourgues.test/", "20160401000000", "text/html", "200", "A3"],
    ["http://ancien-pourgues.test/pages-disparues/plantation-2016", "20161201000000",
     "text/html", "200", "A4"],
    ["http://ancien-pourgues.test/docs/bulletin-2016.pdf", "20170101000000",
     "application/pdf", "200", "A5"],
    ["http://boekel.test/", "20170301000000", "text/html", "200", "B1"],
    ["http://oud-boekel.test/", "20161101000000", "text/html", "200", "B2"],
]

SNAPSHOT_BODIES = {
    "http://pourgues.test/": C.page(
        "EcoVillage de Pourgues (2016)",
        "<h1>EcoVillage de Pourgues</h1>"
        "<p>Nous avons plante la foret-jardin cette annee et nous cultivons 2 hectares.</p>"
        "<p>Le domaine fait 55 hectares.</p>",
        published="2016-09-01"),
    "http://pourgues.test/histoire": C.page(
        "Notre histoire (2017)",
        "<h1>Notre histoire</h1>"
        "<p>Depuis 2016 la foret-jardin est plantee et les baissieres sont en cours de "
        "creusement.</p>",
        published="2017-06-01"),
    "http://ancien-pourgues.test/": C.ANCIEN_HOME,
    "http://boekel.test/": C.page(
        "Ecodorp Boekel (2017)",
        "<h1>Ecodorp Boekel</h1><p>In 2017 zijn 1200 bomen geplant voor het voedselbos. "
        "De wadi is in 2016 aangelegd.</p>",
        lang="nl", published="2017-03-01", footer=C.BOEKEL_FOOTER),
    "http://oud-boekel.test/": C.OUD_BOEKEL_HOME,
    "http://ancien-pourgues.test/pages-disparues/plantation-2016": C.page(
        "Plantation 2016",
        "<h1>Plantation 2016</h1>"
        "<p>Nous avons plante 3000 arbres en 2016. Cette page a disparu du site actuel.</p>",
        published="2016-12-01"),
}

ACADEMIC_RECORDS = {
    "results": [
        {
            "id": "http://theses.test/record/2020TOU30099",
            "doi": "https://doi.org/10.9999/pourgues.2020",
            "title": "Agroecological transition at EcoVillage de Pourgues",
            "publication_year": 2020,
            "authorships": [{"author": {"display_name": "M. Dupont"}}],
            "primary_location": {"source": {"display_name": "Universite de Toulouse"},
                                 "landing_page_url": "http://theses.test/record/2020TOU30099"},
            "locations": [{"pdf_url": "http://theses.test/pdf/2020TOU30099.pdf"}],
            "type": "thesis",
            "abstract_inverted_index": {
                "Agroecological": [0], "transition": [1], "at": [2], "a": [3],
                "French": [4], "ecovillage": [5], "with": [6], "permaculture": [7],
                "and": [8], "no-till": [9], "practices": [10],
            },
        }
    ]
}

SEARCH_RESULTS = {
    "default": [
        {"url": "http://ancien-pourgues.test/", "title": "Pourgues — ancien site",
         "snippet": "Ce site n'est plus mis a jour"},
        {"url": "https://annuaire.test/lieux/pourgues", "title": "Annuaire des ecolieux",
         "snippet": "EcoVillage de Pourgues"},
    ],
}


@dataclass
class FixtureServer:
    port: int = 0
    sites: dict[str, dict[str, Route]] = field(default_factory=build_sites)
    #: Injectable so the stress fixture can serve an archive the size of the
    #: one the reported run met, without touching the pilot fixtures.
    archive_records: list = field(default_factory=lambda: list(ARCHIVE_RECORDS))
    request_log: list[str] = field(default_factory=list)
    #: Seconds to wait before answering, simulating a real server on the far
    #: side of a network. Zero for the functional tests, which want speed; the
    #: benchmark sets it, because waiting on the network is the ONLY thing
    #: parallel communities exist to overlap, and a loopback fixture with no
    #: latency measures the overhead of parallelism without any of its benefit.
    latency_s: float = 0.0
    _server: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None

    def start(self) -> "FixtureServer":
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:      # silence stderr noise
                pass

            def do_GET(self) -> None:                        # noqa: N802
                host = (self.headers.get("Host") or "").split(":")[0].lower()
                parts = urlsplit(self.path)
                path = parts.path
                fixture.request_log.append(f"{host}{path}")

                route = fixture._resolve(host, path, parse_qs(parts.query))
                if route is None:
                    body = b"<html><body>not found</body></html>"
                    self._respond(404, "text/html", body)
                    return
                status, mime, body = route
                self._respond(status, mime, _with_port(body, mime, fixture.port))

            def do_HEAD(self) -> None:                       # noqa: N802
                self.do_GET()

            def _respond(self, status: int, mime: str, body: bytes) -> None:
                if fixture.latency_s:
                    time.sleep(fixture.latency_s)
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except BrokenPipeError:
                    pass

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def __enter__(self) -> "FixtureServer":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # -- routing -----------------------------------------------------------
    def _resolve(self, host: str, path: str, query: dict[str, list[str]]) -> Route | None:
        if host == "archive.test":
            return self._archive(path, query)
        if host == "theses.test" and path.startswith("/api"):
            return self._academic(path, query)
        site = self.sites.get(host)
        if site is None:
            return None
        if path in site:
            return site[path]
        if path.rstrip("/") in site:
            return site[path.rstrip("/")]
        if path + "/" in site:
            return site[path + "/"]
        return None

    def _archive(self, path: str, query: dict[str, list[str]]) -> Route | None:
        if path.startswith("/cdx"):
            target = (query.get("url") or [""])[0].rstrip("*")
            records = self.archive_records or ARCHIVE_RECORDS
            rows = [records[0]] + [
                r for r in records[1:] if target and target in r[0]
            ]
            if len(rows) == 1:
                return _json([])
            return _json(rows)
        if path.startswith("/web/"):
            remainder = path[len("/web/"):]
            _, _, original = remainder.partition("/")
            # The CDX listing is rewritten with this run's port on the way out,
            # so the snapshot request comes back carrying it. Strip it to match
            # the port-free keys the content module defines.
            original = re.sub(r"(\.test):\d+", r"\1", original)
            body = SNAPSHOT_BODIES.get(original) or SNAPSHOT_BODIES.get(original + "/") \
                or SNAPSHOT_BODIES.get(original.rstrip("/"))
            if body is None:
                for key, value in SNAPSHOT_BODIES.items():
                    if original.endswith(key.split("://", 1)[-1]):
                        body = value
                        break
            if body is None and original.endswith(".pdf"):
                return _binary(C.make_pdf(["Bulletin 2016 (snapshot)",
                                           "Nous avons plante 3000 arbres en 2016."]),
                               "application/pdf")
            if body is None:
                return None
            return _html(body)
        return None

    def _academic(self, path: str, query: dict[str, list[str]]) -> Route | None:
        search = " ".join(query.get("search") or query.get("query") or
                          query.get("q") or query.get("keywords") or [""]).lower()
        if path == "/api/works":
            if "pourgues" in search:
                return _json(ACADEMIC_RECORDS)
            return _json({"results": []})
        if path.startswith("/api/doi/"):
            return _json({"message": {
                "title": ["Agroecological transition at EcoVillage de Pourgues"],
                "DOI": "10.9999/pourgues.2020", "issued": {"date-parts": [[2020]]},
            }})
        if path == "/api/search":
            hits = SEARCH_RESULTS["default"] if "pourgues" in search else []
            body = "<html><body>" + "".join(
                f'<div class="result"><a href="{h["url"]}">{h["title"]}</a>'
                f'<span>{h["snippet"]}</span></div>' for h in hits
            ) + "</body></html>"
            return _html(body)
        return None
