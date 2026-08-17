"""Shared fixtures.

Every test runs against a throwaway database in a temporary directory, so the
suite never touches a real workspace and can run in any order.
"""

from __future__ import annotations

import pytest

from joblookup.config import Settings
from joblookup.db import session as db


@pytest.fixture
def settings(tmp_path) -> Settings:
    values = Settings()
    values.paths.workspace = str(tmp_path / "workspace")
    return values


@pytest.fixture
def database(tmp_path):
    db.close_all()
    db.configure(tmp_path / "workspace")
    yield db
    db.close_all()
