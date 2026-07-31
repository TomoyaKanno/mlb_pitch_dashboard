from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from pipeline.schema import AppearanceRecord, FetchStateRecord, GameRecord, NextGameRecord, Snapshot
from pipeline.storage import load_snapshot
from pipeline.update import games_to_refresh, update_season
from pipeline.validation import SnapshotValidationError


NOW = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)


def game(game_pk: int, game_date: str) -> dict:
    return {
        "game_pk": game_pk,
        "game_date": game_date,
        "season": 2026,
        "status": "Final",
        "game_datetime": f"{game_date}T23:10:00Z",
        "away_team_id": 100,
        "away_team_name": "Away",
        "home_team_id": 200,
        "home_team_name": "Home",
    }


def boxscore(game_pk: int) -> list[dict]:
    return [
        {
            "game_pk": game_pk,
            "team_id": 100,
            "team_name": "Away",
            "pitcher_id": game_pk * 10 + 1,
            "pitcher_name": "Away Starter",
            "pitches": 82,
            "official_started": True,
            "appearance_order": 0,
        },
        {
            "game_pk": game_pk,
            "team_id": 100,
            "team_name": "Away",
            "pitcher_id": game_pk * 10 + 2,
            "pitcher_name": "Away Reliever",
            "pitches": 24,
            "official_started": False,
            "appearance_order": 1,
        },
        {
            "game_pk": game_pk,
            "team_id": 200,
            "team_name": "Home",
            "pitcher_id": game_pk * 10 + 3,
            "pitcher_name": "Home Starter",
            "pitches": 91,
            "official_started": True,
            "appearance_order": 0,
        },
    ]


class FakeClient:
    def __init__(self, schedule, boxes, failures=None, next_games=None, rosters=None):
        self.schedule = schedule
        self.boxes = boxes
        self.failures = failures or set()
        self.next_games = next_games or []
        self.rosters = rosters or []
        self.api_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def completed_games(self, season):
        self.api_calls += 1
        return self.schedule

    async def upcoming_games(self, season):
        self.api_calls += 1
        return self.next_games

    async def pitching_rosters(self, season):
        self.api_calls += 1
        return self.rosters

    async def boxscore_appearances(self, value):
        self.api_calls += 1
        if value["game_pk"] in self.failures:
            raise RuntimeError("temporary MLB failure")
        return self.boxes[value["game_pk"]]


def factory(schedule, boxes, failures=None, next_games=None, rosters=None):
    return lambda: FakeClient(schedule, boxes, failures, next_games, rosters)


def test_bootstrap_then_incremental_run_only_loads_schedule(tmp_path):
    schedule = [game(1, "2026-06-01"), game(2, "2026-06-02")]
    boxes = {1: boxscore(1), 2: boxscore(2)}
    first = asyncio.run(
        update_season(2026, tmp_path, reconcile_days=0, now=NOW, client_factory=factory(schedule, boxes))
    )
    second = asyncio.run(
        update_season(2026, tmp_path, reconcile_days=0, now=NOW, client_factory=factory(schedule, boxes))
    )

    assert first.api_calls == 5
    assert first.games_requested == 2
    assert second.api_calls == 3
    assert second.games_requested == 0
    snapshot = load_snapshot(tmp_path, 2026)
    assert len(snapshot.games) == 2
    assert len(snapshot.appearances) == 6
    assert (tmp_path / "seasons/2026/games/2026-06.jsonl").exists()
    assert (tmp_path / "seasons/2026/manifest.json").exists()


def test_recent_failure_preserves_last_known_good_data_as_stale(tmp_path):
    schedule = [game(1, "2026-07-19")]
    boxes = {1: boxscore(1)}
    asyncio.run(
        update_season(2026, tmp_path, reconcile_days=7, now=NOW, client_factory=factory(schedule, boxes))
    )
    summary = asyncio.run(
        update_season(
            2026,
            tmp_path,
            reconcile_days=7,
            now=NOW,
            client_factory=factory(schedule, boxes, failures={1}),
        )
    )

    snapshot = load_snapshot(tmp_path, 2026)
    assert len(snapshot.appearances) == 3
    assert snapshot.fetch_state[1].fetch_status == "failed"
    assert snapshot.fetch_state[1].last_success_at is not None
    assert snapshot.fetch_state[1].attempt_count == 2
    assert summary.result == "failed"
    assert summary.stale_games == 1
    assert summary.missing_games == 0


