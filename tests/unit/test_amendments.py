from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from form4clean.calendar import EASTERN
from form4clean.cleaning.pipeline import CleanOptions, clean
from form4clean.models.enums import AmendmentStatus, QualityStatus
from form4clean.models.raw import ParsedFiling
from tests.conftest import COMPANY, INDEX, parsed

ORIGINAL = "f05_original.xml"
CORRECTION = "f06_amendment_correction.xml"
DATE_FIX = "f07_amendment_date_fix.xml"


def acc(name: str) -> str:
    return INDEX[name]["accession"]


def by_acc(records: list, name: str) -> list:  # type: ignore[type-arg]
    return [r for r in records if r.accession_number == acc(name)]


def test_amendment_correction_supersedes_original() -> None:
    res = clean([parsed(ORIGINAL), parsed(CORRECTION)], COMPANY)
    original = by_acc(res.transactions, ORIGINAL)
    amended = by_acc(res.transactions, CORRECTION)
    assert all(r.amendment_status is AmendmentStatus.SUPERSEDED for r in original)
    assert all(not r.is_current for r in original)
    assert [r.amendment_status for r in amended] == [
        AmendmentStatus.AMENDED_CORRECTED,
        AmendmentStatus.AMENDED_RESTATED,
    ]
    assert amended[0].price_per_share == Decimal("61.00")
    assert original[0].superseded_by == amended[0].transaction_id
    assert amended[0].amends_accession_number == acc(ORIGINAL)
    assert all(r.is_amended for r in amended)
    # Current view counts each sale once.
    current = [r for r in res.transactions if r.is_current]
    assert len(current) == 2
    assert sum(r.shares for r in current) == Decimal("1500")


def test_chained_amendments_and_position_matching() -> None:
    res = clean([parsed(ORIGINAL), parsed(CORRECTION), parsed(DATE_FIX)], COMPANY)
    current = [r for r in res.transactions if r.is_current]
    assert {r.accession_number for r in current} == {acc(DATE_FIX)}
    second = by_acc(res.transactions, DATE_FIX)[1]
    assert second.amendment_status is AmendmentStatus.AMENDED_CORRECTED
    assert "AMENDMENT_MATCHED_BY_POSITION" in second.quality_flags
    middle = by_acc(res.transactions, CORRECTION)
    assert all(r.amendment_status is AmendmentStatus.SUPERSEDED for r in middle)
    links = {link.amendment_accession: link for link in res.amendment_links}
    assert links[acc(DATE_FIX)].original_accession == acc(ORIGINAL)


def test_superseded_records_are_preserved_with_audit_trail() -> None:
    res = clean([parsed(ORIGINAL), parsed(CORRECTION)], COMPANY)
    assert len(res.transactions) == 4
    steps = [d for d in res.decisions if d.step == "amendments"]
    assert any(d.rule.startswith("LINKED") for d in steps)
    assert any(d.rule == "corrects" for d in steps)
    assert any(d.rule == "restates" for d in steps)


def test_ambiguous_amendment_is_flagged_not_applied() -> None:
    names = ["f08a_cfo_first.xml", "f08b_cfo_second.xml", "f08c_cfo_amendment.xml"]
    res = clean([parsed(n) for n in names], COMPANY)
    amended = by_acc(res.transactions, names[2])[0]
    assert amended.amendment_status is AmendmentStatus.AMENDMENT_AMBIGUOUS
    assert not amended.is_current
    assert amended.quality_status is QualityStatus.REVIEW_REQUIRED
    originals = [r for r in res.transactions if r.accession_number != acc(names[2])]
    assert all(r.is_current and r.amendment_status is AmendmentStatus.ORIGINAL for r in originals)
    link = res.amendment_links[0]
    assert link.status == "AMBIGUOUS"
    assert link.candidates == sorted([acc(names[0]), acc(names[1])])


def test_amendment_without_original_in_dataset() -> None:
    res = clean([parsed("f09_amendment_orphan.xml")], COMPANY)
    rec = res.transactions[0]
    assert rec.amendment_status is AmendmentStatus.AMENDMENT_ORIGINAL_NOT_FOUND
    assert rec.is_current
    assert rec.quality_status is QualityStatus.WARNING
    assert "LATE_FILING" not in rec.quality_flags


