"""
Playwright-based scrapers for company career websites.

All scrapers work by launching a headless Chromium browser, navigating to the
company's real careers page, and intercepting the JSON API responses the page
makes internally.  This bypasses the CORS/auth restrictions that block direct
external REST API access, because the browser loads cookies and origin headers
exactly as a real user's session would.

Scraper type  Used for
-----------   --------
eightfold     NVIDIA, Microsoft (both use the Eightfold AI ATS platform)
apple         Apple Jobs (jobs.apple.com)
generic       Everything else — intercepts any JSON response and heuristically
              finds job records in it (handles Workday, custom SPAs, etc.)

Setup (one-time):
    playwright install chromium
"""

import asyncio
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from rich.console import Console

console = Console(stderr=True)

# Keys that hint a dict is a job record
_JOB_KEYS = frozenset(
    {
        "title", "jobtitle", "positiontitle", "requisitiontitle",
        "date_posted", "postingdate", "posteddate", "dateposted",
        "positionid", "requisitionid", "jobid", "externalJobCode",
    }
)


def _require_playwright() -> None:
    try:
        import playwright  # noqa: F401
    except ImportError:
        raise ImportError(
            "playwright is required for career site scraping.\n"
            "Run:  playwright install chromium"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Eightfold AI  (NVIDIA + Microsoft)
# ─────────────────────────────────────────────────────────────────────────────

async def _eightfold_async(
    page_url: str,
    company: dict,
    hours_old: int,
    results_wanted: int,
) -> list[dict]:
    from playwright.async_api import async_playwright

    cutoff = datetime.now() - timedelta(hours=hours_old)
    raw_positions: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await ctx.new_page()

        async def on_resp(response):
            if "api/pcsx/search" in response.url and response.status == 200:
                try:
                    data = await response.json()
                    page_positions = (data.get("data") or {}).get("positions", [])
                    raw_positions.extend(page_positions)
                except Exception:
                    pass

        page.on("response", on_resp)
        try:
            await page.goto(page_url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(5_000)
        except Exception as exc:
            console.print(f"[yellow]  Eightfold ({company['name']}): {exc}[/yellow]")

        await ctx.close()
        await browser.close()

    # Base URL for constructing absolute job URLs (strip at "/careers")
    domain = page_url.split("/careers")[0]  # e.g. https://jobs.nvidia.com
    now = datetime.now()
    jobs: list[dict] = []

    for pos in raw_positions:
        posted_date = _parse_eightfold_date(pos)
        if posted_date and datetime.combine(posted_date, datetime.min.time()) < cutoff:
            continue

        # locations is a flat list of strings e.g. ['US, CA, Santa Clara']
        locs = pos.get("locations") or pos.get("location") or []
        if isinstance(locs, list):
            location = "; ".join(str(loc) for loc in locs if loc)
        else:
            location = str(locs)

        pos_url = pos.get("positionUrl") or ""
        if pos_url.startswith("/"):
            job_url = domain + pos_url
        else:
            job_url = pos_url or (f"{domain}/careers/job/{pos['id']}" if pos.get("id") else "")
        if not job_url:
            continue

        jobs.append(
            {
                "company_name": company["name"],
                "company_rank": company["rank"],
                "title": (pos.get("name") or pos.get("title") or "").strip(),
                "location": location,
                "date_posted": posted_date,
                "date_scraped": now,
                "job_type": (pos.get("type") or "").strip(),
                "salary": None,
                "is_remote": "remote" in location.lower(),
                "source": "careers_direct",
                "job_url": job_url,
            }
        )
        if len(jobs) >= results_wanted:
            break

    return jobs


def _parse_eightfold_date(pos: dict) -> Optional[date]:
    """Parse posting date from 'postedTs' (Unix seconds) in pcsx/search response."""
    ts = pos.get("postedTs") or pos.get("t") or pos.get("timestamp")
    if not ts:
        return None
    try:
        t = float(ts)
        return datetime.fromtimestamp(t / 1000 if t > 1e10 else t).date()
    except (ValueError, OSError, OverflowError):
        return None


def fetch_eightfold(
    page_url: str, company: dict, hours_old: int, results_wanted: int
) -> list[dict]:
    _require_playwright()
    return asyncio.run(_eightfold_async(page_url, company, hours_old, results_wanted))


# ─────────────────────────────────────────────────────────────────────────────
# Apple Jobs  (jobs.apple.com)
# Uses server-side rendering: the search results are embedded in the HTML as
# window.__staticRouterHydrationData, so no browser is needed.
# ─────────────────────────────────────────────────────────────────────────────

def fetch_apple(company: dict, hours_old: int, results_wanted: int) -> list[dict]:
    """Fetch Apple jobs by parsing SSR-rendered HTML pages (no Playwright needed)."""
    import json as _json
    import requests as _requests

    BASE = "https://jobs.apple.com/en-us/search"
    S = _requests.Session()
    S.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })

    cutoff = datetime.now() - timedelta(hours=hours_old)
    now = datetime.now()
    jobs: list[dict] = []
    page_num = 1
    stop = False

    while not stop and len(jobs) < results_wanted:
        url = f"{BASE}?location=united-states-USA&page={page_num}"
        try:
            r = S.get(url, timeout=20)
        except Exception as exc:
            console.print(f"[yellow]  Apple Jobs page {page_num}: {exc}[/yellow]")
            break
        if r.status_code != 200:
            console.print(f"[yellow]  Apple Jobs: HTTP {r.status_code}[/yellow]")
            break

        # Extract the JSON embedded as window.__staticRouterHydrationData
        m = re.search(
            r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\(("(?:[^"\\]|\\.)*")\)',
            r.text,
        )
        if not m:
            console.print("[yellow]  Apple Jobs: hydration data not found in page[/yellow]")
            break
        try:
            hydration = _json.loads(_json.loads(m.group(1)))
        except Exception as exc:
            console.print(f"[yellow]  Apple Jobs: JSON parse error: {exc}[/yellow]")
            break

        results = (
            (hydration.get("loaderData") or {})
            .get("search", {})
            .get("searchResults", [])
        )
        if not results:
            break

        for item in results:
            raw_date = item.get("postDateInGMT") or item.get("postingDate") or ""
            posted_date = _parse_date_multi(raw_date)
            if posted_date and datetime.combine(posted_date, datetime.min.time()) < cutoff:
                stop = True
                break  # results sorted newest-first; everything after is older

            pos_id = item.get("positionId") or ""
            title = (item.get("postingTitle") or "").strip()
            if not pos_id or not title:
                continue

            locs = item.get("locations") or []
            location = ", ".join(
                loc.get("name", "")
                for loc in locs
                if isinstance(loc, dict) and loc.get("name")
            )
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:50].strip("-")
            job_url = f"https://jobs.apple.com/en-us/details/{pos_id}/{slug}"

            jobs.append({
                "company_name": company["name"],
                "company_rank": company["rank"],
                "title": title,
                "location": location,
                "date_posted": posted_date,
                "date_scraped": now,
                "job_type": "",
                "salary": None,
                "is_remote": "remote" in location.lower(),
                "source": "careers_direct",
                "job_url": job_url,
            })
            if len(jobs) >= results_wanted:
                stop = True
                break

        page_num += 1

    return jobs


