"""Workflows shared by the Python API, the CLI and the HTTP API.

Keeping them here means the three interfaces cannot drift apart: each one is a thin layer that
parses its inputs, calls a method below, and formats the result.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from .cleaning.pipeline import CleanOptions, CleanResult, clean
from .cleaning.records import CompanyInfo
from .config import Settings, load_settings
from .exports.writer import (
    DatasetManifest,
    Format,
    amendment_policy,
    build_manifest,
    manifest_file,
    write_frame,
    write_json,
)
from .market_data.providers import Bar, PriceDataError, PriceSeries, get_provider
from .models.raw import FilingRef
from .models.schema import to_frame
from .parsing.ownership import OwnershipParseError, parse_ownership_xml
from .parsing.submission import parse_submission
from .query import TransactionFilter
from .sec.cache import FileCache
from .sec.client import SecClient, SecError
from .sec.edgar import Company, CompanyNotFoundError, Edgar, pad_cik
from .storage.store import Store
from .validation.report import QualityReport
from .versions import CLEANING_VERSION

Progress = Callable[[str, int, int], None]
DOWNLOAD_CONCURRENCY = 4
PRICE_CACHE_TTL = timedelta(hours=12)


@dataclass
class FetchSummary:
    company: Company
    start: date | None
    end: date | None
    listed: int = 0
    already_stored: int = 0
    downloaded: int = 0
    parse_errors: list[tuple[str, str]] = field(default_factory=list)
    download_errors: list[tuple[str, str]] = field(default_factory=list)
    requests: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "company": {
                "cik": self.company.cik,
                "ticker": self.company.ticker,
                "name": self.company.name,
            },
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "filings_listed": self.listed,
            "already_stored": self.already_stored,
            "downloaded": self.downloaded,
            "parse_errors": [{"accession_number": a, "error": e} for a, e in self.parse_errors],
            "download_errors": [
                {"accession_number": a, "error": e} for a, e in self.download_errors
            ],
            "sec_requests": self.requests,
        }


def years_ago(years: float, today: date | None = None) -> date:
    today = today or date.today()
    return today - timedelta(days=round(365.25 * years))


class Form4Service:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.settings.ensure_dirs()
        self.store = Store(self.settings.db_path)
        self._transport = transport

    def _edgar(self) -> tuple[SecClient, Edgar]:
        client = SecClient(self.settings, transport=self._transport)
        edgar = Edgar(
            client, FileCache(self.settings.cache_dir), self.settings.submissions_ttl_hours
        )
        return client, edgar

    # ------------------------------------------------------------ companies

    def local_company(self, query: str) -> Company | None:
        row = self.store.find_company(query)
        if row is None:
            return None
        return Company(cik=row["cik"], ticker=row["ticker"], name=row["name"])

    async def resolve(self, query: str) -> Company:
        """Resolve against the SEC ticker list, falling back to companies already stored."""
        local = self.local_company(query)
        if local and not self.settings.contact_email:
            return local
        client, edgar = self._edgar()
        async with client:
            try:
                company = await edgar.resolve(query)
            except SecError:
                if local:
                    return local
                raise
        self.store.upsert_company(company.cik, company.ticker, company.name)
        return company

    def require_company(self, query: str) -> Company:
        company = self.local_company(query)
        if company is None:
            raise CompanyNotFoundError(
                f"No data for {query.upper()!r} yet. Download it first:  "
                f"form4clean fetch {query.upper()}"
            )
        return company

    # ------------------------------------------------------------ fetch

    async def fetch(
        self,
        query: str,
        *,
        start: date | None = None,
        end: date | None = None,
        progress: Progress | None = None,
    ) -> FetchSummary:
        client, edgar = self._edgar()
        async with client:
            company = await edgar.resolve(query)
            self.store.upsert_company(company.cik, company.ticker, company.name)
            summary = FetchSummary(company=company, start=start, end=end)
            refs = await edgar.ownership_filings(company.cik, start, end)
            summary.listed = len(refs)
            known = self.store.known_accessions()
            todo = [r for r in refs if r.accession_number not in known]
            summary.already_stored = len(refs) - len(todo)
            if progress:
                progress("download", 0, len(todo))
            semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
            done = 0

            async def one(ref: FilingRef) -> None:
                nonlocal done
                async with semaphore:
                    try:
                        data = await edgar.submission_text(company.cik, ref.accession_number)
                    except SecError as exc:
                        summary.download_errors.append((ref.accession_number, str(exc)))
                    else:
                        self._store_submission(company.cik, ref, data, summary)
                done += 1
                if progress:
                    progress("download", done, len(todo))

            await asyncio.gather(*(one(r) for r in todo))
            summary.requests = client.request_count
        summary.parse_errors.sort()
        summary.download_errors.sort()
        self.store.record_fetch(company.cik, start, end, summary.listed, summary.downloaded)
        return summary

    def _store_submission(
        self, cik: str, ref: FilingRef, data: bytes, summary: FetchSummary
    ) -> None:
        sub = parse_submission(data)
        doc = sub.ownership_document()
        parsed = None
        error = None
        if doc is None or doc.xml is None:
            error = (
                "No ownership XML in the submission. Filings before mid-2003 were not filed as XML."
            )
        else:
            try:
                parsed = parse_ownership_xml(
                    doc.xml,
                    accession_number=ref.accession_number,
                    form_type=sub.header.get("form_type") or ref.form_type,
                    header=sub.header,
                    source_document=doc.filename,
                )
            except OwnershipParseError as exc:
                error = str(exc)
        if error:
            summary.parse_errors.append((ref.accession_number, error))
        else:
            summary.downloaded += 1
        self.store.save_filing(
            ref=ref,
            fetched_for_cik=cik,
            parsed=parsed,
            header=sub.header,
            raw_xml=doc.xml if doc else None,
            error=error,
        )

    # ------------------------------------------------------------ clean and query

    def company_info(self, company: Company) -> CompanyInfo:
        return CompanyInfo(cik=pad_cik(company.cik), ticker=company.ticker, name=company.name)

    def clean(
        self, company: Company, options: CleanOptions | None = None, *, persist: bool | None = None
    ) -> CleanResult:
        options = options or CleanOptions()
        filings, failures = self.store.load_filings(pad_cik(company.cik))
        result = clean(filings, self.company_info(company), options, parse_failures=failures)
        if persist if persist is not None else (options == CleanOptions()):
            self.store.save_clean(pad_cik(company.cik), result)
        return result

    def transactions(
        self,
        company: Company,
        *,
        filters: TransactionFilter | None = None,
        as_of: datetime | None = None,
        reconcile: bool = True,
    ) -> tuple[pl.DataFrame, QualityReport | None]:
        """Cleaned records with filters applied. Current view unless as_of/reconcile change it."""
        filters = filters or TransactionFilter()
        cik = pad_cik(company.cik)
        if as_of is not None or not reconcile:
            result = self.clean(
                company, CleanOptions(reconcile_amendments=reconcile, as_of=as_of), persist=False
            )
            return filters.apply(to_frame(result.transactions)), result.report
        df = self.store.load_clean(cik)
        report = self.store.load_report(cik)
        if report is None or report.cleaning_version != CLEANING_VERSION:
            result = self.clean(company)
            df, report = to_frame(result.transactions), result.report
        return filters.apply(df), report

    def raw_transactions(self, company: Company) -> pl.DataFrame:
        return self.store.raw_transactions(pad_cik(company.cik))

    # ------------------------------------------------------------ prices

    async def prices(self, company: Company, start: date, end: date) -> PriceSeries:
        """Daily bars for the chart, cached locally. Never raises for provider problems:
        they come back as a series with status 'unavailable' or 'error' and a message."""
        symbol = company.ticker or ""
        try:
            provider = get_provider(self.settings)
        except PriceDataError as exc:
            return PriceSeries(symbol, self.settings.price_provider, "error", str(exc))
        problem = provider.configured()
        if problem or not symbol:
            return PriceSeries(
                symbol,
                provider.name,
                "unavailable",
                problem or f"{company.name} has no ticker to look up prices for.",
            )
        if provider.name != "csv":
            cached, fetched = self.store.load_prices(provider.name, symbol)
            fresh = fetched is not None and (datetime.now(UTC) - fetched) < PRICE_CACHE_TTL
            if (
                fresh
                and cached
                and cached[0]["date"] <= start + timedelta(days=7)
                and cached[-1]["date"] >= end - timedelta(days=4)
            ):
                bars = [Bar(**b) for b in cached if start <= b["date"] <= end]
                return PriceSeries(
                    symbol,
                    provider.name,
                    "ok",
                    provider.delayed_note,
                    adjusted=provider.adjusted,
                    bars=bars,
                    retrieved_at=fetched,
                )
        try:
            bars = await provider.daily_bars(symbol, start, end)
        except (PriceDataError, httpx.HTTPError) as exc:
            return PriceSeries(symbol, provider.name, "error", str(exc))
        if provider.name != "csv":
            self.store.save_prices(provider.name, symbol, [b.as_dict() for b in bars])
        status, message = (
            ("ok", provider.delayed_note)
            if bars
            else ("unavailable", f"{provider.label} returned no prices for {symbol} in this range.")
        )
        return PriceSeries(
            symbol,
            provider.name,
            status,
            message,
            adjusted=provider.adjusted,
            bars=bars,
            retrieved_at=datetime.now(UTC),
        )

    # ------------------------------------------------------------ exports

    def export_bundle(
        self,
        company: Company,
        out_dir: Path,
        fmt: Format,
        *,
        filters: TransactionFilter | None = None,
        as_of: datetime | None = None,
        reconcile: bool = True,
        include_raw: bool = True,
    ) -> tuple[DatasetManifest, Path]:
        filters = filters or TransactionFilter()
        df, report = self.transactions(company, filters=filters, as_of=as_of, reconcile=reconcile)
        stem = (company.ticker or company.cik).lower()
        suffix = f"_asof_{as_of.date().isoformat()}" if as_of else ""
        out_dir.mkdir(parents=True, exist_ok=True)
        files = []
        clean_path = write_frame(df, out_dir / f"{stem}_transactions{suffix}.{fmt}", fmt)
        files.append(manifest_file(clean_path, out_dir, "clean", fmt, df.height))
        if include_raw:
            raw = self.raw_transactions(company)
            raw_path = write_frame(raw, out_dir / f"{stem}_raw_transactions.{fmt}", fmt)
            files.append(manifest_file(raw_path, out_dir, "raw", fmt, raw.height))
        if report is not None:
            qpath = write_json(
                report.model_dump(mode="json"), out_dir / f"{stem}_quality_report{suffix}.json"
            )
            files.append(manifest_file(qpath, out_dir, "quality_report", "json", None))
        manifest = build_manifest(
            company={"cik": company.cik, "ticker": company.ticker, "name": company.name},
            clean=df,
            files=files,
            amendment_policy=amendment_policy(
                reconciled=reconcile, include_superseded=filters.include_superseded, as_of=as_of
            ),
            filters=filters.model_dump(mode="json", exclude_defaults=True),
            quality_summary=quality_summary(df),
        )
        manifest_path = write_json(
            manifest.model_dump(mode="json"), out_dir / f"{stem}_manifest{suffix}.json"
        )
        return manifest, manifest_path


def quality_summary(df: pl.DataFrame) -> dict[str, Any]:
    counts = dict.fromkeys(("VALID", "WARNING", "REVIEW_REQUIRED", "INVALID"), 0)
    if df.height:
        for row in df.group_by("quality_status").len().iter_rows():
            counts[row[0]] = row[1]
    return {
        "status_distribution": counts,
        "current_records": int(df.get_column("is_current").sum()) if df.height else 0,
    }
