# Job Dashboard Light

A streamlined Australian job aggregation, resume extrapolation, and bespoke application assistant built with FastAPI and React 19, containerized for Google Cloud Run.

## Quickstart (Local Development)

### 1. Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest tests/ -v
uvicorn job_dashboard_light.main:app --reload --port 8080
```

### 2. Frontend
```bash
cd frontend
npm install
npm run dev
```

### 3. Production Multi-Stage Build
```bash
docker build -t job-dashboard-light .
docker run -p 8080:8080 -e ENVIRONMENT=production job-dashboard-light
```
