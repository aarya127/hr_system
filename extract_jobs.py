import argparse
import html
import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

DEFAULT_URLS = [
    "https://careers.micron.com/careers?start=0&pid=41210446&sort_by=timestamp",
    "https://careers.mckesson.com/en/search-jobs?acm=ALL&alrpm=ALL&ascf=[%7B%22key%22:%22custom_fields.JobFunction%22,%22value%22:%22Information+Technology%22%7D]",
    "https://cmegroup.wd1.myworkdayjobs.com/en-US/cme_careers?locations=7a3301e6ea5710f69c0df31964e169fd&locations=7a3301e6ea5710f69c0f7e3613466b20&locations=7a3301e6ea5710f69c0ece8a424a6ab7&locations=7a3301e6ea5710f69c0ea186a0046a8f",
    "https://vrtx.wd501.myworkdayjobs.com/vertex_careers",
    "https://www.capitalonecareers.com/search-jobs/United%20States/234/2/6252001/39x76/-98x5/50/2",
    "https://careers.progressive.com/search/jobs?sort_by=cfm16,desc",
    "https://job-boards.greenhouse.io/ibkr?departments%5B%5D=4027655002&departments%5B%5D=4027657002",
    "https://jobs.intuit.com/search-jobs",
    "https://jobs.bms.com/careers?start=0&pid=137479694501&sort_by=timestamp",
    "https://prologis.wd5.myworkdayjobs.com/Prologis_External_Careers",
    "https://careers.stryker.com/jobs?filter%5Bcategory%5D%5B0%5D=Data%20Analysis&filter%5Bcategory%5D%5B1%5D=Engineering&sort_by=update_date&page_number=1&location_name=united%20states&location_type=1",
    "https://jobs.dell.com/en/search-jobs",
    "https://corningjobs.corning.com/search-jobs?collections=6097279-2023-272212-1&filters=6147437-1%2C6147440-1%2C6147442-1",
    "https://www.applovin.com/en/careers#job-board",
    "https://careers.spglobal.com/jobs?page=1&categories=Information%20Technology&sortBy=posted_date&descending=true&limit=100",
    "https://jobs.paloaltonetworks.com/en/search-jobs",
    "https://careers.qualcomm.com/careers",
    "https://www.lockheedmartinjobs.com/search-jobs",
    # New sources
    "https://careers.honeywell.com/en/sites/Honeywell/jobs?lastSelectedFacet=CATEGORIES&mode=location&selectedCategoriesFacet=300000017425610%3B300000017425634&selectedOrganizationsFacet=300000011497075&sortBy=POSTING_DATES_DESC",
    "https://www.uber.com/ca/en/careers/list/?department=Data%20Science&department=Engineering",
    "https://blackrock.wd1.myworkdayjobs.com/BlackRock_Professional?q=machine%20learning",
    "https://analogdevices.wd1.myworkdayjobs.com/External?q=machine%20learning",
]


def parse_int(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"(\d[\d,]*)", text)
    return int(match.group(1).replace(",", "")) if match else None


