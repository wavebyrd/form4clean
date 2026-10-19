"""Summary statistics for the dashboard overview.

All sums use exact decimals and only records in the current view. Purchases and sales are the
P and S codes; awards, exercises, tax withholding and gifts are reported separately because they
are not trading decisions.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import polars as pl


def _sum(df: pl.DataFrame, col: str) -> Decimal:
    if df.height == 0:
        return Decimal(0)
    value = df.get_column(col).drop_nulls().sum()
    return Decimal(str(value)) if value is not None else Decimal(0)


def overview(df: pl.DataFrame, *, today: date | None = None, months: int = 12) -> dict[str, Any]:
    today = today or date.today()
    since = today - timedelta(days=round(30.44 * months))
    current = df.filter(pl.col("is_current"))
    window = current.filter(pl.col("transaction_date") >= since)
    buys = window.filter(pl.col("transaction_code") == "P")
    sells = window.filter(pl.col("transaction_code") == "S")
    planned = sells.filter(pl.col("is_10b5_1") == True)  # noqa: E712

    # Group by CIK only: an insider whose role changes (CFO, then adviser) is still one person.
    # Name and role come from their latest trade.
    top = (
        window.filter(pl.col("transaction_code").is_in(["P", "S"]))
        .sort("transaction_date", "accession_number")
        .group_by("insider_cik")
        .agg(
            pl.col("insider_name").last(),
            pl.col("insider_role").last(),
            pl.col("transaction_value")
            .filter(pl.col("transaction_code") == "P")
            .sum()
            .alias("purchased"),
            pl.col("transaction_value")
            .filter(pl.col("transaction_code") == "S")
            .sum()
            .alias("sold"),
            pl.len().alias("trades"),
        )
        .with_columns((pl.col("purchased") + pl.col("sold")).alias("total"))
        .sort("total", descending=True, nulls_last=True)
        .head(8)
    )
    monthly = (
        current.filter(
            pl.col("transaction_code").is_in(["P", "S"]) & pl.col("transaction_date").is_not_null()
        )
        .with_columns(pl.col("transaction_date").dt.truncate("1mo").alias("month"))
        .group_by("month")
        .agg(
            pl.col("transaction_value")
            .filter(pl.col("transaction_code") == "P")
            .sum()
            .alias("purchases"),
            pl.col("transaction_value")
            .filter(pl.col("transaction_code") == "S")
            .sum()
            .alias("sales"),
        )
        .sort("month")
    )
    dates = current.get_column("transaction_date").drop_nulls()
    return {
        "window_start": since,
        "window_months": months,
        "purchases": {
            "count": buys.height,
            "value": _sum(buys, "transaction_value"),
            "missing_value": buys.filter(pl.col("transaction_value").is_null()).height,
        },
        "sales": {
            "count": sells.height,
            "value": _sum(sells, "transaction_value"),
            "missing_value": sells.filter(pl.col("transaction_value").is_null()).height,
            "planned_10b5_1": planned.height,
        },
        "other_count": window.height - buys.height - sells.height,
        "insiders": window.get_column("insider_cik").n_unique() if window.height else 0,
        "records_total": df.height,
        "records_current": current.height,
        "first_transaction": dates.min() if dates.len() else None,
        "last_transaction": dates.max() if dates.len() else None,
        "top_insiders": top.to_dicts(),
        "monthly": monthly.to_dicts(),
    }
