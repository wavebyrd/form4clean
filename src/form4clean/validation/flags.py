"""Registry of data quality checks.

Every flag the engine can raise is defined here once, with what it detects, why it matters,
what the engine did about it, and whether a person should look at the record. The quality
report and the dashboard read their explanations from this registry.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.enums import Severity


@dataclass(frozen=True)
class FlagDef:
    code: str
    severity: Severity
    title: str
    why: str
    action: str
    review: bool


_I, _W, _R, _X = Severity.INFO, Severity.WARNING, Severity.REVIEW_REQUIRED, Severity.INVALID

FLAGS: dict[str, FlagDef] = {
    f.code: f
    for f in [
        # Required values
        FlagDef(
            "MISSING_TRANSACTION_CODE",
            _R,
            "Transaction code is missing",
            "Without a code the transaction cannot be classified.",
            "Kept the record and classified it as Unknown.",
            True,
        ),
        FlagDef(
            "UNRECOGNIZED_TRANSACTION_CODE",
            _R,
            "Transaction code is not a Form 4 code",
            "An unknown code may be a typo or a new SEC code; guessing could misclassify it.",
            "Kept the record and classified it as Unknown.",
            True,
        ),
        FlagDef(
            "MISSING_TRANSACTION_DATE",
            _R,
            "Transaction date is missing",
            "The record cannot be placed in time, so date filters and charts will skip it.",
            "Kept the record with a null transaction date.",
            True,
        ),
        FlagDef(
            "INVALID_TRANSACTION_DATE",
            _R,
            "Transaction date cannot be read",
            "The source date is not a valid calendar date.",
            "Set the transaction date to null and kept the source value.",
            True,
        ),
        FlagDef(
            "MISSING_SHARES",
            _R,
            "Share quantity is missing",
            "Totals and transaction values cannot include this record.",
            "Kept the record with null shares.",
            True,
        ),
        FlagDef(
            "VALUE_REPORTED_INSTEAD_OF_SHARES",
            _I,
            "Total value reported instead of shares",
            "Some derivative transactions are reported by total value, not quantity.",
            "Kept the reported total value in source_values; shares are null.",
            False,
        ),
        FlagDef(
            "INVALID_SHARES",
            _X,
            "Share quantity is not a valid number",
            "The quantity cannot be used in any calculation.",
            "Set shares to null and kept the source value.",
            True,
        ),
        FlagDef(
            "INVALID_PRICE",
            _X,
            "Price is not a valid number",
            "The price cannot be used in any calculation.",
            "Set the price to null and kept the source value.",
            True,
        ),
        FlagDef(
            "INVALID_NUMBER",
            _W,
            "A numeric field is not a valid number",
            "A secondary amount, such as holdings after the transaction, cannot be used.",
            "Set that field to null and kept the source value.",
            False,
        ),
        FlagDef(
            "NEGATIVE_AMOUNT",
            _R,
            "A quantity or price is negative",
            "Form 4 amounts are reported as positive numbers with an A/D direction.",
            "Kept the value as filed.",
            True,
        ),
        # Prices and values
        FlagDef(
            "MISSING_PRICE",
            _W,
            "Purchase or sale has no price",
            "The transaction value cannot be calculated for a trade that should have one.",
            "Left price and transaction value null. Nothing was estimated.",
            False,
        ),
        FlagDef(
            "MISSING_PRICE_NON_TRADE",
            _I,
            "No price reported",
            "Awards, gifts and similar transactions often have no price.",
            "Left price and transaction value null.",
            False,
        ),
        FlagDef(
            "ZERO_PRICE_TRADE",
            _R,
            "Purchase or sale reported at a price of zero",
            "A zero-price purchase or sale is unusual and may be a filing error or a "
            "non-market transfer.",
            "Kept the zero price; transaction value is null.",
            True,
        ),
        FlagDef(
            "ZERO_PRICE",
            _I,
            "Price reported as zero",
            "Common for awards and gifts; there is no market value to compute.",
            "Kept the zero price; transaction value is null.",
            False,
        ),
        FlagDef(
            "WEIGHTED_AVERAGE_PRICE",
            _I,
            "Price is a weighted average",
            "The trade was executed in several lots; the footnote gives the price range.",
            "Kept the reported average price.",
            False,
        ),
        FlagDef(
            "PRICE_OUTLIER",
            _W,
            "Price differs sharply from nearby trades",
            "The price is more than 50% away from the median price of other purchases and "
            "sales of the same company within seven days. It may be a typo, a stock split, "
            "or a different security.",
            "Kept the price as filed.",
            True,
        ),
        # Dates
        FlagDef(
            "TRANSACTION_AFTER_FILING",
            _R,
            "Transaction date is after the filing date",
            "A filing cannot report a trade that has not happened yet.",
            "Kept both dates as filed.",
            True,
        ),
        FlagDef(
            "LATE_FILING",
            _I,
            "Filed more than two business days after the transaction",
            "Form 4 is generally due within two business days. Late filings delay public "
            "disclosure. Business days are approximated with the NYSE calendar.",
            "No change; noted for research.",
            False,
        ),
        FlagDef(
            "MISSING_FILING_TIMESTAMP",
            _W,
            "Acceptance timestamp is missing",
            "Without it the disclosure time and point-in-time views fall back to the filing date.",
            "Treated the filing as public at 5:30 p.m. Eastern on its filing date, "
            "the latest time that keeps that date, so point-in-time views never see it early.",
            False,
        ),
        # Direction and ownership
        FlagDef(
            "MISSING_ACQUIRED_DISPOSED",
            _W,
            "Acquired/disposed code is missing",
            "The direction of the trade is unknown.",
            "Set direction to UNKNOWN.",
            False,
        ),
        FlagDef(
            "DIRECTION_CODE_MISMATCH",
            _R,
            "Direction contradicts the transaction code",
            "For example, a purchase (P) reported as a disposition. One of the two fields "
            "is probably wrong.",
            "Kept both as filed and lowered classification confidence to LOW.",
            True,
        ),
        FlagDef(
            "MISSING_OWNERSHIP_TYPE",
            _W,
            "Direct/indirect ownership is missing",
            "Ownership filters will not include this record.",
            "Left ownership_type null.",
            False,
        ),
        FlagDef(
            "INVALID_OWNERSHIP_TYPE",
            _W,
            "Direct/indirect code is not D or I",
            "The ownership type cannot be determined.",
            "Left ownership_type null.",
            False,
        ),
        FlagDef(
            "INDIRECT_WITHOUT_NATURE",
            _W,
            "Indirect ownership with no nature given",
            "Form 4 asks filers to describe indirect ownership (e.g. 'By Trust').",
            "No change.",
            False,
        ),
        FlagDef(
            "DIRECT_WITH_NATURE",
            _W,
            "Direct ownership with an indirect-ownership note",
            "The ownership fields contradict each other.",
            "Kept both as filed.",
            False,
        ),
        FlagDef(
            "HOLDINGS_INCONSISTENT",
            _W,
            "Holdings after the trade do not follow",
            "Shares owned after this transaction differ from the previous row's holdings "
            "plus or minus this trade, for the same security and ownership. Rows may be out "
            "of order, or an amount may be wrong.",
            "Kept the values as filed.",
            False,
        ),
        # Insider identity
        FlagDef(
            "MISSING_INSIDER_CIK",
            _W,
            "Reporting owner has no CIK",
            "The insider cannot be reliably matched across filings.",
            "Kept the name; insider_cik is null.",
            False,
        ),
        FlagDef(
            "INVALID_INSIDER_CIK",
            _W,
            "Reporting owner CIK is not valid",
            "The insider cannot be reliably matched across filings.",
            "Set insider_cik to null and kept the source value.",
            False,
        ),
        FlagDef(
            "MULTIPLE_REPORTING_OWNERS",
            _I,
            "Joint filing with several reporting owners",
            "The same transaction is reported for several owners. Counting it once per "
            "owner would double-count shares.",
            "Kept one record, attributed to the first owner, with all owners listed in "
            "reporting_owners.",
            False,
        ),
        # Duplicates and relationships
        FlagDef(
            "POSSIBLE_DUPLICATE_IN_FILING",
            _W,
            "Identical row in the same filing",
            "Two rows have identical values. They may be separate trades or a duplicate.",
            "Kept both rows.",
            True,
        ),
        FlagDef(
            "POSSIBLE_DUPLICATE_ACROSS_FILINGS",
            _W,
            "Same trade appears in another filing",
            "Another filing reports a trade with the same date, code, shares and price. "
            "Often several related owners (a fund and its general partner) file separately "
            "for one trade, which would double-count it.",
            "Kept all records and linked them in related_transaction_ids.",
            True,
        ),
        # Amendments
        FlagDef(
            "SUPERSEDED",
            _I,
            "Replaced by an amendment",
            "A later Form 4/A restates or corrects this record.",
            "Excluded from the current view; kept in the full and point-in-time views.",
            False,
        ),
        FlagDef(
            "AMENDMENT_ORIGINAL_NOT_FOUND",
            _W,
            "Original filing not found for amendment",
            "The amended filing could not be linked to an original in this dataset, often "
            "because it falls outside the fetched date range.",
            "Kept the amendment's records in the current view.",
            False,
        ),
        FlagDef(
            "AMENDMENT_AMBIGUOUS",
            _R,
            "Amendment could not be matched confidently",
            "Several originals could be the one amended, or the amended rows do not line up "
            "with the original rows.",
            "Excluded this amendment record from the current view; the earlier records stay "
            "current.",
            True,
        ),
        FlagDef(
            "AMENDMENT_MATCHED_BY_POSITION",
            _W,
            "Amendment matched by row position",
            "The amended row changes the date, code or security, so it was matched to the "
            "original row in the same position.",
            "Replaced the original row with the amended row.",
            False,
        ),
        FlagDef(
            "AMENDMENT_MAY_REMOVE",
            _R,
            "Amendment did not restate this record",
            "The amendment's table has no rows, which can mean the record was reported in "
            "error and removed.",
            "Kept the record in the current view.",
            True,
        ),
        FlagDef(
            "ORIGINAL_NOT_RESTATED",
            _I,
            "Not restated by the amendment",
            "The filing was amended, but this record was not part of the amendment.",
            "Kept the record in the current view.",
            False,
        ),
        # Filing-level
        FlagDef(
            "FOOTNOTE_NOT_FOUND",
            _W,
            "Referenced footnote is missing",
            "A field cites a footnote that is not in the filing.",
            "Kept the footnote id with no text.",
            False,
        ),
        FlagDef(
            "NOT_SUBJECT_TO_SECTION_16",
            _I,
            "Filer is no longer subject to Section 16",
            "The filer checked the box indicating it is no longer subject to Section 16.",
            "No change.",
            False,
        ),
    ]
}


def severity(code: str) -> Severity:
    return FLAGS[code].severity
