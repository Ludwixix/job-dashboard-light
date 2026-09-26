"""
Hybrid Expiry Lifecycle Worker.

Enforces:
1. Explicit closing dates: marks expired when closing_date < current date.
2. Background URL verification: checks external URLs for ads >= 14 days old (404, 410, taken down, expired banners).
3. 30-day hard fallback: marks unverified stale ads with posted_age_days > 30 as expired.
4. Auto-detects table schema (status column and optional is_expired column).
"""

from __future__ import annotations

import datetime
import logging
import sqlite3
from pathlib import Path
from typing import Any

from .verifier import verify_job_url

logger = logging.getLogger("job_dashboard_light.services.expiry")


def run_hybrid_expiry_check(
    conn_or_path: sqlite3.Connection | str | Path,
    current_date: datetime.date | None = None,
    force_url_check: bool = False,
) -> dict[str, Any]:
    """Execute 3-tier hybrid expiry evaluation on database listings.

    Returns structured metrics payload matching E2E test contracts:
    {
        "total_expired": int,
        "closing_date_expired": int,
        "url_check_expired": int,
        "fallback_30d_expired": int,
        "jobs_evaluated": int,
        "timestamp": str,
    }
    """
    today = current_date or datetime.datetime.now(datetime.timezone.utc).date()
    today_iso = today.isoformat()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    close_conn_on_exit = False
    if isinstance(conn_or_path, sqlite3.Connection):
        conn = conn_or_path
    else:
        conn = sqlite3.connect(str(conn_or_path))
        conn.row_factory = sqlite3.Row
        close_conn_on_exit = True

    try:
        cur = conn.cursor()

        # Introspect table columns to support both schema styles seamlessly
        table_info = cur.execute("PRAGMA table_info(jobs);").fetchall()
        cols = {row[1] for row in table_info}
        has_is_expired = "is_expired" in cols
        has_status = "status" in cols

        # Helper to mark a list of job IDs as expired
        def mark_jobs_expired(job_ids: list[str]) -> None:
            if not job_ids:
                return
            placeholders = ",".join("?" for _ in job_ids)
            if has_is_expired and has_status:
                sql = f"UPDATE jobs SET status = 'expired', is_expired = 1, updated_at = ? WHERE id IN ({placeholders})"
                params = [now_iso] + job_ids
                cur.execute(sql, params)
            elif has_is_expired:
                sql = f"UPDATE jobs SET is_expired = 1, updated_at = ? WHERE id IN ({placeholders})"
                params = [now_iso] + job_ids
                cur.execute(sql, params)
            else:
                sql = f"UPDATE jobs SET status = 'expired', updated_at = ? WHERE id IN ({placeholders})"
                params = [now_iso] + job_ids
                cur.execute(sql, params)

        # ----------------------------------------------------------------------
        # Tier 1: Explicit Closing Date Expiry
        # Closing dates strictly BEFORE today (< today_iso).
        # Today's jobs remain active until midnight passes.
        # ----------------------------------------------------------------------
        active_filter = "is_expired = 0" if has_is_expired else "status != 'expired'"
        cur.execute(
            f"""
            SELECT id, closing_date FROM jobs
            WHERE {active_filter}
              AND closing_date IS NOT NULL
              AND closing_date != ''
              AND closing_date < ?
            """,
            (today_iso,),
        )
        tier1_rows = cur.fetchall()
        tier1_ids = [r["id"] for r in tier1_rows]
        mark_jobs_expired(tier1_ids)
        closing_date_expired = len(tier1_ids)

        # ----------------------------------------------------------------------
        # Tier 2: Automated URL Verification for listings between 14 and 30 days old
        # Skips listings < 14 days old (listings > 30 days are handled by Tier 3 fallback).
        # ----------------------------------------------------------------------
        cur.execute(
            f"""
            SELECT id, url, clean_url, posted_age_days FROM jobs
            WHERE {active_filter}
              AND posted_age_days >= 14
              AND posted_age_days <= 30
            """
            if "clean_url" in cols
            else f"""
            SELECT id, url, posted_age_days FROM jobs
            WHERE {active_filter}
              AND posted_age_days >= 14
              AND posted_age_days <= 30
            """
        )
        tier2_candidates = cur.fetchall()
        tier2_expired_ids = []

        for row in tier2_candidates:
            target_url = (
                row["clean_url"]
                if "clean_url" in cols and row["clean_url"]
                else row["url"]
            )
            ver_res = verify_job_url(target_url, force=force_url_check)
            if ver_res.get("is_expired"):
                tier2_expired_ids.append(row["id"])

        mark_jobs_expired(tier2_expired_ids)
        url_check_expired = len(tier2_expired_ids)

        # ----------------------------------------------------------------------
        # Tier 3: 30-Day Hard Expiry Fallback
        # Unverified stale listings with posted_age_days > 30 (i.e. >= 31).
        # Listings at <= 30 days remain active.
        # ----------------------------------------------------------------------
        cur.execute(
            f"""
            SELECT id, posted_age_days FROM jobs
            WHERE {active_filter}
              AND posted_age_days > 30
            """
        )
        tier3_rows = cur.fetchall()
        tier3_ids = [r["id"] for r in tier3_rows]
        mark_jobs_expired(tier3_ids)
        fallback_30d_expired = len(tier3_ids)

        conn.commit()

        total_expired = closing_date_expired + url_check_expired + fallback_30d_expired
        jobs_evaluated = len(tier1_rows) + len(tier2_candidates) + len(tier3_rows)

        return {
            "status": "success",
            "total_expired": total_expired,
            "closing_date_expired": closing_date_expired,
            "url_check_expired": url_check_expired,
            "fallback_30d_expired": fallback_30d_expired,
            "jobs_evaluated": jobs_evaluated,
            "timestamp": now_iso,
        }

    finally:
        if close_conn_on_exit:
            conn.close()
