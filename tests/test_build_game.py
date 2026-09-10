"""Tests for build_game — the three transforms and the dropped fields."""

from __future__ import annotations

from datetime import timezone
from typing import Any

import pytest

import seed


class TestSeasonIdBackfill:
    """Transform 1. The single most important line in the script."""

    def test_regular_game_gains_season_id(self, regular_game: dict[str, Any]) -> None:
        assert "seasonId" not in regular_game
        game = seed.build_game(regular_game, "8")
        assert game.seasonId == "8"

    def test_playoff_game_season_id_matches_position(
        self, playoff_game: dict[str, Any]
    ) -> None:
        """Playoff records carry their own seasonId. The positional key wins,
        because position is where the export's real structure lives."""
        assert playoff_game["seasonId"] == "1"
        game = seed.build_game(playoff_game, "7")
        assert game.seasonId == "7"

    def test_source_record_is_not_mutated(self, regular_game: dict[str, Any]) -> None:
        seed.build_game(regular_game, "8")
        assert "seasonId" not in regular_game


class TestDateNormalization:
    """Transform 2. Done by the model's validator, not by seed.py."""

    def test_naive_date_becomes_utc(self, regular_game: dict[str, Any]) -> None:
        game = seed.build_game(regular_game, "1")
        assert game.date.tzinfo is not None
        assert game.date.utcoffset() == timezone.utc.utcoffset(None)

    def test_z_suffixed_date_stays_utc(self, playoff_game: dict[str, Any]) -> None:
        game = seed.build_game(playoff_game, "1")
        assert game.date.tzinfo is not None

    def test_mixed_dates_are_comparable(
        self, regular_game: dict[str, Any], playoff_game: dict[str, Any]
    ) -> None:
        """The bug this transform exists to prevent: comparing a naive
        datetime to an aware one raises TypeError, and list_games sorts by
        date across both kinds of record."""
        naive_source = seed.build_game(regular_game, "1")
        aware_source = seed.build_game(playoff_game, "1")
        assert isinstance(naive_source.date < aware_source.date, bool)

    def test_serializes_with_z(self, regular_game: dict[str, Any]) -> None:
        game = seed.build_game(regular_game, "1")
        assert game.model_dump(mode="json")["date"].endswith("Z")


class TestSuperbowlConference:
    """Transform 3. The export tags all nine Super Bowls AFC."""

    def test_superbowl_conference_cleared(
        self, superbowl_game: dict[str, Any]
    ) -> None:
        assert superbowl_game["conference"] == "AFC"
        game = seed.build_game(superbowl_game, "1")
        assert game.conference is None

    def test_other_playoff_rounds_keep_conference(
        self, playoff_game: dict[str, Any]
    ) -> None:
        game = seed.build_game(playoff_game, "1")
        assert game.conference == "AFC"

    @pytest.mark.parametrize("round_name", ["wildcard", "divisional", "conference"])
    def test_non_superbowl_rounds_unaffected(
        self, playoff_game: dict[str, Any], round_name: str
    ) -> None:
        game = seed.build_game({**playoff_game, "round": round_name}, "1")
        assert game.conference == "AFC"


class TestDroppedFields:
    def test_status_and_broadcast_removed(
        self, regular_game: dict[str, Any]
    ) -> None:
        game = seed.build_game(regular_game, "1")
        assert not hasattr(game, "status")
        assert not hasattr(game, "broadcast")

    def test_missing_dropped_fields_are_fine(
        self, regular_game: dict[str, Any]
    ) -> None:
        """886 records have no status field at all."""
        record = {k: v for k, v in regular_game.items() if k != "status"}
        assert seed.build_game(record, "1").id == regular_game["id"]


class TestValidation:
    """build_game constructs through the model, so bad data fails here
    rather than reaching storage."""

    def test_unknown_round_rejected(self, playoff_game: dict[str, Any]) -> None:
        with pytest.raises(Exception):
            seed.build_game({**playoff_game, "round": "quarterfinal"}, "1")

    def test_missing_required_field_rejected(
        self, regular_game: dict[str, Any]
    ) -> None:
        record = {k: v for k, v in regular_game.items() if k != "homeScore"}
        with pytest.raises(Exception):
            seed.build_game(record, "1")

    def test_playoff_defaults_applied(self, regular_game: dict[str, Any]) -> None:
        game = seed.build_game(regular_game, "1")
        assert game.isPlayoff is False
        assert game.round is None
        assert game.homeTeamSeed is None