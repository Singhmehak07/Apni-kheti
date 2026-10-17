"""One pooled AsyncClient for all providers (keep-alive cuts TLS handshakes per call)."""
from __future__ import annotations

import asyncio
import time

import httpx

_client: httpx.AsyncClient | None = None
_transport: httpx.AsyncBaseTransport | None = None  # tests inject a mock transport


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    global _transport, _client
    _transport = transport
    _client = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            transport=_transport,
            timeout=httpx.Timeout(12.0, connect=4.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16, keepalive_expiry=60),
            headers={"User-Agent": "ApniKheti/0.1"},
        )
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def request(method: str, url: str, *, retries: int = 1, timeout: float | None = None, **kw) -> httpx.Response:
    """Request with a single quick retry on connect errors / 429 / 5xx."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client().request(method, url, timeout=timeout, **kw)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            return resp
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.ConnectTimeout) as exc:
            last = exc
            if attempt < retries:
                await asyncio.sleep(0.3)
    raise last or RuntimeError("request failed")


class Timer:
    """Collects named spans in milliseconds for the debug panel."""

    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.spans: dict[str, float] = {}

    def span(self, name: str):
        timer = self

        class _Span:
            def __enter__(self):
                self.s = time.perf_counter()

            def __exit__(self, *a):
                timer.spans[name] = round(timer.spans.get(name, 0) + (time.perf_counter() - self.s) * 1000, 1)

        return _Span()

    def add(self, name: str, ms: float) -> None:
        self.spans[name] = round(self.spans.get(name, 0) + ms, 1)

    def done(self) -> dict:
        return {**self.spans, "total": round((time.perf_counter() - self.t0) * 1000, 1)}
