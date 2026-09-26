"""
Adzuna Australia Job Source Adapter for Job Dashboard Light.

Integrates with Adzuna's official REST API (v1) using APP ID and APP KEY.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from ..config import settings
from ..models import HealthStatus, JobDetails, NormalizedJob, SearchQuery
from ..services.dedup import sanitize_url
from ..services.salary import normalize_australian_salary
from .base import BaseJobSource

logger = logging.getLogger("job_dashboard_light.scrapers.adzuna")


class AdzunaJobSource(BaseJobSource):
    """Adapter for searching Adzuna Australia."""

    source_name: str = "Adzuna"
    endpoint: str = "https://api.adzuna.com/v1/api/jobs/au/search/1"

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_key: Optional[str] = None,
        timeout: float = 15.0,
    ):
        self.app_id = app_id or settings.ADZUNA_APP_ID
        self.app_key = app_key or settings.ADZUNA_APP_KEY
        self.timeout = timeout

    async def search(self, query: SearchQuery) -> list[NormalizedJob]:
        """Query Adzuna Australia API."""
        if not self.app_id or not self.app_key:
            logger.info("Adzuna credentials not configured, skipping search.")
            return []

        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": query.page_size,
            "what": query.term,
            "where": query.location if query.location != "All Australia" else "Australia",
            "sort_by": "relevance",
            "content-type": "application/json",
        }

        results: list[NormalizedJob] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.endpoint, params=params)
                if resp.status_code == 200:
                    payload = resp.json()
                    for item in payload.get("results", []):
                        job_id = str(item.get("id") or "")
                        title = str(item.get("title") or "").strip()
                        company = str(
                            item.get("company", {}).get("display_name") or "Confidential"
                        ).strip()
                        loc = str(
                            item.get("location", {}).get("display_name") or query.location
                        ).strip()
                        desc = str(item.get("description") or "").strip()
                        url = str(item.get("redirect_url") or "").strip()
                        created = str(item.get("created") or "")

                        salary_min = item.get("salary_min")
                        salary_max = item.get("salary_max")
                        salary_raw = ""
                        if salary_min or salary_max:
                            salary_raw = f"${salary_min or 0} - ${salary_max or 0}"

                        salary_info = normalize_australian_salary(salary_raw)

                        results.append(
                            NormalizedJob(
                                id=f"adzuna_{job_id}",
                                title=title,
                                company=company,
                                location=loc,
                                description=desc,
                                salary_raw=salary_raw or None,
                                salary_min=salary_info.min_amount or salary_min,
                                salary_max=salary_info.max_amount or salary_max,
                                salary_type=salary_info.rate_type,
                                salary_annualized=salary_info.annualized_midpoint,
                                posted_date=created or None,
                                source="Adzuna",
                                url=sanitize_url(url),
                                tags=[query.term],
                            )
                        )
        except Exception as err:
            logger.warning(f"Adzuna query failed for '{query.term}': {err}")

        return results

    async def get_details(self, job_id: str, url: str) -> Optional[JobDetails]:
        """Fetch Adzuna job details."""
        return JobDetails(id=job_id, full_description="")

    async def check_expired(self, job_id: str, url: str) -> bool:
        """Check if Adzuna redirect link is expired."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.head(sanitize_url(url))
                return resp.status_code in (404, 410)
        except Exception:
            return False

    async def health_check(self) -> HealthStatus:
        """Verify Adzuna API health."""
        if not self.app_id or not self.app_key:
            return HealthStatus(
                healthy=True,
                source_name=self.source_name,
                message="Adzuna unconfigured (optional)",
            )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    self.endpoint,
                    params={
                        "app_id": self.app_id,
                        "app_key": self.app_key,
                        "results_per_page": 1,
                        "what": "test",
                    },
                )
                healthy = resp.status_code == 200
                return HealthStatus(
                    healthy=healthy,
                    source_name=self.source_name,
                    message="Endpoint responsive" if healthy else f"HTTP {resp.status_code}",
                )
        except Exception as err:
            return HealthStatus(healthy=False, source_name=self.source_name, message=str(err))