def test_first_failure_is_missing_and_successful_retry_becomes_current(tmp_path):
    schedule = [game(1, "2026-06-01")]
    boxes = {1: boxscore(1)}

    failed = asyncio.run(
        update_season(
            2026,
            tmp_path,
            reconcile_days=0,
            now=NOW,
            client_factory=factory(schedule, boxes, failures={1}),
        )
    )
    failed_snapshot = load_snapshot(tmp_path, 2026)

    assert failed.result == "failed"
    assert failed.current_games == 0
    assert failed.stale_games == 0
    assert failed.missing_games == 1
    assert failed_snapshot.appearances == {}
    assert failed_snapshot.fetch_state[1].fetch_status == "failed"
    assert failed_snapshot.fetch_state[1].last_success_at is None
    assert failed_snapshot.fetch_state[1].last_error == "temporary MLB failure"
    assert failed_snapshot.fetch_state[1].attempt_count == 1

    recovered = asyncio.run(
        update_season(
            2026,
            tmp_path,
            reconcile_days=0,
            now=NOW,
            client_factory=factory(schedule, boxes),
        )
    )
    recovered_snapshot = load_snapshot(tmp_path, 2026)

    assert recovered.result == "complete"
    assert recovered.current_games == 1
    assert recovered.stale_games == 0
    assert recovered.missing_games == 0
    assert recovered_snapshot.fetch_state[1].fetch_status == "success"
    assert recovered_snapshot.fetch_state[1].last_error is None
    assert recovered_snapshot.fetch_state[1].last_success_at == NOW.isoformat()
    assert recovered_snapshot.fetch_state[1].attempt_count == 2
    assert len(recovered_snapshot.appearances) == 3


def test_new_game_failure_is_partial_when_prior_games_remain_current(tmp_path):
    existing_schedule = [game(1, "2026-06-01")]
    boxes = {1: boxscore(1), 2: boxscore(2)}
    asyncio.run(
        update_season(
            2026,
            tmp_path,
            reconcile_days=0,
            now=NOW,
            client_factory=factory(existing_schedule, boxes),
        )
    )

    summary = asyncio.run(
        update_season(
            2026,
            tmp_path,
            reconcile_days=0,
            now=NOW,
            client_factory=factory(
                [*existing_schedule, game(2, "2026-06-02")],
                boxes,
                failures={2},
            ),
        )
    )

    assert summary.result == "partial"
    assert summary.games_requested == 1
    assert summary.current_games == 1
    assert summary.stale_games == 0
    assert summary.missing_games == 1


def test_refresh_plan_includes_missing_failed_and_recent_games():
    games = [GameRecord.from_dict(game(1, "2026-06-01")), GameRecord.from_dict(game(2, "2026-07-19"))]
    snapshot = Snapshot(season=2026)
    snapshot.fetch_state[1] = FetchStateRecord(1, "failed", NOW.isoformat(), None, "x", 1)
    snapshot.fetch_state[2] = FetchStateRecord(2, "success", NOW.isoformat(), NOW.isoformat(), None, 1)
    snapshot.appearances[(2, 100, 21)] = AppearanceRecord(
        2, "2026-07-19", 2026, 100, "Away", 21, "Pitcher", 10, True, 0, "SP", "official starter"
    )

    planned = games_to_refresh(games, snapshot, force=False, reconcile_days=7, as_of=NOW.date())
    assert [row.game_pk for row in planned] == [1, 2]


def test_force_refresh_includes_every_scheduled_game():
    games = [
        GameRecord.from_dict(game(1, "2026-06-01")),
        GameRecord.from_dict(game(2, "2026-06-02")),
    ]
    snapshot = Snapshot(season=2026)
    for game_record in games:
        snapshot.fetch_state[game_record.game_pk] = FetchStateRecord(
            game_record.game_pk, "success", NOW.isoformat(), NOW.isoformat(), None, 1,
        )
        appearance_record = AppearanceRecord(
            game_record.game_pk,
            game_record.game_date,
            2026,
            100,
            "Away",
            game_record.game_pk * 10,
            "Pitcher",
            80,
            True,
            0,
            "SP",
            "official starter",
        )
        snapshot.appearances[appearance_record.key] = appearance_record

    assert games_to_refresh(
        games, snapshot, force=False, reconcile_days=0, as_of=NOW.date(),
    ) == []
    assert games_to_refresh(
        games, snapshot, force=True, reconcile_days=0, as_of=NOW.date(),
    ) == games


def test_refresh_rejects_negative_reconciliation_window(tmp_path):
    with pytest.raises(ValueError, match="reconcile_days"):
        asyncio.run(update_season(2026, tmp_path, reconcile_days=-1, now=NOW))


@pytest.mark.parametrize(
    ("duplicate", "message"),
    [
        ("schedule", "duplicate game identifiers"),
        ("next-games", "upcoming schedule contains duplicate teams"),
        ("roster", "pitching roster contains duplicate team/pitcher rows"),
    ],
)
def test_refresh_rejects_duplicate_upstream_records(tmp_path, duplicate, message):
    schedule = [game(1, "2026-06-01")]
    next_games = [
        {
            "team_id": 100,
            "team_name": "Away",
            "game_pk": 2,
            "game_date": "2026-06-02",
            "game_datetime": "2026-06-02T23:10:00Z",
            "opponent_id": 200,
            "opponent_name": "Home",
            "is_home": False,
            "probable_pitcher_id": None,
            "probable_pitcher_name": None,
            "is_rest_day_today": False,
            "schedule_date": "2026-06-01",
        },
    ]
    rosters = [
        {
            "team_id": 100,
            "team_name": "Away",
            "pitcher_id": 11,
            "pitcher_name": "Starter",
            "depth_role": "SP",
            "depth_order": 0,
            "status_code": "A",
            "status_description": "Active",
        },
    ]
    if duplicate == "schedule":
        schedule *= 2
    elif duplicate == "next-games":
        next_games *= 2
    else:
        rosters *= 2

    with pytest.raises(SnapshotValidationError, match=message):
        asyncio.run(
            update_season(
                2026,
                tmp_path,
                reconcile_days=0,
                now=NOW,
                client_factory=factory(
                    schedule,
                    {1: boxscore(1)},
                    next_games=next_games,
                    rosters=rosters,
                ),
            )
        )


