from datetime import date, timedelta

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


