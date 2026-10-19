"""Controlled vocabularies used across the standardized schema."""

from __future__ import annotations

from enum import StrEnum


class Category(StrEnum):
    MARKET_PURCHASE = "Market Purchase"
    MARKET_SALE = "Market Sale"
    EQUITY_COMPENSATION = "Equity Compensation"
    DERIVATIVE_EXERCISE = "Derivative Exercise"
    TAX_RELATED = "Tax-Related"
    GIFT_OR_TRANSFER = "Gift or Transfer"
    CONVERSION = "Conversion"
    OTHER = "Other"
    UNKNOWN = "Unknown"


class Direction(StrEnum):
    ACQUISITION = "ACQUISITION"
    DISPOSITION = "DISPOSITION"
    UNKNOWN = "UNKNOWN"


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class QualityStatus(StrEnum):
    VALID = "VALID"
    WARNING = "WARNING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INVALID = "INVALID"

    @property
    def rank(self) -> int:
        return _STATUS_RANK[self]


_STATUS_RANK = {
    QualityStatus.VALID: 0,
    QualityStatus.WARNING: 1,
    QualityStatus.REVIEW_REQUIRED: 2,
    QualityStatus.INVALID: 3,
}


class Severity(StrEnum):
    """Severity of a single quality flag. INFO notes a fact without lowering the status."""

    INFO = "INFO"
    WARNING = "WARNING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INVALID = "INVALID"

    def to_status(self) -> QualityStatus:
        if self is Severity.INFO:
            return QualityStatus.VALID
        return QualityStatus(self.value)


class AmendmentStatus(StrEnum):
    ORIGINAL = "ORIGINAL"
    """From an original Form 4 that no amendment has touched."""
    SUPERSEDED = "SUPERSEDED"
    """Replaced by a matching record in a later amendment. Excluded from the current view."""
    ORIGINAL_NOT_RESTATED = "ORIGINAL_NOT_RESTATED"
    """From an amended filing, but the amendment did not restate this record. Still current."""
    AMENDED_RESTATED = "AMENDED_RESTATED"
    """Amendment record that repeats an earlier record with the same values."""
    AMENDED_CORRECTED = "AMENDED_CORRECTED"
    """Amendment record that replaces an earlier record with different values."""
    AMENDED_ADDED = "AMENDED_ADDED"
    """Amendment record with no counterpart in the earlier filing."""
    AMENDMENT_ORIGINAL_NOT_FOUND = "AMENDMENT_ORIGINAL_NOT_FOUND"
    """Amendment whose original filing is not in the dataset. Kept current, with a warning."""
    AMENDMENT_AMBIGUOUS = "AMENDMENT_AMBIGUOUS"
    """Amendment record that could not be matched confidently. Excluded from the current view."""
    NOT_RECONCILED = "NOT_RECONCILED"
    """Amendment reconciliation was turned off for this view."""


class DisclosureTiming(StrEnum):
    PRE_MARKET = "PRE_MARKET"
    MARKET_HOURS = "MARKET_HOURS"
    AFTER_CLOSE = "AFTER_CLOSE"
    NON_TRADING_DAY = "NON_TRADING_DAY"
    UNKNOWN = "UNKNOWN"
