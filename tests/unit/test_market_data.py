from __future__ import annotations

import asyncio
import sys
import types
from datetime import date
from importlib.machinery import ModuleSpec
from pathlib import Path

import pandas as pd
import pytest

from form4clean.config import Settings
from form4clean.market_data.providers import (
    CsvProvider,
    NoProvider,
    PriceDataError,
    YahooProvider,
    get_provider,
    read_price_csv,
)


def test_no_provider_explains_how_to_enable(settings: Settings) -> None:
    message = NoProvider(settings).configured()
    assert message
    assert "Yahoo Finance" in message


def test_csv_standard_format(tmp_path: Path) -> None:
    path = tmp_path / "EXRB.csv"
    path.write_text(
        "Date,Open,High,Low,Close,Volume\n2025-03-04,50,52,49.5,51,1000\n"
        "2025-03-03,49,50.5,48,50,2000\n",
        encoding="utf-8",
    )
    bars = read_price_csv(path)
    assert [b.date for b in bars] == [date(2025, 3, 3), date(2025, 3, 4)]
    assert bars[1].close == 51


def test_csv_nasdaq_download_format(tmp_path: Path) -> None:
    path = tmp_path / "EXRB.csv"
    path.write_text(
        "Date,Close/Last,Volume,Open,High,Low\n03/04/2025,$51.00,1000,$50.00,$52.00,$49.50\n",
        encoding="utf-8",
    )
    bar = read_price_csv(path)[0]
    assert (bar.date, bar.open, bar.close, bar.volume) == (date(2025, 3, 4), 50, 51, 1000)


def test_csv_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "EXRB.csv"
    path.write_text("Date,Close\n2025-03-04,51\n", encoding="utf-8")
    with pytest.raises(PriceDataError, match="missing columns"):
        read_price_csv(path)


def test_csv_provider_missing_file_says_where(settings: Settings) -> None:
    provider = CsvProvider(settings)
    with pytest.raises(PriceDataError, match=r"EXRB\.csv"):
        asyncio.run(provider.daily_bars("EXRB", date(2025, 1, 1), date(2025, 2, 1)))


def test_unknown_provider(settings: Settings) -> None:
    with pytest.raises(PriceDataError, match="Unknown price provider"):
        get_provider(settings.model_copy(update={"price_provider": "scraper"}))


def _fake_yfinance(monkeypatch: pytest.MonkeyPatch, history: object) -> list[dict[str, object]]:
    """Install a stand-in yfinance module so tests never touch the network."""
    calls: list[dict[str, object]] = []

    class Ticker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, **kwargs: object) -> pd.DataFrame:
            calls.append({"symbol": self.symbol, **kwargs})
            if isinstance(history, Exception):
                raise history
            assert isinstance(history, pd.DataFrame)
            return history

    module = types.ModuleType("yfinance")
    module.__spec__ = ModuleSpec("yfinance", None)
    module.Ticker = Ticker  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", module)
    return calls


def test_yahoo_explains_how_to_install(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "yfinance", None)
    message = YahooProvider(settings).configured()
    assert message
    assert 'pip install "form4clean[yfinance]"' in message
    with pytest.raises(PriceDataError, match="not installed"):
        asyncio.run(YahooProvider(settings).daily_bars("EXRB", date(2025, 3, 1), date(2025, 3, 5)))


def test_yahoo_parses_history(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    frame = pd.DataFrame(
        {
            "Open": [49.0, float("nan"), 50.0],
            "High": [50.5, float("nan"), 52.0],
            "Low": [48.0, float("nan"), 49.5],
            "Close": [50.0, float("nan"), 51.0],
            "Volume": [2000, 0, 1000],
        },
        index=pd.DatetimeIndex(
            ["2025-03-03", "2025-03-04", "2025-03-05"], tz="America/New_York", name="Date"
        ),
    )
    calls = _fake_yfinance(monkeypatch, frame)
    provider = YahooProvider(settings)
    assert provider.configured() is None
    bars = asyncio.run(provider.daily_bars("brk.b", date(2025, 3, 1), date(2025, 3, 5)))
    assert [b.date for b in bars] == [date(2025, 3, 3), date(2025, 3, 5)]
    assert (bars[1].open, bars[1].close, bars[1].volume) == (50, 51, 1000)
    assert calls[0]["symbol"] == "BRK-B"
    assert calls[0]["end"] == "2025-03-06"  # yfinance's end date is exclusive
    assert calls[0]["auto_adjust"] is False


def test_yahoo_failure_becomes_clear_error(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_yfinance(monkeypatch, RuntimeError("Too Many Requests"))
    with pytest.raises(PriceDataError, match="Too Many Requests"):
        asyncio.run(YahooProvider(settings).daily_bars("EXRB", date(2025, 3, 1), date(2025, 3, 5)))


def test_yahoo_is_registered_but_not_default(settings: Settings) -> None:
    assert settings.price_provider == "none"
    provider = get_provider(settings.model_copy(update={"price_provider": "yahoo"}))
    assert isinstance(provider, YahooProvider)
