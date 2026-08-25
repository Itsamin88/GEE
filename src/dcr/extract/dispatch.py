"""Route a downloaded file to the right parser, safely.

Nothing downloaded is executed, extensions are never trusted, and archives are
expanded only within strict member, size and ratio limits (brief §61).
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..ids import safe_name
from ..logging_setup import get_logger
from ..net.mime import sniff
from . import office, pdf, spreadsheet, text as text_extract

log = get_logger("extract")


@dataclass
class ExtractedImage:
    data: bytes
    name: str
    extension: str
    page_number: int | None = None
    width: int = 0
    height: int = 0
    nearby_text: str = ""


@dataclass
class ExtractedTable:
    sheet_name: str | None
    page_number: int | None
    cell_range: str | None
    rows: list[list[str]]
    header: list[str] = field(default_factory=list)


@dataclass
class Extraction:
    """One file's parse result, with every status recorded honestly."""

    mime: str = ""
    extension: str = ""
    parser: str = ""
    parser_status: str = "not_attempted"
    text_status: str = "not_attempted"
    table_status: str = "not_attempted"
    image_status: str = "not_attempted"
    ocr_status: str = "not_attempted"
    text: str = ""
    page_count: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    tables: list[ExtractedTable] = field(default_factory=list)
    images: list[ExtractedImage] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    hyperlinks: list[str] = field(default_factory=list)
    detail: str = ""
    contained_files: list[tuple[str, bytes]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.parser_status == "parsed"


def extract(
    data: bytes,
    *,
    declared_mime: str | None = None,
    filename: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> Extraction:
    cfg = dict(config or {})
    ocr_cfg = dict(cfg.get("ocr", {}))
    image_cfg = dict(cfg.get("images", {}))
    security = dict(cfg.get("security", {}))

    mime, extension = sniff(data, declared_mime, filename)
    result = Extraction(mime=mime, extension=extension)

    min_pixels = int(image_cfg.get("min_embedded_image_pixels", 90000))
    want_images = bool(image_cfg.get("extract_from_documents", True))

    try:
        if extension == "pdf":
            parsed = pdf.extract_pdf(
                data,
                ocr_mode=str(ocr_cfg.get("enabled", "auto")),
                ocr_min_chars=int(ocr_cfg.get("min_chars_per_page", 120)),
                ocr_max_pages=int(ocr_cfg.get("max_pages_per_document", 40)),
                ocr_languages=list(ocr_cfg.get("languages", ["eng"])),
                extract_images=want_images,
                min_image_pixels=min_pixels,
            )
            _from_pdf(parsed, result)
        elif extension == "docx":
            _from_office(office.extract_docx(data, extract_images=want_images,
                                             min_image_pixels=min_pixels), result)
        elif extension == "pptx":
            _from_office(office.extract_pptx(data, extract_images=want_images,
                                             min_image_pixels=min_pixels), result)
        elif extension in ("odt", "odp"):
            _from_office(office.extract_odf(data, extract_images=want_images,
                                            min_image_pixels=min_pixels), result)
        elif extension == "doc":
            _from_office(office.extract_legacy_doc(data), result)
        elif extension in ("xlsx", "xlsm", "ods"):
            _from_spreadsheet(spreadsheet.extract_xlsx(data), result)
        elif extension == "xls":
            _from_spreadsheet(spreadsheet.extract_xls(data), result)
        elif extension in ("csv", "tsv"):
            _from_spreadsheet(spreadsheet.extract_csv(data, filename=filename or "data.csv"), result)
        elif extension == "zip":
            _from_zip(data, result, security)
        elif extension in ("txt", "xml", "json", "kml", "geojson", "gpx", "html"):
            parsed = text_extract.extract_plain(data, extension=extension)
            result.parser = parsed.parser
            result.parser_status = parsed.parser_status
            result.text_status = parsed.text_status
            result.text = parsed.text
            result.metadata = parsed.metadata
            result.detail = parsed.detail
        elif extension == "kmz":
            _from_kmz(data, result, security)
        elif mime.startswith("image/"):
            result.parser = "image"
            result.parser_status = "parsed"
            result.text_status = "empty"
            result.image_status = "extracted"
            result.images = [
                ExtractedImage(data=data, name=filename or "image", extension=extension)
            ]
        else:
            result.parser_status = "unsupported_format"
            result.detail = f"no parser for {mime} (.{extension}); the original file is preserved"
    except Exception as exc:  # a parser must never abort a run
        result.parser_status = "corrupt"
        result.text_status = "failed"
        result.detail = f"{type(exc).__name__}: {exc}"
        log.debug("extraction failed for %s", filename, exc_info=True)
    return result


def _from_pdf(parsed: pdf.PdfResult, result: Extraction) -> None:
    result.parser = parsed.parser or "pypdf"
    result.parser_status = parsed.parser_status
    result.text_status = parsed.text_status
    result.table_status = parsed.table_status
    result.image_status = parsed.image_status
    result.ocr_status = parsed.ocr_status
    result.text = parsed.text
    result.page_count = parsed.page_count
    result.metadata = parsed.metadata
    result.detail = parsed.detail
    for page in parsed.pages:
        result.headings.extend(page.headings)
    for table in parsed.tables:
        result.tables.append(
            ExtractedTable(sheet_name=None, page_number=table.page_number,
                           cell_range=None, rows=table.rows)
        )
    for index, image in enumerate(parsed.images, start=1):
        result.images.append(
            ExtractedImage(
                data=image.data, name=f"page{image.page_number}_img{index}.{image.extension}",
                extension=image.extension, page_number=image.page_number,
                width=image.width, height=image.height, nearby_text=image.nearby_text,
            )
        )


def _from_office(parsed: office.OfficeResult, result: Extraction) -> None:
    result.parser = parsed.parser
    result.parser_status = parsed.parser_status
    result.text_status = parsed.text_status
    result.table_status = parsed.table_status
    result.image_status = parsed.image_status
    result.text = parsed.text
    result.metadata = parsed.metadata
    result.headings = parsed.headings
    result.hyperlinks = parsed.hyperlinks
    result.detail = parsed.detail
    for rows in parsed.tables:
        result.tables.append(
            ExtractedTable(sheet_name=None, page_number=None, cell_range=None,
                           rows=rows, header=rows[0] if rows else [])
        )
    for image in parsed.images:
        result.images.append(
            ExtractedImage(data=image.data, name=image.name, extension=image.extension,
                           width=image.width, height=image.height,
                           nearby_text=image.nearby_text)
        )


def _from_spreadsheet(parsed: spreadsheet.SpreadsheetResult, result: Extraction) -> None:
    result.parser = parsed.parser
    result.parser_status = parsed.parser_status
    result.text_status = parsed.text_status
    result.table_status = parsed.table_status
    result.text = parsed.text
    result.metadata = parsed.metadata
    result.detail = parsed.detail
    if parsed.hidden_sheets:
        result.metadata["hidden_sheets"] = "; ".join(parsed.hidden_sheets)
    for table in parsed.tables:
        result.tables.append(
            ExtractedTable(sheet_name=table.sheet_name, page_number=None,
                           cell_range=table.cell_range, rows=table.rows, header=table.header)
        )


def _from_zip(data: bytes, result: Extraction, security: Mapping[str, Any]) -> None:
    """Open a zip only within strict limits: no bombs, no path traversal."""
    max_members = int(security.get("max_archive_members", 500))
    max_total = int(security.get("max_archive_uncompressed_bytes", 500_000_000))
    max_ratio = float(security.get("max_archive_ratio", 120))
    result.parser = "zip"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > max_members:
                result.parser_status = "too_large"
                result.detail = f"{len(infos)} members exceeds the {max_members} limit"
                return
            total_uncompressed = sum(i.file_size for i in infos)
            compressed = max(1, sum(i.compress_size for i in infos))
            if total_uncompressed > max_total:
                result.parser_status = "too_large"
                result.detail = f"{total_uncompressed} uncompressed bytes exceeds the limit"
                return
            if total_uncompressed / compressed > max_ratio:
                result.parser_status = "too_large"
                result.detail = (
                    f"compression ratio {total_uncompressed / compressed:.0f}:1 looks like a "
                    "decompression bomb; the archive is stored unexpanded"
                )
                return
            listing: list[str] = []
            for info in infos:
                name = info.filename
                listing.append(f"{name} ({info.file_size} bytes)")
                if info.is_dir():
                    continue
                # Path traversal defence: the stored name is never used as a path.
                flat = safe_name(name.replace("/", "_"), max_length=90)
                if info.file_size > 60_000_000:
                    continue
                try:
                    result.contained_files.append((flat, archive.read(info)))
                except Exception:
                    continue
            result.text = "\n".join(listing)
            result.parser_status = "parsed"
            result.text_status = "extracted"
            result.detail = f"{len(result.contained_files)} members extracted for separate parsing"
    except zipfile.BadZipFile as exc:
        result.parser_status = "corrupt"
        result.detail = f"bad zip: {exc}"


def _from_kmz(data: bytes, result: Extraction, security: Mapping[str, Any]) -> None:
    _from_zip(data, result, security)
    for name, blob in result.contained_files:
        if name.lower().endswith(".kml"):
            parsed = text_extract.extract_plain(blob, extension="kml")
            result.text = parsed.text
            result.metadata.update(parsed.metadata)
            result.parser = "kmz"
            result.text_status = parsed.text_status
            break
