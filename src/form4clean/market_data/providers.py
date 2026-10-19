"""Daily price providers for the dashboard chart.

Prices are only used to draw the chart; they never enter the insider dataset. Every series
says where it came from and whether it is delayed, and a missing provider produces an explicit
"unavailable" series, never placeholder data.

Providers:

* ``yahoo``: Yahoo Finance prices through the community ``yfinance`` package. No key, but it
  uses Yahoo's unofficial data feed, can break when Yahoo changes it, and is not installed by
  default: ``pip install "form4clean[yfinance]"``.
* ``csv``: daily bars from ``{prices_dir}/{TICKER}.csv`` that you download yourself. Accepts
  ``date,open,high,low,close[,volume]`` columns, and Nasdaq.com historical-data exports.
* ``none``: no prices; the dashboard shows insider activity without a price chart.

To add a provider, subclass PriceProvider and register it in ``PROVIDERS``.
"""

from __future__ import annotations

import asyncio
import csv
import importlib.util
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from ..config import Settings


class PriceDataError(Exception):
    pass


@dataclass
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass
class PriceSeries:
    symbol: str
    provider: str
    status: str  # "ok" | "unavailable" | "error"
    message: str
    delayed: bool = True
    adjusted: bool = False
    bars: list[Bar] = field(default_factory=list)
    retrieved_at: datetime | None = None


class PriceProvider(ABC):
    name: ClassVar[str]
    label: ClassVar[str]
    adjusted: ClassVar[bool] = False
    delayed_note: ClassVar[str] = "End-of-day prices; today's session is not included."

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    def configured(self) -> str | None:
        """None when ready, otherwise what the user must do."""

    @abstractmethod
    async def daily_bars(self, symbol: str, start: date, end: date) -> list[Bar]: ...


class NoProvider(PriceProvider):
    name = "none"
    label = "None"

    def configured(self) -> str | None:
        return (
            "No price provider is configured. Choose Yahoo Finance or a CSV file in Settings to "
            "see the price chart. Insider data works without one."
        )

    async def daily_bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        return []


class YahooProvider(PriceProvider):
    """Yahoo Finance daily bars via the optional ``yfinance`` package.

    yfinance reads Yahoo's unofficial web endpoints. It needs no key, but Yahoo can change or
    throttle those endpoints at any time, so this provider is opt-in and never installed by
    default.
    """

    name = "yahoo"
    label = "Yahoo Finance (unofficial, optional)"
    adjusted = True
    delayed_note = (
        "End-of-day prices from Yahoo Finance's unofficial feed, adjusted for splits; "
        "today's session is not included."
    )
    install_hint = 'pip install "form4clean[yfinance]"'

    def configured(self) -> str | None:
        if importlib.util.find_spec("yfinance") is None:
            return (
                "The Yahoo Finance provider needs the optional yfinance package, which is not "
                f"installed. Install it with:  {self.install_hint}"
            )
        return None

    @staticmethod
    def yahoo_symbol(symbol: str) -> str:
        # Yahoo writes share classes with a hyphen (BRK-B), the SEC sometimes with a dot.
        return symbol.upper().replace(".", "-")

    def _download(self, symbol: str, start: date, end: date) -> list[Bar]:
        import yfinance

        # auto_adjust=False keeps raw closes; Yahoo still adjusts every price for splits.
        frame = yfinance.Ticker(self.yahoo_symbol(symbol)).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=False,
            raise_errors=True,
        )
        bars = []
        for stamp, row in frame.iterrows():
            values = (row["Open"], row["High"], row["Low"], row["Close"])
            if any(v != v for v in values):  # NaN: Yahoo has no bar for that day
                continue
            volume = row.get("Volume")
            bars.append(
                Bar(
                    date=stamp.date(),
                    # Yahoo stores prices as 32-bit floats; round away the noise (135.49000549).
                    open=round(float(values[0]), 4),
                    high=round(float(values[1]), 4),
                    low=round(float(values[2]), 4),
                    close=round(float(values[3]), 4),
                    volume=None if volume is None or volume != volume else float(volume),
                )
            )
        return bars

    async def daily_bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        problem = self.configured()
        if problem:
            raise PriceDataError(problem)
        try:
            return await asyncio.to_thread(self._download, symbol, start, end)
        except Exception as exc:  # yfinance raises many types, and they change between versions
            raise PriceDataError(
                f"Yahoo Finance did not return prices for {symbol.upper()}: {exc}. Yahoo's "
                "unofficial feed may be throttling requests or may have changed; try again "
                "later or use a CSV file."
            ) from exc


class CsvProvider(PriceProvider):
    name = "csv"
    label = "Local CSV files"
    delayed_note = "Prices from a local file; as current as the file."

    def path(self, symbol: str) -> Path:
        return self.settings.prices_dir / f"{symbol.upper()}.csv"

    def configured(self) -> str | None:
        return None

    async def daily_bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        path = self.path(symbol)
        if not path.exists():
            raise PriceDataError(
                f"No price file for {symbol.upper()}. Save daily prices as {path} with columns "
                "date,open,high,low,close,volume (Nasdaq.com historical-data downloads work "
                "as-is)."
            )
        bars = read_price_csv(path)
        return [b for b in bars if start <= b.date <= end]


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = text.strip().replace("$", "").replace(",", "")
    if cleaned in ("", "-", "N/A", "null"):
        return None
    return float(cleaned)


def _parse_day(text: str) -> date:
    text = text.strip()
    if "/" in text:
        month, day, year = (int(p) for p in text.split("/"))
        return date(year, month, day)
    return date.fromisoformat(text[:10])


def read_price_csv(path: Path) -> list[Bar]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise PriceDataError(f"{path} is empty.")
        cols = {name.strip().lower(): name for name in reader.fieldnames}
        close_col = cols.get("close") or cols.get("close/last") or cols.get("adj close")
        needed = {
            "date": cols.get("date"),
            "open": cols.get("open"),
            "high": cols.get("high"),
            "low": cols.get("low"),
            "close": close_col,
        }
        missing = [k for k, v in needed.items() if v is None]
        if missing:
            raise PriceDataError(f"{path} is missing columns: {', '.join(missing)}.")
        bars = []
        for i, row in enumerate(reader, start=2):
            try:
                o, h, lo, c = (_num(row[str(needed[k])]) for k in ("open", "high", "low", "close"))
                if o is None or h is None or lo is None or c is None:
                    continue
                volume = _num(row[cols["volume"]]) if "volume" in cols else None
                bars.append(Bar(_parse_day(row[str(needed["date"])]), o, h, lo, c, volume))
            except (ValueError, KeyError) as exc:
                raise PriceDataError(f"{path} line {i}: {exc}") from exc
    return sorted(bars, key=lambda b: b.date)


PROVIDERS: dict[str, type[PriceProvider]] = {
    p.name: p for p in (NoProvider, YahooProvider, CsvProvider)
}


def get_provider(settings: Settings) -> PriceProvider:
    cls = PROVIDERS.get(settings.price_provider)
    if cls is None:
        raise PriceDataError(
            f"Unknown price provider {settings.price_provider!r}. "
            f"Choose one of: {', '.join(PROVIDERS)}."
        )
    return cls(settings)
