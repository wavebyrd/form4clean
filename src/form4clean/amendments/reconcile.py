"""Reconcile Form 4/A amendments with the filings they amend.

Amendments do not say which accession number they amend. They give the reporting owner and,
usually, ``dateOfOriginalSubmission``. Linking is therefore an inference, made conservatively:

Filing level
    Candidates are earlier original Forms 4 that share a reporting owner with the amendment and
    were filed (or accepted) on the date of original submission. Without that date, candidates
    must share the period of report. Exactly one candidate links; zero means the original is not
    in the dataset; several means the link is ambiguous.

Record level
    Amendments of the same original are applied in acceptance order against the records that
    are current at that point, table by table:

    1. Rows match when they share table, transaction date, code, security title and ownership
       type, in order of appearance.
    2. Leftover rows on both sides with equal counts are paired by position (an amendment that
       corrects a date or code), and flagged.
    3. Leftover amended rows with nothing left to match are additions.
    4. Leftover rows on both sides with unequal counts are ambiguous: the amended rows leave the
       current view and are flagged for review; the earlier rows stay current.
    5. Earlier rows the amendment does not restate stay current. If the amendment's table is
       empty, they are flagged, because the amendment may have removed them.

Superseded and ambiguous records are never deleted; they stay in the full view with an audit
trail (``superseded_by``, ``amends_accession_number``, and the cleaning log).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from ..cleaning.normalize import parse_date
from ..cleaning.records import CleaningDecision, Draft, public_time
from ..models.enums import AmendmentStatus, Confidence
from ..models.raw import ParsedFiling


@dataclass
class AmendmentLink:
    amendment_accession: str
    original_accession: str | None
    status: str  # LINKED | ORIGINAL_NOT_FOUND | AMBIGUOUS
    confidence: Confidence | None
    reason: str
    candidates: list[str]


def _owners(filing: ParsedFiling) -> set[str]:
    return {o.cik.strip().lstrip("0") for o in filing.reporting_owners if o.cik}


def _sort_key(filing: ParsedFiling) -> tuple[datetime | str, str]:
    ts = public_time(filing)
    return (ts.isoformat() if ts else "", filing.accession_number)


def link_amendments(filings: Sequence[ParsedFiling]) -> list[AmendmentLink]:
    originals = [f for f in filings if not f.is_amendment]
    links: list[AmendmentLink] = []
    for amendment in sorted((f for f in filings if f.is_amendment), key=_sort_key):
        owners = _owners(amendment)
        amended_at = public_time(amendment)
        pool = [
            f
            for f in originals
            if _owners(f) & owners
            and (amended_at is None or (public_time(f) or amended_at) <= amended_at)
        ]
        original_date, _ = parse_date(amendment.date_of_original_submission)
        if original_date is not None:
            cands = []
            for f in pool:
                filed, _ = parse_date(f.filing_date)
                accepted = public_time(f)
                if filed == original_date or (accepted and accepted.date() == original_date):
                    cands.append(f)
            basis = f"filed on the date of original submission ({original_date})"
            confidence = Confidence.HIGH
        else:
            cands = [f for f in pool if f.period_of_report == amendment.period_of_report]
            basis = f"same period of report ({amendment.period_of_report})"
            confidence = Confidence.MEDIUM
        if len(cands) > 1:
            narrowed = [f for f in cands if f.period_of_report == amendment.period_of_report]
            if len(narrowed) == 1:
                cands = narrowed
                basis += " and same period of report"
                confidence = Confidence.MEDIUM
        accs = sorted(f.accession_number for f in cands)
        if len(cands) == 1:
            links.append(
                AmendmentLink(
                    amendment.accession_number,
                    accs[0],
                    "LINKED",
                    confidence,
                    f"Only one earlier Form 4 from the same reporting owner was {basis}.",
                    accs,
                )
            )
        elif not cands:
            links.append(
                AmendmentLink(
                    amendment.accession_number,
                    None,
                    "ORIGINAL_NOT_FOUND",
                    None,
                    f"No earlier Form 4 in the dataset from the same reporting owner was {basis}.",
                    [],
                )
            )
        else:
            links.append(
                AmendmentLink(
                    amendment.accession_number,
                    None,
                    "AMBIGUOUS",
                    None,
                    f"{len(cands)} earlier Forms 4 from the same reporting owner were {basis}.",
                    accs,
                )
            )
    return links


def _match_key(d: Draft) -> tuple[object, ...]:
    r = d.record
    return (
        r.transaction_table,
        r.transaction_date,
        (r.transaction_code or "").upper(),
        (r.security_title or "").lower(),
        r.ownership_type,
    )


def _values(d: Draft) -> tuple[object, ...]:
    r = d.record
    return (
        r.transaction_date,
        (r.transaction_code or "").upper(),
        r.shares,
        r.price_per_share,
        (r.acquired_disposed_code or "").upper(),
        r.shares_owned_after,
        r.ownership_type,
        r.ownership_nature,
        r.security_title,
    )


def reconcile(
    filings: Sequence[ParsedFiling],
    drafts_by_accession: dict[str, list[Draft]],
    log: list[CleaningDecision],
) -> list[AmendmentLink]:
    links = link_amendments(filings)
    by_original: dict[str, list[str]] = defaultdict(list)
    for link in links:
        drafts = drafts_by_accession.get(link.amendment_accession, [])
        if link.status == "LINKED" and link.original_accession:
            by_original[link.original_accession].append(link.amendment_accession)
        elif link.status == "ORIGINAL_NOT_FOUND":
            for d in drafts:
                d.record.amendment_status = AmendmentStatus.AMENDMENT_ORIGINAL_NOT_FOUND
                d.flag("AMENDMENT_ORIGINAL_NOT_FOUND", link.reason)
        else:
            for d in drafts:
                _ambiguous(d, link.reason, log)
        log.append(
            CleaningDecision(
                link.amendment_accession,
                None,
                "amendments",
                None,
                f"{link.status}: {link.reason}",
                None,
                link.original_accession,
            )
        )

    for original, amendments in by_original.items():
        active = list(drafts_by_accession.get(original, []))
        for amendment_acc in amendments:  # already in acceptance order
            new = drafts_by_accession.get(amendment_acc, [])
            for table in ("non_derivative", "derivative"):
                old_t = [d for d in active if d.record.transaction_table == table]
                new_t = [d for d in new if d.record.transaction_table == table]
                active = _apply(active, old_t, new_t, original, amendment_acc, log)
    return links


def _apply(
    active: list[Draft],
    old: list[Draft],
    new: list[Draft],
    original: str,
    amendment: str,
    log: list[CleaningDecision],
) -> list[Draft]:
    if not old and not new:
        return active
    pairs: list[tuple[Draft, Draft, bool]] = []
    old_groups: dict[tuple[object, ...], list[Draft]] = defaultdict(list)
    for d in old:
        old_groups[_match_key(d)].append(d)
    left_new: list[Draft] = []
    for d in new:
        group = old_groups.get(_match_key(d))
        if group:
            pairs.append((group.pop(0), d, False))
        else:
            left_new.append(d)
    left_old = [d for d in old if any(d is g for grp in old_groups.values() for g in grp)]

    if left_old and left_new and len(left_old) == len(left_new):
        pairs.extend((o, nw, True) for o, nw in zip(left_old, left_new, strict=True))
        left_old, left_new = [], []

    for prior, amended, by_position in pairs:
        prior.record.amendment_status = AmendmentStatus.SUPERSEDED
        prior.record.is_current = False
        prior.record.superseded_by = amended.record.transaction_id
        prior.flag("SUPERSEDED", f"Replaced by {amended.record.transaction_id} in {amendment}.")
        same = _values(prior) == _values(amended)
        amended.record.amendment_status = (
            AmendmentStatus.AMENDED_RESTATED if same else AmendmentStatus.AMENDED_CORRECTED
        )
        amended.record.amends_accession_number = prior.record.accession_number
        if by_position:
            amended.flag(
                "AMENDMENT_MATCHED_BY_POSITION", f"Paired with {prior.record.transaction_id}."
            )
        log.append(
            CleaningDecision(
                amendment,
                amended.record.transaction_id,
                "amendments",
                None,
                ("restates" if same else "corrects")
                + (" (matched by position)" if by_position else ""),
                prior.record.transaction_id,
                amended.record.transaction_id,
            )
        )
        active = [amended if d is prior else d for d in active]

    if left_new and not left_old:
        for d in left_new:
            d.record.amendment_status = AmendmentStatus.AMENDED_ADDED
            d.record.amends_accession_number = original
            log.append(
                CleaningDecision(
                    amendment,
                    d.record.transaction_id,
                    "amendments",
                    None,
                    "added: no counterpart in the amended filing",
                    None,
                    d.record.transaction_id,
                )
            )
            active.append(d)
    elif left_new:
        for d in left_new:
            d.record.amends_accession_number = original
            _ambiguous(
                d,
                f"{len(left_new)} amended rows could not be paired with "
                f"{len(left_old)} earlier rows.",
                log,
            )

    for d in left_old:
        if not new:
            d.flag("AMENDMENT_MAY_REMOVE", f"Amendment {amendment} reports no rows in this table.")
        elif left_new:
            d.flag("AMENDMENT_AMBIGUOUS", f"Amendment {amendment} has unpaired rows.")
        else:
            d.flag("ORIGINAL_NOT_RESTATED", f"Amendment {amendment} did not restate this row.")
        if d.record.amendment_status is AmendmentStatus.ORIGINAL:
            d.record.amendment_status = AmendmentStatus.ORIGINAL_NOT_RESTATED
    return active


def _ambiguous(d: Draft, reason: str, log: list[CleaningDecision]) -> None:
    d.record.amendment_status = AmendmentStatus.AMENDMENT_AMBIGUOUS
    d.record.is_current = False
    d.flag("AMENDMENT_AMBIGUOUS", reason)
    log.append(
        CleaningDecision(
            d.record.accession_number,
            d.record.transaction_id,
            "amendments",
            None,
            f"ambiguous: {reason}",
            None,
            None,
        )
    )