def test_refresh_rejects_duplicate_appearance_from_boxscore(tmp_path):
    rows = boxscore(1)
    boxes = {1: [rows[0], rows[0], *rows[1:]]}

    with pytest.raises(SnapshotValidationError, match="duplicate appearance returned by MLB"):
        asyncio.run(
            update_season(
                2026,
                tmp_path,
                reconcile_days=0,
                now=NOW,
                client_factory=factory([game(1, "2026-06-01")], boxes),
            )
        )


def test_schedule_regression_is_rejected_before_writing(tmp_path):
    schedule = [game(1, "2026-06-01")]
    boxes = {1: boxscore(1)}
    asyncio.run(
        update_season(2026, tmp_path, reconcile_days=0, now=NOW, client_factory=factory(schedule, boxes))
    )

    with pytest.raises(SnapshotValidationError, match="previously completed"):
        asyncio.run(
            update_season(2026, tmp_path, reconcile_days=0, now=NOW, client_factory=factory([], {}))
        )



def test_refresh_persists_next_game_with_optional_probable_starter(tmp_path):
    schedule = [game(1, "2026-07-20")]
    boxes = {1: boxscore(1)}
    next_games = [
        {
            "team_id": 100,
            "team_name": "Away",
            "game_pk": 3,
            "game_date": "2026-07-21",
            "game_datetime": "2026-07-21T23:10:00Z",
            "opponent_id": 200,
            "opponent_name": "Home",
            "is_home": False,
            "probable_pitcher_id": 11,
            "probable_pitcher_name": "Away Probable",
            "is_rest_day_today": False,
            "schedule_date": "2026-07-20",
        },
        {
            "team_id": 200,
            "team_name": "Home",
            "game_pk": 3,
            "game_date": "2026-07-21",
            "game_datetime": "2026-07-21T23:10:00Z",
            "opponent_id": 100,
            "opponent_name": "Away",
            "is_home": True,
            "probable_pitcher_id": None,
            "probable_pitcher_name": None,
            "is_rest_day_today": False,
            "schedule_date": "2026-07-20",
        },
    ]
    asyncio.run(
        update_season(
            2026,
            tmp_path,
            reconcile_days=0,
            now=NOW,
            client_factory=factory(schedule, boxes, next_games=next_games),
        )
    )

    snapshot = load_snapshot(tmp_path, 2026)
    assert snapshot.next_games[100] == NextGameRecord(
        team_id=100,
        team_name="Away",
        game_pk=3,
        game_date="2026-07-21",
        game_datetime="2026-07-21T23:10:00Z",
        opponent_id=200,
        opponent_name="Home",
        is_home=False,
        probable_pitcher_id=11,
        probable_pitcher_name="Away Probable",
        is_rest_day_today=False,
        schedule_date="2026-07-20",
    )
    assert snapshot.next_games[200].probable_pitcher_name is None
    assert (tmp_path / "seasons/2026/next-games.json").exists()


def test_refresh_persists_pitching_roster_depth_and_status(tmp_path):
    schedule = [game(1, "2026-07-20")]
    boxes = {1: boxscore(1)}
    rosters = [
        {
            "team_id": 100,
            "team_name": "Away",
            "pitcher_id": 21,
            "pitcher_name": "Away Reliever",
            "depth_role": "RP",
            "depth_order": 0,
            "status_code": "A",
            "status_description": "Active",
        },
        {
            "team_id": 100,
            "team_name": "Away",
            "pitcher_id": 22,
            "pitcher_name": "Away IL",
            "depth_role": "RP",
            "depth_order": 1,
            "status_code": "D15",
            "status_description": "Injured 15-Day",
        },
    ]
    asyncio.run(
        update_season(
            2026,
            tmp_path,
            reconcile_days=0,
            now=NOW,
            client_factory=factory(schedule, boxes, rosters=rosters),
        )
    )

    snapshot = load_snapshot(tmp_path, 2026)
    assert snapshot.roster_pitchers[(100, 21)].depth_role == "RP"
    assert snapshot.roster_pitchers[(100, 22)].status_code == "D15"
    assert (tmp_path / "seasons/2026/roster-pitchers.json").exists()
