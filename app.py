import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional

from flask import Flask, render_template, request

from extract_jobs import DEFAULT_URLS, extract_jobs

app = Flask(__name__)
CACHE_TTL = timedelta(minutes=5)
_cache: Dict[str, Any] = {
    "jobs": [],
    "errors": [],
    "updated_at": None,
    "urls": DEFAULT_URLS,
}
_cache_lock = threading.Lock()
_cache_loading = False


def parse_posted_date(posted: str) -> Optional[datetime]:
    if not posted:
        return None

    text = posted.strip()
    text = text.replace("Date Posted:", "").replace("Posted:", "").strip()
    text = text.replace("Posted", "").replace("Date Posted", "").strip()

    now = datetime.now()
    relative_match = None
    if "today" in text.lower():
        return now
    if "yesterday" in text.lower():
        return now - timedelta(days=1)

    # Handle "a day ago", "an hour ago", "a month ago" etc. by substituting "1"
    text = re.sub(r'\ba\b(?=\s+(second|minute|hour|day|week|month|year))', '1', text, flags=re.IGNORECASE)
    text = re.sub(r'\ban\b(?=\s+(second|minute|hour|day|week|month|year))', '1', text, flags=re.IGNORECASE)

    relative_match = None
    for pattern in [
        (r"(\d+)\s+days?\s+ago", lambda value: now - timedelta(days=int(value))),
        (r"(\d+)\s+hours?\s+ago", lambda value: now - timedelta(hours=int(value))),
        (r"(\d+)\s+hrs?\s+ago", lambda value: now - timedelta(hours=int(value))),
        (r"(\d+)\s+minutes?\s+ago", lambda value: now - timedelta(minutes=int(value))),
        (r"(\d+)\s+weeks?\s+ago", lambda value: now - timedelta(weeks=int(value))),
        (r"(\d+)\s+months?\s+ago", lambda value: now - timedelta(days=int(value) * 30)),
        (r"(\d+)\s+years?\s+ago", lambda value: now - timedelta(days=int(value) * 365)),
    ]:
        try:
            match = re.search(pattern[0], text, re.IGNORECASE)
            if match:
                return pattern[1](match.group(1))
        except Exception:
            continue

    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y"]:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def source_name(url: str) -> str:
    hostname = urlparse(url).hostname or "unknown"
    return hostname.replace("www.", "")


def fetch_jobs(urls: List[str]) -> Dict[str, Any]:
    jobs: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for url in urls:
        try:
            data = extract_jobs(url)
            source = source_name(url)
            for job in data.get("jobs", []):
                posted_text = job.get("posted", "") or ""
                job_date = parse_posted_date(posted_text)
                jobs.append(
                    {
                        "title": job.get("title", "(no title)"),
                        "location": job.get("location", ""),
                        "posted": posted_text,
                        "url": job.get("url", ""),
                        "source": source,
                        "posted_date": job_date,
                        "source_url": url,
                    }
                )
        except Exception as exc:
            errors.append({"url": url, "message": str(exc)})

    jobs.sort(key=lambda item: (item["posted_date"] or datetime.min), reverse=True)
    return {"jobs": jobs, "errors": errors}


def _fetch_one(url: str) -> tuple[str, list, str | None]:
    """Fetch jobs for a single URL. Returns (url, new_jobs, error_message)."""
    source = source_name(url)
    try:
        data = extract_jobs(url)
        new_jobs = []
        for job in data.get("jobs", []):
            posted_text = job.get("posted", "") or ""
            job_date = parse_posted_date(posted_text)
            posted_normalized = job_date.strftime("%Y-%m-%d") if job_date else posted_text
            new_jobs.append({
                "title": job.get("title", "(no title)"),
                "location": job.get("location", ""),
                "posted": posted_normalized,
                "url": job.get("url", ""),
                "source": source,
                "posted_date": job_date,
                "source_url": url,
            })
        return url, new_jobs, None
    except Exception as exc:
        return url, [], str(exc)


def _run_fetch() -> None:
    global _cache_loading
    try:
        urls = list(_cache["urls"])
        all_new_jobs: List[Dict[str, Any]] = []
        all_errors: List[Dict[str, str]] = []

        # Run all scrapers concurrently; old cached jobs stay visible until done
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch_one, url): url for url in urls}
            for future in as_completed(futures):
                url, new_jobs, error = future.result()
                if error:
                    all_errors.append({"url": url, "message": error})
                else:
                    all_new_jobs.extend(new_jobs)

        all_new_jobs.sort(
            key=lambda item: (item["posted_date"] or datetime.min),
            reverse=True,
        )

        # Atomic swap — replaces stale data all at once
        with _cache_lock:
            _cache["jobs"] = all_new_jobs
            _cache["errors"] = all_errors
            _cache["updated_at"] = datetime.now()
    finally:
        with _cache_lock:
            _cache_loading = False


def start_fetch_jobs() -> None:
    global _cache_loading
    with _cache_lock:
        if _cache_loading:
            return
        _cache_loading = True

    thread = threading.Thread(target=_run_fetch, daemon=True)
    thread.start()


@app.route("/")
def index() -> str:
    refresh = request.args.get("refresh", "0") == "1"
    now = datetime.now()
    with _cache_lock:
        updated_at = _cache["updated_at"]
        expired = not updated_at or now - updated_at > CACHE_TTL
        loading = _cache_loading
        jobs = list(_cache["jobs"])
        errors = list(_cache["errors"])
        urls = list(_cache["urls"])

    triggered_fetch = False
    if refresh or not jobs or expired:
        start_fetch_jobs()
        triggered_fetch = True

    return render_template(
        "index.html",
        jobs=jobs,
        errors=errors,
        updated_at=updated_at,
        urls=urls,
        cache_ttl_minutes=int(CACHE_TTL.total_seconds() / 60),
        loading=_cache_loading or triggered_fetch,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5003, debug=True)
