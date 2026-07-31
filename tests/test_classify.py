from datetime import date, timedelta

import pytest

from pipeline.classify import Appearance, classify_appearances


BASE = date(2026, 6, 1)


def appearance(
    game_pk: int,
    day: int,
    pitcher_id: int,
    pitches: int,
    started: bool,
    order: int = 0,
    team_id: int = 119,
) -> Appearance:
    return Appearance(
        game_pk=game_pk,
        game_date=BASE + timedelta(days=day),
        team_id=team_id,
        pitcher_id=pitcher_id,
        pitches=pitches,
        official_started=started,
        appearance_order=order,
    )


def role(result, row):
    return result[(row.game_pk, row.team_id, row.pitcher_id)].role


def test_short_failed_start_stays_sp():
    failed = appearance(1, 0, 10, 31, True)
    prior_start = appearance(2, -6, 10, 92, True)
    result = classify_appearances([failed, prior_start])
    assert role(result, failed) == "SP"


def test_relief_dominant_opener_moves_to_rp():
    opener = appearance(10, 0, 20, 24, True, 0)
    bulk = appearance(10, 0, 21, 72, False, 1)
    relief_history = [appearance(11 + i, -(i + 1) * 3, 20, 18 + i, False) for i in range(4)]
    result = classify_appearances([opener, bulk, *relief_history])
    assert role(result, opener) == "RP"


def test_starter_identity_bulk_moves_to_sp():
    bulk = appearance(20, 0, 30, 76, False, 1)
    nearby_start = appearance(21, 7, 30, 88, True)
    result = classify_appearances([bulk, nearby_start])
    assert role(result, bulk) == "SP"


def test_long_reliever_does_not_become_sp_by_length_alone():
    long_relief = appearance(30, 0, 40, 67, False, 1)
    relief_history = [appearance(31 + i, -(i + 1) * 4, 40, 22, False) for i in range(3)]
    result = classify_appearances([long_relief, *relief_history])
    classification = result[(long_relief.game_pk, long_relief.team_id, long_relief.pitcher_id)]
    assert classification.role == "RP"
    assert classification.needs_review is True


def test_manual_override_wins():
    row = appearance(40, 0, 50, 14, False)
    result = classify_appearances([row], {"40:50": {"role": "SP", "note": "spot starter"}})
    assert role(result, row) == "SP"


@pytest.mark.parametrize(
    ("opener_pitches", "follower_pitches", "expected"),
    [
        (40, 45, "RP"),
        (41, 45, "SP"),
        (40, 44, "SP"),
    ],
)
def test_opener_shape_uses_inclusive_pitch_boundaries(
    opener_pitches: int,
    follower_pitches: int,
    expected: str,
):
    opener = appearance(100, 0, 60, opener_pitches, True, 0)
    follower = appearance(100, 0, 61, follower_pitches, False, 1)
    relief_history = [appearance(101 + day, -day, 60, 30, False) for day in range(1, 4)]

    result = classify_appearances([opener, follower, *relief_history])

    assert role(result, opener) == expected


@pytest.mark.parametrize(("relief_pitches", "expected"), [(35, "RP"), (36, "SP")])
def test_relief_identity_median_boundary(relief_pitches: int, expected: str):
    opener = appearance(110, 0, 70, 40, True, 0)
    follower = appearance(110, 0, 71, 45, False, 1)
    relief_history = [
        appearance(111 + day, -day, 70, relief_pitches, False)
        for day in range(1, 4)
    ]

    result = classify_appearances([opener, follower, *relief_history])

    assert role(result, opener) == expected


@pytest.mark.parametrize(("days_away", "expected"), [(28, "SP"), (29, "RP")])
def test_starter_identity_window_boundary(days_away: int, expected: str):
    bulk = appearance(120, 0, 80, 45, False, 1)
    start = appearance(121, days_away, 80, 80, True)

    result = classify_appearances([bulk, start])

    assert role(result, bulk) == expected


@pytest.mark.parametrize(("pitches", "needs_review"), [(54, False), (55, True)])
def test_long_relief_review_boundary(pitches: int, needs_review: bool):
    row = appearance(130, 0, 90, pitches, False, 1)

    classification = classify_appearances([row])[(row.game_pk, row.team_id, row.pitcher_id)]

    assert classification.role == "RP"
    assert classification.needs_review is needs_review


def test_string_override_is_case_insensitive():
    row = appearance(140, 0, 100, 14, False)

    result = classify_appearances([row], {"140:100": "sp"})

    assert role(result, row) == "SP"
    assert result[(140, 119, 100)].reason == "manual override"


def test_invalid_override_falls_back_to_domain_classification():
    row = appearance(150, 0, 110, 14, False)

    result = classify_appearances([row], {"150:110": {"role": "swingman"}})

    assert role(result, row) == "RP"
    assert result[(150, 119, 110)].reason == "official reliever"

