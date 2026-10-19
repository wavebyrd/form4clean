"""Column types for the standardized dataset, and conversion between records and DataFrames."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

import polars as pl

from .transaction import InsiderTransaction

ET = "America/New_York"
QTY = pl.Decimal(38, 10)
MONEY = pl.Decimal(38, 2)
OWNERS = pl.List(pl.Struct({"cik": pl.String, "name": pl.String}))
FOOTNOTES = pl.List(pl.Struct({"id": pl.String, "fields": pl.List(pl.String), "text": pl.String}))

CLEAN_SCHEMA: dict[str, pl.DataType] = {
    "transaction_id": pl.String(),
    "source_transaction_id": pl.String(),
    "accession_number": pl.String(),
    "form_type": pl.String(),
    "transaction_table": pl.String(),
    "sequence": pl.Int32(),
    "company_cik": pl.String(),
    "ticker": pl.String(),
    "company_name": pl.String(),
    "issuer_trading_symbol": pl.String(),
    "insider_cik": pl.String(),
    "insider_name": pl.String(),
    "insider_name_raw": pl.String(),
    "insider_role": pl.String(),
    "is_director": pl.Boolean(),
    "is_officer": pl.Boolean(),
    "is_ten_percent_owner": pl.Boolean(),
    "is_other_reporting_owner": pl.Boolean(),
    "officer_title": pl.String(),
    "other_relationship_text": pl.String(),
    "reporting_owners": OWNERS,
    "reporting_owner_count": pl.Int32(),
    "transaction_date": pl.Date(),
    "deemed_execution_date": pl.Date(),
    "filing_date": pl.Date(),
    "filing_timestamp": pl.Datetime("us", ET),
    "disclosure_timing": pl.String(),
    "disclosure_session_date": pl.Date(),
    "days_to_file": pl.Int32(),
    "transaction_code": pl.String(),
    "transaction_type": pl.String(),
    "transaction_category": pl.String(),
    "transaction_direction": pl.String(),
    "acquired_disposed_code": pl.String(),
    "equity_swap_involved": pl.Boolean(),
    "shares": QTY,
    "price_per_share": QTY,
    "transaction_value": MONEY,
    "shares_owned_after": QTY,
    "security_title": pl.String(),
    "security_title_raw": pl.String(),
    "is_derivative": pl.Boolean(),
    "underlying_security_title": pl.String(),
    "underlying_shares": QTY,
    "exercise_price": QTY,
    "exercise_date": pl.Date(),
    "expiration_date": pl.Date(),
    "ownership_type": pl.String(),
    "ownership_nature": pl.String(),
    "is_market_transaction": pl.Boolean(),
    "is_discretionary_trade": pl.Boolean(),
    "is_10b5_1": pl.Boolean(),
    "is_10b5_1_source": pl.String(),
    "classification_confidence": pl.String(),
    "classification_reason": pl.String(),
    "is_amended": pl.Boolean(),
    "amendment_status": pl.String(),
    "amends_accession_number": pl.String(),
    "superseded_by": pl.String(),
    "is_current": pl.Boolean(),
    "quality_status": pl.String(),
    "quality_flags": pl.List(pl.String()),
    "quality_explanations": pl.List(pl.String()),
    "footnotes": FOOTNOTES,
    "related_transaction_ids": pl.List(pl.String()),
    "sec_filing_url": pl.String(),
    "source_document": pl.String(),
    "source_values": pl.String(),
    "cleaning_version": pl.String(),
    "schema_version": pl.String(),
}

RAW_SCHEMA: dict[str, pl.DataType] = {
    "source_transaction_id": pl.String(),
    "accession_number": pl.String(),
    "form_type": pl.String(),
    "filing_date": pl.String(),
    "acceptance_datetime": pl.String(),
    "issuer_cik": pl.String(),
    "issuer_name": pl.String(),
    "issuer_trading_symbol": pl.String(),
    "reporting_owner_ciks": pl.String(),
    "reporting_owner_names": pl.String(),
    "table": pl.String(),
    "sequence": pl.Int32(),
    "security_title": pl.String(),
    "transaction_date": pl.String(),
    "deemed_execution_date": pl.String(),
    "transaction_code": pl.String(),
    "equity_swap_involved": pl.String(),
    "shares": pl.String(),
    "total_value": pl.String(),
    "price_per_share": pl.String(),
    "acquired_disposed_code": pl.String(),
    "shares_owned_after": pl.String(),
    "value_owned_after": pl.String(),
    "direct_or_indirect": pl.String(),
    "nature_of_ownership": pl.String(),
    "conversion_or_exercise_price": pl.String(),
    "exercise_date": pl.String(),
    "expiration_date": pl.String(),
    "underlying_security_title": pl.String(),
    "underlying_shares": pl.String(),
    "aff_10b5_one": pl.String(),
    "footnote_ids": pl.String(),
    "sec_filing_url": pl.String(),
}

# Columns that hold lists or structs. CSV cannot represent them, so CSV exports encode them as
# JSON text.
NESTED_COLUMNS = tuple(
    name for name, dtype in CLEAN_SCHEMA.items() if isinstance(dtype, (pl.List, pl.Struct))
)


def to_frame(records: Sequence[InsiderTransaction]) -> pl.DataFrame:
    rows = [r.model_dump(mode="python") for r in records]
    for row in rows:
        for key in (
            "transaction_category",
            "transaction_direction",
            "classification_confidence",
            "quality_status",
            "amendment_status",
            "disclosure_timing",
        ):
            row[key] = str(row[key]) if row[key] is not None else None
    return pl.DataFrame(rows, schema=CLEAN_SCHEMA, orient="row") if rows else empty_clean()


def empty_clean() -> pl.DataFrame:
    return pl.DataFrame(schema=CLEAN_SCHEMA)


def raw_frame(rows: Iterable[dict[str, Any]]) -> pl.DataFrame:
    data = list(rows)
    return (
        pl.DataFrame(data, schema=RAW_SCHEMA, orient="row")
        if data
        else pl.DataFrame(schema=RAW_SCHEMA)
    )


def flatten_nested(df: pl.DataFrame) -> pl.DataFrame:
    """Encode list and struct columns as JSON strings (for CSV)."""
    exprs = []
    for name in df.columns:
        if isinstance(df.schema[name], (pl.List, pl.Struct)):
            exprs.append(pl.col(name).map_elements(_json_cell, return_dtype=pl.String).alias(name))
    return df.with_columns(exprs) if exprs else df


def _json_cell(value: Any) -> str:
    if isinstance(value, pl.Series):
        value = value.to_list()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
