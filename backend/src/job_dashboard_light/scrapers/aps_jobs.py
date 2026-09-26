"""APS Jobs Job Source Adapter."""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from ..models import HealthStatus, JobDetails, NormalizedJob, SearchQuery
from ..services.dedup import sanitize_url
from ..services.salary import normalize_australian_salary
from .base import BaseJobSource

logger = logging.getLogger("job_dashboard_light.scrapers.aps_jobs")


class APSJobsJobSource(BaseJobSource):
    """Adapter for searching APS Jobs (Australian Public Service)."""

    source_name: str = "APS Jobs"
    endpoint: str = "https://www.apsjobs.gov.au/s/job-search"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def search(self, query: SearchQuery) -> list[NormalizedJob]:
        params = {"keyword": query.term}
        headers = {"User-Agent": "Mozilla/5.0"}
        results: list[NormalizedJob] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.endpoint, params=params, headers=headers)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for card in soup.select(".job-card, .search-result, .job-listing"):
                        link = card.select_one("a[href*='/job/'], a[href*='/s/job-details']")
                        if not link:
                            continue
                        href = link.get("href", "")
                        url = f"https://www.apsjobs.gov.au{href}" if href.startswith("/") else href
                        job_id_match = re.search(r"Id=([a-zA-Z0-9]+)", url) or re.search(
                            r"/job/(\w+)", url
                        )
                        id_str = (
                            f"aps_{job_id_match.group(1)}"
                            if job_id_match
                            else f"aps_{abs(hash(url))}"
                        )

                        title = link.get_text(strip=True)
                        agency = card.select_one(".agency, .department")
                        company = (
                            agency.get_text(strip=True) if agency else "Australian Public Service"
                        )
                        loc = card.select_one(".location")
                        location = loc.get_text(strip=True) if loc else "Canberra ACT"
                        desc = card.select_one(".description, .summary")
                        teaser = desc.get_text(strip=True) if desc else ""
                        sal = card.select_one(".salary, .remuneration")
                        sal_txt = sal.get_text(strip=True) if sal else ""

                        # APS jobs default to 15.4% super rate
                        salary_info = normalize_australian_salary(sal_txt, is_aps=True)

                        results.append(
                            NormalizedJob(
                                id=id_str,
                                title=title,
                                company=company,
                                location=location,
                                description=teaser,
                                salary_raw=sal_txt or None,
                                salary_min=salary_info.min_amount,
                                salary_max=salary_info.max_amount,
                                salary_type=salary_info.rate_type,
                                salary_annualized=salary_info.annualized_midpoint,
                                source="APS Jobs",
                                url=sanitize_url(url),
                                tags=[query.term, "APS", "Federal Government"],
                            )
                        )
        except Exception as err:
            logger.warning(f"APS Jobs query failed: {err}")
        return results

    async def get_details(self, job_id: str, url: str) -> Optional[JobDetails]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(sanitize_url(url))
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    body = soup.select_one(".job-details, main")
                    full_desc = body.get_text("\n", strip=True) if body else ""
                    ksc_items = [
                        li.get_text(strip=True)
                        for li in soup.select(".ksc-list li, .selection-criteria li")
                        if li.get_text(strip=True)
                    ]
                    closing = soup.select_one(".closing-date, .close-date")
                    closing_date = closing.get_text(strip=True) if closing else None
                    return JobDetails(
                        id=job_id,
                        full_description=full_desc,
                        key_selection_criteria=ksc_items,
                        closing_date=closing_date,
                    )
        except Exception as err:
            logger.warning(f"Failed to fetch APS details: {err}")
        return None

    async def check_expired(self, job_id: str, url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(sanitize_url(url))
                return resp.status_code in (404, 410) or "position has closed" in resp.text.lower()
        except Exception:
            return False

    async def health_check(self) -> HealthStatus:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self.endpoint)
                healthy = resp.status_code == 200
                return HealthStatus(
                    healthy=healthy,
                    source_name=self.source_name,
                    message="Endpoint responsive" if healthy else f"HTTP {resp.status_code}",
                )
        except Exception as err:
            return HealthStatus(healthy=False, source_name=self.source_name, message=str(err))
