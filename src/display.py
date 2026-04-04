"""
Rich-based terminal display helpers.
"""

from datetime import date, datetime
from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _rank_style(rank) -> str:
    if not isinstance(rank, int):
        return "white"
    if rank <= 3:
        return "bold bright_yellow"
    if rank <= 10:
        return "bold bright_cyan"
    if rank <= 20:
        return "bold cyan"
    return "cyan"


def _format_date(value) -> str:
    """Return a colour-coded human-readable date string."""
    if not value:
        return "[dim]—[/dim]"

    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return f"[dim]{value}[/dim]"

    if isinstance(value, datetime):
        value = value.date()

    today = date.today()
    delta = (today - value).days

    if delta < 0:
        return f"[dim]{value.strftime('%b %d, %Y')}[/dim]"
    if delta == 0:
        return "[bold bright_green]Today[/bold bright_green]"
    if delta == 1:
        return "[green]Yesterday[/green]"
    if delta <= 7:
        return f"[yellow]{delta}d ago[/yellow]"
    if delta <= 30:
        return f"[orange3]{delta}d ago[/orange3]"
    return f"[dim]{value.strftime('%b %d, %Y')}[/dim]"


_SOURCE_STYLE = {
    "linkedin":       "[blue]LinkedIn[/blue]",
    "indeed":         "[bright_cyan]Indeed[/bright_cyan]",
    "glassdoor":      "[bright_green]Glassdoor[/bright_green]",
    "google":         "[bright_red]Google[/bright_red]",
    "zip_recruiter":  "[orange3]ZipRecruiter[/orange3]",
    "amazon_direct":  "[bold yellow]Amazon.jobs[/bold yellow]",
}


# ---------------------------------------------------------------------------
# Public display functions
# ---------------------------------------------------------------------------

def display_jobs(jobs: list[dict], title: str = "Job Openings") -> None:
    """Render a rich table of job postings."""
    if not jobs:
        console.print("[yellow]No jobs found.[/yellow]")
        return

    table = Table(
        title=title,
        box=box.ROUNDED,
        header_style="bold white on dark_blue",
        border_style="bright_blue",
        show_lines=False,
        expand=False,
    )

    table.add_column("#",        style="dim",         width=4,  justify="right")
    table.add_column("Rank",                          width=6,  justify="center")
    table.add_column("Company",   min_width=18, max_width=24)
    table.add_column("Position",  min_width=28, max_width=46)
    table.add_column("Location",  min_width=14, max_width=26)
    table.add_column("Posted",    width=13)
    table.add_column("Type",      width=11)
    table.add_column("Source",    width=12)

    for idx, job in enumerate(jobs, 1):
        rank = job.get("company_rank")
        style = _rank_style(rank)

        company_txt = Text(job.get("company_name") or "—")
        company_txt.stylize(style)

        title_raw = job.get("title") or "—"
        if len(title_raw) > 45:
            title_raw = title_raw[:42] + "…"

        location = job.get("location") or ""
        if len(location) > 25:
            location = location[:22] + "…"

        job_type = (job.get("job_type") or "").replace("fulltime", "Full-time").replace("parttime", "Part-time")

        source_key = (job.get("source") or "").lower()
        source_display = _SOURCE_STYLE.get(source_key, source_key or "—")

        remote_badge = " [dim](remote)[/dim]" if job.get("is_remote") else ""

        table.add_row(
            str(idx),
            f"[{style}]#{rank or '?'}[/{style}]",
            company_txt,
            title_raw + remote_badge,
            location or "—",
            _format_date(job.get("date_posted")),
            job_type or "—",
            source_display,
        )

    console.print(table)
    console.print(f"[dim]Showing {len(jobs)} job(s)[/dim]\n")


def display_stats(stats: list[dict]) -> None:
    """Render a summary table of job counts per company."""
    if not stats:
        console.print("[yellow]No data yet. Run 'scrape' first.[/yellow]")
        return

    table = Table(
        title="Job Posting Statistics — Top 25 US Companies",
        box=box.ROUNDED,
        header_style="bold white on dark_blue",
        border_style="bright_blue",
        show_lines=False,
    )

    table.add_column("Rank",         width=6,  justify="center")
    table.add_column("Company",      min_width=22)
    table.add_column("Total",        width=8,  justify="right")
    table.add_column("Last 30d",     width=9,  justify="right")
    table.add_column("Last 7d",      width=8,  justify="right")
    table.add_column("Last 24h",     width=9,  justify="right")
    table.add_column("Newest",       width=14)

    for row in stats:
        rank = row.get("company_rank")
        style = _rank_style(rank)

        def _hi(n: int, green_threshold: int = 1) -> str:
            if n and n >= green_threshold:
                return f"[green]{n}[/green]"
            return f"[dim]{n or 0}[/dim]"

        table.add_row(
            f"[{style}]#{rank or '?'}[/{style}]",
            f"[{style}]{row.get('company_name', '—')}[/{style}]",
            str(row.get("total_jobs", 0)),
            _hi(row.get("last_30d", 0)),
            _hi(row.get("last_7d", 0)),
            _hi(row.get("last_24h", 0)),
            _format_date(row.get("newest_posting")),
        )

    console.print(table)


def display_scrape_summary(results: dict[str, tuple[int, int]]) -> None:
    """
    Print a compact per-company summary after a scrape run.

    results: {company_name: (found, new)}
    """
    table = Table(
        title="Scrape Summary",
        box=box.SIMPLE,
        header_style="bold white",
        show_lines=False,
    )
    table.add_column("Company",   min_width=22)
    table.add_column("Found",     width=8,  justify="right")
    table.add_column("New",       width=8,  justify="right")
    table.add_column("Status",    width=10)

    for name, (found, new) in results.items():
        status = "[green]✓[/green]" if found > 0 else "[dim]—[/dim]"
        new_str = f"[bright_green]+{new}[/bright_green]" if new > 0 else "[dim]0[/dim]"
        table.add_row(name, str(found), new_str, status)

    console.print(table)


def display_company_list() -> None:
    """Print the list of tracked companies."""
    from src.companies import COMPANIES

    table = Table(
        title="Tracked Companies (Top 25 by US Market Cap)",
        box=box.ROUNDED,
        header_style="bold white on dark_blue",
        border_style="bright_blue",
    )
    table.add_column("Rank",       width=6,  justify="center")
    table.add_column("Company",    min_width=22)
    table.add_column("Source",     width=13)
    table.add_column("Careers Page", min_width=40)

    for c in COMPANIES:
        style = _rank_style(c["rank"])
        src = c.get("scraper", "jobspy")
        src_display = "[bold yellow]amazon.jobs[/bold yellow]" if src == "amazon" else "[bright_cyan]Indeed+Google[/bright_cyan]"
        table.add_row(
            f"[{style}]#{c['rank']}[/{style}]",
            f"[{style}]{c['name']}[/{style}]",
            src_display,
            f"[bright_blue]{c['careers_url']}[/bright_blue]",
        )

    console.print(table)
