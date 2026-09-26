"""
SQLite database engine, connection lifecycle management, and FTS5 search index.

Enforces:
- WAL journal mode: PRAGMA journal_mode=WAL;
- Busy timeout: PRAGMA busy_timeout=5000;
- Foreign key constraints: PRAGMA foreign_keys=ON;
- Synchronous setting: PRAGMA synchronous=NORMAL;
- FTS5 virtual table (jobs_fts) with unicode61 tokenizer preserving '+#.' symbols.
- Real-time synchronization triggers on INSERT, DELETE, and selective UPDATE.
- WAL checkpointing utility for safe GCS backups and graceful shutdown.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from .models import FTS_DDL, SCHEMA_DDL, TRIGGERS_DDL

logger = logging.getLogger("job_dashboard_light.database")

# Default database location inside project data directory
DEFAULT_DB_PATH = Path(
    os.getenv(
        "JOB_DASHBOARD_DB_PATH",
        str(Path(__file__).parent.parent.parent / "data" / "jobs.sqlite3"),
    )
)


def get_db_path(custom_path: Optional[str | Path] = None) -> Path:
    """Resolve database path, ensuring parent directory exists."""
    path = Path(custom_path) if custom_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def create_connection(
    db_path: Optional[str | Path] = None, timeout: float = 5.0
) -> sqlite3.Connection:
    """Create a new SQLite connection configured with mandatory WAL pragmas.

    Pragmas enforced:
    1. journal_mode=WAL: Allows concurrent readers alongside an active writer.
    2. busy_timeout=5000: Waits up to 5.0s for locked tables before raising OperationalError.
    3. foreign_keys=ON: Enforces relational integrity and cascading deletes.
    4. synchronous=NORMAL: Safe durability with minimum disk write overhead in WAL mode.
    """
    resolved_path = get_db_path(db_path)
    conn = sqlite3.connect(
        str(resolved_path),
        timeout=timeout,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row

    # Execute mandatory PRAGMAs
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-64000;")  # 64MB memory cache

    return conn


@contextmanager
def get_db_connection(
    db_path: Optional[str | Path] = None,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding a database connection with auto-commit and rollback on error.

    Usage:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO jobs ...")
    """
    conn = create_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db(
    db_path: Optional[str | Path] = None,
) -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency yielding a managed database connection."""
    with get_db_connection(db_path) as conn:
        yield conn


def checkpoint_wal(
    conn_or_path: sqlite3.Connection | str | Path, mode: str = "TRUNCATE"
) -> tuple[int, int, int]:
    """Flush and truncate the SQLite Write-Ahead Log (WAL) into the primary database file.

    Modes: PASSIVE, FULL, RESTART, TRUNCATE.
    Returns: (busy_flag, log_pages, checkpointed_pages)
    Used by GCS backup services and SIGTERM shutdown handlers.
    """
    valid_modes = {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}
    mode_upper = mode.upper()
    if mode_upper not in valid_modes:
        raise ValueError(
            f"Invalid WAL checkpoint mode: {mode}. Must be one of {valid_modes}"
        )

    if isinstance(conn_or_path, sqlite3.Connection):
        cursor = conn_or_path.execute(f"PRAGMA wal_checkpoint({mode_upper});")
        res = cursor.fetchone()
        return (res[0], res[1], res[2])
    else:
        with get_db_connection(conn_or_path) as conn:
            cursor = conn.execute(f"PRAGMA wal_checkpoint({mode_upper});")
            res = cursor.fetchone()
            return (res[0], res[1], res[2])


def sanitize_fts5_query(term: Optional[str], prefix_last: bool = True) -> str:
    """Sanitize user search string into a syntax-valid FTS5 query.

    Handles:
    - Technical symbols (C++, C#, .NET, Node.js)
    - Double quotes for exact phrases
    - Stray boolean tokens (AND, OR, NOT)
    - Trailing wildcard prefix matching for incremental queries
    """
    if not term or not str(term).strip():
        return ""
    raw = str(term).strip()
    pattern = re.compile(r"\"([^\"]*)\"|(\S+)")
    matches = list(pattern.finditer(raw))
    if not matches:
        return ""

    tokens: list[str] = []
    for i, match in enumerate(matches):
        phrase, word = match.groups()
        is_last = i == len(matches) - 1

        if phrase is not None:
            clean_phrase = phrase.strip().replace('"', '""')
            if clean_phrase:
                tokens.append(f'"{clean_phrase}"')
        elif word:
            clean_word = word.strip('"').replace('"', '""')
            if not clean_word:
                continue
            upper_word = clean_word.upper()
            if upper_word in ("AND", "OR", "NOT"):
                if tokens and tokens[-1] not in ("AND", "OR", "NOT") and not is_last:
                    tokens.append(upper_word)
            else:
                has_trailing_star = clean_word.endswith("*")
                base_word = clean_word.rstrip("*")
                if not base_word:
                    continue
                if (
                    is_last
                    and prefix_last
                    and not has_trailing_star
                    and len(base_word) > 1
                ):
                    tokens.append(f'"{base_word}"*')
                elif has_trailing_star:
                    tokens.append(f'"{base_word}"*')
                else:
                    tokens.append(f'"{base_word}"')

    while tokens and tokens[-1] in ("AND", "OR", "NOT"):
        tokens.pop()
    while tokens and tokens[0] in ("AND", "OR", "NOT"):
        tokens.pop(0)

    return " ".join(tokens)


def init_db(
    db_path: Optional[str | Path] = None, force_rebuild_fts: bool = False
) -> None:
    """Initialize database schema, secondary indexes, and FTS5 full-text search triggers.

    Idempotent: safe to run multiple times without data corruption or index errors.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Execute core relational tables & indexes
        cursor.executescript(SCHEMA_DDL)

        # 2. Check existing FTS table configuration
        existing_fts = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs_fts'"
        ).fetchone()

        if existing_fts and existing_fts[0]:
            sql_def = existing_fts[0].lower()
            if (
                "content='jobs'" not in sql_def
                or "tokenchars" not in sql_def
                or force_rebuild_fts
            ):
                logger.info("Migrating or rebuilding jobs_fts virtual table...")
                cursor.execute("DROP TRIGGER IF EXISTS jobs_ai;")
                cursor.execute("DROP TRIGGER IF EXISTS jobs_ad;")
                cursor.execute("DROP TRIGGER IF EXISTS jobs_au;")
                cursor.execute("DROP TABLE IF EXISTS jobs_fts;")

        # 3. Create FTS5 virtual table
        cursor.execute(FTS_DDL)

        # 4. Attach synchronization triggers
        cursor.executescript(TRIGGERS_DDL)

        # 5. Populate or rebuild FTS index if jobs exist
        jobs_count_row = cursor.execute("SELECT count(*) FROM jobs").fetchone()
        jobs_count = jobs_count_row[0] if jobs_count_row else 0
        if jobs_count > 0:
            fts_count_row = cursor.execute("SELECT count(*) FROM jobs_fts").fetchone()
            fts_count = fts_count_row[0] if fts_count_row else 0
            if fts_count == 0 or force_rebuild_fts:
                logger.info(f"Rebuilding FTS5 search index for {jobs_count} jobs...")
                cursor.execute("INSERT INTO jobs_fts(jobs_fts) VALUES('rebuild');")
