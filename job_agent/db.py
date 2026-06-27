"""SQLite layer. One table: jobs."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    company TEXT,
    location TEXT,
    work_type TEXT,
    platform TEXT,
    url TEXT UNIQUE,
    description TEXT,
    fit_score INTEGER,
    fit_reason TEXT,
    cover_letter TEXT,
    status TEXT DEFAULT 'pending',
    applied_at TIMESTAMP,
    screenshot_path TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(fit_score);
"""


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    purge_non_us()


def purge_non_us() -> int:
    """Delete jobs whose location matches a non-US keyword. Returns deleted count."""
    try:
        from agent import NON_US_KEYWORDS, _is_non_us_location
    except Exception:
        return 0
    with get_conn() as conn:
        rows = conn.execute("SELECT id, location FROM jobs").fetchall()
        to_delete = [r["id"] for r in rows if _is_non_us_location(r["location"] or "")]
        if to_delete:
            conn.executemany("DELETE FROM jobs WHERE id = ?", [(i,) for i in to_delete])
    return len(to_delete)


def insert_job(job: dict) -> Optional[int]:
    """Insert if URL is new; return row id or None on duplicate."""
    with get_conn() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO jobs
                   (title, company, location, work_type, platform, url, description,
                    fit_score, fit_reason, cover_letter, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job.get("title"),
                    job.get("company"),
                    job.get("location"),
                    job.get("work_type"),
                    job.get("platform"),
                    job.get("url"),
                    job.get("description"),
                    job.get("fit_score"),
                    job.get("fit_reason"),
                    job.get("cover_letter"),
                    job.get("status", "pending"),
                ),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def url_exists(url: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone()
        return row is not None


def get_jobs(status: Optional[str] = None, min_score: int = 0) -> list[dict]:
    sql = "SELECT * FROM jobs WHERE fit_score >= ?"
    params: list = [min_score]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY fit_score DESC, created_at DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_job(job_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def update_status(
    job_id: int,
    status: str,
    screenshot_path: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    applied_at = datetime.utcnow().isoformat() if status == "applied" else None
    with get_conn() as conn:
        conn.execute(
            """UPDATE jobs
               SET status = ?,
                   applied_at = COALESCE(?, applied_at),
                   screenshot_path = COALESCE(?, screenshot_path),
                   error_message = COALESCE(?, error_message)
               WHERE id = ?""",
            (status, applied_at, screenshot_path, error_message, job_id),
        )


def stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        scored = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE fit_score >= ?", (70,)
        ).fetchone()[0]
        applied = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'applied'"
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'failed'"
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'pending'"
        ).fetchone()[0]
        needs_manual = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'needs_manual'"
        ).fetchone()[0]
    return {
        "total": total,
        "scored_above_threshold": scored,
        "applied": applied,
        "failed": failed,
        "pending": pending,
        "needs_manual": needs_manual,
    }
