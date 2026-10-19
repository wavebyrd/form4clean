"""HTTP client for SEC EDGAR that follows the SEC's fair-access policy.

* Every request carries a User-Agent with an application name and a contact email.
* Requests are spaced to a configurable rate (default 5 per second; the SEC limit is 10).
* 429 and 5xx responses are retried with exponential backoff, honoring Retry-After.
* 403 responses are not retried: the SEC uses them for blocked or unidentified clients, and
  hammering would make things worse.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from collections.abc import Callable
from types import TracebackType

import httpx

from ..config import Settings

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_BACKOFF_SECONDS = 60.0


class SecError(Exception):
    """A request to the SEC failed. The message says what happened and what to try."""


class SecNotFoundError(SecError):
    pass


class RateLimiter:
    """Spaces request start times at least ``1 / rate`` seconds apart."""

    def __init__(self, rate: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.interval = 1.0 / rate
        self._clock = clock
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = self._clock()
            delay = self._next - now
            if delay > 0:
                await asyncio.sleep(delay)
                now = self._clock()
            self._next = max(now, self._next) + self.interval


class SecClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], object] | None = None,
    ) -> None:
        self.settings = settings
        self._limiter = RateLimiter(settings.requests_per_second)
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.user_agent(),
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=settings.timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )
        self._sleep = sleep or asyncio.sleep
        self.request_count = 0

    async def __aenter__(self) -> SecClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_bytes(self, url: str) -> bytes:
        attempts = self.settings.max_retries + 1
        last_error = ""
        for attempt in range(attempts):
            await self._limiter.wait()
            self.request_count += 1
            try:
                response = await self._client.get(url)
            except httpx.TransportError as exc:
                last_error = f"network error: {exc.__class__.__name__}: {exc}"
                await self._backoff(attempt, None)
                continue
            if response.status_code == 200:
                return response.content
            if response.status_code == 404:
                raise SecNotFoundError(f"SEC returned 404 Not Found for {url}")
            if response.status_code == 403:
                raise SecError(
                    f"SEC returned 403 Forbidden for {url}. The SEC blocks requests without a "
                    "descriptive User-Agent or that exceed its rate limit. Check your contact "
                    "email (form4clean config), lower requests_per_second, and wait ten "
                    "minutes before retrying."
                )
            if response.status_code in RETRYABLE_STATUS:
                last_error = f"HTTP {response.status_code}"
                await self._backoff(attempt, response.headers.get("Retry-After"))
                continue
            raise SecError(f"SEC returned HTTP {response.status_code} for {url}")
        raise SecError(f"Giving up on {url} after {attempts} attempts ({last_error}).")

    async def _backoff(self, attempt: int, retry_after: str | None) -> None:
        delay = min(MAX_BACKOFF_SECONDS, 1.0 * 2**attempt) + random.uniform(0, 0.5)
        if retry_after:
            with contextlib.suppress(ValueError):
                delay = max(delay, min(MAX_BACKOFF_SECONDS * 5, float(retry_after)))
        result = self._sleep(delay)
        if asyncio.iscoroutine(result):
            await result