# ─────────────────────────────────────────────────────────────────────────────
# Generic JSON-intercepting scraper
# Works for Workday, Google, Meta, Tesla, Walmart, etc.
# ─────────────────────────────────────────────────────────────────────────────

async def _generic_async(
    page_url: str,
    company: dict,
    hours_old: int,
    results_wanted: int,
    intercept_pattern: Optional[str],
) -> list[dict]:
    from playwright.async_api import async_playwright

    captured: list[tuple[str, Any]] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await ctx.new_page()

        async def on_resp(response):
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            if intercept_pattern and intercept_pattern not in response.url:
                return
            try:
                data = await response.json()
                captured.append((response.url, data))
            except Exception:
                pass

        page.on("response", on_resp)
        try:
            await page.goto(page_url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3_000)
            # Dismiss cookie-consent dialogs (e.g., Google careers)
            for _sel in (
                'button:has-text("Agree")',
                'button:has-text("Accept all")',
                'button:has-text("I agree")',
                'button:has-text("Accept")',
            ):
                try:
                    btn = page.locator(_sel)
                    if await btn.count() > 0:
                        await btn.first.click(timeout=3_000)
                        await page.wait_for_timeout(2_000)
                        break
                except Exception:
                    pass
            await page.wait_for_timeout(5_000)  # wait for JS to make API calls
            # Scroll to trigger any lazy-loaded content
            await page.evaluate("window.scrollTo(0, 400)")
            await page.wait_for_timeout(3_000)
        except Exception as exc:
            console.print(
                f"[yellow]  Playwright ({company['name']}): {exc}[/yellow]"
            )

        await ctx.close()
        await browser.close()

    return _parse_generic(captured, company, hours_old, results_wanted)


