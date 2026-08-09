from __future__ import annotations

import json
from pathlib import Path

from pipeline.classify import load_role_overrides


ROOT = Path(__file__).resolve().parents[1]


def test_committed_role_overrides_config_is_strictly_valid():
    """Catch a malformed override at PR time instead of at the nightly refresh."""
    config_path = ROOT / "config" / "role_overrides.json"
    payload = json.loads(config_path.read_text())

    assert payload["seasons"], "config should list at least one season"
    for season_key in payload["seasons"]:
        load_role_overrides(config_path, int(season_key))
