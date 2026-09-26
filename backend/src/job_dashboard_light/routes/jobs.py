"""
Jobs Discovery, FTS5 Search, Details, and Candidate Match Filtering Routes.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..database import get_db, sanitize_fts5_query
from ..services.scoring import calculate_match_score

logger = logging.getLogger("job_dashboard_light.routes.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobListResponse(BaseModel):
    """Paginated jobs discovery payload."""

    jobs: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    sources: List[str] = Field(default_factory=list)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    q: Optional[str] = Query(default=None, description="Search keyword or phrase"),
    location: Optional[str] = Query(default=None, description="Location filter"),
    source: Optional[str] = Query(default=None, description="Job source filter (Seek, APS Jobs, etc)"),
    status: str = Query(default="active", description="Status filter (active, expired, all)"),
    min_salary: Optional[float] = Query(default=None, description="Minimum annualized salary"),
    max_age_days: Optional[int] = Query(default=None, description="Maximum posting age in days"),
    sort_by: str = Query(default="posted_date", description="Sort by: posted_date, salary, match"),
    user_id: Optional[str] = Query(default="usr_default", description="User ID for profile match scoring"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: sqlite3.Connection = Depends(get_db),
) -> JobListResponse:
    """Query jobs with optional FTS5 full-text matching, filters, and match scores."""
    cursor = db.cursor()

    conditions: List[str] = []
    params: List[Any] = []

    # 1. Status condition
    if status != "all":
        conditions.append("j.status = ?")
        params.append(status)

    # 2. Location condition
    if location and location.strip() and location.strip().lower() != "all australia":
        loc_term = f"%{location.strip()}%"
        conditions.append("(j.location LIKE ? OR j.location = 'All Australia')")
        params.append(loc_term)

    # 3. Source condition
    if source and source.strip():
        conditions.append("j.source = ?")
        params.append(source.strip())

    # 4. Salary condition
    if min_salary is not None and min_salary > 0:
        conditions.append("(j.salary_annualized IS NOT NULL AND j.salary_annualized >= ?)")
        params.append(min_salary)

    # 5. Age condition
    if max_age_days is not None and max_age_days > 0:
        conditions.append("(j.posted_age_days IS NULL OR j.posted_age_days <= ?)")
        params.append(max_age_days)

    # 6. FTS5 Search
    fts_clean = sanitize_fts5_query(q) if q else ""
    use_fts = bool(fts_clean)

    if use_fts:
        join_clause = "JOIN jobs_fts f ON j.rowid = f.rowid"
        conditions.insert(0, "jobs_fts MATCH ?")
        params.insert(0, fts_clean)
    else:
        join_clause = ""
        if q and q.strip():
            raw_pattern = f"%{q.strip()}%"
            conditions.append("(j.title LIKE ? OR j.description LIKE ? OR j.company LIKE ?)")
            params.extend([raw_pattern, raw_pattern, raw_pattern])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Total count query
    count_sql = f"SELECT COUNT(*) FROM jobs j {join_clause} {where_clause}"
    cursor.execute(count_sql, params)
    total_row = cursor.fetchone()
    total = total_row[0] if total_row else 0

    # Sorting
    if sort_by == "salary":
        order_clause = "ORDER BY j.salary_annualized DESC NULLS LAST, j.posted_date DESC"
    else:
        order_clause = "ORDER BY j.posted_date DESC"

    offset = (page - 1) * page_size
    query_sql = f"""
        SELECT j.* FROM jobs j
        {join_clause}
        {where_clause}
        {order_clause}
        LIMIT ? OFFSET ?
    """
    cursor.execute(query_sql, params + [page_size, offset])
    rows = cursor.fetchall()

    # Load candidate profile for match scoring
    candidate_profile = None
    if user_id:
        try:
            # Query candidate profile directly from current db connection
            p_cursor = db.cursor()
            p_cols = [r[1] for r in p_cursor.execute("PRAGMA table_info(user_profiles)").fetchall()]
            if p_cols:
                phone_col = "p.phone" if "phone" in p_cols else "NULL as phone"
                p_row = p_cursor.execute(
                    f"""
                    SELECT
                        p.user_id,
                        COALESCE(u.name, 'Candidate') as name,
                        u.email,
                        {phone_col},
                        p.seniority,
                        p.target_titles,
                        p.core_skills,
                        p.experience_summary,
                        p.preferred_locations,
                        p.target_salary_min
                    FROM user_profiles p
                    LEFT JOIN users u ON u.id = p.user_id
                    WHERE p.user_id = ?;
                    """,
                    (user_id,),
                ).fetchone()
                if p_row:


                    from ..models import CandidateProfile
                    candidate_profile = CandidateProfile(
                        user_id=p_row["user_id"],
                        name=p_row["name"],
                        email=p_row["email"],
                        phone=p_row["phone"],
                        seniority=p_row["seniority"],
                        target_titles=json.loads(p_row["target_titles"]) if isinstance(p_row["target_titles"], str) else (p_row["target_titles"] or []),
                        core_skills=json.loads(p_row["core_skills"]) if isinstance(p_row["core_skills"], str) else (p_row["core_skills"] or []),
                        experience_summary=p_row["experience_summary"] or "",
                        preferred_locations=json.loads(p_row["preferred_locations"]) if isinstance(p_row["preferred_locations"], str) else (p_row["preferred_locations"] or []),
                        target_salary_min=p_row["target_salary_min"],
                    )
        except Exception as exc:
            logger.warning(f"Could not load candidate profile for user '{user_id}': {exc}")
    profile_dict = candidate_profile.model_dump() if candidate_profile else {}

    job_dicts: List[Dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        # Parse tags
        if isinstance(item.get("tags"), str):
            try:
                item["tags"] = json.loads(item["tags"])
            except Exception:
                item["tags"] = []

        # Calculate match scoring
        if profile_dict and (profile_dict.get("core_skills") or profile_dict.get("target_titles")):
            scoring_res = calculate_match_score(item, profile_dict)
            item["match_score"] = scoring_res["score"]
            item["match_fit"] = scoring_res["fit"]
            item["matched_skills"] = scoring_res["matched_skills"]
            item["missing_skills"] = scoring_res["missing_skills"]
            item["match_breakdown"] = scoring_res["breakdown"]
        else:
            item["match_score"] = None
            item["match_fit"] = None
            item["matched_skills"] = []
            item["missing_skills"] = []
            item["match_breakdown"] = None

        job_dicts.append(item)

    if sort_by == "match":
        job_dicts.sort(key=lambda x: x.get("match_score") or 0, reverse=True)

    # Extract distinct sources available
    src_cursor = db.cursor()
    src_cursor.execute("SELECT DISTINCT source FROM jobs WHERE status = 'active' ORDER BY source")
    distinct_sources = [row[0] for row in src_cursor.fetchall() if row[0]]

    return JobListResponse(
        jobs=job_dicts,
        total=total,
        page=page,
        page_size=page_size,
        sources=distinct_sources,
    )


@router.get("/{job_id}")
async def get_job_details(
    job_id: str,
    user_id: Optional[str] = Query(default="usr_default"),
    db: sqlite3.Connection = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve full details of a specific job posting with match breakdown."""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job posting '{job_id}' not found.",
        )

    job_data = dict(row)
    if isinstance(job_data.get("tags"), str):
        try:
            job_data["tags"] = json.loads(job_data["tags"])
        except Exception:
            job_data["tags"] = []

    # Attach match score if profile exists
    candidate_profile = None
    if user_id:
        try:
            p_cursor = db.cursor()
            p_cols = [r[1] for r in p_cursor.execute("PRAGMA table_info(user_profiles)").fetchall()]
            if p_cols:
                phone_col = "p.phone" if "phone" in p_cols else "NULL as phone"
                p_row = p_cursor.execute(
                    f"""
                    SELECT
                        p.user_id,
                        COALESCE(u.name, 'Candidate') as name,
                        u.email,
                        {phone_col},
                        p.seniority,
                        p.target_titles,
                        p.core_skills,
                        p.experience_summary,
                        p.preferred_locations,
                        p.target_salary_min
                    FROM user_profiles p
                    LEFT JOIN users u ON u.id = p.user_id
                    WHERE p.user_id = ?;
                    """,
                    (user_id,),
                ).fetchone()
                if p_row:


                    from ..models import CandidateProfile
                    candidate_profile = CandidateProfile(
                        user_id=p_row["user_id"],
                        name=p_row["name"],
                        email=p_row["email"],
                        phone=p_row["phone"],
                        seniority=p_row["seniority"],
                        target_titles=json.loads(p_row["target_titles"]) if isinstance(p_row["target_titles"], str) else (p_row["target_titles"] or []),
                        core_skills=json.loads(p_row["core_skills"]) if isinstance(p_row["core_skills"], str) else (p_row["core_skills"] or []),
                        experience_summary=p_row["experience_summary"] or "",
                        preferred_locations=json.loads(p_row["preferred_locations"]) if isinstance(p_row["preferred_locations"], str) else (p_row["preferred_locations"] or []),
                        target_salary_min=p_row["target_salary_min"],
                    )
        except Exception as exc:
            logger.warning(f"Could not load candidate profile for user '{user_id}': {exc}")

    if candidate_profile:
        scoring_res = calculate_match_score(job_data, candidate_profile.model_dump())
        job_data["match_score"] = scoring_res["score"]
        job_data["match_fit"] = scoring_res["fit"]
        job_data["matched_skills"] = scoring_res["matched_skills"]
        job_data["missing_skills"] = scoring_res["missing_skills"]
        job_data["match_breakdown"] = scoring_res["breakdown"]

    return {"success": True, "job": job_data}
