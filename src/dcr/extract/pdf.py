"""PDF extraction: text, page structure, tables, embedded images, metadata.

OCR is not run on every PDF. Usable text is looked for first, and OCR is
attempted only where a page has almost none (brief §19). Where OCR is
unavailable the fact is recorded and the original artefact is preserved — the
document is never marked processed when it was not.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

from ..logging_setup import get_logger

log = get_logger("pdf")


@dataclass
class PdfPage:
    number: int
    text: str = ""
    chars: int = 0
    ocr_used: bool = False
    headings: list[str] = field(default_factory=list)


@dataclass
class PdfImage:
    page_number: int
    data: bytes
    width: int
    height: int
    extension: str
    nearby_text: str = ""


@dataclass
class PdfTable:
    page_number: int
    rows: list[list[str]]


@dataclass
class PdfResult:
    ok: bool = False
    pages: list[PdfPage] = field(default_factory=list)
    tables: list[PdfTable] = field(default_factory=list)
    images: list[PdfImage] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    page_count: int = 0
    text: str = ""
    parser: str = ""
    parser_status: str = "not_attempted"
    text_status: str = "not_attempted"
    table_status: str = "not_attempted"
    image_status: str = "not_attempted"
    ocr_status: str = "not_attempted"
    encrypted: bool = False
    detail: str = ""

    @property
    def total_chars(self) -> int:
        return sum(p.chars for p in self.pages)


_HEADING = re.compile(r"^\s*(?:\d+(?:\.\d+)*\s+)?[A-ZÀ-ſ][^\n]{2,80}$")


def extract_pdf(
    data: bytes,
    *,
    ocr_mode: str = "auto",
    ocr_min_chars: int = 120,
    ocr_max_pages: int = 40,
    ocr_languages: list[str] | None = None,
    extract_images: bool = True,
    min_image_pixels: int = 90000,
) -> PdfResult:
    result = PdfResult()
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:  # pragma: no cover
        result.parser_status = "unsupported_format"
        result.detail = "pypdf is not installed"
        return result

    try:
        reader = PdfReader(io.BytesIO(data))
        if getattr(reader, "is_encrypted", False):
            result.encrypted = True
            try:
                if reader.decrypt("") == 0:
                    result.parser_status = "encrypted"
                    result.text_status = "failed"
                    result.detail = "PDF is encrypted and no password is available"
                    return result
            except Exception as exc:
                result.parser_status = "encrypted"
                result.text_status = "failed"
                result.detail = f"encrypted PDF: {exc}"
                return result

        result.parser = "pypdf"
        result.page_count = len(reader.pages)
        meta = reader.metadata or {}
        for key, value in dict(meta).items():
            try:
                result.metadata[str(key).lstrip("/")] = str(value)[:1000]
            except Exception:
                continue

        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                text = ""
                log.debug("page %d text extraction failed: %s", index, exc)
            cleaned = _tidy(text)
            result.pages.append(
                PdfPage(number=index, text=cleaned, chars=len(cleaned),
                        headings=_headings(cleaned))
            )
        result.parser_status = "parsed"
    except PdfReadError as exc:
        result.parser_status = "corrupt"
        result.text_status = "failed"
        result.detail = f"corrupt PDF: {exc}"
        return result
    except Exception as exc:
        result.parser_status = "corrupt"
        result.text_status = "failed"
        result.detail = f"{type(exc).__name__}: {exc}"
        return result

    # Tables, where a layout-aware parser is available.
    result.table_status = _extract_tables(data, result)
    # Embedded figures, which carry site plans and before/after photographs.
    if extract_images:
        result.image_status = _extract_images(data, result, min_image_pixels)
    else:
        result.image_status = "not_attempted"

    # OCR only for pages that genuinely lack text.
    thin_pages = [p for p in result.pages if p.chars < ocr_min_chars]
    if ocr_mode == "never" or not thin_pages:
        result.ocr_status = "not_needed" if not thin_pages else "disabled"
    else:
        result.ocr_status = _run_ocr(data, result, thin_pages[:ocr_max_pages], ocr_languages or ["eng"])

    result.text = "\n\n".join(f"[page {p.number}]\n{p.text}" for p in result.pages if p.text)
    if result.total_chars == 0:
        result.text_status = "empty" if result.ocr_status in ("not_needed", "disabled") else "ocr_unavailable"
        if result.ocr_status == "ocr_used":
            result.text_status = "ocr_used"
    else:
        result.text_status = "ocr_used" if result.ocr_status == "ocr_used" else "extracted"
    result.ok = result.parser_status == "parsed"
    return result


def _extract_tables(data: bytes, result: PdfResult) -> str:
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return "unavailable"
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                try:
                    for table in page.extract_tables() or []:
                        rows = [
                            [("" if cell is None else str(cell).strip()) for cell in row]
                            for row in table
                        ]
                        rows = [r for r in rows if any(c for c in r)]
                        if len(rows) > 1:
                            result.tables.append(PdfTable(page_number=index, rows=rows[:400]))
                except Exception:
                    continue
    except Exception as exc:
        log.debug("table extraction failed: %s", exc)
        return "failed"
    return "extracted" if result.tables else "none_found"


def _extract_images(data: bytes, result: PdfResult, min_pixels: int) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        return "unavailable"
    try:
        reader = PdfReader(io.BytesIO(data))
        for index, page in enumerate(reader.pages, start=1):
            try:
                images = list(getattr(page, "images", []) or [])
            except Exception:
                continue
            nearby = ""
            if index - 1 < len(result.pages):
                nearby = result.pages[index - 1].text[:600]
            for image in images:
                try:
                    blob = image.data
                    if not blob or len(blob) < 4000:
                        continue
                    width, height = _image_dimensions(blob)
                    if width * height < min_pixels:
                        continue
                    extension = (image.name or "img.png").rsplit(".", 1)[-1].lower()
                    result.images.append(
                        PdfImage(page_number=index, data=blob, width=width, height=height,
                                 extension=extension, nearby_text=nearby)
                    )
                except Exception:
                    continue
    except Exception as exc:
        log.debug("embedded image extraction failed: %s", exc)
        return "failed"
    return "extracted" if result.images else "none_found"


def _image_dimensions(blob: bytes) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(blob)) as img:
            return img.width, img.height
    except Exception:
        return 0, 0


def _run_ocr(data: bytes, result: PdfResult, pages: list[PdfPage], languages: list[str]) -> str:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # noqa: F401
    except ImportError:
        return "ocr_unavailable"
    try:
        import pdf2image  # type: ignore
    except ImportError:
        return "ocr_unavailable"
    try:
        lang = "+".join(languages)
        numbers = [p.number for p in pages]
        rendered = pdf2image.convert_from_bytes(
            data, first_page=min(numbers), last_page=max(numbers), dpi=200
        )
        by_number = {p.number: p for p in result.pages}
        for offset, image in enumerate(rendered):
            number = min(numbers) + offset
            page = by_number.get(number)
            if page is None or page.chars >= 120:
                continue
            text = _tidy(pytesseract.image_to_string(image, lang=lang))
            if text:
                page.text = text
                page.chars = len(text)
                page.ocr_used = True
        return "ocr_used" if any(p.ocr_used for p in result.pages) else "ocr_empty"
    except Exception as exc:
        log.debug("OCR failed: %s", exc)
        return "ocr_failed"


def _tidy(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"-\n(?=[a-zà-ÿ])", "", text)      # de-hyphenate line breaks
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _headings(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if 4 <= len(stripped) <= 90 and _HEADING.match(stripped) and not stripped.endswith("."):
            out.append(stripped)
    return out[:40]


def detect_document_kind(title: str, text: str, metadata: dict[str, str]) -> str:
    """Name what kind of document this is, from its own words."""
    haystack = " ".join([title or "", (text or "")[:6000],
                         " ".join(metadata.values())]).lower()
    patterns = (
        ("thesis", ("thesis", "dissertation", "master's", "phd", "mémoire", "proefschrift",
                    "tese de", "tesis de", "abschlussarbeit", "scriptie")),
        ("paper", ("abstract", "introduction", "methodology", "references", "doi:", "et al.")),
        ("permit", ("permit", "permis", "vergunning", "genehmigung", "licencia", "autorisation")),
        ("plan", ("site plan", "master plan", "plan de masse", "inrichtingsplan", "design plan",
                  "bestemmingsplan", "zoning")),
        ("report", ("annual report", "rapport annuel", "jaarverslag", "project report",
                    "final report", "rapport final", "evaluation")),
        ("newsletter", ("newsletter", "bulletin", "nieuwsbrief", "lettre d'information")),
        ("inventory", ("inventory", "inventaire", "planting record", "species list",
                       "plantenlijst", "registre")),
    )
    for label, needles in patterns:
        if any(needle in haystack for needle in needles):
            return label
    return "unknown"
