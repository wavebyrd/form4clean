"""Compare what was publicly known on a past date with what is known today.

The point-in-time view uses only filings accepted by the cutoff, reconciled with only the
amendments accepted by then, so a backtest built on it has no look-ahead bias.

    python examples/point_in_time.py NVDA 2025-06-01
"""

from __future__ import annotations

import sys

import polars as pl

from form4clean import InsiderData

ticker, as_of = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("NVDA", "2025-06-01")
data = InsiderData(ticker)

then = data.transactions(end=as_of, as_of=as_of).to_polars()
now = data.transactions(end=as_of).to_polars()

print(f"Transactions dated on or before {as_of}:")
print(f"  known on {as_of}: {then.height}")
print(f"  known today:      {now.height}")

late = now.join(then, on="transaction_id", how="anti")
if late.height:
    print(f"\n{late.height} were disclosed after {as_of} (late filings or amendments):")
    print(
        late.select(
            "transaction_date",
            "filing_date",
            "insider_name",
            "transaction_code",
            "amendment_status",
        ).sort("filing_date")
    )

# Disclosure timing matters for event studies: most filings arrive after the close.
print(now.group_by("disclosure_timing").agg(pl.len().alias("filings")).sort("filings"))
