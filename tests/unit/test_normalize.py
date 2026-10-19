from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from form4clean.calendar import EASTERN
from form4clean.cleaning import normalize as n


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12000", Decimal("12000")),
        ("6,800", Decimal("6800")),
        (" 51.2345 ", Decimal("51.2345")),
        ("$1,234.50", Decimal("1234.50")),
        ("0", Decimal("0")),
        ("", None),
        (None, None),
    ],
)
def test_parse_decimal(raw: str | None, expected: Decimal | None) -> None:
    value, error = n.parse_decimal(raw)
    assert value == expected
    assert error is None


@pytest.mark.parametrize("raw", ["12x", "NaN", "Infinity", "1.12345678901"])
def test_parse_decimal_rejects(raw: str) -> None:
    value, error = n.parse_decimal(raw)
    assert value is None
    assert error


def test_money_rounds_half_up_to_cents() -> None:
    assert n.money(Decimal("3"), Decimal("0.335")) == Decimal("1.01")
    assert n.money(Decimal("12000"), Decimal("51.2345")) == Decimal("614814.00")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2025-03-03", date(2025, 3, 3)),
        ("2022-08-16-04:00", date(2022, 8, 16)),
        ("2022-08-16Z", date(2022, 8, 16)),
        ("20250305", date(2025, 3, 5)),
        ("3/5/2025", date(2025, 3, 5)),
    ],
)
def test_parse_date(raw: str, expected: date) -> None:
    assert n.parse_date(raw) == (expected, None)


@pytest.mark.parametrize("raw", ["2025-02-30", "March 5", "2025/03/05"])
def test_parse_date_rejects(raw: str) -> None:
    value, error = n.parse_date(raw)
    assert value is None
    assert error


def test_parse_acceptance_is_eastern_time() -> None:
    value, error = n.parse_acceptance("20261013170929")
    assert error is None
    assert value == datetime(2026, 10, 13, 17, 9, 29, tzinfo=EASTERN)
    assert value is not None
    assert value.utcoffset() is not None
    assert value.utcoffset().total_seconds() == -4 * 3600  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DOE JANE A", "Jane A Doe"),
        ("HUANG JEN HSUN", "Jen Hsun Huang"),
        ("Parker Nicholas P.", "Nicholas P. Parker"),
        ("O'BRIEN PATRICK J JR", "Patrick J O'Brien Jr"),
        ("MCCAFFERY MICHAEL G", "Michael G McCaffery"),
        ("VAN DER BERG JOHN", "John Van Der Berg"),
        ("Smith, John Q", "John Q Smith"),
        ("EXAMPLE VENTURES FUND II, L.P.", "Example Ventures Fund II, L.P."),
        ("BERKSHIRE HATHAWAY INC", "Berkshire Hathaway Inc"),
        ("PLATINUM EQUITY CAPITAL PARTNERS-A III LP", "Platinum Equity Capital Partners-A III LP"),
        ("Madonna", "Madonna"),
    ],
)
def test_names(raw: str, expected: str) -> None:
    assert n.normalize_person_or_entity(raw)[0] == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Common", "Common Stock"),
        ("COMMON STOCK, PAR VALUE $0.001 PER SHARE", "Common Stock"),
        ("Common Stock, $.01 par value", "Common Stock"),
        ("Class A Common", "Class A Common Stock"),
        ("class b common stock", "Class B Common Stock"),
        ("RSU", "Restricted Stock Units"),
        ("Restricted Stock Unit", "Restricted Stock Units"),
        ("Employee Stock Option (right to buy)", "Employee Stock Option (Right to Buy)"),
        ("Series B Convertible Preferred Stock", "Series B Convertible Preferred Stock"),
        ("AMERICAN DEPOSITARY SHARES", "American Depositary Shares"),
    ],
)
def test_security_titles(raw: str, expected: str) -> None:
    assert n.normalize_security_title(raw)[0] == expected


@pytest.mark.parametrize(
    ("title", "flags", "expected"),
    [
        ("President and CEO", {"is_officer": True}, "CEO"),
        ("EVP & Chief Financial Officer", {"is_officer": True}, "CFO"),
        ("Executive Vice President", {"is_officer": True}, "Officer"),
        ("Vice Chairman", {"is_officer": True}, "Officer"),
        ("Executive Chairman", {"is_officer": True}, "Chair"),
        ("EVP, General Counsel and Sec", {"is_officer": True}, "General Counsel"),
        ("Principal Accounting Officer", {"is_officer": True}, "CAO"),
        ("President", {"is_officer": True}, "President"),
        (None, {"is_director": True}, "Director"),
        (None, {"is_ten_percent": True}, "10% Owner"),
        (None, {"is_other": True}, "Other"),
        (None, {}, "Unknown"),
    ],
)
def test_roles(title: str | None, flags: dict[str, bool], expected: str) -> None:
    kwargs = {
        "is_officer": None,
        "is_director": None,
        "is_ten_percent": None,
        "is_other": None,
        "officer_title": title,
        "other_text": None,
    } | flags
    assert n.standard_role(**kwargs) == expected  # type: ignore[arg-type]


def test_normalize_cik() -> None:
    assert n.normalize_cik("999101") == ("0000999101", None)
    assert n.normalize_cik("ABC")[1] is not None
    assert n.normalize_cik(None) == (None, None)
