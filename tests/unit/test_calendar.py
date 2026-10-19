from __future__ import annotations

from datetime import date, datetime, time

import pytest

from form4clean.calendar import (
    EARLY_CLOSE,
    EASTERN,
    business_days_between,
    disclosure,
    holidays,
    is_trading_day,
    next_trading_day,
    session_close,
)
from form4clean.models.enums import DisclosureTiming


def test_2025_nyse_holidays() -> None:
    assert sorted(holidays(2025)) == [
        date(2025, 1, 1),
        date(2025, 1, 20),
        date(2025, 2, 17),
        date(2025, 4, 18),
        date(2025, 5, 26),
        date(2025, 6, 19),
        date(2025, 7, 4),
        date(2025, 9, 1),
        date(2025, 11, 27),
        date(2025, 12, 25),
    ]


def test_2026_observed_holidays() -> None:
    days = holidays(2026)
    assert date(2026, 7, 3) in days  # July 4 is a Saturday
    assert date(2026, 4, 3) in days  # Good Friday


def test_new_year_on_saturday_is_not_observed() -> None:
    assert date(2021, 12, 31) not in holidays(2022)
    assert is_trading_day(date(2021, 12, 31))


def test_special_closure() -> None:
    assert not is_trading_day(date(2025, 1, 9))


@pytest.mark.parametrize(
    ("day", "close"),
    [
        (date(2025, 11, 28), EARLY_CLOSE),
        (date(2025, 12, 24), EARLY_CLOSE),
        (date(2025, 7, 3), EARLY_CLOSE),
        (date(2025, 7, 2), time(16, 0)),
    ],
)
def test_session_close(day: date, close: time) -> None:
    assert session_close(day) == close


def at(*args: int) -> datetime:
    return datetime(*args, tzinfo=EASTERN)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("accepted", "timing", "session"),
    [
        (at(2025, 3, 5, 7, 15), DisclosureTiming.PRE_MARKET, date(2025, 3, 5)),
        (at(2025, 3, 5, 11, 30), DisclosureTiming.MARKET_HOURS, date(2025, 3, 5)),
        (at(2025, 3, 5, 16, 0), DisclosureTiming.AFTER_CLOSE, date(2025, 3, 6)),
        (at(2025, 3, 7, 18, 30), DisclosureTiming.AFTER_CLOSE, date(2025, 3, 10)),
        (at(2025, 4, 18, 10, 30), DisclosureTiming.NON_TRADING_DAY, date(2025, 4, 21)),
        (at(2025, 11, 28, 14, 0), DisclosureTiming.AFTER_CLOSE, date(2025, 12, 1)),
        (None, DisclosureTiming.UNKNOWN, None),
    ],
)
def test_disclosure(
    accepted: datetime | None, timing: DisclosureTiming, session: date | None
) -> None:
    assert disclosure(accepted) == (timing, session)


def test_disclosure_converts_other_timezones() -> None:
    from zoneinfo import ZoneInfo

    utc = datetime(2025, 3, 5, 21, 5, tzinfo=ZoneInfo("UTC"))  # 4:05 p.m. Eastern
    assert disclosure(utc)[0] is DisclosureTiming.AFTER_CLOSE


def test_next_trading_day_skips_weekends_and_holidays() -> None:
    assert next_trading_day(date(2025, 4, 17)) == date(2025, 4, 21)


def test_business_days_between() -> None:
    assert business_days_between(date(2025, 4, 28), date(2025, 4, 30)) == 2
    assert business_days_between(date(2025, 4, 17), date(2025, 4, 21)) == 1
