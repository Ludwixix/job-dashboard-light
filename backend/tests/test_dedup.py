"""
Unit tests for URL sanitization and job deduplication hashing.
"""

from job_dashboard_light.services.dedup import compute_job_dedup_hash, sanitize_url


def test_sanitize_url_strips_utm_and_tracking_tokens():
    raw_url = "https://www.seek.com.au/job/12345?utm_source=google&utm_medium=cpc&gclid=ABC123XYZ&ref=search#apply"
    cleaned = sanitize_url(raw_url)
    assert cleaned == "https://www.seek.com.au/job/12345"
    assert "utm_source" not in cleaned
    assert "gclid" not in cleaned
    assert "#apply" not in cleaned


def test_sanitize_url_preserves_legitimate_queries():
    raw_url = "https://www.apsjobs.gov.au/s/job-details?Id=98765"
    cleaned = sanitize_url(raw_url)
    assert cleaned == "https://www.apsjobs.gov.au/s/job-details?Id=98765"


def test_compute_job_dedup_hash_deterministic():
    hash1 = compute_job_dedup_hash(
        company="Canva Pty Ltd",
        title="Senior Python Engineer",
        clean_url="https://canva.com/job/1",
    )
    hash2 = compute_job_dedup_hash(
        company="canva pty ltd",
        title="Senior Python Engineer",
        clean_url="https://canva.com/job/1",
    )
    assert hash1 == hash2
    assert len(hash1) == 16


def test_compute_job_dedup_hash_distinguishes_different_titles():
    hash_eng = compute_job_dedup_hash("Atlassian", "Software Engineer", "https://atlassian.com/1")
    hash_mgr = compute_job_dedup_hash("Atlassian", "Engineering Manager", "https://atlassian.com/1")
    assert hash_eng != hash_mgr
