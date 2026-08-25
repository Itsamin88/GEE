"""Content-type sniffing. File extensions are never trusted (brief §61)."""

from __future__ import annotations

MAGIC = (
    (b"%PDF-", "application/pdf", "pdf"),
    (b"PK\x03\x04", "application/zip", "zip"),          # refined below
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "application/x-ole-storage", "ole"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"GIF87a", "image/gif", "gif"),
    (b"GIF89a", "image/gif", "gif"),
    (b"BM", "image/bmp", "bmp"),
    (b"II*\x00", "image/tiff", "tif"),
    (b"MM\x00*", "image/tiff", "tif"),
    (b"{\\rtf", "application/rtf", "rtf"),
    (b"\x1f\x8b", "application/gzip", "gz"),
    (b"<?xml", "application/xml", "xml"),
)

# Signatures inside a zip container that identify an OOXML / ODF payload.
ZIP_MEMBERS = (
    (b"word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
    (b"xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    (b"ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "pptx"),
    (b"mimetypeapplication/vnd.oasis.opendocument.text", "application/vnd.oasis.opendocument.text", "odt"),
    (b"mimetypeapplication/vnd.oasis.opendocument.spreadsheet", "application/vnd.oasis.opendocument.spreadsheet", "ods"),
    (b"mimetypeapplication/vnd.oasis.opendocument.presentation", "application/vnd.oasis.opendocument.presentation", "odp"),
    (b"doc.kml", "application/vnd.google-earth.kmz", "kmz"),
)

TEXTUAL_HINTS = (
    (b"<!doctype html", "text/html", "html"),
    (b"<html", "text/html", "html"),
    (b"<?xml", "application/xml", "xml"),
    (b"<svg", "image/svg+xml", "svg"),
    (b"<rss", "application/rss+xml", "xml"),
    (b"<feed", "application/atom+xml", "xml"),
    (b"{", "application/json", "json"),
    (b"[", "application/json", "json"),
)


def sniff(data: bytes, declared: str | None = None, filename: str | None = None) -> tuple[str, str]:
    """Return (mime, extension) from the bytes themselves.

    The declared Content-Type and the filename are only tie-breakers; a server
    that labels a PDF as text/html does not get to decide how it is parsed.
    """
    head = data[:4096]
    for magic, mime, ext in MAGIC:
        if head.startswith(magic):
            if ext == "zip":
                window = data[:400000]
                for member, zmime, zext in ZIP_MEMBERS:
                    if member in window:
                        return zmime, zext
                if filename and filename.lower().endswith(".kmz"):
                    return "application/vnd.google-earth.kmz", "kmz"
                return "application/zip", "zip"
            if ext == "ole":
                lowered = (filename or "").lower()
                if lowered.endswith(".xls"):
                    return "application/vnd.ms-excel", "xls"
                if lowered.endswith(".ppt"):
                    return "application/vnd.ms-powerpoint", "ppt"
                return "application/msword", "doc"
            return mime, ext

    lowered = head.lstrip()[:200].lower()
    for marker, mime, ext in TEXTUAL_HINTS:
        if lowered.startswith(marker):
            return mime, ext

    if declared:
        base = declared.split(";", 1)[0].strip().lower()
        mapping = {
            "text/html": "html", "application/xhtml+xml": "html",
            "text/plain": "txt", "text/csv": "csv", "text/tab-separated-values": "tsv",
            "application/json": "json", "application/xml": "xml", "text/xml": "xml",
            "application/pdf": "pdf", "image/webp": "webp",
            "application/vnd.google-earth.kml+xml": "kml",
            "application/geo+json": "geojson",
        }
        if base in mapping:
            return base, mapping[base]

    try:
        head.decode("utf-8")
        return "text/plain", "txt"
    except UnicodeDecodeError:
        return "application/octet-stream", "bin"


def is_html(mime: str) -> bool:
    return mime.split(";")[0].strip().lower() in {
        "text/html", "application/xhtml+xml", "application/xml", "text/xml",
        "application/rss+xml", "application/atom+xml",
    }


def is_image(mime: str) -> bool:
    return mime.split(";")[0].strip().lower().startswith("image/")
