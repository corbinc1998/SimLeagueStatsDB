# SimLeague

A stats platform for a CPU-vs-CPU Madden simulation league — nine seasons,
2,403 games, and a box score entry tool for the stats behind them.

The games are simulated in Madden 10 on an Xbox 360 and streamed. Results
were already tracked in a web app; this project takes that export, puts it
in Postgres, and adds what the web app could not: per-player and per-team
box scores, with the splits and totals that follow from them.

---

## What it does

- Imports a nested JSON export of nine seasons into a normalized schema
- Serves games, teams, rosters, and stat lines over a REST API
- Answers matchup questions — a player's numbers against one opponent, a
  team's numbers in one season — without scanning every row
- Provides a web form for entering box scores, which exist only on screen
  in a console game and have to be typed by hand

---

## Architecture

Ports and adapters. The dependency arrow points one way:

```
   HTTP handlers  ──▶  ports (Protocol)  ◀──  adapters
         │                    │                  │
         └──────────▶  domain models  ◀──────────┘
```

`domain/` imports nothing from `adapters/` or `api/`. Delete either of
those folders and the models still import cleanly.

```
src/simleague/
  domain/
    models.py          Pydantic models — no FastAPI, no psycopg
    repositories.py    eight Protocol ports
  adapters/
    postgres.py        the only file in the project containing SQL
    memory.py          dict-backed, for tests
  api/
    main.py            HTTP handlers
    dependencies.py    connection pool lifespan, Depends wiring
```

**Ports are `Protocol`, not ABC.** Adapters do not inherit from them and do
not import them — a class with matching method signatures satisfies the
protocol, and mypy verifies it. That keeps the dependency direction honest
in a way inheritance would not.

**Two adapter sets exist deliberately.** An interface with one
implementation is indirection, not abstraction. The in-memory adapters let
the API be tested without a database, and writing them surfaced a real
semantic difference between the two that a single implementation would have
hidden.

**Repositories return `None` for a miss**, never an HTTP exception.
Raising `HTTPException` from storage would make the domain depend on a web
framework. Turning `None` into a 404 is the handler's job.

---

## Schema decisions

### Composite primary keys on the stat tables

```sql
PRIMARY KEY (game_id, player_id)
```

"One stat line per player per game" is a database guarantee rather than a
check the application has to remember. An earlier design had a surrogate
`id` column and nothing preventing a duplicate, which would have silently
doubled a player's totals.

### Denormalized opponent

`opponent_id` and `is_home` are stored on both stat tables even though the
same facts live in `games`. That is duplication on purpose: "how does this
player perform against Jacksonville" becomes a single index scan on
`(player_id, opponent_id)` instead of a join plus a CASE expression to work
out which side of the game he was on.

The cost of duplication is drift, so a trigger enforces agreement:

```sql
CREATE TRIGGER player_game_stats_matchup_check
    BEFORE INSERT OR UPDATE ON player_game_stats
    FOR EACH ROW EXECUTE FUNCTION assert_stat_matchup();
```

A stat line claiming a matchup that did not happen is rejected. Postgres
cannot express a cross-table `CHECK`, which is why this is a trigger.

### A player has no team

Team membership lives in three places, each answering a different question:

| Table | Question |
|---|---|
| `players` | name, position — things that never change |
| `player_seasons` | who was on this roster that year |
| `player_game_stats.team_id` | who he played for in this game |

A quarterback traded after season 5 has four roster rows for one team and
four for another, and his season 3 stats stay attributed correctly forever
because each stat row carries its own team. Putting `team_id` on `players`
would collapse that history the first time anyone was traded.

### Constraints instead of application checks

Made cannot exceed attempted. Punts inside the 20 cannot exceed punts. A
team cannot play itself. A Super Bowl cannot have a conference. Each one is
a class of bad data that cannot reach the database.

---

## Stat coverage

76 columns per player stat line, 32 per team, grouped as the box score
groups them: passing, rushing, receiving, blocking, defense, kicking,
punting, returns.

Derived values are not stored. Completion percentage, yards per attempt,
field goal percentage and the rest are computed from their components,
because storing them would create two sources of truth that drift the first
time a typo is corrected.

Two values need conversion at the boundary. Time of possession is entered
as `17:15` and stored as seconds, so it can be summed and averaged. Sacks
are `numeric(4,1)`, because half-sacks are real when two players share one.

---

## The import

The source export is nested by season, and three problems had to be fixed
on the way in:

**Season backfill.** 2,304 of 2,403 game records had no season field —
their season was implied by which dictionary key they sat under. Lifting a
record out of that structure lost the information, so it is now written
onto every row.

**Mixed timestamp formats.** Regular season games used naive timestamps
(`2021-09-01T00:00:00`), playoff games used UTC
(`2025-07-18T00:00:00.000Z`). Python raises `TypeError` comparing one to the
other, so any sort spanning both would have crashed. A field validator
forces everything to aware UTC at the boundary.

**Every Super Bowl was tagged AFC.** All nine, which is why the raw
conference counts read 54/45 rather than 45/45. A Super Bowl is not a
conference game, so the field is cleared rather than guessed at.

---

## Setup

Requires Python 3.11+, Node 18+, and Postgres 16.

```bash
# database
createdb simleague
psql simleague -f migrations/001_initial.sql
psql simleague -f migrations/002_full_box_score.sql

# python
python -m venv .venv && source .venv/bin/activate
uv pip install -e .

# import the export
python scripts/seed.py data/raw/nfl-standings-data-8-26-2026.json --write
python scripts/load_db.py

# frontend
cd web && npm install
```

## Running

```bash
uvicorn simleague.api.main:app --reload    # API on :8000
cd web && npm run dev                      # UI on :5173
```

- `http://localhost:5173` — the app
- `http://localhost:8000/docs` — interactive API documentation

## Tests

```bash
pytest                          # 47 tests, no database required
python tests/smoke_test.py      # end-to-end against live Postgres
mypy --strict src/
```

`smoke_test.py` is separate from the suite because it needs a running
server and a real database. It is the only thing that catches errors the
type checker and the in-memory adapters cannot — it found a query summing a
text column, which type-checked, parsed as valid SQL, and never executed in
the in-memory path.

---

## Not included

Team logos. The frontend expects them at `web/public/logos/{teamId}.png`
using the ids in `data/raw` — they are NFL marks and not mine to
redistribute.

---

## Status

The schema, API, and import pipeline are complete and tested against the
full nine-season dataset. The entry form works end to end. No box scores
have been entered yet, so the stat tables are empty — those come from
watching game film and typing.

Known gaps are tracked in the project notes: playoff games are not yet
excluded from season totals, three models still use camelCase attributes
where the rest use an alias generator, and the API has no test coverage
despite the in-memory adapters existing for exactly that purpose.