"""Shared test fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dcr.config import load_settings          # noqa: E402
from dcr.db import Database, utcnow           # noqa: E402


@pytest.fixture(scope="session")
def settings():
    return load_settings(ROOT)


@pytest.fixture(scope="session")
def schema(settings):
    return settings.schema


@pytest.fixture(scope="session")
def lexicon(settings):
    return settings.lexicon


@pytest.fixture()
def db(tmp_path) -> Database:
    database = Database(tmp_path / "test.sqlite3")
    yield database
    database.close()


@pytest.fixture()
def community(db) -> str:
    db.insert("communities", {
        "community_id": "IC001", "site_id": "IC001", "name_input": "Test Community",
        "safe_name": "Test_Community", "created_utc": utcnow(), "updated_utc": utcnow(),
    })
    return "IC001"
