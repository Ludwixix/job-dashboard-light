"""
Scrape Trigger and Diagnostics REST Routes.
Executes multi-source scraping via ScrapeCoordinator with single-flight deduplication.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..config import settings
from ..models import SearchQuery
from ..services.coordinator import ScrapeCoordinator

logger = logging.getLogger("job_dashboard_light.routes.scrape")

router = APIRouter(prefix="/api/scrape", tags=["scrape"])

_COORDINATOR: Optional[ScrapeCoordinator] = None


def get_coordinator() -> ScrapeCoordinator:
    """Singleton getter for ScrapeCoordinator."""
    global _COORDINATOR
    if _COORDINATOR is None:
        db_file = str(settings.DATA_DIR / "jobs.sqlite3")
        _COORDINATOR = ScrapeCoordinator(db_path=db_file)
    return _COORDINATOR


class ScrapeTriggerRequest(BaseModel):
    """Payload to trigger on-demand scraping."""

    term: str = Field(..., min_length=2, description="Job title, keyword, or technical role")
    location: str = Field(default="All Australia", description="Location (e.g. Sydney, Melbourne, Remote)")
    force: bool = Field(default=False, description="Bypass local DB sufficiency cache and force external hit")
    exclude_terms: List[str] = Field(default_factory=list)


@router.post("")
async def trigger_scrape(
    payload: ScrapeTriggerRequest,
    coordinator: ScrapeCoordinator = Depends(get_coordinator),
) -> Dict[str, Any]:
    """Trigger coordinated scrape across Seek, Indeed, LinkedIn, Adzuna, Careers Vic, and APS Jobs."""
    query = SearchQuery(
        term=payload.term.strip(),
        location=payload.location.strip(),
        exclude_terms=payload.exclude_terms,
    )

    try:
        jobs = await coordinator.search_and_ingest(query, force=payload.force)
        return {
            "success": True,
            "term": query.term,
            "location": query.location,
            "total_returned": len(jobs),
            "jobs": [j.model_dump() for j in jobs[:25]],
        }
    except Exception as exc:
        logger.error(f"Scrape coordinator error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scraper execution error: {exc!s}",
        )


@router.get("/status")
async def check_scraper_health(
    coordinator: ScrapeCoordinator = Depends(get_coordinator),
) -> Dict[str, Any]:
    """Check connectivity and operational health across all 6 scraper adapters."""
    health_results = []
    for src in coordinator.sources:
        try:
            h = await src.health_check()
            health_results.append({
                "source": src.source_name,
                "healthy": h.healthy,
                "message": h.message,
                "last_checked": h.last_checked.isoformat(),
            })
        except Exception as exc:
            health_results.append({
                "source": src.source_name,
                "healthy": False,
                "message": f"Health check failed: {exc}",
                "last_checked": None,
            })

    all_healthy = all(item["healthy"] for item in health_results)
    return {
        "status": "operational" if all_healthy else "degraded",
        "healthy_sources": sum(1 for item in health_results if item["healthy"]),
        "total_sources": len(health_results),
        "sources": health_results,
    }
