from __future__ import annotations

import pytest
from defusedxml import EntitiesForbidden

from form4clean.parsing.ownership import OwnershipParseError, parse_filing, parse_ownership_xml
from form4clean.parsing.submission import parse_submission
from tests.conftest import FIXTURES, parsed


def test_full_submission_header_and_document() -> None:
    sub = parse_submission((FIXTURES / "submission_f01.txt").read_bytes())
    assert sub.header == {
        "acceptance_datetime": "20250305163012",
        "accession_number": "0000999101-25-000003",
        "form_type": "4",
        "period_of_report": "20250303",
        "filed_as_of_date": "20250305",
    }
    doc = sub.ownership_document()
    assert doc is not None
    assert doc.filename == "form4.xml"
    assert doc.xml is not None
    assert doc.xml.startswith("<?xml")


def test_parse_filing_from_submission() -> None:
    filing = parse_filing((FIXTURES / "submission_f01.txt").read_bytes())
    assert filing.accession_number == "0000999101-25-000003"
    assert filing.form_type == "4"
    assert filing.acceptance_datetime == "20250305163012"
    assert filing.filing_date == "20250305"
    assert filing.issuer_cik == "0000999001"
    assert filing.sec_filing_url == (
        "https://www.sec.gov/Archives/edgar/data/999001/000099910125000003/"
        "0000999101-25-000003-index.htm"
    )


def test_multiple_transactions_and_holdings_are_extracted() -> None:
    filing = parsed("f01_sale_10b5_1.xml")
    assert [(t.table, t.sequence, t.shares, t.price_per_share) for t in filing.transactions] == [
        ("non_derivative", 0, "12000", "51.2345"),
        ("non_derivative", 1, "3000", "52.1"),
    ]
    assert len(filing.holdings) == 1
    holding = filing.holdings[0]
    assert holding.direct_or_indirect == "I"
    assert holding.nature_of_ownership == "By Doe Family Trust"
    assert filing.aff_10b5_one == "1"


def test_values_are_kept_exactly_as_filed() -> None:
    tx = parsed("f02_option_exercise.xml").transactions
    sale = next(t for t in tx if t.transaction_code == "S")
    assert sale.shares == "6,800"
    assert sale.transaction_date == "2022-08-16-04:00"
    assert sale.price_per_share == "86.10"


def test_derivative_fields() -> None:
    deriv = next(
        t for t in parsed("f02_option_exercise.xml").transactions if t.table == "derivative"
    )
    assert deriv.security_title == "Employee Stock Option (right to buy)"
    assert deriv.conversion_or_exercise_price == "12.50"
    assert deriv.exercise_date is None
    assert deriv.footnote_ids["exercise_date"] == ["F2"]
    assert deriv.expiration_date == "2027-02-01"
    assert deriv.underlying_security_title == "Common Stock"
    assert deriv.underlying_shares == "10000"
    assert deriv.acquired_disposed_code == "D"


def test_footnotes_are_linked_to_fields() -> None:
    filing = parsed("f01_sale_10b5_1.xml")
    first = filing.transactions[0]
    assert first.footnote_ids == {"transaction_code": ["F1"], "price_per_share": ["F2"]}
    assert "10b5-1" in filing.footnotes["F1"]


def test_multiple_reporting_owners() -> None:
    filing = parsed("f04_joint_filing.xml")
    assert [(o.cik, o.name, o.is_ten_percent_owner) for o in filing.reporting_owners] == [
        ("0000999103", "EXAMPLE VENTURES FUND II, L.P.", "1"),
        ("0000999104", "EXAMPLE VENTURES GP LLC", "1"),
    ]


def test_missing_footnote_is_a_parse_warning() -> None:
    filing = parsed("f03_edge_cases.xml")
    assert filing.parse_warnings == ["Footnote F9 is referenced but not present in the filing."]


def test_amendment_fields() -> None:
    filing = parsed("f06_amendment_correction.xml")
    assert filing.is_amendment
    assert filing.date_of_original_submission == "2025-04-03"
    assert filing.remarks
    assert "corrects the price" in filing.remarks


def test_malformed_xml_raises_clear_error() -> None:
    with pytest.raises(OwnershipParseError, match="malformed"):
        parse_ownership_xml("<ownershipDocument><issuer>", accession_number="x")


def test_non_ownership_document_rejected() -> None:
    with pytest.raises(OwnershipParseError, match="expected an ownershipDocument"):
        parse_ownership_xml("<edgarSubmission/>", accession_number="x")


def test_submission_without_xml_raises() -> None:
    text = (
        "<SEC-HEADER>\nACCESSION NUMBER:\t0000000000-01-000001\n</SEC-HEADER>\n"
        "<DOCUMENT>\n<TYPE>4\n<TEXT>paper filing text</TEXT>\n</DOCUMENT>"
    )
    with pytest.raises(OwnershipParseError, match="no ownership XML"):
        parse_filing(text)


def test_external_entities_are_refused() -> None:
    evil = (
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
        "<ownershipDocument><remarks>&e;</remarks></ownershipDocument>"
    )
    with pytest.raises(EntitiesForbidden):
        parse_ownership_xml(evil, accession_number="x")
