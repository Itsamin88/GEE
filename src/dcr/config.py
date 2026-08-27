"""Configuration loading, validation and the reproducibility record.

Every setting that could change what the crawler does is loaded from
``config/*.yaml`` and copied verbatim into each run manifest, so no hidden
default can alter the research process between runs (brief §63).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import __version__

# Repo root = two levels above this file (src/dcr/config.py -> src -> root)
ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required configuration file is missing: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not parse to a mapping")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class OptionalFeature:
    """One optional capability and whether this installation actually has it."""

    name: str
    available: bool
    detail: str
    degrades_to: str


@dataclass
class Settings:
    """The effective configuration for a run."""

    root: Path
    app: dict[str, Any]
    schema: dict[str, Any]
    sources: dict[str, Any]
    lexicon: dict[str, Any]
    decisions: dict[str, Any]
    env: dict[str, str] = field(default_factory=dict)
    #: Set by the orchestrator so one worker writes to one community's own
    #: database. None means the shared path from `paths.database`.
    database_override: Path | None = None

    # ---- convenience accessors -------------------------------------------
    @property
    def output_root(self) -> Path:
        return self._abs(self.app["paths"]["output_root"])

    @property
    def database_path(self) -> Path:
        """Where this run's evidence is stored.

        One database per community is the default, and it is what makes the
        isolation the brief asks for real: a corrupt or half-written database in
        C007 cannot reach C001, and sixteen workers are not queueing behind one
        SQLite writer lock (brief §8, §39). The override is set by the
        orchestrator when it hands a community to a worker.
        """
        if self.database_override is not None:
            return Path(self.database_override)
        return self._abs(self.app["paths"]["database"])

    def with_database(self, path: Path) -> "Settings":
        """The same configuration, pointed at one community's own database."""
        return replace(self, database_override=Path(path))

    @property
    def workbook_template(self) -> Path:
        return self._abs(self.app["paths"]["workbook_template"])

    @property
    def research_inputs(self) -> Path:
        return self._abs(self.app["paths"]["research_inputs"])

    def _abs(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else (self.root / p)

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.app
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    @property
    def contact(self) -> str:
        return self.env.get("DCR_CONTACT") or self.app["identity"]["contact"]

    @property
    def user_agent(self) -> str:
        return self.app["identity"]["user_agent_template"].format(
            version=__version__, contact=self.contact
        )

    # ---- reproducibility --------------------------------------------------
    def research_document_lock(self) -> list[dict[str, str]]:
        """Hash every research document actually present, for the version lock."""
        entries: list[dict[str, str]] = []
        inputs = self.research_inputs
        if inputs.exists():
            for path in sorted(inputs.iterdir()):
                if path.is_file():
                    entries.append(
                        {
                            "filename": path.name,
                            "sha256": sha256_file(path),
                            "bytes": str(path.stat().st_size),
                        }
                    )
        template = self.workbook_template
        if template.exists():
            entries.append(
                {
                    "filename": f"template/{template.name}",
                    "sha256": sha256_file(template),
                    "bytes": str(template.stat().st_size),
                }
            )
        return entries

    def config_lock(self) -> list[dict[str, str]]:
        entries = []
        for name in ("config.yaml", "field_schema.yaml", "sources.yaml",
                     "practice_lexicon.yaml", "decisions.yaml"):
            path = CONFIG_DIR / name
            if path.exists():
                entries.append({"filename": f"config/{name}", "sha256": sha256_file(path)})
        return entries

    def reproducibility_record(self, features: list[OptionalFeature]) -> dict[str, Any]:
        return {
            "app_version": __version__,
            "config_version": self.app.get("config_version"),
            "field_schema_version": self.schema.get("schema_version"),
            "register_version": self.schema.get("register_version"),
            "workbook_version": self.schema.get("workbook_version"),
            "plan_version": self.schema.get("plan_version"),
            "decision_record_version": self.decisions.get("decision_record_version"),
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "python": os.sys.version.split()[0],
            "research_documents": self.research_document_lock(),
            "configuration_files": self.config_lock(),
            "optional_features": [
                {
                    "name": f.name,
                    "available": f.available,
                    "detail": f.detail,
                    "degrades_to": f.degrades_to,
                }
                for f in features
            ],
        }


def load_settings(root: Path | None = None) -> Settings:
    base = Path(root).resolve() if root else ROOT
    cfg_dir = base / "config"
    env = _load_env(base)
    return Settings(
        root=base,
        app=_load_yaml(cfg_dir / "config.yaml"),
        schema=_load_yaml(cfg_dir / "field_schema.yaml"),
        sources=_load_yaml(cfg_dir / "sources.yaml"),
        lexicon=_load_yaml(cfg_dir / "practice_lexicon.yaml"),
        decisions=_load_yaml(cfg_dir / "decisions.yaml"),
        env=env,
    )


def _load_env(base: Path) -> dict[str, str]:
    """Read .env if present, then let real environment variables win."""
    values: dict[str, str] = {}
    env_file = base / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip().strip('"').strip("'")
    for key in list(values) + [
        "ANTHROPIC_API_KEY", "CORE_API_KEY", "BASE_API_KEY", "BRAVE_API_KEY",
        "SERPAPI_KEY", "GOOGLE_CSE_KEY", "GOOGLE_CSE_CX", "BING_API_KEY",
        "OPENCORPORATES_KEY", "DCR_CONTACT",
    ]:
        real = os.environ.get(key)
        if real:
            values[key] = real
    return values


def detect_optional_features(settings: Settings) -> list[OptionalFeature]:
    """Report which advanced features this installation actually has.

    Nothing here fails a run: a missing capability degrades the pipeline and is
    recorded, never silently skipped (brief §78, §79).
    """
    features: list[OptionalFeature] = []

    def probe(name: str, module: str, detail_yes: str, detail_no: str, degrade: str) -> None:
        try:
            __import__(module)
            features.append(OptionalFeature(name, True, detail_yes, degrade))
        except Exception:  # pragma: no cover - import failure path
            features.append(OptionalFeature(name, False, detail_no, degrade))

    probe("browser_automation", "playwright",
          "Playwright installed; JS-rendered pages can be read.",
          "Playwright not installed.",
          "HTTP-only extraction; JS-only pages recorded as js_required.")
    probe("pdf_layout_tables", "pdfplumber",
          "pdfplumber installed; PDF tables extracted with layout.",
          "pdfplumber not installed.",
          "Text-only PDF extraction; tables recorded as not extracted.")
    probe("ocr", "pytesseract",
          "pytesseract installed.",
          "pytesseract not installed.",
          "OCR skipped; original artefact preserved and ocr_status recorded.")
    probe("legacy_xls", "xlrd",
          "xlrd installed; legacy .xls readable.",
          "xlrd not installed.",
          ".xls files stored unparsed with parser_status=unsupported_format.")
    probe("legacy_doc", "olefile",
          "olefile installed; legacy .doc partially readable.",
          "olefile not installed.",
          ".doc files stored unparsed with parser_status=unsupported_format.")
    probe("language_detection", "langdetect",
          "langdetect installed.",
          "langdetect not installed.",
          "Language inferred from HTTP/HTML metadata and country only.")

    has_key = bool(settings.env.get("ANTHROPIC_API_KEY"))
    features.append(
        OptionalFeature(
            "llm_semantic_extraction",
            has_key,
            "ANTHROPIC_API_KEY present; semantic evidence mapping available."
            if has_key else "No ANTHROPIC_API_KEY.",
            "Deterministic extraction only; ambiguous evidence goes to the human review queue.",
        )
    )
    for engine in settings.sources.get("search_engines", []):
        if engine.get("needs_key"):
            key = engine.get("key_env", "")
            present = bool(settings.env.get(key))
            features.append(
                OptionalFeature(
                    f"search_engine:{engine['id']}",
                    present,
                    f"{key} present." if present else f"{key} absent.",
                    "Engine recorded as not_configured; other engines used.",
                )
            )
    return features
