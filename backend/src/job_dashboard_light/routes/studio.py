"""
Studio REST API Endpoints: OpenRouter Model Presets, ATS CV, Polarized Cover Letters,
Australian KSC STAR Generator, Document Export (Markdown & PDF), and Document History.

Endpoints:
- GET /api/studio/models: Returns supported model presets and active default model.
- POST /api/studio/cv: Generates tailored ATS CV and persists to generated_documents.
- POST /api/studio/cover-letter: Generates polarized cover letter and persists to generated_documents.
- POST /api/studio/ksc: Generates Australian KSC STAR response report mapped to APS/VPSC frameworks.
- POST /api/studio/generate: Unified generation endpoint (cv | cover_letter | ksc).
- POST /api/studio/export: Generalized export router supporting format='markdown' | 'pdf'.
- POST /api/studio/export/markdown: 1-click clean Markdown export.
- POST /api/studio/export/pdf: 1-click ReportLab A4 vector PDF export.
- GET /api/studio/documents: Lists generated documents for user.
- GET /api/studio/documents/{doc_id}: Retrieves generated document by ID.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

import jwt
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from pydantic import BaseModel, Field

from ..config import settings
from ..database import get_db
from ..models import now_iso
from ..services.export import export_markdown, export_pdf_bytes, sanitize_filename
from ..services.ksc import generate_ksc_report
from ..services.llm import (
    DEFAULT_MODEL_ID,
    MODEL_PRESETS,
    OpenRouterAPIError,
    OpenRouterAuthError,
    OpenRouterRateLimitError,
    generate_polarized_cover_letter,
    generate_tailored_cv,
)

logger = logging.getLogger("job_dashboard_light.routes.studio")

router = APIRouter(prefix="", tags=["studio"])

# ==============================================================================
# Request & Response Schemas
# ==============================================================================


class ModelPresetsResponse(BaseModel):
    """Model presets payload."""

    models: List[Dict[str, Any]]
    default_model: str


class CVGenerationRequest(BaseModel):
    """Request payload for tailored ATS CV generation."""

    job_id: Optional[str] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = "All Australia"
    job_description: Optional[str] = None
    model: Optional[str] = None
    user_id: Optional[str] = "default_user"
    profile_data: Optional[Dict[str, Any]] = None
    custom_instructions: Optional[str] = None


class CoverLetterGenerationRequest(BaseModel):
    """Request payload for polarized cover letter generation."""

    job_id: Optional[str] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = "All Australia"
    job_description: Optional[str] = None
    model: Optional[str] = None
    variant: str = Field(
        default="high_conviction",
        description="Cover letter variant: high_conviction, systems_architect, or cultural_outlier",
    )
    user_id: Optional[str] = "default_user"
    profile_data: Optional[Dict[str, Any]] = None
    custom_instructions: Optional[str] = None


class KscRequest(BaseModel):
    """Request payload for KSC STAR generation."""

    job_id: Optional[str] = None
    job_title: Optional[str] = "Specialist / Advisor"
    company: Optional[str] = "Australian Public Service"
    description: Optional[str] = ""
    job_description: Optional[str] = ""
    criteria: Optional[List[str]] = None
    ksc_criteria: Optional[List[str]] = None
    framework: Optional[str] = "APS"
    target_word_limit: Optional[int] = 350
    doc_type: Optional[str] = None
    user_id: Optional[str] = "default_user"
    profile_data: Optional[Dict[str, Any]] = None


class StudioGenerateRequest(BaseModel):
    """Unified generation request supporting cv, cover_letter, and ksc."""

    doc_type: str = "cover_letter"  # "cv" | "cover_letter" | "ksc"
    model: Optional[str] = None
    job_id: Optional[str] = None
    job_title: Optional[str] = "Specialist / Advisor"
    company: Optional[str] = "Australian Enterprise"
    location: Optional[str] = "All Australia"
    job_description: Optional[str] = ""
    description: Optional[str] = ""
    user_id: Optional[str] = None
    profile_data: Optional[Dict[str, Any]] = None
    custom_instructions: Optional[str] = None
    variant: str = "high_conviction"
    ksc_criteria: Optional[List[str]] = None
    criteria: Optional[List[str]] = None
    framework: str = "APS"
    target_word_limit: int = 350


class ExportRequest(BaseModel):
    """Request payload for document export."""

    content: str = ""
    format: Optional[str] = "markdown"
    title: Optional[str] = "document"


class GeneratedDocumentResponse(BaseModel):
    """Response payload for generated asset."""

    document_id: str
    user_id: str
    job_id: str
    doc_type: str
    model_used: str
    title: str
    content_markdown: str
    created_at: str
    swappability_score: Optional[int] = None
    anti_template_passed: Optional[bool] = None
    audit_issues: Optional[List[str]] = None
    is_fallback: bool = False


# ==============================================================================
# Helper Functions
# ==============================================================================


def resolve_auth_user_id(
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    user_id_query: Optional[str] = Query(default=None, alias="user_id"),
    body_user_id: Optional[str] = None,
) -> Optional[str]:
    """Resolve active user ID from Authorization Bearer token, custom headers, query or body."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                options={"verify_signature": False},
            )
            sub = payload.get("sub") or payload.get("email")
            if sub:
                return str(sub)
        except Exception:
            pass
        return "auth_user"

    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    if user_id_query and user_id_query.strip():
        return user_id_query.strip()
    if body_user_id and body_user_id.strip():
        return body_user_id.strip()

    return None