def _parse_generic(
    captured: list[tuple[str, Any]],
    company: dict,
    hours_old: int,
    results_wanted: int,
) -> list[dict]:
    """Find job records inside any captured JSON response, heuristically."""
    cutoff = datetime.now() - timedelta(hours=hours_old)
    now = datetime.now()

    # Pick the response with the most job-like records
    best: list[dict] = []
    for _url, data in captured:
        records = _find_job_records(data)
        if len(records) > len(best):
            best = records

    if not best:
        console.print(
            f"[yellow]  No job data found for {company['name']} "
            f"(intercepted {len(captured)} JSON responses)[/yellow]"
        )
        return []

    base_domain = "/".join((company.get("careers_url") or "").split("/")[:3])
    jobs: list[dict] = []

    for rec in best:
        title = _field(rec, ["title", "jobTitle", "positionTitle", "name",
                             "RequisitionTitle", "JobTitle", "job_title"])
        location = _field(rec, ["location", "locationDescription", "city",
                                "primaryLocation", "Location__c", "normalizedCountryName",
                                "locationName", "locations"])
        raw_date = _field(rec, ["datePosted", "postingDate", "postedDate",
                                "date_posted", "CreatedDate", "posted_date", "publishedDate"])
        job_url = _field(rec, ["url", "jobUrl", "directDataPageUrl", "externalApplyUrl",
                               "detailUrl", "canonicalPositionUrl", "applyUrl", "link"])

        if not title:
            continue

        posted_date = _parse_date_multi(raw_date or "")
        if posted_date and datetime.combine(posted_date, datetime.min.time()) < cutoff:
            continue

        # Resolve relative URLs
        if job_url and not job_url.startswith("http") and base_domain:
            from urllib.parse import urljoin
            job_url = urljoin(base_domain + "/", job_url.lstrip("/"))

        if not job_url:
            continue

        loc_str = str(location or "").strip()
        jobs.append(
            {
                "company_name": company["name"],
                "company_rank": company["rank"],
                "title": str(title).strip(),
                "location": loc_str,
                "date_posted": posted_date,
                "date_scraped": now,
                "job_type": "",
                "salary": None,
                "is_remote": "remote" in loc_str.lower(),
                "source": "careers_direct",
                "job_url": job_url,
            }
        )
        if len(jobs) >= results_wanted:
            break

    return jobs


def _find_job_records(data: Any, depth: int = 0) -> list[dict]:
    """Recursively find a list of dicts that looks like job postings."""
    if depth > 5:
        return []
    if isinstance(data, list) and len(data) >= 2 and all(isinstance(x, dict) for x in data[:3]):
        sample_keys = {k.lower() for d in data[:3] for k in d}
        if sample_keys & _JOB_KEYS:
            return data
    if isinstance(data, dict):
        best: list[dict] = []
        for v in data.values():
            found = _find_job_records(v, depth + 1)
            if len(found) > len(best):
                best = found
        return best
    return []


def _field(d: dict, keys: list[str]) -> Optional[str]:
    """Try multiple key names and return the first non-empty string value."""
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list) and v:
            first = v[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
            if isinstance(first, dict):
                inner = first.get("name") or first.get("label") or first.get("value")
                if inner:
                    return str(inner).strip()
        if isinstance(v, dict):
            inner = v.get("name") or v.get("label") or v.get("value")
            if inner:
                return str(inner).strip()
    return None


def _parse_date_multi(raw: str) -> Optional[date]:
    """Try several common date formats."""
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(raw[:26].strip(), fmt).date()
        except ValueError:
            continue
    return None


def fetch_generic(
    page_url: str,
    company: dict,
    hours_old: int,
    results_wanted: int,
    intercept_pattern: Optional[str] = None,
) -> list[dict]:
    _require_playwright()
    return asyncio.run(
        _generic_async(page_url, company, hours_old, results_wanted, intercept_pattern)
    )
