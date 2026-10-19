"""The ``form4clean`` command."""

from __future__ import annotations

import asyncio
import json
import webbrowser
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from . import __version__
from .client import parse_as_of
from .config import ConfigError, load_settings, save_settings
from .exports.writer import FORMATS
from .market_data.providers import PROVIDERS
from .query import TransactionFilter
from .sec.client import SecError
from .sec.edgar import CompanyNotFoundError, pad_cik
from .service import Form4Service, years_ago
from .storage.store import StoreError

app = typer.Typer(
    name="form4clean",
    help="Clean, standardized, research-ready SEC insider trading data (Forms 4 and 4/A).",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
)
console = Console()
err = Console(stderr=True)

Company = Annotated[str, typer.Argument(help="Ticker (e.g. NVDA) or SEC CIK (e.g. 1045810).")]


@contextmanager
def handled() -> Iterator[None]:
    try:
        yield
    except (ConfigError, CompanyNotFoundError, SecError, StoreError, ValueError) as exc:
        err.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(1) from None


def _service() -> Form4Service:
    return Form4Service(load_settings())


def _version(value: bool) -> None:
    if value:
        console.print(f"form4clean {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version, is_eager=True, help="Show the version and exit."
        ),
    ] = False,
) -> None:
    """Download Form 4 filings from SEC EDGAR, clean them, and export research-ready data."""


# ------------------------------------------------------------------ config


@app.command()
def config(
    email: Annotated[
        str | None,
        typer.Option(
            help="Contact email sent to the SEC in the User-Agent header (required by the SEC)."
        ),
    ] = None,
    app_name: Annotated[
        str | None, typer.Option(help="Application name for the User-Agent.")
    ] = None,
    rate: Annotated[float | None, typer.Option(help="Max SEC requests per second (<= 10).")] = None,
    price_provider: Annotated[
        str | None, typer.Option(help=f"Price source for the chart: {', '.join(PROVIDERS)}.")
    ] = None,
) -> None:
    """Show or change settings. Settings are saved in the data directory."""
    with handled():
        settings = load_settings()
        changes = {
            "contact_email": email,
            "app_name": app_name,
            "requests_per_second": rate,
            "price_provider": price_provider,
        }
        changes = {k: v for k, v in changes.items() if v is not None}
        if price_provider and price_provider not in PROVIDERS:
            raise ValueError(
                f"Unknown provider {price_provider!r}. Choose one of: {', '.join(PROVIDERS)}."
            )
        if changes:
            settings = load_settings(None, **changes)
            path = save_settings(settings)
            console.print(f"[green]Saved[/] {path}")
        table = Table(show_header=False, box=None)
        table.add_row("Data directory", str(settings.home))
        table.add_row(
            "SEC User-Agent",
            settings.user_agent()
            if settings.contact_email
            else "[yellow]not set: run form4clean config --email you@example.com[/]",
        )
        table.add_row("Requests per second", str(settings.requests_per_second))
        table.add_row("Price provider", settings.price_provider)
        console.print(table)


# ------------------------------------------------------------------ fetch / clean


def _progress_bar() -> tuple[Progress, Callable[[str, int, int], None]]:
    bar = Progress(
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )
    task = bar.add_task("Downloading filings", total=None)

    def update(stage: str, done: int, total: int) -> None:
        bar.update(task, completed=done, total=total)

    return bar, update


@app.command()
def fetch(
    company: Company,
    years: Annotated[float, typer.Option(help="Years of history to download.")] = 5,
    start: Annotated[
        str | None, typer.Option(help="First filing date (YYYY-MM-DD). Overrides --years.")
    ] = None,
    end: Annotated[str | None, typer.Option(help="Last filing date (YYYY-MM-DD).")] = None,
) -> None:
    """Download Forms 4 and 4/A from SEC EDGAR, then clean them.

    Filings already downloaded are skipped, so running this again only fetches new ones.
    """
    with handled():
        service = _service()
        first = date.fromisoformat(start) if start else years_ago(years)
        last = date.fromisoformat(end) if end else None
        bar, update = _progress_bar()
        with bar:
            summary = asyncio.run(service.fetch(company, start=first, end=last, progress=update))
        c = summary.company
        console.print(f"[bold]{c.name}[/] ({c.ticker or 'no ticker'}, CIK {c.cik})")
        console.print(f"  Filings listed since {first}: {summary.listed}")
        console.print(
            f"  Already stored: {summary.already_stored}   "
            f"Downloaded: {summary.downloaded}   SEC requests: {summary.requests}"
        )
        for acc, msg in summary.parse_errors:
            console.print(f"  [yellow]Could not parse {acc}:[/] {msg}")
        for acc, msg in summary.download_errors:
            console.print(f"  [red]Could not download {acc}:[/] {msg}")
        other = service.store.other_issuer_filings(pad_cik(c.cik))
        if other:
            console.print(
                f"  {other} of these were filed by {c.name} as an owner of another company's "
                "shares and are not included."
            )
        result = service.clean(c)
        _print_clean_summary(result.report.model_dump())
        if summary.download_errors:
            console.print(
                "[yellow]Some filings could not be downloaded. Run the same command "
                "again to retry them.[/]"
            )


