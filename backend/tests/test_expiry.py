"""Unit test suite for Verifier and Hybrid Expiry Lifecycle Worker."""

from __future__ import annotations

import datetime
import sqlite3

from job_dashboard_light.services.expiry import run_hybrid_expiry_check
from job_dashboard_light.services.verifier import (
    clear_verify_cache,
    verify_job_url,
    verify_job_urls,
)


def test_verify_job_url():
    clear_verify_cache()
    # Invalid URLs
    assert verify_job_url("")["is_expired"] is True
    assert verify_job_url("ftp://seek.com")["is_expired"] is True

    # Simulated URLs
    res_404 = verify_job_url("http://seek.com/404")
    assert res_404["is_expired"] is True
    assert res_404["status_code"] == 404

    res_live = verify_job_url("http://seek.com/live")
    assert res_live["is_expired"] is False
    assert res_live["status_code"] == 200

    res_banner = verify_job_url("http://seek.com/expired-ad")
    assert res_banner["is_expired"] is True


def test_verify_job_urls_batch():
    urls = ["http://seek.com/live", "http://seek.com/404"]
    batch = verify_job_urls(urls)
    assert len(batch) == 2
    assert batch["http://seek.com/live"]["is_expired"] is False
    assert batch["http://seek.com/404"]["is_expired"] is True


def test_hybrid_expiry_lifecycle():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            clean_url TEXT,
            closing_date TEXT,
            posted_age_days INTEGER,
            status TEXT DEFAULT 'active',
            is_expired INTEGER DEFAULT 0,
            updated_at TEXT
        );
    """)

    today = datetime.date(2026, 9, 26)
    yesterday = datetime.date(2026, 9, 25).isoformat()
    tomorrow = datetime.date(2026, 9, 27).isoformat()
    today_iso = today.isoformat()

    cur.executemany(
        """
        INSERT INTO jobs (id, title, url, clean_url, closing_date, posted_age_days, status, is_expired)
        VALUES (?, ?, ?, ?, ?, ?, 'active', 0)
        """,
        [
            ("j1", "Closed", "http://t/1", "http://t/1", yesterday, 5),
            ("j2", "Closing Today", "http://t/2", "http://t/2", today_iso, 5),
            ("j3", "Future", "http://t/3", "http://t/3", tomorrow, 5),
            (
                "j4",
                "Dead URL 16d",
                "http://seek.com/404",
                "http://seek.com/404",
                None,
                16,
            ),
            (
                "j5",
                "Live 16d",
                "http://seek.com/live",
                "http://seek.com/live",
                None,
                16,
            ),
            (
                "j6",
                "Recent 404 (5d)",
                "http://seek.com/404",
                "http://seek.com/404",
                None,
                5,
            ),
            ("j7", "Stale 35d", "http://t/7", "http://t/7", None, 35),
            ("j8", "Day 30", "http://t/8", "http://t/8", None, 30),
        ],
    )
    conn.commit()

    res = run_hybrid_expiry_check(conn, current_date=today)

    assert res["status"] == "success"
    assert res["closing_date_expired"] == 1  # j1
    assert res["url_check_expired"] == 1  # j4
    assert res["fallback_30d_expired"] == 1  # j7
    assert res["total_expired"] == 3

    def check(jid):
        return cur.execute(
            "SELECT status, is_expired FROM jobs WHERE id = ?", (jid,)
        ).fetchone()

    assert check("j1")["is_expired"] == 1
    assert check("j2")["is_expired"] == 0
    assert check("j3")["is_expired"] == 0
    assert check("j4")["is_expired"] == 1
    assert check("j5")["is_expired"] == 0
    assert check("j6")["is_expired"] == 0
    assert check("j7")["is_expired"] == 1
    assert check("j8")["is_expired"] == 0
