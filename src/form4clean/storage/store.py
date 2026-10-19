"""DuckDB storage for filings, parsed rows, cleaned datasets and their audit trail.

Connections are opened per operation and closed right away, so the CLI and the dashboard can
share one database file. DuckDB allows one writer process at a time; a second writer gets a
clear error instead of corrupting anything.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from ..cleaning.pipeline import CleanResult
from ..models.raw import FilingRef, ParsedFiling
from ..models.schema import CLEAN_SCHEMA, RAW_SCHEMA, empty_clean, raw_frame, to_frame
from ..validation.report import QualityReport

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    cik VARCHAR PRIMARY KEY,
    ticker VARCHAR,
    name VARCHAR,
    updated_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS filings (
    accession_number VARCHAR PRIMARY KEY,
    fetched_for_cik VARCHAR,
    issuer_cik VARCHAR,
    form_type VARCHAR,
    filing_date DATE,
    acceptance_datetime VARCHAR,
    acceptance_datetime_listed VARCHAR,
    primary_document VARCHAR,
    sec_filing_url VARCHAR,
    parse_status VARCHAR,
    parse_error VARCHAR,
    raw_header JSON,
    raw_xml VARCHAR,
    parsed JSON,
    fetched_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS fetch_log (
    company_cik VARCHAR,
    start_date DATE,
    end_date DATE,
    filings_listed INTEGER,
    filings_downloaded INTEGER,
    fetched_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS cleaning_log (
    company_cik VARCHAR,
    accession_number VARCHAR,
    transaction_id VARCHAR,
    step VARCHAR,
    field VARCHAR,
    rule VARCHAR,
    before VARCHAR,
    after VARCHAR
);
CREATE TABLE IF NOT EXISTS amendment_links (
    company_cik VARCHAR,
    amendment_accession VARCHAR,
    original_accession VARCHAR,
    status VARCHAR,
    confidence VARCHAR,
    reason VARCHAR,
    candidates VARCHAR[]
);
CREATE TABLE IF NOT EXISTS quality_reports (
    company_cik VARCHAR PRIMARY KEY,
    cleaning_version VARCHAR,
    generated_at TIMESTAMPTZ,
    report JSON
);
CREATE TABLE IF NOT EXISTS price_bars (
    provider VARCHAR,
    symbol VARCHAR,
    date DATE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    fetched_at TIMESTAMPTZ,
    PRIMARY KEY (provider, symbol, date)
);
"""


class StoreError(Exception):
    pass


def _ddl(table: str, schema: dict[str, pl.DataType], extra: str = "") -> str:
    cols = [extra] if extra else []
    cols += [f'"{name}" {_duck_type(dtype)}' for name, dtype in schema.items()]
    return f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols)});"


