"""
Unit and integration tests for OpenRouter Client, Model Presets, ATS CV & Polarized Cover Letters.
"""

from __future__ import annotations

import asyncio
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from job_dashboard_light.config import settings
from job_dashboard_light.database import create_connection, get_db, init_db
from job_dashboard_light.main import app
from job_dashboard_light.services.llm import (
    DEFAULT_MODEL_ID,
    DELIMITER_COVER_LETTER,
    DELIMITER_RESUME,
    MODEL_PRESETS,
    OpenRouterAPIError,
    OpenRouterAuthError,
    OpenRouterClient,
    OpenRouterRateLimitError,
    audit_cover_letter_swappability,
    extract_delimited_content,
    generate_polarized_cover_letter,
    generate_tailored_cv,
    localize_australian,
)


@pytest.fixture
def client_with_temp_db(tmp_path) -> Generator[TestClient, None, None]:
    """TestClient with an isolated temporary SQLite database."""
    db_file = str(tmp_path / "test_studio.sqlite3")
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
    yield TestClient(app)
    app.dependency_overrides.clear()


# ==============================================================================
# 1. Model Presets & Dropdown Tests
# ==============================================================================


def test_model_presets_specification():
    """Verify that all required model presets and default model are defined."""
    assert len(MODEL_PRESETS) >= 4
    preset_ids = [m["id"] for m in MODEL_PRESETS]

    assert "deepseek/deepseek-chat" in preset_ids
    assert "anthropic/claude-3.5-sonnet" in preset_ids
    assert "openai/gpt-4o-mini" in preset_ids
    assert "google/gemini-2.5-flash" in preset_ids

    assert DEFAULT_MODEL_ID == "deepseek/deepseek-chat"
    default_preset = next(m for m in MODEL_PRESETS if m["id"] == DEFAULT_MODEL_ID)
    assert default_preset["is_default"] is True


def test_get_studio_models_endpoint(client_with_temp_db: TestClient):
    """Verify that GET /api/studio/models returns valid presets JSON."""
    response = client_with_temp_db.get("/api/studio/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "default_model" in data
    assert data["default_model"] == "deepseek/deepseek-chat"
    assert len(data["models"]) >= 4


# ==============================================================================
# 2. Delimiter Parsing & String Extraction Tests
# ==============================================================================


def test_extract_delimited_content_resume():
    """Verify reliable CV extraction following ===RESUME=== delimiter."""
    sample_llm_output = (
        "Here is the tailored resume you requested:\n\n"
        "===RESUME===\n"
        "# Sam Ludwig\n"
        "**Email:** sam@example.com | **Location:** Melbourne, VIC\n\n"
        "## Professional Summary\n"
        "Senior Systems Engineer with deep expertise in cloud platforms.\n"
    )
    extracted = extract_delimited_content(sample_llm_output, DELIMITER_RESUME)
    assert extracted.startswith("# Sam Ludwig")
    assert "Here is the tailored resume" not in extracted
    assert "## Professional Summary" in extracted


def test_extract_delimited_content_cover_letter():
    """Verify reliable Cover Letter extraction following ===COVER_LETTER=== delimiter."""
    sample_llm_output = (
        "Certainly! Attached is your high-conviction cover letter:\n\n"
        "===COVER_LETTER===\n"
        "Dear Canva Hiring Team,\n\n"
        "Scaling global infrastructure requires rigorous operational discipline.\n\n"
        "Kind regards,\n"
        "Sam Ludwig"
    )
    extracted = extract_delimited_content(sample_llm_output, DELIMITER_COVER_LETTER)
    assert extracted.startswith("Dear Canva Hiring Team,")
    assert "Attached is your high-conviction cover letter" not in extracted


def test_extract_delimited_content_handles_multiple_delimiters():
    """Verify delimiter cutting isolates only the targeted document part."""
    multi_part_output = (
        "===RESUME===\n"
        "# Resume Content Here\n"
        "===COVER_LETTER===\n"
        "Dear Hiring Manager,\n"
        "Cover letter content here.\n"
    )
    resume = extract_delimited_content(multi_part_output, DELIMITER_RESUME)
    assert resume == "# Resume Content Here"


def test_extract_delimited_content_fallback_strip_markdown():
    """Verify fallback cleaning when the model omits delimiter token."""
    output_without_delim = (
        "Sure, here is your document:\n\n"
        "```markdown\n"
        "# Executive CV\n"
        "Experienced Engineer.\n"
        "```"
    )
    extracted = extract_delimited_content(output_without_delim, DELIMITER_RESUME)
    assert extracted.startswith("# Executive CV")
    assert "Experienced Engineer." in extracted


# ==============================================================================
# 3. OpenRouter Client & Error Handling Tests
# ==============================================================================


def test_openrouter_client_request_construction():
    """Verify that OpenRouterClient formats headers, auth token, and payload correctly."""
    client = OpenRouterClient(api_key="sk-or-testkey-12345")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "===RESUME===\n# Test CV"}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        messages = [{"role": "user", "content": "Generate CV"}]
        res = asyncio.run(
            client.chat_completion(
                messages=messages,
                model="anthropic/claude-3.5-sonnet",
                temperature=0.3,
                max_tokens=2000,
            )
        )

        assert res == "===RESUME===\n# Test CV"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args

        assert args[0] == "https://openrouter.ai/api/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer sk-or-testkey-12345"
        assert (
            kwargs["headers"]["HTTP-Referer"] == "https://job-dashboard-light.openclaw"
        )
        assert kwargs["json"]["model"] == "anthropic/claude-3.5-sonnet"
        assert kwargs["json"]["temperature"] == 0.3
        assert kwargs["json"]["max_tokens"] == 2000


