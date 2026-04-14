"""Check which career sites embed job data in their HTML (SSR vs SPA)."""
import requests, re, json

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})

sites = [
    ("Google",       "https://careers.google.com/jobs/results/?location=United+States"),
    ("Meta",         "https://www.metacareers.com/jobs/"),
    ("Berkshire",    "https://www.berkshirehathaway.com/jobs"),
    ("Visa",         "https://careers.visa.com/jobs/search?location=United+States"),
    ("Exxon",        "https://jobs.exxonmobil.com/jobs?location=United+States"),
    ("UnitedHealth", "https://careers.unitedhealthgroup.com/search-jobs/United+States/10625/3/6252001/-/-/-/50/2"),
    ("Walmart",      "https://careers.walmart.com/results?q=&page=1&sort=postDate&jobState=US"),
    ("Oracle",       "https://careers.oracle.com/jobs/#en/sites/jobsearch/jobs?location=United+States"),
    ("Mastercard",   "https://mastercard.wd1.myworkdayjobs.com/en-US/CorporateCareers"),
    ("P&G",          "https://www.pgcareers.com/global/en/search-results"),
    ("Home Depot",   "https://careers.homedepot.com/jobs/search?location=United+States"),
    ("Chevron",      "https://chevron.wd5.myworkdayjobs.com/en-US/SearchJobs"),
    ("Abbott",       "https://www.jobs.abbott/us/en/search-results?location=United+States"),
    ("PepsiCo",      "https://www.pepsicojobs.com/main/jobs?location=United+States"),
    ("Lilly",        "https://careers.lilly.com/us/en/search-results?keywords=&location=United+States"),
]

JOB_WORDS = re.compile(r'(jobTitle|postingTitle|positionTitle|requisitionTitle|"title"\s*:\s*"[A-Z]|searchResults|jobResults|totalRecords|job_count|numJobs)', re.I)
NEXT_DATA  = re.compile(r'__NEXT_DATA__|__staticRouterHydrationData|window\.__STATE__|window\.__INITIAL_STATE__')
SPA_SHELL  = re.compile(r'<div id="(root|app|__next)">\s*</div>|<div id="(root|app)">\s*</div>', re.I)

for name, url in sites:
    try:
        r = S.get(url, timeout=12, allow_redirects=True)
        html = r.text
        size = len(html)
        
        has_jobs  = bool(JOB_WORDS.search(html))
        has_ssr   = bool(NEXT_DATA.search(html))
        is_spa    = bool(SPA_SHELL.search(html))
        maintenance = "maintenance" in r.url or "maintenance" in html[:500]
        
        # Count apparent JSON blobs > 1KB
        big_json = len(re.findall(r'\{[^{}]{500,}\}', html))
        
        verdict = "SSR✅" if has_jobs else ("SPA" if is_spa else "unknown")
        if maintenance:
            verdict = "MAINTENANCE"
        
        print(f"  {name:12} {r.status_code}  {size//1000:4}KB  jobs={str(has_jobs):<5}  ssr={str(has_ssr):<5}  spa={str(is_spa):<5}  → {verdict}")
        
        # If SSR, show what hydration key was found
        if has_ssr:
            m = NEXT_DATA.search(html)
            print(f"             SSR key: {m.group(0) if m else '?'}")
        if has_jobs and not has_ssr:
            # Show which job word triggered it
            m = JOB_WORDS.search(html)
            print(f"             job signal: {m.group(0)[:50] if m else '?'}")

    except Exception as e:
        print(f"  {name:12} ERR  {str(e)[:60]}")
