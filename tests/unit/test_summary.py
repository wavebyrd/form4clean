from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl

from form4clean.summary import overview


def _frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    defaults: dict[str, object] = {
        "is_current": True,
        "is_10b5_1": None,
        "insider_cik": "0000000001",
        "insider_name": "Jane Doe",
        "insider_role": "CFO",
        "accession_number": "0000000001-25-000001",
    }
    return pl.DataFrame(
        [{**defaults, **row} for row in rows],
        schema_overrides={"transaction_value": pl.Decimal(38, 2)},
    )


def test_role_change_is_one_insider() -> None:
    df = _frame(
        [
            {
                "transaction_date": date(2025, 3, 3),
                "transaction_code": "S",
                "transaction_value": Decimal("100.10"),
            },
            {
                "transaction_date": date(2025, 9, 3),
                "transaction_code": "S",
                "transaction_value": Decimal("200.20"),
                "insider_role": "Other",
                "accession_number": "0000000001-25-000002",
            },
        ]
    )
    top = overview(df, today=date(2025, 12, 31))["top_insiders"]
    assert len(top) == 1
    assert top[0]["insider_role"] == "Other"  # the latest role
    assert top[0]["sold"] == Decimal("300.30")
    assert top[0]["trades"] == 2


def test_only_current_open_market_trades_count() -> None:
    df = _frame(
        [
            {
                "transaction_date": date(2025, 3, 3),
                "transaction_code": "P",
                "transaction_value": Decimal("50.00"),
            },
            {
                "transaction_date": date(2025, 3, 3),
                "transaction_code": "S",
                "transaction_value": Decimal("75.00"),
                "is_10b5_1": True,
            },
            {
                "transaction_date": date(2025, 3, 4),
                "transaction_code": "S",
                "transaction_value": Decimal("999.00"),
                "is_current": False,  # superseded by an amendment
            },
            {
                "transaction_date": date(2025, 3, 5),
                "transaction_code": "A",
                "transaction_value": None,
            },
        ]
    )
    result = overview(df, today=date(2025, 12, 31))
    assert result["purchases"]["value"] == Decimal("50.00")
    assert result["sales"] == {
        "count": 1,
        "value": Decimal("75.00"),
        "missing_value": 0,
        "planned_10b5_1": 1,
    }
    assert result["other_count"] == 1
    assert result["records_current"] == 3
