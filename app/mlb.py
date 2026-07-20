from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Awaitable, Callable

import httpx


BASE_URL = "https://statsapi.mlb.com/api/v1"


class MLBClient:
    def __init__(self, concurrency: int = 8):
        self.api_calls = 0
        self._semaphore = asyncio.Semaphore(concurrency)
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
            for attempt in range(3):
                self.api_calls += 1
                response = await self._client.get(path, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == 2:
                        response.raise_for_status()
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                response.raise_for_status()
                return response.json()
        raise RuntimeError("MLB request exhausted retries")

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
) -> None:
    async def fetch_one(game: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return game, await client.boxscore_appearances(game)

    tasks = [asyncio.create_task(fetch_one(game)) for game in games]
    for task in asyncio.as_completed(tasks):
        game, appearances = await task
        await on_result(game, appearances)
