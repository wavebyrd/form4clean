from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from form4clean.cleaning.pipeline import clean
from form4clean.exports.writer import sha256, write_frame
from form4clean.models.schema import CLEAN_SCHEMA, to_frame
from form4clean.models.transaction import InsiderTransaction
from form4clean.query import TransactionFilter
from tests.conftest import COMPANY, all_parsed


@pytest.fixture(scope="module")
def frame() -> pl.DataFrame:
    return to_frame(clean(all_parsed(), COMPANY).transactions)


def test_schema_matches_model() -> None:
    assert list(CLEAN_SCHEMA) == list(InsiderTransaction.model_fields)


def test_frame_types(frame: pl.DataFrame) -> None:
    assert frame.schema["price_per_share"] == pl.Decimal(38, 10)
    assert frame.schema["transaction_value"] == pl.Decimal(38, 2)
    assert frame.schema["filing_timestamp"] == pl.Datetime("us", "America/New_York")


def test_default_filter_is_current_view(frame: pl.DataFrame) -> None:
    current = TransactionFilter().apply(frame)
    assert current.height == frame.filter(pl.col("is_current")).height
    everything = TransactionFilter(include_superseded=True).apply(frame)
    assert everything.height == frame.height


@pytest.mark.parametrize(
    ("flt", "check"),
    [
        (TransactionFilter(codes=["s"]), lambda r: r["transaction_code"] == "S"),
        (TransactionFilter(roles=["CEO", "CFO"]), lambda r: r["insider_role"] in ("CEO", "CFO")),
        (
            TransactionFilter(categories=["Market Purchase"]),
            lambda r: r["transaction_category"] == "Market Purchase",
        ),
        (
            TransactionFilter(min_value=Decimal("100000")),
            lambda r: r["transaction_value"] >= 100000,
        ),
        (
            TransactionFilter(max_value=Decimal("100000")),
            lambda r: r["transaction_value"] <= 100000,
        ),
        (TransactionFilter(min_shares=Decimal("5000")), lambda r: r["shares"] >= 5000),
        (TransactionFilter(derivative=True), lambda r: r["is_derivative"]),
        (TransactionFilter(ownership="Indirect"), lambda r: r["ownership_type"] == "Indirect"),
        (TransactionFilter(is_10b5_1="true"), lambda r: r["is_10b5_1"] is True),
        (TransactionFilter(is_10b5_1="unknown"), lambda r: r["is_10b5_1"] is None),
        (
            TransactionFilter(direction="ACQUISITION"),
            lambda r: r["transaction_direction"] == "ACQUISITION",
        ),
        (TransactionFilter(insiders=["doe"]), lambda r: "Doe" in r["insider_name"]),
        (TransactionFilter(insiders=["999102"]), lambda r: r["insider_cik"] == "0000999102"),
        (
            TransactionFilter(quality_statuses=["INVALID"]),
            lambda r: r["quality_status"] == "INVALID",
        ),
        (
            TransactionFilter(flags=["MISSING_PRICE"]),
            lambda r: "MISSING_PRICE" in r["quality_flags"],
        ),
        (
            TransactionFilter(search="ventures"),
            lambda r: "Ventures" in (r["insider_name"] + (r["ownership_nature"] or "")),
        ),
        (
            TransactionFilter(start=date(2025, 4, 1), end=date(2025, 4, 30)),
            lambda r: date(2025, 4, 1) <= r["transaction_date"] <= date(2025, 4, 30),
        ),
        (
            TransactionFilter(start=date(2025, 6, 10), date_field="disclosure"),
            lambda r: r["disclosure_session_date"] >= date(2025, 6, 10),
        ),
    ],
)
def test_filters(frame: pl.DataFrame, flt: TransactionFilter, check: object) -> None:
    out = flt.apply(frame)
    assert out.height > 0, "filter fixture should match something"
    assert out.height <= frame.height
    for row in out.iter_rows(named=True):
        assert check(row)  # type: ignore[operator]


def test_combined_filters(frame: pl.DataFrame) -> None:
    flt = TransactionFilter(
        roles=["CEO", "CFO"],
        categories=["Market Sale"],
        min_value=Decimal("100000"),
        start=date(2022, 1, 1),
    )
    out = flt.apply(frame)
    assert set(out["insider_role"]) <= {"CEO", "CFO"}
    assert out.height == 4


@pytest.mark.parametrize("fmt", ["csv", "parquet", "json"])
def test_exports_are_deterministic(frame: pl.DataFrame, tmp_path: Path, fmt: str) -> None:
    a = write_frame(frame, tmp_path / f"a.{fmt}", fmt)  # type: ignore[arg-type]
    b = write_frame(frame, tmp_path / f"b.{fmt}", fmt)  # type: ignore[arg-type]
    assert sha256(a) == sha256(b)


def test_parquet_round_trip_keeps_exact_decimals(frame: pl.DataFrame, tmp_path: Path) -> None:
    path = write_frame(frame, tmp_path / "x.parquet", "parquet")
    back = pl.read_parquet(path)
    assert back.schema == frame.schema
    assert back.equals(frame)
    meta = pl.read_parquet_metadata(path)
    assert meta["form4clean.schema_version"] == "1.0.0"
    assert meta["form4clean.cleaning_version"] == "1.0.0"


def test_csv_encodes_lists_and_keeps_decimals(frame: pl.DataFrame, tmp_path: Path) -> None:
    path = write_frame(frame, tmp_path / "x.csv", "csv")
    back = pl.read_csv(path, infer_schema=False)
    assert "51.2345000000" in back["price_per_share"].to_list()
    flags = json.loads(back.filter(pl.col("transaction_code") == "Q")["quality_flags"][0])
    assert "INVALID_SHARES" in flags


def test_json_export_uses_decimal_strings(frame: pl.DataFrame, tmp_path: Path) -> None:
    path = write_frame(frame, tmp_path / "x.json", "json")
    rows = json.loads(path.read_text("utf-8"))
    assert len(rows) == frame.height
    values = {r["transaction_value"] for r in rows}
    assert "614814.00" in values


def test_unknown_format_rejected(frame: pl.DataFrame, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported format"):
        write_frame(frame, tmp_path / "x.xlsx", "xlsx")  # type: ignore[arg-type]
