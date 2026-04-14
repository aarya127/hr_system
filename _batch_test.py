"""Batch test all untested / recently-fixed companies."""
import sys, time
sys.path.insert(0, ".")

from src.companies import COMPANIES
from src.scraper import scrape_company_jobs

# Companies to test (by rank) — skip confirmed-working Amazon/NVIDIA/MSFT/Apple
# and skip still-in-maintenance Workday: JPMorgan(11), Costco(20), J&J(17), Coke(23), Broadcom(9)
SKIP_RANKS = {1, 2, 4, 5, 9, 11, 17, 20, 23}  # working or known-maintenance
TEST_RANKS = [c for c in COMPANIES if c["rank"] not in SKIP_RANKS]

results = []
for company in TEST_RANKS:
    name = company["name"]
    rank = company["rank"]
    scraper = company["scraper"]
    print(f"\n[{rank:2}] {name} ({scraper}) ...", flush=True)
    t0 = time.time()
    try:
        jobs = scrape_company_jobs(company, hours_old=168, results_wanted=10)
        elapsed = time.time() - t0
        status = "✅" if jobs else "❌"
        print(f"     {status} {len(jobs)} jobs  ({elapsed:.1f}s)")
        results.append((rank, name, scraper, len(jobs), None))
    except Exception as e:
        elapsed = time.time() - t0
        print(f"     💥 ERROR: {str(e)[:80]}  ({elapsed:.1f}s)")
        results.append((rank, name, scraper, 0, str(e)[:80]))

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
for rank, name, scraper, count, err in results:
    if err:
        print(f"  [{rank:2}] {name:25} 💥 ERROR: {err[:50]}")
    elif count:
        print(f"  [{rank:2}] {name:25} ✅ {count} jobs")
    else:
        print(f"  [{rank:2}] {name:25} ❌ 0 jobs")
