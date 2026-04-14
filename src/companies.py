"""
Top 25 US companies by market cap, with metadata for job scraping.

scraper:        Which fetcher strategy to use (see src/scraper.py):
                - "eightfold" : Playwright + network intercept for Eightfold AI ATS.
                - "apple"     : Playwright + network intercept for Apple's custom ATS.
                - "amazon"    : Direct amazon.jobs JSON API.
                - "playwright": Generic Playwright browser scraper (Workday, etc.).
careers_url:    Official careers page URL — navigated to by the Playwright scrapers.
match_terms:    Lower-case substrings to verify scraped job entries belong to
                this company.
scraper_config: Optional dict passed to the scraper (e.g. intercept_pattern).
"""

COMPANIES: list[dict] = [
    {
        "rank": 1,
        "name": "NVIDIA",
        "search_term": "NVIDIA",
        "match_terms": ["nvidia"],
        "scraper": "eightfold",
        "careers_url": "https://jobs.nvidia.com/careers?start=0&location=united+states&sort_by=timestamp",
    },
    {
        "rank": 2,
        "name": "Apple",
        "search_term": "Apple Inc",
        "match_terms": ["apple inc", "apple"],
        "scraper": "apple",
        "careers_url": "https://jobs.apple.com/en-us/search?location=united-states-USA",
    },
    {
        "rank": 3,
        "name": "Alphabet (Google)",
        "search_term": "Google",
        "match_terms": ["google", "alphabet", "deepmind", "waymo"],
        "scraper": "playwright",
        "careers_url": "https://careers.google.com/jobs/results/?location=United+States",
        "scraper_config": {"intercept_pattern": "jobs/search"},
    },
    {
        "rank": 4,
        "name": "Microsoft",
        "search_term": "Microsoft",
        "match_terms": ["microsoft"],
        "scraper": "eightfold",
        "careers_url": "https://apply.careers.microsoft.com/careers?domain=microsoft.com&start=0&location=United+States&sort_by=distance&filter_include_remote=1",
    },
    {
        "rank": 5,
        "name": "Amazon",
        "search_term": "Amazon",
        "match_terms": ["amazon", "amazon web services", "aws", "kuiper", "zappos", "whole foods"],
        "scraper": "amazon",
        "careers_url": "https://www.amazon.jobs/en/search?country=US&sort=recent",
    },
    {
        "rank": 6,
        "name": "Meta Platforms",
        "search_term": "Meta Platforms",
        "match_terms": ["meta platforms", "meta", "facebook", "instagram", "whatsapp"],
        "scraper": "jobspy",  # metacareers.com blocks headless browsers (no GraphQL fires)
        "careers_url": "https://www.metacareers.com/jobs/",
        "scraper_config": {},
    },
    {
        "rank": 7,
        "name": "Berkshire Hathaway",
        "search_term": "Berkshire Hathaway",
        "match_terms": ["berkshire hathaway", "berkshire"],
        "scraper": "playwright",
        "careers_url": "https://www.berkshirehathaway.com/jobs",
        "scraper_config": {},
    },
    {
        "rank": 8,
        "name": "Eli Lilly",
        "search_term": "Eli Lilly",
        "match_terms": ["eli lilly", "lilly"],
        "scraper": "playwright",
        "careers_url": "https://careers.lilly.com/us/en/search-results?keywords=&location=United+States",
        "scraper_config": {"intercept_pattern": "phenompeople"},  # Lilly uses Phenom People, not Workday
    },
    {
        "rank": 9,
        "name": "Broadcom",
        "search_term": "Broadcom",
        "match_terms": ["broadcom"],
        "scraper": "playwright",
        "careers_url": "https://broadcom.wd5.myworkdayjobs.com/External_Career_Portal",
        "scraper_config": {"intercept_pattern": "wday/cxs"},
    },
    {
        "rank": 10,
        "name": "Tesla",
        "search_term": "Tesla",
        "match_terms": ["tesla"],
        "scraper": "jobspy",  # tesla.com/careers is behind Cloudflare WAF (hard 403)
        "careers_url": "https://www.tesla.com/careers/search/#/?country=US",
        "scraper_config": {},
    },
    {
        "rank": 11,
        "name": "JPMorgan Chase",
        "search_term": "JPMorgan Chase",
        "match_terms": ["jpmorgan", "jp morgan", "chase bank", "jpmc"],
        "scraper": "playwright",
        "careers_url": "https://jpmc.wd5.myworkdayjobs.com/en-US/External",
        "scraper_config": {"intercept_pattern": "wday/cxs"},
    },
    {
        "rank": 12,
        "name": "Visa",
        "search_term": "Visa Inc",
        "match_terms": ["visa inc", "visa"],
        "scraper": "playwright",
        "careers_url": "https://careers.visa.com/jobs/search?location=United+States",
        "scraper_config": {},
    },
    {
        "rank": 13,
        "name": "Exxon Mobil",
        "search_term": "ExxonMobil",
        "match_terms": ["exxonmobil", "exxon mobil", "exxon"],
        "scraper": "playwright",
        "careers_url": "https://jobs.exxonmobil.com/jobs?location=United+States",
        "scraper_config": {},
    },
    {
        "rank": 14,
        "name": "Mastercard",
        "search_term": "Mastercard",
        "match_terms": ["mastercard"],
        "scraper": "playwright",
        "careers_url": "https://mastercard.wd1.myworkdayjobs.com/en-US/CorporateCareers",
        "scraper_config": {"intercept_pattern": "wday/cxs"},
    },
    {
        "rank": 15,
        "name": "UnitedHealth",
        "search_term": "UnitedHealth Group",
        "match_terms": ["unitedhealth", "united health", "optum", "unitedhealthcare"],
        "scraper": "playwright",
        "careers_url": "https://careers.unitedhealthgroup.com/search-jobs/United+States/10625/3/6252001/-/-/-/50/2",
        "scraper_config": {},
    },
    {
        "rank": 16,
        "name": "Walmart",
        "search_term": "Walmart",
        "match_terms": ["walmart", "sam's club"],
        "scraper": "playwright",
        "careers_url": "https://careers.walmart.com/results?q=&page=1&sort=postDate&jobState=US",
        "scraper_config": {},
    },
    {
        "rank": 17,
        "name": "Johnson & Johnson",
        "search_term": "Johnson Johnson",
        "match_terms": ["johnson & johnson", "johnson and johnson", "j&j", "janssen", "jnj"],
        "scraper": "playwright",
        "careers_url": "https://jnjglobal.wd1.myworkdayjobs.com/en-US/External",
        "scraper_config": {"intercept_pattern": "wday/cxs"},
    },
    {
        "rank": 18,
        "name": "Oracle",
        "search_term": "Oracle Corporation",
        "match_terms": ["oracle"],
        "scraper": "playwright",
        "careers_url": "https://careers.oracle.com/jobs/#en/sites/jobsearch/jobs?location=United+States",
        "scraper_config": {},
    },
    {
        "rank": 19,
        "name": "Procter & Gamble",
        "search_term": "Procter Gamble",
        "match_terms": ["procter & gamble", "procter and gamble", "p&g"],
        "scraper": "playwright",
        "careers_url": "https://www.pgcareers.com/global/en/search-results",
        "scraper_config": {"intercept_pattern": "wday/cxs"},
    },
    {
        "rank": 20,
        "name": "Costco",
        "search_term": "Costco Wholesale",
        "match_terms": ["costco"],
        "scraper": "playwright",
        "careers_url": "https://costco.wd5.myworkdayjobs.com/en-US/Costco_Careers",
        "scraper_config": {"intercept_pattern": "wday/cxs"},
    },
    {
        "rank": 21,
        "name": "Home Depot",
        "search_term": "Home Depot",
        "match_terms": ["home depot"],
        "scraper": "playwright",
        "careers_url": "https://careers.homedepot.com/jobs/search?location=United+States",
        "scraper_config": {},
    },
    {
        "rank": 22,
        "name": "Chevron",
        "search_term": "Chevron Corporation",
        "match_terms": ["chevron"],
        "scraper": "playwright",
        "careers_url": "https://chevron.wd5.myworkdayjobs.com/en-US/SearchJobs",
        "scraper_config": {"intercept_pattern": "wday/cxs"},
    },
    {
        "rank": 23,
        "name": "Coca-Cola",
        "search_term": "Coca-Cola Company",
        "match_terms": ["coca-cola", "coca cola", "the coca-cola"],
        "scraper": "playwright",
        "careers_url": "https://coke.wd5.myworkdayjobs.com/en-US/coca-cola-careers",
        "scraper_config": {"intercept_pattern": "wday/cxs"},
    },
    {
        "rank": 24,
        "name": "Abbott Laboratories",
        "search_term": "Abbott Laboratories",
        "match_terms": ["abbott laboratories", "abbott"],
        "scraper": "playwright",
        "careers_url": "https://www.jobs.abbott/us/en/search-results?location=United+States",
        "scraper_config": {},
    },
    {
        "rank": 25,
        "name": "PepsiCo",
        "search_term": "PepsiCo",
        "match_terms": ["pepsico", "pepsi"],
        "scraper": "playwright",
        "careers_url": "https://www.pepsicojobs.com/main/jobs?location=United+States",
        "scraper_config": {},
    },
]

# Quick lookup helpers
COMPANIES_BY_RANK: dict[int, dict] = {c["rank"]: c for c in COMPANIES}
COMPANIES_BY_NAME: dict[str, dict] = {c["name"].lower(): c for c in COMPANIES}


def find_company(query: str) -> dict | None:
    """Return a company dict by rank number string or partial name match."""
    if query.isdigit():
        return COMPANIES_BY_RANK.get(int(query))
    q = query.lower()
    # Exact name match first
    if q in COMPANIES_BY_NAME:
        return COMPANIES_BY_NAME[q]
    # Partial match
    for c in COMPANIES:
        if q in c["name"].lower() or q in c["search_term"].lower():
            return c
    return None
