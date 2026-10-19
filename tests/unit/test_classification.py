from __future__ import annotations

import pytest

from form4clean.classification.classify import classify, plan_status
from form4clean.classification.codes import CODES
from form4clean.models.enums import Category, Confidence, Direction

FORM_4_CODES = set("PSVADFIMCEHOXGLWZJKU")


def test_taxonomy_covers_every_form_4_code() -> None:
    assert set(CODES) == FORM_4_CODES


@pytest.mark.parametrize(
    ("code", "table", "ad", "category"),
    [
        ("P", "non_derivative", "A", Category.MARKET_PURCHASE),
        ("S", "non_derivative", "D", Category.MARKET_SALE),
        ("A", "non_derivative", "A", Category.EQUITY_COMPENSATION),
        ("F", "non_derivative", "D", Category.TAX_RELATED),
        ("M", "non_derivative", "A", Category.DERIVATIVE_EXERCISE),
        ("M", "derivative", "D", Category.DERIVATIVE_EXERCISE),
        ("X", "derivative", "D", Category.DERIVATIVE_EXERCISE),
        ("O", "derivative", "D", Category.DERIVATIVE_EXERCISE),
        ("C", "derivative", "D", Category.CONVERSION),
        ("G", "non_derivative", "D", Category.GIFT_OR_TRANSFER),
        ("W", "non_derivative", "A", Category.GIFT_OR_TRANSFER),
        ("D", "non_derivative", "D", Category.OTHER),
        ("J", "non_derivative", "A", Category.OTHER),
        ("K", "derivative", "A", Category.OTHER),
    ],
)
def test_categories(code: str, table: str, ad: str, category: Category) -> None:
    result = classify(code, table=table, acquired_disposed=ad)
    assert result.category is category
    assert result.direction_mismatch is None


def test_purchase_and_sale_market_execution_is_unknown_by_default() -> None:
    for code in ("P", "S"):
        result = classify(
            code, table="non_derivative", acquired_disposed="A" if code == "P" else "D"
        )
        assert result.is_market_transaction is None
        assert "open-market and private" in result.reason


def test_footnotes_resolve_market_execution() -> None:
    open_market = classify(
        "S",
        table="non_derivative",
        acquired_disposed="D",
        footnotes=["Shares were sold in open-market transactions."],
    )
    private = classify(
        "P",
        table="non_derivative",
        acquired_disposed="A",
        footnotes=["Purchased in a privately negotiated transaction."],
    )
    underwritten = classify(
        "S",
        table="non_derivative",
        acquired_disposed="D",
        footnotes=["Sold in an underwritten secondary offering."],
    )
    assert open_market.is_market_transaction is True
    assert private.is_market_transaction is False
    assert underwritten.is_market_transaction is False


def test_compensation_exercises_and_tax_are_not_discretionary_market_trades() -> None:
    award = classify("A", table="non_derivative", acquired_disposed="A")
    exercise = classify("M", table="non_derivative", acquired_disposed="A")
    tax = classify("F", table="non_derivative", acquired_disposed="D")
    for result in (award, exercise, tax):
        assert result.is_market_transaction is False
    assert award.is_discretionary_trade is False
    assert tax.is_discretionary_trade is False
    assert exercise.is_discretionary_trade is None


@pytest.mark.parametrize(
    ("aff", "notes", "code", "expected", "source"),
    [
        ("1", [], "S", True, "checkbox"),
        ("0", [], "S", False, "checkbox"),
        (None, [], "S", None, None),
        (None, ["Effected pursuant to a Rule 10b5-1 trading plan."], "S", True, "footnote"),
        (
            None,
            ["Sold under a 10b5\N{NON-BREAKING HYPHEN}1 plan adopted May 1."],
            "S",
            True,
            "footnote",
        ),
        ("1", ["This sale was not made pursuant to a Rule 10b5-1 plan."], "S", False, "footnote"),
        ("1", [], "A", None, None),
    ],
)
def test_10b5_1_status(
    aff: str | None, notes: list[str], code: str, expected: bool | None, source: str | None
) -> None:
    value, src, reason = plan_status(aff, notes, code)
    assert value is expected
    assert src == source
    assert reason


def test_plan_trades_are_not_discretionary() -> None:
    planned = classify("S", table="non_derivative", acquired_disposed="D", aff_10b5_one="1")
    unplanned = classify("S", table="non_derivative", acquired_disposed="D", aff_10b5_one="0")
    unknown = classify("S", table="non_derivative", acquired_disposed="D")
    assert planned.is_discretionary_trade is False
    assert unplanned.is_discretionary_trade is True
    assert unknown.is_discretionary_trade is None


def test_unrecognized_code_is_unknown_not_guessed() -> None:
    result = classify("Q", table="non_derivative", acquired_disposed="A")
    assert result.category is Category.UNKNOWN
    assert result.confidence is Confidence.LOW
    assert result.unknown_code


def test_missing_code() -> None:
    result = classify(None, table="non_derivative", acquired_disposed=None)
    assert result.category is Category.UNKNOWN
    assert result.direction is Direction.UNKNOWN


def test_direction_mismatch_lowers_confidence() -> None:
    result = classify("P", table="non_derivative", acquired_disposed="D")
    assert result.direction_mismatch is not None
    assert result.confidence is Confidence.LOW
    assert result.direction is Direction.DISPOSITION


def test_codes_are_case_insensitive() -> None:
    assert classify("s", table="non_derivative", acquired_disposed="d").category is (
        Category.MARKET_SALE
    )
