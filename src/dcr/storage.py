"""The per-community output tree.

    Research_Web_Crawler_Output/<community_id>_<safe_name>/
        01_raw_sources/   02_documents/   03_images/    04_archives/
        05_extracted_text/ 06_tables/     07_evidence/  08_logs/
        09_final/          10_debug/

Every file written here is traceable back to a source (brief §24, §72).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .ids import safe_name

SUBDIRS = (
    "01_raw_sources",
    "02_documents",
    "03_images",
    "04_archives",
    "05_extracted_text",
    "06_tables",
    "07_evidence",
    "08_logs",
    "09_final",
    "10_debug",
)


@dataclass
class CommunityStorage:
    root: Path
    community_id: str

    @classmethod
    def create(cls, output_root: Path, community_id: str, community_name: str) -> "CommunityStorage":
        folder = output_root / f"{community_id}_{safe_name(community_name)}"
        storage = cls(root=folder, community_id=community_id)
        storage.ensure()
        return storage

    def ensure(self) -> None:
        for name in SUBDIRS:
            (self.root / name).mkdir(parents=True, exist_ok=True)

    # -- directories -------------------------------------------------------
    @property
    def raw(self) -> Path:
        return self.root / "01_raw_sources"

    @property
    def documents(self) -> Path:
        return self.root / "02_documents"

    @property
    def images(self) -> Path:
        return self.root / "03_images"

    @property
    def archives(self) -> Path:
        return self.root / "04_archives"

    @property
    def text(self) -> Path:
        return self.root / "05_extracted_text"

    @property
    def tables(self) -> Path:
        return self.root / "06_tables"

    @property
    def evidence(self) -> Path:
        return self.root / "07_evidence"

    @property
    def logs(self) -> Path:
        return self.root / "08_logs"

    @property
    def final(self) -> Path:
        return self.root / "09_final"

    @property
    def debug(self) -> Path:
        return self.root / "10_debug"

    # -- writing -----------------------------------------------------------
    def write_bytes(self, directory: Path, filename: str, data: bytes) -> Path:
        """Write a file, refusing any name that could escape the directory."""
        clean = safe_name(filename, max_length=120)
        target = (directory / clean).resolve()
        base = directory.resolve()
        if not str(target).startswith(str(base)):
            raise ValueError(f"refusing to write outside the output tree: {filename!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def write_text(self, directory: Path, filename: str, content: str) -> Path:
        return self.write_bytes(directory, filename, content.encode("utf-8"))

    def relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def raw_page_path(self, page_id: str, extension: str = "html") -> str:
        return f"{page_id}.{safe_name(extension, max_length=8) or 'html'}"

    def text_path(self, ref_id: str) -> str:
        return f"{ref_id}.txt"

    @staticmethod
    def content_hash(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
