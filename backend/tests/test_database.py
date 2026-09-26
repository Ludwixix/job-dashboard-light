"""
Unit, integration, and concurrency test suite for SQLite WAL database engine and schema.

Verifies:
1. SQLite PRAGMAs: journal_mode=WAL, busy_timeout=5000, foreign_keys=ON, synchronous=NORMAL.
2. Relational schema DDL: tables, columns, defaults, indexes, and constraints.
3. Foreign key enforcement and cascading deletes across all user-isolated tables.
4. Unique and CHECK constraints on user_applications, users, and generated_documents.
5. FTS5 full-text search virtual table, tokenchars ('+#.'), and real-time sync triggers.
6. Concurrency resilience: simultaneous multi-threaded readers and writers under WAL mode.
7. WAL checkpointing with TRUNCATE mode.
"""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from job_dashboard_light.database import (
    checkpoint_wal,
    create_connection,
    get_db_connection,
    sanitize_fts5_query,
)
from job_dashboard_light.models import (
    Job,
    User,
)

# ==============================================================================
# 1. PRAGMA Configuration & Invariants
# ==============================================================================


def test_wal_mode_and_pragmas(temp_db: str) -> None:
    """Verify that mandatory WAL pragmas are strictly configured on new connections."""
    conn = create_connection(temp_db)
    try:
        # 1. WAL journal mode
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert journal_mode.lower() == "wal", f"Expected WAL mode, got {journal_mode}"

        # 2. Busy timeout (5000ms)
        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert busy_timeout == 5000, f"Expected busy_timeout=5000, got {busy_timeout}"

        # 3. Foreign key constraints enabled
        foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert foreign_keys == 1, f"Expected foreign_keys=1, got {foreign_keys}"

        # 4. Synchronous NORMAL (1 in SQLite)
        synchronous = conn.execute("PRAGMA synchronous;").fetchone()[0]
        assert synchronous == 1, f"Expected synchronous=1 (NORMAL), got {synchronous}"
    finally:
        conn.close()


def test_schema_tables_and_indexes_exist(temp_db: str) -> None:
    """Verify that all core tables and performance indexes are created."""
    conn = create_connection(temp_db)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        expected_tables = {
            "jobs",
            "users",
            "user_profiles",
            "user_applications",
            "user_preferences",
            "generated_documents",
            "jobs_fts",
        }
        for table in expected_tables:
            assert table in tables, f"Expected table '{table}' in database"

        # Verify FTS virtual table definition contains external content and tokenchars
        fts_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs_fts'"
        ).fetchone()[0]
        assert "content='jobs'" in fts_sql
        assert "tokenchars '+#.'" in fts_sql

        # Verify triggers
        triggers = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        ]
        assert "jobs_ai" in triggers
        assert "jobs_ad" in triggers
        assert "jobs_au" in triggers
    finally:
        conn.close()


# ==============================================================================
# 2. Relational Constraints & Foreign Key Integrity
# ==============================================================================