def _print_clean_summary(report: dict[str, Any]) -> None:
    s = report["status_distribution"]
    console.print(
        f"  Transactions: {report['transactions_extracted']}  "
        f"(current view: {report['current_transactions']})   "
        f"[green]valid {s['VALID']}[/]  [yellow]warning {s['WARNING']}[/]  "
        f"[magenta]review {s['REVIEW_REQUIRED']}[/]  [red]invalid {s['INVALID']}[/]"
    )


@app.command()
def clean(company: Company) -> None:
    """Re-run the cleaning engine on stored filings (no network needed)."""
    with handled():
        service = _service()
        c = service.require_company(company)
        result = service.clean(c)
        console.print(f"[bold]{c.name}[/]: cleaned {result.report.filings_processed} filings")
        _print_clean_summary(result.report.model_dump())


# ------------------------------------------------------------------ query and export


def _filters(
    start: str | None,
    end: str | None,
    codes: list[str] | None,
    roles: list[str] | None,
    categories: list[str] | None,
    insider: list[str] | None,
    min_value: float | None,
    include_superseded: bool,
) -> TransactionFilter:
    return TransactionFilter(
        start=date.fromisoformat(start) if start else None,
        end=date.fromisoformat(end) if end else None,
        codes=codes or [],
        roles=roles or [],
        categories=categories or [],
        insiders=insider or [],
        min_value=Decimal(str(min_value)) if min_value is not None else None,
        include_superseded=include_superseded,
    )


StartOpt = Annotated[str | None, typer.Option(help="Earliest transaction date (YYYY-MM-DD).")]
EndOpt = Annotated[str | None, typer.Option(help="Latest transaction date (YYYY-MM-DD).")]
CodeOpt = Annotated[list[str] | None, typer.Option("--code", help="SEC transaction code (repeat).")]
RoleOpt = Annotated[list[str] | None, typer.Option("--role", help="Role, e.g. CEO (repeat).")]
CatOpt = Annotated[
    list[str] | None, typer.Option("--category", help="Category, e.g. 'Market Purchase' (repeat).")
]
InsiderOpt = Annotated[
    list[str] | None, typer.Option("--insider", help="Insider name or CIK (repeat).")
]
MinValOpt = Annotated[float | None, typer.Option(help="Minimum transaction value in dollars.")]
AsOfOpt = Annotated[
    str | None,
    typer.Option(
        "--as-of", help="Point-in-time view: only what was public by this date or timestamp."
    ),
]
AllOpt = Annotated[
    bool, typer.Option("--all", help="Include superseded and ambiguous amendment records.")
]


@app.command()
def transactions(
    company: Company,
    start: StartOpt = None,
    end: EndOpt = None,
    code: CodeOpt = None,
    role: RoleOpt = None,
    category: CatOpt = None,
    insider: InsiderOpt = None,
    min_value: MinValOpt = None,
    as_of: AsOfOpt = None,
    include_all: AllOpt = False,
    limit: Annotated[int, typer.Option(help="Rows to show (most recent first).")] = 25,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON records.")] = False,
) -> None:
    """Show cleaned transactions in the terminal."""
    with handled():
        service = _service()
        c = service.require_company(company)
        flt = _filters(start, end, code, role, category, insider, min_value, include_all)
        df, _ = service.transactions(c, filters=flt, as_of=parse_as_of(as_of))
        df = df.sort("filing_timestamp", descending=True, nulls_last=True)
        if as_json:
            console.print_json(df.head(limit).write_json())
            return
        table = Table(title=f"{c.ticker or c.cik}: {df.height} transactions", header_style="bold")
        for col in (
            "Date",
            "Filed",
            "Insider",
            "Role",
            "Code",
            "Type",
            "Shares",
            "Price",
            "Value",
            "Own.",
            "Quality",
        ):
            table.add_column(
                col,
                justify="right" if col in ("Shares", "Price", "Value") else "left",
                overflow="fold",
            )
        for r in df.head(limit).iter_rows(named=True):
            colour = {"ACQUISITION": "green", "DISPOSITION": "red"}.get(
                r["transaction_direction"], "white"
            )
            table.add_row(
                str(r["transaction_date"] or "-"),
                str(r["filing_date"] or "-"),
                r["insider_name"] or "-",
                r["insider_role"],
                r["transaction_code"] or "-",
                f"[{colour}]{r['transaction_category']}[/]",
                _fmt(r["shares"], 0),
                _fmt(r["price_per_share"], 2, "$"),
                _fmt(r["transaction_value"], 0, "$"),
                (r["ownership_type"] or "-")[:3],
                r["quality_status"],
            )
        console.print(table)


def _fmt(value: Decimal | None, places: int, prefix: str = "") -> str:
    if value is None:
        return "-"
    return f"{prefix}{value:,.{places}f}"


