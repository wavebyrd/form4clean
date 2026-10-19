"""Parsed, uncleaned filing data.

Every value here is the exact string found in the SEC document (or None when the element is
absent). Nothing is converted, trimmed beyond XML whitespace, or inferred. The cleaning engine
works from these models and keeps them as the record of what the source said.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

TableName = str  # "non_derivative" | "derivative"


class FilingRef(BaseModel):
    """A filing listed in a company's EDGAR submissions history."""

    accession_number: str
    form_type: str
    filing_date: date
    report_date: str | None = None
    acceptance_datetime_listed: str | None = None
    primary_document: str | None = None


class ReportingOwner(BaseModel):
    cik: str | None = None
    name: str | None = None
    is_director: str | None = None
    is_officer: str | None = None
    is_ten_percent_owner: str | None = None
    is_other: str | None = None
    officer_title: str | None = None
    other_text: str | None = None


class ParsedTransaction(BaseModel):
    """One row of Table I (non-derivative) or Table II (derivative), as reported."""

    table: TableName
    sequence: int = Field(description="0-based position among transactions in its table")
    security_title: str | None = None
    transaction_date: str | None = None
    deemed_execution_date: str | None = None
    transaction_form_type: str | None = None
    transaction_code: str | None = None
    equity_swap_involved: str | None = None
    transaction_timeliness: str | None = None
    shares: str | None = None
    total_value: str | None = None
    price_per_share: str | None = None
    acquired_disposed_code: str | None = None
    shares_owned_after: str | None = None
    value_owned_after: str | None = None
    direct_or_indirect: str | None = None
    nature_of_ownership: str | None = None
    conversion_or_exercise_price: str | None = None
    exercise_date: str | None = None
    expiration_date: str | None = None
    underlying_security_title: str | None = None
    underlying_shares: str | None = None
    underlying_value: str | None = None
    footnote_ids: dict[str, list[str]] = Field(
        default_factory=dict, description="Footnote ids referenced, keyed by field name"
    )


class ParsedHolding(BaseModel):
    """A holding row (no transaction). Kept so source records are never dropped."""

    table: TableName
    sequence: int
    security_title: str | None = None
    shares_owned_after: str | None = None
    value_owned_after: str | None = None
    direct_or_indirect: str | None = None
    nature_of_ownership: str | None = None
    footnote_ids: dict[str, list[str]] = Field(default_factory=dict)


class ParsedFiling(BaseModel):
    """A full ownership filing: header metadata plus the parsed XML document."""

    accession_number: str
    form_type: str
    filing_date: str | None = None
    acceptance_datetime: str | None = None
    period_of_report: str | None = None
    document_type: str | None = None
    schema_version: str | None = None
    date_of_original_submission: str | None = None
    not_subject_to_section16: str | None = None
    issuer_cik: str | None = None
    issuer_name: str | None = None
    issuer_trading_symbol: str | None = None
    aff_10b5_one: str | None = None
    reporting_owners: list[ReportingOwner] = Field(default_factory=list)
    transactions: list[ParsedTransaction] = Field(default_factory=list)
    holdings: list[ParsedHolding] = Field(default_factory=list)
    footnotes: dict[str, str] = Field(default_factory=dict)
    remarks: str | None = None
    signature_date: str | None = None
    source_document: str | None = None
    sec_filing_url: str | None = None
    parse_warnings: list[str] = Field(default_factory=list)

    @property
    def is_amendment(self) -> bool:
        return self.form_type.upper().endswith("/A")
