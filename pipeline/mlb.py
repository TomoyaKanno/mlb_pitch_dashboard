from __future__ import annotations

import asyncio
import os
import random
import time
from datetime import date
from typing import Any, Awaitable, Callable

import httpx


BASE_URL = "https://statsapi.mlb.com/api/v1"

# Defaults are overridable via the environment so a deployment can dial the
# load down without a code change. Concurrency caps in-flight requests; the
# rate limit paces how fast new requests may start, regardless of how quickly
# responses come back.
DEFAULT_CONCURRENCY = int(os.getenv("MLB_CONCURRENCY", "8"))
DEFAULT_RATE_LIMIT = float(os.getenv("MLB_RATE_LIMIT", "5"))
MAX_ATTEMPTS = 4
BACKOFF_BASE = 0.5


class RateLimiter:
    """Spaces out request *starts* by a minimum interval.

    A concurrency semaphore alone bounds how many requests are in flight but
    not how fast they are issued: with fast responses a small pool still bursts
    hundreds of requests per second. This limiter hands each caller a scheduled
    start time so starts are staggered even under full concurrency.
    """

    def __init__(self, rate_per_sec: float):
        self._min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next_time = 0.0

    async def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            scheduled = max(now, self._next_time)
            self._next_time = scheduled + self._min_interval
            wait = scheduled - now
        if wait > 0:
            await asyncio.sleep(wait)


class MLBClient:
    def __init__(self, concurrency: int | None = None, rate_per_sec: float | None = None):
        concurrency = concurrency if concurrency is not None else DEFAULT_CONCURRENCY
        rate_per_sec = rate_per_sec if rate_per_sec is not None else DEFAULT_RATE_LIMIT
        if concurrency < 1:
            raise ValueError("MLB_CONCURRENCY must be at least 1")
        if rate_per_sec < 0:
            raise ValueError("MLB_RATE_LIMIT must be zero or greater")
        self.api_calls = 0
        self._semaphore = asyncio.Semaphore(concurrency)
        self._limiter = RateLimiter(rate_per_sec)
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": "personal-mlb-pitch-dashboard/0.1"},
            limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
        )

    async def __aenter__(self) -> "MLBClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._semaphore:
            for attempt in range(MAX_ATTEMPTS):
                await self._limiter.acquire()
                self.api_calls += 1
                try:
                    response = await self._client.get(path, params=params)
                except httpx.TransportError:
                    if attempt == MAX_ATTEMPTS - 1:
                        raise
                    await asyncio.sleep(self._retry_delay(None, attempt))
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == MAX_ATTEMPTS - 1:
                        response.raise_for_status()
                    await asyncio.sleep(self._retry_delay(response, attempt))
                    continue
                response.raise_for_status()
                return response.json()
        raise RuntimeError("MLB request exhausted retries")

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        """Exponential backoff with jitter, honoring Retry-After when present.

        Jitter breaks the lock-step retry storm that a fixed delay produces when
        several concurrent requests are throttled at once. A numeric Retry-After
        (seconds) from a 429 wins when it asks for a longer wait; the HTTP-date
        form is ignored in favor of the computed backoff.
        """
        base = BACKOFF_BASE * (2**attempt)
        retry_after = response.headers.get("Retry-After") if response is not None else None
        if retry_after:
            try:
                base = max(base, float(retry_after))
            except ValueError:
                pass
        return base + random.uniform(0, base * 0.25)

    async def completed_games(self, season: int) -> list[dict[str, Any]]:
        today = date.today()
        end_date = today.isoformat() if season == today.year else f"{season}-11-15"
        payload = await self.get_json(
            "/schedule",
            params={
                "sportId": 1,
                "gameType": "R",
                "startDate": f"{season}-03-01",
                "endDate": end_date,
            },
        )
        games: dict[int, dict[str, Any]] = {}
        for day in payload.get("dates", []):
            for game in day.get("games", []):
                status = game.get("status", {})
                official_date = game.get("officialDate") or day["date"]
                if official_date > end_date:
                    continue
                if status.get("abstractGameState") != "Final":
                    continue
                if status.get("detailedState") in {"Postponed", "Cancelled", "Suspended"}:
                    continue
                game_pk = int(game["gamePk"])
                games[game_pk] = {
                    "game_pk": game_pk,
                    "game_date": official_date,
                    "season": season,
                    "status": status.get("detailedState", "Final"),
                }
        return sorted(games.values(), key=lambda item: (item["game_date"], item["game_pk"]))

    async def boxscore_appearances(self, game: dict[str, Any]) -> list[dict[str, Any]]:
        payload = await self.get_json(f"/game/{game['game_pk']}/boxscore")
        appearances: list[dict[str, Any]] = []
        for side in ("away", "home"):
            team_payload = payload.get("teams", {}).get(side, {})
            team = team_payload.get("team", {})
            team_id = int(team.get("id", 0))
            team_name = team.get("name", side.title())
            players = team_payload.get("players", {})
            for order, pitcher_id in enumerate(team_payload.get("pitchers", [])):
                player = players.get(f"ID{pitcher_id}", {})
                pitching = player.get("stats", {}).get("pitching", {})
                pitches = int(pitching.get("numberOfPitches") or 0)
                if pitches <= 0:
                    continue
                person = player.get("person", {})
                appearances.append(
                    {
                        "game_pk": game["game_pk"],
                        "team_id": team_id,
                        "team_name": team_name,
                        "pitcher_id": int(pitcher_id),
                        "pitcher_name": person.get("fullName", f"Player {pitcher_id}"),
                        "pitches": pitches,
                        "official_started": int(pitching.get("gamesStarted") or 0) > 0,
                        "appearance_order": order,
                    }
                )
        return appearances


async def fetch_game_batch(
    client: MLBClient,
    games: list[dict[str, Any]],
    on_result: Callable[[dict[str, Any], list[dict[str, Any]]], Awaitable[None]],
) -> list[tuple[dict[str, Any], str]]:
    """Fetch boxscores concurrently, isolating per-game failures.

    A single game whose request exhausts its retries must not abort the whole
    refresh: its error is collected and the remaining games still flow through
    to ``on_result``, so the caller can classify and report whatever was
    stored. Returns ``(game, error)`` pairs for the games that could not be
    fetched. Any pending tasks are cancelled on exit to avoid orphaning work.
    """

    async def fetch_one(
        game: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]] | None, Exception | None]:
        try:
            return game, await client.boxscore_appearances(game), None
        except Exception as exc:  # network/HTTP/parse errors for this game only
            return game, None, exc

    failures: list[tuple[dict[str, Any], str]] = []
    tasks = [asyncio.create_task(fetch_one(game)) for game in games]
    try:
        for task in asyncio.as_completed(tasks):
            game, appearances, error = await task
            if error is not None:
                failures.append((game, str(error)))
                continue
            await on_result(game, appearances)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
    return failures

