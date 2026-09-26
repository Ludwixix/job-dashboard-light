"""
Kanban Application Pipeline Tracker REST Routes.
Manages applicant progression: Draft -> Applied -> Interviewing -> Offered -> Rejected.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..database import get_db
from ..models import now_iso

logger = logging.getLogger("job_dashboard_light.routes.tracker")

router = APIRouter(prefix="/api/applications", tags=["tracker"])


class ApplicationUpsertRequest(BaseModel):
    """Payload to create or update an application tracking card."""

    job_id: str
    status: str = Field(default="Draft", description="Draft, Applied, Interviewing, Offered, Rejected")
    recruiter_name: Optional[str] = None
    recruiter_email: Optional[str] = None
    recruiter_phone: Optional[str] = None
    interview_at: Optional[str] = None
    notes: Optional[str] = ""
    applied_at: Optional[str] = None


class ApplicationStatusUpdateRequest(BaseModel):
    """Payload to transition card stage or update interview notes."""

    status: Optional[str] = None
    interview_at: Optional[str] = None
    notes: Optional[str] = None
    recruiter_name: Optional[str] = None
    recruiter_email: Optional[str] = None


def resolve_tracker_user_id(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    user_id: Optional[str] = Query(default=None),
) -> str:
    """Resolve user ID from header or query for tracker operations."""
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    if user_id and user_id.strip():
        return user_id.strip()
    return "usr_default"


@router.get("")
async def list_applications(
    active_user_id: str = Depends(resolve_tracker_user_id),
    db: sqlite3.Connection = Depends(get_db),
) -> Dict[str, Any]:
    """List all Kanban tracked applications for user with joined job card data."""
    cursor = db.cursor()
    sql = """
        SELECT
            a.id, a.user_id, a.job_id, a.status,
            a.recruiter_name, a.recruiter_email, a.recruiter_phone,
            a.interview_at, a.notes, a.applied_at, a.updated_at,
            j.title as job_title, j.company as job_company,
            j.location as job_location, j.salary_raw, j.salary_annualized,
            j.url as job_url, j.source as job_source, j.closing_date
        FROM user_applications a
        JOIN jobs j ON a.job_id = j.id
        WHERE a.user_id = ?
        ORDER BY a.updated_at DESC;
    """
    cursor.execute(sql, (active_user_id,))
    rows = cursor.fetchall()
    apps = [dict(r) for r in rows]

    # Organize cards into 5 kanban buckets for immediate frontend rendering
    kanban_stages = {
        "Draft": [],
        "Applied": [],
        "Interviewing": [],
        "Offered": [],
        "Rejected": [],
    }

    for app in apps:
        stage = app.get("status", "Draft")
        if stage in kanban_stages:
            kanban_stages[stage].append(app)
        else:
            kanban_stages["Draft"].append(app)

    return {
        "success": True,
        "total": len(apps),
        "applications": apps,
        "board": kanban_stages,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def upsert_application(
    payload: ApplicationUpsertRequest,
    active_user_id: str = Depends(resolve_tracker_user_id),
    db: sqlite3.Connection = Depends(get_db),
) -> Dict[str, Any]:
    """Create or update a tracked job application."""
    cursor = db.cursor()

    # Verify job exists
    cursor.execute("SELECT id FROM jobs WHERE id = ?", (payload.job_id,))
    if not cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{payload.job_id}' not found in database.",
        )

    # Check if application already exists
    cursor.execute(
        "SELECT id FROM user_applications WHERE user_id = ? AND job_id = ?",
        (active_user_id, payload.job_id),
    )
    existing = cursor.fetchone()
    app_id = existing[0] if existing else f"app_{uuid.uuid4().hex[:12]}"
    now = now_iso()

    applied_date = payload.applied_at or (now if payload.status == "Applied" else None)

    cursor.execute(
        """
        INSERT INTO user_applications (
            id, user_id, job_id, status, recruiter_name, recruiter_email, recruiter_phone,
            interview_at, notes, applied_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, job_id) DO UPDATE SET
            status = excluded.status,
            recruiter_name = COALESCE(excluded.recruiter_name, user_applications.recruiter_name),
            recruiter_email = COALESCE(excluded.recruiter_email, user_applications.recruiter_email),
            recruiter_phone = COALESCE(excluded.recruiter_phone, user_applications.recruiter_phone),
            interview_at = COALESCE(excluded.interview_at, user_applications.interview_at),
            notes = excluded.notes,
            applied_at = COALESCE(excluded.applied_at, user_applications.applied_at),
            updated_at = excluded.updated_at;
        """,
        (
            app_id,
            active_user_id,
            payload.job_id,
            payload.status,
            payload.recruiter_name,
            payload.recruiter_email,
            payload.recruiter_phone,
            payload.interview_at,
            payload.notes or "",
            applied_date,
            now,
        ),
    )

    return {
        "success": True,
        "message": f"Job tracked in '{payload.status}' status.",
        "application_id": app_id,
    }


@router.patch("/{app_id}")
async def update_application_status(
    app_id: str,
    payload: ApplicationStatusUpdateRequest,
    active_user_id: str = Depends(resolve_tracker_user_id),
    db: sqlite3.Connection = Depends(get_db),
) -> Dict[str, Any]:
    """Patch stage, interview date, or notes for tracked application."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM user_applications WHERE id = ? AND user_id = ?",
        (app_id, active_user_id),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{app_id}' not found.",
        )

    current = dict(row)
    now = now_iso()
    new_status = payload.status or current["status"]
    new_notes = payload.notes if payload.notes is not None else current["notes"]
    new_interview = payload.interview_at if payload.interview_at is not None else current["interview_at"]
    new_recruiter_name = payload.recruiter_name if payload.recruiter_name is not None else current["recruiter_name"]
    new_recruiter_email = payload.recruiter_email if payload.recruiter_email is not None else current["recruiter_email"]

    cursor.execute(
        """
        UPDATE user_applications
        SET status = ?, notes = ?, interview_at = ?, recruiter_name = ?, recruiter_email = ?, updated_at = ?
        WHERE id = ?;
        """,
        (new_status, new_notes, new_interview, new_recruiter_name, new_recruiter_email, now, app_id),
    )

    return {
        "success": True,
        "message": f"Application updated to '{new_status}'.",
        "application_id": app_id,
    }


@router.delete("/{app_id}")
async def delete_application(
    app_id: str,
    active_user_id: str = Depends(resolve_tracker_user_id),
    db: sqlite3.Connection = Depends(get_db),
) -> Dict[str, Any]:
    """Remove application card from tracker."""
    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM user_applications WHERE id = ? AND user_id = ?",
        (app_id, active_user_id),
    )
    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{app_id}' not found.",
        )
    return {"success": True, "message": f"Application '{app_id}' removed."}
