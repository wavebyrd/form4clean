# SEC data sources

Form4Clean uses only official, public SEC EDGAR endpoints. It needs no SEC account or API
key, and it does not scrape third-party insider trading websites.

## Endpoints

| Purpose | Endpoint | Cached |
|---|---|---|
| Ticker to CIK | `https://www.sec.gov/files/company_tickers.json` | 24 hours |
| Filing history | `https://data.sec.gov/submissions/CIK##########.json`, plus the older pages it lists under `filings.files` | 6 hours (older pages permanently) |
| Filing content | `https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt` | Permanently |

The complete submission (`.txt`) contains the SGML header and every document in the filing,
including the ownership XML, so each filing needs exactly one request.

Filings never change after the SEC accepts them. Corrections arrive as new Form 4/A filings, so
downloaded filings are cached forever and a re-fetch only downloads filings that are new.
The cache and database live in `~/.form4clean` (or `FORM4CLEAN_HOME`).

## Fair access

The SEC publishes [rules for automated access](https://www.sec.gov/os/accessing-edgar-data).
Form4Clean follows them:

* **Identification.** Every request sends `User-Agent: Form4Clean you@example.com`. Form4Clean
  refuses to contact the SEC until you set a contact email; it never invents one.
* **Rate.** Requests are spaced to 5 per second by default (configurable, capped at the SEC's
  limit of 10).
* **Retries.** HTTP 429 and 5xx responses are retried with exponential backoff and jitter,
  honoring `Retry-After`, up to five times.
* **No retries on 403.** The SEC returns 403 to clients it has blocked or that do not identify
  themselves. Form4Clean stops and explains what to check rather than retrying.
* **Caching.** Nothing is downloaded twice.

## Acceptance timestamps

When a filing became public is the most important timestamp for research, and EDGAR offers it
in two places that disagree.

The submissions JSON lists `acceptanceDateTime` values with a `Z` (UTC) suffix. Comparing them
with the `<ACCEPTANCE-DATETIME>` line in each filing's own header (US Eastern time, EDGAR's
documented convention) shows the JSON value is the Eastern time shifted by **twice** the UTC
offset: 8 hours ahead during daylight saving time and 10 hours ahead in winter. For example:

| Filing | Header (Eastern) | Submissions JSON |
|---|---|---|
| 0002152188-26-000007 | 2026-10-13 17:09:29 | 2026-10-14T01:09:29.000Z |
| 2026-01-23 filing | 2026-01-23 17:06:26 | 2026-01-24T03:06:26.000Z |

Treating the JSON value as UTC would put after-close filings into the next trading day's
session by mistake. Form4Clean therefore reads the acceptance time from the filing header and
treats it as US Eastern. The JSON value is stored too (`acceptance_datetime_listed` in the
`filings` table) for reference. This was observed in October 2026; if the SEC fixes the JSON,
nothing in Form4Clean changes, because it never relies on it.

A filing accepted after 5:30 p.m. Eastern receives the next business day's filing date, so
`filing_date` can be later than the date of `filing_timestamp`. Both are kept.

## What is collected

Forms 4 and 4/A where the company is the issuer. The company's EDGAR history also lists
filings where it is itself a reporting owner (for example a 10% stake in another company).
Those are downloaded and stored with their own issuer CIK, so they never mix into the
company's dataset.

Filings from before mid-2003 were not filed as XML. They are reported as parse failures in the
quality report instead of being skipped silently.

The parser reads the `ownershipDocument` schema shared by Forms 3, 4 and 5. Adding Forms 3 and
5 needs their codes in `SUPPORTED_FORMS` (`sec/edgar.py`) and classification rules for their
holdings-only tables.

## Prices

Stock prices only draw the dashboard chart and never enter the insider dataset. The SEC does
not publish prices, so they come from a provider you choose (see
[dashboard.md](dashboard.md#price-data)). Form4Clean does not scrape TradingView or any other
site; TradingView Lightweight Charts is used only as a charting library.
