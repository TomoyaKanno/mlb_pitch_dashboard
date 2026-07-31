import asyncio
from types import SimpleNamespace

import httpx
import pytest

import pipeline.mlb as mlb_module
from pipeline.mlb import MLBClient, RateLimiter, fetch_game_batch


class StubClient:
    """Minimal stand-in exposing the one method fetch_game_batch calls."""

    def __init__(self, failing_pks: set[int]):
        self.failing_pks = failing_pks

    async def boxscore_appearances(self, game):
        if game["game_pk"] in self.failing_pks:
            raise RuntimeError("boom")
        return [{"game_pk": game["game_pk"]}]


def _fake_asyncio(monkeypatch):
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        mlb_module,
        "asyncio",
        SimpleNamespace(
            Lock=asyncio.Lock,
            Semaphore=asyncio.Semaphore,
            sleep=sleep,
        ),
    )
    return delays


async def _request_with_transport(handler):
    client = MLBClient(concurrency=1, rate_per_sec=0)
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url=mlb_module.BASE_URL,
        transport=httpx.MockTransport(handler),
    )
    async with client:
        payload = await client.get_json("/test")
        return payload, client.api_calls


def test_batch_isolates_failures_and_processes_the_rest():
    games = [{"game_pk": pk} for pk in range(5)]
    client = StubClient(failing_pks={2})
    processed: list[int] = []

    async def on_result(game, appearances):
        processed.append(game["game_pk"])

    failures = asyncio.run(fetch_game_batch(client, games, on_result))

    assert sorted(processed) == [0, 1, 3, 4]
    assert [game["game_pk"] for game, _ in failures] == [2]


def test_batch_with_all_failures_returns_them_without_raising():
    games = [{"game_pk": pk} for pk in range(3)]
    client = StubClient(failing_pks={0, 1, 2})

    async def on_result(game, appearances):  # pragma: no cover - never called
        raise AssertionError("on_result should not run for a failed game")

    failures = asyncio.run(fetch_game_batch(client, games, on_result))

    assert len(failures) == 3


def test_rate_limiter_paces_request_starts_without_using_wall_clock(monkeypatch):
    clock = SimpleNamespace(now=10.0)
    delays = _fake_asyncio(monkeypatch)

    async def sleep(delay: float) -> None:
        delays.append(delay)
        clock.now += delay

    mlb_module.asyncio.sleep = sleep
    monkeypatch.setattr(
        mlb_module,
        "time",
        SimpleNamespace(monotonic=lambda: clock.now),
    )
    limiter = RateLimiter(rate_per_sec=50)  # 20ms between starts

    async def run():
        for _ in range(5):
            await limiter.acquire()

    asyncio.run(run())

    assert delays == pytest.approx([0.02, 0.02, 0.02, 0.02])
    assert clock.now == pytest.approx(10.08)


def test_rate_limiter_disabled_is_noop(monkeypatch):
    delays = _fake_asyncio(monkeypatch)
    limiter = RateLimiter(rate_per_sec=0)

    async def run():
        for _ in range(100):
            await limiter.acquire()

    asyncio.run(run())

    assert delays == []


def test_client_retries_transport_errors(monkeypatch):
    delays = _fake_asyncio(monkeypatch)
    monkeypatch.setattr(mlb_module.random, "uniform", lambda *_: 0)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("temporary disconnect", request=request)
        return httpx.Response(200, json={"ok": True})

    payload, api_calls = asyncio.run(_request_with_transport(handler))

    assert payload == {"ok": True}
    assert attempts == 3
    assert api_calls == 3
    assert delays == [0.5, 1.0]


def test_client_raises_after_final_transport_error(monkeypatch):
    delays = _fake_asyncio(monkeypatch)
    monkeypatch.setattr(mlb_module.random, "uniform", lambda *_: 0)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("still disconnected", request=request)

    with pytest.raises(httpx.ConnectError, match="still disconnected"):
        asyncio.run(_request_with_transport(handler))

    assert attempts == mlb_module.MAX_ATTEMPTS
    assert delays == [0.5, 1.0, 2.0]


def test_client_retries_throttling_and_server_errors(monkeypatch):
    delays = _fake_asyncio(monkeypatch)
    monkeypatch.setattr(mlb_module.random, "uniform", lambda *_: 0)
    statuses = iter([429, 503, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        headers = {"Retry-After": "2"} if status == 429 else None
        return httpx.Response(status, headers=headers, json={"ok": True}, request=request)

    payload, api_calls = asyncio.run(_request_with_transport(handler))

    assert payload == {"ok": True}
    assert api_calls == 3
    assert delays == [2.0, 1.0]


def test_client_uses_computed_backoff_for_invalid_retry_after(monkeypatch):
    monkeypatch.setattr(mlb_module.random, "uniform", lambda *_: 0)
    request = httpx.Request("GET", mlb_module.BASE_URL)
    response = httpx.Response(429, headers={"Retry-After": "tomorrow"}, request=request)

    assert MLBClient._retry_delay(response, 0) == 0.5


def test_client_raises_after_final_retryable_response(monkeypatch):
    delays = _fake_asyncio(monkeypatch)
    monkeypatch.setattr(mlb_module.random, "uniform", lambda *_: 0)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, request=request)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_request_with_transport(handler))

    assert attempts == mlb_module.MAX_ATTEMPTS
    assert delays == [0.5, 1.0, 2.0]


def test_client_does_not_retry_nonretryable_client_error(monkeypatch):
    delays = _fake_asyncio(monkeypatch)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, request=request)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_request_with_transport(handler))

    assert attempts == 1
    assert delays == []


@pytest.mark.parametrize("kwargs", [{"concurrency": 0}, {"rate_per_sec": -1}])
def test_client_rejects_invalid_pacing_configuration(kwargs):
    with pytest.raises(ValueError):
        MLBClient(**kwargs)
