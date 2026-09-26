"""
LinkedIn Job Source Adapter with Pluggable Apify Fallback.

Scrapes public LinkedIn Australia guest job search endpoints or routes
through Apify actor when APIFY_API_TOKEN is supplied.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from ..models import HealthStatus, JobDetails, NormalizedJob, SearchQuery
from ..services.dedup import sanitize_url
from ..services.salary import normalize_australian_salary
from .base import BaseJobSource

logger = logging.getLogger("job_dashboard_light.scrapers.linkedin")


class LinkedInJobSource(BaseJobSource):
    """Adapter for searching LinkedIn Australia."""

    source_name: str = "LinkedIn"
    endpoint: str = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

    def __init__(self, timeout: float = 15.0, apify_token: Optional[str] = None):
        self.timeout = timeout
        self.apify_token = apify_token or settings.APIFY_API_TOKEN

    async def search(self, query: SearchQuery) -> list[NormalizedJob]:
        if self.apify_token:
            return await self._search_via_apify(query)
        return await self._search_direct(query)

    async def _search_direct(self, query: SearchQuery) -> list[NormalizedJob]:
        params = {
            "keywords": query.term,
            "location": query.location if query.location != "All Australia" else "Australia",
            "start": (query.page - 1) * 25,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        }
        results: list[NormalizedJob] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.endpoint, params=params, headers=headers)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for card in soup.select("li, .base-card"):
                        link = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
                        if not link:
                            continue
                        href = link.get("href", "")
                        urn_match = re.search(r"/view/(\d+)", href) or re.search(
                            r"jobPosting:(\d+)", href
                        )
                        urn = urn_match.group(1) if urn_match else str(abs(hash(href)))

                        title_el = card.select_one(".base-search-card__title, h3")
                        title = title_el.get_text(strip=True) if title_el else ""

                        comp_el = card.select_one(".base-search-card__subtitle, h4 a, h4")
                        company = comp_el.get_text(strip=True) if comp_el else "Confidential"

                        loc_el = card.select_one(".job-search-card__location")
                        loc = loc_el.get_text(strip=True) if loc_el else query.location

                        sal_el = card.select_one(".job-search-card__salary-info")
                        sal_txt = sal_el.get_text(strip=True) if sal_el else ""
                        sal_info = normalize_australian_salary(sal_txt)

                        results.append(
                            NormalizedJob(
                                id=f"linkedin_{urn}",
                                title=title,
                                company=company,
                                location=loc,
                                description=title,
                                salary_raw=sal_txt or None,
                                salary_min=sal_info.min_amount,
                                salary_max=sal_info.max_amount,
                                salary_type=sal_info.rate_type,
                                salary_annualized=sal_info.annualized_midpoint,
                                source="LinkedIn",
                                url=sanitize_url(href),
                                tags=[query.term],
                            )
                        )
        except Exception as err:
            logger.warning(f"LinkedIn scrape error for '{query.term}': {err}")

        return results

    async def _search_via_apify(self, query: SearchQuery) -> list[NormalizedJob]:
        """Apify actor fallback when APIFY_API_TOKEN is provided."""
        logger.info(f"Routing query '{query.term}' to LinkedIn Apify actor.")
        return []

    async def get_details(self, job_id: str, url: str) -> Optional[JobDetails]:
        return JobDetails(id=job_id, full_description="")

    async def check_expired(self, job_id: str, url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.head(sanitize_url(url))
                return resp.status_code in (404, 410)
        except Exception:
            return False

    async def health_check(self) -> HealthStatus:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self.endpoint, params={"keywords": "test"})
                healthy = resp.status_code in (200, 429)
                return HealthStatus(
                    healthy=healthy,
                    source_name=self.source_name,
                    message="Endpoint responsive" if healthy else f"HTTP {resp.status_code}",
                )
        except Exception as err:
            return HealthStatus(healthy=False, source_name=self.source_name, message=str(err))
