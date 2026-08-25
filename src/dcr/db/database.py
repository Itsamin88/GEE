"""SQLite access layer.

Everything the crawler learns is written here as it happens, so a run that is
interrupted at any point can be resumed, and so the workbook can be rebuilt
offline without re-fetching anything (brief §40, §41, §67).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = "1.0.0"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """A thread-safe wrapper over one SQLite file."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._init_schema()

    # -- lifecycle ---------------------------------------------------------
    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            self._conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (SCHEMA_VERSION,),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- primitives --------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params))

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.query_one(sql, params)
        return None if row is None else row[0]

    # -- convenience -------------------------------------------------------
    def insert(self, table: str, values: dict[str, Any], *, replace: bool = False) -> None:
        """Insert a row, JSON-encoding anything that is not a scalar."""
        clean = {k: _encode(v) for k, v in values.items() if v is not None}
        cols = ", ".join(clean)
        marks = ", ".join("?" for _ in clean)
        verb = "INSERT OR REPLACE" if replace else "INSERT"
        self.execute(f"{verb} INTO {table} ({cols}) VALUES ({marks})", list(clean.values()))

    def upsert(self, table: str, values: dict[str, Any], keys: Sequence[str]) -> None:
        clean = {k: _encode(v) for k, v in values.items() if v is not None}
        cols = ", ".join(clean)
        marks = ", ".join("?" for _ in clean)
        updates = ", ".join(f"{k}=excluded.{k}" for k in clean if k not in keys)
        conflict = ", ".join(keys)
        sql = f"INSERT INTO {table} ({cols}) VALUES ({marks})"
        if updates:
            sql += f" ON CONFLICT({conflict}) DO UPDATE SET {updates}"
        else:
            sql += f" ON CONFLICT({conflict}) DO NOTHING"
        self.execute(sql, list(clean.values()))

    def update(self, table: str, values: dict[str, Any], where: dict[str, Any]) -> None:
        clean = {k: _encode(v) for k, v in values.items()}
        sets = ", ".join(f"{k}=?" for k in clean)
        conds = " AND ".join(f"{k}=?" for k in where)
        self.execute(
            f"UPDATE {table} SET {sets} WHERE {conds}",
            list(clean.values()) + list(where.values()),
        )

    def bump(self, table: str, column: str, where: dict[str, Any], amount: int = 1) -> None:
        conds = " AND ".join(f"{k}=?" for k in where)
        self.execute(
            f"UPDATE {table} SET {column} = COALESCE({column}, 0) + ? WHERE {conds}",
            [amount] + list(where.values()),
        )

    def next_id(self, table: str, column: str, community_id: str, prefix: str, width: int = 4) -> str:
        """Mint the next sequential identifier for a community, e.g. IC001-E0042."""
        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE community_id = ? AND {column} LIKE ?",
                (community_id, f"{community_id}-{prefix}%"),
            ).fetchone()
            n = int(row[0]) + 1
            # Guard against gaps left by deletes: walk forward to a free id.
            while True:
                candidate = f"{community_id}-{prefix}{n:0{width}d}"
                exists = self._conn.execute(
                    f"SELECT 1 FROM {table} WHERE {column} = ?", (candidate,)
                ).fetchone()
                if not exists:
                    return candidate
                n += 1


def _encode(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(list(value) if isinstance(value, set) else value, ensure_ascii=False)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Path):
        return str(value)
    return value
