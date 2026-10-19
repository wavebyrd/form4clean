"""One filter definition shared by the Python API, CLI, HTTP API and dashboard.

Filters combine with AND. List filters match any of their values. Unset filters do nothing.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

import polars as pl
from pydantic import BaseModel, Field

TriState = Literal["true", "false", "unknown"]


class TransactionFilter(BaseModel):
    start: date | None = Field(None, description="Earliest date (inclusive), see date_field.")
    end: date | None = Field(None, description="Latest date (inclusive), see date_field.")
    date_field: Literal["transaction", "disclosure", "filing"] = Field(
        "transaction",
        description="Which date start/end apply to: transaction date, disclosure session date, "
        "or filing date.",
    )
    insiders: list[str] = Field(
        default_factory=list, description="Insider name substrings or CIKs (any match)."
    )
    roles: list[str] = Field(default_factory=list, description="Standardized roles, e.g. CEO.")
    categories: list[str] = Field(default_factory=list, description="Transaction categories.")
    codes: list[str] = Field(default_factory=list, description="SEC transaction codes.")
    direction: Literal["ACQUISITION", "DISPOSITION"] | None = None
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    min_shares: Decimal | None = None
    derivative: bool | None = Field(None, description="True: Table II only; False: Table I only.")
    ownership: Literal["Direct", "Indirect"] | None = None
    is_10b5_1: TriState | None = None
    amendment_statuses: list[str] = Field(default_factory=list)
    quality_statuses: list[str] = Field(default_factory=list)
    flags: list[str] = Field(
        default_factory=list, description="Quality flag codes; matches records with any of them."
    )
    include_superseded: bool = Field(
        False, description="Include records that are not in the current view."
    )
    search: str | None = Field(None, description="Case-insensitive text search.")

    def is_empty(self) -> bool:
        return self == TransactionFilter()

    def apply(self, df: pl.DataFrame) -> pl.DataFrame:
        exprs: list[pl.Expr] = []
        if not self.include_superseded:
            exprs.append(pl.col("is_current"))
        date_col = {
            "transaction": "transaction_date",
            "disclosure": "disclosure_session_date",
            "filing": "filing_date",
        }[self.date_field]
        if self.start:
            exprs.append(pl.col(date_col) >= self.start)
        if self.end:
            exprs.append(pl.col(date_col) <= self.end)
        if self.insiders:
            terms = [t.strip() for t in self.insiders if t.strip()]
            any_match = pl.lit(False)
            for term in terms:
                if term.isdigit():
                    any_match = any_match | (pl.col("insider_cik") == term.zfill(10))
                else:
                    needle = term.lower()
                    any_match = (
                        any_match
                        | pl.col("insider_name")
                        .str.to_lowercase()
                        .str.contains(needle, literal=True)
                        | pl.col("insider_name_raw")
                        .str.to_lowercase()
                        .str.contains(needle, literal=True)
                    )
            exprs.append(any_match.fill_null(False))
        if self.roles:
            exprs.append(pl.col("insider_role").is_in(self.roles))
        if self.categories:
            exprs.append(pl.col("transaction_category").is_in(self.categories))
        if self.codes:
            exprs.append(
                pl.col("transaction_code").str.to_uppercase().is_in([c.upper() for c in self.codes])
            )
        if self.direction:
            exprs.append(pl.col("transaction_direction") == self.direction)
        if self.min_value is not None:
            exprs.append(pl.col("transaction_value") >= self.min_value)
        if self.max_value is not None:
            exprs.append(pl.col("transaction_value") <= self.max_value)
        if self.min_shares is not None:
            exprs.append(pl.col("shares") >= self.min_shares)
        if self.derivative is not None:
            exprs.append(pl.col("is_derivative") == self.derivative)
        if self.ownership:
            exprs.append(pl.col("ownership_type") == self.ownership)
        if self.is_10b5_1 == "unknown":
            exprs.append(pl.col("is_10b5_1").is_null())
        elif self.is_10b5_1:
            exprs.append(pl.col("is_10b5_1") == (self.is_10b5_1 == "true"))
        if self.amendment_statuses:
            exprs.append(pl.col("amendment_status").is_in(self.amendment_statuses))
        if self.quality_statuses:
            exprs.append(pl.col("quality_status").is_in(self.quality_statuses))
        if self.flags:
            exprs.append(
                pl.any_horizontal([pl.col("quality_flags").list.contains(f) for f in self.flags])
            )
        if self.search and self.search.strip():
            needle = self.search.strip().lower()
            haystack = pl.concat_str(
                [
                    pl.col(c).cast(pl.String).fill_null("")
                    for c in (
                        "insider_name",
                        "insider_name_raw",
                        "officer_title",
                        "insider_role",
                        "transaction_type",
                        "transaction_category",
                        "transaction_code",
                        "security_title",
                        "accession_number",
                        "ownership_nature",
                    )
                ],
                separator=" ",
            ).str.to_lowercase()
            exprs.append(haystack.str.contains(needle, literal=True))
        if not exprs:
            return df
        combined = exprs[0]
        for e in exprs[1:]:
            combined = combined & e
        return df.filter(combined.fill_null(False))
