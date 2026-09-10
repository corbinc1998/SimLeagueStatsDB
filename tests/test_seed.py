"""Tests for the builders, load_export, and the integrity checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import seed
from simleague.domain.models import GameModel


class TestBuildTeams:
    def test_thirty_two_teams(self) -> None:
        assert len(seed.build_teams()) == 32

    def test_every_team_has_conference_and_division(self) -> None:
        for team in seed.build_teams():
            assert team.conference in ("AFC", "NFC")
            assert team.division in ("East", "North", "South", "West")

    def test_four_teams_per_division(self) -> None:
        """A wrong division assignment is the one error the script cannot
        detect on its own, so pin the shape here."""
        buckets: dict[tuple[str, str], int] = {}
        for team in seed.build_teams():
            key = (team.conference or "", team.division or "")
            buckets[key] = buckets.get(key, 0) + 1
        assert len(buckets) == 8
        assert all(count == 4 for count in buckets.values())

    def test_ids_are_unique(self) -> None:
        ids = [t.id for t in seed.build_teams()]
        assert len(ids) == len(set(ids))


class TestBuildSeasons:
    def test_uses_name_when_present(self, tiny_export: dict[str, Any]) -> None:
        seasons = seed.build_seasons(tiny_export)
        assert [s.name for s in seasons] == ["1", "2"]

    def test_falls_back_to_key_when_name_absent(self) -> None:
        """Guards the `value.get("name", key)` two-argument form. Writing
        `value.get("name, key")` instead returns None and every season ends
        up named "None" with no error raised."""
        raw = {"seasons": {"3": {"games": []}}}
        seasons = seed.build_seasons(raw)
        assert seasons[0].name == "3"
        assert seasons[0].name != "None"

    def test_sorted_numerically_not_lexically(self) -> None:
        raw = {"seasons": {str(n): {"name": str(n), "games": []} for n in range(1, 12)}}
        ids = [s.id for s in seed.build_seasons(raw)]
        assert ids == [str(n) for n in range(1, 12)]
        assert ids[9] == "10"  # lexical sort would put "10" second

    def test_all_reference_the_league(self, tiny_export: dict[str, Any]) -> None:
        for season in seed.build_seasons(tiny_export):
            assert season.leagueId == seed.LEAGUE_ID


class TestLoadExport:
    def test_returns_all_four_collections(self, export_file: Path) -> None:
        data = seed.load_export(export_file)
        assert set(data) == {"leagues", "seasons", "teams", "games"}

    def test_flattens_nested_games(self, export_file: Path) -> None:
        data = seed.load_export(export_file)
        assert len(data["games"]) == 4

    def test_every_game_carries_its_season(self, export_file: Path) -> None:
        data = seed.load_export(export_file)
        by_season: dict[str, int] = {}
        for game in data["games"]:
            by_season[game.seasonId] = by_season.get(game.seasonId, 0) + 1
        assert by_season == {"1": 2, "2": 2}

    def test_games_are_models_not_dicts(self, export_file: Path) -> None:
        data = seed.load_export(export_file)
        assert all(isinstance(g, GameModel) for g in data["games"])

    def test_empty_season_is_tolerated(self, tmp_path: Path) -> None:
        import json

        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"seasons": {"1": {"name": "1"}}}))
        assert seed.load_export(path)["games"] == []


class TestCheck:
    """Each check should stay quiet on clean data and fire on the specific
    corruption it exists to catch."""

    def test_clean_data_has_no_problems(self, export_file: Path) -> None:
        assert seed.check(seed.load_export(export_file)) == []

    def test_duplicate_ids_detected(self, export_file: Path) -> None:
        data = seed.load_export(export_file)
        data["games"].append(data["games"][0])
        problems = seed.check(data)
        assert any("duplicate" in p for p in problems)

    def test_orphan_season_detected(self, export_file: Path) -> None:
        data = seed.load_export(export_file)
        data["games"][0] = data["games"][0].model_copy(update={"seasonId": "99"})
        problems = seed.check(data)
        assert any("unknown seasons" in p for p in problems)

    def test_unknown_team_detected(self, export_file: Path) -> None:
        data = seed.load_export(export_file)
        data["games"][0] = data["games"][0].model_copy(
            update={"homeTeamId": "lv"}
        )
        problems = seed.check(data)
        assert any("unknown team" in p for p in problems)

    def test_team_playing_itself_detected(self, export_file: Path) -> None:
        data = seed.load_export(export_file)
        data["games"][0] = data["games"][0].model_copy(
            update={"awayTeamId": data["games"][0].homeTeamId}
        )
        problems = seed.check(data)
        assert any("playing itself" in p for p in problems)

    def test_naive_date_detected(self, export_file: Path) -> None:
        """Only reachable if the model validator is bypassed, which is
        exactly what this check is watching for."""
        from datetime import datetime

        data = seed.load_export(export_file)
        data["games"][0] = data["games"][0].model_construct(
            **{**data["games"][0].model_dump(), "date": datetime(2021, 9, 1)}
        )
        problems = seed.check(data)
        assert any("naive" in p for p in problems)

    def test_reports_every_problem_not_just_the_first(
        self, export_file: Path
    ) -> None:
        data = seed.load_export(export_file)
        data["games"].append(data["games"][0])
        data["games"][1] = data["games"][1].model_copy(update={"seasonId": "99"})
        assert len(seed.check(data)) >= 2


class TestWrite:
    def test_writes_one_file_per_collection(
        self, export_file: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "normalized"
        seed.write(seed.load_export(export_file), out)
        written = {p.name for p in out.iterdir()}
        assert written == {
            "leagues.json",
            "seasons.json",
            "teams.json",
            "games.json",
        }

    def test_output_is_json_serializable(
        self, export_file: Path, tmp_path: Path
    ) -> None:
        """mode="json" is what turns the datetime into a string. Without it
        json.dumps raises."""
        import json

        out = tmp_path / "normalized"
        seed.write(seed.load_export(export_file), out)
        games = json.loads((out / "games.json").read_text())
        assert isinstance(games[0]["date"], str)
        assert games[0]["date"].endswith("Z")

    def test_playoff_fields_are_null_not_absent(
        self, export_file: Path, tmp_path: Path
    ) -> None:
        """Null maps to a nullable column; absent means the column is
        missing from the insert."""
        import json

        out = tmp_path / "normalized"
        seed.write(seed.load_export(export_file), out)
        games = json.loads((out / "games.json").read_text())
        regular = next(g for g in games if not g["isPlayoff"])
        assert "round" in regular
        assert regular["round"] is None

    def test_creates_missing_directory(
        self, export_file: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "does" / "not" / "exist"
        seed.write(seed.load_export(export_file), out)
        assert (out / "games.json").exists()


EXPORT = Path(__file__).resolve().parents[1] / "data/raw"
REAL_EXPORT = EXPORT / "nfl-standings-data-8-26-2026.json"


@pytest.fixture(scope="module")
def data() -> dict[str, list[Any]]:
    """Parsed once for the whole module — 2,403 records is not free."""
    return seed.load_export(REAL_EXPORT)


@pytest.mark.skipif(not REAL_EXPORT.exists(), reason="real export not present")
class TestRealExport:
    """Pinned against the actual nine-season file. These fail loudly if a
    future export changes shape."""

    def test_game_count(self, data: dict[str, list[Any]]) -> None:
        assert len(data["games"]) == 2403

    def test_nine_seasons_of_267(self, data: dict[str, list[Any]]) -> None:
        assert len(data["seasons"]) == 9
        for season in data["seasons"]:
            rows = [g for g in data["games"] if g.seasonId == season.id]
            assert len(rows) == 267

    def test_regular_playoff_split(self, data: dict[str, list[Any]]) -> None:
        playoff = [g for g in data["games"] if g.isPlayoff]
        assert len(playoff) == 99
        assert len(data["games"]) - len(playoff) == 2304

    def test_conferences_balance_after_superbowl_fix(
        self, data: dict[str, list[Any]]
    ) -> None:
        """Straight from the export this reads AFC 54 / NFC 45."""
        playoff = [g for g in data["games"] if g.isPlayoff]
        afc = sum(1 for g in playoff if g.conference == "AFC")
        nfc = sum(1 for g in playoff if g.conference == "NFC")
        none = sum(1 for g in playoff if g.conference is None)
        assert (afc, nfc, none) == (45, 45, 9)

    def test_no_naive_dates_survive(self, data: dict[str, list[Any]]) -> None:
        assert all(g.date.tzinfo is not None for g in data["games"])

    def test_all_checks_pass(self, data: dict[str, list[Any]]) -> None:
        assert seed.check(data) == []