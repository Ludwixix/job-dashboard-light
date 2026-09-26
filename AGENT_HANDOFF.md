# Agent Handoff Guide — Job Dashboard Light

## Operational Overview
Job Dashboard Light is an Australian career assistant combining multi-source web scrapers (Seek, Indeed, LinkedIn, Adzuna, Careers Vic, APS Jobs), an ATS CV and Cover Letter Studio powered by OpenRouter LLMs, and an isolated SQLite WAL database synced to Google Cloud Storage.

## Repository Commands
- **Backend Tests**: `cd backend && python3 -m pytest tests/ -v`
- **Backend Lint**: `cd backend && ruff check .`
- **Frontend Build**: `cd frontend && npm run build`
- **Health Check Probe**: `curl -f http://localhost:8080/health`
- **Docker Build**: `docker build -t job-dashboard-light .`
