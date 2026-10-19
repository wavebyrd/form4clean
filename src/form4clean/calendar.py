"""NYSE regular-session calendar, used to place filings relative to market hours.

Holidays are computed from the NYSE's published rules, plus a list of unscheduled closures.
Regular hours are 9:30 a.m. to 4:00 p.m. Eastern; early closes are at 1:00 p.m. on the day after
Thanksgiving, on Christmas Eve, and on July 3 when they fall on trading days.

Limitations: closures before 2000 are not listed, and any future unscheduled closure must be
added to ``SPECIAL_CLOSURES``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from .models.enums import DisclosureTiming

EASTERN = ZoneInfo("America/New_York")
OPEN = time(9, 30)
CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)

SPECIAL_CLOSURES = frozenset(
    {
        date(2001, 9, 11),
        date(2001, 9, 12),
        date(2001, 9, 13),
        date(2001, 9, 14),
        date(2004, 6, 11),  # President Reagan
        date(2007, 1, 2),  # President Ford
        date(2012, 10, 29),
        date(2012, 10, 30),  # Hurricane Sandy
        date(2018, 12, 5),  # President G. H. W. Bush
        date(2025, 1, 9),  # President Carter
    }
)


def _easter(year: int) -> date:
    """Gregorian Easter (anonymous algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: date) -> date | None:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


@lru_cache(maxsize=256)
def holidays(year: int) -> frozenset[date]:
    days: set[date | None] = set()
    new_year = date(year, 1, 1)
    # NYSE does not close on Friday Dec 31 when Jan 1 falls on a Saturday.
    days.add(None if new_year.weekday() == 5 else _observed(new_year))
    if year >= 1998:
        days.add(_nth_weekday(year, 1, 0, 3))  # Martin Luther King Jr. Day
    days.add(_nth_weekday(year, 2, 0, 3))  # Washington's Birthday
    days.add(_easter(year) - timedelta(days=2))  # Good Friday
    days.add(_last_weekday(year, 5, 0))  # Memorial Day
    if year >= 2022:
        days.add(_observed(date(year, 6, 19)))  # Juneteenth
    days.add(_observed(date(year, 7, 4)))
    days.add(_nth_weekday(year, 9, 0, 1))  # Labor Day
    days.add(_nth_weekday(year, 11, 3, 4))  # Thanksgiving
    days.add(_observed(date(year, 12, 25)))
    return frozenset(d for d in days if d is not None)


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day not in holidays(day.year) and day not in SPECIAL_CLOSURES


def next_trading_day(day: date) -> date:
    day += timedelta(days=1)
    while not is_trading_day(day):
        day += timedelta(days=1)
    return day


def session_close(day: date) -> time:
    if not is_trading_day(day):
        raise ValueError(f"{day} is not a trading day")
    thanksgiving = _nth_weekday(day.year, 11, 3, 4)
    july_4 = date(day.year, 7, 4)
    if (
        day == thanksgiving + timedelta(days=1)
        or (day.month == 12 and day.day == 24)
        or (day.month == 7 and day.day == 3 and july_4.weekday() < 5)
    ):
        return EARLY_CLOSE
    return CLOSE


def disclosure(accepted: datetime | None) -> tuple[DisclosureTiming, date | None]:
    """Timing of an acceptance timestamp and the first session during which it was public."""
    if accepted is None:
        return DisclosureTiming.UNKNOWN, None
    local = accepted.astimezone(EASTERN)
    day = local.date()
    if not is_trading_day(day):
        return DisclosureTiming.NON_TRADING_DAY, next_trading_day(day)
    if local.time() < OPEN:
        return DisclosureTiming.PRE_MARKET, day
    if local.time() < session_close(day):
        return DisclosureTiming.MARKET_HOURS, day
    return DisclosureTiming.AFTER_CLOSE, next_trading_day(day)


def business_days_between(start: date, end: date) -> int:
    """Trading days after ``start`` up to and including ``end``."""
    count = 0
    day = start
    while day < end:
        day += timedelta(days=1)
        if is_trading_day(day):
            count += 1
    return count
