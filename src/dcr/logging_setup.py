"""Structured logging: console progress, a full file log, and a JSONL stream.

Progress messages are written so a non-programmer can see what is happening —
[Stage 4/9] archive enumeration, [DOC] PDF found, [BLOCKED] Instagram — while
the JSONL stream stays machine-readable for the audit (brief §59).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER_NAME = "dcr"


class JsonlHandler(logging.Handler):
    """Writes one JSON object per record, for machine-readable auditing."""

    def __init__(self, path: Path):
        super().__init__(level=logging.DEBUG)
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload: dict[str, Any] = {
                "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            for key, value in record.__dict__.items():
                if key.startswith("dcr_"):
                    payload[key[4:]] = value
            if record.exc_info:
                payload["exception"] = self.format(record)
            self._fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            self._fh.flush()
        except Exception:  # pragma: no cover - logging must never crash a run
            self.handleError(record)

    def close(self) -> None:
        try:
            self._fh.close()
        finally:
            super().close()


class ConsoleFormatter(logging.Formatter):
    """Short, readable console lines. Tags stay at the front where they scan."""

    def format(self, record: logging.LogRecord) -> str:
        stamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        message = record.getMessage()
        if record.levelno >= logging.ERROR:
            return f"{stamp}  ERROR  {message}"
        if record.levelno >= logging.WARNING:
            return f"{stamp}  WARN   {message}"
        return f"{stamp}  {message}"


def setup_logging(
    log_dir: Path | None = None,
    *,
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    jsonl: bool = True,
) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    console.setFormatter(ConsoleFormatter())
    logger.addHandler(console)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
        file_handler.setLevel(getattr(logging, file_level.upper(), logging.DEBUG))
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-7s  %(name)s  %(message)s")
        )
        logger.addHandler(file_handler)
        if jsonl:
            logger.addHandler(JsonlHandler(log_dir / "events.jsonl"))
    return logger


def get_logger(suffix: str | None = None) -> logging.Logger:
    return logging.getLogger(LOGGER_NAME if not suffix else f"{LOGGER_NAME}.{suffix}")


def event(logger: logging.Logger, tag: str, message: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log a tagged progress line plus machine-readable fields.

    ``event(log, "DOC", "PDF found: annual report 2019")`` prints
    ``[DOC] PDF found: annual report 2019`` and records the extra fields in the
    JSONL stream.
    """
    extra = {f"dcr_{k}": v for k, v in fields.items()}
    extra["dcr_tag"] = tag
    logger.log(level, f"[{tag}] {message}", extra=extra)