def request_html(url: str) -> str:
    try:
        import requests
    except ImportError as exc:
        raise ImportError(
            "Requests is required for McKesson scraping. "
            "Install it with: pip install requests"
        ) from exc

    response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def extract_mckesson_jobs(url: str) -> dict[str, Any]:
    html_text = request_html(url)
    jobs = []
    # McKesson (Phenom/TalentBrew) structure:
    # <a class="search-results__job-title-link" href="...">Title</a>
    # <span class="search-results__job-location">Location</span>
    # <span class="search-results__job-date-posted">04/13/2026</span>
    for match in re.finditer(
        r'<a[^>]+class="search-results__job-title-link"[^>]+href="(?P<href>[^"]+)"[^>]*>'
        r'(?P<title>[^<]+)</a>\s*'
        r'<span[^>]+class="search-results__job-location"[^>]*>(?P<location>[^<]+)</span>'
        r'(?:\s*<span[^>]+class="search-results__job-date-posted"[^>]*>(?P<posted>[^<]+)</span>)?',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        title = html.unescape(match.group("title")).strip()
        location = html.unescape(match.group("location")).strip()
        href = match.group("href").strip()
        posted = html.unescape(match.group("posted") or "").strip()
        full_url = urljoin(url, href)
        jobs.append({"title": title, "location": location, "posted": posted, "url": full_url})
    return {"total_jobs": len(jobs), "jobs": jobs}

def extract_spglobal_jobs(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            'Playwright is required for S&P Global scraping. '
            'Install it with: pip install playwright && playwright install chromium'
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=REQUEST_HEADERS['User-Agent'],
            extra_http_headers={'Accept-Language': REQUEST_HEADERS['Accept-Language']},
        )
        page = context.new_page()
        page.goto(url, wait_until='domcontentloaded', timeout=120000)
        page.wait_for_timeout(8000)
        page.wait_for_selector('a.job-title-link', timeout=30000)

        jobs = []
        locator = page.locator('mat-expansion-panel')
        for i in range(locator.count()):
            item = locator.nth(i)
            title = item.locator('a.job-title-link').inner_text().strip()
            href = item.locator('a.job-title-link').get_attribute('href') or ''
            apply_href = item.locator('a.apply-button').get_attribute('href') or ''
            full_url = apply_href if apply_href.startswith('http') else urljoin(url, apply_href or href)

            location = ''
            location_locator = item.locator('span.location.label-value')
            if location_locator.count() > 0:
                location = location_locator.first.inner_text().strip()
                location = re.sub(r'\s+', ' ', location)

            posted = ''
            posted_locator = item.locator('span.label-value.posted_date')
            if posted_locator.count() > 0:
                posted = posted_locator.first.inner_text().strip()

            jobs.append(
                {
                    'title': title,
                    'location': location,
                    'posted': posted,
                    'url': full_url,
                }
            )

        total_jobs = locator.count()
        browser.close()

    return {'total_jobs': total_jobs, 'jobs': jobs}


def extract_paloalto_jobs(url: str) -> dict[str, Any]:
    html_text = request_html(url)
    jobs = []

    for match in re.finditer(
        r'<a[^>]+class=["\']section29__search-results-link["\'][^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<body>.*?)</a>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        href = match.group('href').strip()
        body = match.group('body')

        title_match = re.search(r'<h2[^>]*>(?P<title>[^<]+)</h2>', body, re.IGNORECASE)
        location_match = re.search(
            r'<span[^>]+class=["\'][^"\']*section29__result-location[^"\']*["\'][^>]*>(?P<location>[^<]+)</span>',
            body,
            re.IGNORECASE,
        )
        posted_match = re.search(r'Posted\s+([^<\n]+)', body, re.IGNORECASE)

        title = html.unescape(title_match.group('title').strip()) if title_match else '(no title)'
        location = html.unescape(location_match.group('location').strip()) if location_match else ''
        posted = posted_match.group(0).strip() if posted_match else ''

        jobs.append(
            {
                'title': title,
                'location': re.sub(r'\s+', ' ', location).strip(),
                'posted': posted,
                'url': urljoin(url, href),
            }
        )

    return {'total_jobs': len(jobs), 'jobs': jobs}


def extract_qualcomm_jobs(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            'Playwright is required for Qualcomm scraping. '
            'Install it with: pip install playwright && playwright install chromium'
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=REQUEST_HEADERS['User-Agent'],
            extra_http_headers={'Accept-Language': REQUEST_HEADERS['Accept-Language']},
        )
        page = context.new_page()
        page.goto(url, wait_until='domcontentloaded', timeout=120000)
        page.wait_for_timeout(10000)
        page.wait_for_selector('a[href^="/careers/job/"]', timeout=30000)

        jobs = []
        locator = page.locator('a[href^="/careers/job/"]')
        for i in range(locator.count()):
            item = locator.nth(i)
            href = item.get_attribute('href') or ''
            text = item.inner_text().strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            title = lines[0] if lines else '(no title)'
            location = lines[1] if len(lines) > 1 else ''
            posted = ''
            if len(lines) > 2 and lines[-1].lower().startswith('posted'):
                posted = lines[-1]

            jobs.append(
                {
                    'title': html.unescape(title),
                    'location': re.sub(r'\s+', ' ', html.unescape(location)).strip(),
                    'posted': posted,
                    'url': urljoin(url, href),
                }
            )

        total_jobs = locator.count()
        browser.close()

    return {'total_jobs': total_jobs, 'jobs': jobs}


def extract_lockheed_jobs(url: str) -> dict[str, Any]:
    html_text = request_html(url)
    jobs = {}

    for match in re.finditer(
        r"<a[^>]+href=[\"'](?P<href>/job/[^\"']+)[\"'][^>]*data-job-id=[\"'](?P<jobid>[^\"']+)[\"'][^>]*>(?P<body>.*?)</a>",
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        href = match.group('href').strip()
        body = match.group('body')
        title = ''
        location = ''
        posted = ''
        full_url = urljoin(url, href)

        title_match = re.search(
            r"<span[^>]+class=[\"'][^\"']*job-title[^\"']*[\"'][^>]*>(?P<title>[^<]+)</span>",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        if title_match:
            title = html.unescape(title_match.group('title').strip())
        else:
            title = re.sub(r'<[^>]+>', '', body).strip()
            title = html.unescape(title) or '(no title)'

        location_match = re.search(
            r"<span[^>]+class=[\"'][^\"']*job-location[^\"']*[\"'][^>]*>(?P<location>[^<]+)</span>",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        if location_match:
            location = html.unescape(location_match.group('location').strip())

        posted_match = re.search(
            r"<span[^>]+class=[\"'][^\"']*job-date-posted[^\"']*[\"'][^>]*>(?P<posted>[^<]+)</span>",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        if posted_match:
            posted = html.unescape(posted_match.group('posted').strip())

        if not location or not posted:
            try:
                job_page = request_html(full_url)
                if not location:
                    location_match = re.search(
                        r"<p[^>]+id=[\"']collapsible-locations[\"'][^>]*>(?P<location>[^<]+)</p>",
                        job_page,
                        re.IGNORECASE | re.DOTALL,
                    )
                    if not location_match:
                        location_match = re.search(
                            r"<div[^>]+class=[\"'][^\"']*locations-toggle-wrapper[^\"']*[\"'][^>]*>.*?<p[^>]+class=[\"'][^\"']*locations-collapsed[^\"']*[\"'][^>]*>(?P<location>[^<]+)</p>",
                            job_page,
                            re.IGNORECASE | re.DOTALL,
                        )
                    if location_match:
                        location = html.unescape(location_match.group('location').strip())

                if not posted:
                    posted_match = re.search(r'"datePosted"\s*:\s*"(?P<posted>[^"]+)"', job_page)
                    if not posted_match:
                        posted_match = re.search(r'Posted":"(?P<posted>[^"]+)"', job_page)
                    if posted_match:
                        posted = posted_match.group('posted').strip()
                        if posted:
                            posted = f'Posted: {posted}'
            except Exception:
                pass

        job_record = {
            'title': title,
            'location': re.sub(r'\s+', ' ', location).strip(),
            'posted': posted,
            'url': full_url,
        }
        if full_url in jobs:
            existing = jobs[full_url]
            if not existing['location'] and job_record['location']:
                existing['location'] = job_record['location']
            if not existing['posted'] and job_record['posted']:
                existing['posted'] = job_record['posted']
            if not existing['title'] and job_record['title']:
                existing['title'] = job_record['title']
        else:
            jobs[full_url] = job_record

    deduped_jobs = list(jobs.values())
    return {'total_jobs': len(deduped_jobs), 'jobs': deduped_jobs}


def extract_intuit_jobs(url: str) -> dict[str, Any]:
    html_text = request_html(url)
    jobs = []
    for match in re.finditer(
        r'<a(?=[^>]*\bclass=["\"][^"\"]*\bsr-item\b[^"\"]*["\"])(?=[^>]*\bhref=["\"](?P<href>[^"\"]+)["\"])[^>]*>(?P<body>.*?)</a>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        href = match.group("href").strip()
        body = match.group("body")

        title_match = re.search(r'<h2[^>]*>(?P<title>[^<]+)</h2>', body, re.IGNORECASE)
        if not title_match:
            title_match = re.search(r'data-title=["\"](?P<title>[^"\"]+)["\"]', body, re.IGNORECASE)

        location_match = re.search(
            r'<span[^>]+class=["\"][^"\"]*\bjob-location\b[^"\"]*["\"][^>]*>(?P<location>[^<]+)</span>',
            body,
            re.IGNORECASE,
        )

        title = html.unescape(title_match.group("title").strip()) if title_match else "(no title)"
        location = html.unescape(location_match.group("location").strip()) if location_match else ""
        jobs.append(
            {
                "title": title,
                "location": location,
                "posted": "",
                "url": urljoin(url, href),
            }
        )

    return {"total_jobs": len(jobs), "jobs": jobs}


def extract_dell_jobs(url: str) -> dict[str, Any]:
    html_text = request_html(url)
    jobs = []
    for match in re.finditer(
        r'<a(?=[^>]*\bdata-job-id=["\"][^"\"]+["\"])(?=[^>]*\bhref=["\"](?P<href>[^"\"]+)["\"])[^>]*>(?P<body>.*?)</a>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        href = match.group("href").strip()
        body = match.group("body")

        title_match = re.search(r'<h2[^>]*>(?P<title>[^<]+)</h2>', body, re.IGNORECASE)
        location_match = re.search(
            r'<span[^>]+class=["\"][^"\"]*\bjob-info\b[^"\"]*\bjob-location\b[^"\"]*["\"][^>]*>(?P<location>.*?)</span>',
            body,
            re.IGNORECASE | re.DOTALL,
        )

        title = html.unescape(title_match.group("title").strip()) if title_match else "(no title)"
        raw_location = location_match.group("location") if location_match else ""
        location = re.sub(r"\s+", " ", html.unescape(re.sub(r'<[^>]+>', '', raw_location)).strip())

        jobs.append(
            {
                "title": title,
                "location": location,
                "posted": "",
                "url": urljoin(url, href),
            }
        )

    return {"total_jobs": len(jobs), "jobs": jobs}


def extract_stryker_jobs(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            "Playwright is required for Stryker scraping. "
            "Install it with: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=REQUEST_HEADERS["User-Agent"],
            extra_http_headers={"Accept-Language": REQUEST_HEADERS["Accept-Language"]},
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(12000)

        accept_buttons = page.locator('button:has-text("Accept All Cookies")')
        if accept_buttons.count() > 0:
            accept_buttons.first.click()
            page.wait_for_timeout(1000)

        jobs = []
        locator = page.locator("a.results-list__item-title--link")
        for i in range(locator.count()):
            item = locator.nth(i)
            title = item.inner_text().strip()
            href = item.get_attribute("href") or ""
            full_url = href if href.startswith("http") else urljoin(url, href)

            location = ""
            parent_item = item.locator('xpath=ancestor::li[1]')
            location_locator = parent_item.locator("span.results-list__item-street--label")
            if location_locator.count() > 0:
                location = location_locator.first.inner_text().strip()

            jobs.append(
                {
                    "title": title,
                    "location": location,
                    "posted": "",
                    "url": full_url,
                }
            )

        total_jobs = len(jobs)
        browser.close()

    return {"total_jobs": total_jobs, "jobs": jobs}


def extract_bms_jobs(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            "Playwright is required for BMS scraping. "
            "Install it with: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=REQUEST_HEADERS["User-Agent"],
            extra_http_headers={"Accept-Language": REQUEST_HEADERS["Accept-Language"]},
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(12000)

        accept_buttons = page.locator('button:has-text("Accept All Cookies")')
        if accept_buttons.count() > 0:
            accept_buttons.first.click()
            page.wait_for_timeout(1000)

        jobs = []
        locator = page.locator('a[aria-label^="View job:"][href^="/careers/job/"]')
        for i in range(locator.count()):
            item = locator.nth(i)
            href = item.get_attribute("href") or ""
            aria_label = item.get_attribute("aria-label") or ""
            title = re.sub(r"^View job:\s*", "", aria_label).strip()

            text = item.inner_text().strip()
            posted = ""
            posted_match = re.search(
                r"(Posted\s+(?:Today|Yesterday|\d+\s+days?\s+ago))$",
                text,
                re.IGNORECASE,
            )
            if posted_match:
                posted = posted_match.group(1).strip()

            location = text
            if posted_match:
                location = text[: posted_match.start()].strip()
            if title and location.startswith(title):
                location = location[len(title) :].strip()
            location = re.sub(r"\bR\d+\s*$", "", location).strip()

            jobs.append(
                {
                    "title": title or "(no title)",
                    "location": location,
                    "posted": posted,
                    "url": urljoin(url, href),
                }
            )

        total_jobs = len(jobs)
        browser.close()

    return {"total_jobs": total_jobs, "jobs": jobs}


def extract_workday_jobs(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            "Playwright is required for Workday scraping. "
            "Install it with: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=REQUEST_HEADERS["User-Agent"],
            extra_http_headers={"Accept-Language": REQUEST_HEADERS["Accept-Language"]},
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)

        accept_buttons = page.locator('button:has-text("Accept All Cookies")')
        if accept_buttons.count() > 0:
            accept_buttons.first.click()
            page.wait_for_timeout(1000)

        page.wait_for_selector("section[data-automation-id=\"jobResults\"]", timeout=30000)
        page.wait_for_timeout(2000)

        total_jobs_text = page.locator("p[data-automation-id=jobFoundText]").inner_text().strip()
        total_jobs = parse_int(total_jobs_text)

        jobs = []
        locator = page.locator("section[data-automation-id=jobResults] ul[role=\"list\"] li")
        for i in range(locator.count()):
            item = locator.nth(i)
            title_locator = item.locator("a[data-automation-id=jobTitle]")
            if title_locator.count() == 0:
                continue

            title = title_locator.inner_text().strip()
            href = title_locator.get_attribute("href") or ""
            full_url = urljoin(url, href)

            location = ""
            location_locator = item.locator("div[data-automation-id=locations]")
            if location_locator.count() > 0:
                location = location_locator.inner_text().strip()
                location = re.sub(r"^\s*locations?\s*", "", location, flags=re.IGNORECASE).strip()

            posted = ""
            text = item.inner_text()
            posted_match = re.search(
                r"Posted\s+(?:Yesterday|Today|\d+\s+days?\s+ago)",
                text,
                re.IGNORECASE,
            )
            if posted_match:
                posted = posted_match.group(0).strip()

            jobs.append(
                {
                    "title": title,
                    "location": location,
                    "posted": posted,
                    "url": full_url,
                }
            )

        browser.close()

    return {"total_jobs": total_jobs, "jobs": jobs}


def extract_micron_jobs(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            "Playwright is required for rendering the Micron careers page. "
            "Install it with: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=REQUEST_HEADERS["User-Agent"],
            extra_http_headers={"Accept-Language": REQUEST_HEADERS["Accept-Language"]},
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(10000)

        body_text = page.inner_text("body")
        count_match = re.search(r"(\d+)\s+jobs", body_text)
        total_jobs = int(count_match.group(1)) if count_match else None

        jobs = []
        locator = page.locator('a[id^="job-card-"]')
        for i in range(locator.count()):
            element = locator.nth(i)
            href = element.get_attribute("href") or ""
            full_url = href if href.startswith("http") else f"https://careers.micron.com{href}"
            text = element.inner_text().strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) >= 3 and lines[-1].startswith("Posted"):
                title = " ".join(lines[:-2]).strip() if len(lines) > 3 else lines[0]
                location = lines[-2]
                posted = lines[-1]
            elif len(lines) == 3:
                title, location, posted = lines
            else:
                title = lines[0] if lines else "(no title)"
                location = lines[1] if len(lines) > 1 else "(no location)"
                posted = lines[2] if len(lines) > 2 else "(no posted date)"

            jobs.append(
                {
                    "title": title,
                    "location": location,
                    "posted": posted,
                    "url": full_url,
                }
            )

        browser.close()

    return {"total_jobs": total_jobs, "jobs": jobs}


def extract_capitalone_jobs(url: str) -> dict[str, Any]:
    html_text = request_html(url)
    jobs: dict[str, Any] = {}
    for match in re.finditer(
        r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*data-job-id=["\'][^"\']+["\'][^>]*>(?P<body>.*?)</a>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        href = match.group('href').strip()
        body = match.group('body')
        full_url = urljoin(url, href)

        title_match = re.search(r'<h2[^>]*>\s*(?P<title>[^<]+)\s*</h2>', body, re.IGNORECASE)
        title = html.unescape(title_match.group('title').strip()) if title_match else (
            re.sub(r'<[^>]+>', '', body).strip() or '(no title)'
        )

        location_match = re.search(
            r'<span[^>]+class=["\'][^"\']*job-location[^"\']*["\'][^>]*>(?P<location>[^<]+)</span>',
            body, re.IGNORECASE,
        )
        location = html.unescape(location_match.group('location').strip()) if location_match else ''

        posted_match = re.search(
            r'<span[^>]+class=["\'][^"\']*job-date-posted[^"\']*["\'][^>]*>(?P<posted>[^<]+)</span>',
            body, re.IGNORECASE,
        )
        posted = html.unescape(posted_match.group('posted').strip()) if posted_match else ''

        if full_url not in jobs:
            jobs[full_url] = {
                'title': title,
                'location': re.sub(r'\s+', ' ', location).strip(),
                'posted': posted,
                'url': full_url,
            }
    return {'total_jobs': len(jobs), 'jobs': list(jobs.values())}


def extract_progressive_jobs(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            'Playwright is required for Progressive scraping. '
            'Install it with: pip install playwright && playwright install chromium'
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=REQUEST_HEADERS['User-Agent'],
            extra_http_headers={'Accept-Language': REQUEST_HEADERS['Accept-Language']},
        )
        page = context.new_page()
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(5000)
        try:
            page.wait_for_selector('a.search-results__job-title-link', timeout=20000)
        except Exception:
            pass
        html_text = page.content()
        browser.close()

    jobs = []
    for match in re.finditer(
        r'<a[^>]+class=["\']search-results__job-title-link["\'][^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>'
        r'(?P<title>[^<]+)</a>\s*'
        r'<span[^>]+class=["\']search-results__job-location["\'][^>]*>(?P<location>[^<]+)</span>'
        r'(?:\s*<span[^>]+class=["\']search-results__job-date-posted["\'][^>]*>(?P<posted>[^<]+)</span>)?',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        title = html.unescape(match.group('title')).strip()
        location = html.unescape(match.group('location')).strip()
        href = match.group('href').strip()
        posted = html.unescape(match.group('posted') or '').strip()
        full_url = urljoin(url, href)
        jobs.append({'title': title, 'location': location, 'posted': posted, 'url': full_url})
    return {'total_jobs': len(jobs), 'jobs': jobs}


def extract_greenhouse_jobs(url: str) -> dict[str, Any]:
    html_text = request_html(url)
    jobs = []
    for match in re.finditer(
        r'<tr[^>]+class=["\']job-post["\'][^>]*>.*?'
        r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>.*?'
        r'<p[^>]+class=["\'][^"\']*body--medium[^"\']*["\'][^>]*>(?P<title>[^<]+)</p>.*?'
        r'(?:<p[^>]+class=["\'][^"\']*body--metadata[^"\']*["\'][^>]*>(?P<location>[^<]+)</p>)?',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        href = match.group('href').strip()
        title = html.unescape(match.group('title')).strip()
        location = html.unescape(match.group('location') or '').strip()
        jobs.append({'title': title, 'location': location, 'posted': '', 'url': href})
    return {'total_jobs': len(jobs), 'jobs': jobs}


def extract_corning_jobs(url: str) -> dict[str, Any]:
    base_url = 'https://corningjobs.corning.com'
    html_text = request_html(url)
    jobs = []
    for row in re.finditer(
        r'<tr[^>]+class=["\']data-row["\'][^>]*>(.*?)</tr>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        row_html = row.group(1)
        title_match = re.search(
            r'<a[^>]+class=["\'][^"\']*jobTitle-link[^"\']*["\'][^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>'
            r'(?P<title>[^<]+)</a>',
            row_html, re.IGNORECASE,
        )
        if not title_match:
            continue
        title = html.unescape(title_match.group('title')).strip()
        href = title_match.group('href').strip()
        full_url = href if href.startswith('http') else urljoin(base_url, href)

        location_match = re.search(
            r'<td[^>]+class=["\']colLocation[^"\']*["\'][^>]*>.*?'
            r'<span[^>]+class=["\'][^"\']*jobLocation[^"\']*["\'][^>]*>(?P<location>[^<]+)</span>',
            row_html, re.IGNORECASE | re.DOTALL,
        )
        location = ''
        if location_match:
            location = html.unescape(location_match.group('location')).strip()
        else:
            loc_match2 = re.search(
                r'<span[^>]+class=["\'][^"\']*jobLocation[^"\']*["\'][^>]*>\s*'
                r'<span[^>]+class=["\'][^"\']*jobLocation[^"\']*["\'][^>]*>(?P<location>[^<]+)</span>',
                row_html, re.IGNORECASE | re.DOTALL,
            )
            if loc_match2:
                location = html.unescape(loc_match2.group('location')).strip()

        posted_match = re.search(
            r'<td[^>]+class=["\']colDate[^"\']*["\'][^>]*>.*?'
            r'<span[^>]+class=["\'][^"\']*jobDate[^"\']*["\'][^>]*>(?P<posted>[^<]+)</span>',
            row_html, re.IGNORECASE | re.DOTALL,
        )
        if not posted_match:
            posted_match = re.search(
                r'<span[^>]+class=["\'][^"\']*jobDate[^"\']*["\'][^>]*>(?P<posted>[^<]+)</span>',
                row_html, re.IGNORECASE | re.DOTALL,
            )
        posted = html.unescape(posted_match.group('posted')).strip() if posted_match else ''

        jobs.append({
            'title': title,
            'location': re.sub(r'\s+', ' ', location).strip(),
            'posted': re.sub(r'\s+', ' ', posted).strip(),
            'url': full_url,
        })
    return {'total_jobs': len(jobs), 'jobs': jobs}


def extract_honeywell_jobs(url: str) -> dict[str, Any]:
    import ast as _ast
    try:
        import requests as _req
    except ImportError as exc:
        raise ImportError("requests is required") from exc

    from urllib.parse import parse_qs

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    categories = qs.get("selectedCategoriesFacet", [""])[0]
    orgs = qs.get("selectedOrganizationsFacet", [""])[0]
    last_facet = qs.get("lastSelectedFacet", ["CATEGORIES"])[0]
    sort_by = qs.get("sortBy", ["POSTING_DATES_DESC"])[0]

    # Fetch the careers page HTML to extract Oracle pod URL + site number from CX_CONFIG
    session = _req.Session()
    session.headers.update(REQUEST_HEADERS)
    html_resp = session.get(url, timeout=30)
    html_resp.raise_for_status()
    html_text = html_resp.text

    api_base_match = re.search(r"apiBaseUrl:\s*'([^']+)'", html_text)
    site_number_match = re.search(r"siteNumber:\s*'([^']+)'", html_text)
    if not api_base_match:
        raise ValueError("Could not find Oracle HCM apiBaseUrl on Honeywell careers page")
    api_base = api_base_match.group(1).rstrip("/")
    site_number = site_number_match.group(1) if site_number_match else "CX_1"

    session.headers["Accept"] = "application/json"
    session.headers["Origin"] = "https://careers.honeywell.com"
    session.headers["Referer"] = "https://careers.honeywell.com/"

    expand = (
        "requisitionList.workLocation,requisitionList.otherWorkLocations,"
        "requisitionList.secondaryLocations,flexFieldsFacet.values,"
        "requisitionList.requisitionFlexFields"
    )
    facets_list = "LOCATIONS%3BWORK_LOCATIONS%3BWORKPLACE_TYPES%3BTITLES%3BCATEGORIES%3BORGANIZATIONS%3BPOSTING_DATES%3BFLEX_FIELDS"
    limit = 100
    offset = 0
    total = None
    jobs = []

    while True:
        finder_parts = [
            f"siteNumber={site_number}",
            f"facetsList={facets_list}",
            f"limit={limit}",
            f"offset={offset}",
            f"lastSelectedFacet={last_facet}",
            f"sortBy={sort_by}",
        ]
        if categories:
            finder_parts.append(f"selectedCategoriesFacet={categories}")
        if orgs:
            finder_parts.append(f"selectedOrganizationsFacet={orgs}")
        finder = ",".join(finder_parts)

        api_url = (
            f"{api_base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            f"?onlyData=true&expand={expand}&finder=findReqs;{finder}"
        )
        resp = session.get(api_url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        if not items:
            break
        search = items[0]
        if total is None:
            total = int(search.get("TotalJobsCount", 0) or 0)

        req_list = search.get("requisitionList", [])
        if isinstance(req_list, str):
            req_list = _ast.literal_eval(req_list)
        if not req_list:
            break

        for req in req_list:
            job_id = req.get("Id", "")
            title = (req.get("Title") or "").strip()
            posted = (req.get("PostedDate") or "")[:10]
            location = (req.get("PrimaryLocation") or "").strip()
            jobs.append({
                "title": title,
                "location": location,
                "posted": posted,
                "url": f"https://careers.honeywell.com/en/sites/Honeywell/job/{job_id}",
            })

        offset += limit
        if total is not None and offset >= total:
            break

    return {"total_jobs": total, "jobs": jobs}


def extract_uber_jobs(url: str) -> dict[str, Any]:
    from urllib.parse import parse_qs
    try:
        import requests as _req
    except ImportError as exc:
        raise ImportError("requests is required") from exc

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    departments = qs.get("department", ["Engineering"])

    session = _req.Session()
    session.headers.update(REQUEST_HEADERS)
    session.headers["x-csrf-token"] = "x"
    session.headers["Content-Type"] = "application/json"

    resp = session.post(
        "https://www.uber.com/api/loadSearchJobsResults?page=1",
        json={"params": {"department": departments}},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    results = data.get("data", {}).get("results", [])
    jobs = []
    for item in results:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        loc = item.get("location") or {}
        location = ", ".join(filter(None, [
            loc.get("city", ""),
            loc.get("region", ""),
            loc.get("countryName", ""),
        ]))
        posted = (item.get("creationDate") or "")[:10]
        job_id = item.get("id", "")
        jobs.append({
            "title": title,
            "location": location,
            "posted": posted,
            "url": f"https://www.uber.com/global/en/careers/list/{job_id}/",
        })

    return {"total_jobs": len(jobs), "jobs": jobs}


def extract_applovin_jobs(url: str) -> dict[str, Any]:
    import json as _json
    api_url = 'https://boards-api.greenhouse.io/v1/boards/applovin/jobs'
    response_text = request_html(api_url)
    data = _json.loads(response_text)
    jobs = []
    for job in data.get('jobs', []):
        title = job.get('title', '').strip()
        location = (job.get('location') or {}).get('name', '').strip()
        absolute_url = job.get('absolute_url', '').strip()
        updated_at = job.get('updated_at', '')[:10]
        jobs.append({
            'title': title,
            'location': location,
            'posted': updated_at,
            'url': absolute_url,
        })
    return {'total_jobs': len(jobs), 'jobs': jobs}


def extract_jobs(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    if "careers.micron.com" in hostname:
        return extract_micron_jobs(url)
    if "careers.mckesson.com" in hostname:
        return extract_mckesson_jobs(url)
    if "jobs.intuit.com" in hostname:
        return extract_intuit_jobs(url)
    if "jobs.bms.com" in hostname:
        return extract_bms_jobs(url)
    if "careers.stryker.com" in hostname:
        return extract_stryker_jobs(url)
    if "jobs.dell.com" in hostname:
        return extract_dell_jobs(url)
    if "myworkdayjobs.com" in hostname:
        return extract_workday_jobs(url)
    if "capitalonecareers.com" in hostname:
        return extract_capitalone_jobs(url)
    if "careers.progressive.com" in hostname:
        return extract_progressive_jobs(url)
    if "greenhouse.io" in hostname:
        return extract_greenhouse_jobs(url)
    if "corningjobs.corning.com" in hostname:
        return extract_corning_jobs(url)
    if "applovin.com" in hostname:
        return extract_applovin_jobs(url)
    if "careers.spglobal.com" in hostname:
        return extract_spglobal_jobs(url)
    if "jobs.paloaltonetworks.com" in hostname:
        return extract_paloalto_jobs(url)
    if "careers.qualcomm.com" in hostname:
        return extract_qualcomm_jobs(url)
    if "lockheedmartinjobs.com" in hostname:
        return extract_lockheed_jobs(url)
    if "careers.honeywell.com" in hostname:
        return extract_honeywell_jobs(url)
    if "uber.com" in hostname:
        return extract_uber_jobs(url)

    raise ValueError(f"Unsupported URL host: {hostname}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch career listings from Micron, McKesson, Intuit, BMS, Prologis, Stryker, Dell, Corning, AppLovin, S&P Global, Palo Alto Networks, Qualcomm, Lockheed Martin, or Workday-based sites and print titles, location, posted date, and URL."
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="One or more careers page URLs to fetch. If omitted, the built-in default list will be used.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of jobs to print per URL.",
    )
    args = parser.parse_args()

    urls = args.urls if args.urls else DEFAULT_URLS
    for url in urls:
        print(f"=== {url} ===")
        try:
            data = extract_jobs(url)
        except Exception as exc:
            print(f"Error fetching jobs from {url}: {exc}\n")
            continue

        total_jobs = data["total_jobs"]
        jobs = data["jobs"]

        if total_jobs is not None:
            print(f"Total jobs found on page: {total_jobs}")
        print(f"Extracted {len(jobs)} job cards; showing up to {args.limit}:\n")

        for job in jobs[: args.limit]:
            print(f"- {job['title']}")
            print(f"  Location: {job['location']}")
            if job["posted"]:
                print(f"  {job['posted']}")
            print(f"  URL: {job['url']}\n")


if __name__ == "__main__":
    main()
