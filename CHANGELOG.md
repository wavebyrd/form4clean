# Changelog

## 0.1.0 (unreleased)

First release. Schema 1.0.0, cleaning rules 1.0.0.

- SEC EDGAR ingestion for Forms 4 and 4/A: ticker and CIK lookup, full filing history with
  date ranges, one request per filing, permanent cache, User-Agent with contact email, rate
  limiting, retries with backoff and `Retry-After`
- Acceptance timestamps read from each filing's header (US Eastern). The submissions JSON lists
  them shifted by twice the UTC offset; see docs/sec-data.md
- Ownership XML parser that keeps exact source strings, footnote links per field, holdings
  rows, multiple reporting owners, and parse warnings instead of failures
- Cleaning engine: exact decimal amounts, date and timestamp normalization, owner name and
  security title normalization, standardized roles, transaction values, stable transaction IDs,
  source values on every record, and a cleaning log of every change
- Classification for every Form 4 transaction code, with three-state open-market, discretionary
  and Rule 10b5-1 fields and a reason for each classification
- Conservative Form 4/A reconciliation with current, all-records, unreconciled and
  point-in-time views
- Quality engine with 39 documented checks, per-record status and explanations, and an
  aggregate quality report
- DuckDB storage; CSV, Parquet and JSON exports with a manifest and SHA-256 checksums;
  reproducible output
- Python API (`InsiderData`), Typer CLI, FastAPI HTTP API
- Local dashboard: overview, price chart with insider markers on the disclosure session,
  filters shared by chart and table, transaction table, data quality explorer, exports,
  settings, dark and light themes
- Price providers: Tiingo (free key), local CSV, none, and an optional Yahoo Finance provider
  (`form4clean[yfinance]` extra, never installed by default)