def test_openrouter_client_unauthorized_error():
    """Verify OpenRouterAuthError is raised when OpenRouter returns 401."""
    client = OpenRouterClient(api_key="invalid-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized: Invalid API key"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(OpenRouterAuthError):
            asyncio.run(
                client.chat_completion(messages=[{"role": "user", "content": "hi"}])
            )


def test_openrouter_client_rate_limit_error():
    """Verify OpenRouterRateLimitError is raised on HTTP 429."""
    client = OpenRouterClient(api_key="valid-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate limit exceeded"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(OpenRouterRateLimitError):
            asyncio.run(
                client.chat_completion(messages=[{"role": "user", "content": "hi"}])
            )


def test_openrouter_client_timeout_error():
    """Verify OpenRouterAPIError is raised on timeout."""
    client = OpenRouterClient(api_key="valid-key")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Read timed out")
        with pytest.raises(OpenRouterAPIError) as exc_info:
            asyncio.run(
                client.chat_completion(messages=[{"role": "user", "content": "hi"}])
            )
        assert "timed out" in str(exc_info.value)


# ==============================================================================
# 4. Tailored ATS CV Generation Tests
# ==============================================================================


def test_generate_tailored_cv_mocked_llm():
    """Verify tailored CV generation extracts clean markdown and localizes spelling."""
    client = OpenRouterClient(api_key="mock-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        "===RESUME===\n"
                        "# Candidate Name\n"
                        "## Professional Summary\n"
                        "Spearheaded technical programs to optimize system throughput.\n"
                    )
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = asyncio.run(
            generate_tailored_cv(
                job={
                    "title": "Cloud Architect",
                    "company": "Atlassian",
                    "description": "AWS & Kubernetes",
                },
                profile={"name": "Jane Doe", "core_skills": ["AWS", "Kubernetes"]},
                model="openai/gpt-4o-mini",
                client=client,
            )
        )

        assert result["model_used"] == "openai/gpt-4o-mini"
        assert result["is_fallback"] is False
        assert "# Candidate Name" in result["content_markdown"]
        # Assert Australian localization: optimize -> optimise, programs -> programmes
        assert "optimise" in result["content_markdown"]
        assert "programmes" in result["content_markdown"]


def test_cv_generation_api_endpoint(client_with_temp_db: TestClient):
    """Verify POST /api/studio/cv endpoint end-to-end with DB persistence."""
    req_payload = {
        "job_title": "Staff Infrastructure Engineer",
        "company": "Canva",
        "location": "Sydney, NSW",
        "job_description": "Building high-availability Kubernetes platforms.",
        "model": "deepseek/deepseek-chat",
        "user_id": "test_user_cv",
        "profile_data": {
            "name": "Alex Smith",
            "core_skills": ["Kubernetes", "Terraform", "Python"],
            "experience_summary": "10 years scaling platform infrastructure.",
        },
    }

    response = client_with_temp_db.post("/api/studio/cv", json=req_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["doc_type"] == "cv"
    assert data["document_id"].startswith("doc_cv_")
    assert (
        "Alex Smith" in data["content_markdown"] or "Canva" in data["content_markdown"]
    )

    # Verify document persisted in database
    list_resp = client_with_temp_db.get("/api/studio/documents?user_id=test_user_cv")
    assert list_resp.status_code == 200
    docs = list_resp.json()
    assert len(docs) == 1
    assert docs[0]["document_id"] == data["document_id"]


# ==============================================================================
# 5. Polarized Cover Letter Generation & Audit Tests
# ==============================================================================


def test_generate_polarized_cover_letter_mocked_llm():
    """Verify 3-paragraph polarized cover letter generation and swappability audit."""
    client = OpenRouterClient(api_key="mock-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        "===COVER_LETTER===\n"
                        "Scaling infrastructure at Canva requires rigorous operational discipline and high systems reliability.\n\n"
                        "Over the past five years, I orchestrated cloud migrations cutting costs by 35% across 1.2M transactions.\n\n"
                        "I welcome the opportunity to discuss Canva's operational roadmap and immediate technical deliverables."
                    )
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = asyncio.run(
            generate_polarized_cover_letter(
                job={"title": "Platform Lead", "company": "Canva"},
                profile={"name": "Alex", "core_skills": ["Kubernetes"]},
                model="anthropic/claude-3.5-sonnet",
                variant="high_conviction",
                client=client,
            )
        )

        assert result["model_used"] == "anthropic/claude-3.5-sonnet"
        assert result["anti_template_passed"] is True
        assert result["swappability_score"] <= 35  # low swappability risk


def test_cover_letter_anti_template_cliche_detection():
    """Verify audit_cover_letter_swappability flags generic corporate cliché openers."""
    cliche_letter = (
        "I am writing to apply for the role of Systems Administrator at TestCorp.\n\n"
        "I am a results-driven team player with a passion for excellence.\n\n"
        "Please accept my resume and contact me at your convenience."
    )
    score, passed, issues = audit_cover_letter_swappability(
        cliche_letter, company="TestCorp", title="Systems Administrator"
    )
    assert passed is False
    assert any("Cliché opener detected" in issue for issue in issues)
    assert score > 50  # high swappability risk


def test_cover_letter_generation_api_endpoint(client_with_temp_db: TestClient):
    """Verify POST /api/studio/cover-letter endpoint end-to-end with DB persistence."""
    req_payload = {
        "job_title": "Senior Reliability Engineer",
        "company": "ANZ Bank",
        "location": "Melbourne, VIC",
        "job_description": "Managing mission-critical financial ledger reliability.",
        "model": "google/gemini-2.5-flash",
        "variant": "systems_architect",
        "user_id": "test_user_cl",
    }

    response = client_with_temp_db.post("/api/studio/cover-letter", json=req_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["doc_type"] == "cover_letter"
    assert data["document_id"].startswith("doc_cl_")
    assert "ANZ Bank" in data["content_markdown"]
    assert data["anti_template_passed"] is True
    assert data["swappability_score"] is not None

    # Verify retrieval by document ID
    get_resp = client_with_temp_db.get(f"/api/studio/documents/{data['document_id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == data["title"]


# ==============================================================================
# 6. Localization & Offline Fallback Tests
# ==============================================================================


def test_australian_english_spelling_transforms():
    """Verify comprehensive conversion of American spellings to Australian English."""
    american_text = (
        "We prioritize efficiency and organize teams to optimize performance and analyze behaviors. "
        "Our defense program utilizes centralized licenses."
    )
    au_text = localize_australian(american_text)
    assert "prioritise" in au_text
    assert "organise" in au_text
    assert "optimise" in au_text
    assert "analyse" in au_text
    assert "behaviours" in au_text
    assert "defence" in au_text
    assert "programme" in au_text
    assert "utilise" in au_text
    assert "licence" in au_text


def test_offline_fallback_generation_when_no_api_key():
    """Verify that generator returns clean, valid grounded documents when API key is unset."""
    with patch.object(settings, "OPENROUTER_API_KEY", ""):
        cv_res = asyncio.run(
            generate_tailored_cv(
                job={"title": "DevOps Engineer", "company": "Telstra"},
                profile={"name": "Sam Ludwig", "core_skills": ["Terraform", "AWS"]},
            )
        )
        assert cv_res["is_fallback"] is True
        assert "# Sam Ludwig" in cv_res["content_markdown"]
        assert "Telstra" in cv_res["content_markdown"]

        cl_res = asyncio.run(
            generate_polarized_cover_letter(
                job={"title": "DevOps Engineer", "company": "Telstra"},
                profile={"name": "Sam Ludwig", "core_skills": ["Terraform", "AWS"]},
                variant="cultural_outlier",
            )
        )
        assert cl_res["is_fallback"] is True
        assert "Telstra" in cl_res["content_markdown"]
        assert cl_res["anti_template_passed"] is True
