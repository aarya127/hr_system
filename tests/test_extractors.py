"""
Integration test suite for extract_jobs.py extractors.

Usage
-----
Run all fast tests (no browser needed):
    pytest tests/ -v -m "not slow"

Run everything including Playwright-based scrapers:
    pytest tests/ -v

Run only a single company:
    pytest tests/ -v -k mckesson
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import pytest

# ── shared helpers ────────────────────────────────────────────────────────────

REQUIRED_KEYS = {"title", "location", "posted", "url"}


def assert_valid_result(result: dict, *, min_jobs: int = 1) -> None:
    """Assert that a scraper result has the expected structure and content."""
    assert isinstance(result, dict), "Result must be a dict"
    assert "jobs" in result, "Result must contain 'jobs'"
    assert "total_jobs" in result, "Result must contain 'total_jobs'"

    jobs = result["jobs"]
    assert isinstance(jobs, list), "'jobs' must be a list"
    assert len(jobs) >= min_jobs, f"Expected ≥{min_jobs} job(s), got {len(jobs)}"

    for i, job in enumerate(jobs):
        missing = REQUIRED_KEYS - job.keys()
        assert not missing, f"Job[{i}] is missing keys: {missing}"
        assert isinstance(job["title"], str) and job["title"], \
            f"Job[{i}] title must be a non-empty string"
        assert isinstance(job["url"], str) and job["url"], \
            f"Job[{i}] url must be a non-empty string"
        parsed = urlparse(job["url"])
        assert parsed.scheme in ("http", "https"), \
            f"Job[{i}] has an invalid URL scheme: {job['url']}"


# ── date parsing / normalization (unit tests – no network) ────────────────────

class TestDateParsing:
    """Tests for app.parse_posted_date, which normalises all date formats."""

    @pytest.fixture(autouse=True)
    def _load(self):
        from app import parse_posted_date
        self.parse = parse_posted_date

    def test_iso_format(self):
        result = self.parse("2026-04-09")
        assert result is not None
        assert result.date() == date(2026, 4, 9)

    def test_iso_datetime(self):
        result = self.parse("2026-04-09T14:30:00")
        assert result is not None
        assert result.date() == date(2026, 4, 9)

    def test_us_format_mm_dd_yyyy(self):
        result = self.parse("04/13/2026")
        assert result is not None
        assert result.date() == date(2026, 4, 13)

    def test_us_format_mm_dd_yy(self):
        result = self.parse("04/13/26")
        assert result is not None
        assert result.date() == date(2026, 4, 13)

    def test_mmm_dd_yyyy(self):
        result = self.parse("Apr 13, 2026")
        assert result is not None
        assert result.date() == date(2026, 4, 13)

    def test_full_month_name(self):
        result = self.parse("April 13, 2026")
        assert result is not None
        assert result.date() == date(2026, 4, 13)

    def test_today(self):
        result = self.parse("Today")
        assert result is not None
        assert result.date() == datetime.now().date()

    def test_posted_today(self):
        result = self.parse("Posted Today")
        assert result is not None
        assert result.date() == datetime.now().date()

    def test_yesterday(self):
        result = self.parse("Yesterday")
        assert result is not None
        assert result.date() == (datetime.now() - timedelta(days=1)).date()

    def test_days_ago(self):
        result = self.parse("3 days ago")
        assert result is not None
        assert result.date() == (datetime.now() - timedelta(days=3)).date()

    def test_posted_days_ago(self):
        result = self.parse("Posted 5 days ago")
        assert result is not None
        assert result.date() == (datetime.now() - timedelta(days=5)).date()

    def test_posted_colon_iso(self):
        # Lockheed-style: "Posted: 2026-04-09"
        result = self.parse("Posted: 2026-04-09")
        assert result is not None
        assert result.date() == date(2026, 4, 9)

    def test_hours_ago(self):
        result = self.parse("Posted 4 hours ago")
        assert result is not None
        expected = datetime.now() - timedelta(hours=4)
        assert abs((result - expected).total_seconds()) < 5

    def test_a_day_ago(self):
        result = self.parse("Posted a day ago")
        assert result is not None
        assert result.date() == (datetime.now() - timedelta(days=1)).date()

    def test_a_month_ago(self):
        result = self.parse("Posted a month ago")
        assert result is not None
        expected = datetime.now() - timedelta(days=30)
        assert abs((result - expected).total_seconds()) < 86400

    def test_months_ago(self):
        result = self.parse("Posted 2 months ago")
        assert result is not None
        expected = datetime.now() - timedelta(days=60)
        assert abs((result - expected).total_seconds()) < 86400

    def test_a_week_ago(self):
        result = self.parse("Posted a week ago")
        assert result is not None
        assert result.date() == (datetime.now() - timedelta(weeks=1)).date()

    def test_empty_string(self):
        assert self.parse("") is None

    def test_whitespace_only(self):
        assert self.parse("   ") is None


class TestDateNormalization:
    """Verify that app._run_fetch stores dates as YYYY-MM-DD strings."""

    def test_normalized_format(self):
        from app import parse_posted_date
        raw_dates = [
            "04/13/2026",
            "Apr 13, 2026",
            "April 13, 2026",
            "2026-04-13",
        ]
        for raw in raw_dates:
            dt = parse_posted_date(raw)
            assert dt is not None, f"Failed to parse: {raw!r}"
            normalized = dt.strftime("%Y-%m-%d")
            assert normalized == "2026-04-13", \
                f"Expected 2026-04-13 from {raw!r}, got {normalized}"

    def test_relative_normalizes_to_today_or_near(self):
        from app import parse_posted_date
        for raw in ("Today", "Posted Today", "0 days ago"):
            dt = parse_posted_date(raw)
            assert dt is not None, f"Failed to parse {raw!r}"
            # Should be within 1 day of now
            delta = abs((datetime.now() - dt).total_seconds())
            assert delta < 86400, f"{raw!r} resolved to {dt}, too far from now"


# ── fast (requests-based) extractor integration tests ─────────────────────────

@pytest.mark.integration
def test_mckesson():
    from extract_jobs import extract_mckesson_jobs
    result = extract_mckesson_jobs(
        "https://careers.mckesson.com/en/search-jobs?acm=ALL&alrpm=ALL"
        "&ascf=[%7B%22key%22:%22custom_fields.JobFunction%22,%22value%22:%22Information+Technology%22%7D]"
    )
    assert_valid_result(result)
    assert any(j["posted"] for j in result["jobs"]), "McKesson should return posted dates"


@pytest.mark.integration
def test_capitalone():
    from extract_jobs import extract_capitalone_jobs
    result = extract_capitalone_jobs(
        "https://www.capitalonecareers.com/search-jobs/United%20States/234/2/6252001/39x76/-98x5/50/2"
    )
    assert_valid_result(result)
    assert any(j["posted"] for j in result["jobs"]), "Capital One should return posted dates"


@pytest.mark.integration
def test_greenhouse_ibkr():
    from extract_jobs import extract_greenhouse_jobs
    result = extract_greenhouse_jobs(
        "https://job-boards.greenhouse.io/ibkr"
        "?departments%5B%5D=4027655002&departments%5B%5D=4027657002"
    )
    assert_valid_result(result)


@pytest.mark.integration
def test_corning():
    from extract_jobs import extract_corning_jobs
    result = extract_corning_jobs(
        "https://corningjobs.corning.com/search-jobs"
        "?collections=6097279-2023-272212-1&filters=6147437-1%2C6147440-1%2C6147442-1"
    )
    assert_valid_result(result)
    assert any(j["posted"] for j in result["jobs"]), "Corning should return posted dates"


@pytest.mark.integration
def test_applovin():
    from extract_jobs import extract_applovin_jobs
    result = extract_applovin_jobs("https://www.applovin.com/en/careers#job-board")
    assert_valid_result(result)
    # AppLovin returns ISO dates from the Greenhouse API
    assert any(j["posted"] for j in result["jobs"]), "AppLovin should return posted dates"
    # Verify ISO format YYYY-MM-DD
    for job in result["jobs"]:
        if job["posted"]:
            assert len(job["posted"]) == 10 and job["posted"][4] == "-", \
                f"AppLovin date not ISO format: {job['posted']!r}"


@pytest.mark.integration
def test_paloalto():
    from extract_jobs import extract_paloalto_jobs
    result = extract_paloalto_jobs("https://jobs.paloaltonetworks.com/en/search-jobs")
    assert_valid_result(result)


@pytest.mark.integration
def test_dell():
    from extract_jobs import extract_dell_jobs
    result = extract_dell_jobs("https://jobs.dell.com/en/search-jobs")
    assert_valid_result(result)


@pytest.mark.integration
def test_intuit():
    from extract_jobs import extract_intuit_jobs
    result = extract_intuit_jobs("https://jobs.intuit.com/search-jobs")
    assert_valid_result(result)


@pytest.mark.integration
def test_lockheed():
    from extract_jobs import extract_lockheed_jobs
    result = extract_lockheed_jobs("https://www.lockheedmartinjobs.com/search-jobs")
    assert_valid_result(result)


# ── slow (Playwright-based) extractor integration tests ───────────────────────

@pytest.mark.slow
@pytest.mark.integration
def test_micron():
    pytest.importorskip("playwright.sync_api")
    from extract_jobs import extract_micron_jobs
    result = extract_micron_jobs(
        "https://careers.micron.com/careers?start=0&pid=41210446&sort_by=timestamp"
    )
    assert_valid_result(result)


@pytest.mark.slow
@pytest.mark.integration
def test_workday_cme():
    pytest.importorskip("playwright.sync_api")
    from extract_jobs import extract_workday_jobs
    result = extract_workday_jobs(
        "https://cmegroup.wd1.myworkdayjobs.com/en-US/cme_careers"
        "?locations=7a3301e6ea5710f69c0df31964e169fd"
        "&locations=7a3301e6ea5710f69c0f7e3613466b20"
        "&locations=7a3301e6ea5710f69c0ece8a424a6ab7"
        "&locations=7a3301e6ea5710f69c0ea186a0046a8f"
    )
    assert_valid_result(result)


@pytest.mark.slow
@pytest.mark.integration
def test_workday_vertex():
    pytest.importorskip("playwright.sync_api")
    from extract_jobs import extract_workday_jobs
    result = extract_workday_jobs("https://vrtx.wd501.myworkdayjobs.com/vertex_careers")
    assert_valid_result(result)


@pytest.mark.slow
@pytest.mark.integration
def test_workday_prologis():
    pytest.importorskip("playwright.sync_api")
    from extract_jobs import extract_workday_jobs
    result = extract_workday_jobs("https://prologis.wd5.myworkdayjobs.com/Prologis_External_Careers")
    assert_valid_result(result)


@pytest.mark.slow
@pytest.mark.integration
def test_stryker():
    pytest.importorskip("playwright.sync_api")
    from extract_jobs import extract_stryker_jobs
    result = extract_stryker_jobs(
        "https://careers.stryker.com/jobs"
        "?filter%5Bcategory%5D%5B0%5D=Data%20Analysis"
        "&filter%5Bcategory%5D%5B1%5D=Engineering"
        "&sort_by=update_date&page_number=1"
        "&location_name=united%20states&location_type=1"
    )
    assert_valid_result(result)


@pytest.mark.slow
@pytest.mark.integration
def test_bms():
    pytest.importorskip("playwright.sync_api")
    from extract_jobs import extract_bms_jobs
    result = extract_bms_jobs(
        "https://jobs.bms.com/careers?start=0&pid=137479694501&sort_by=timestamp"
    )
    assert_valid_result(result)


@pytest.mark.slow
@pytest.mark.integration
def test_spglobal():
    pytest.importorskip("playwright.sync_api")
    from extract_jobs import extract_spglobal_jobs
    result = extract_spglobal_jobs(
        "https://careers.spglobal.com/jobs"
        "?page=1&categories=Information%20Technology"
        "&sortBy=posted_date&descending=true&limit=100"
    )
    assert_valid_result(result)


@pytest.mark.slow
@pytest.mark.integration
def test_qualcomm():
    pytest.importorskip("playwright.sync_api")
    from extract_jobs import extract_qualcomm_jobs
    result = extract_qualcomm_jobs("https://careers.qualcomm.com/careers")
    assert_valid_result(result)


@pytest.mark.slow
@pytest.mark.integration
def test_progressive():
    pytest.importorskip("playwright.sync_api")
    from extract_jobs import extract_progressive_jobs
    result = extract_progressive_jobs(
        "https://careers.progressive.com/search/jobs?sort_by=cfm16,desc"
    )
    assert_valid_result(result)
