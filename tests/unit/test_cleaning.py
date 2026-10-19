from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from form4clean.cleaning.pipeline import CleanResult, clean
from form4clean.models.enums import Category, DisclosureTiming, QualityStatus
from form4clean.models.transaction import InsiderTransaction
from tests.conftest import COMPANY, INDEX, all_parsed, parsed


@pytest.fixture(scope="module")
def result() -> CleanResult:
    return clean(all_parsed(), COMPANY)


def records_of(result: CleanResult, fixture: str) -> list[InsiderTransaction]:
    acc = INDEX[fixture]["accession"]
    return [r for r in result.transactions if r.accession_number == acc]


def test_no_source_record_is_dropped(result: CleanResult) -> None:
    source_rows = sum(len(f.transactions) for f in all_parsed())
    assert len(result.transactions) == source_rows
    assert result.report.transactions_extracted == source_rows


def test_sale_under_10b5_1_plan(result: CleanResult) -> None:
    first, second = records_of(result, "f01_sale_10b5_1.xml")
    assert first.transaction_category is Category.MARKET_SALE
    assert first.shares == Decimal("12000")
    assert first.price_per_share == Decimal("51.2345")
    assert first.transaction_value == Decimal("614814.00")
    assert first.is_10b5_1 is True
    assert first.is_10b5_1_source == "footnote"
    assert first.is_discretionary_trade is False
    assert first.is_market_transaction is None
    assert first.security_title == "Common Stock"
    assert first.security_title_raw == "COMMON STOCK, PAR VALUE $0.001 PER SHARE"
    assert first.insider_name == "Jane A Doe"
    assert first.insider_name_raw == "DOE JANE A"
    assert first.insider_role == "CEO"
    assert first.is_director
    assert first.is_officer
    assert "WEIGHTED_AVERAGE_PRICE" in first.quality_flags
    assert first.quality_status is QualityStatus.VALID
    assert second.sequence == 1
    assert [f.id for f in first.footnotes] == ["F1", "F2"]
    assert first.footnotes[0].fields == ["transaction_code"]


def test_option_exercise_legs_are_linked(result: CleanResult) -> None:
    rows = records_of(result, "f02_option_exercise.xml")
    stock = next(r for r in rows if r.transaction_code == "M" and not r.is_derivative)
    option = next(r for r in rows if r.is_derivative)
    assert option.transaction_category is Category.DERIVATIVE_EXERCISE
    assert option.exercise_price == Decimal("12.50")
    assert option.expiration_date == date(2027, 2, 1)
    assert option.exercise_date is None
    assert option.underlying_shares == Decimal("10000")
    assert option.security_title == "Employee Stock Option (Right to Buy)"
    assert stock.related_transaction_ids == [option.transaction_id]
    assert option.related_transaction_ids == [stock.transaction_id]
    assert stock.is_discretionary_trade is None
    assert stock.is_market_transaction is False


def test_tax_withholding(result: CleanResult) -> None:
    tax = next(
        r for r in records_of(result, "f02_option_exercise.xml") if r.transaction_code == "F"
    )
    assert tax.transaction_category is Category.TAX_RELATED
    assert tax.is_discretionary_trade is False
    assert tax.is_market_transaction is False
    assert tax.transaction_value == Decimal("272000.00")


def test_open_market_footnote_and_formats(result: CleanResult) -> None:
    sale = next(
        r for r in records_of(result, "f02_option_exercise.xml") if r.transaction_code == "S"
    )
    assert sale.is_market_transaction is True
    assert sale.is_10b5_1 is None  # filed before the 10b5-1 checkbox existed
    assert sale.shares == Decimal("6800")
    assert sale.transaction_date == date(2022, 8, 16)


def test_gift_with_indirect_ownership_and_no_price(result: CleanResult) -> None:
    gift = records_of(result, "f03_edge_cases.xml")[0]
    assert gift.transaction_category is Category.GIFT_OR_TRANSFER
    assert gift.price_per_share is None
    assert gift.transaction_value is None
    assert gift.ownership_type == "Indirect"
    assert "MISSING_PRICE_NON_TRADE" in gift.quality_flags
    assert "MISSING_PRICE" not in gift.quality_flags
    assert "INDIRECT_WITHOUT_NATURE" in gift.quality_flags


def test_purchase_missing_price_is_a_warning(result: CleanResult) -> None:
    purchase = records_of(result, "f03_edge_cases.xml")[2]
    assert purchase.transaction_code == "P"
    assert purchase.price_per_share is None
    assert purchase.transaction_value is None
    assert {"MISSING_PRICE", "FOOTNOTE_NOT_FOUND"} <= set(purchase.quality_flags)
    assert purchase.quality_status is QualityStatus.WARNING


