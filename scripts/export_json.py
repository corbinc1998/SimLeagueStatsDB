"""Export the league from Postgres back to the nested JSON the web app reads.

The inverse of scripts/load_db.py. Produces the same shape as the original
export — seasons keyed by id, each holding its games — so a new season
entered in the app can be pulled back out, and so the data has a form that
does not depend on Postgres being up.

    python scripts/export_json.py                          # to stdout
    python scripts/export_json.py --out data/raw/league.json
    python scripts/export_json.py --season 10              # one season
    python scripts/export_json.py --dsn postgresql://...

Two fields the original export had are gone and are not invented here:
`broadcast`, which was an empty string on most records, and `status`, which
was missing on 886 of 2,403 games and said nothing that `completed` does
not. `status` is written anyway, derived from `completed`, because the web
app branches on it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

DEFAULT_DSN = os.environ.get("DATABASE_URL", "postgresql:///simleague")

# Ordered the same way the API orders games: season, week, kickoff, then id
# as a tiebreaker. Without the last one, games that tie on every other key
# come back in whatever order the table happens to hold them, which changes
# as soon as a row is updated.
GAMES_SQL = """
    SELECT id, season_id, week, home_team_id, away_team_id,
           home_score, away_score, played_at, completed,
           is_playoff, round, conference, matchup,
           home_team_seed, away_team_seed
    FROM games
    {where}
    ORDER BY season_id::int, week, played_at, id
"""

SEASONS_SQL = "SELECT id, name FROM seasons {where} ORDER BY id::int"


def to_export(row: dict[str, Any]) -> dict[str, Any]:
    """One database row in the export's shape."""
    game: dict[str, Any] = {
        "id": row["id"],
        "seasonId": row["season_id"],
        "week": row["week"],
        "homeTeamId": row["home_team_id"],
        "awayTeamId": row["away_team_id"],
        "homeScore": row["home_score"],
        "awayScore": row["away_score"],
        # timestamptz comes back timezone-aware; the export used a Z suffix
        "date": row["played_at"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "completed": row["completed"],
        # the web app branches on status, so derive it rather than omit it
        "status": "final" if row["completed"] else "scheduled",
    }
    if row["is_playoff"]:
        game["isPlayoff"] = True
        for key, column in (
            ("round", "round"),
            ("conference", "conference"),
            ("matchup", "matchup"),
            ("homeTeamSeed", "home_team_seed"),
            ("awayTeamSeed", "away_team_seed"),
        ):
            value = row[column]
            if value is not None:
                # seeds are text in the export, smallint in the database
                game[key] = str(value) if key.endswith("Seed") else value
    return game


def export(connection: psycopg.Connection, season: str | None) -> dict[str, Any]:
    where = "WHERE id = %(season)s" if season else ""
    games_where = "WHERE season_id = %(season)s" if season else ""
    params = {"season": season} if season else {}

    with connection.cursor(row_factory=dict_row) as cur:
        cur.execute(SEASONS_SQL.format(where=where), params)
        seasons = {
            row["id"]: {"name": row["name"], "games": []} for row in cur.fetchall()
        }

        cur.execute(GAMES_SQL.format(where=games_where), params)
        for row in cur.fetchall():
            season_id = row["season_id"]
            if season_id not in seasons:
                # a game whose season has no record still has to land
                # somewhere, rather than vanish from the export
                seasons[season_id] = {"name": season_id, "games": []}
            seasons[season_id]["games"].append(to_export(row))

    return {
        "exportDate": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "seasons": seasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--season", help="export one season instead of all")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()

    with psycopg.connect(args.dsn) as connection:
        data = export(connection, args.season)

    text = json.dumps(data, indent=args.indent)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        print(text)

    counts = {sid: len(s["games"]) for sid, s in data["seasons"].items()}
    total = sum(counts.values())
    print(f"{len(counts)} seasons, {total} games", file=sys.stderr)
    for season_id in sorted(counts, key=lambda s: int(s) if s.isdigit() else 0):
        print(f"  season {season_id:>2}  {counts[season_id]:>4} games", file=sys.stderr)
    if args.out:
        print(f"written {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
