"""
FastAPI REST Routes for Candidate Profile Management & Resume Upload.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import jwt
from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from job_dashboard_light.config import settings
from job_dashboard_light.database import get_db
from job_dashboard_light.models import CandidateProfile

from ..services.profile import (
    MAX_RESUME_CHARS,
    extract_text_from_file,
    extrapolate_profile_with_llm,
    get_candidate_profile,
    save_candidate_profile,
)

logger = logging.getLogger("job_dashboard_light.routes.profile")

router = APIRouter(prefix="/api/profile", tags=["profile"])


def get_current_user_id(
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    user_id: Optional[str] = Query(default=None),
) -> str:
    """Resolve active user ID with support for dev headers, queries, and JWT tokens."""
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    if user_id and user_id.strip():
        return user_id.strip()
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            sub = payload.get("sub")
            if sub:
                return str(sub)
        except Exception:
            pass
    return "usr_default"


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    active_user_id: str = Depends(get_current_user_id),
    db: Any = Depends(get_db),
) -> Dict[str, Any]:
    """Upload resume (PDF, DOCX, TXT), extract text, extrapolate profile via LLM, and persist."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename.",
        )

    ext = file.filename.lower().split(".")[-1] if "." in file.filename else ""
    if ext not in ("pdf", "docx", "txt", "md"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: .{ext}. Allowed formats are PDF, DOCX, and TXT.",
        )

    try:
        content = await file.read()
    except Exception as exc:
        logger.error(f"Failed to read uploaded file: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file content.",
        )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty."
        )

    # 1. Extract text and slice to 9,000 characters
    raw_text = extract_text_from_file(
        content, filename=file.filename, max_chars=MAX_RESUME_CHARS
    )
    if not raw_text or len(raw_text.strip()) < 15:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to extract readable text from document. Ensure it is not password-protected or a scanned image.",
        )

    # 2. Extrapolate candidate facts using LLM (or fallback heuristic)
    profile = await extrapolate_profile_with_llm(raw_text, user_id=active_user_id)

    # 3. Persist in database
    saved_profile = save_candidate_profile(profile, raw_resume_text=raw_text)

    return {
        "success": True,
        "message": "Resume uploaded and profile extrapolated successfully.",
        "profile": saved_profile.model_dump(),
        "extracted_chars": len(raw_text),
    }


@router.get("")
async def get_profile(
    active_user_id: str = Depends(get_current_user_id),
    db: Any = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve candidate profile for active user."""
    profile = get_candidate_profile(active_user_id)
    if not profile:
        # Return sensible default empty profile
        default_profile = CandidateProfile(
            user_id=active_user_id,
            name="Candidate",
            seniority="Mid",
            target_titles=["Systems Engineer", "Cloud Engineer"],
            core_skills=[],
            experience_summary="",
            preferred_locations=["All Australia"],
        )
        return {"success": True, "profile": default_profile.model_dump()}

    return {"success": True, "profile": profile.model_dump()}


@router.put("")
async def update_profile(
    profile_data: CandidateProfile,
    active_user_id: str = Depends(get_current_user_id),
    db: Any = Depends(get_db),
) -> Dict[str, Any]:
    """Update candidate profile for active user."""
    # Ensure user_id matches active user
    profile_data.user_id = active_user_id
    saved = save_candidate_profile(profile_data)
    return {
        "success": True,
        "message": "Profile updated successfully.",
        "profile": saved.model_dump(),
    }