def test_unrecognized_code_and_invalid_number(result: CleanResult) -> None:
    odd = records_of(result, "f03_edge_cases.xml")[3]
    assert odd.transaction_code == "Q"
    assert odd.transaction_category is Category.UNKNOWN
    assert odd.shares is None
    assert {"UNRECOGNIZED_TRANSACTION_CODE", "INVALID_SHARES"} <= set(odd.quality_flags)
    assert odd.quality_status is QualityStatus.INVALID
    assert json.loads(odd.source_values)["transaction"]["shares"] == "12x"


def test_impossible_record_requires_review(result: CleanResult) -> None:
    bad = records_of(result, "f03_edge_cases.xml")[4]
    assert {"TRANSACTION_AFTER_FILING", "DIRECTION_CODE_MISMATCH", "ZERO_PRICE_TRADE"} <= set(
        bad.quality_flags
    )
    assert bad.quality_status is QualityStatus.REVIEW_REQUIRED


def test_optional_fields_absent_is_not_invalid(result: CleanResult) -> None:
    rsu = next(r for r in records_of(result, "f03_edge_cases.xml") if r.is_derivative)
    assert rsu.exercise_price is None
    assert rsu.exercise_date is None
    assert rsu.security_title == "Restricted Stock Units"
    assert rsu.quality_status is QualityStatus.VALID


def test_joint_filing_is_one_record_per_transaction(result: CleanResult) -> None:
    rows = records_of(result, "f04_joint_filing.xml")
    assert len(rows) == 1
    rec = rows[0]
    assert rec.reporting_owner_count == 2
    assert [o.cik for o in rec.reporting_owners] == ["0000999103", "0000999104"]
    assert rec.insider_name == "Example Ventures Fund II, L.P."
    assert rec.insider_role == "10% Owner"
    assert rec.is_market_transaction is False  # privately negotiated, per footnote
    assert "MULTIPLE_REPORTING_OWNERS" in rec.quality_flags


@pytest.mark.parametrize(
    ("fixture", "timing", "session"),
    [
        ("f01_sale_10b5_1.xml", DisclosureTiming.AFTER_CLOSE, date(2025, 3, 6)),
        ("f03_edge_cases.xml", DisclosureTiming.PRE_MARKET, date(2025, 5, 2)),
        ("f04_joint_filing.xml", DisclosureTiming.MARKET_HOURS, date(2025, 6, 10)),
        ("f09_amendment_orphan.xml", DisclosureTiming.NON_TRADING_DAY, date(2025, 4, 21)),
    ],
)
def test_disclosure_after_market_close(
    result: CleanResult, fixture: str, timing: DisclosureTiming, session: date
) -> None:
    rec = records_of(result, fixture)[0]
    assert rec.disclosure_timing is timing
    assert rec.disclosure_session_date == session
    assert rec.filing_timestamp is not None
    assert rec.filing_timestamp.tzinfo is not None


def test_late_filing_is_informational(result: CleanResult) -> None:
    rsu = next(r for r in records_of(result, "f03_edge_cases.xml") if r.is_derivative)
    assert "LATE_FILING" in rsu.quality_flags
    assert rsu.days_to_file == 4


def test_transaction_ids_are_stable_and_unique(result: CleanResult) -> None:
    ids = [r.transaction_id for r in result.transactions]
    assert len(ids) == len(set(ids))
    again = clean(list(reversed(all_parsed())), COMPANY)
    assert [r.transaction_id for r in again.transactions] == ids
    assert [r.model_dump() for r in again.transactions] == [
        r.model_dump() for r in result.transactions
    ]


def test_every_change_is_logged(result: CleanResult) -> None:
    name_changes = [d for d in result.decisions if d.field == "insider_name"]
    assert any(d.before == "DOE JANE A" and d.after == "Jane A Doe" for d in name_changes)
    shares = [d for d in result.decisions if d.field == "shares" and d.before == "6,800"]
    assert shares
    assert shares[0].after == "6800"


def test_report(result: CleanResult) -> None:
    report = result.report
    assert report.filings_processed == len(INDEX)
    assert report.transactions_classified == report.transactions_extracted - 1
    assert report.status_distribution["INVALID"] == 1
    assert report.missing_values["price_per_share"] >= 3
    assert report.amendments.amendment_filings == 4
    codes = {i.code for i in report.issues}
    assert {"AMENDMENT_AMBIGUOUS", "INVALID_SHARES", "MISSING_PRICE"} <= codes
    for issue in report.issues:
        assert issue.why
        assert issue.action


def test_single_filing_still_works() -> None:
    res = clean([parsed("f01_sale_10b5_1.xml")], COMPANY)
    assert len(res.transactions) == 2


def test_empty_input() -> None:
    res = clean([], COMPANY)
    assert res.transactions == []
    assert res.report.classification_coverage == 1.0
