"""
Opaque Blob Storage Service for Job Dashboard Light.

Provides resilient backup, restore, and snapshotting of the primary SQLite
database (`jobs.sqlite3`) to Google Cloud Storage (GCS) with:
1. SQLite WAL Checkpoint (TRUNCATE) before upload for 100% ACID consistency.
2. GCS Object Generation matching (`if_generation_match`) for optimistic concurrency.
3. Safe fallback to local disk storage when GCS is unreachable or unconfigured.
4. Automatic cleanup of stale `-wal` and `-shm` auxiliary files on restore.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("job_dashboard_light.storage")

DEFAULT_BUCKET = "acaa-agent-job-dashboard-light-data"
DEFAULT_DB_FILENAME = "jobs.sqlite3"


@dataclass
class StorageResult:
    """Outcome of a storage backup, restore, or snapshot operation."""

    success: bool
    bytes_transferred: int = 0
    generation: Optional[int] = None
    conflict: bool = False
    message: str = ""
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class StorageStatus:
    """Status metadata for local and remote storage layers."""

    gcs_configured: bool
    bucket_name: Optional[str]
    accessible: bool
    local_db_exists: bool
    local_db_size_bytes: int
    local_db_modified: Optional[str]
    remote_blob_exists: bool
    remote_generation: Optional[int]
    last_synced_generation: Optional[int]
    status_message: str


class StorageService:
    """Manages SQLite opaque blob backups to Google Cloud Storage."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        data_dir: Optional[Path | str] = None,
        db_filename: str = DEFAULT_DB_FILENAME,
    ) -> None:
        self.bucket_name = (
            bucket_name
            if bucket_name is not None
            else os.environ.get("JOB_DASHBOARD_GCS_DATA_BUCKET", DEFAULT_BUCKET)
        )
        if data_dir is not None:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(os.environ.get("JOB_DASHBOARD_DATA_DIR", "/app/data"))
        self.db_filename = db_filename
        self.last_known_generation: Optional[int] = None
        self._client: Any = None
        self._client_initialized: bool = False

    @property
    def db_path(self) -> Path:
        """Absolute path to the local primary SQLite database file."""
        return self.data_dir / self.db_filename

    def _get_client(self) -> Any:
        """
        Lazily initialize and return the GCS client.

        Returns None with a logged warning if google-cloud-storage is missing,
        credentials cannot be resolved, or client construction fails.
        """
        if self._client_initialized:
            return self._client

        self._client_initialized = True
        try:
            from google.cloud import storage  # type: ignore[import-untyped]
        except ImportError:
            logger.warning(
                "google-cloud-storage library not installed; operating in local-only disk storage mode."
            )
            self._client = None
            return None

        try:
            self._client = storage.Client()
            return self._client
        except Exception as err:
            logger.warning(
                "GCS client initialization failed (e.g. missing GCP credentials in local dev mode): %s. "
                "Operating in local-only disk storage mode.",
                err,
            )
            self._client = None
            return None

    def checkpoint_wal(self, timeout_sec: float = 10.0) -> tuple[int, int, int]:
        """
        Execute `PRAGMA wal_checkpoint(TRUNCATE)` on the local SQLite database.

        Flushes all uncheckpointed WAL pages into the main .sqlite3 file and
        truncates the WAL file to 0 bytes. Returns (busy, log, checkpointed).
        """
        if not self.db_path.exists():
            logger.debug(
                "Database file %s does not exist; skipping WAL checkpoint.",
                self.db_path,
            )
            return (0, 0, 0)

        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=timeout_sec)
            cursor = conn.cursor()
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            row = cursor.fetchone()
            if row:
                busy, log_pages, ckpt_pages = int(row[0]), int(row[1]), int(row[2])
                if busy != 0:
                    logger.warning(
                        "WAL checkpoint TRUNCATE blocked by concurrent reader/writer (busy=%d, log=%d, ckpt=%d)",
                        busy,
                        log_pages,
                        ckpt_pages,
                    )
                else:
                    logger.info(
                        "WAL checkpoint TRUNCATE completed successfully (log=%d, ckpt=%d)",
                        log_pages,
                        ckpt_pages,
                    )
                return (busy, log_pages, ckpt_pages)
            return (0, 0, 0)
        except Exception as err:
            logger.warning("Error executing PRAGMA wal_checkpoint(TRUNCATE): %s", err)
            return (1, 0, 0)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def backup_database(
        self,
        force: bool = False,
        checkpoint: bool = True,
    ) -> StorageResult:
        """
        Snapshot local SQLite database and upload to GCS as an opaque blob.

        Parameters:
            force: If True, bypasses generation match check (last-write-wins).
            checkpoint: If True, executes PRAGMA wal_checkpoint(TRUNCATE) before upload.
        """
        if not self.bucket_name:
            logger.info("JOB_DASHBOARD_GCS_DATA_BUCKET not configured; backup skipped.")
            return StorageResult(
                success=True,
                message="GCS bucket not configured; local disk state preserved.",
            )

        if not self.db_path.exists():
            logger.warning(
                "Local database file %s not found; skipping GCS backup.",
                self.db_path,
            )
            return StorageResult(
                success=False,
                error="file_not_found",
                message=f"Local database {self.db_path} does not exist.",
            )

        # 1. Flush WAL into main database file
        if checkpoint:
            self.checkpoint_wal()

        # 2. Acquire GCS client
        client = self._get_client()
        if client is None:
            logger.warning(
                "GCS client unavailable; database backup preserved on local disk only."
            )
            return StorageResult(
                success=True,
                message="GCS client unavailable; local disk storage active.",
            )

        # 3. Perform generation-checked upload
        try:
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(self.db_filename)

            generation_match = None
            if not force:
                if self.last_known_generation is not None:
                    generation_match = self.last_known_generation
                else:
                    try:
                        blob.reload()
                        generation_match = blob.generation
                    except Exception as reload_err:
                        # Blob does not exist yet; precondition 0 asserts non-existence
                        generation_match = 0
                        logger.debug(
                            "Remote blob does not exist yet; asserting generation 0: %s",
                            reload_err,
                        )

            # Upload with optimistic concurrency guard
            blob.upload_from_filename(
                str(self.db_path),
                if_generation_match=generation_match,
            )

            new_generation = getattr(blob, "generation", None)
            self.last_known_generation = new_generation
            file_size = self.db_path.stat().st_size

            logger.info(
                "Successfully backed up %s (%d bytes) to gs://%s/%s [gen: %s]",
                self.db_filename,
                file_size,
                self.bucket_name,
                self.db_filename,
                new_generation,
            )
            return StorageResult(
                success=True,
                bytes_transferred=file_size,
                generation=new_generation,
                message=f"Backed up to gs://{self.bucket_name}/{self.db_filename}",
            )

        except Exception as upload_err:
            err_str = str(upload_err)
            # Detect HTTP 412 Precondition Failed
            is_precondition_failed = (
                "PreconditionFailed" in type(upload_err).__name__
                or "412" in err_str
                or "conditionNotMet" in err_str
            )
            if is_precondition_failed:
                logger.warning(
                    "GCS optimistic concurrency check failed for %s (generation mismatch): %s. "
                    "Another instance has written newer data. Aborting upload to prevent overwrite.",
                    self.db_filename,
                    upload_err,
                )
                return StorageResult(
                    success=False,
                    conflict=True,
                    error="generation_mismatch",
                    message="Optimistic concurrency conflict: remote blob has a newer generation.",
                )

            logger.warning(
                "GCS backup failed (%s); local database remains safe on disk: %s",
                type(upload_err).__name__,
                upload_err,
            )
            return StorageResult(
                success=False,
                error=type(upload_err).__name__,
                message=f"GCS backup error: {upload_err}",
            )

    def restore_database(
        self,
        overwrite_local: bool = False,
    ) -> StorageResult:
        """
        Download primary SQLite database from GCS into local data_dir.

        If overwrite_local is False and local db exists, the restore is skipped.
        On restore, stale auxiliary -wal and -shm files are removed to prevent
        corrupted recovery against mismatched WAL logs.
        """
        if not self.bucket_name:
            logger.info(
                "JOB_DASHBOARD_GCS_DATA_BUCKET not configured; restore skipped."
            )
            return StorageResult(
                success=True,
                message="GCS bucket not configured; using local disk database.",
            )

        if not overwrite_local and self.db_path.exists():
            logger.info(
                "Local database %s already exists; skipping GCS restore.",
                self.db_path,
            )
            return StorageResult(
                success=True,
                message=f"Local database already exists at {self.db_path}.",
            )

        client = self._get_client()
        if client is None:
            logger.warning(
                "GCS client unavailable; starting with local/empty database."
            )
            return StorageResult(
                success=True,
                message="GCS client unavailable; proceeding with local disk storage.",
            )

        try:
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(self.db_filename)

            if not blob.exists():
                logger.info(
                    "No remote database found at gs://%s/%s; starting fresh.",
                    self.bucket_name,
                    self.db_filename,
                )
                return StorageResult(
                    success=True,
                    message="Remote blob does not exist; initialized fresh local database.",
                )

            self.data_dir.mkdir(parents=True, exist_ok=True)

            # CRITICAL: Clean up stale -wal and -shm files before downloading fresh db
            wal_path = self.data_dir / f"{self.db_filename}-wal"
            shm_path = self.data_dir / f"{self.db_filename}-shm"
            if wal_path.exists():
                wal_path.unlink()
                logger.debug("Removed stale WAL file: %s", wal_path)
            if shm_path.exists():
                shm_path.unlink()
                logger.debug("Removed stale SHM file: %s", shm_path)

            blob.download_to_filename(str(self.db_path))
            blob.reload()
            self.last_known_generation = getattr(blob, "generation", None)
            file_size = self.db_path.stat().st_size

            logger.info(
                "Successfully restored %s (%d bytes) from gs://%s/%s [gen: %s]",
                self.db_filename,
                file_size,
                self.bucket_name,
                self.db_filename,
                self.last_known_generation,
            )
            return StorageResult(
                success=True,
                bytes_transferred=file_size,
                generation=self.last_known_generation,
                message=f"Restored from gs://{self.bucket_name}/{self.db_filename}",
            )

        except Exception as restore_err:
            logger.warning(
                "GCS restore failed (%s): %s. Starting with local disk state.",
                type(restore_err).__name__,
                restore_err,
            )
            return StorageResult(
                success=False,
                error=type(restore_err).__name__,
                message=f"GCS restore error: {restore_err}",
            )

    def create_snapshot(
        self,
        tag: Optional[str] = None,
    ) -> StorageResult:
        """
        Upload a point-in-time timestamped snapshot of the SQLite database to GCS.
        Target path: snapshots/jobs_<iso_timestamp>[_<tag>].sqlite3
        """
        if not self.bucket_name:
            return StorageResult(
                success=True,
                message="GCS bucket not configured; snapshot skipped.",
            )

        if not self.db_path.exists():
            return StorageResult(
                success=False,
                error="file_not_found",
                message=f"Local database {self.db_path} does not exist.",
            )

        # Checkpoint WAL first
        self.checkpoint_wal()

        client = self._get_client()
        if client is None:
            return StorageResult(
                success=True,
                message="GCS client unavailable; snapshot skipped.",
            )

        try:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
            suffix = f"_{tag}" if tag else ""
            snapshot_filename = f"snapshots/jobs_{now_str}{suffix}.sqlite3"

            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(snapshot_filename)
            blob.upload_from_filename(str(self.db_path))

            file_size = self.db_path.stat().st_size
            logger.info(
                "Created timestamped snapshot at gs://%s/%s (%d bytes)",
                self.bucket_name,
                snapshot_filename,
                file_size,
            )
            return StorageResult(
                success=True,
                bytes_transferred=file_size,
                generation=getattr(blob, "generation", None),
                message=f"Created snapshot gs://{self.bucket_name}/{snapshot_filename}",
            )
        except Exception as err:
            logger.warning("GCS snapshot creation failed: %s", err)
            return StorageResult(
                success=False,
                error=type(err).__name__,
                message=f"Snapshot error: {err}",
            )

    def get_status(self) -> StorageStatus:
        """Inspect and return current local and remote storage status."""
        gcs_configured = bool(self.bucket_name)
        accessible = False
        remote_blob_exists = False
        remote_gen = None
        status_msg = "Local disk storage active."

        local_exists = self.db_path.exists()
        local_size = self.db_path.stat().st_size if local_exists else 0
        local_mtime = (
            datetime.fromtimestamp(
                self.db_path.stat().st_mtime, tz=timezone.utc
            ).isoformat()
            if local_exists
            else None
        )

        if gcs_configured:
            client = self._get_client()
            if client is not None:
                try:
                    bucket = client.bucket(self.bucket_name)
                    blob = bucket.blob(self.db_filename)
                    if blob.exists():
                        remote_blob_exists = True
                        blob.reload()
                        remote_gen = getattr(blob, "generation", None)
                    accessible = True
                    status_msg = "GCS bucket accessible."
                except Exception as err:
                    status_msg = f"GCS inaccessible: {err}"
            else:
                status_msg = "GCS client unavailable (local dev mode)."

        return StorageStatus(
            gcs_configured=gcs_configured,
            bucket_name=self.bucket_name,
            accessible=accessible,
            local_db_exists=local_exists,
            local_db_size_bytes=local_size,
            local_db_modified=local_mtime,
            remote_blob_exists=remote_blob_exists,
            remote_generation=remote_gen,
            last_synced_generation=self.last_known_generation,
            status_message=status_msg,
        )


# Global singleton instance and accessors
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Return or initialize the process-wide StorageService instance."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
