"""Flatten the nested standings export into normalized records.

Reads the `{seasons: {"1": {games: [...]}}}` shape and produces flat
league / season / team / game records that match the models in main.py.

Usage:
    python seed.py nfl-standings-data-8-26-2026.json           # report only
    python seed.py nfl-standings-data-8-26-2026.json --write   # write ./data
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from simleague.domain.models import (
    GameModel,
    LeagueModel,
    SeasonModel,
    TeamModel,
)

LEAGUE_ID = "sim"
LEAGUE_NAME = "The Sim League"

# 2007 alignment, which is what the team id vocabulary in the export reflects
# (oak, sd, stl, was are all present).
TEAMS: dict[str, tuple[str, str, str]] = {
    "buf": ("Bills", "AFC", "East"),
    "mia": ("Dolphins", "AFC", "East"),
    "ne": ("Patriots", "AFC", "East"),
    "nyj": ("Jets", "AFC", "East"),
    "bal": ("Ravens", "AFC", "North"),
    "cin": ("Bengals", "AFC", "North"),
    "cle": ("Browns", "AFC", "North"),
    "pit": ("Steelers", "AFC", "North"),
    "hou": ("Texans", "AFC", "South"),
    "ind": ("Colts", "AFC", "South"),
    "jax": ("Jaguars", "AFC", "South"),
    "ten": ("Titans", "AFC", "South"),
    "den": ("Broncos", "AFC", "West"),
    "kc": ("Chiefs", "AFC", "West"),
    "oak": ("Raiders", "AFC", "West"),
    "sd": ("Chargers", "AFC", "West"),
    "dal": ("Cowboys", "NFC", "East"),
    "nyg": ("Giants", "NFC", "East"),
    "phi": ("Eagles", "NFC", "East"),
    "was": ("Redskins", "NFC", "East"),
    "chi": ("Bears", "NFC", "North"),
    "det": ("Lions", "NFC", "North"),
    "gb": ("Packers", "NFC", "North"),
    "min": ("Vikings", "NFC", "North"),
    "atl": ("Falcons", "NFC", "South"),
    "car": ("Panthers", "NFC", "South"),
    "no": ("Saints", "NFC", "South"),
    "tb": ("Buccaneers", "NFC", "South"),
    "ari": ("Cardinals", "NFC", "West"),
    "sf": ("49ers", "NFC", "West"),
    "sea": ("Seahawks", "NFC", "West"),
    "stl": ("Rams", "NFC", "West"),
}

# Present in the export, deliberately not carried over.
#   status    - missing on 886 of 2,403 games, and `completed` is True on all
#               of them, so the two fields say the same thing and one is
#               unreliable.
#   broadcast - empty string on most records.
DROPPED_FIELDS = {"status", "broadcast"}


def build_league() -> LeagueModel:
    return LeagueModel(id=LEAGUE_ID, name=LEAGUE_NAME)


def build_teams() -> list[TeamModel]:
    return [
        TeamModel(id=tid, name=name, conference=conf, division=div)
        for tid, (name, conf, div) in TEAMS.items()
    ]


def build_seasons(raw: dict[str, Any]) -> list[SeasonModel]:
    return [
        SeasonModel(id=key, leagueId=LEAGUE_ID, name=str(value.get("name", key)))
        for key, value in sorted(raw["seasons"].items(), key=lambda kv: int(kv[0]))
    ]


def build_game(record: dict[str, Any], season_id: str) -> GameModel:
    """Transform one raw game record.

    Three fixes happen here:

    1. seasonId backfill. Absent on the 2,304 regular season records, where
       the season is implied by which dict key the game sits under. Lift the
       record out of the tree and that meaning is lost, so it gets written
       onto the record explicitly.

    2. Date normalization. Handled by GameModel's to_utc validator, which is
       why records go through the model rather than straight into storage.
       The export mixes naive (`...T00:00:00`) and UTC (`...T00:00:00.000Z`)
       timestamps, and Python raises TypeError comparing one to the other.

    3. Super Bowl conference. All nine Super Bowls in the export are tagged
       AFC, which is why the raw counts come out AFC 54 / NFC 45. A Super
       Bowl is not a conference game, so the field is cleared rather than
       guessed at.
    """
    payload = {k: v for k, v in record.items() if k not in DROPPED_FIELDS}
    payload["seasonId"] = season_id

    if payload.get("round") == "superbowl":
        payload["conference"] = None

    return GameModel(**payload)


def load_export(path: Path) -> dict[str, list[Any]]:
    raw = json.loads(path.read_text())

    games: list[GameModel] = []
    for season_key, season in sorted(
        raw["seasons"].items(), key=lambda kv: int(kv[0])
    ):
        for record in season.get("games", []):
            games.append(build_game(record, season_key))

    return {
        "leagues": [build_league()],
        "seasons": build_seasons(raw),
        "teams": build_teams(),
        "games": games,
    }


def check(data: dict[str, list[Any]]) -> list[str]:
    """Integrity checks the models cannot express on their own."""
    problems: list[str] = []
    games: list[GameModel] = data["games"]

    ids = Counter(g.id for g in games)
    duplicates = [gid for gid, n in ids.items() if n > 1]
    if duplicates:
        problems.append(f"duplicate game ids: {duplicates[:5]}")

    season_ids = {s.id for s in data["seasons"]}
    orphans = {g.seasonId for g in games} - season_ids
    if orphans:
        problems.append(f"games referencing unknown seasons: {sorted(orphans)}")

    unknown_teams = set()
    for g in games:
        unknown_teams |= {g.homeTeamId, g.awayTeamId} - TEAMS.keys()
    if unknown_teams:
        problems.append(f"unknown team ids: {sorted(unknown_teams)}")

    for g in games:
        if g.homeTeamId == g.awayTeamId:
            problems.append(f"game {g.id} has a team playing itself")

    naive = [g.id for g in games if g.date.tzinfo is None]
    if naive:
        problems.append(f"timezone-naive dates survived: {naive[:5]}")

    return problems


def report(data: dict[str, list[Any]]) -> None:
    games: list[GameModel] = data["games"]
    regular = [g for g in games if not g.isPlayoff]
    playoff = [g for g in games if g.isPlayoff]

    print(f"leagues  {len(data['leagues']):>6}")
    print(f"teams    {len(data['teams']):>6}")
    print(f"seasons  {len(data['seasons']):>6}")
    print(f"games    {len(games):>6}  ({len(regular)} regular, {len(playoff)} playoff)")
    print()

    print("per season:")
    for season in data["seasons"]:
        rows = [g for g in games if g.seasonId == season.id]
        weeks = [g.week for g in rows if not g.isPlayoff]
        print(
            f"  season {season.id:>2}  {len(rows):>4} games"
            f"  weeks {min(weeks)}-{max(weeks)}"
        )
    print()

    rounds = Counter(g.round for g in playoff if g.round)
    print("playoff rounds:", dict(rounds))
    conferences = Counter(g.conference for g in playoff)
    print("playoff conferences:", dict(conferences))
    print()

    problems = check(data)
    if problems:
        print("PROBLEMS")
        for p in problems:
            print(" ", p)
    else:
        print("all checks passed")


def write(data: dict[str, list[Any]], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, records in data.items():
        target = out / f"{name}.json"
        target.write_text(
            json.dumps([r.model_dump(mode="json") for r in records], indent=2)
        )
        print(f"wrote {target}  ({len(records)} records)")


def seed_app(path: Path) -> None:
    """Load the export directly into the running app's in-memory stores."""
    from simleague.api import main

    data = load_export(path)
    for name in ("leagues", "seasons", "teams", "games"):
        store = getattr(main, name)
        store.clear()
        for record in data[name]:
            store[record.id] = record.model_dump()


def main_cli() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"no such file: {path}")
        return 1

    data = load_export(path)
    report(data)

    if "--write" in sys.argv:
        print()
        write(data, Path("data/normalized"))

    return 0 if not check(data) else 1


if __name__ == "__main__":
    raise SystemExit(main_cli())