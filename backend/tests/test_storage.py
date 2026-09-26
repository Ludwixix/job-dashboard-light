"""
Unit tests for Job Dashboard Light StorageService with mocked GCS client.

Tests:
1. SQLite WAL checkpoint TRUNCATE flushes pages and truncates WAL to 0 bytes.
2. Initial backup with generation matching.
3. Optimistic concurrency conflict detection (HTTP 412 / PreconditionFailed).
4. Force overwrite bypasses generation matching.
5. Restore downloads database and unlinks stale -wal and -shm files.
6. Restore skips when local DB exists unless overwrite_local=True.
7. Restore begins fresh when remote blob does not exist in bucket.
8. Graceful no-op fallback when bucket is unconfigured.
9. Graceful fallback to local disk storage when GCS credentials are missing.
10. Point-in-time timestamped snapshot creation.
11. Storage status metadata introspection.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import pytest

from job_dashboard_light.services.storage import StorageService


class MockPreconditionFailed(Exception):
    """Simulates google.cloud.exceptions.PreconditionFailed (HTTP 412)."""

    pass


class MockNotFound(Exception):
    """Simulates google.cloud.exceptions.NotFound (HTTP 404)."""

    pass


class MockBlob:
    """Mock GCS Blob supporting generation tracking and conditional upload."""

    def __init__(self, name: str, generation: int = 0, exists: bool = False):
        self.name = name
        self.generation = generation
        self._exists = exists
        self.downloaded_to: list[str] = []
        self.uploaded_from: list[str] = []

    def exists(self) -> bool:
        return self._exists

    def reload(self) -> None:
        if not self._exists:
            raise MockNotFound(f"Blob {self.name} not found")

    def upload_from_filename(
        self, filename: str, if_generation_match: Optional[int] = None
    ) -> None:
        if if_generation_match is not None:
            if if_generation_match == 0 and self._exists:
                raise MockPreconditionFailed("Blob already exists (generation > 0)")
            if if_generation_match > 0:
                if not self._exists or self.generation != if_generation_match:
                    raise MockPreconditionFailed(
                        f"Generation mismatch: expected {if_generation_match}, current {self.generation}"
                    )

        self._exists = True
        self.generation = 1 if self.generation == 0 else self.generation + 1
        self.uploaded_from.append(filename)

    def download_to_filename(self, filename: str) -> None:
        if not self._exists:
            raise MockNotFound(f"Blob {self.name} not found")
        self.downloaded_to.append(filename)
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        with open(filename, "wb") as f:
            f.write(b"MOCKED_SQLITE_PERSISTED_CONTENT")


class MockBucket:
    """Mock GCS Bucket."""

    def __init__(self, name: str):
        self.name = name
        self.blobs: dict[str, MockBlob] = {}

    def blob(self, name: str) -> MockBlob:
        if name not in self.blobs:
            self.blobs[name] = MockBlob(name=name, generation=0, exists=False)
        return self.blobs[name]


class MockGCSClient:
    """Mock GCS Client."""

    def __init__(self):
        self.buckets: dict[str, MockBucket] = {}

    def bucket(self, name: str) -> MockBucket:
        if name not in self.buckets:
            self.buckets[name] = MockBucket(name=name)
        return self.buckets[name]


@pytest.fixture
def mock_gcs():
    """Provides a fresh MockGCSClient."""
    return MockGCSClient()


@pytest.fixture
def temp_service(tmp_path: Path, mock_gcs: MockGCSClient) -> StorageService:
    """Provides a StorageService configured with tmp_path and injected mock GCS client."""
    service = StorageService(
        bucket_name="acaa-agent-job-dashboard-light-data",
        data_dir=tmp_path,
        db_filename="jobs.sqlite3",
    )
    service._client = mock_gcs
    service._client_initialized = True
    return service


def test_sqlite_wal_checkpoint_truncate(tmp_path: Path):
    """Verify that checkpoint_wal flushes WAL pages and truncates the WAL file to 0 bytes."""
    service = StorageService(data_dir=tmp_path)
    db_file = service.db_path
    wal_file = tmp_path / "jobs.sqlite3-wal"

    # Keep a reader connection open to prevent SQLite from unlinking the WAL on close
    conn_keepalive = sqlite3.connect(str(db_file))
    conn_keepalive.execute("PRAGMA journal_mode=WAL;")
    conn_keepalive.execute(
        "CREATE TABLE test_data (id INTEGER PRIMARY KEY, note TEXT);"
    )
    conn_keepalive.commit()

    # Writer inserts data into WAL
    conn_writer = sqlite3.connect(str(db_file))
    conn_writer.execute("INSERT INTO test_data (note) VALUES ('job_entry_1');")
    conn_writer.commit()
    conn_writer.close()

    assert wal_file.exists(), "WAL file should exist while connection is alive"
    wal_size_before = wal_file.stat().st_size
    assert wal_size_before > 0, "WAL file should contain uncheckpointed pages"

    # Run checkpoint_wal
    busy, log, ckpt = service.checkpoint_wal()
    assert busy == 0, "Checkpoint should succeed"

    # Verify WAL file is truncated to 0 bytes
    assert wal_file.exists()
    assert wal_file.stat().st_size == 0, "WAL file must be truncated to 0 bytes"

    # Verify data in main db file
    row = conn_keepalive.execute("SELECT note FROM test_data WHERE id=1").fetchone()
    conn_keepalive.close()
    assert row[0] == "job_entry_1"


def test_backup_database_success(temp_service: StorageService, mock_gcs: MockGCSClient):
    """Verify successful backup with generation assignment."""
    # Create valid local SQLite database
    conn = sqlite3.connect(str(temp_service.db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, title TEXT);")
    conn.execute("INSERT INTO jobs VALUES ('j1', 'Senior Full Stack Engineer');")
    conn.commit()
    conn.close()

    # Initial backup to empty bucket (generation 0 match)
    res = temp_service.backup_database()

    assert res.success is True
    assert res.bytes_transferred > 0
    assert res.generation == 1  # Initial write gets generation 1
    assert temp_service.last_known_generation == 1

    bucket = mock_gcs.bucket("acaa-agent-job-dashboard-light-data")
    blob = bucket.blob("jobs.sqlite3")
    assert blob.exists() is True
    assert len(blob.uploaded_from) == 1


def test_backup_optimistic_concurrency_conflict(
    temp_service: StorageService, mock_gcs: MockGCSClient
):
    """
    Verify optimistic concurrency: If remote generation changes (another instance wrote),
    backup_database detects the conflict, logs a warning, returns conflict=True,
    and does NOT throw or crash.
    """
    conn = sqlite3.connect(str(temp_service.db_path))
    conn.execute("CREATE TABLE t (id INT);")
    conn.close()
    temp_service.last_known_generation = 100

    bucket = mock_gcs.bucket("acaa-agent-job-dashboard-light-data")
    # Simulate remote blob already updated to generation 101 by another instance
    bucket.blobs["jobs.sqlite3"] = MockBlob("jobs.sqlite3", generation=101, exists=True)

    # Attempt backup with expected generation 100
    res = temp_service.backup_database()

    assert res.success is False
    assert res.conflict is True
    assert res.error == "generation_mismatch"
    assert "Optimistic concurrency conflict" in res.message


def test_backup_force_bypasses_concurrency_check(
    temp_service: StorageService, mock_gcs: MockGCSClient
):
    """Verify that force=True bypasses the generation check."""
    conn = sqlite3.connect(str(temp_service.db_path))
    conn.execute("CREATE TABLE t (id INT);")
    conn.close()
    temp_service.last_known_generation = 100

    bucket = mock_gcs.bucket("acaa-agent-job-dashboard-light-data")
    bucket.blobs["jobs.sqlite3"] = MockBlob("jobs.sqlite3", generation=101, exists=True)

    res = temp_service.backup_database(force=True)

    assert res.success is True
    assert res.conflict is False


def test_restore_database_success_and_stale_wal_cleanup(
    temp_service: StorageService, mock_gcs: MockGCSClient
):
    """
    Verify restore downloads jobs.sqlite3 and purges stale -wal and -shm files.
    """
    # Seed remote blob
    bucket = mock_gcs.bucket("acaa-agent-job-dashboard-light-data")
    bucket.blobs["jobs.sqlite3"] = MockBlob("jobs.sqlite3", generation=42, exists=True)

    # Create stale local -wal and -shm files
    wal_file = temp_service.data_dir / "jobs.sqlite3-wal"
    shm_file = temp_service.data_dir / "jobs.sqlite3-shm"
    wal_file.write_bytes(b"STALE_WAL_FROM_CRASH")
    shm_file.write_bytes(b"STALE_SHM_FROM_CRASH")

    res = temp_service.restore_database(overwrite_local=True)

    assert res.success is True
    assert temp_service.last_known_generation == 42
    assert temp_service.db_path.exists()
    assert temp_service.db_path.read_bytes() == b"MOCKED_SQLITE_PERSISTED_CONTENT"

    # Stale auxiliary files must be purged
    assert not wal_file.exists(), "Stale WAL file must be removed on restore"
    assert not shm_file.exists(), "Stale SHM file must be removed on restore"


def test_restore_database_skips_when_local_exists_without_overwrite(
    temp_service: StorageService, mock_gcs: MockGCSClient
):
    """Verify restore does not overwrite local DB unless overwrite_local=True."""
    temp_service.db_path.write_bytes(b"LOCAL_EXISTING_DB")
    bucket = mock_gcs.bucket("acaa-agent-job-dashboard-light-data")
    bucket.blobs["jobs.sqlite3"] = MockBlob("jobs.sqlite3", generation=50, exists=True)

    res = temp_service.restore_database(overwrite_local=False)

    assert res.success is True
    assert "already exists" in res.message
    # Local content untouched
    assert temp_service.db_path.read_bytes() == b"LOCAL_EXISTING_DB"


def test_restore_remote_not_found_starts_fresh(
    temp_service: StorageService, mock_gcs: MockGCSClient
):
    """Verify restore starts fresh when remote blob does not exist in bucket."""
    res = temp_service.restore_database()

    assert res.success is True
    assert "fresh" in res.message
    assert not temp_service.db_path.exists()


def test_fallback_unconfigured_bucket(tmp_path: Path):
    """Verify graceful no-op when bucket name is not configured."""
    service = StorageService(bucket_name="", data_dir=tmp_path)
    res_backup = service.backup_database()
    res_restore = service.restore_database()

    assert res_backup.success is True
    assert "not configured" in res_backup.message
    assert res_restore.success is True
    assert "not configured" in res_restore.message


def test_fallback_missing_gcs_credentials(tmp_path: Path):
    """Verify safe fallback to local storage when GCP credentials cannot be resolved."""
    service = StorageService(
        bucket_name="acaa-agent-job-dashboard-light-data", data_dir=tmp_path
    )
    # Simulate client returning None (e.g. DefaultCredentialsError)
    service._client = None
    service._client_initialized = True

    service.db_path.write_bytes(b"LOCAL_DATA")

    res_backup = service.backup_database(checkpoint=False)
    res_restore = service.restore_database(overwrite_local=True)

    assert res_backup.success is True
    assert "local disk storage active" in res_backup.message
    assert res_restore.success is True
    assert "proceeding with local disk storage" in res_restore.message


def test_create_snapshot_timestamped(
    temp_service: StorageService, mock_gcs: MockGCSClient
):
    """Verify timestamped snapshot creation under snapshots/ prefix."""
    conn = sqlite3.connect(str(temp_service.db_path))
    conn.execute("CREATE TABLE t (id INT);")
    conn.close()

    res = temp_service.create_snapshot(tag="manual")

    assert res.success is True
    assert "Created snapshot" in res.message

    bucket = mock_gcs.bucket("acaa-agent-job-dashboard-light-data")
    snapshot_blobs = [k for k in bucket.blobs if k.startswith("snapshots/")]
    assert len(snapshot_blobs) == 1
    assert "manual.sqlite3" in snapshot_blobs[0]


def test_get_status_introspection(
    temp_service: StorageService, mock_gcs: MockGCSClient
):
    """Verify get_status returns structured metadata."""
    temp_service.db_path.write_bytes(b"STATUS_TEST_DATA")
    status = temp_service.get_status()

    assert status.gcs_configured is True
    assert status.bucket_name == "acaa-agent-job-dashboard-light-data"
    assert status.accessible is True
    assert status.local_db_exists is True
    assert status.local_db_size_bytes == len(b"STATUS_TEST_DATA")
