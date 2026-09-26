"""
Seek Australia Job Source Adapter for Job Dashboard Light.

Integrates with Seek's Chalice job search endpoints to ingest Australian listings.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from ..models import HealthStatus, JobDetails, NormalizedJob, SearchQuery
from ..services.dedup import sanitize_url
from ..services.salary import normalize_australian_salary
from .base import BaseJobSource

logger = logging.getLogger("job_dashboard_light.scrapers.seek")


class SeekJobSource(BaseJobSource):
    """Adapter for scraping Seek Australia listings."""

    source_name: str = "Seek"
    endpoint: str = "https://chalice-search-api.cloud.seek.com.au/search"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def search(self, query: SearchQuery) -> list[NormalizedJob]:
        """Search Seek Australia and map results to NormalizedJob."""
        params = {
            "keywords": query.term,
            "where": query.location if query.location != "All Australia" else "All Australia",
            "page": query.page,
            "pageSize": query.page_size,
            "sortMode": "KeywordRelevance",
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        }

        results: list[NormalizedJob] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.endpoint, params=params, headers=headers)
                if resp.status_code == 200:
                    payload = resp.json()
                    for item in payload.get("data", []):
                        job_id = str(item.get("id") or "")
                        title = str(item.get("title") or "").strip()
                        advertiser = item.get("advertiser", {})
                        company = str(advertiser.get("description") or "Confidential").strip()
                        location_data = item.get("locationHierarchy", {})
                        city = location_data.get("city", {}).get("description") or query.location
                        teaser = str(item.get("teaser") or "").strip()
                        salary_text = str(item.get("salary") or "").strip()
                        listing_date = str(item.get("listingDate") or "")

                        salary_info = normalize_australian_salary(salary_text)
                        url = f"https://www.seek.com.au/job/{job_id}" if job_id else ""

                        results.append(
                            NormalizedJob(
                                id=f"seek_{job_id}",
                                title=title,
                                company=company,
                                location=city,
                                description=teaser,
                                salary_raw=salary_text or None,
                                salary_min=salary_info.min_amount,
                                salary_max=salary_info.max_amount,
                                salary_type=salary_info.rate_type,
                                salary_annualized=salary_info.annualized_midpoint,
                                posted_date=listing_date or None,
                                source="Seek",
                                url=sanitize_url(url),
                                tags=[query.term],
                            )
                        )
        except Exception as err:
            logger.warning(f"Seek query failed for '{query.term}': {err}")

        return results

    async def get_details(self, job_id: str, url: str) -> Optional[JobDetails]:
        """Fetch full Seek job description."""
        numeric_id = job_id.replace("seek_", "")
        detail_endpoint = f"https://chalice-search-api.cloud.seek.com.au/jobdetails/{numeric_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(detail_endpoint)
                if resp.status_code == 200:
                    desc = resp.json().get("job", {}).get("description", "")
                    return JobDetails(id=job_id, full_description=desc)
        except Exception as err:
            logger.warning(f"Failed to fetch Seek details for {job_id}: {err}")
        return None

    async def check_expired(self, job_id: str, url: str) -> bool:
        """Check if Seek job listing is expired."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.head(sanitize_url(url))
                return resp.status_code in (404, 410) or "/job/" not in str(resp.url)
        except Exception:
            return False

    async def health_check(self) -> HealthStatus:
        """Verify Seek search API accessibility."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.endpoint}?keywords=test&pageSize=1")
                healthy = resp.status_code in (200, 403)
                return HealthStatus(
                    healthy=healthy,
                    source_name=self.source_name,
                    message="Endpoint responsive" if healthy else f"HTTP {resp.status_code}",
                )
        except Exception as err:
            return HealthStatus(healthy=False, source_name=self.source_name, message=str(err))
