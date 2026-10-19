# Architecture

```
            SEC EDGAR (public endpoints)
                       │  rate-limited, retried, cached
                       ▼
 sec/          client.py  edgar.py  cache.py        ticker → CIK, filing list, .txt downloads
                       │
                       ▼
 parsing/      submission.py  ownership.py          SGML header + ownership XML → ParsedFiling
                       │                             (exact source strings, nothing converted)
                       ▼
 storage/      store.py (DuckDB)                     raw XML, parsed filings, raw rows
                       │
                       ▼
 cleaning/     pipeline.py ─┬─ records.py            one source row → one standardized record
                            ├─ normalize.py          numbers, dates, names, titles, roles
 classification/            ├─ classify.py, codes.py  SEC code taxonomy, 10b5-1, market, discretion
 amendments/                ├─ reconcile.py          4/A linking and record-level matching
 validation/                └─ flags.py, report.py   quality flags and the aggregate report
                       │
                       ▼
 storage/      store.py (DuckDB)                     clean records, cleaning log, links, reports
                       │
          ┌────────────┼──────────────┬───────────────────┐
          ▼            ▼              ▼                   ▼
 client.py        cli.py        api/app.py           exports/writer.py
 Python API       Typer CLI     FastAPI + dashboard   CSV · Parquet · JSON + manifest
                                       │
                                       ▼
                              frontend/ (React, built into api/static)
```

## Layers

**Ingestion (`sec/`).** `SecClient` is the only thing that talks to the network. It owns the
User-Agent, the rate limiter and retries. `Edgar` adds the endpoints and the disk cache.

**Parsing (`parsing/`).** Produces `ParsedFiling` models (`models/raw.py`) holding the exact
strings from the document. Parsing never raises on odd content; it records `parse_warnings`.
XML is parsed with `defusedxml`.

**Cleaning (`cleaning/`, `classification/`, `amendments/`, `validation/`).** A pure function:
`clean(filings, company, options) -> CleanResult`. No I/O, no clock, no randomness, so the same
input and `CLEANING_VERSION` always give the same output. Point-in-time views are produced by
running it on the subset of filings that were public at the cutoff.

**Storage (`storage/`).** DuckDB, one file. Connections are short-lived so the CLI and the
dashboard can share the database. Tables: `companies`, `filings` (raw XML, header, parsed JSON),
`raw_transactions`, `clean_transactions`, `cleaning_log`, `amendment_links`, `quality_reports`,
`fetch_log`, `price_bars`.

**Interfaces.** `service.py` holds every workflow (fetch, clean, query, export, prices). The
Python API (`client.py`), the CLI (`cli.py`) and the HTTP API (`api/app.py`) are thin layers
over it, and all three filter with the same `TransactionFilter` (`query.py`), so the dashboard
chart, its table and every export agree.

**Market data (`market_data/`).** A small provider interface (`PriceProvider`) with Tiingo,
local CSV, "none" and an optional Yahoo Finance provider (the `yfinance` extra, imported only
when chosen). Prices are cached in DuckDB and never touch the insider dataset.

**Dashboard (`frontend/`).** React, TypeScript, Vite, Tailwind CSS, shadcn/ui-style components
(Radix primitives), TanStack Query and Table, TradingView Lightweight Charts and Lucide icons.
`npm run build` writes into `src/form4clean/api/static`, which ships in the Python package so
users do not need Node.

## Design rules

* **Never drop, never invent.** Every source row becomes a record. A value that cannot be read
  becomes null with a flag; nothing is estimated.
* **Exact money.** `Decimal` in Python, `DECIMAL` in DuckDB and Parquet, decimal strings in JSON
  and CSV. Floats are used only for chart prices.
* **Provenance.** Every record carries its accession number, SEC link, source document, source
  position and original strings (`source_values`), and every change is in the cleaning log.
* **Determinism.** Stable IDs (hash of the source position), deterministic sort order and
  versioned rules (`SCHEMA_VERSION`, `CLEANING_VERSION`).
* **Conservatism.** When a link or classification is uncertain, the record is kept and flagged,
  and the uncertain choice is not applied to the current view.
