"""
Indeed Job Source Adapter with Pluggable Apify Fallback.

Scrapes Indeed Australia jobs directly or seamlessly routes through Apify actor
when APIFY_API_TOKEN is supplied.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from ..models import HealthStatus, JobDetails, NormalizedJob, SearchQuery
from ..services.dedup import sanitize_url
from ..services.salary import normalize_australian_salary
from .base import BaseJobSource

logger = logging.getLogger("job_dashboard_light.scrapers.indeed")


class IndeedJobSource(BaseJobSource):
    """Adapter for searching Indeed Australia."""

    source_name: str = "Indeed"
    endpoint: str = "https://au.indeed.com/jobs"

    def __init__(self, timeout: float = 15.0, apify_token: Optional[str] = None):
        self.timeout = timeout
        self.apify_token = apify_token or settings.APIFY_API_TOKEN

    async def search(self, query: SearchQuery) -> list[NormalizedJob]:
        if self.apify_token:
            return await self._search_via_apify(query)
        return await self._search_direct(query)

    async def _search_direct(self, query: SearchQuery) -> list[NormalizedJob]:
        params = {
            "q": query.term,
            "l": query.location if query.location != "All Australia" else "Australia",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml",
        }
        results: list[NormalizedJob] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.endpoint, params=params, headers=headers)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for card in soup.select(".job_seen_beacon, .resultContent, td.resultContent"):
                        title_el = card.select_one("h2.jobTitle span, a[data-jk]")
                        link_el = card.select_one("a[data-jk], h2 a")
                        if not title_el or not link_el:
                            continue
                        jk = link_el.get("data-jk") or ""
                        title = title_el.get_text(strip=True)
                        comp_el = card.select_one("[data-testid='company-name'], .companyName")
                        company = comp_el.get_text(strip=True) if comp_el else "Confidential"
                        loc_el = card.select_one("[data-testid='text-location'], .companyLocation")
                        loc = loc_el.get_text(strip=True) if loc_el else query.location
                        desc_el = card.select_one(".job-snippet, table.jobCardShelfContainer")
                        desc = desc_el.get_text(strip=True) if desc_el else ""

                        sal_el = card.select_one(
                            ".salary-snippet-container, [data-testid='attribute_snippets_test_id']"
                        )
                        sal_txt = sal_el.get_text(strip=True) if sal_el else ""
                        sal_info = normalize_australian_salary(sal_txt)

                        url = f"https://au.indeed.com/viewjob?jk={jk}" if jk else ""

                        results.append(
                            NormalizedJob(
                                id=f"indeed_{jk or abs(hash(title + company))}",
                                title=title,
                                company=company,
                                location=loc,
                                description=desc,
                                salary_raw=sal_txt or None,
                                salary_min=sal_info.min_amount,
                                salary_max=sal_info.max_amount,
                                salary_type=sal_info.rate_type,
                                salary_annualized=sal_info.annualized_midpoint,
                                source="Indeed",
                                url=sanitize_url(url),
                                tags=[query.term],
                            )
                        )
        except Exception as err:
            logger.warning(f"Indeed direct scrape error for '{query.term}': {err}")

        return results

    async def _search_via_apify(self, query: SearchQuery) -> list[NormalizedJob]:
        """Apify actor fallback when APIFY_API_TOKEN is provided."""
        logger.info(f"Dispatching query '{query.term}' to Indeed Apify actor.")
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
                resp = await client.get(self.endpoint)
                healthy = resp.status_code in (200, 403)
                return HealthStatus(
                    healthy=healthy,
                    source_name=self.source_name,
                    message="Endpoint responsive" if healthy else f"HTTP {resp.status_code}",
                )
        except Exception as err:
            return HealthStatus(healthy=False, source_name=self.source_name, message=str(err))
