"""Smoke test the API against the live Postgres database.

Everything so far has been verified against in-memory adapters. This walks
the Postgres path for real: resolve a player, put him on a roster, write a
player stat line and both team stat lines, read them back, and check the
totals query.

Cleans up after itself, so it is safe to run repeatedly.

Usage:
    # terminal 1
    uvicorn simleague.api.main:app --reload

    # terminal 2
    python scripts/smoke_test.py
    python scripts/smoke_test.py --keep        # leave the rows behind
    python scripts/smoke_test.py --url http://127.0.0.1:8001

Uses only the standard library, so there is nothing to install.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:8000"

PASS = "  ok  "
FAIL = " FAIL "


class ApiError(Exception):
    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


def call(
    method: str, path: str, payload: dict[str, Any] | None = None
) -> tuple[int, Any]:
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    def decode(raw: bytes) -> Any:
        # A 500 comes back as plain text, not JSON. Returning the raw body
        # instead of raising keeps the failure readable.
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.decode(errors="replace").strip()

    try:
        with urllib.request.urlopen(request) as response:
            return response.status, decode(response.read())
    except urllib.error.HTTPError as error:
        return error.code, decode(error.read())
    except urllib.error.URLError as error:
        print(f"\ncannot reach {BASE} — is uvicorn running?\n  {error.reason}")
        raise SystemExit(1) from error


def expect(label: str, got: int, *allowed: int) -> bool:
    ok = got in allowed
    print(f"{PASS if ok else FAIL} {label:44} {got}")
    return ok


def main() -> int:
    global BASE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE)
    parser.add_argument(
        "--keep", action="store_true", help="do not delete the test rows"
    )
    args = parser.parse_args()
    BASE = args.url.rstrip("/")

    failures = 0

    # ---------------------------------------------------------- find a game
    print("\nreading existing data")
    status, games = call("GET", "/games?seasonId=8&week=1")
    if not expect("GET /games?seasonId=8&week=1", status, 200):
        return 1
    if not games:
        print("  no games found — run scripts/load_db.py first")
        return 1

    game = games[0]
    game_id = game["id"]
    home, away = game["homeTeamId"], game["awayTeamId"]
    print(
        f"       using game {game_id}: "
        f"{away} at {home} ({game['awayScore']}-{game['homeScore']})"
    )

    # --------------------------------------------------------------- resolve
    print("\nresolve a player (creates player + roster row)")
    name = "Smoke Test QB"
    status, resolved = call(
        "POST",
        "/players/resolve",
        {
            "name": name,
            "position": "QB",
            "seasonId": "8",
            "teamId": home,
        },
    )
    failures += not expect("POST /players/resolve", status, 200, 201)
    if status not in (200, 201):
        print("  ", resolved)
        return 1

    player_id = resolved["player"]["id"]
    print(f"       player id {player_id}")
    print(f"       roster: season {resolved['season']['seasonId']} "
          f"team {resolved['season']['teamId']}")

    # idempotent — same name again should find him, not create a second
    status, again = call(
        "POST",
        "/players/resolve",
        {"name": name.lower(), "position": "QB", "seasonId": "8", "teamId": home},
    )
    failures += not expect("  resolve again (case-insensitive)", status, 200)
    if status == 200 and again["player"]["id"] != player_id:
        print(f"{FAIL}   expected the same player id back")
        failures += 1

    # ------------------------------------------------------------ roster read
    print("\nautocomplete source")
    status, roster = call("GET", f"/players?teamId={home}&seasonId=8")
    failures += not expect(f"GET /players?teamId={home}&seasonId=8", status, 200)
    if status == 200:
        names = [p["name"] for p in roster]
        print(f"       {len(names)} on roster: {names}")
        if name not in names:
            print(f"{FAIL}   {name!r} missing from the roster")
            failures += 1

    # ------------------------------------------------------ player stat line
    print("\nplayer stat line")
    stat = {
        "gameId": game_id,
        "playerId": player_id,
        "teamId": home,
        "opponentId": away,
        "isHome": True,
        "passAttempts": 32,
        "passCompletions": 21,
        "passYards": 287,
        "passTouchdowns": 3,
        "interceptions": 1,
        "passLong": 44,
        "sacks": "1.5",
        "rushAttempts": 2,
        "rushYards": -3,
    }
    status, created = call("POST", "/stats/players", stat)
    failures += not expect("POST /stats/players", status, 201)
    if status != 201:
        print("  ", created)
    else:
        print(f"       passYards {created['passYards']}  "
              f"sacks {created['sacks']}  rushYards {created['rushYards']}")

    # the matchup guard
    bad = dict(stat, opponentId=home)
    status, _ = call("POST", "/stats/players", bad)
    failures += not expect("  wrong opponent rejected", status, 422)

    # read it back
    status, read = call("GET", f"/stats/players/{game_id}/{player_id}")
    failures += not expect("GET /stats/players/{game}/{player}", status, 200)
    if status == 200:
        same = read["passYards"] == 287 and read["sacks"] == "1.5"
        print(f"       round trip intact: {same}")
        if not same:
            print(f"         got passYards={read['passYards']} "
                  f"sacks={read['sacks']}")
            failures += 1

    # negative yardage survived (smallint is signed)
    if status == 200 and read["rushYards"] != -3:
        print(f"{FAIL}   negative rush yards lost: {read['rushYards']}")
        failures += 1

    # ------------------------------------------------------- team stat lines
    print("\nteam stat lines (both sides)")
    status, _ = call(
        "POST",
        "/stats/teams",
        {
            "gameId": game_id, "teamId": home, "opponentId": away,
            "isHome": True, "points": game["homeScore"],
            "totalOffense": 412, "thirdDownAtt": 16, "thirdDownConv": 4,
            "redzoneTrips": 4, "redzoneTouchdowns": 3, "redzoneFieldGoals": 1,
            "timeOfPossession": 1935,
        },
    )
    failures += not expect(f"POST /stats/teams ({home})", status, 201)

    status, _ = call(
        "POST",
        "/stats/teams",
        {
            "gameId": game_id, "teamId": away, "opponentId": home,
            "isHome": False, "points": game["awayScore"], "totalOffense": 355,
        },
    )
    failures += not expect(f"POST /stats/teams ({away})", status, 201)

    status, rows = call("GET", f"/stats/teams?gameId={game_id}")
    failures += not expect("GET /stats/teams?gameId=...", status, 200)
    if status == 200:
        print(f"       {len(rows)} rows for this game (expected 2)")
        if len(rows) != 2:
            failures += 1

    # ---------------------------------------------------------------- totals
    print("\ntotals (the GROUP BY path)")
    status, totals = call("GET", f"/players/{player_id}/totals")
    failures += not expect("GET /players/{id}/totals", status, 200)
    if status == 200:
        t = totals["totals"]
        print(f"       gamesPlayed {totals['gamesPlayed']}  "
              f"passYards {t['passYards']}  sacks {t['sacks']}")
        if totals["gamesPlayed"] != 1 or t["passYards"] != 287:
            failures += 1
        # a stat nobody recorded should be 0, not null — the COALESCE
        if t.get("puntLong") != 0:
            print(f"{FAIL}   COALESCE missing: puntLong = {t.get('puntLong')}")
            failures += 1

    status, totals = call("GET", f"/players/{player_id}/totals?opponentId={away}")
    failures += not expect("  filtered by opponent", status, 200)
    if status == 200 and totals["gamesPlayed"] != 1:
        failures += 1

    status, totals = call("GET", f"/players/{player_id}/totals?opponentId={home}")
    failures += not expect("  wrong opponent gives zero", status, 200)
    if status == 200:
        if totals["gamesPlayed"] != 0:
            failures += 1
        elif totals["totals"]["passYards"] != 0:
            print(f"{FAIL}   empty SUM should be 0, got "
                  f"{totals['totals']['passYards']}")
            failures += 1

    status, tt = call("GET", f"/teams/{home}/totals?seasonId=8")
    failures += not expect(f"GET /teams/{home}/totals?seasonId=8", status, 200)
    if status != 200:
        print(f"       {tt}")
    if status == 200:
        print(f"       gamesPlayed {tt['gamesPlayed']}  "
              f"points {tt['totals']['points']}")

    # --------------------------------------------------------------- cleanup
    if args.keep:
        print("\nleaving rows in place (--keep)")
        print(f"  player  {player_id}")
        print(f"  game    {game_id}")
    else:
        print("\ncleanup")
        status, _ = call("DELETE", f"/stats/players/{game_id}/{player_id}")
        failures += not expect("DELETE player stat line", status, 204)
        for team in (home, away):
            status, _ = call("DELETE", f"/stats/teams/{game_id}/{team}")
            failures += not expect(f"DELETE team stat line ({team})", status, 204)
        status, _ = call("DELETE", f"/players/{player_id}/seasons/8")
        failures += not expect("DELETE roster entry", status, 204)
        print("       (the players row stays — there is no delete endpoint;")
        print(f"        remove by hand if you care: DELETE FROM players "
              f"WHERE id = '{player_id}';)")

    print()
    if failures:
        print(f"{failures} check(s) failed")
        return 1
    print("all checks passed — the Postgres path works end to end")
    return 0


if __name__ == "__main__":
    sys.exit(main())