def _resolve_job_and_profile(
    db: sqlite3.Connection,
    job_id: Optional[str],
    job_title: Optional[str],
    company: Optional[str],
    location: Optional[str],
    job_description: Optional[str],
    user_id: Optional[str],
    explicit_profile: Optional[Dict[str, Any]],
) -> Tuple[str, Dict[str, Any], str, Dict[str, Any]]:
    """Resolve job requisition and candidate profile facts from DB or fallback."""
    uid = user_id or "default_user"

    # 1. Defensive User Record Provisioning (to satisfy FK constraints)
    db.execute(
        """
        INSERT OR IGNORE INTO users (id, email, name, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (uid, f"{uid}@local.dev", "Default Candidate", now_iso(), now_iso()),
    )

    # 2. Resolve Profile
    profile_dict: Dict[str, Any] = {}
    if uid:
        row = db.execute(
            "SELECT raw_resume_text, seniority, target_titles, core_skills, experience_summary, preferred_locations, target_salary_min FROM user_profiles WHERE user_id = ?",
            (uid,),
        ).fetchone()
        if row:
            profile_dict = {
                "seniority": row["seniority"],
                "target_titles": json.loads(row["target_titles"] or "[]"),
                "core_skills": json.loads(row["core_skills"] or "[]"),
                "experience_summary": row["experience_summary"] or "",
                "preferred_locations": json.loads(row["preferred_locations"] or "[]"),
                "target_salary_min": row["target_salary_min"],
            }

    if explicit_profile:
        profile_dict.update(explicit_profile)

    if not profile_dict:
        profile_dict = {
            "name": "Alex Smith",
            "email": "alex.smith@example.com.au",
            "phone": "0412 345 678",
            "seniority": "Senior",
            "target_titles": [job_title or "Platform Engineer"],
            "core_skills": [
                "Cloud Architecture",
                "PowerShell",
                "CI/CD",
                "Infrastructure as Code",
            ],
            "experience_summary": "Extensive experience delivering resilient systems and automation pipelines.",
            "preferred_locations": ["Melbourne, VIC"],
        }

    # 3. Resolve Job
    jid = job_id or f"adhoc_{uuid.uuid4().hex[:8]}"
    j_title = job_title or "Target Role"
    j_company = company or "Target Employer"
    j_loc = location or "All Australia"
    j_desc = job_description or ""

    if job_id:
        j_row = db.execute(
            "SELECT id, title, company, location, description FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if j_row:
            j_title = j_row["title"]
            j_company = j_row["company"]
            j_loc = j_row["location"]
            j_desc = j_row["description"]
        else:
            # Defensive Job Record Provisioning (to satisfy FK constraints)
            db.execute(
                """
                INSERT OR IGNORE INTO jobs (id, title, company, location, description, source, url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'Studio', '', ?, ?)
                """,
                (jid, j_title, j_company, j_loc, j_desc, now_iso(), now_iso()),
            )
    else:
        # Create ad-hoc record for FK integrity
        db.execute(
            """
            INSERT OR IGNORE INTO jobs (id, title, company, location, description, source, url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'Studio', '', ?, ?)
            """,
            (jid, j_title, j_company, j_loc, j_desc, now_iso(), now_iso()),
        )

    job_dict = {
        "id": jid,
        "title": j_title,
        "company": j_company,
        "location": j_loc,
        "description": j_desc,
    }

    return jid, job_dict, uid, profile_dict


# ==============================================================================
# Endpoints
# ==============================================================================


@router.get("/api/studio/models", response_model=ModelPresetsResponse)
async def get_model_presets():
    """Retrieve supported OpenRouter model presets and active default model."""
    return ModelPresetsResponse(
        models=MODEL_PRESETS,
        default_model=settings.DEFAULT_MODEL or DEFAULT_MODEL_ID,
    )


@router.post(
    "/api/studio/cv",
    response_model=GeneratedDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_cv_endpoint(
    req: CVGenerationRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    """Generate tailored, grounded ATS CV and save to generated_documents."""
    jid, job_dict, uid, profile_dict = _resolve_job_and_profile(
        db=db,
        job_id=req.job_id,
        job_title=req.job_title,
        company=req.company,
        location=req.location,
        job_description=req.job_description,
        user_id=req.user_id,
        explicit_profile=req.profile_data,
    )

    try:
        cv_result = await generate_tailored_cv(
            job=job_dict,
            profile=profile_dict,
            model=req.model,
            custom_instructions=req.custom_instructions,
        )
    except OpenRouterAuthError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err)
        ) from err
    except OpenRouterRateLimitError as err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(err)
        ) from err
    except OpenRouterAPIError as err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(err)
        ) from err
    except Exception as err:
        logger.error(f"Unexpected error in CV generation: {err}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CV generation failed: {err}",
        ) from err

    doc_id = f"doc_cv_{uuid.uuid4().hex[:12]}"
    created_at = now_iso()

    db.execute(
        """
        INSERT INTO generated_documents (id, user_id, job_id, doc_type, model_used, title, content_markdown, created_at)
        VALUES (?, ?, ?, 'cv', ?, ?, ?, ?)
        """,
        (
            doc_id,
            uid,
            jid,
            cv_result["model_used"],
            cv_result["title"],
            cv_result["content_markdown"],
            created_at,
        ),
    )

    return GeneratedDocumentResponse(
        document_id=doc_id,
        user_id=uid,
        job_id=jid,
        doc_type="cv",
        model_used=cv_result["model_used"],
        title=cv_result["title"],
        content_markdown=cv_result["content_markdown"],
        created_at=created_at,
        is_fallback=cv_result.get("is_fallback", False),
    )


@router.post(
    "/api/studio/cover-letter",
    response_model=GeneratedDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_cover_letter_endpoint(
    req: CoverLetterGenerationRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    """Generate polarized 3-paragraph cover letter passing Anti-Template audit."""
    jid, job_dict, uid, profile_dict = _resolve_job_and_profile(
        db=db,
        job_id=req.job_id,
        job_title=req.job_title,
        company=req.company,
        location=req.location,
        job_description=req.job_description,
        user_id=req.user_id,
        explicit_profile=req.profile_data,
    )

    try:
        cl_result = await generate_polarized_cover_letter(
            job=job_dict,
            profile=profile_dict,
            model=req.model,
            variant=req.variant,
            custom_instructions=req.custom_instructions,
        )
    except OpenRouterAuthError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err)
        ) from err
    except OpenRouterRateLimitError as err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(err)
        ) from err
    except OpenRouterAPIError as err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(err)
        ) from err
    except Exception as err:
        logger.error(
            f"Unexpected error in cover letter generation: {err}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cover letter generation failed: {err}",
        ) from err

    doc_id = f"doc_cl_{uuid.uuid4().hex[:12]}"
    created_at = now_iso()

    db.execute(
        """
        INSERT INTO generated_documents (id, user_id, job_id, doc_type, model_used, title, content_markdown, created_at)
        VALUES (?, ?, ?, 'cover_letter', ?, ?, ?, ?)
        """,
        (
            doc_id,
            uid,
            jid,
            cl_result["model_used"],
            cl_result["title"],
            cl_result["content_markdown"],
            created_at,
        ),
    )

    return GeneratedDocumentResponse(
        document_id=doc_id,
        user_id=uid,
        job_id=jid,
        doc_type="cover_letter",
        model_used=cl_result["model_used"],
        title=cl_result["title"],
        content_markdown=cl_result["content_markdown"],
        created_at=created_at,
        swappability_score=cl_result.get("swappability_score"),
        anti_template_passed=cl_result.get("anti_template_passed"),
        audit_issues=cl_result.get("audit_issues"),
        is_fallback=cl_result.get("is_fallback", False),
    )


@router.post("/api/studio/ksc")
async def generate_ksc_endpoint(
    req: KscRequest,
    db: sqlite3.Connection = Depends(get_db),
) -> Dict[str, Any]:
    """Generates KSC STAR statement report mapped to APS ILS or VPSC frameworks."""
    criteria = req.criteria or req.ksc_criteria
    limit = req.target_word_limit or 350
    fw = req.framework or "APS"

    jid, job_dict, uid, profile_dict = _resolve_job_and_profile(
        db=db,
        job_id=req.job_id,
        job_title=req.job_title,
        company=req.company,
        location="All Australia",
        job_description=req.job_description or req.description,
        user_id=req.user_id,
        explicit_profile=req.profile_data,
    )

    report = generate_ksc_report(
        job=job_dict,
        profile=profile_dict,
        custom_criteria=criteria,
        framework=fw,
        word_limit=limit,
    )
    total_words = sum(s.word_count for s in report.solutions)

    doc_id = f"doc_ksc_{uuid.uuid4().hex[:12]}"
    created_at = now_iso()
    db.execute(
        """
        INSERT INTO generated_documents (id, user_id, job_id, doc_type, model_used, title, content_markdown, created_at)
        VALUES (?, ?, ?, 'ksc', 'ksc-generator', ?, ?, ?)
        """,
        (
            doc_id,
            uid,
            jid,
            f"KSC - {job_dict.get('title')}",
            report.master_document,
            created_at,
        ),
    )

    return {
        "success": True,
        "id": doc_id,
        "document_id": doc_id,
        "doc_type": "ksc",
        "model": "ksc-generator",
        "model_used": "ksc-generator",
        "content": report.master_document,
        "content_markdown": report.master_document,
        "word_count": total_words,
        "report": report.to_dict(),
    }


@router.post("/api/studio/generate")
async def studio_generate_endpoint(
    req: StudioGenerateRequest,
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    user_id_query: Optional[str] = Query(default=None, alias="user_id"),
    db: sqlite3.Connection = Depends(get_db),
) -> Dict[str, Any]:
    """Unified generator supporting doc_type='cv' | 'cover_letter' | 'ksc'."""
    resolved_uid = resolve_auth_user_id(
        authorization=authorization,
        x_user_id=x_user_id,
        user_id_query=user_id_query,
        body_user_id=req.user_id,
    )

    if not resolved_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for studio generation.",
        )

    doc_type = (req.doc_type or "cover_letter").lower()
    model = req.model or settings.DEFAULT_MODEL or DEFAULT_MODEL_ID
    job_desc = req.job_description or req.description or ""

    jid, job_dict, uid, profile_dict = _resolve_job_and_profile(
        db=db,
        job_id=req.job_id,
        job_title=req.job_title,
        company=req.company,
        location=req.location,
        job_description=job_desc,
        user_id=resolved_uid,
        explicit_profile=req.profile_data,
    )

    if doc_type == "cv":
        cv_res = await generate_tailored_cv(
            job=job_dict,
            profile=profile_dict,
            model=model,
            custom_instructions=req.custom_instructions,
        )
        doc_id = f"doc_cv_{uuid.uuid4().hex[:12]}"
        created_at = now_iso()
        content = cv_res["content_markdown"]

        db.execute(
            """
            INSERT INTO generated_documents (id, user_id, job_id, doc_type, model_used, title, content_markdown, created_at)
            VALUES (?, ?, ?, 'cv', ?, ?, ?, ?)
            """,
            (
                doc_id,
                uid,
                jid,
                cv_res["model_used"],
                cv_res["title"],
                content,
                created_at,
            ),
        )

        return {
            "id": doc_id,
            "document_id": doc_id,
            "doc_type": "cv",
            "model": cv_res["model_used"],
            "model_used": cv_res["model_used"],
            "title": cv_res["title"],
            "content": content,
            "content_markdown": content,
            "word_count": len(content.split()),
            "is_fallback": cv_res.get("is_fallback", False),
        }

    elif doc_type == "ksc":
        criteria = req.criteria or req.ksc_criteria
        limit = req.target_word_limit or 350
        fw = req.framework or "APS"

        report = generate_ksc_report(
            job=job_dict,
            profile=profile_dict,
            custom_criteria=criteria,
            framework=fw,
            word_limit=limit,
        )
        total_words = sum(s.word_count for s in report.solutions)
        doc_id = f"doc_ksc_{uuid.uuid4().hex[:12]}"
        created_at = now_iso()
        content = report.master_document

        db.execute(
            """
            INSERT INTO generated_documents (id, user_id, job_id, doc_type, model_used, title, content_markdown, created_at)
            VALUES (?, ?, ?, 'ksc', ?, ?, ?, ?)
            """,
            (
                doc_id,
                uid,
                jid,
                model,
                f"KSC - {job_dict.get('title')}",
                content,
                created_at,
            ),
        )

        return {
            "id": doc_id,
            "document_id": doc_id,
            "doc_type": "ksc",
            "model": model,
            "model_used": model,
            "title": f"KSC - {job_dict.get('title')}",
            "content": content,
            "content_markdown": content,
            "word_count": total_words,
            "report": report.to_dict(),
        }

    else:  # default: cover_letter
        cl_res = await generate_polarized_cover_letter(
            job=job_dict,
            profile=profile_dict,
            model=model,
            variant=req.variant,
            custom_instructions=req.custom_instructions,
        )
        doc_id = f"doc_cl_{uuid.uuid4().hex[:12]}"
        created_at = now_iso()
        content = cl_res["content_markdown"]

        db.execute(
            """
            INSERT INTO generated_documents (id, user_id, job_id, doc_type, model_used, title, content_markdown, created_at)
            VALUES (?, ?, ?, 'cover_letter', ?, ?, ?, ?)
            """,
            (
                doc_id,
                uid,
                jid,
                cl_res["model_used"],
                cl_res["title"],
                content,
                created_at,
            ),
        )

        return {
            "id": doc_id,
            "document_id": doc_id,
            "doc_type": "cover_letter",
            "model": cl_res["model_used"],
            "model_used": cl_res["model_used"],
            "title": cl_res["title"],
            "content": content,
            "content_markdown": content,
            "word_count": len(content.split()),
            "anti_template_passed": cl_res.get("anti_template_passed"),
            "swappability_score": cl_res.get("swappability_score"),
            "audit_issues": cl_res.get("audit_issues"),
            "is_fallback": cl_res.get("is_fallback", False),
        }


@router.post("/api/studio/export/markdown")
async def export_markdown_endpoint(req: ExportRequest) -> Response:
    """1-click download clean Markdown document."""
    content, headers = export_markdown(req.content, title=req.title or "document")
    return Response(
        content=content, media_type="text/markdown; charset=utf-8", headers=headers
    )


@router.post("/api/studio/export/pdf")
async def export_pdf_endpoint(req: ExportRequest) -> Response:
    """1-click download professional vector ReportLab A4 PDF."""
    pdf_bytes = export_pdf_bytes(req.content, title=req.title or "document")
    safe_title = sanitize_filename(req.title or "document")
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_title}.pdf"',
        "Content-Type": "application/pdf",
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.post("/api/studio/export")
async def export_general_endpoint(req: ExportRequest) -> Response:
    """Generalized export endpoint supporting format='markdown' (default) or format='pdf'."""
    fmt = (req.format or "markdown").lower()
    if fmt == "pdf":
        return await export_pdf_endpoint(req)
    return await export_markdown_endpoint(req)


@router.get("/api/studio/documents", response_model=List[GeneratedDocumentResponse])
async def list_generated_documents(
    user_id: str = Query("default_user"),
    doc_type: Optional[str] = None,
    db: sqlite3.Connection = Depends(get_db),
):
    """List generated documents for a user with optional doc_type filtering."""
    query = "SELECT id, user_id, job_id, doc_type, model_used, title, content_markdown, created_at FROM generated_documents WHERE user_id = ?"
    params: List[Any] = [user_id]
    if doc_type:
        query += " AND doc_type = ?"
        params.append(doc_type)
    query += " ORDER BY created_at DESC"

    rows = db.execute(query, params).fetchall()
    return [
        GeneratedDocumentResponse(
            document_id=r["id"],
            user_id=r["user_id"],
            job_id=r["job_id"],
            doc_type=r["doc_type"],
            model_used=r["model_used"],
            title=r["title"],
            content_markdown=r["content_markdown"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/api/studio/documents/{doc_id}", response_model=GeneratedDocumentResponse)
async def get_generated_document(
    doc_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    """Retrieve a specific generated document by document ID."""
    row = db.execute(
        "SELECT id, user_id, job_id, doc_type, model_used, title, content_markdown, created_at FROM generated_documents WHERE id = ?",
        (doc_id,),
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found."
        )

    return GeneratedDocumentResponse(
        document_id=row["id"],
        user_id=row["user_id"],
        job_id=row["job_id"],
        doc_type=row["doc_type"],
        model_used=row["model_used"],
        title=row["title"],
        content_markdown=row["content_markdown"],
        created_at=row["created_at"],
    )