def _duck_type(dtype: Any) -> str:
    if isinstance(dtype, pl.Decimal):
        return f"DECIMAL({dtype.precision}, {dtype.scale})"
    if isinstance(dtype, pl.Datetime):
        return "TIMESTAMPTZ"
    if isinstance(dtype, pl.List):
        return f"{_duck_type(dtype.inner)}[]"
    if isinstance(dtype, pl.Struct):
        inner = ", ".join(f'"{f.name}" {_duck_type(f.dtype)}' for f in dtype.fields)
        return f"STRUCT({inner})"
    mapping = {
        pl.String: "VARCHAR",
        pl.Int32: "INTEGER",
        pl.Int64: "BIGINT",
        pl.Boolean: "BOOLEAN",
        pl.Date: "DATE",
        pl.Float64: "DOUBLE",
    }
    for pl_type, duck in mapping.items():
        if dtype == pl_type:
            return duck
    raise TypeError(f"no DuckDB type for {dtype}")


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute(SCHEMA_SQL)
            con.execute(_ddl("clean_transactions", CLEAN_SCHEMA))
            con.execute(_ddl("raw_transactions", RAW_SCHEMA))

    @contextmanager
    def connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        try:
            con = duckdb.connect(str(self.path))
        except duckdb.IOException as exc:
            raise StoreError(
                f"Could not open {self.path}: {exc}. Another Form4Clean process may be writing "
                "to it; wait for it to finish and try again."
            ) from exc
        try:
            con.execute("SET TimeZone = 'America/New_York'")
            yield con
        finally:
            con.close()

    # ------------------------------------------------------------ companies

    def upsert_company(self, cik: str, ticker: str | None, name: str | None) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO companies VALUES (?, ?, ?, ?)",
                [cik, ticker, name, datetime.now(UTC)],
            )

    def companies(self) -> list[dict[str, Any]]:
        sql = """
            SELECT c.cik, c.ticker, c.name, c.updated_at,
                   (SELECT count(*) FROM filings f WHERE f.issuer_cik = c.cik) AS filings,
                   (SELECT count(*) FROM clean_transactions t WHERE t.company_cik = c.cik)
                       AS transactions,
                   (SELECT max(fetched_at) FROM fetch_log l WHERE l.company_cik = c.cik)
                       AS last_fetched
            FROM companies c ORDER BY c.ticker NULLS LAST, c.cik
        """
        with self.connect() as con:
            rows = con.execute(sql).fetchall()
            cols = [d[0] for d in con.description or []]
        return [dict(zip(cols, row, strict=True)) for row in rows]

    def company(self, cik: str) -> dict[str, Any] | None:
        return next((c for c in self.companies() if c["cik"] == cik), None)

    def find_company(self, query: str) -> dict[str, Any] | None:
        q = query.strip().upper()
        digits = q.removeprefix("CIK")
        for c in self.companies():
            if (c["ticker"] or "").upper() == q or (
                digits.isdigit() and c["cik"] == digits.zfill(10)
            ):
                return c
        return None

    # ------------------------------------------------------------ filings

    def known_accessions(self) -> set[str]:
        with self.connect() as con:
            return {
                r[0]
                for r in con.execute(
                    "SELECT accession_number FROM filings WHERE parse_status = 'ok'"
                ).fetchall()
            }

    def save_filing(
        self,
        *,
        ref: FilingRef,
        fetched_for_cik: str,
        parsed: ParsedFiling | None,
        header: dict[str, str] | None,
        raw_xml: str | None,
        error: str | None,
    ) -> None:
        issuer = None
        if parsed and parsed.issuer_cik and parsed.issuer_cik.strip().isdigit():
            issuer = parsed.issuer_cik.strip().zfill(10)
        row = [
            ref.accession_number,
            fetched_for_cik,
            issuer,
            ref.form_type,
            ref.filing_date,
            parsed.acceptance_datetime if parsed else (header or {}).get("acceptance_datetime"),
            ref.acceptance_datetime_listed,
            ref.primary_document,
            parsed.sec_filing_url if parsed else None,
            "ok" if parsed else "error",
            error,
            json.dumps(header or {}),
            raw_xml,
            parsed.model_dump_json() if parsed else None,
            datetime.now(UTC),
        ]
        with self.connect() as con:
            con.execute("BEGIN")
            con.execute(
                "INSERT OR REPLACE INTO filings VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            con.execute(
                "DELETE FROM raw_transactions WHERE accession_number = ?", [ref.accession_number]
            )
            if parsed and parsed.transactions:
                df = raw_frame(raw_rows(parsed))
                con.register("incoming", df.to_arrow())
                con.execute("INSERT INTO raw_transactions SELECT * FROM incoming")
                con.unregister("incoming")
            con.execute("COMMIT")

    def load_filings(self, issuer_cik: str) -> tuple[list[ParsedFiling], list[tuple[str, str]]]:
        with self.connect() as con:
            ok = con.execute(
                "SELECT parsed FROM filings WHERE issuer_cik = ? AND parse_status = 'ok' "
                "ORDER BY accession_number",
                [issuer_cik],
            ).fetchall()
            failed = con.execute(
                "SELECT accession_number, parse_error FROM filings "
                "WHERE fetched_for_cik = ? AND parse_status = 'error' ORDER BY accession_number",
                [issuer_cik],
            ).fetchall()
        filings = [ParsedFiling.model_validate_json(row[0]) for row in ok]
        return filings, [(a, e or "") for a, e in failed]

    def raw_xml(self, accession: str) -> str | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT raw_xml FROM filings WHERE accession_number = ?", [accession]
            ).fetchone()
        return row[0] if row else None

    def raw_transactions(self, issuer_cik: str) -> pl.DataFrame:
        with self.connect() as con:
            df = con.execute(
                "SELECT * FROM raw_transactions WHERE issuer_cik = ? "
                'ORDER BY acceptance_datetime, accession_number, "table" DESC, sequence',
                [issuer_cik],
            ).pl()
        return df.cast(RAW_SCHEMA) if df.height else pl.DataFrame(schema=RAW_SCHEMA)  # type: ignore[arg-type]

    # ------------------------------------------------------------ fetch log

    def record_fetch(
        self, cik: str, start: date | None, end: date | None, listed: int, downloaded: int
    ) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT INTO fetch_log VALUES (?, ?, ?, ?, ?, ?)",
                [cik, start, end, listed, downloaded, datetime.now(UTC)],
            )

    def coverage(self, cik: str) -> tuple[date | None, datetime | None]:
        """Earliest start date fetched (None = full history) and the latest fetch time."""
        with self.connect() as con:
            row = con.execute(
                "SELECT bool_or(start_date IS NULL), min(start_date), max(fetched_at), count(*) "
                "FROM fetch_log WHERE company_cik = ?",
                [cik],
            ).fetchone()
        if not row or row[3] == 0:
            return None, None
        full_history, earliest, last = row[0], row[1], row[2]
        return (date.min if full_history else earliest), last

    # ------------------------------------------------------------ cleaned data

    def save_clean(self, cik: str, result: CleanResult) -> None:
        df = to_frame(result.transactions)
        log = pl.DataFrame(
            [{"company_cik": cik, **asdict(d)} for d in result.decisions],
            schema={
                "company_cik": pl.String,
                "accession_number": pl.String,
                "transaction_id": pl.String,
                "step": pl.String,
                "field": pl.String,
                "rule": pl.String,
                "before": pl.String,
                "after": pl.String,
            },
            orient="row",
        )
        links = pl.DataFrame(
            [
                {
                    "company_cik": cik,
                    "amendment_accession": link.amendment_accession,
                    "original_accession": link.original_accession,
                    "status": link.status,
                    "confidence": str(link.confidence) if link.confidence else None,
                    "reason": link.reason,
                    "candidates": link.candidates,
                }
                for link in result.amendment_links
            ],
            schema={
                "company_cik": pl.String,
                "amendment_accession": pl.String,
                "original_accession": pl.String,
                "status": pl.String,
                "confidence": pl.String,
                "reason": pl.String,
                "candidates": pl.List(pl.String),
            },
            orient="row",
        )
        with self.connect() as con:
            con.execute("BEGIN")
            for table in ("clean_transactions", "cleaning_log", "amendment_links"):
                con.execute(f"DELETE FROM {table} WHERE company_cik = ?", [cik])
            for table, frame in (
                ("clean_transactions", df),
                ("cleaning_log", log),
                ("amendment_links", links),
            ):
                if frame.height:
                    con.register("incoming", frame.to_arrow())
                    con.execute(f"INSERT INTO {table} SELECT * FROM incoming")
                    con.unregister("incoming")
            con.execute(
                "INSERT OR REPLACE INTO quality_reports VALUES (?, ?, ?, ?)",
                [
                    cik,
                    result.report.cleaning_version,
                    datetime.now(UTC),
                    result.report.model_dump_json(),
                ],
            )
            con.execute("COMMIT")

    def load_clean(self, cik: str) -> pl.DataFrame:
        with self.connect() as con:
            df = con.execute(
                "SELECT * FROM clean_transactions WHERE company_cik = ? "
                "ORDER BY filing_timestamp, accession_number, transaction_table DESC, sequence",
                [cik],
            ).pl()
        if df.height == 0:
            return empty_clean()
        return df.cast(CLEAN_SCHEMA)  # type: ignore[arg-type]

    def load_report(self, cik: str) -> QualityReport | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT report FROM quality_reports WHERE company_cik = ?", [cik]
            ).fetchone()
        return QualityReport.model_validate_json(row[0]) if row else None

    def cleaning_log(self, cik: str, transaction_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * EXCLUDE (company_cik) FROM cleaning_log WHERE company_cik = ?"
        params: list[Any] = [cik]
        if transaction_id:
            sql += " AND transaction_id = ?"
            params.append(transaction_id)
        with self.connect() as con:
            rows = con.execute(sql, params).fetchall()
            cols = [d[0] for d in con.description or []]
        return [dict(zip(cols, r, strict=True)) for r in rows]

    def amendment_links(self, cik: str) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * EXCLUDE (company_cik) FROM amendment_links WHERE company_cik = ? "
                "ORDER BY amendment_accession",
                [cik],
            ).fetchall()
            cols = [d[0] for d in con.description or []]
        return [dict(zip(cols, r, strict=True)) for r in rows]

    # ------------------------------------------------------------ prices

    def save_prices(self, provider: str, symbol: str, bars: Sequence[dict[str, Any]]) -> None:
        if not bars:
            return
        now = datetime.now(UTC)
        rows = [
            [
                provider,
                symbol,
                b["date"],
                b["open"],
                b["high"],
                b["low"],
                b["close"],
                b.get("volume"),
                now,
            ]
            for b in bars
        ]
        with self.connect() as con:
            con.executemany(
                "INSERT OR REPLACE INTO price_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
            )

    def load_prices(
        self, provider: str, symbol: str
    ) -> tuple[list[dict[str, Any]], datetime | None]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT date, open, high, low, close, volume, fetched_at FROM price_bars "
                "WHERE provider = ? AND symbol = ? ORDER BY date",
                [provider, symbol],
            ).fetchall()
        bars = [
            {"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
            for r in rows
        ]
        fetched = max((r[6] for r in rows), default=None)
        return bars, fetched


def raw_rows(filing: ParsedFiling) -> list[dict[str, Any]]:
    owners = filing.reporting_owners
    rows = []
    for tx in filing.transactions:
        rows.append(
            {
                "source_transaction_id": f"{filing.accession_number}:"
                f"{'ND' if tx.table == 'non_derivative' else 'D'}:{tx.sequence}",
                "accession_number": filing.accession_number,
                "form_type": filing.form_type,
                "filing_date": filing.filing_date,
                "acceptance_datetime": filing.acceptance_datetime,
                "issuer_cik": (filing.issuer_cik or "").strip().zfill(10) or None,
                "issuer_name": filing.issuer_name,
                "issuer_trading_symbol": filing.issuer_trading_symbol,
                "reporting_owner_ciks": "; ".join(o.cik or "" for o in owners),
                "reporting_owner_names": "; ".join(o.name or "" for o in owners),
                "table": tx.table,
                "sequence": tx.sequence,
                "security_title": tx.security_title,
                "transaction_date": tx.transaction_date,
                "deemed_execution_date": tx.deemed_execution_date,
                "transaction_code": tx.transaction_code,
                "equity_swap_involved": tx.equity_swap_involved,
                "shares": tx.shares,
                "total_value": tx.total_value,
                "price_per_share": tx.price_per_share,
                "acquired_disposed_code": tx.acquired_disposed_code,
                "shares_owned_after": tx.shares_owned_after,
                "value_owned_after": tx.value_owned_after,
                "direct_or_indirect": tx.direct_or_indirect,
                "nature_of_ownership": tx.nature_of_ownership,
                "conversion_or_exercise_price": tx.conversion_or_exercise_price,
                "exercise_date": tx.exercise_date,
                "expiration_date": tx.expiration_date,
                "underlying_security_title": tx.underlying_security_title,
                "underlying_shares": tx.underlying_shares,
                "aff_10b5_one": filing.aff_10b5_one,
                "footnote_ids": json.dumps(tx.footnote_ids, sort_keys=True)
                if tx.footnote_ids
                else None,
                "sec_filing_url": filing.sec_filing_url,
            }
        )
    return rows
