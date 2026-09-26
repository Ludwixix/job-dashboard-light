"""
Integration test suite for Milestone M3 routes:
- Jobs search, filtering, pagination, and candidate match scoring.
- Scraper coordinator on-demand trigger and health check.
- Auth Google GIS token exchange and active session introspection.
- Kanban tracker application lifecycle stages, notes, and dates.
"""

from __future__ import annotations

from typing import Generator

import pytest
from fastapi.testclient import TestClient

from job_dashboard_light.database import create_connection, get_db, init_db
from job_dashboard_light.main import app
from job_dashboard_light.models import now_iso
from job_dashboard_light.routes.auth import create_session_token


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    """Test client with isolated SQLite database."""
    db_file = str(tmp_path / "test_m3.sqlite3")
    init_db(db_file)

    def override_get_db():
        conn = create_connection(db_file)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed sample jobs
    with create_connection(db_file) as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, title, company, location, description, salary_raw, salary_min, salary_max,
                salary_annualized, source, url, tags, status, posted_date, posted_age_days,
                created_at, updated_at
            ) VALUES
            (
                'job_1', 'Senior Site Reliability Engineer', 'Atlassian', 'Sydney, NSW',
                'Looking for an SRE with strong Kubernetes, Terraform, and Python expertise.',
                '$160,000 - $180,000 + 11.5% Super', 160000.0, 180000.0, 170000.0,
                'Seek', 'https://seek.com.au/job/1', '["Kubernetes", "Terraform", "Python"]',
                'active', '2026-09-24T00:00:00Z', 2, ?, ?
            ),
            (
                'job_2', 'Cloud DevOps Engineer', 'Canva', 'Melbourne, VIC',
                'Join our platform team building scalable infrastructure with AWS, Docker, and CI/CD.',
                '$140,000', 140000.0, 140000.0, 140000.0,
                'LinkedIn', 'https://linkedin.com/job/2', '["AWS", "Docker"]',
                'active', '2026-09-20T00:00:00Z', 6, ?, ?
            ),
            (
                'job_3', 'APS 6 Systems Administrator', 'Department of Defence', 'Canberra, ACT',
                'Public sector systems administration role with Linux and Azure focus.',
                '$95,000 - $110,000', 95000.0, 110000.0, 102500.0,
                'APS Jobs', 'https://apsjobs.gov.au/job/3', '["Linux", "Azure"]',
                'active', '2026-09-15T00:00:00Z', 11, ?, ?
            ),
            (
                'job_expired', 'Legacy Systems Analyst', 'OldCorp', 'Sydney, NSW',
                'This job is archived and expired.', '$100,000', 100000.0, 100000.0, 100000.0,
                'Seek', 'https://seek.com.au/job/expired', '["COBOL"]',
                'expired', '2026-08-01T00:00:00Z', 56, ?, ?
            );
            """,
            (now_iso(), now_iso(), now_iso(), now_iso(), now_iso(), now_iso(), now_iso(), now_iso()),
        )
        # Seed user record first (for foreign key constraint)
        conn.execute(
            "INSERT INTO users (id, email, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("usr_sre_alice", "alice@example.com", "Alice SRE", now_iso(), now_iso()),
        )
        # Seed candidate profile
        conn.execute(
            """
            INSERT INTO user_profiles (
                user_id, seniority, target_titles, core_skills, preferred_locations, target_salary_min, updated_at
            ) VALUES (
                'usr_sre_alice', 'Senior', '["Site Reliability Engineer", "DevOps Engineer"]',
                '["Kubernetes", "Terraform", "Python", "AWS"]', '["Sydney, NSW", "All Australia"]', 150000.0, ?
            );
            """,
            (now_iso(),),
        )

    yield TestClient(app)
    app.dependency_overrides.clear()


def test_jobs_list_and_match_scoring(client: TestClient):
    """Verify GET /api/jobs returns jobs with accurate match scoring for candidate profile."""
    res = client.get("/api/jobs?user_id=usr_sre_alice")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3  # Active jobs only by default
    assert len(data["jobs"]) == 3

    # Check top job match scoring
    sre_job = next(j for j in data["jobs"] if j["id"] == "job_1")
    assert sre_job["company"] == "Atlassian"
    assert sre_job["match_score"] is not None
    assert sre_job["match_score"] >= 75.0  # Strong match
    assert "Kubernetes" in sre_job["matched_skills"]
    assert "Terraform" in sre_job["matched_skills"]


def test_jobs_filters_and_fts(client: TestClient):
    """Verify keyword FTS5 search, location filtering, and salary filtering."""
    # FTS search
    res_search = client.get("/api/jobs?q=Kubernetes")
    assert res_search.status_code == 200
    assert len(res_search.json()["jobs"]) == 1
    assert res_search.json()["jobs"][0]["id"] == "job_1"

    # Location filter
    res_loc = client.get("/api/jobs?location=Melbourne")
    assert res_loc.status_code == 200
    assert len(res_loc.json()["jobs"]) == 1
    assert res_loc.json()["jobs"][0]["company"] == "Canva"

    # Salary floor filter
    res_sal = client.get("/api/jobs?min_salary=150000")
    assert res_sal.status_code == 200
    assert len(res_sal.json()["jobs"]) == 1
    assert res_sal.json()["jobs"][0]["id"] == "job_1"


def test_jobs_detail_endpoint(client: TestClient):
    """Verify GET /api/jobs/{job_id} returns enriched job details."""
    res = client.get("/api/jobs/job_1?user_id=usr_sre_alice")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["job"]["title"] == "Senior Site Reliability Engineer"
    assert body["job"]["match_score"] > 70.0


def test_auth_token_and_me_endpoint(client: TestClient):
    """Verify session token creation and /api/auth/me resolution."""
    token = create_session_token("usr_test_auth", "auth@example.com", "Auth User")
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    user = res.json()
    assert user["id"] == "usr_test_auth"
    assert user["email"] == "auth@example.com"
    assert user["name"] == "Auth User"


def test_auth_google_login(client: TestClient):
    """Verify POST /api/auth/google returns session token and upserts user."""
    res = client.post("/api/auth/google", json={"credential": "mock_google_id_token_12345"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "token" in data
    assert data["user"]["id"].startswith("google_")


def test_tracker_lifecycle_crud(client: TestClient):
    """Verify Kanban pipeline tracking CRUD: create Draft -> move to Interviewing -> update notes -> delete."""
    headers = {"X-User-Id": "usr_sre_alice"}

    # 1. Initially 0 tracked applications
    res_list = client.get("/api/applications", headers=headers)
    assert res_list.status_code == 200
    assert res_list.json()["total"] == 0

    # 2. Track Atlassian job in Draft
    create_payload = {
        "job_id": "job_1",
        "status": "Draft",
        "notes": "Need to tailor CV first.",
    }
    res_create = client.post("/api/applications", json=create_payload, headers=headers)
    assert res_create.status_code == 201
    app_id = res_create.json()["application_id"]

    # 3. Retrieve board and assert card is in Draft bucket
    res_board = client.get("/api/applications", headers=headers)
    board_data = res_board.json()
    assert board_data["total"] == 1
    assert len(board_data["board"]["Draft"]) == 1
    assert board_data["board"]["Draft"][0]["job_company"] == "Atlassian"

    # 4. Patch status to Interviewing with interview date
    patch_payload = {
        "status": "Interviewing",
        "interview_at": "2026-10-01T14:00:00Z",
        "notes": "System design round with Head of Platform.",
        "recruiter_name": "Dave Miller",
    }
    res_patch = client.patch(f"/api/applications/{app_id}", json=patch_payload, headers=headers)
    assert res_patch.status_code == 200

    # 5. Verify card moved to Interviewing bucket
    res_board_updated = client.get("/api/applications", headers=headers)
    updated_board = res_board_updated.json()
    assert len(updated_board["board"]["Draft"]) == 0
    assert len(updated_board["board"]["Interviewing"]) == 1
    card = updated_board["board"]["Interviewing"][0]
    assert card["recruiter_name"] == "Dave Miller"
    assert card["interview_at"] == "2026-10-01T14:00:00Z"

    # 6. Delete application
    res_del = client.delete(f"/api/applications/{app_id}", headers=headers)
    assert res_del.status_code == 200

    # 7. Assert board is empty
    res_empty = client.get("/api/applications", headers=headers)
    assert res_empty.json()["total"] == 0


def test_scraper_health_endpoint(client: TestClient):
    """Verify GET /api/scrape/status checks scraper adapters."""
    res = client.get("/api/scrape/status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "sources" in data
    assert len(data["sources"]) == 6  # Seek, Indeed, LinkedIn, Adzuna, Careers Vic, APS Jobs
