"""
Unit Tests for Candidate Profile Ingestion, LLM Extraction, Query Expansion, and REST Endpoints.
"""

from __future__ import annotations

import io
import zipfile

import pypdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from job_dashboard_light.database import init_db
from job_dashboard_light.models import CandidateProfile, NormalizedJob
from job_dashboard_light.routes.profile import router as profile_router
from job_dashboard_light.services.profile import (
    MAX_RESUME_CHARS,
    detect_query_stream,
    expand_search_queries,
    extract_text_from_docx,
    extract_text_from_file,
    extract_text_from_pdf,
    extract_text_from_txt,
    filter_jobs_by_exclude_terms,
    get_default_exclude_terms,
    parse_llm_json_response,
    synthesize_profile_heuristic,
)

# ==============================================================================
# 1. Multi-Format Resume Text Extraction Tests
# ==============================================================================


def test_extract_text_from_pdf():
    # Build a valid in-memory PDF with pypdf
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=300, height=300)
    pdf_buffer = io.BytesIO()
    writer.write(pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()

    # Empty page should extract safely to empty or minimal string
    extracted = extract_text_from_pdf(pdf_bytes)
    assert isinstance(extracted, str)

    # Malformed bytes test
    corrupted = b"NOT_A_PDF_STREAM"
    assert extract_text_from_pdf(corrupted) == ""
    assert extract_text_from_pdf(b"") == ""


def test_extract_text_from_docx():
    # Create valid in-memory docx zip
    docx_buffer = io.BytesIO()
    xml_content = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        "<w:p><w:r><w:t>Sam Ludwig</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Senior Systems &amp; Cloud Engineer</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Melbourne, VIC | AWS, Kubernetes, Terraform</w:t></w:r></w:p>"
        "</w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(docx_buffer, "w") as zf:
        zf.writestr("word/document.xml", xml_content)
    docx_bytes = docx_buffer.getvalue()

    extracted = extract_text_from_docx(docx_bytes)
    assert "Sam Ludwig" in extracted
    assert "Senior Systems & Cloud Engineer" in extracted
    assert "Kubernetes" in extracted

    # Corrupt archive test
    assert extract_text_from_docx(b"corrupted_zip_bytes") == ""
    assert extract_text_from_docx(b"") == ""


def test_extract_text_from_txt():
    # UTF-8
    assert "Hello Melbourne" in extract_text_from_txt("Hello Melbourne".encode("utf-8"))
    # Latin-1
    assert "Resume Café" in extract_text_from_txt("Resume Café".encode("latin-1"))
    # Empty
    assert extract_text_from_txt(b"") == ""


def test_character_slicing_9000_chars():
    long_content = "A" * 15000
    sliced = extract_text_from_file(long_content.encode("utf-8"), filename="test.txt")
    assert len(sliced) == MAX_RESUME_CHARS
    assert len(sliced) == 9000


# ==============================================================================
# 2. Resilient JSON Parsing & LLM Profile Synthesis Tests
# ==============================================================================


def test_resilient_json_parsing():
    # Case 1: Wrapped in markdown code fences
    sample_fenced = (
        "```json\n"
        "{\n"
        '  "name": "Alex Taylor",\n'
        '  "seniority": "Senior",\n'
        '  "target_titles": ["Senior Cloud Engineer"],\n'
        '  "core_skills": ["AWS", "Terraform"]\n'
        "}\n"
        "```"
    )
    parsed = parse_llm_json_response(sample_fenced)
    assert parsed.get("name") == "Alex Taylor"
    assert parsed.get("seniority") == "Senior"

    # Case 2: Leading / trailing commentary and trailing commas
    sample_anomalies = (
        "Here is the parsed candidate profile:\n"
        "{\n"
        '  "name": "Jane Smith",\n'
        '  "target_titles": ["DevOps Lead", "SRE",],\n'
        '  "core_skills": ["Kubernetes", "Docker",],\n'
        "}\n"
        "Let me know if you need more fields."
    )
    parsed2 = parse_llm_json_response(sample_anomalies)
    assert parsed2.get("name") == "Jane Smith"
    assert "DevOps Lead" in parsed2.get("target_titles", [])

    # Case 3: Complete junk input
    assert (
        parse_llm_json_response("This is completely invalid text without any JSON")
        == {}
    )


def test_heuristic_profile_synthesis():
    sample_cv = """
    Jane Smith
    Senior Cloud & DevOps Engineer
    Melbourne, VIC, Australia
    jane.smith@example.com
    0405 123 456

    Professional Summary:
    Over 8 years of experience architecting and automating enterprise cloud infrastructure.
    Specializing in AWS, Kubernetes, Terraform, Docker, Python automation, and CI/CD pipelines.

    Key Skills:
    AWS, Azure, Kubernetes, Terraform, Docker, Python, Bash, CI/CD, GitHub Actions, Linux

    Experience:
    Senior Cloud Specialist - Tech Solutions (2020 - Present)
    - Automated multi-account cloud platform using Terraform and AWS Organizations.
    """
    profile = synthesize_profile_heuristic(sample_cv, user_id="usr_jane_101")
    assert profile.name == "Jane Smith"
    assert profile.email == "jane.smith@example.com"
    assert profile.phone is not None and "0405" in profile.phone
    assert profile.seniority == "Senior"
    assert any("Cloud" in t or "Systems" in t for t in profile.target_titles)
    assert "AWS" in profile.core_skills
    assert "Kubernetes" in profile.core_skills
    assert "Terraform" in profile.core_skills
    assert (
        profile.target_salary_min is not None and profile.target_salary_min >= 140000.0
    )
    assert any("Melbourne" in loc for loc in profile.preferred_locations)


# ==============================================================================
# 3. Dynamic Query Expansion & Negative Filtering Tests
# ==============================================================================


def test_detect_query_stream():
    assert detect_query_stream("Senior Cloud Architect") == "technology"
    assert detect_query_stream("Registered Nurse - Aged Care") == "healthcare"
    assert detect_query_stream("Chartered Accountant / Tax Manager") == "finance"
    assert detect_query_stream("Commercial Carpenter / Site Supervisor") == "trades"
    assert detect_query_stream("Corporate Legal Counsel") == "legal"
    assert detect_query_stream("Operations Coordinator") == "general"


def test_dynamic_query_expansion():
    profile = CandidateProfile(
        user_id="usr_test",
        name="Alex Smith",
        seniority="Senior",
        target_titles=["Systems Engineer", "Cloud Engineer"],
        core_skills=["AWS", "Terraform", "Kubernetes", "PowerShell"],
        preferred_locations=["Melbourne, VIC"],
    )

    queries = expand_search_queries(profile)
    assert len(queries) >= 3

    terms = [q.term for q in queries]
    assert any("Systems Engineer" in t for t in terms)
    assert any("Cloud Engineer" in t for t in terms)

    # Check stream auto-classification
    for q in queries:
        assert q.stream == "technology"
        assert q.location == "Melbourne, VIC"
        # Check negative keyword injection for Senior
        assert "junior" in q.exclude_terms
        assert "intern" in q.exclude_terms
        assert "graduate" in q.exclude_terms


def test_negative_keyword_filtering():
    jobs = [
        NormalizedJob(
            id="job_1",
            title="Senior Cloud Engineer",
            company="Telstra",
            location="Melbourne, VIC",
            description="Manage scalable AWS infrastructure.",
            source="Seek",
            url="https://seek.com.au/job/1",
        ),
        NormalizedJob(
            id="job_2",
            title="Junior Systems Administrator",
            company="Optus",
            location="Sydney, NSW",
            description="Entry level support role.",
            source="Indeed",
            url="https://indeed.com/job/2",
        ),
        NormalizedJob(
            id="job_3",
            title="Graduate Cloud Intern",
            company="Atlassian",
            location="Sydney, NSW",
            description="Summer internship for students.",
            source="LinkedIn",
            url="https://linkedin.com/job/3",
        ),
        NormalizedJob(
            id="job_4",
            title="International Cloud Infrastructure Lead",
            company="BHP",
            location="Melbourne, VIC",
            description="Oversee international enterprise platforms.",
            source="Seek",
            url="https://seek.com.au/job/4",
        ),
    ]

    exclude_terms = get_default_exclude_terms("Senior")
    filtered = filter_jobs_by_exclude_terms(jobs, exclude_terms)

    # Should filter out job_2 (Junior) and job_3 (Graduate/Intern)
    filtered_ids = [j.id for j in filtered]
    assert "job_1" in filtered_ids
    assert "job_4" in filtered_ids  # 'International' must NOT trigger 'intern' match
    assert "job_2" not in filtered_ids
    assert "job_3" not in filtered_ids


# ==============================================================================
# 4. Database Persistence & REST API Endpoints Tests
# ==============================================================================


@pytest.fixture
def test_db_path(tmp_path):
    db_file = tmp_path / "test_jobs.sqlite3"
    init_db(db_file)
    return db_file


@pytest.fixture
def client(test_db_path, monkeypatch):
    import job_dashboard_light.database as db_mod

    monkeypatch.setattr(db_mod, "DEFAULT_DB_PATH", test_db_path)

    app = FastAPI()
    app.include_router(profile_router)
    return TestClient(app)


def test_api_profile_flow(client):
    # 1. GET initial profile (should return default profile)
    res_get = client.get("/api/profile", headers={"X-User-Id": "usr_flow_1"})
    assert res_get.status_code == 200
    body = res_get.json()
    assert body["success"] is True
    assert body["profile"]["user_id"] == "usr_flow_1"

    # 2. POST /upload with plain text resume
    resume_text = (
        "Sarah Jenkins\n"
        "Senior Infrastructure Specialist\n"
        "Brisbane, QLD\n"
        "sarah.jenkins@example.com\n"
        "0405 999 888\n\n"
        "Summary: 7 years managing Azure hybrid infrastructure.\n"
        "Skills: Azure, Terraform, PowerShell, Kubernetes, Docker, Linux\n"
    )
    files = {
        "file": ("resume.txt", io.BytesIO(resume_text.encode("utf-8")), "text/plain")
    }
    res_upload = client.post(
        "/api/profile/upload", files=files, headers={"X-User-Id": "usr_flow_1"}
    )
    assert res_upload.status_code == 200
    upload_body = res_upload.json()
    assert upload_body["success"] is True
    assert upload_body["profile"]["name"] == "Sarah Jenkins"
    assert upload_body["profile"]["email"] == "sarah.jenkins@example.com"
    assert upload_body["profile"]["seniority"] == "Senior"

    # 3. GET profile after upload (should return saved facts)
    res_saved = client.get("/api/profile", headers={"X-User-Id": "usr_flow_1"})
    assert res_saved.status_code == 200
    saved_profile = res_saved.json()["profile"]
    assert saved_profile["name"] == "Sarah Jenkins"
    assert "Azure" in saved_profile["core_skills"]

    # 4. PUT /api/profile to update preferences
    saved_profile["target_salary_min"] = 160000.0
    saved_profile["target_titles"].append("Cloud Architect")
    res_put = client.put(
        "/api/profile", json=saved_profile, headers={"X-User-Id": "usr_flow_1"}
    )
    assert res_put.status_code == 200
    assert res_put.json()["profile"]["target_salary_min"] == 160000.0

    # 5. Verify persistence across fresh GET
    res_verify = client.get("/api/profile", headers={"X-User-Id": "usr_flow_1"})
    assert res_verify.json()["profile"]["target_salary_min"] == 160000.0
    assert "Cloud Architect" in res_verify.json()["profile"]["target_titles"]
