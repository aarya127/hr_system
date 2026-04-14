"""
Real-time job scraper.

Strategy per company (controlled by companies.COMPANIES[*]["scraper"])
----------------------------------------------------------------------
"eightfold"  : Playwright + network interception for Eightfold AI ATS
                (NVIDIA, Microsoft).
"apple"      : Playwright + network interception for Apple's custom ATS.
"amazon"     : Direct amazon.jobs public JSON API.
"playwright" : Generic Playwright browser scraper — captures internal XHR/fetch
                JSON for Workday ATS, Meta, Google, Tesla, and others.
"jobspy"     : Legacy fallback — python-jobspy via Google Jobs only.

All errors are caught and logged; a failed source never aborts others.
"""

import time
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import requests
from rich.console import Console

try:
    from jobspy import scrape_jobs as _scrape

    _JOBSPY_OK = True
except ImportError:  # pragma: no cover
    _JOBSPY_OK = False

console = Console(stderr=True)

# Seconds between consecutive scrape calls to the same job board.
_RATE_LIMIT_SLEEP = 2

_AMAZON_SEARCH_URL = "https://www.amazon.jobs/en/search.json"
_AMAZON_BASE_URL = "https://www.amazon.jobs"
# amazon.jobs returns dates like "March 24, 2026"
_AMAZON_DATE_FMT = "%B %d, %Y"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scrape_company_jobs(
    company: dict,
    hours_old: int = 168,
    results_wanted: int = 50,
) -> list[dict]:
    """
    Fetch open job postings for *company*.

    Parameters
    ----------
    company        : Company dict from src.companies.COMPANIES
    hours_old      : Only return postings from the last N hours
    results_wanted : Max results to fetch

    Returns
    -------
    List of normalised job dicts ready for database.insert_jobs()
    """
    strategy = company.get("scraper", "playwright")

    if strategy == "amazon":
        return _fetch_amazon(company, hours_old=hours_old, results_wanted=results_wanted)

    if strategy == "eightfold":
        from src.playwright_scraper import fetch_eightfold
        return fetch_eightfold(company["careers_url"], company, hours_old, results_wanted)

    if strategy == "apple":
        from src.playwright_scraper import fetch_apple
        return fetch_apple(company, hours_old, results_wanted)

    if strategy == "playwright":
        from src.playwright_scraper import fetch_generic
        cfg = company.get("scraper_config") or {}
        return fetch_generic(
            company["careers_url"], company, hours_old, results_wanted,
            intercept_pattern=cfg.get("intercept_pattern"),
        )

    # Legacy fallback: Google Jobs only
    if not _JOBSPY_OK:
        raise ImportError(
            "python-jobspy is required. Install with: pip install python-jobspy"
        )
    return _fetch_jobspy(company, hours_old=hours_old, results_wanted=results_wanted)


def scrape_all_companies(
    companies: list[dict],
    hours_old: int = 168,
    results_wanted: int = 50,
    on_progress=None,
) -> dict[str, list[dict]]:
    """
    Scrape all companies sequentially.

    Parameters
    ----------
    on_progress : optional callable(company_dict, jobs_found: int) called after
                  each company finishes.

    Returns
    -------
    Dict mapping company name → list of job dicts.
    """
    results: dict[str, list[dict]] = {}
    for company in companies:
        jobs = scrape_company_jobs(
            company, hours_old=hours_old, results_wanted=results_wanted
        )
        results[company["name"]] = jobs
        if on_progress:
            on_progress(company, len(jobs))
    return results


# ---------------------------------------------------------------------------
# Scraper implementations
# ---------------------------------------------------------------------------


