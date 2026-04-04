# HR System — Real-time Job Tracker

Track **live job openings** at the **top 25 US companies by market cap**, filtered by posting date and stored locally for trend analysis.

---

## Companies tracked (ranked by market cap)

| # | Company | # | Company |
|---|---------|---|---------|
| 1 | NVIDIA | 14 | Mastercard |
| 2 | Apple | 15 | UnitedHealth |
| 3 | Alphabet (Google) | 16 | Walmart |
| 4 | Microsoft | 17 | Johnson & Johnson |
| 5 | Amazon | 18 | Oracle |
| 6 | Meta Platforms | 19 | Procter & Gamble |
| 7 | Berkshire Hathaway | 20 | Costco |
| 8 | Eli Lilly | 21 | Home Depot |
| 9 | Broadcom | 22 | Chevron |
| 10 | Tesla | 23 | Coca-Cola |
| 11 | JPMorgan Chase | 24 | Abbott Laboratories |
| 12 | Visa | 25 | PepsiCo |
| 13 | Exxon Mobil | | |

---

## Quick start

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Scrape all 25 companies (last 7 days of postings)
python main.py scrape

# 3. See new jobs posted since a specific date
python main.py new --since 2025-03-15

# 4. Filter to one company
python main.py new -c NVIDIA

# 5. Open the stats dashboard
python main.py stats
```

---

## Commands

| Command | Description |
|---------|-------------|
| `scrape` | Fetch live postings from LinkedIn, Indeed, and Google Jobs |
| `new` | Show jobs posted **since a date** (default: last 7 days) |
| `list` | Browse all stored jobs with optional date/company filters |
| `stats` | Dashboard: job counts per company (total / 30d / 7d / 24h) |
| `companies` | Print the list of 25 tracked companies |
| `export` | Export to CSV |

### `scrape` options

```
-c / --company   Company name or rank (1-25). Omit to scrape all.
-d / --days      Look-back window in days (default: 7)
-r / --results   Max results per job board per company (default: 50)
```

### `new` / `list` options

```
-s / --since     YYYY-MM-DD  lower bound on posting date
-u / --until     YYYY-MM-DD  upper bound on posting date  (list only)
-c / --company   Filter by company name or rank
-l / --limit     Max rows to display
```

### `export` options

```
-s / --since   Only export jobs posted on or after this date
-c / --company Filter by company
-o / --output  Output file path (default: jobs_export.csv)
```

---

## Examples

```bash
# Scrape only Tesla, looking back 14 days
python main.py scrape -c Tesla -d 14

# Scrape company #4 (Microsoft)
python main.py scrape -c 4

# Show all new jobs discovered since March 1st
python main.py new --since 2025-03-01

# Show Apple jobs from the last 3 days
python main.py new -c Apple --since 2025-03-21

# Export Amazon postings since January 1st
python main.py export -c Amazon -s 2025-01-01 -o amazon_jobs.csv
```

---

## Project layout

```
hr_system/
├── main.py           CLI entry point (click)
├── requirements.txt
├── data/
│   └── jobs.db       SQLite database (auto-created on first run)
└── src/
    ├── companies.py  Company registry (25 entries with LinkedIn IDs)
    ├── database.py   SQLite read/write helpers
    ├── scraper.py    python-jobspy integration + company filtering
    └── display.py    Rich-based terminal tables
```

---

## How it works

1. **Scraping** — `python-jobspy` is used to pull postings from **LinkedIn** (via company ID where available), **Indeed**, and **Google Jobs** simultaneously.
2. **Filtering** — results are matched against each company's `match_terms` list to discard false positives (e.g. "Apple Bank" when searching for Apple).
3. **Deduplication** — jobs are keyed on their URL; re-running `scrape` never creates duplicates.
4. **Date filtering** — the `new` and `list` commands let you slice the dataset by `date_posted`.
5. **Persistence** — everything is stored in `data/jobs.db` (SQLite). Export to CSV anytime with `export`.

---

## Automating daily scrapes (optional)

Add a cron job to keep the database fresh:

```cron
# Run every day at 08:00
0 8 * * * cd /path/to/hr_system && python main.py scrape >> logs/scrape.log 2>&1
```