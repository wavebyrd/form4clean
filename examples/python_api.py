"""Pull a company's insider transactions, filter them, and export a research dataset.

export FORM4CLEAN_SEC_EMAIL="you@example.com"
python examples/python_api.py NVDA
"""

from __future__ import annotations

import sys

from form4clean import InsiderData

ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
data = InsiderData(ticker)  # downloads five years on first use, then reads the local copy

transactions = data.transactions(
    start="2024-01-01",
    end="2026-01-01",
    clean=True,
    reconcile_amendments=True,
)
print(transactions)

df = transactions.to_pandas()
print(
    df[
        [
            "transaction_date",
            "insider_name",
            "insider_role",
            "transaction_code",
            "shares",
            "price_per_share",
            "transaction_value",
            "quality_status",
        ]
    ].head(10)
)

# Open-market or private sales by the CEO or CFO worth at least $1 million,
# excluding anything the cleaning engine wants a person to review.
big_sales = data.transactions(
    transaction_types=["Market Sale"],
    roles=["CEO", "CFO"],
    min_value=1_000_000,
    quality=["VALID", "WARNING"],
)
print(f"{len(big_sales)} large executive sales")

# Exact decimals survive the round trip: Parquet decimal columns, plus a manifest
# with the schema version, cleaning version and a SHA-256 checksum.
path = transactions.to_parquet(f"{ticker.lower()}_insiders.parquet")
print(f"Wrote {path} and {path.with_name(path.stem + '.manifest.json')}")

report = transactions.quality_report
if report is not None:
    print(
        f"{report.records_requiring_review} records need review; "
        f"{report.amendments.records_superseded} superseded by amendments"
    )