def _fetch_amazon(company: dict, hours_old: int, results_wanted: int) -> list[dict]:
    """Fetch jobs from the public amazon.jobs JSON API."""
    cutoff = datetime.now() - timedelta(hours=hours_old)
    jobs: list[dict] = []
    offset = 0
    page_size = min(50, results_wanted)

    while len(jobs) < results_wanted:
        try:
            response = requests.get(
                _AMAZON_SEARCH_URL,
                params={
                    "base_query": "",
                    "loc_query": "United States",
                    "offset": offset,
                    "result_limit": page_size,
                    "sort": "recent",
                },
                headers={"User-Agent": "Mozilla/5.0 (compatible; job-tracker/1.0)"},
                timeout=20,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            console.print(f"[yellow]  amazon.jobs error: {exc}[/yellow]")
            break

        page = response.json().get("jobs", [])
        if not page:
            break  # no more results

        for raw in page:
            # Keep only US jobs; country_code is a 3-letter ISO code ("USA")
            cc = (raw.get("country_code") or "").upper()
            if cc and cc != "USA":
                continue

            posted_date = _parse_amazon_date(raw.get("posted_date", ""))

            # Results are sorted by recency; stop early once we pass the cutoff.
            if posted_date and datetime.combine(posted_date, datetime.min.time()) < cutoff:
                return jobs

            job_path = raw.get("job_path", "")
            job_url = f"{_AMAZON_BASE_URL}{job_path}" if job_path else ""
            if not job_url:
                continue

            jobs.append(
                {
                    "company_name": company["name"],
                    "company_rank": company["rank"],
                    "title": (raw.get("title") or "").strip(),
                    "location": (raw.get("location") or "").strip(),
                    "date_posted": posted_date,
                    "date_scraped": datetime.now(),
                    "job_type": (raw.get("job_schedule_type") or "").strip(),
                    "salary": None,  # amazon.jobs doesn't expose salary in the API
                    "is_remote": _amazon_is_remote(raw),
                    "source": "amazon_direct",
                    "job_url": job_url,
                }
            )
            if len(jobs) >= results_wanted:
                return jobs

        offset += len(page)
        time.sleep(_RATE_LIMIT_SLEEP)

    return jobs


def _fetch_jobspy(company: dict, hours_old: int, results_wanted: int) -> list[dict]:
    """Fallback: fetch jobs via python-jobspy using Google Jobs only."""
    df = _safe_scrape(
        site_name=["google"],
        search_term=f"{company['search_term']} jobs",
        location="United States",
        hours_old=hours_old,
        results_wanted=results_wanted,
    )
    if df is None or df.empty:
        return []
    df = _filter_by_company(df, company)
    if df.empty:
        return []
    return _to_job_list(df, company)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_scrape(**kwargs) -> Optional[pd.DataFrame]:
    """Call jobspy scrape_jobs, swallow exceptions and return None on failure."""
    try:
        return _scrape(verbose=0, **kwargs)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]  scrape warning: {exc}[/yellow]")
        return None


def _filter_by_company(df: pd.DataFrame, company: dict) -> pd.DataFrame:
    """Keep only rows whose 'company' field matches one of company['match_terms']."""
    if df.empty or "company" not in df.columns:
        return df

    match_terms: list[str] = company.get("match_terms", [company["search_term"].split()[0]])

    def _matches(value) -> bool:
        if not isinstance(value, str):
            return False
        v = value.lower()
        return any(t.lower() in v for t in match_terms)

    return df[df["company"].apply(_matches)]


def _to_job_list(df: pd.DataFrame, company: dict) -> list[dict]:
    """Convert a scraped DataFrame to our internal job dict format."""
    jobs: list[dict] = []
    now = datetime.now()

    for _, row in df.iterrows():
        # ── date_posted ───────────────────────────────────────────────────
        date_posted: Optional[date] = None
        raw_date = row.get("date_posted")
        if raw_date is not None and pd.notna(raw_date):
            if isinstance(raw_date, datetime):
                date_posted = raw_date.date()
            elif isinstance(raw_date, date):
                date_posted = raw_date
            else:
                try:
                    date_posted = pd.to_datetime(raw_date).date()
                except Exception:
                    date_posted = None

        # ── salary ───────────────────────────────────────────────────────
        salary: Optional[str] = None
        min_amt = row.get("min_amount")
        if min_amt is not None and pd.notna(min_amt):
            max_amt = row.get("max_amount")
            interval = row.get("interval") or "year"
            currency = row.get("currency") or "USD"
            try:
                if max_amt is not None and pd.notna(max_amt):
                    salary = f"{currency} {int(min_amt):,} – {int(max_amt):,} / {interval}"
                else:
                    salary = f"{currency} {int(min_amt):,} / {interval}"
            except (ValueError, TypeError):
                salary = None

        def _str(field: str) -> str:
            v = row.get(field)
            return str(v).strip() if v is not None and pd.notna(v) else ""

        jobs.append(
            {
                "company_name": company["name"],
                "company_rank": company["rank"],
                "title": _str("title"),
                "location": _str("location"),
                "date_posted": date_posted,
                "date_scraped": now,
                "job_type": _str("job_type"),
                "salary": salary,
                "is_remote": bool(row.get("is_remote", False)),
                "source": _str("site"),
                "job_url": _str("job_url"),
            }
        )

    return [j for j in jobs if j["job_url"]]  # discard entries with no URL


def _parse_amazon_date(raw: str) -> Optional[date]:
    """Parse an amazon.jobs date string like 'March 24, 2026' → datetime.date."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, _AMAZON_DATE_FMT).date()
    except ValueError:
        return None


def _amazon_is_remote(raw: dict) -> bool:
    """Detect remote flag from amazon.jobs job record."""
    location = (raw.get("location") or "").lower()
    title = (raw.get("title") or "").lower()
    return "remote" in location or "virtual" in location or "remote" in title
