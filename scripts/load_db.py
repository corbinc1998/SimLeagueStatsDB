"""Load normalized JSON records into Postgres.

Reads what `seed.py --write` produced and inserts it in dependency order.
Idempotent: re-running updates existing rows rather than failing, so this is
safe to run repeatedly while the schema is still moving.

Usage:
    python scripts/load_db.py                      # load ./data/normalized
    python scripts/load_db.py --dsn ...            # non-default connection
    python scripts/load_db.py --verify             # counts and spot checks only
    python scripts/load_db.py --truncate           # empty the tables first

Connection defaults to $DATABASE_URL, then to a local `simleague` database.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

import psycopg

DEFAULT_DSN = os.environ.get(
    "DATABASE_URL", "postgresql:///simleague"
)
DEFAULT_INPUT = Path("data/normalized")

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")


def snake(name: str) -> str:
    """seasonId -> season_id, homeTeamId -> home_team_id."""
    return _CAMEL.sub("_", name).lower()


def as_smallint(value: Any) -> int | None:
    """The export stores playoff seeds as strings ("3"), the column is
    smallint. Empty strings appear too, so they map to NULL rather than
    blowing up the insert."""
    if value is None or value == "":
        return None
    return int(value)


# JSON key -> (column, converter). Anything not listed is snake_cased and
# passed through unchanged.
OVERRIDES: dict[str, tuple[str, Callable[[Any], Any]]] = {
    "date": ("played_at", lambda v: v),
    "homeTeamSeed": ("home_team_seed", as_smallint),
    "awayTeamSeed": ("away_team_seed", as_smallint),
}


def to_row(record: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in record.items():
        column, convert = OVERRIDES.get(key, (snake(key), lambda v: v))
        row[column] = convert(value)
    return row


# Order matters: a table cannot be loaded before what it references.
LOAD_ORDER: list[tuple[str, str, list[str]]] = [
    ("leagues", "leagues.json", ["id"]),
    ("seasons", "seasons.json", ["id"]),
    ("teams", "teams.json", ["id"]),
    ("games", "games.json", ["id"]),
]


def upsert_sql(table: str, columns: list[str], conflict: list[str]) -> str:
    """INSERT with ON CONFLICT DO UPDATE, so a re-run refreshes rows instead
    of failing on the primary key."""
    cols = ", ".join(columns)
    placeholders = ", ".join(f"%({c})s" for c in columns)
    updatable = [c for c in columns if c not in conflict]
    if updatable:
        assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in updatable)
        action = f"DO UPDATE SET {assignments}"
    else:
        action = "DO NOTHING"
    return (
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})\n"
        f"ON CONFLICT ({', '.join(conflict)}) {action}"
    )


def load_table(
    conn: psycopg.Connection,
    table: str,
    records: Iterable[dict[str, Any]],
    conflict: list[str],
) -> int:
    rows = [to_row(r) for r in records]
    if not rows:
        print(f"  {table:10} 0 records, skipped")
        return 0

    columns = sorted(rows[0])
    for row in rows:
        if sorted(row) != columns:
            missing = set(columns) ^ set(row)
            raise SystemExit(
                f"{table}: inconsistent keys across records ({missing})"
            )

    sql = upsert_sql(table, columns, conflict)
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    print(f"  {table:10} {len(rows):>5} records")
    return len(rows)


def read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"missing input file: {path}  (run seed.py --write first)")
    return json.loads(path.read_text())


def truncate(conn: psycopg.Connection) -> None:
    """CASCADE reaches the stat tables, which reference games."""
    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE games, teams, seasons, leagues, "
            "players, player_seasons, team_game_stats, player_game_stats "
            "RESTART IDENTITY CASCADE"
        )
    print("truncated all tables")


VERIFY_QUERIES: list[tuple[str, str]] = [
    ("leagues", "SELECT count(*) FROM leagues"),
    ("seasons", "SELECT count(*) FROM seasons"),
    ("teams", "SELECT count(*) FROM teams"),
    ("games", "SELECT count(*) FROM games"),
    ("players", "SELECT count(*) FROM players"),
    ("team stat rows", "SELECT count(*) FROM team_game_stats"),
    ("player stat rows", "SELECT count(*) FROM player_game_stats"),
]


def verify(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        print("row counts:")
        for label, sql in VERIFY_QUERIES:
            cur.execute(sql)
            row = cur.fetchone()
            print(f"  {label:18} {row[0] if row else 0:>6}")

        print()
        print("games per season:")
        cur.execute(
            """
            SELECT season_id,
                   count(*) AS total,
                   count(*) FILTER (WHERE is_playoff) AS playoff,
                   min(week) AS first_week,
                   max(week) FILTER (WHERE NOT is_playoff) AS last_reg_week
            FROM games
            GROUP BY season_id
            ORDER BY season_id::int
            """
        )
        for season, total, playoff, first_week, last_reg in cur.fetchall():
            print(
                f"  season {season:>2}  {total:>4} games"
                f"  ({playoff} playoff)  weeks {first_week}-{last_reg}"
            )

        print()
        print("playoff conferences:")
        cur.execute(
            """
            SELECT coalesce(conference, 'none') AS conf, count(*)
            FROM games WHERE is_playoff
            GROUP BY conference ORDER BY conf
            """
        )
        for conf, count in cur.fetchall():
            print(f"  {conf:>5}  {count:>4}")

        print()
        print("integrity:")
        cur.execute(
            """
            SELECT count(*) FROM games g
            LEFT JOIN teams h ON h.id = g.home_team_id
            LEFT JOIN teams a ON a.id = g.away_team_id
            WHERE h.id IS NULL OR a.id IS NULL
            """
        )
        orphan_teams = cur.fetchone()
        cur.execute(
            "SELECT count(*) FROM games g "
            "LEFT JOIN seasons s ON s.id = g.season_id WHERE s.id IS NULL"
        )
        orphan_seasons = cur.fetchone()
        print(f"  games with unknown team    {orphan_teams[0] if orphan_teams else 0}")
        print(f"  games with unknown season  {orphan_seasons[0] if orphan_seasons else 0}")

        cur.execute("SELECT played_at FROM games ORDER BY played_at LIMIT 1")
        earliest = cur.fetchone()
        if earliest:
            print(f"  earliest played_at         {earliest[0]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--truncate", action="store_true")
    parser.add_argument("--verify", action="store_true", help="skip the load")
    args = parser.parse_args()

    with psycopg.connect(args.dsn) as conn:
        if args.verify:
            verify(conn)
            return 0

        if args.truncate:
            truncate(conn)

        print(f"loading from {args.input}")
        total = 0
        for table, filename, conflict in LOAD_ORDER:
            total += load_table(
                conn, table, read(args.input / filename), conflict
            )

        conn.commit()
        print(f"\ncommitted {total} records\n")
        verify(conn)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())