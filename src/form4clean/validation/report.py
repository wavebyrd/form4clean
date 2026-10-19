"""Aggregate data quality report for one cleaned dataset.

The report contains no timestamps of its own, so it is identical whenever the source data and
cleaning version are the same. Generation time lives in the export manifest.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from ..models.enums import AmendmentStatus, Category, QualityStatus
from ..models.raw import ParsedFiling
from ..models.transaction import InsiderTransaction
from ..versions import CLEANING_VERSION, SCHEMA_VERSION
from .flags import FLAGS

if TYPE_CHECKING:
    from ..amendments.reconcile import AmendmentLink
    from ..cleaning.records import CompanyInfo

# Fields whose missing values are counted in the report.
TRACKED_FIELDS = (
    "insider_cik",
    "transaction_date",
    "filing_timestamp",
    "transaction_code",
    "shares",
    "price_per_share",
    "transaction_value",
    "shares_owned_after",
    "security_title",
    "ownership_type",
    "acquired_disposed_code",
    "is_market_transaction",
    "is_discretionary_trade",
    "is_10b5_1",
)


class IssueSummary(BaseModel):
    code: str
    severity: str
    title: str
    why: str
    action: str
    review_recommended: bool
    count: int


class AmendmentSummary(BaseModel):
    amendment_filings: int
    linked: int
    original_not_found: int
    ambiguous: int
    records_superseded: int
    records_corrected: int
    records_restated: int
    records_added: int
    records_ambiguous: int


class QualityReport(BaseModel):
    company_cik: str
    ticker: str | None
    schema_version: str = SCHEMA_VERSION
    cleaning_version: str = CLEANING_VERSION
    as_of: datetime | None
    amendments_reconciled: bool
    filings_processed: int
    filings_failed: int
    parse_failures: list[dict[str, str]]
    duplicate_filings_ignored: int
    holdings_reported: int
    filing_date_range: tuple[str | None, str | None]
    transactions_extracted: int
    transactions_classified: int
    classification_coverage: float
    current_transactions: int
    duplicates_detected: int
    amendments: AmendmentSummary
    records_requiring_review: int
    status_distribution: dict[str, int]
    category_distribution: dict[str, int]
    missing_values: dict[str, int]
    issues: list[IssueSummary]


def build_report(
    *,
    company: CompanyInfo,
    filings: Sequence[ParsedFiling],
    records: Sequence[InsiderTransaction],
    links: Sequence[AmendmentLink],
    duplicate_filings: int,
    parse_failures: Sequence[tuple[str, str]],
    options_as_of: datetime | None,
    reconciled: bool,
) -> QualityReport:
    total = len(records)
    classified = sum(1 for r in records if r.transaction_category != Category.UNKNOWN)
    statuses = Counter(str(r.quality_status) for r in records)
    flags = Counter(code for r in records for code in r.quality_flags)
    amend = Counter(str(r.amendment_status) for r in records)
    link_status = Counter(link.status for link in links)
    dates = sorted(f.filing_date for f in filings if f.filing_date)
    dup_codes = ("POSSIBLE_DUPLICATE_IN_FILING", "POSSIBLE_DUPLICATE_ACROSS_FILINGS")
    issues = [
        IssueSummary(
            code=code,
            severity=str(FLAGS[code].severity),
            title=FLAGS[code].title,
            why=FLAGS[code].why,
            action=FLAGS[code].action,
            review_recommended=FLAGS[code].review,
            count=count,
        )
        for code, count in sorted(flags.items(), key=lambda kv: (-_rank(kv[0]), kv[0]))
    ]
    return QualityReport(
        company_cik=company.cik,
        ticker=company.ticker,
        as_of=options_as_of,
        amendments_reconciled=reconciled,
        filings_processed=len(filings),
        filings_failed=len(parse_failures),
        parse_failures=[{"accession_number": a, "error": e} for a, e in parse_failures],
        duplicate_filings_ignored=duplicate_filings,
        holdings_reported=sum(len(f.holdings) for f in filings),
        filing_date_range=(_iso(dates[0]) if dates else None, _iso(dates[-1]) if dates else None),
        transactions_extracted=total,
        transactions_classified=classified,
        classification_coverage=round(classified / total, 4) if total else 1.0,
        current_transactions=sum(1 for r in records if r.is_current),
        duplicates_detected=sum(1 for r in records if any(c in r.quality_flags for c in dup_codes)),
        amendments=AmendmentSummary(
            amendment_filings=len(links),
            linked=link_status.get("LINKED", 0),
            original_not_found=link_status.get("ORIGINAL_NOT_FOUND", 0),
            ambiguous=link_status.get("AMBIGUOUS", 0),
            records_superseded=amend.get(AmendmentStatus.SUPERSEDED, 0),
            records_corrected=amend.get(AmendmentStatus.AMENDED_CORRECTED, 0),
            records_restated=amend.get(AmendmentStatus.AMENDED_RESTATED, 0),
            records_added=amend.get(AmendmentStatus.AMENDED_ADDED, 0),
            records_ambiguous=amend.get(AmendmentStatus.AMENDMENT_AMBIGUOUS, 0),
        ),
        records_requiring_review=statuses.get(QualityStatus.REVIEW_REQUIRED, 0)
        + statuses.get(QualityStatus.INVALID, 0),
        status_distribution={s.value: statuses.get(s.value, 0) for s in QualityStatus},
        category_distribution={
            c.value: n
            for c in Category
            if (n := sum(1 for r in records if r.transaction_category == c))
        },
        missing_values={
            f: sum(1 for r in records if getattr(r, f) is None) for f in TRACKED_FIELDS
        },
        issues=issues,
    )


def _rank(code: str) -> int:
    return FLAGS[code].severity.to_status().rank * 10 + (1 if FLAGS[code].review else 0)


def _iso(value: str) -> str:
    v = value.strip()
    if len(v) == 8 and v.isdigit():
        return f"{v[:4]}-{v[4:6]}-{v[6:]}"
    return v
