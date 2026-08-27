"""Plain text, XML, JSON and geospatial sidecar extraction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class TextResult:
    ok: bool = False
    text: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    parser: str = ""
    parser_status: str = "not_attempted"
    text_status: str = "not_attempted"
    detail: str = ""


def extract_plain(data: bytes, *, extension: str = "txt") -> TextResult:
    result = TextResult(parser=f"plain:{extension}")
    text = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        result.parser_status = "corrupt"
        result.detail = "undecodable bytes"
        return result

    if extension in ("kml", "kmz", "geojson", "gpx", "xml"):
        result.text, result.metadata = _geospatial_text(text, extension)
    elif extension == "json":
        try:
            payload = json.loads(text)
            result.text = json.dumps(payload, ensure_ascii=False, indent=1)[:400000]
        except json.JSONDecodeError:
            result.text = text[:400000]
    else:
        result.text = text[:400000]

    result.text = re.sub(r"\n{3,}", "\n\n", result.text).strip()
    result.parser_status = "parsed"
    result.text_status = "extracted" if result.text else "empty"
    result.ok = True
    return result


def _geospatial_text(text: str, extension: str) -> tuple[str, dict[str, str]]:
    """Names and descriptions out of a KML/GeoJSON file.

    Only the LABELS are read. Geometry is never turned into an area figure —
    the polygon is the researcher's controlled measurement (brief §70).
    """
    metadata: dict[str, str] = {"geometry_read": "no — labels only, by design"}
    pieces: list[str] = []
    if extension in ("kml", "xml", "gpx"):
        from bs4 import BeautifulSoup

        try:
            soup = BeautifulSoup(text, "xml")
        except Exception:
            return text[:200000], metadata
        for tag in ("name", "description", "Snippet", "displayName", "value", "desc"):
            for node in soup.find_all(tag):
                content = node.get_text(" ", strip=True)
                if content and len(content) < 4000:
                    pieces.append(f"{tag}: {content}")
        metadata["placemarks"] = str(len(soup.find_all("Placemark")))
    elif extension == "geojson":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text[:200000], metadata
        features = payload.get("features", []) if isinstance(payload, dict) else []
        metadata["features"] = str(len(features))
        for feature in features[:2000]:
            properties = (feature or {}).get("properties") or {}
            for key, value in properties.items():
                if isinstance(value, (str, int, float)) and str(value).strip():
                    pieces.append(f"{key}: {value}")
    return "\n".join(pieces)[:200000], metadata
