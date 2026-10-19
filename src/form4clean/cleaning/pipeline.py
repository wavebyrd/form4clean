"""The cleaning pipeline: parsed filings in, standardized records and an audit trail out.

Steps (each deterministic, so the same input and CLEANING_VERSION give the same output):

1. Drop repeated copies of the same accession number (logged, counted).
2. Point-in-time: keep only filings public at or before ``as_of``.
3. Build one record per source transaction row (normalize, classify, flag).
4. Reconcile amendments (or mark everything NOT_RECONCILED).
5. Cross-record checks: option-exercise legs, duplicates in and across filings, holdings
   continuity, and price outliers.
6. Set each record's quality status from its flags and sort deterministically.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median

from ..amendments.reconcile import AmendmentLink, reconcile
from ..models.enums import AmendmentStatus
from ..models.raw import ParsedFiling
from ..models.transaction import InsiderTransaction
from ..validation.report import QualityReport, build_report
from .records import CleaningDecision, CompanyInfo, Draft, RecordBuilder, public_time

EXERCISE_CODES = frozenset({"M", "X", "O", "C"})
OUTLIER_WINDOW_DAYS = 7
OUTLIER_THRESHOLD = Decimal("0.5")


@dataclass(frozen=True)
class CleanOptions:
    reconcile_amendments: bool = True
    as_of: datetime | None = None


@dataclass
class CleanResult:
    transactions: list[InsiderTransaction]
    decisions: list[CleaningDecision]
    amendment_links: list[AmendmentLink]
    report: QualityReport
    filings: list[ParsedFiling] = field(default_factory=list)

    @property
    def current(self) -> list[InsiderTransaction]:
        return [t for t in self.transactions if t.is_current]


def clean(
    filings: Iterable[ParsedFiling],
    company: CompanyInfo,
    options: CleanOptions | None = None,
    *,
    parse_failures: Sequence[tuple[str, str]] = (),
) -> CleanResult:
    options = options or CleanOptions()
    log: list[CleaningDecision] = []

    unique: dict[str, ParsedFiling] = {}
    duplicates = 0
    for f in filings:
        if f.accession_number in unique:
            duplicates += 1
            log.append(
                CleaningDecision(
                    f.accession_number,
                    None,
                    "deduplicate",
                    None,
                    "duplicate copy of an accession number ignored",
                )
            )
            continue
        unique[f.accession_number] = f
    selected = list(unique.values())

    if options.as_of is not None:
        as_of = options.as_of
        kept = []
        for f in selected:
            ts = public_time(f)
            if ts is not None and ts <= as_of:
                kept.append(f)
        selected = kept

    builder = RecordBuilder(company, log)
    drafts_by_acc: dict[str, list[Draft]] = {}
    for f in sorted(selected, key=lambda f: f.accession_number):
        drafts_by_acc[f.accession_number] = [builder.build(f, tx) for tx in f.transactions]

    links: list[AmendmentLink] = []
    if options.reconcile_amendments:
        links = reconcile(selected, drafts_by_acc, log)
    else:
        for drafts in drafts_by_acc.values():
            for d in drafts:
                if d.record.is_amended:
                    d.record.amendment_status = AmendmentStatus.NOT_RECONCILED

    drafts = [d for ds in drafts_by_acc.values() for d in ds]
    _link_exercise_legs(drafts_by_acc)
    _flag_duplicates(drafts_by_acc, drafts)
    _check_holdings(drafts_by_acc)
    _flag_price_outliers(drafts)

    records = sorted(
        (d.finalize() for d in drafts),
        key=lambda r: (
            r.filing_timestamp.isoformat() if r.filing_timestamp else "",
            r.accession_number,
            r.transaction_table != "non_derivative",
            r.sequence,
        ),
    )
    for r in records:
        r.related_transaction_ids = sorted(set(r.related_transaction_ids))
    report = build_report(
        company=company,
        filings=selected,
        records=records,
        links=links,
        duplicate_filings=duplicates,
        parse_failures=parse_failures,
        options_as_of=options.as_of,
        reconciled=options.reconcile_amendments,
    )
    return CleanResult(records, log, links, report, selected)


def _relate(a: Draft, b: Draft) -> None:
    a.record.related_transaction_ids.append(b.record.transaction_id)
    b.record.related_transaction_ids.append(a.record.transaction_id)


def _link_exercise_legs(drafts_by_acc: dict[str, list[Draft]]) -> None:
    """Pair the derivative and common-stock legs of an exercise or conversion in one filing."""
    for drafts in drafts_by_acc.values():
        derivs = [
            d
            for d in drafts
            if d.record.is_derivative
            and (d.record.transaction_code or "").upper() in EXERCISE_CODES
        ]
        stock = [
            d
            for d in drafts
            if not d.record.is_derivative
            and (d.record.transaction_code or "").upper() in EXERCISE_CODES
        ]
        used: set[int] = set()
        for dv in derivs:
            qty = dv.record.underlying_shares or dv.record.shares
            for i, st in enumerate(stock):
                if i in used:
                    continue
                if (
                    st.record.transaction_code == dv.record.transaction_code
                    and st.record.transaction_date == dv.record.transaction_date
                    and qty is not None
                    and st.record.shares == qty
                ):
                    _relate(dv, st)
                    used.add(i)
                    break


def _flag_duplicates(drafts_by_acc: dict[str, list[Draft]], drafts: list[Draft]) -> None:
    for acc_drafts in drafts_by_acc.values():
        seen: dict[tuple[object, ...], Draft] = {}
        for d in acc_drafts:
            key = (
                *d.economic_key,
                d.record.shares_owned_after,
                d.record.ownership_type,
                d.record.ownership_nature,
            )
            if key in seen:
                first = seen[key]
                d.flag(
                    "POSSIBLE_DUPLICATE_IN_FILING", f"Same values as {first.record.transaction_id}."
                )
                first.flag(
                    "POSSIBLE_DUPLICATE_IN_FILING", f"Same values as {d.record.transaction_id}."
                )
                _relate(first, d)
            else:
                seen[key] = d

    # Across filings, identical trade terms alone are common (standard award sizes go to many
    # insiders on the same day). Joint filers reporting the same trade separately also report
    # the same holdings afterwards, so holdings and ownership are part of the key.
    groups: dict[tuple[object, ...], list[Draft]] = defaultdict(list)
    for d in drafts:
        r = d.record
        if (
            not r.is_current
            or r.transaction_date is None
            or r.shares is None
            or r.shares_owned_after is None
        ):
            continue
        groups[(*d.economic_key, r.shares_owned_after, r.ownership_type)].append(d)
    for group in groups.values():
        accessions = {d.record.accession_number for d in group}
        if len(accessions) < 2:
            continue
        for d in group:
            others = [o for o in group if o.record.accession_number != d.record.accession_number]
            d.flag(
                "POSSIBLE_DUPLICATE_ACROSS_FILINGS",
                "Also reported in "
                + ", ".join(sorted({o.record.accession_number for o in others}))
                + ".",
            )
            for o in others:
                d.record.related_transaction_ids.append(o.record.transaction_id)


def _check_holdings(drafts_by_acc: dict[str, list[Draft]]) -> None:
    for drafts in drafts_by_acc.values():
        last: dict[tuple[object, ...], Draft] = {}
        for d in drafts:
            r = d.record
            if r.is_derivative:
                continue
            key = ((r.security_title or "").lower(), r.ownership_type, r.ownership_nature)
            prev = last.get(key)
            last[key] = d
            if prev is None:
                continue
            before = prev.record.shares_owned_after
            if before is None or r.shares is None or r.shares_owned_after is None:
                continue
            ad = (r.acquired_disposed_code or "").upper()
            if ad not in ("A", "D"):
                continue
            expected = before + r.shares if ad == "A" else before - r.shares
            if expected != r.shares_owned_after:
                d.flag(
                    "HOLDINGS_INCONSISTENT",
                    f"Previous row leaves {before:f}; {ad} {r.shares:f} implies "
                    f"{expected:f}, but {r.shares_owned_after:f} is reported.",
                )


def _flag_price_outliers(drafts: list[Draft]) -> None:
    trades = [
        d
        for d in drafts
        if d.record.is_current
        and not d.record.is_derivative
        and (d.record.transaction_code or "").upper() in ("P", "S")
        and d.record.price_per_share
        and d.record.transaction_date
        and (d.record.security_title or "").lower() == "common stock"
    ]
    trades.sort(key=lambda d: d.record.transaction_date)  # type: ignore[arg-type,return-value]
    window = timedelta(days=OUTLIER_WINDOW_DAYS)
    for d in trades:
        day = d.record.transaction_date
        assert day is not None
        peers = [
            o.record.price_per_share
            for o in trades
            if o is not d
            and o.record.transaction_date is not None
            and abs(o.record.transaction_date - day) <= window
            and o.record.accession_number != d.record.accession_number
        ]
        prices = [p for p in peers if p is not None]
        if len(prices) < 2:
            continue
        mid = Decimal(median(prices))
        price = d.record.price_per_share
        assert price is not None
        if mid > 0 and abs(price - mid) / mid > OUTLIER_THRESHOLD:
            d.flag(
                "PRICE_OUTLIER",
                f"Price {price:f} vs median {mid:f} of {len(prices)} nearby trades.",
            )
