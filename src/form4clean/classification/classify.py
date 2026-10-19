"""Classify a transaction from its code, table, and footnote evidence.

Rules, in order:

1. The SEC code fixes the category and transaction type (see codes.py). Unknown codes are
   classified ``Unknown`` with LOW confidence and flagged for review, never guessed.
2. Rule 10b5-1: the filing's 10b5-1 checkbox (forms since April 2023) or a footnote attached to
   the transaction. A footnote saying the trade was *not* under a plan wins over the checkbox.
3. Market execution, for P and S only: a footnote mentioning an open-market trade makes it
   true; a private, negotiated or underwritten trade makes it false; otherwise unknown.
4. Discretion: a 10b5-1 plan trade is never discretionary. P and S are discretionary only when
   the filing explicitly says no plan was used (checkbox present and unchecked). Other codes use
   the defaults in codes.py.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..models.enums import Category, Confidence, Direction
from .codes import CodeInfo, lookup

# Filers type the hyphens in "10b5-1" with several Unicode dash characters.
_10B51 = re.compile(r"10\s*b\s*[-\u2010-\u2015]?\s*5\s*[-\u2010-\u2015]\s*1", re.IGNORECASE)
_NOT_10B51 = re.compile(
    r"\bnot\b[^.;]{0,80}?10\s*b\s*[-\u2010-\u2015]?\s*5\s*[-\u2010-\u2015]\s*1", re.IGNORECASE
)
_OPEN_MARKET = re.compile(r"\bopen[-\s]market\b", re.IGNORECASE)
_NOT_MARKET = re.compile(
    r"\bprivately[-\s]negotiated\b|\bprivate (?:sale|purchase|transaction|placement)\b"
    r"|\bunderwritten\b|\bsecondary offering\b|\bblock trade\b",
    re.IGNORECASE,
)


@dataclass
class Classification:
    transaction_type: str
    category: Category
    direction: Direction
    is_market_transaction: bool | None
    is_discretionary_trade: bool | None
    is_10b5_1: bool | None
    is_10b5_1_source: str | None
    confidence: Confidence
    reasons: list[str] = field(default_factory=list)
    direction_mismatch: str | None = None
    unknown_code: bool = False

    @property
    def reason(self) -> str:
        return " ".join(self.reasons)


def _flag(value: str | None) -> bool | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("1", "true", "y", "yes"):
        return True
    if v in ("0", "false", "n", "no"):
        return False
    return None


def plan_status(
    aff_10b5_one: str | None, footnotes: Sequence[str], code: str | None
) -> tuple[bool | None, str | None, str]:
    """Rule 10b5-1 status for one transaction: (value, source, reason)."""
    text = " ".join(footnotes)
    if _NOT_10B51.search(text):
        return False, "footnote", "A footnote states the trade was not made under a 10b5-1 plan."
    if _10B51.search(text):
        return True, "footnote", "A footnote attached to the trade cites a Rule 10b5-1 plan."
    box = _flag(aff_10b5_one)
    if box is False:
        return False, "checkbox", "The filing's 10b5-1 checkbox is not checked."
    if box is True:
        if code in ("P", "S"):
            return True, "checkbox", "The filing's 10b5-1 checkbox is checked."
        return (
            None,
            None,
            "The filing's 10b5-1 checkbox is checked, but it covers the filing as a whole and no "
            "footnote ties this non-trade transaction to the plan.",
        )
    return None, None, "The filing predates the 10b5-1 checkbox and no footnote mentions a plan."


def classify(
    code: str | None,
    *,
    table: str,
    acquired_disposed: str | None,
    footnotes: Sequence[str] = (),
    aff_10b5_one: str | None = None,
) -> Classification:
    info: CodeInfo | None = lookup(code)
    ad = (acquired_disposed or "").strip().upper()
    direction = {"A": Direction.ACQUISITION, "D": Direction.DISPOSITION}.get(ad, Direction.UNKNOWN)
    norm_code = code.strip().upper() if code else None
    plan, plan_source, plan_reason = plan_status(aff_10b5_one, footnotes, norm_code)

    if info is None:
        label = f"Unrecognized code {code!r}" if code else "Missing transaction code"
        return Classification(
            transaction_type=label,
            category=Category.UNKNOWN,
            direction=direction,
            is_market_transaction=None,
            is_discretionary_trade=False if plan else None,
            is_10b5_1=plan,
            is_10b5_1_source=plan_source,
            confidence=Confidence.LOW,
            reasons=[
                f"{label}; it is not in the Form 4 code list, so it is not classified.",
                plan_reason,
            ],
            unknown_code=True,
        )

    reasons = [info.reason]
    market = info.is_market
    if info.code in ("P", "S"):
        text = " ".join(footnotes)
        if _NOT_MARKET.search(text):
            market = False
            reasons.append("A footnote describes a private, negotiated or underwritten trade.")
        elif _OPEN_MARKET.search(text):
            market = True
            reasons.append("A footnote says the trade was made in the open market.")

    if plan is True:
        discretionary: bool | None = False
    elif info.code in ("P", "S"):
        discretionary = True if plan is False else None
    else:
        discretionary = info.is_discretionary
    reasons.append(plan_reason)

    expected = info.expected_d if table == "derivative" else info.expected_nd
    mismatch = None
    if expected and ad in ("A", "D") and ad != expected:
        mismatch = (
            f"Code {info.code} in the {table.replace('_', '-')} table should be "
            f"{'an acquisition (A)' if expected == 'A' else 'a disposition (D)'}, but the filing "
            f"reports {ad}."
        )

    return Classification(
        transaction_type=info.description,
        category=info.category,
        direction=direction,
        is_market_transaction=market,
        is_discretionary_trade=discretionary,
        is_10b5_1=plan,
        is_10b5_1_source=plan_source,
        confidence=info.confidence if mismatch is None else Confidence.LOW,
        reasons=reasons,
        direction_mismatch=mismatch,
    )
