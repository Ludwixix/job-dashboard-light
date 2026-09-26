"""Unified job scraping adapters for Australian job boards."""

from .adzuna import AdzunaJobSource
from .aps_jobs import APSJobsJobSource
from .base import BaseJobSource
from .careers_vic import CareersVicJobSource
from .indeed import IndeedJobSource
from .linkedin import LinkedInJobSource
from .seek import SeekJobSource

__all__ = [
    "BaseJobSource",
    "SeekJobSource",
    "AdzunaJobSource",
    "CareersVicJobSource",
    "APSJobsJobSource",
    "IndeedJobSource",
    "LinkedInJobSource",
]
