"""
Unit tests for ScrapeCoordinator: single-flight coalescing and database-first priority.
"""

import asyncio

from job_dashboard_light.database import get_db_connection, init_db
from job_dashboard_light.models import Job, NormalizedJob, SearchQuery
from job_dashboard_light.scrapers.base import BaseJobSource
from job_dashboard_light.services.coordinator import ScrapeCoordinator


class MockSource(BaseJobSource):
    source_name = "MockSource"

    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self.call_count = 0

    async def search(self, query: SearchQuery) -> list[NormalizedJob]:
        self.call_count += 1
        await asyncio.sleep(self.delay)
        return [
            NormalizedJob(
                id=f"mock_{self.call_count}",
                title=f"{query.term} Specialist",
                company="Mock Australia Pty Ltd",
                location=query.location,
                description=f"Great opportunity for a {query.term} expert.",
                source="MockSource",
                url=f"https://mock.com.au/job/{self.call_count}",
            )
        ]

    async def get_details(self, job_id: str, url: str):
        return None

    async def check_expired(self, job_id: str, url: str) -> bool:
        return False

    async def health_check(self):
        return None


def test_single_flight_coalescing(tmp_path):
    async def run_test():
        db_file = tmp_path / "test_coalesce.sqlite3"
        init_db(db_file)

        mock_src = MockSource(delay=0.1)
        coordinator = ScrapeCoordinator(
            db_path=str(db_file),
            sources=[mock_src],
            min_pacing_seconds=0.0,
        )

        query = SearchQuery(term="DevOps", location="Sydney")

        t1 = asyncio.create_task(coordinator.search_and_ingest(query, force=True))
        t2 = asyncio.create_task(coordinator.search_and_ingest(query, force=True))
        t3 = asyncio.create_task(coordinator.search_and_ingest(query, force=True))

        results = await asyncio.gather(t1, t2, t3)

        assert len(results[0]) == 1
        assert results[0][0].title == "DevOps Specialist"
        assert results[0] == results[1] == results[2]
        assert mock_src.call_count == 1

    asyncio.run(run_test())


def test_database_first_sufficiency(tmp_path):
    async def run_test():
        db_file = tmp_path / "test_db_first.sqlite3"
        init_db(db_file)

        mock_src = MockSource(delay=0.0)
        coordinator = ScrapeCoordinator(
            db_path=str(db_file),
            sources=[mock_src],
            min_pacing_seconds=0.0,
        )

        with get_db_connection(str(db_file)) as conn:
            for i in range(12):
                job = Job(
                    id=f"cached_eng_{i}",
                    title=f"Senior Software Engineer {i}",
                    company="Seed Corp",
                    location="Melbourne",
                    description="Developing scalable backend systems.",
                    posted_date="2026-09-24T00:00:00Z",
                    posted_age_days=2,
                    source="Seek",
                    url=f"https://seek.com.au/job/{i}",
                    status="active",
                )
                conn.execute(
                    """
                    INSERT INTO jobs (id, title, company, location, description, source, url, status, posted_age_days, posted_date, created_at, updated_at)
                    VALUES (:id, :title, :company, :location, :description, :source, :url, :status, :posted_age_days, :posted_date, :created_at, :updated_at)
                    """,
                    job.to_db_row(),
                )

        query = SearchQuery(term="Engineer", location="Melbourne")
        results = await coordinator.search_and_ingest(query, force=False)
        assert len(results) >= 10
        assert mock_src.call_count == 0

    asyncio.run(run_test())
