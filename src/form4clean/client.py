"""Python API.

from form4clean import InsiderData

data = InsiderData("NVDA")
tx = data.transactions(start="2024-01-01", end="2026-01-01")
df = tx.to_pandas()
tx.to_parquet("nvda_insiders.parquet")
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator, Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import polars as pl

from .calendar import EASTERN
from .config import Settings, load_settings
from .exports.writer import (
    Format,
    amendment_policy,
    build_manifest,
    manifest_file,
    write_frame,
    write_json,
)
from .query import TransactionFilter
from .sec.edgar import Company
from .service import FetchSummary, Form4Service, Progress, quality_summary, years_ago
from .validation.report import QualityReport

if TYPE_CHECKING:
    import pandas as pd

DEFAULT_YEARS = 5
DateLike = str | date | datetime | None


def _date(value: DateLike, name: str) -> date | None:
    if value is None or (isinstance(value, date) and not isinstance(value, datetime)):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name}={value!r} is not a date in YYYY-MM-DD format") from exc


def parse_as_of(value: DateLike) -> datetime | None:
    """A bare date means the end of that day, US Eastern. Naive datetimes are Eastern."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=EASTERN)
    if isinstance(value, date):
        return datetime.combine(value, time(23, 59, 59, 999999), tzinfo=EASTERN)
    text = value.strip()
    if len(text) == 10:
        return parse_as_of(date.fromisoformat(text))
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"as_of={value!r} is not an ISO date or timestamp") from exc
    return parse_as_of(parsed)


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "InsiderData's methods are synchronous and cannot run inside an event loop "
        "(for example in Jupyter). Use `await data.afetch(...)` there, or call "
        "`nest_asyncio.apply()` first."
    )


class TransactionSet:
    """A filtered dataset with export helpers. ``kind`` is 'clean' or 'raw'."""

    def __init__(
        self,
        df: pl.DataFrame,
        *,
        kind: Literal["clean", "raw"],
        company: Company,
        report: QualityReport | None,
        policy: str,
        filters: TransactionFilter,
    ) -> None:
        self._df = df
        self.kind = kind
        self.company = company
        self.quality_report = report
        self.amendment_policy = policy
        self.filters = filters

    def __len__(self) -> int:
        return self._df.height

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._df.iter_rows(named=True))

    def __repr__(self) -> str:
        return (
            f"<TransactionSet {self.company.ticker or self.company.cik} {self.kind}: "
            f"{len(self)} records>"
        )

    def to_polars(self) -> pl.DataFrame:
        return self._df.clone()

    def to_pandas(self) -> pd.DataFrame:
        """Decimal columns become Python ``Decimal`` objects, keeping exact values."""
        return self._df.to_pandas()

    def to_dicts(self) -> list[dict[str, Any]]:
        return self._df.to_dicts()

    def _write(self, path: str | Path, fmt: Format, manifest: bool) -> Path:
        out = write_frame(self._df, Path(path), fmt)
        if manifest:
            m = build_manifest(
                company={
                    "cik": self.company.cik,
                    "ticker": self.company.ticker,
                    "name": self.company.name,
                },
                clean=self._df if self.kind == "clean" else _empty_dates(),
                files=[manifest_file(out, out.parent, self.kind, fmt, self._df.height)],
                amendment_policy=self.amendment_policy,
                filters=self.filters.model_dump(mode="json", exclude_defaults=True),
                quality_summary=quality_summary(self._df) if self.kind == "clean" else {},
            )
            m.record_count = self._df.height
            write_json(m.model_dump(mode="json"), out.with_name(out.stem + ".manifest.json"))
        return out

    def to_parquet(self, path: str | Path, *, manifest: bool = True) -> Path:
        return self._write(path, "parquet", manifest)

    def to_csv(self, path: str | Path, *, manifest: bool = True) -> Path:
        return self._write(path, "csv", manifest)

    def to_json(self, path: str | Path, *, manifest: bool = True) -> Path:
        return self._write(path, "json", manifest)


def _empty_dates() -> pl.DataFrame:
    return pl.DataFrame(schema={"filing_date": pl.Date})


