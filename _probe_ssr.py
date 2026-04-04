"""Probe HTML structure of SSR sites to find the job data format."""
import requests, re, json
from bs4 import BeautifulSoup

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})

def probe(name, url, extra_headers=None):
    print(f"\n{'='*60}")
    print(f"  {name}: {url}")
    print('='*60)
    h = {**S.headers}
    if extra_headers:
        h.update(extra_headers)
    r = requests.get(url, headers=h, timeout=20, allow_redirects=True)
    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    
    # Try __NEXT_DATA__
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd:
        try:
            d = json.loads(nd.string)
            print("  Type: __NEXT_DATA__")
            # Find job records
            s = json.dumps(d)
            # Look for arrays with job-like content
            def find_arrays(obj, path="", depth=0):
                if depth > 8: return
                if isinstance(obj, list) and len(obj) >= 2:
                    if isinstance(obj[0], dict):
                        keys = set(obj[0].keys())
                        job_ish = keys & {'title','jobTitle','positionTitle','requisitionTitle','name','postingTitle'}
                        if job_ish:
                            print(f"  Jobs array at {path}: {len(obj)} items, keys={list(obj[0].keys())[:8]}")
                            print(f"  First: {json.dumps(obj[0], default=str)[:400]}")
                            return
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        find_arrays(v, f"{path}.{k}", depth+1)
                elif isinstance(obj, list):
                    for i, v in enumerate(obj[:3]):
                        find_arrays(v, f"{path}[{i}]", depth+1)
            find_arrays(d)
            return
        except Exception as e:
            print(f"  __NEXT_DATA__ parse error: {e}")
    
    # Try window.__staticRouterHydrationData (Apple-style)
    m = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\(("(?:[^"\\]|\\.)*")\)', html)
    if m:
        try:
            d = json.loads(json.loads(m.group(1)))
            print("  Type: __staticRouterHydrationData")
            s = json.dumps(d)
            titles = re.findall(r'"(?:title|postingTitle|jobTitle)"\s*:\s*"([^"]{5,60})"', s)
            print(f"  Job titles found: {len(titles)}")
            if titles:
                print(f"  Examples: {titles[:3]}")
            return
        except Exception as e:
            print(f"  Hydration parse error: {e}")
    
    # Try finding large JSON blobs in script tags
    print("  No standard SSR key found. Scanning script tags...")
    for script in soup.find_all("script"):
        src = script.get_text()
        if len(src) < 200:
            continue
        # Look for JSON with job arrays
        job_titles = re.findall(r'"(?:title|jobTitle|postingTitle|RequisitionTitle)"\s*:\s*"([^"]{5,80})"', src)
        if job_titles:
            print(f"  Script len={len(src)}: {len(job_titles)} job title refs")
            print(f"  Titles: {job_titles[:3]}")
            # Try to extract the JSON
            # Look for window.xxx = {...} or var xxx = {...}
            assigns = re.findall(r'(?:window\.[a-zA-Z_$]+|var [a-zA-Z_$]+)\s*=\s*(\{.{50,})', src[:5000])
            for a in assigns[:2]:
                print(f"  Assignment: {a[:120]}")
            break
    else:
        # Show a snippet that mentions job data
        idx = re.search(r'(?:jobTitle|postingTitle|searchResults|job_count)', html, re.I)
        if idx:
            start = max(0, idx.start()-50)
            end = min(len(html), idx.end()+300)
            print(f"  Found at pos {idx.start()}: ...{html[start:end]}...")

# Probe each SSR site
probe("Walmart", "https://careers.walmart.com/results?q=&page=1&sort=postDate&jobState=US")
probe("Exxon", "https://jobs.exxonmobil.com/jobs?location=United+States")
probe("Oracle", "https://careers.oracle.com/jobs/#en/sites/jobsearch/jobs?location=United+States")
probe("Abbott", "https://www.jobs.abbott/us/en/search-results?location=United+States")
probe("PepsiCo", "https://www.pepsicojobs.com/main/jobs?location=United+States")
probe("Lilly", "https://careers.lilly.com/us/en/search-results?keywords=&location=United+States")
probe("P&G", "https://www.pgcareers.com/global/en/search-results")
