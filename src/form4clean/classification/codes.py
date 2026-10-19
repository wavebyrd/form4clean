"""The complete Form 4 transaction code taxonomy.

Codes and descriptions follow General Instruction 8 of SEC Form 4
(https://www.sec.gov/about/forms/form4data.pdf). Each code maps to a standardized category and
to default answers for the three-state questions in the schema. ``None`` means "cannot be
determined from the code alone".
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.enums import Category, Confidence


@dataclass(frozen=True)
class CodeInfo:
    code: str
    description: str
    group: str
    category: Category
    confidence: Confidence
    # Expected acquired/disposed code per table, or None if either is legitimate.
    expected_nd: str | None
    expected_d: str | None
    # Defaults before footnote and 10b5-1 evidence are applied.
    is_market: bool | None
    is_discretionary: bool | None
    reason: str


GENERAL = "General transaction codes"
RULE_16B3 = "Rule 16b-3 transaction codes"
DERIVATIVE = "Derivative securities codes"
EXEMPT = "Other Section 16(b) exempt transaction and small acquisition codes"
OTHER = "Other transaction codes"

_P_S_REASON = (
    "Code {code} covers both open-market and private {kind}s, so whether it was executed on an "
    "exchange is unknown unless a footnote says so."
)

CODES: dict[str, CodeInfo] = {
    c.code: c
    for c in [
        CodeInfo(
            "P",
            "Open market or private purchase",
            GENERAL,
            Category.MARKET_PURCHASE,
            Confidence.HIGH,
            "A",
            "A",
            None,
            None,
            _P_S_REASON.format(code="P", kind="purchase"),
        ),
        CodeInfo(
            "S",
            "Open market or private sale",
            GENERAL,
            Category.MARKET_SALE,
            Confidence.HIGH,
            "D",
            "D",
            None,
            None,
            _P_S_REASON.format(code="S", kind="sale"),
        ),
        CodeInfo(
            "V",
            "Transaction voluntarily reported earlier than required",
            GENERAL,
            Category.OTHER,
            Confidence.LOW,
            None,
            None,
            False,
            None,
            "Code V marks early voluntary reporting and does not describe the transaction.",
        ),
        CodeInfo(
            "A",
            "Grant, award or other acquisition from the issuer (Rule 16b-3(d))",
            RULE_16B3,
            Category.EQUITY_COMPENSATION,
            Confidence.MEDIUM,
            "A",
            "A",
            False,
            False,
            "Code A is an acquisition from the issuer, usually a compensation grant or award; "
            "it can also be another issuer-approved acquisition.",
        ),
        CodeInfo(
            "D",
            "Disposition to the issuer (Rule 16b-3(e))",
            RULE_16B3,
            Category.OTHER,
            Confidence.HIGH,
            "D",
            "D",
            False,
            False,
            "Code D is a disposition back to the issuer, such as a forfeiture or redemption.",
        ),
        CodeInfo(
            "F",
            "Payment of exercise price or tax liability by delivering or withholding securities",
            RULE_16B3,
            Category.TAX_RELATED,
            Confidence.HIGH,
            "D",
            "D",
            False,
            False,
            "Code F is shares withheld or delivered to cover tax or an exercise price, not a "
            "trading decision.",
        ),
        CodeInfo(
            "I",
            "Discretionary transaction under Rule 16b-3(f)",
            RULE_16B3,
            Category.OTHER,
            Confidence.HIGH,
            None,
            None,
            False,
            True,
            "Code I is a discretionary transaction within an employee benefit plan, such as "
            "moving money into or out of a company stock fund.",
        ),
        CodeInfo(
            "M",
            "Exercise or conversion of derivative security exempted under Rule 16b-3",
            RULE_16B3,
            Category.DERIVATIVE_EXERCISE,
            Confidence.MEDIUM,
            "A",
            "D",
            False,
            None,
            "Code M is the exercise or conversion of an exempt derivative, usually an employee "
            "stock option or vesting RSU.",
        ),
        CodeInfo(
            "C",
            "Conversion of derivative security",
            DERIVATIVE,
            Category.CONVERSION,
            Confidence.HIGH,
            "A",
            "D",
            False,
            None,
            "Code C is a conversion of a derivative security into the underlying.",
        ),
        CodeInfo(
            "E",
            "Expiration of short derivative position",
            DERIVATIVE,
            Category.OTHER,
            Confidence.HIGH,
            None,
            None,
            False,
            False,
            "Code E is the expiration of a short derivative position.",
        ),
        CodeInfo(
            "H",
            "Expiration (or cancellation) of long derivative position with value received",
            DERIVATIVE,
            Category.OTHER,
            Confidence.HIGH,
            None,
            "D",
            False,
            False,
            "Code H is the expiration or cancellation of a long derivative position.",
        ),
        CodeInfo(
            "O",
            "Exercise of out-of-the-money derivative security",
            DERIVATIVE,
            Category.DERIVATIVE_EXERCISE,
            Confidence.HIGH,
            "A",
            "D",
            False,
            None,
            "Code O is an exercise of an out-of-the-money derivative.",
        ),
        CodeInfo(
            "X",
            "Exercise of in-the-money or at-the-money derivative security",
            DERIVATIVE,
            Category.DERIVATIVE_EXERCISE,
            Confidence.HIGH,
            "A",
            "D",
            False,
            None,
            "Code X is an exercise of an in-the-money or at-the-money derivative.",
        ),
        CodeInfo(
            "G",
            "Bona fide gift",
            EXEMPT,
            Category.GIFT_OR_TRANSFER,
            Confidence.HIGH,
            None,
            None,
            False,
            False,
            "Code G is a gift. The giver reports a disposition and the recipient an acquisition.",
        ),
        CodeInfo(
            "L",
            "Small acquisition under Rule 16a-6",
            EXEMPT,
            Category.OTHER,
            Confidence.HIGH,
            "A",
            "A",
            False,
            None,
            "Code L is a small acquisition exempt under Rule 16a-6.",
        ),
        CodeInfo(
            "W",
            "Acquisition or disposition by will or the laws of descent and distribution",
            EXEMPT,
            Category.GIFT_OR_TRANSFER,
            Confidence.HIGH,
            None,
            None,
            False,
            False,
            "Code W is a transfer by will or inheritance.",
        ),
        CodeInfo(
            "Z",
            "Deposit into or withdrawal from voting trust",
            EXEMPT,
            Category.OTHER,
            Confidence.HIGH,
            None,
            None,
            False,
            False,
            "Code Z is a deposit into or withdrawal from a voting trust.",
        ),
        CodeInfo(
            "J",
            "Other acquisition or disposition (described in footnotes)",
            OTHER,
            Category.OTHER,
            Confidence.LOW,
            None,
            None,
            False,
            None,
            "Code J is a catch-all; the footnotes describe what happened.",
        ),
        CodeInfo(
            "K",
            "Transaction in equity swap or instrument with similar characteristics",
            OTHER,
            Category.OTHER,
            Confidence.HIGH,
            None,
            None,
            False,
            None,
            "Code K is an equity swap or similar instrument.",
        ),
        CodeInfo(
            "U",
            "Disposition pursuant to a tender of shares in a change of control transaction",
            OTHER,
            Category.OTHER,
            Confidence.HIGH,
            "D",
            "D",
            False,
            None,
            "Code U is a disposition by tendering shares in a change of control.",
        ),
    ]
}


def lookup(code: str | None) -> CodeInfo | None:
    if code is None:
        return None
    return CODES.get(code.strip().upper())
