from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import httpx
import pytest

from form4clean.config import Settings
from form4clean.sec.cache import FileCache
from form4clean.sec.client import RateLimiter, SecClient, SecError, SecNotFoundError
from form4clean.sec.edgar import CompanyNotFoundError, Edgar, normalize_ticker, pad_cik
from tests.conftest import FakeEdgar


def run[T](coro: object) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


def client_for(settings: Settings, handler: httpx.MockTransport) -> SecClient:
    sleeps: list[float] = []
    client = SecClient(settings, transport=handler, sleep=sleeps.append)
    client.sleeps = sleeps  # type: ignore[attr-defined]
    return client


def test_user_agent_identifies_app_and_contact(settings: Settings) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["User-Agent"])
        return httpx.Response(200, text="ok")

    async def go() -> None:
        async with SecClient(settings, transport=httpx.MockTransport(handler)) as c:
            await c.get_bytes("https://www.sec.gov/x")

    run(go())
    assert seen == ["Form4Clean tests@example.com"]


def test_retries_429_and_honors_retry_after(settings: Settings) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        if calls["n"] == 2:
            return httpx.Response(503)
        return httpx.Response(200, content=b"done")

    client = client_for(settings, httpx.MockTransport(handler))
    assert run(client.get_bytes("https://www.sec.gov/x")) == b"done"
    assert calls["n"] == 3
    assert client.sleeps[0] >= 7  # type: ignore[attr-defined]
    assert 2 <= client.sleeps[1] < 3  # type: ignore[attr-defined]
    run(client.aclose())


def test_gives_up_after_max_retries(settings: Settings) -> None:
    client = client_for(settings, httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(SecError, match="after 3 attempts"):
        run(client.get_bytes("https://www.sec.gov/x"))


def test_forbidden_is_not_retried(settings: Settings) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403)

    client = client_for(settings, httpx.MockTransport(handler))
    with pytest.raises(SecError, match="User-Agent"):
        run(client.get_bytes("https://www.sec.gov/x"))
    assert calls["n"] == 1


def test_not_found(settings: Settings) -> None:
    client = client_for(settings, httpx.MockTransport(lambda r: httpx.Response(404)))
    with pytest.raises(SecNotFoundError):
        run(client.get_bytes("https://www.sec.gov/x"))


def test_rate_limiter_spaces_requests() -> None:
    now = {"t": 0.0}
    waits: list[float] = []

    async def go() -> None:
        limiter = RateLimiter(5, clock=lambda: now["t"])
        original = asyncio.sleep

        async def fake_sleep(delay: float) -> None:
            waits.append(delay)
            now["t"] += delay
            await original(0)

        asyncio.sleep = fake_sleep  # type: ignore[assignment]
        try:
            for _ in range(3):
                await limiter.wait()
        finally:
            asyncio.sleep = original

    run(go())
    assert waits == pytest.approx([0.2, 0.2])


def test_rate_above_sec_limit_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fair-access"):
        Settings(home=tmp_path, requests_per_second=11)


def _edgar(settings: Settings, fake: FakeEdgar) -> tuple[SecClient, Edgar]:
    client = SecClient(settings, transport=httpx.MockTransport(fake))
    return client, Edgar(client, FileCache(settings.cache_dir), 1)


def test_resolve_ticker_and_cik(settings: Settings) -> None:
    fake = FakeEdgar()
    client, edgar = _edgar(settings, fake)
    assert run(edgar.resolve("exrb")).cik == "0000999001"
    assert run(edgar.resolve("999001")).ticker == "EXRB"
    with pytest.raises(CompanyNotFoundError, match="ZZZZ"):
        run(edgar.resolve("zzzz"))
    run(client.aclose())


def test_ownership_filings_filters_forms_and_dates(settings: Settings) -> None:
    fake = FakeEdgar()
    client, edgar = _edgar(settings, fake)
    refs = run(edgar.ownership_filings("0000999001", date(2025, 1, 1), date(2025, 5, 31)))
    assert all(r.form_type in ("4", "4/A") for r in refs)
    assert all(date(2025, 1, 1) <= r.filing_date <= date(2025, 5, 31) for r in refs)
    assert len(refs) == 6
    run(client.aclose())


def test_documents_are_cached(settings: Settings) -> None:
    fake = FakeEdgar()
    client, edgar = _edgar(settings, fake)
    acc = "0000999101-25-000003"
    first = run(edgar.submission_text("0000999001", acc))
    count = len(fake.requests)
    second = run(edgar.submission_text("0000999001", acc))
    assert first == second
    assert len(fake.requests) == count
    assert edgar.cache_hits == 1
    run(client.aclose())


def test_helpers() -> None:
    assert pad_cik("1045810") == "0001045810"
    assert pad_cik("CIK0001045810") == "0001045810"
    assert normalize_ticker("brk.b") == "BRK-B"
    with pytest.raises(ValueError, match="not a CIK"):
        pad_cik("abc")
