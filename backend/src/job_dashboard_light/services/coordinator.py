"""
Scraper Coordinator Service with Single-Flight Coalescing and Database-First Priority.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from typing import Dict, List, Optional

from ..database import get_db_connection, sanitize_fts5_query
from ..models import Job, NormalizedJob, SearchQuery
from ..scrapers.adzuna import AdzunaJobSource
from ..scrapers.aps_jobs import APSJobsJobSource
from ..scrapers.base import BaseJobSource
from ..scrapers.careers_vic import CareersVicJobSource
from ..scrapers.indeed import IndeedJobSource
from ..scrapers.linkedin import LinkedInJobSource
from ..scrapers.seek import SeekJobSource
from .dedup import compute_job_dedup_hash, sanitize_url

logger = logging.getLogger("job_dashboard_light.services.coordinator")


class ScrapeCoordinator:
    """Coordinates multi-source scraping with caching and single-flight dispatch."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        sources: Optional[List[BaseJobSource]] = None,
        min_pacing_seconds: float = 2.0,
    ):
        self.db_path = db_path
        self.min_pacing_seconds = min_pacing_seconds
        self.last_scrape_timestamp = 0.0

        self.sources: List[BaseJobSource] = sources or [
            SeekJobSource(),
            AdzunaJobSource(),
            CareersVicJobSource(),
            APSJobsJobSource(),
            IndeedJobSource(),
            LinkedInJobSource(),
        ]

        self._in_flight: Dict[str, asyncio.Future[List[Job]]] = {}
        self._lock = asyncio.Lock()

    def _query_key(self, query: SearchQuery) -> str:
        return f"{query.term.strip().lower()}::{query.location.strip().lower()}"

    def check_database_sufficiency(
        self, query: SearchQuery, min_jobs: int = 10, max_age_days: int = 21
    ) -> List[Job]:
        """Check if database contains sufficient fresh jobs before scraping."""
        fts_query = sanitize_fts5_query(query.term)
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            rows = []
            if fts_query:
                sql = """
                    SELECT j.* FROM jobs j
                    JOIN jobs_fts f ON j.rowid = f.rowid
                    WHERE jobs_fts MATCH ?
                      AND j.status = 'active'
                      AND (j.posted_age_days IS NULL OR j.posted_age_days <= ?)
                    ORDER BY j.posted_date DESC
                    LIMIT 50;
                """
                try:
                    cursor.execute(sql, (fts_query, max_age_days))
                    rows = cursor.fetchall()
                except sqlite3.OperationalError:
                    rows = []

            if not rows:
                pattern = f"%{query.term}%"
                cursor.execute(
                    """
                    SELECT * FROM jobs
                    WHERE (title LIKE ? OR description LIKE ?)
                      AND status = 'active'
                      AND (posted_age_days IS NULL OR posted_age_days <= ?)
                    ORDER BY posted_date DESC
                    LIMIT 50;
                    """,
                    (pattern, pattern, max_age_days),
                )
                rows = cursor.fetchall()

            jobs = [Job(**dict(r)) for r in rows]
            return jobs if len(jobs) >= min_jobs else []

    async def search_and_ingest(self, query: SearchQuery, force: bool = False) -> List[Job]:
        """Execute coordinated search, coalescing concurrent identical requests."""
        if not force:
            cached_jobs = self.check_database_sufficiency(query)
            if cached_jobs:
                logger.info(f"Database hit: found {len(cached_jobs)} fresh jobs for '{query.term}'")
                return cached_jobs

        key = self._query_key(query)
        async with self._lock:
            if key in self._in_flight:
                logger.info(f"Coalescing query '{query.term}' on in-flight future.")
                return await self._in_flight[key]

            loop = asyncio.get_running_loop()
            fut: asyncio.Future[List[Job]] = loop.create_future()
            self._in_flight[key] = fut

        try:
            now = time.monotonic()
            elapsed = now - self.last_scrape_timestamp
            if elapsed < self.min_pacing_seconds:
                await asyncio.sleep(self.min_pacing_seconds - elapsed)
            self.last_scrape_timestamp = time.monotonic()

            tasks = [s.search(query) for s in self.sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_normalized: List[NormalizedJob] = []
            for res in results:
                if isinstance(res, list):
                    all_normalized.extend(res)
                elif isinstance(res, Exception):
                    logger.warning(f"Scraper error: {res}")

            saved_jobs = self._persist_jobs(all_normalized, query)
            fut.set_result(saved_jobs)
            return saved_jobs
        except Exception as exc:
            fut.set_exception(exc)
            raise
        finally:
            async with self._lock:
                self._in_flight.pop(key, None)

    def _persist_jobs(self, normalized_jobs: List[NormalizedJob], query: SearchQuery) -> List[Job]:
        """Deduplicate and insert/update jobs in SQLite."""
        saved_jobs: List[Job] = []
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            for nj in normalized_jobs:
                clean_url = sanitize_url(nj.url)
                dedup_hash = compute_job_dedup_hash(nj.company, nj.title, clean_url)
                job_id = f"job_{dedup_hash}"

                if query.exclude_terms:
                    text_blob = f"{nj.title} {nj.description}".lower()
                    if any(exc.lower() in text_blob for exc in query.exclude_terms):
                        continue

                job = Job(
                    id=job_id,
                    title=nj.title,
                    company=nj.company,
                    location=nj.location,
                    description=nj.description,
                    salary_raw=nj.salary_raw,
                    salary_min=nj.salary_min,
                    salary_max=nj.salary_max,
                    salary_type=nj.salary_type,
                    salary_annualized=nj.salary_annualized,
                    posted_date=nj.posted_date,
                    posted_age_days=nj.posted_age_days,
                    closing_date=nj.closing_date,
                    source=nj.source,
                    url=clean_url,
                    tags=nj.tags,
                    status="active",
                )

                cursor.execute(
                    """
                    INSERT INTO jobs (
                        id, title, company, location, description,
                        salary_raw, salary_min, salary_max, salary_type, salary_annualized,
                        posted_date, posted_age_days, closing_date, source, url, tags, status,
                        created_at, updated_at
                    ) VALUES (
                        :id, :title, :company, :location, :description,
                        :salary_raw, :salary_min, :salary_max, :salary_type, :salary_annualized,
                        :posted_date, :posted_age_days, :closing_date, :source, :url, :tags, :status,
                        :created_at, :updated_at
                    )
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        company = excluded.company,
                        location = excluded.location,
                        description = excluded.description,
                        salary_raw = COALESCE(excluded.salary_raw, jobs.salary_raw),
                        salary_annualized = COALESCE(excluded.salary_annualized, jobs.salary_annualized),
                        updated_at = excluded.updated_at;
                    """,
                    job.to_db_row(),
                )
                saved_jobs.append(job)

        return saved_jobs
