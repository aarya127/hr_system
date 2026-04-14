"""
SQLite persistence layer for HR job tracking.

Schema
------
jobs       — deduplicated job postings (unique on job_url)
scrape_log — audit log of every scrape run
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Generator, Optional

# Database file lives in <repo_root>/data/jobs.db
_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "jobs.db",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name    TEXT    NOT NULL,
    company_rank    INTEGER,
    title           TEXT,
    location        TEXT,
    date_posted     DATE,
    date_scraped    DATETIME NOT NULL,
    job_type        TEXT,
    salary          TEXT,
    is_remote       INTEGER  DEFAULT 0,
    source          TEXT,
    job_url         TEXT     UNIQUE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs (company_name);
CREATE INDEX IF NOT EXISTS idx_jobs_posted  ON jobs (date_posted);
CREATE INDEX IF NOT EXISTS idx_jobs_scraped ON jobs (date_scraped);
CREATE INDEX IF NOT EXISTS idx_jobs_rank    ON jobs (company_rank);

CREATE TABLE IF NOT EXISTS scrape_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name   TEXT,
    scraped_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    jobs_found     INTEGER  DEFAULT 0,
    jobs_new       INTEGER  DEFAULT 0,
    status         TEXT     DEFAULT 'success',
    error_message  TEXT
);
"""


def init_db() -> None:
    """Create tables if they do not exist."""
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    with _conn() as conn:
        conn.executescript(_SCHEMA)


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def insert_jobs(jobs: list[dict]) -> tuple[int, int]:
    """
    Persist jobs list to the database.

    Returns
    -------
    (total_submitted, newly_inserted)
    """
    if not jobs:
        return 0, 0

    new_count = 0
    with _conn() as conn:
        for job in jobs:
            url = job.get("job_url", "").strip()
            if not url:
                continue  # skip entries without a URL

            date_posted_val = job.get("date_posted")
            if isinstance(date_posted_val, (date, datetime)):
                date_posted_val = date_posted_val.isoformat()

            date_scraped_val = job.get("date_scraped", datetime.now())
            if isinstance(date_scraped_val, datetime):
                date_scraped_val = date_scraped_val.isoformat()

            conn.execute(
                """
                INSERT OR IGNORE INTO jobs
                    (company_name, company_rank, title, location,
                     date_posted, date_scraped, job_type, salary,
                     is_remote, source, job_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.get("company_name"),
                    job.get("company_rank"),
                    job.get("title"),
                    job.get("location"),
                    date_posted_val,
                    date_scraped_val,
                    job.get("job_type"),
                    job.get("salary"),
                    1 if job.get("is_remote") else 0,
                    job.get("source"),
                    url,
                ),
            )
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                new_count += 1

    return len(jobs), new_count


def log_scrape(
    company_name: str,
    jobs_found: int,
    jobs_new: int,
    status: str = "success",
    error: Optional[str] = None,
) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO scrape_log
                (company_name, scraped_at, jobs_found, jobs_new, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                company_name,
                datetime.now().isoformat(),
                jobs_found,
                jobs_new,
                status,
                error,
            ),
        )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_jobs(
    since: Optional[date] = None,
    until: Optional[date] = None,
    company: Optional[str] = None,
    limit: int = 500,
) -> list[dict]:
    """Return jobs filtered by posting date range and/or company."""
    conditions: list[str] = []
    params: list = []

    if since:
        conditions.append("date_posted >= ?")
        params.append(since.isoformat())
    if until:
        conditions.append("date_posted <= ?")
        params.append(until.isoformat())
    if company:
        conditions.append("LOWER(company_name) LIKE ?")
        params.append(f"%{company.lower()}%")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM jobs
            {where}
            ORDER BY date_posted DESC, date_scraped DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_new_jobs_since(
    since: date,
    company: Optional[str] = None,
) -> list[dict]:
    """
    Return jobs whose posting date (or scrape date when posting date is unknown)
    is >= since.
    """
    conditions = [
        "(date_posted >= ? OR (date_posted IS NULL AND DATE(date_scraped) >= ?))"
    ]
    params: list = [since.isoformat(), since.isoformat()]

    if company:
        conditions.append("LOWER(company_name) LIKE ?")
        params.append(f"%{company.lower()}%")

    where = "WHERE " + " AND ".join(conditions)

    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM jobs
            {where}
            ORDER BY company_rank ASC, date_posted DESC
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> list[dict]:
    """Aggregate job counts per company for the stats dashboard."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT
                company_rank,
                company_name,
                COUNT(*)                                                AS total_jobs,
                COUNT(CASE WHEN date_posted >= DATE('now','-1 day')  THEN 1 END) AS last_24h,
                COUNT(CASE WHEN date_posted >= DATE('now','-7 days') THEN 1 END) AS last_7d,
                COUNT(CASE WHEN date_posted >= DATE('now','-30 days') THEN 1 END) AS last_30d,
                MAX(date_posted)                                        AS newest_posting
            FROM jobs
            GROUP BY company_name
            ORDER BY company_rank
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_scrape_history(limit: int = 50) -> list[dict]:
    """Return recent scrape log entries."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM scrape_log
            ORDER BY scraped_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
