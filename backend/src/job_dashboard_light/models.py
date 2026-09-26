"""
Relational Schema DDL, SQL Triggers, and Pydantic Domain Models for Job Dashboard Light.

Defines schemas for:
- jobs: Global shared job listings pool with salary parsing and expiry tracking.
- users: User identity records authenticated via Google GIS OAuth.
- user_profiles: Candidate facts, resumes, target roles, skills, and salary expectations.
- user_applications: Kanban tracking stages, recruiter contact info, interview dates, and notes.
- user_preferences: Search keywords, excluded terms, salary floor, and model selection.
- generated_documents: ATS CVs, Cover Letters, and Australian STAR KSC statements.
- jobs_fts: SQLite FTS5 external content full-text index with sync triggers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator

# ==============================================================================
# 1. Relational Schema DDL & Performance Indexes
# ==============================================================================

SCHEMA_DDL = """
-- 1. Global Scraped Jobs Table
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT 'All Australia',
    description TEXT NOT NULL,
    salary_raw TEXT,
    salary_min REAL,
    salary_max REAL,
    salary_type TEXT, -- 'annual', 'hourly', 'daily', 'undisclosed'
    salary_annualized REAL,
    posted_date TEXT, -- ISO 8601 string
    posted_age_days INTEGER,
    closing_date TEXT, -- ISO 8601 string or YYYY-MM-DD
    source TEXT NOT NULL, -- 'Seek', 'Indeed', 'LinkedIn', 'Adzuna', 'Careers Vic', 'APS Jobs'
    url TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]', -- JSON array of strings
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'expired', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_age ON jobs(posted_age_days);
CREATE INDEX IF NOT EXISTS idx_jobs_salary_annualized ON jobs(salary_annualized DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_closing_date ON jobs(closing_date);
CREATE INDEX IF NOT EXISTS idx_jobs_company_title ON jobs(company, title);

-- 2. Authenticated Users Table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, -- 'google_<sub_id>' or 'user_<uuid>'
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    avatar_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 3. Candidate Source-of-Truth Profile Table
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    raw_resume_text TEXT NOT NULL DEFAULT '',
    seniority TEXT NOT NULL DEFAULT 'Mid',
    target_titles TEXT NOT NULL DEFAULT '[]', -- JSON array of strings
    core_skills TEXT NOT NULL DEFAULT '[]', -- JSON array of strings
    experience_summary TEXT NOT NULL DEFAULT '',
    preferred_locations TEXT NOT NULL DEFAULT '[]', -- JSON array of strings
    target_salary_min REAL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 4. User Application Pipeline Kanban Table
CREATE TABLE IF NOT EXISTS user_applications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Draft' CHECK(status IN ('Draft', 'Applied', 'Interviewing', 'Offered', 'Rejected')),
    recruiter_name TEXT,
    recruiter_email TEXT,
    recruiter_phone TEXT,
    interview_at TEXT, -- ISO 8601 string
    notes TEXT NOT NULL DEFAULT '',
    applied_at TEXT, -- ISO 8601 string
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, job_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_apps_user ON user_applications(user_id);
CREATE INDEX IF NOT EXISTS idx_user_apps_status ON user_applications(user_id, status);
CREATE INDEX IF NOT EXISTS idx_user_apps_updated ON user_applications(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_apps_interview ON user_applications(user_id, interview_at);

-- 5. User Search & Model Preferences Table
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    search_terms TEXT NOT NULL DEFAULT '[]', -- JSON array of strings
    preferred_locations TEXT NOT NULL DEFAULT '[]', -- JSON array of strings
    salary_floor REAL,
    exclude_terms TEXT NOT NULL DEFAULT '[]', -- JSON array of strings
    default_model TEXT NOT NULL DEFAULT 'deepseek/deepseek-chat',
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 6. Generated Tailored Documents Table
CREATE TABLE IF NOT EXISTS generated_documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    doc_type TEXT NOT NULL CHECK(doc_type IN ('cv', 'cover_letter', 'ksc')),
    model_used TEXT NOT NULL,
    title TEXT NOT NULL,
    content_markdown TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_gen_docs_user_job ON generated_documents(user_id, job_id);
CREATE INDEX IF NOT EXISTS idx_gen_docs_user_type ON generated_documents(user_id, doc_type);
CREATE INDEX IF NOT EXISTS idx_gen_docs_created ON generated_documents(user_id, created_at DESC);
"""

# ==============================================================================
# 2. SQLite FTS5 Full-Text Search Virtual Table
# ==============================================================================

FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
    title,
    company,
    location,
    description,
    content='jobs',
    content_rowid='rowid',
    tokenize="porter unicode61 tokenchars '+#.'"
);
"""

# ==============================================================================
# 3. Real-Time Full-Text Search Synchronization Triggers
# ==============================================================================

TRIGGERS_DDL = """
-- Trigger 1: Real-time sync on INSERT
CREATE TRIGGER IF NOT EXISTS jobs_ai AFTER INSERT ON jobs BEGIN
    INSERT INTO jobs_fts(rowid, title, company, location, description)
    VALUES (new.rowid, new.title, new.company, new.location, new.description);
END;

-- Trigger 2: Real-time sync on DELETE
CREATE TRIGGER IF NOT EXISTS jobs_ad AFTER DELETE ON jobs BEGIN
    INSERT INTO jobs_fts(jobs_fts, rowid, title, company, location, description)
    VALUES ('delete', old.rowid, old.title, old.company, old.location, old.description);
END;

-- Trigger 3: Real-time sync on selective UPDATE
-- Strictly limits re-indexing to text search columns, preventing index churn
-- when status, posted_age_days, or salary updates occur.
CREATE TRIGGER IF NOT EXISTS jobs_au AFTER UPDATE OF title, company, location, description ON jobs BEGIN
    INSERT INTO jobs_fts(jobs_fts, rowid, title, company, location, description)
    VALUES ('delete', old.rowid, old.title, old.company, old.location, old.description);
    INSERT INTO jobs_fts(rowid, title, company, location, description)
    VALUES (new.rowid, new.title, new.company, new.location, new.description);
END;
"""


# ==============================================================================
# 4. Pydantic Domain Models
# ==============================================================================


def now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class Job(BaseModel):
    """Database representation and API model for a job posting."""

    id: str
    title: str
    company: str
    location: str = "All Australia"
    description: str
    salary_raw: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_type: Optional[str] = None
    salary_annualized: Optional[float] = None
    posted_date: Optional[str] = None
    posted_age_days: Optional[int] = None
    closing_date: Optional[str] = None
    source: str
    url: str
    tags: List[str] = Field(default_factory=list)
    status: str = "active"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags_json(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        if isinstance(v, (list, tuple)):
            return [str(x) for x in v]
        return []

    def to_db_row(self) -> dict[str, Any]:
        """Convert model into SQLite column mapping with serialized JSON fields."""
        data = self.model_dump()
        data["tags"] = json.dumps(data["tags"])
        return data


class User(BaseModel):
    """Authenticated user model."""

    id: str
    email: str
    name: str
    avatar_url: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def to_db_row(self) -> dict[str, Any]:
        return self.model_dump()


class UserProfile(BaseModel):
    """Candidate profile source-of-truth model."""

    user_id: str
    raw_resume_text: str = ""
    seniority: str = "Mid"
    target_titles: List[str] = Field(default_factory=list)
    core_skills: List[str] = Field(default_factory=list)
    experience_summary: str = ""
    preferred_locations: List[str] = Field(default_factory=list)
    target_salary_min: Optional[float] = None
    updated_at: str = Field(default_factory=now_iso)

    @field_validator(
        "target_titles", "core_skills", "preferred_locations", mode="before"
    )
    @classmethod
    def parse_string_list_json(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        if isinstance(v, (list, tuple)):
            return [str(x) for x in v]
        return []

    def to_db_row(self) -> dict[str, Any]:
        data = self.model_dump()
        data["target_titles"] = json.dumps(data["target_titles"])
        data["core_skills"] = json.dumps(data["core_skills"])
        data["preferred_locations"] = json.dumps(data["preferred_locations"])
        return data


class UserApplication(BaseModel):
    """Kanban application pipeline card model."""

    id: str
    user_id: str
    job_id: str
    status: str = "Draft"
    recruiter_name: Optional[str] = None
    recruiter_email: Optional[str] = None
    recruiter_phone: Optional[str] = None
    interview_at: Optional[str] = None
    notes: str = ""
    applied_at: Optional[str] = None
    updated_at: str = Field(default_factory=now_iso)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid_statuses = {"Draft", "Applied", "Interviewing", "Offered", "Rejected"}
        if v not in valid_statuses:
            raise ValueError(
                f"Invalid application status: '{v}'. Must be one of {valid_statuses}"
            )
        return v

    def to_db_row(self) -> dict[str, Any]:
        return self.model_dump()


class UserPreferences(BaseModel):
    """User search filters and OpenRouter model settings."""

    user_id: str
    search_terms: List[str] = Field(default_factory=list)
    preferred_locations: List[str] = Field(default_factory=list)
    salary_floor: Optional[float] = None
    exclude_terms: List[str] = Field(default_factory=list)
    default_model: str = "deepseek/deepseek-chat"
    updated_at: str = Field(default_factory=now_iso)

    @field_validator(
        "search_terms", "preferred_locations", "exclude_terms", mode="before"
    )
    @classmethod
    def parse_string_list_json(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        if isinstance(v, (list, tuple)):
            return [str(x) for x in v]
        return []

    def to_db_row(self) -> dict[str, Any]:
        data = self.model_dump()
        data["search_terms"] = json.dumps(data["search_terms"])
        data["preferred_locations"] = json.dumps(data["preferred_locations"])
        data["exclude_terms"] = json.dumps(data["exclude_terms"])
        return data


class GeneratedDocument(BaseModel):
    """Generated bespoke application asset model."""

    id: str
    user_id: str
    job_id: str
    doc_type: str  # 'cv', 'cover_letter', 'ksc'
    model_used: str
    title: str
    content_markdown: str
    created_at: str = Field(default_factory=now_iso)

    @field_validator("doc_type")
    @classmethod
    def validate_doc_type(cls, v: str) -> str:
        valid_types = {"cv", "cover_letter", "ksc"}
        if v not in valid_types:
            raise ValueError(f"Invalid doc_type: '{v}'. Must be one of {valid_types}")
        return v

    def to_db_row(self) -> dict[str, Any]:
        return self.model_dump()


# ==============================================================================
# 5. Interface Contracts & Transport Models (per PROJECT.md)
# ==============================================================================


class SearchQuery(BaseModel):
    """Search request criteria passed to BaseJobSource adapters."""

    term: str
    location: str = "All Australia"
    stream: Optional[str] = None
    exclude_terms: List[str] = Field(default_factory=list)
    page: int = 1
    page_size: int = 25


class NormalizedJob(BaseModel):
    """Standardized job item produced by job source adapters."""

    id: str
    title: str
    company: str
    location: str
    description: str
    salary_raw: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_type: Optional[str] = None
    salary_annualized: Optional[float] = None
    posted_date: Optional[str] = None
    posted_age_days: Optional[int] = None
    closing_date: Optional[str] = None
    source: str
    url: str
    tags: List[str] = Field(default_factory=list)


class JobDetails(BaseModel):
    """Full job details enriched from ad pages."""

    id: str
    full_description: str
    key_selection_criteria: List[str] = Field(default_factory=list)
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    closing_date: Optional[str] = None


class HealthStatus(BaseModel):
    """Scraper connectivity and health diagnostic model."""

    healthy: bool
    source_name: str
    message: str
    last_checked: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SalaryAnalysis(BaseModel):
    """Output of Australian salary normalization engine."""

    raw_salary: str
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    annualized_min: Optional[float] = None
    annualized_max: Optional[float] = None
    annualized_midpoint: Optional[float] = None
    rate_type: str = "undisclosed"
    super_included: bool = False
    super_rate: float = 0.115


class CandidateProfile(BaseModel):
    """Extrapolated candidate profile facts."""

    user_id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    seniority: str = "Mid"
    target_titles: List[str] = Field(default_factory=list)
    core_skills: List[str] = Field(default_factory=list)
    experience_summary: str = ""
    preferred_locations: List[str] = Field(default_factory=list)
    target_salary_min: Optional[float] = None


class DocumentGenerationRequest(BaseModel):
    """Request payload for bespoke document generation."""

    model: str
    doc_type: str  # 'cv', 'cover_letter', 'ksc'
    job_id: str
    job_title: str
    job_description: str
    ksc_criteria: Optional[List[str]] = None
    target_word_limit: int = 350
