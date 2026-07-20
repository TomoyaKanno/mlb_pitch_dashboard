from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .classify import classify_appearances
from .db import Database
from .mlb import MLBClient, fetch_game_batch


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = Path(os.getenv("MLB_FRONTEND_DIST", ROOT / "frontend" / "dist"))
INDEX_FILE = FRONTEND_DIST / "index.html"
ASSETS_DIR = FRONTEND_DIST / "assets"
DB_PATH = Path(os.getenv("MLB_DB_PATH", ROOT / "data" / "mlb.sqlite3"))
OVERRIDES_PATH = Path(os.getenv("MLB_ROLE_OVERRIDES", ROOT / "config" / "role_overrides.json"))

app = FastAPI(title="MLB Pitch Workload Dashboard", version="0.1.0")
if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
database = Database(DB_PATH)


def frontend_index() -> Response:
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)
    return HTMLResponse(
        "<h1>Frontend not built</h1>"
        "<p>Run <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>, "
        "or use <code>npm run dev</code> for a hot-reload dev server.</p>",
        status_code=503,
    )


class RefreshRequest(BaseModel):
    season: int = Field(default_factory=lambda: date.today().year, ge=2000, le=2100)
    force: bool = False


class RefreshManager:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.task: asyncio.Task[None] | None = None
        self.state: dict[str, Any] = {
            "running": False,
            "phase": "idle",
            "season": date.today().year,
            "games_total": 0,
            "games_processed": 0,
            "games_failed": 0,
            "api_calls": 0,
            "error": None,
        }

    async def start(self, request: RefreshRequest) -> None:
        if self.task is not None and not self.task.done():
            raise HTTPException(status_code=409, detail="A refresh is already running")
        self.state.update(running=True, phase="queued", season=request.season, error=None)
        self.task = asyncio.create_task(self.run(request))

    async def run(self, request: RefreshRequest) -> None:
        async with self.lock:
            self.state = {
                "running": True,
                "phase": "loading schedule",
                "season": request.season,
                "games_total": 0,
                "games_processed": 0,
                "games_failed": 0,
                "api_calls": 0,
                "error": None,
            }
            try:
                async with MLBClient() as client:
                    games = await client.completed_games(request.season)
                    existing = set() if request.force else database.existing_game_pks(request.season)
                    pending = [game for game in games if game["game_pk"] not in existing]
                    self.state.update(
                        phase="loading boxscores",
                        games_total=len(pending),
                        api_calls=client.api_calls,
                    )

                    async def save(game: dict[str, Any], appearances: list[dict[str, Any]]) -> None:
                        await asyncio.to_thread(database.upsert_game, game, appearances)
                        self.state["games_processed"] += 1
                        self.state["api_calls"] = client.api_calls

                    failures = await fetch_game_batch(client, pending, save)
                    for failed_game, error in failures:
                        await asyncio.to_thread(database.record_game_failure, failed_game, error)
                    self.state.update(
                        phase="classifying roles",
                        api_calls=client.api_calls,
                        games_failed=len(failures),
                    )

                    overrides: dict[str, Any] = {}
                    if OVERRIDES_PATH.exists():
                        overrides = json.loads(OVERRIDES_PATH.read_text())
                    rows = await asyncio.to_thread(database.all_appearances, request.season)
                    classifications = classify_appearances(rows, overrides)
                    await asyncio.to_thread(database.save_classifications, classifications)

                    finished_at = datetime.now(timezone.utc).isoformat()
                    coverage = await asyncio.to_thread(
                        database.refresh_coverage,
                        request.season,
                        [game["game_pk"] for game in games],
                    )
                    if failures and len(failures) == len(pending) and pending:
                        refresh_result = "failed"
                    elif failures:
                        refresh_result = "partial"
                    else:
                        refresh_result = "complete"
                    metadata = {
                        "last_refresh_at": finished_at,
                        "last_refresh_season": request.season,
                        "last_refresh_result": refresh_result,
                        "last_api_calls": client.api_calls,
                        "last_games_fetched": len(pending) - len(failures),
                        "last_games_failed": len(failures),
                        "completed_games": len(games),
                        "last_games_scheduled": coverage["scheduled"],
                        "last_games_current": coverage["current"],
                        "last_games_stale": coverage["stale"],
                        "last_games_missing": coverage["missing"],
                    }
                    await asyncio.to_thread(database.set_metadata, metadata)
                    self.state.update(
                        running=False,
                        phase=refresh_result,
                        api_calls=client.api_calls,
                        finished_at=finished_at,
                    )
            except Exception as exc:  # surfaced to the dashboard status panel
                self.state.update(running=False, phase="failed", error=str(exc))

    def status(self) -> dict[str, Any]:
        return {**database.metadata(), **self.state}


refresh_manager = RefreshManager()


@app.get("/")
async def index() -> Response:
    return frontend_index()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
async def status() -> dict[str, Any]:
    return refresh_manager.status()


@app.post("/api/refresh", status_code=202)
async def refresh(request: RefreshRequest) -> dict[str, Any]:
    await refresh_manager.start(request)
    return {"accepted": True, "season": request.season, "force": request.force}


@app.get("/api/teams")
async def teams(season: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100)) -> dict[str, Any]:
    rows = await asyncio.to_thread(database.team_totals, season)
    return {"season": season, "teams": rows}


@app.get("/api/audit")
async def audit(
    season: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    rows = await asyncio.to_thread(database.audit, season, limit)
    return {"season": season, "appearances": rows}


@app.get("/api/failures")
async def failures(
    season: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    rows = await asyncio.to_thread(database.fetch_failures, season, limit)
    return {"season": season, "failures": rows}


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str) -> Response:
    # Client-side routes (e.g. future /team/:id pages) resolve to the SPA entry
    # point. API and asset paths are handled by their own routes/mounts above;
    # anything left under those prefixes is a genuine 404.
    if full_path.startswith(("api/", "assets/")):
        raise HTTPException(status_code=404, detail="Not found")
    return frontend_index()