def test_reconciliation_can_be_turned_off() -> None:
    res = clean(
        [parsed(ORIGINAL), parsed(CORRECTION)], COMPANY, CleanOptions(reconcile_amendments=False)
    )
    assert all(r.is_current for r in res.transactions)
    statuses = {r.amendment_status for r in by_acc(res.transactions, CORRECTION)}
    assert statuses == {AmendmentStatus.NOT_RECONCILED}
    restated = by_acc(res.transactions, CORRECTION)[1]
    assert "POSSIBLE_DUPLICATE_ACROSS_FILINGS" in restated.quality_flags


def _amend(base: ParsedFiling, accession: str, accepted: str, rows: int) -> ParsedFiling:
    return base.model_copy(
        update={
            "accession_number": accession,
            "form_type": "4/A",
            "acceptance_datetime": accepted,
            "filing_date": accepted[:8],
            "date_of_original_submission": "2025-04-03",
            "transactions": base.transactions[:rows],
        }
    )


def test_amendment_with_empty_table_may_remove_records() -> None:
    original = parsed(ORIGINAL)
    empty = _amend(original, "0000999101-25-000077", "20250410100000", 0)
    res = clean([original, empty], COMPANY)
    rows = by_acc(res.transactions, ORIGINAL)
    assert all(r.is_current for r in rows)
    assert all("AMENDMENT_MAY_REMOVE" in r.quality_flags for r in rows)
    assert all(r.quality_status is QualityStatus.REVIEW_REQUIRED for r in rows)


def test_partial_amendment_keeps_unrestated_rows() -> None:
    original = parsed(ORIGINAL)
    partial = _amend(original, "0000999101-25-000078", "20250410100000", 1)
    res = clean([original, partial], COMPANY)
    first, second = by_acc(res.transactions, ORIGINAL)
    assert first.amendment_status is AmendmentStatus.SUPERSEDED
    assert second.amendment_status is AmendmentStatus.ORIGINAL_NOT_RESTATED
    assert second.is_current
    assert len([r for r in res.transactions if r.is_current]) == 2


def test_point_in_time_excludes_later_filings() -> None:
    filings = [parsed(ORIGINAL), parsed(CORRECTION), parsed(DATE_FIX)]
    # The correction was accepted 2025-04-21 09:00 Eastern.
    before = clean(
        filings, COMPANY, CleanOptions(as_of=datetime(2025, 4, 21, 8, 59, tzinfo=EASTERN))
    )
    after = clean(filings, COMPANY, CleanOptions(as_of=datetime(2025, 4, 21, 9, 0, tzinfo=EASTERN)))
    assert {r.accession_number for r in before.transactions} == {acc(ORIGINAL)}
    assert all(
        r.is_current and r.amendment_status is AmendmentStatus.ORIGINAL for r in before.transactions
    )
    current_after = {r.accession_number for r in after.transactions if r.is_current}
    assert current_after == {acc(CORRECTION)}
    assert acc(DATE_FIX) not in {r.accession_number for r in after.transactions}


def test_point_in_time_never_sees_unpublished_filings() -> None:
    filings = [parsed(n) for n in INDEX]
    cutoff = datetime(2025, 5, 1, 0, 0, tzinfo=EASTERN)
    res = clean(filings, COMPANY, CleanOptions(as_of=cutoff))
    assert res.transactions
    for r in res.transactions:
        assert r.filing_timestamp is not None
        assert r.filing_timestamp <= cutoff


def test_missing_timestamp_uses_conservative_cutoff() -> None:
    original = parsed(ORIGINAL).model_copy(update={"acceptance_datetime": None})
    # Filed 2025-04-03 with no acceptance time: treated as public at 5:30 p.m. that day.
    early = clean(
        [original], COMPANY, CleanOptions(as_of=datetime(2025, 4, 3, 17, 0, tzinfo=EASTERN))
    )
    late = clean(
        [original], COMPANY, CleanOptions(as_of=datetime(2025, 4, 3, 17, 30, tzinfo=EASTERN))
    )
    assert early.transactions == []
    assert len(late.transactions) == 2
    assert "MISSING_FILING_TIMESTAMP" in late.transactions[0].quality_flags
