"""The standardized insider transaction record (schema version in ``form4clean.versions``).

Field descriptions here are the source of truth for docs/schema.md, which is generated from them
by ``scripts/generate_schema_docs.py`` and checked in tests.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from .enums import AmendmentStatus, Category, Confidence, Direction, DisclosureTiming, QualityStatus


class OwnerRef(BaseModel):
    cik: str | None
    name: str | None


class FootnoteRef(BaseModel):
    id: str
    fields: list[str]
    text: str | None


class QualityFlag(BaseModel):
    code: str
    severity: str
    message: str


class InsiderTransaction(BaseModel):
    # Identity and provenance
    transaction_id: str = Field(
        description="Stable identifier: 'f4c_' plus the first 20 hex characters of SHA-256 over "
        "source_transaction_id. Unchanged when the same filing is processed again."
    )
    source_transaction_id: str = Field(
        description="Position of the record in its source filing: '{accession}:{ND|D}:{sequence}' (ND = "
        "Table I non-derivative, D = Table II derivative, sequence is 0-based)."
    )
    accession_number: str = Field(
        description="SEC accession number of the filing, e.g. 0001197647-26-000011."
    )
    form_type: str = Field(description="Form type from the filing header: '4' or '4/A'.")
    transaction_table: str = Field(
        description="'non_derivative' (Table I) or 'derivative' (Table II)."
    )
    sequence: int = Field(description="0-based position among transactions in its table.")

    # Issuer
    company_cik: str = Field(description="Issuer CIK, 10 digits with leading zeros.")
    ticker: str | None = Field(
        description="Ticker of the company the dataset was built for, from SEC's ticker file. Null if the "
        "company has no current ticker."
    )
    company_name: str | None = Field(description="Issuer name as reported in the filing.")
    issuer_trading_symbol: str | None = Field(
        description="Trading symbol exactly as reported in the filing, which may differ from the current "
        "ticker."
    )

    # Insider
    insider_cik: str | None = Field(description="CIK of the first reporting owner, 10 digits.")
    insider_name: str | None = Field(
        description="Display name of the first reporting owner. Individuals reported as 'LAST FIRST' are "
        "reordered to 'First Last'; entity names keep their order. See insider_name_raw."
    )
    insider_name_raw: str | None = Field(description="Reporting owner name exactly as filed.")
    insider_role: str = Field(
        description="Primary standardized role: CEO, CFO, COO, President, Chair, General Counsel, CTO, "
        "CAO, Officer, Director, 10% Owner, Other or Unknown."
    )
    is_director: bool | None = Field(description="Reporting owner relationship box: director.")
    is_officer: bool | None = Field(description="Reporting owner relationship box: officer.")
    is_ten_percent_owner: bool | None = Field(
        description="Reporting owner relationship box: 10% owner."
    )
    is_other_reporting_owner: bool | None = Field(
        description="Reporting owner relationship box: other."
    )
    officer_title: str | None = Field(description="Officer title as filed, whitespace-normalized.")
    other_relationship_text: str | None = Field(
        description="Text describing an 'other' relationship."
    )
    reporting_owners: list[OwnerRef] = Field(
        description="All reporting owners on the filing. Joint filings report one set of transactions for "
        "several owners; the record is kept once, not once per owner, so shares are not "
        "double-counted."
    )
    reporting_owner_count: int = Field(description="Number of reporting owners on the filing.")

    # Dates and disclosure
    transaction_date: date | None = Field(description="Date the transaction was executed.")
    deemed_execution_date: date | None = Field(description="Deemed execution date, if reported.")
    filing_date: date | None = Field(
        description="SEC filing date from the header. Filings accepted after 5:30 p.m. Eastern receive the "
        "next business day's filing date."
    )
    filing_timestamp: datetime | None = Field(
        description="Time the SEC accepted the filing (US Eastern, timezone-aware), from the filing header's "
        "ACCEPTANCE-DATETIME. This is when the information became public."
    )
    disclosure_timing: DisclosureTiming = Field(
        description="When the filing was accepted relative to regular NYSE hours: PRE_MARKET, "
        "MARKET_HOURS, AFTER_CLOSE, NON_TRADING_DAY or UNKNOWN."
    )
    disclosure_session_date: date | None = Field(
        description="First regular trading session during which the filing was public: the same day if "
        "accepted before the close of a trading day, otherwise the next trading day."
    )
    days_to_file: int | None = Field(
        description="Calendar days from transaction_date to filing_date."
    )

    # Classification
    transaction_code: str | None = Field(
        description="SEC transaction code exactly as filed (e.g. P, S, M)."
    )
    transaction_type: str = Field(description="Plain-language description of the transaction code.")
    transaction_category: Category = Field(
        description="Standardized category. See docs/classification.md."
    )
    transaction_direction: Direction = Field(
        description="ACQUISITION or DISPOSITION, from the acquired/disposed code (A/D), or UNKNOWN."
    )
    acquired_disposed_code: str | None = Field(
        description="Acquired (A) / disposed (D) code as filed."
    )
    equity_swap_involved: bool | None = Field(description="Equity swap box as filed.")

    # Amounts
    shares: Decimal | None = Field(
        description="Number of securities in the transaction. For derivative rows, the number of derivative "
        "securities. Exact decimal."
    )
    price_per_share: Decimal | None = Field(
        description="Price per security as filed. Null when the filing gives no price. Often a weighted "
        "average; see footnotes."
    )
    transaction_value: Decimal | None = Field(
        description="shares x price_per_share, rounded half-up to cents. Null when either is missing or the "
        "price is zero (gifts and awards have no market value at a zero price)."
    )
    shares_owned_after: Decimal | None = Field(
        description="Securities owned following the transaction."
    )

    # Security
    security_title: str | None = Field(description="Security title after normalization rules.")
    security_title_raw: str | None = Field(description="Security title exactly as filed.")
    is_derivative: bool = Field(description="True for Table II (derivative) rows.")
    underlying_security_title: str | None = Field(
        description="Derivative rows: underlying security title."
    )
    underlying_shares: Decimal | None = Field(
        description="Derivative rows: number of underlying securities."
    )
    exercise_price: Decimal | None = Field(
        description="Derivative rows: conversion or exercise price."
    )
    exercise_date: date | None = Field(description="Derivative rows: date exercisable.")
    expiration_date: date | None = Field(description="Derivative rows: expiration date.")

    # Ownership
    ownership_type: str | None = Field(
        description="'Direct' or 'Indirect', from the D/I code. Null if absent."
    )
    ownership_nature: str | None = Field(
        description="Nature of indirect ownership as filed, e.g. 'By Trust'."
    )

    # Trade characteristics (three-state: true, false, null = unknown)
    is_market_transaction: bool | None = Field(
        description="Whether the trade was executed in the open market. Null for P and S codes unless a "
        "footnote says open market or private; false for all other codes."
    )
    is_discretionary_trade: bool | None = Field(
        description="Whether the insider chose the timing of the trade. False for awards, exercises, tax "
        "withholding and 10b5-1 plan trades; null when it cannot be determined."
    )
    is_10b5_1: bool | None = Field(
        description="Whether the trade was made under a Rule 10b5-1 plan. From the filing's 10b5-1 "
        "checkbox (forms since April 2023) or a footnote; null when unknown."
    )
    is_10b5_1_source: str | None = Field(description="'checkbox', 'footnote', or null.")
    classification_confidence: Confidence = Field(description="HIGH, MEDIUM or LOW.")
    classification_reason: str = Field(description="Why the record was classified this way.")

    # Amendments
    is_amended: bool = Field(
        description="True when this record comes from an amendment (Form 4/A)."
    )
    amendment_status: AmendmentStatus = Field(
        description="Reconciliation outcome. See docs/amendments.md."
    )
    amends_accession_number: str | None = Field(
        description="For amendment records: accession number of the filing it was reconciled against."
    )
    superseded_by: str | None = Field(
        description="transaction_id of the record that replaced this one."
    )
    is_current: bool = Field(
        description="True when the record belongs to the current view (not superseded, not ambiguous)."
    )

    # Quality
    quality_status: QualityStatus = Field(description="VALID, WARNING, REVIEW_REQUIRED or INVALID.")
    quality_flags: list[str] = Field(
        description="Codes of every quality check that fired, including INFO."
    )
    quality_explanations: list[str] = Field(
        description="Plain-language explanation for each flag, same order."
    )

    # Context
    footnotes: list[FootnoteRef] = Field(
        description="Footnotes referenced by this record, with the fields that reference them."
    )
    related_transaction_ids: list[str] = Field(
        description="Records that are probably part of the same economic event: the two legs of an option "
        "exercise, or the same trade reported by several joint filers."
    )
    sec_filing_url: str | None = Field(description="Link to the filing index on sec.gov.")
    source_document: str | None = Field(
        description="File name of the ownership XML within the filing."
    )
    source_values: str = Field(
        description="JSON object of the original source strings for this record."
    )
    cleaning_version: str = Field(
        description="Version of the cleaning rules that produced the record."
    )
    schema_version: str = Field(description="Version of this schema.")
