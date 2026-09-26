"""
FastAPI application entrypoint, lifespan event hooks, and SPA fallback router.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import checkpoint_wal, get_db_connection, init_db
from .routes.profile import router as profile_router
from .routes.studio import router as studio_router
from .services.expiry import run_hybrid_expiry_check
from .services.storage import get_storage_service

logger = logging.getLogger("job_dashboard_light.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for FastAPI container execution and graceful shutdown."""
    # Startup hook: prepare storage directory, restore state from GCS if available, initialize schema
    logger.info("Initializing Job Dashboard Light application...")
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_file = settings.DATA_DIR / "jobs.sqlite3"

    storage_service = get_storage_service()
    storage_service.data_dir = settings.DATA_DIR
    storage_service.bucket_name = settings.GCS_DATA_BUCKET

    try:
        restore_res = storage_service.restore_database(overwrite_local=False)
        logger.info(f"Storage restore result: {restore_res.message}")
    except Exception as err:
        logger.warning(f"Storage restore encountered warning: {err}")

    init_db(db_file)
    logger.info(f"Database schema initialized at {db_file}")

    yield

    # Shutdown hook: flush WAL pages with TRUNCATE and snapshot to GCS
    logger.info("Graceful shutdown: executing WAL checkpoint and GCS backup...")
    try:
        checkpoint_wal(db_file, mode="TRUNCATE")
        backup_res = storage_service.backup_database(checkpoint=False)
        logger.info(f"Storage backup result: {backup_res.message}")
    except Exception as err:
        logger.warning(f"Storage backup encountered warning on shutdown: {err}")


app = FastAPI(
    title="Job Dashboard Light API",
    description="Streamlined Australian job aggregation and application assistant",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Healthcheck probe for Cloud Run and container orchestration."""
    storage_service = get_storage_service()
    status = storage_service.get_status()
    return {
        "status": "healthy",
        "service": "job-dashboard-light",
        "storage": {
            "gcs_configured": status.gcs_configured,
            "accessible": status.accessible,
            "local_db_exists": status.local_db_exists,
            "local_db_size_bytes": status.local_db_size_bytes,
        },
    }


# Mount REST API routers
app.include_router(profile_router)
app.include_router(studio_router)


# Expiry lifecycle triggers
@app.post("/api/jobs/verify-expiry")
@app.post("/api/admin/expiry/run")
async def verify_expiry_endpoint():
    """Trigger hybrid expiry lifecycle worker across database postings."""
    db_file = settings.DATA_DIR / "jobs.sqlite3"
    with get_db_connection(db_file) as conn:
        return run_hybrid_expiry_check(conn)


# Static file serving & SPA fallback
STATIC_DIR = Path(__file__).resolve().parent / "static"
if (STATIC_DIR / "assets").exists():
    app.mount(
        "/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets"
    )


@app.get("/{full_path:path}")
async def serve_spa_or_fallback(full_path: str):
    """Serve SPA index.html fallback for client-side routing while 404ing API routes."""
    if full_path.startswith("api/") or full_path in (
        "health",
        "docs",
        "redoc",
        "openapi.json",
    ):
        raise HTTPException(status_code=404, detail="Not Found")

    target_file = STATIC_DIR / full_path
    if target_file.is_file():
        return FileResponse(target_file)

    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)

    return JSONResponse(
        {
            "status": "running",
            "service": "job-dashboard-light",
            "message": "SPA assets not compiled in dev mode.",
        },
        status_code=200,
    )