class InsiderData:
    """Insider transactions for one company, by ticker or CIK.

    Data is downloaded from SEC EDGAR on first use and stored locally; later calls read the
    local copy and only download filings that are new.
    """

    def __init__(
        self,
        company: str,
        *,
        settings: Settings | None = None,
        email: str | None = None,
        auto_fetch: bool = True,
        service: Form4Service | None = None,
    ) -> None:
        self.query = company
        self.service = service or Form4Service(settings or load_settings(contact_email=email))
        self.auto_fetch = auto_fetch
        self._company: Company | None = None

    @property
    def company(self) -> Company:
        if self._company is None:
            local = self.service.local_company(self.query)
            self._company = local or _run(self.service.resolve(self.query))
        return self._company

    async def afetch(
        self,
        start: DateLike = None,
        end: DateLike = None,
        *,
        years: float | None = None,
        progress: Progress | None = None,
    ) -> FetchSummary:
        s = _date(start, "start") or years_ago(years or DEFAULT_YEARS)
        summary = await self.service.fetch(
            self.query, start=s, end=_date(end, "end"), progress=progress
        )
        self._company = summary.company
        self.service.clean(summary.company)
        return summary

    def fetch(
        self,
        start: DateLike = None,
        end: DateLike = None,
        *,
        years: float | None = None,
        progress: Progress | None = None,
    ) -> FetchSummary:
        """Download Forms 4 and 4/A (default: last five years) and rebuild the clean dataset."""
        return _run(self.afetch(start, end, years=years, progress=progress))

    def _ensure(self, start: date | None) -> None:
        """Download what is missing: everything on first use, older history when ``start``
        reaches back further than what is stored, and new filings when the local copy is stale.
        """
        if not self.auto_fetch:
            return
        local = self.service.local_company(self.query)
        if local is None:
            self.fetch(start=start)
            return
        earliest, last = self.service.store.coverage(local.cik)
        if earliest is None or last is None:
            self.fetch(start=start)
            return
        if start is not None and start < earliest:
            self.fetch(start=start)
            return
        age = (datetime.now(UTC) - last).total_seconds()
        if age > self.service.settings.submissions_ttl_hours * 3600:
            # Incremental: only filings not already stored are downloaded.
            self.fetch(start=earliest)

    def transactions(
        self,
        start: DateLike = None,
        end: DateLike = None,
        *,
        clean: bool = True,
        reconcile_amendments: bool = True,
        as_of: DateLike = None,
        transaction_types: Sequence[str] = (),
        codes: Sequence[str] = (),
        insiders: Sequence[str] = (),
        roles: Sequence[str] = (),
        direction: Literal["ACQUISITION", "DISPOSITION"] | None = None,
        min_value: float | int | str | Decimal | None = None,
        max_value: float | int | str | Decimal | None = None,
        quality: Sequence[str] = (),
        include_superseded: bool = False,
        date_field: Literal["transaction", "disclosure", "filing"] = "transaction",
    ) -> TransactionSet:
        """Insider transactions.

        ``clean=False`` returns the raw parsed rows (source strings, no reconciliation); only
        ``start`` and ``end`` apply to it. ``as_of`` returns the point-in-time view: only
        filings public by then, reconciled with the amendments public by then.
        ``transaction_types`` are categories such as "Market Purchase".
        """
        s, e = _date(start, "start"), _date(end, "end")
        self._ensure(s)
        company = self.company
        filters = TransactionFilter(
            start=s,
            end=e,
            date_field=date_field,
            categories=list(transaction_types),
            codes=list(codes),
            insiders=list(insiders),
            roles=list(roles),
            direction=direction,
            min_value=Decimal(str(min_value)) if min_value is not None else None,
            max_value=Decimal(str(max_value)) if max_value is not None else None,
            quality_statuses=list(quality),
            include_superseded=include_superseded,
        )
        cutoff = parse_as_of(as_of)
        if not clean:
            raw = self.service.raw_transactions(company)
            if s:
                raw = raw.filter(pl.col("transaction_date").str.slice(0, 10) >= s.isoformat())
            if e:
                raw = raw.filter(pl.col("transaction_date").str.slice(0, 10) <= e.isoformat())
            return TransactionSet(
                raw,
                kind="raw",
                company=company,
                report=None,
                policy="raw: parsed source rows, no cleaning or reconciliation",
                filters=TransactionFilter(start=s, end=e),
            )
        df, report = self.service.transactions(
            company, filters=filters, as_of=cutoff, reconcile=reconcile_amendments
        )
        policy = amendment_policy(
            reconciled=reconcile_amendments, include_superseded=include_superseded, as_of=cutoff
        )
        return TransactionSet(
            df, kind="clean", company=company, report=report, policy=policy, filters=filters
        )

    def quality_report(self) -> QualityReport | None:
        return self.service.transactions(self.company)[1]
