"""
Shared pytest fixtures for Job Dashboard Light test suite.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator

import pytest

from job_dashboard_light.database import create_connection, init_db


@pytest.fixture
def temp_db(tmp_path: Path) -> Generator[str, None, None]:
    """Provide a fresh SQLite test database path with initialized schema."""
    db_file = str(tmp_path / "test_jobs.sqlite3")
    init_db(db_file)
    yield db_file


@pytest.fixture
def db_conn(temp_db: str) -> Generator[sqlite3.Connection, None, None]:
    """Provide a managed database connection to temp_db."""
    conn = create_connection(temp_db)
    yield conn
    conn.close()