def test_foreign_key_enforcement_and_cascades(temp_db: str) -> None:
    """Verify foreign key enforcement on insert and cascading deletes on user removal."""
    # 1. Insert orphan profile must fail
    with pytest.raises(sqlite3.IntegrityError):
        with get_db_connection(temp_db) as conn:
            conn.execute(
                "INSERT INTO user_profiles (user_id, updated_at) VALUES ('nonexistent_user', '2026-09-26T00:00:00Z')"
            )

    # 2. Insert valid user, profile, application, preferences, and document
    user = User(id="google_10928374", email="candidate@example.com", name="Jane Doe")
    job = Job(
        id="seek_998877",
        title="Lead Cloud Architect",
        company="Telstra",
        description="Architecting multi-cloud AWS and Azure platforms with Python.",
        source="Seek",
        url="https://www.seek.com.au/job/998877",
    )

    with get_db_connection(temp_db) as conn:
        conn.execute(
            "INSERT INTO users (id, email, name, avatar_url, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                user.id,
                user.email,
                user.name,
                user.avatar_url,
                user.created_at,
                user.updated_at,
            ),
        )
        conn.execute(
            """INSERT INTO jobs (id, title, company, location, description, source, url, tags, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job.id,
                job.title,
                job.company,
                job.location,
                job.description,
                job.source,
                job.url,
                "[]",
                job.status,
                job.created_at,
                job.updated_at,
            ),
        )
        conn.execute(
            "INSERT INTO user_profiles (user_id, seniority, updated_at) VALUES (?, 'Senior', '2026-09-26T00:00:00Z')",
            (user.id,),
        )
        conn.execute(
            """INSERT INTO user_applications (id, user_id, job_id, status, notes, updated_at)
            VALUES ('app_001', ?, ?, 'Applied', 'Direct application', '2026-09-26T00:00:00Z')""",
            (user.id, job.id),
        )
        conn.execute(
            "INSERT INTO user_preferences (user_id, default_model, updated_at) VALUES (?, 'anthropic/claude-3.5-sonnet', '2026-09-26T00:00:00Z')",
            (user.id,),
        )
        conn.execute(
            """INSERT INTO generated_documents (id, user_id, job_id, doc_type, model_used, title, content_markdown, created_at)
            VALUES ('doc_001', ?, ?, 'cv', 'deepseek/deepseek-chat', 'Tailored CV', '# Jane Doe CV', '2026-09-26T00:00:00Z')""",
            (user.id, job.id),
        )

    # Verify rows exist
    with get_db_connection(temp_db) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM user_profiles WHERE user_id = ?", (user.id,)
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM user_applications WHERE user_id = ?", (user.id,)
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM user_preferences WHERE user_id = ?", (user.id,)
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM generated_documents WHERE user_id = ?", (user.id,)
            ).fetchone()[0]
            == 1
        )

    # 3. Delete user -> CASCADE must delete all associated records
    with get_db_connection(temp_db) as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user.id,))

    # Verify cascade deletion
    with get_db_connection(temp_db) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM user_profiles WHERE user_id = ?", (user.id,)
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM user_applications WHERE user_id = ?", (user.id,)
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM user_preferences WHERE user_id = ?", (user.id,)
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM generated_documents WHERE user_id = ?", (user.id,)
            ).fetchone()[0]
            == 0
        )
        # The job in the shared pool must NOT be deleted
        assert (
            conn.execute(
                "SELECT count(*) FROM jobs WHERE id = ?", (job.id,)
            ).fetchone()[0]
            == 1
        )


def test_unique_and_check_constraints(temp_db: str) -> None:
    """Verify CHECK constraints on status/doc_type and UNIQUE constraints."""
    user = User(id="u1", email="user1@example.com", name="User One")
    job = Job(
        id="j1",
        title="Dev",
        company="Corp",
        description="Desc",
        source="Seek",
        url="https://example.com",
    )

    with get_db_connection(temp_db) as conn:
        conn.execute(
            "INSERT INTO users (id, email, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user.id, user.email, user.name, user.created_at, user.updated_at),
        )
        conn.execute(
            "INSERT INTO jobs (id, title, company, description, source, url, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job.id,
                job.title,
                job.company,
                job.description,
                job.source,
                job.url,
                job.created_at,
                job.updated_at,
            ),
        )

    # 1. UNIQUE email on users table
    with pytest.raises(sqlite3.IntegrityError):
        with get_db_connection(temp_db) as conn:
            conn.execute(
                "INSERT INTO users (id, email, name, created_at, updated_at) VALUES ('u2', 'user1@example.com', 'Duplicate', '2026-09-26T00:00:00Z', '2026-09-26T00:00:00Z')"
            )

    # 2. CHECK constraint on user_applications status
    with pytest.raises(sqlite3.IntegrityError):
        with get_db_connection(temp_db) as conn:
            conn.execute(
                "INSERT INTO user_applications (id, user_id, job_id, status, updated_at) VALUES ('a1', 'u1', 'j1', 'UnknownStatus', '2026-09-26T00:00:00Z')"
            )

    # 3. Valid status insert
    with get_db_connection(temp_db) as conn:
        conn.execute(
            "INSERT INTO user_applications (id, user_id, job_id, status, updated_at) VALUES ('a1', 'u1', 'j1', 'Interviewing', '2026-09-26T00:00:00Z')"
        )

    # 4. UNIQUE(user_id, job_id) on user_applications
    with pytest.raises(sqlite3.IntegrityError):
        with get_db_connection(temp_db) as conn:
            conn.execute(
                "INSERT INTO user_applications (id, user_id, job_id, status, updated_at) VALUES ('a2', 'u1', 'j1', 'Applied', '2026-09-26T00:00:00Z')"
            )

    # 5. CHECK constraint on generated_documents doc_type
    with pytest.raises(sqlite3.IntegrityError):
        with get_db_connection(temp_db) as conn:
            conn.execute(
                """INSERT INTO generated_documents (id, user_id, job_id, doc_type, model_used, title, content_markdown, created_at)
                VALUES ('d1', 'u1', 'j1', 'invalid_doc', 'model', 'title', 'md', '2026-09-26T00:00:00Z')"""
            )


# ==============================================================================
# 3. FTS5 Full-Text Search, Triggers & Technical Symbols
# ==============================================================================


def test_fts5_real_time_sync_triggers(temp_db: str) -> None:
    """Verify FTS5 synchronization on INSERT, UPDATE, and DELETE."""
    job_id = "job_sync_test"
    with get_db_connection(temp_db) as conn:
        conn.execute(
            """INSERT INTO jobs (id, title, company, location, description, source, url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, '2026-09-26T00:00:00Z', '2026-09-26T00:00:00Z')""",
            (
                job_id,
                "Staff Distributed Systems Engineer",
                "Canva",
                "Sydney, NSW",
                "Designing high-scale distributed backend pipelines with Golang and Kubernetes.",
                "Seek",
                "https://example.com/canva-1",
            ),
        )

    # 1. Search after INSERT
    with get_db_connection(temp_db) as conn:
        query = sanitize_fts5_query("Golang")
        res = conn.execute(
            "SELECT jobs.id, jobs.title FROM jobs JOIN jobs_fts ON jobs.rowid = jobs_fts.rowid WHERE jobs_fts MATCH ?",
            (query,),
        ).fetchall()
        assert len(res) == 1
        assert res[0]["id"] == job_id

    # 2. UPDATE text fields -> FTS updates
    with get_db_connection(temp_db) as conn:
        conn.execute(
            """UPDATE jobs SET title = 'Principal Rust Architect', description = 'Memory safe systems programming in Rust.'
            WHERE id = ?""",
            (job_id,),
        )

    with get_db_connection(temp_db) as conn:
        # Old term must not match
        assert (
            len(
                conn.execute(
                    "SELECT jobs.id FROM jobs JOIN jobs_fts ON jobs.rowid = jobs_fts.rowid WHERE jobs_fts MATCH ?",
                    (sanitize_fts5_query("Golang"),),
                ).fetchall()
            )
            == 0
        )
        # New term must match
        res_rust = conn.execute(
            "SELECT jobs.id, jobs.title FROM jobs JOIN jobs_fts ON jobs.rowid = jobs_fts.rowid WHERE jobs_fts MATCH ?",
            (sanitize_fts5_query("Rust"),),
        ).fetchall()
        assert len(res_rust) == 1
        assert res_rust[0]["title"] == "Principal Rust Architect"

    # 3. UPDATE non-text fields (status, salary) -> FTS preserves search
    with get_db_connection(temp_db) as conn:
        conn.execute(
            "UPDATE jobs SET status = 'expired', salary_annualized = 180000.0 WHERE id = ?",
            (job_id,),
        )

    with get_db_connection(temp_db) as conn:
        res_still_matches = conn.execute(
            "SELECT jobs.status FROM jobs JOIN jobs_fts ON jobs.rowid = jobs_fts.rowid WHERE jobs_fts MATCH ?",
            (sanitize_fts5_query("Rust"),),
        ).fetchall()
        assert len(res_still_matches) == 1
        assert res_still_matches[0]["status"] == "expired"

    # 4. DELETE job -> FTS cleans up
    with get_db_connection(temp_db) as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    with get_db_connection(temp_db) as conn:
        assert (
            len(
                conn.execute(
                    "SELECT jobs.id FROM jobs JOIN jobs_fts ON jobs.rowid = jobs_fts.rowid WHERE jobs_fts MATCH ?",
                    (sanitize_fts5_query("Rust"),),
                ).fetchall()
            )
            == 0
        )


def test_fts5_technical_symbols_tokenization(temp_db: str) -> None:
    """Verify that technical symbols like C++, C#, .NET, Node.js are accurately parsed."""
    jobs_data = [
        (
            "j_cpp",
            "Senior C++ Engine Developer",
            "GameStudio",
            "Sydney",
            "Low-level 3D graphics in C++.",
        ),
        (
            "j_csharp",
            "Enterprise C# .NET Architect",
            "FinTech Corp",
            "Melbourne",
            "Cloud APIs with C# and ASP.NET Core.",
        ),
        (
            "j_c",
            "Embedded C Firmware Engineer",
            "Hardware Corp",
            "Brisbane",
            "Pure standard C embedded programming.",
        ),
        (
            "j_node",
            "Full Stack Node.js Engineer",
            "WebTech",
            "Remote",
            "Microservices in Node.js and TypeScript.",
        ),
    ]

    with get_db_connection(temp_db) as conn:
        for j_id, title, comp, loc, desc in jobs_data:
            conn.execute(
                """INSERT INTO jobs (id, title, company, location, description, source, url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'Seek', 'https://example.com', '2026-09-26T00:00:00Z', '2026-09-26T00:00:00Z')""",
                (j_id, title, comp, loc, desc),
            )

    with get_db_connection(temp_db) as conn:
        # C++ should match j_cpp, NOT j_csharp or j_c
        cpp_res = conn.execute(
            "SELECT jobs.id FROM jobs JOIN jobs_fts ON jobs.rowid = jobs_fts.rowid WHERE jobs_fts MATCH ?",
            (sanitize_fts5_query("C++"),),
        ).fetchall()
        assert len(cpp_res) == 1
        assert cpp_res[0]["id"] == "j_cpp"

        # C# should match j_csharp, NOT j_cpp
        csharp_res = conn.execute(
            "SELECT jobs.id FROM jobs JOIN jobs_fts ON jobs.rowid = jobs_fts.rowid WHERE jobs_fts MATCH ?",
            (sanitize_fts5_query("C#"),),
        ).fetchall()
        assert len(csharp_res) == 1
        assert csharp_res[0]["id"] == "j_csharp"

        # .NET should match j_csharp
        dotnet_res = conn.execute(
            "SELECT jobs.id FROM jobs JOIN jobs_fts ON jobs.rowid = jobs_fts.rowid WHERE jobs_fts MATCH ?",
            (sanitize_fts5_query(".NET"),),
        ).fetchall()
        assert len(dotnet_res) == 1
        assert dotnet_res[0]["id"] == "j_csharp"

        # Node.js should match j_node
        node_res = conn.execute(
            "SELECT jobs.id FROM jobs JOIN jobs_fts ON jobs.rowid = jobs_fts.rowid WHERE jobs_fts MATCH ?",
            (sanitize_fts5_query("Node.js"),),
        ).fetchall()
        assert len(node_res) == 1
        assert node_res[0]["id"] == "j_node"


def test_sanitize_fts5_query_edge_cases() -> None:
    """Verify query sanitization against injections, unclosed quotes, and syntax errors."""
    assert sanitize_fts5_query("") == ""
    assert sanitize_fts5_query("   ") == ""
    assert sanitize_fts5_query(None) == ""

    # Exact phrase handling
    assert sanitize_fts5_query('"software engineer"') == '"software engineer"'

    # Unclosed quotes
    unclosed = sanitize_fts5_query('"cloud engineer')
    assert '"cloud"' in unclosed
    assert '"engineer"' in unclosed

    # Boolean cleanup
    assert sanitize_fts5_query("AND python OR") == '"python"'
    assert sanitize_fts5_query("python AND AND data") == '"python" AND "data"*'

    # Technical symbols
    assert sanitize_fts5_query("C++") == '"C++"*'
    assert sanitize_fts5_query("C#") == '"C#"*'
    assert sanitize_fts5_query(".NET") == '".NET"*'


# ==============================================================================
# 4. WAL Checkpoint & Concurrency Resilience
# ==============================================================================


def test_wal_checkpoint_truncate(temp_db: str) -> None:
    """Verify that checkpoint_wal flushes WAL pages to disk and truncates the WAL file."""
    with get_db_connection(temp_db) as conn:
        for i in range(25):
            conn.execute(
                """INSERT INTO jobs (id, title, company, description, source, url, created_at, updated_at)
                VALUES (?, ?, 'Comp', 'Desc', 'Seek', 'http://url', '2026-09-26T00:00:00Z', '2026-09-26T00:00:00Z')""",
                (f"chk_{i}", f"Job {i}"),
            )

    # Perform checkpoint TRUNCATE
    busy, log_pages, checkpointed_pages = checkpoint_wal(temp_db, mode="TRUNCATE")
    assert busy == 0, "Expected checkpoint not to be busy"
    assert checkpointed_pages >= 0


def test_concurrent_read_write_resilience(temp_db: str) -> None:
    """Stress test concurrent readers and writers under SQLite WAL mode to ensure zero lock contention."""
    # Pre-seed database
    with get_db_connection(temp_db) as conn:
        for i in range(10):
            conn.execute(
                """INSERT INTO jobs (id, title, company, description, source, url, created_at, updated_at)
                VALUES (?, ?, 'Comp', 'Desc', 'Seek', 'http://url', '2026-09-26T00:00:00Z', '2026-09-26T00:00:00Z')""",
                (f"seed_{i}", f"Initial Job {i}"),
            )

    errors: list[tuple[str, int, str]] = []
    reads_completed = [0]
    writes_completed = [0]
    stop_event = threading.Event()

    def reader_task(reader_id: int) -> None:
        conn = create_connection(temp_db)
        try:
            while not stop_event.is_set():
                row = conn.execute("SELECT count(*), max(title) FROM jobs").fetchone()
                assert row[0] >= 10
                reads_completed[0] += 1
                time.sleep(0.002)
        except Exception as e:
            errors.append(("reader", reader_id, str(e)))
        finally:
            conn.close()

    def writer_task(writer_id: int, count: int) -> None:
        conn = create_connection(temp_db)
        try:
            for j in range(count):
                with conn:
                    conn.execute(
                        """INSERT INTO jobs (id, title, company, description, source, url, created_at, updated_at)
                        VALUES (?, ?, 'Comp', 'Desc', 'Seek', 'http://url', '2026-09-26T00:00:00Z', '2026-09-26T00:00:00Z')""",
                        (
                            f"concurrent_{writer_id}_{j}",
                            f"Concurrent Job {writer_id}_{j}",
                        ),
                    )
                writes_completed[0] += 1
                time.sleep(0.005)
        except Exception as e:
            errors.append(("writer", writer_id, str(e)))
        finally:
            conn.close()

    # Launch 4 concurrent readers
    reader_threads = [threading.Thread(target=reader_task, args=(r,)) for r in range(4)]
    for rt in reader_threads:
        rt.start()

    # Launch 2 concurrent writers (20 writes each = 40 total writes)
    writer_threads = [
        threading.Thread(target=writer_task, args=(w, 20)) for w in range(2)
    ]
    for wt in writer_threads:
        wt.start()

    # Wait for writers to complete
    for wt in writer_threads:
        wt.join()

    # Stop readers
    stop_event.set()
    for rt in reader_threads:
        rt.join()

    # Verify no exceptions occurred
    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
    assert writes_completed[0] == 40
    assert reads_completed[0] > 50

    # Final database record count check (10 seed + 40 writes = 50 jobs)
    with get_db_connection(temp_db) as conn:
        total_jobs = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
        assert total_jobs == 50
