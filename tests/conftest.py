"""Shared fixtures.

`scripts/` is not a package, so it is not on the import path by default.
Adding it here lets tests do `import seed` the same way the CLI does.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

EXPORT_PATH = PROJECT_ROOT / "data" / "raw" / "nfl-standings-data-8-26-2026.json"


@pytest.fixture
def regular_game() -> dict[str, Any]:
    """A regular season record exactly as it appears in the export.

    Note what is absent: no seasonId, no playoff fields, and a naive date.
    """
    return {
        "week": 1,
        "homeTeamId": "jax",
        "awayTeamId": "ten",
        "date": "2026-03-30T00:00:00",
        "broadcast": "",
        "status": "final",
        "homeScore": 34,
        "awayScore": 27,
        "id": "1774907847609",
        "completed": True,
    }


@pytest.fixture
def playoff_game() -> dict[str, Any]:
    """A playoff record. Carries seasonId already, and a Z-suffixed date."""
    return {
        "round": "wildcard",
        "conference": "AFC",
        "matchup": 1,
        "homeTeamId": "mia",
        "homeTeamSeed": "3",
        "awayTeamId": "cin",
        "awayTeamSeed": "6",
        "homeScore": 30,
        "awayScore": 17,
        "date": "2025-07-18T00:00:00.000Z",
        "broadcast": "",
        "status": "final",
        "isPlayoff": True,
        "id": "playoff_1752816943569",
        "week": 18,
        "seasonId": "1",
        "completed": True,
    }


@pytest.fixture
def superbowl_game(playoff_game: dict[str, Any]) -> dict[str, Any]:
    """The export tags every Super Bowl as AFC."""
    return {
        **playoff_game,
        "id": "playoff_superbowl_1",
        "round": "superbowl",
        "conference": "AFC",
        "matchup": 1,
    }


@pytest.fixture
def tiny_export(
    regular_game: dict[str, Any], playoff_game: dict[str, Any]
) -> dict[str, Any]:
    """Two seasons, two games each, in the nested export shape."""
    return {
        "exportDate": "2026-08-26T17:40:11.094Z",
        "seasons": {
            "1": {
                "name": "1",
                "games": [
                    regular_game,
                    {**playoff_game, "seasonId": "1"},
                ],
            },
            "2": {
                "name": "2",
                "games": [
                    {**regular_game, "id": "game-2a"},
                    {**playoff_game, "id": "game-2b", "seasonId": "2"},
                ],
            },
        },
    }


@pytest.fixture
def export_file(tmp_path: Path, tiny_export: dict[str, Any]) -> Path:
    import json

    path = tmp_path / "export.json"
    path.write_text(json.dumps(tiny_export))
    return path