"""EDGAR endpoints: ticker resolution, submissions history, and filing documents.

Endpoints used (all public, documented at https://www.sec.gov/edgar/sec-api-documentation):

* https://www.sec.gov/files/company_tickers.json for ticker to CIK.
* https://data.sec.gov/submissions/CIK##########.json for a company's filing history, plus the
  older pages it lists under ``filings.files``.
* https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt for the complete submission:
  the SGML header (with the authoritative acceptance timestamp) and the ownership XML.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from ..models.raw import FilingRef
from .cache import FileCache
from .client import SecClient, SecNotFoundError

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVE_ROOT = "https://www.sec.gov/Archives/edgar/data"

# Ownership forms this version processes. The parser handles any ownershipDocument; adding
# Forms 3 and 5 means adding them here and to the classification rules.
SUPPORTED_FORMS = frozenset({"4", "4/A"})

DAY = 24 * 3600


class CompanyNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class Company:
    cik: str
    ticker: str | None
    name: str


def pad_cik(cik: str | int) -> str:
    digits = str(cik).strip().lstrip("CIKcik").strip()
    if not digits.isdigit():
        raise ValueError(f"{cik!r} is not a CIK")
    return digits.zfill(10)


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-").replace("/", "-")


def filing_index_url(cik: str, accession: str) -> str:
    return f"{ARCHIVE_ROOT}/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm"


def submission_text_url(cik: str, accession: str) -> str:
    return f"{ARCHIVE_ROOT}/{int(cik)}/{accession.replace('-', '')}/{accession}.txt"


class Edgar:
    """Cached access to EDGAR. All network calls go through one rate-limited SecClient."""

    def __init__(self, client: SecClient, cache: FileCache, submissions_ttl_hours: float) -> None:
        self.client = client
        self.cache = cache
        self.submissions_ttl = submissions_ttl_hours * 3600
        self.downloaded = 0
        self.cache_hits = 0

    async def _cached(self, key: str, url: str, ttl: float | None) -> bytes:
        data = self.cache.get(key, ttl)
        if data is not None:
            self.cache_hits += 1
            return data
        data = await self.client.get_bytes(url)
        self.downloaded += 1
        self.cache.put(key, data)
        return data

    async def ticker_table(self) -> list[Company]:
        raw = json.loads(await self._cached("company_tickers.json", TICKERS_URL, DAY))
        return [
            Company(cik=pad_cik(row["cik_str"]), ticker=row["ticker"].upper(), name=row["title"])
            for row in raw.values()
        ]

    async def resolve(self, query: str) -> Company:
        """Resolve a ticker or CIK to a Company."""
        query = query.strip()
        if not query:
            raise CompanyNotFoundError("Enter a ticker (e.g. NVDA) or a CIK (e.g. 1045810).")
        companies = await self.ticker_table()
        if query.upper().removeprefix("CIK").isdigit():
            cik = pad_cik(query)
            for company in companies:
                if company.cik == cik:
                    return company
            data = await self.submissions(cik)
            tickers = data.get("tickers") or []
            return Company(cik=cik, ticker=tickers[0] if tickers else None, name=data["name"])
        wanted = normalize_ticker(query)
        for company in companies:
            if company.ticker and normalize_ticker(company.ticker) == wanted:
                return company
        raise CompanyNotFoundError(
            f"No SEC-registered company has the ticker {query.upper()!r}. Check the symbol, or "
            "use the company's CIK (search at https://www.sec.gov/edgar/searchedgar/companysearch)."
        )

    async def submissions(self, cik: str) -> dict[str, Any]:
        name = f"CIK{pad_cik(cik)}.json"
        try:
            data = await self._cached(
                f"submissions/{name}", SUBMISSIONS_URL.format(name=name), self.submissions_ttl
            )
        except SecNotFoundError as exc:
            raise CompanyNotFoundError(f"SEC has no filing history for CIK {cik}.") from exc
        result: dict[str, Any] = json.loads(data)
        return result

    async def ownership_filings(
        self, cik: str, start: date | None = None, end: date | None = None
    ) -> list[FilingRef]:
        """Forms 4 and 4/A in the company's history with filing dates in [start, end]."""
        data = await self.submissions(cik)
        pages: list[dict[str, Any]] = [data["filings"]["recent"]]
        for extra in data["filings"].get("files", []):
            page_from = date.fromisoformat(extra["filingFrom"])
            page_to = date.fromisoformat(extra["filingTo"])
            if (start and page_to < start) or (end and page_from > end):
                continue
            # Older pages never change once written, so cache them permanently.
            raw = await self._cached(
                f"submissions/{extra['name']}",
                SUBMISSIONS_URL.format(name=extra["name"]),
                None,
            )
            pages.append(json.loads(raw))
        refs: dict[str, FilingRef] = {}
        for page in pages:
            for i, form in enumerate(page["form"]):
                if form not in SUPPORTED_FORMS:
                    continue
                filed = date.fromisoformat(page["filingDate"][i])
                if (start and filed < start) or (end and filed > end):
                    continue
                acc = page["accessionNumber"][i]
                refs[acc] = FilingRef(
                    accession_number=acc,
                    form_type=form,
                    filing_date=filed,
                    report_date=page.get("reportDate", [None] * len(page["form"]))[i] or None,
                    acceptance_datetime_listed=page["acceptanceDateTime"][i],
                    primary_document=page["primaryDocument"][i],
                )
        return sorted(refs.values(), key=lambda r: (r.filing_date, r.accession_number))

    async def submission_text(self, cik: str, accession: str) -> bytes:
        key = f"filings/{pad_cik(cik)}/{accession}.txt"
        return await self._cached(key, submission_text_url(cik, accession), None)
