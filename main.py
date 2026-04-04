#!/usr/bin/env python3
"""
HR System — Real-time job tracking for the top 25 US companies.

Usage
-----
  python main.py scrape                   # scrape all 25 companies (last 7 days)
  python main.py scrape -c NVIDIA         # scrape one company
  python main.py scrape -c 3 -d 14       # company #3, last 14 days
  python main.py new                      # new jobs in the last 7 days
  python main.py new --since 2025-03-01  # new jobs since a specific date
  python main.py new -c Apple            # filter by company
  python main.py list                     # browse all stored jobs
  python main.py list -c Tesla --since 2025-03-01
  python main.py stats                   # dashboard summary
  python main.py companies               # list tracked companies
  python main.py export -o jobs.csv      # export to CSV
"""

import csv
import sys
from datetime import date, timedelta

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from src.companies import COMPANIES, find_company
from src.database import (
    get_jobs,
    get_new_jobs_since,
    get_stats,
    init_db,
    insert_jobs,
    log_scrape,
)
from src.display import (
    console,
    display_company_list,
    display_jobs,
    display_scrape_summary,
    display_stats,
)
from src.scraper import scrape_company_jobs

# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option("1.0.0", prog_name="hr-system")
def cli() -> None:
    """HR System — track real-time job openings at the top 25 US companies."""
    init_db()


# ---------------------------------------------------------------------------
# scrape
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--company", "-c", default=None,
    help="Company name or rank (1-25). Omit to scrape all 25.",
)
@click.option(
    "--days", "-d", default=7, type=int, show_default=True,
    help="Look back N days when fetching postings.",
)
@click.option(
    "--results", "-r", default=50, type=int, show_default=True,
    help="Max results requested per job board per company.",
)
def scrape(company: str | None, days: int, results: int) -> None:
    """Fetch live job postings and save new ones to the local database."""
    hours_old = days * 24

    if company:
        c = find_company(company)
        if not c:
            console.print(
                f"[red]Company '{company}' not found. "
                "Use a name or rank 1-25 (run 'companies' to see the list).[/red]"
            )
            sys.exit(1)
        targets = [c]
    else:
        targets = COMPANIES

    console.print(
        Panel(
            f"[bold]Scraping [bright_cyan]{len(targets)}[/bright_cyan] "
            f"compan{'y' if len(targets) == 1 else 'ies'} — "
            f"last [bright_cyan]{days}[/bright_cyan] day(s)[/bold]",
            style="bright_blue",
        )
    )

    summary: dict[str, tuple[int, int]] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Starting…", total=len(targets))

        for c in targets:
            progress.update(task, description=f"[cyan]{c['name']}…")

            try:
                jobs = scrape_company_jobs(
                    c, hours_old=hours_old, results_wanted=results
                )
                found, new = insert_jobs(jobs)
                log_scrape(c["name"], found, new)
                summary[c["name"]] = (found, new)

                tag = f"[bright_green]+{new} new[/bright_green]" if new else "[dim]no new[/dim]"
                progress.console.print(
                    f"  [dim]#{c['rank']:>2}[/dim] {c['name']:<26} "
                    f"{found} found  {tag}"
                )
            except Exception as exc:  # noqa: BLE001
                log_scrape(c["name"], 0, 0, status="error", error=str(exc))
                summary[c["name"]] = (0, 0)
                progress.console.print(
                    f"  [red]✗[/red]  {c['name']:<26} [red]{exc}[/red]"
                )

            progress.advance(task)

    total_found = sum(v[0] for v in summary.values())
    total_new = sum(v[1] for v in summary.values())
    console.print(
        f"\n[bold green]Finished.[/bold green]  "
        f"Found [white]{total_found}[/white] jobs, "
        f"[bright_green]{total_new}[/bright_green] new.\n"
    )


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--since", "-s", default=None, metavar="YYYY-MM-DD",
    help="Show jobs posted on or after this date. Defaults to 7 days ago.",
)
@click.option("--company", "-c", default=None, help="Filter by company name or rank.")
@click.option("--limit", "-l", default=200, type=int, show_default=True, help="Max rows to display.")
def new(since: str | None, company: str | None, limit: int) -> None:
    """Show job openings posted since a given date."""
    if since:
        try:
            since_date = date.fromisoformat(since)
        except ValueError:
            console.print(f"[red]Invalid date '{since}'. Use YYYY-MM-DD format.[/red]")
            sys.exit(1)
    else:
        since_date = date.today() - timedelta(days=7)

    company_filter: str | None = None
    if company:
        c = find_company(company)
        company_filter = c["name"] if c else company

    jobs = get_new_jobs_since(since_date, company=company_filter)

    title_parts = [f"New Jobs Since {since_date.strftime('%B %d, %Y')}"]
    if company_filter:
        title_parts.append(company_filter)
    display_jobs(jobs[:limit], title=" — ".join(title_parts))


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@cli.command("list")
@click.option("--since", "-s", default=None, metavar="YYYY-MM-DD", help="Posting date ≥ this date.")
@click.option("--until", "-u", default=None, metavar="YYYY-MM-DD", help="Posting date ≤ this date.")
@click.option("--company", "-c", default=None, help="Filter by company name or rank.")
@click.option("--limit", "-l", default=100, type=int, show_default=True, help="Max rows.")
def list_jobs(
    since: str | None,
    until: str | None,
    company: str | None,
    limit: int,
) -> None:
    """Browse all stored job postings with optional filters."""
    since_date = date.fromisoformat(since) if since else None
    until_date = date.fromisoformat(until) if until else None

    company_filter: str | None = None
    if company:
        c = find_company(company)
        company_filter = c["name"] if c else company

    jobs = get_jobs(since=since_date, until=until_date, company=company_filter, limit=limit)

    parts: list[str] = []
    if company_filter:
        parts.append(company_filter)
    if since_date:
        parts.append(f"from {since_date}")
    if until_date:
        parts.append(f"until {until_date}")

    title = "Job Openings" + (f" — {', '.join(parts)}" if parts else "")
    display_jobs(jobs, title=title)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


@cli.command()
def stats() -> None:
    """Dashboard: job counts per company (total / 30d / 7d / 24h)."""
    data = get_stats()
    if not data:
        console.print(
            "[yellow]No data yet. Run [bold]python main.py scrape[/bold] first.[/yellow]"
        )
        return
    display_stats(data)


# ---------------------------------------------------------------------------
# companies
# ---------------------------------------------------------------------------


@cli.command()
def companies() -> None:
    """List all 25 tracked companies with their ranks."""
    display_company_list()


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--since", "-s", default=None, metavar="YYYY-MM-DD", help="Export jobs posted on or after this date.")
@click.option("--company", "-c", default=None, help="Filter by company.")
@click.option(
    "--output", "-o", default="jobs_export.csv", show_default=True,
    help="Output CSV file path.",
)
def export(since: str | None, company: str | None, output: str) -> None:
    """Export stored job postings to a CSV file."""
    since_date = date.fromisoformat(since) if since else None

    company_filter: str | None = None
    if company:
        c = find_company(company)
        company_filter = c["name"] if c else company

    jobs = get_jobs(since=since_date, company=company_filter, limit=100_000)

    if not jobs:
        console.print("[yellow]No jobs match the criteria — nothing exported.[/yellow]")
        return

    fields = [
        "company_rank", "company_name", "title", "location",
        "date_posted", "job_type", "salary", "is_remote", "source", "job_url",
    ]

    with open(output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(jobs)

    console.print(f"[green]Exported {len(jobs)} job(s) → [bold]{output}[/bold][/green]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
