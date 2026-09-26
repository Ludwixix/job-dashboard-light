"""
Unit tests for all BaseJobSource scraper adapters using mocked HTTP responses.
"""

import asyncio

import httpx

from job_dashboard_light.models import SearchQuery
from job_dashboard_light.scrapers.adzuna import AdzunaJobSource
from job_dashboard_light.scrapers.aps_jobs import APSJobsJobSource
from job_dashboard_light.scrapers.careers_vic import CareersVicJobSource
from job_dashboard_light.scrapers.seek import SeekJobSource


def test_seek_job_source_search(monkeypatch):
    source = SeekJobSource()

    mock_resp = {
        "data": [
            {
                "id": "112233",
                "title": "Cloud Architect",
                "advertiser": {"description": "Seek Limited"},
                "locationHierarchy": {"city": {"description": "Melbourne"}},
                "teaser": "Help design next-gen cloud platforms.",
                "salary": "$150k - $180k + super",
                "listingDate": "2026-09-20T00:00:00Z",
            }
        ]
    }

    async def mock_get(*args, **kwargs):
        return httpx.Response(200, json=mock_resp)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    query = SearchQuery(term="Architect", location="Melbourne")
    jobs = asyncio.run(source.search(query))
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "seek_112233"
    assert job.title == "Cloud Architect"
    assert job.company == "Seek Limited"
    assert job.source == "Seek"
    assert job.salary_min == 150000.0


def test_adzuna_job_source_search(monkeypatch):
    source = AdzunaJobSource(app_id="dummy_app", app_key="dummy_key")

    mock_resp = {
        "results": [
            {
                "id": "998877",
                "title": "Lead Python Developer",
                "company": {"display_name": "Adzuna Tech"},
                "location": {"display_name": "Sydney NSW"},
                "description": "Full-stack Python and FastAPI development.",
                "salary_min": 140000,
                "salary_max": 160000,
                "redirect_url": "https://www.adzuna.com.au/land/ad/998877",
                "created": "2026-09-22T08:00:00Z",
            }
        ]
    }

    async def mock_get(*args, **kwargs):
        return httpx.Response(200, json=mock_resp)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    query = SearchQuery(term="Python", location="Sydney")
    jobs = asyncio.run(source.search(query))
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "adzuna_998877"
    assert job.title == "Lead Python Developer"
    assert job.source == "Adzuna"


def test_careers_vic_job_source_search(monkeypatch):
    source = CareersVicJobSource()

    mock_html = """
    <div class="job-item">
        <a href="/job/445566">Senior Policy Analyst</a>
        <div class="department">Department of Premier and Cabinet</div>
        <div class="location">Melbourne CBD</div>
        <div class="summary">Lead state public policy initiatives.</div>
        <div class="salary">$115,000 - $130,000</div>
    </div>
    """

    async def mock_get(*args, **kwargs):
        return httpx.Response(200, text=mock_html)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    query = SearchQuery(term="Policy")
    jobs = asyncio.run(source.search(query))
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "vic_445566"
    assert job.title == "Senior Policy Analyst"
    assert job.company == "Department of Premier and Cabinet"
    assert job.source == "Careers Vic"


def test_aps_jobs_job_source_search(monkeypatch):
    source = APSJobsJobSource()

    mock_html = """
    <div class="job-card">
        <a href="/s/job-details?Id=APS1234">Assistant Director - Data Governance</a>
        <div class="agency">Australian Bureau of Statistics</div>
        <div class="location">Canberra ACT</div>
        <div class="description">Deliver high-quality statistical governance.</div>
        <div class="remuneration">$125,000 + 15.4% super</div>
    </div>
    """

    async def mock_get(*args, **kwargs):
        return httpx.Response(200, text=mock_html)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    query = SearchQuery(term="Director", location="Canberra")
    jobs = asyncio.run(source.search(query))
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "aps_APS1234"
    assert job.title == "Assistant Director - Data Governance"
    assert job.company == "Australian Bureau of Statistics"
    assert job.source == "APS Jobs"
