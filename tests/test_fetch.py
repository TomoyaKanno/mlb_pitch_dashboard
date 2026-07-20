import asyncio
import time

from app.mlb import RateLimiter, fetch_game_batch


class StubClient:
    """Minimal stand-in exposing the one method fetch_game_batch calls."""

    def __init__(self, failing_pks: set[int]):
        self.failing_pks = failing_pks

    async def boxscore_appearances(self, game):
        if game["game_pk"] in self.failing_pks:
            raise RuntimeError("boom")
        return [{"game_pk": game["game_pk"]}]


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


def test_rate_limiter_paces_request_starts():
    limiter = RateLimiter(rate_per_sec=50)  # 20ms between starts

    async def run():
        start = time.monotonic()
        for _ in range(5):
            await limiter.acquire()
        return time.monotonic() - start

    elapsed = asyncio.run(run())
    # 5 serial acquisitions => at least 4 gaps of 20ms.
    assert elapsed >= 0.07


def test_rate_limiter_disabled_is_noop():
    limiter = RateLimiter(rate_per_sec=0)

    async def run():
        start = time.monotonic()
        for _ in range(100):
            await limiter.acquire()
        return time.monotonic() - start

    assert asyncio.run(run()) < 0.05
