"""
Unified Base Scraper Interface and Protocol for Job Dashboard Light.

Every job scraper source (Seek, Indeed, LinkedIn, Adzuna, Careers Vic, APS Jobs)
implements the BaseJobSource abstract base class to guarantee interface uniformity.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..models import HealthStatus, JobDetails, NormalizedJob, SearchQuery


class BaseJobSource(ABC):
    """Abstract Base Class for all job provider scrapers."""

    source_name: str = "Unknown"

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[NormalizedJob]:
        """Search job board and return normalized listings."""
        pass

    @abstractmethod
    async def get_details(self, job_id: str, url: str) -> Optional[JobDetails]:
        """Retrieve full job details, closing dates, and selection criteria."""
        pass

    @abstractmethod
    async def check_expired(self, job_id: str, url: str) -> bool:
        """Verify whether an ad is expired (404, redirect, or expired banner)."""
        pass

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Verify upstream endpoint connectivity and availability."""
        pass