@app.command()
def quality(
    company: Company,
    as_json: Annotated[bool, typer.Option("--json", help="Print the full report as JSON.")] = False,
) -> None:
    """Show the data quality report."""
    with handled():
        service = _service()
        c = service.require_company(company)
        _, report = service.transactions(c)
        if report is None:
            raise ValueError("No report yet. Run: form4clean clean " + company)
        if as_json:
            console.print_json(report.model_dump_json())
            return
        console.print(f"[bold]Data quality: {c.name}[/] (cleaning v{report.cleaning_version})")
        rows = [
            ("Filings processed", report.filings_processed),
            ("Filings that failed to parse", report.filings_failed),
            ("Duplicate filings ignored", report.duplicate_filings_ignored),
            ("Transactions extracted", report.transactions_extracted),
            (
                "Transactions classified",
                f"{report.transactions_classified} ({report.classification_coverage:.1%})",
            ),
            ("Current view", report.current_transactions),
            ("Possible duplicates", report.duplicates_detected),
            ("Amendment filings", report.amendments.amendment_filings),
            ("  linked to their original", report.amendments.linked),
            ("  original not in dataset", report.amendments.original_not_found),
            ("  ambiguous", report.amendments.ambiguous),
            ("Records superseded", report.amendments.records_superseded),
            ("Records requiring review", report.records_requiring_review),
        ]
        t = Table(show_header=False, box=None)
        for k, v in rows:
            t.add_row(k, str(v))
        console.print(t)
        dist = Table(title="Quality status", header_style="bold")
        dist.add_column("Status")
        dist.add_column("Records", justify="right")
        for k, v in report.status_distribution.items():
            dist.add_row(k, str(v))
        console.print(dist)
        if report.issues:
            issues = Table(title="Issues", header_style="bold")
            for col in ("Code", "Severity", "Count", "Review?", "What it means"):
                issues.add_column(col, overflow="fold")
            for i in report.issues:
                issues.add_row(
                    i.code, i.severity, str(i.count), "yes" if i.review_recommended else "no", i.why
                )
            console.print(issues)


@app.command()
def export(
    company: Company,
    fmt: Annotated[
        str, typer.Option("--format", "-f", help=f"One of: {', '.join(FORMATS)}.")
    ] = "parquet",
    output: Annotated[Path, typer.Option("--output", "-o", help="Output directory.")] = Path(
        "form4clean_exports"
    ),
    start: StartOpt = None,
    end: EndOpt = None,
    code: CodeOpt = None,
    role: RoleOpt = None,
    category: CatOpt = None,
    insider: InsiderOpt = None,
    min_value: MinValOpt = None,
    as_of: AsOfOpt = None,
    include_all: AllOpt = False,
    no_reconcile: Annotated[
        bool,
        typer.Option(
            "--no-reconcile", help="Do not reconcile amendments; export every record as filed."
        ),
    ] = False,
    no_raw: Annotated[bool, typer.Option("--no-raw", help="Skip the raw dataset.")] = False,
) -> None:
    """Export the cleaned dataset, the raw dataset, the quality report and a manifest."""
    with handled():
        if fmt not in FORMATS:
            raise ValueError(f"Unknown format {fmt!r}. Use one of: {', '.join(FORMATS)}.")
        service = _service()
        c = service.require_company(company)
        flt = _filters(start, end, code, role, category, insider, min_value, include_all)
        out = output / (c.ticker or c.cik).upper()
        manifest, path = service.export_bundle(
            c,
            out,
            fmt,
            filters=flt,
            as_of=parse_as_of(as_of),
            reconcile=not no_reconcile,
            include_raw=not no_raw,
        )
        console.print(
            f"[green]Exported {manifest.record_count} records[/] ({manifest.amendment_policy})"
        )
        for f in manifest.files:
            console.print(f"  {out / f.path}  [dim]{f.dataset}, {f.bytes:,} bytes[/]")
        console.print(f"  {path}  [dim]manifest[/]")


@app.command()
def resolve(company: Company) -> None:
    """Look up a company's CIK and name."""
    with handled():
        c = asyncio.run(_service().resolve(company))
        console.print(json.dumps({"cik": c.cik, "ticker": c.ticker, "name": c.name}))


@app.command()
def dashboard(
    host: Annotated[
        str,
        typer.Option(help="Interface to bind. Keep 127.0.0.1 unless you know you need otherwise."),
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port.")] = 8765,
    no_browser: Annotated[bool, typer.Option("--no-browser", help="Don't open a browser.")] = False,
) -> None:
    """Start the local dashboard and open it in your browser."""
    import threading

    import uvicorn

    from .api.app import create_app

    with handled():
        api = create_app(_service())
    url = f"http://{host}:{port}"
    console.print(f"Form4Clean dashboard running at [bold]{url}[/]  (Ctrl+C to stop)")
    if not no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(api, host=host, port=port, log_level="warning")
