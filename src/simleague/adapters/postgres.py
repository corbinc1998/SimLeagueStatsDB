"""Postgres adapters.

Each class here satisfies a Protocol from simleague.domain.repositories.
Note that none of them inherit from those protocols and this module does
not import them: satisfying a Protocol is structural, and mypy is what
checks it. The dependency arrow points one way — this module imports the
domain, the domain knows nothing about this module.

This is the only place in the application where SQL appears.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from simleague.domain.models import (
    STAT_FIELDS,
    GameModel,
    LeagueModel,
    PlayerGameStatModel,
    PlayerModel,
    SeasonModel,
    TeamGameStatsModel,
    TeamModel,
)

# ---------------------------------------------------------------- mapping
#
# GameModel uses camelCase attribute names (seasonId, homeTeamId) while the
# columns are snake_case, and one field is named differently altogether:
# the model calls it `date`, the column is `played_at`.
#
# Rather than scatter that translation through every method, it lives here
# once, in both directions.
#
# The stat models do NOT need this. They use snake_case attributes with an
# alias_generator, so their field names already match their columns.
# Converting GameModel to the same pattern would let you delete this whole
# section — a good cleanup, but it ripples through seed.py and main.py.

GAME_FIELD_TO_COLUMN: dict[str, str] = {
    "id": "id",
    "seasonId": "season_id",
    "week": "week",
    "homeTeamId": "home_team_id",
    "awayTeamId": "away_team_id",
    "homeScore": "home_score",
    "awayScore": "away_score",
    "date": "played_at",
    "completed": "completed",
    "isPlayoff": "is_playoff",
    "round": "round",
    "conference": "conference",
    "matchup": "matchup",
    "homeTeamSeed": "home_team_seed",
    "awayTeamSeed": "away_team_seed",
}

GAME_COLUMN_TO_FIELD = {col: field for field, col in GAME_FIELD_TO_COLUMN.items()}
GAME_COLUMNS = list(GAME_FIELD_TO_COLUMN.values())

# The stat models' field names are their column names, so the column list
# is derived rather than written out. Add a column to the model and the
# migration, and this follows automatically.
PLAYER_STAT_COLUMNS = list(PlayerGameStatModel.model_fields)
TEAM_STAT_COLUMNS = list(TeamGameStatsModel.model_fields)

PLAYER_STAT_KEY = ("game_id", "player_id")
TEAM_STAT_KEY = ("game_id", "team_id")


def game_to_row(game: GameModel) -> dict[str, Any]:
    """Model -> a dict keyed by column name, ready to pass as query params."""
    data = game.model_dump()
    row = {GAME_FIELD_TO_COLUMN[field]: value for field, value in data.items()}
    # The seeds are strings on the model ("3") but smallint columns.
    for key in ("home_team_seed", "away_team_seed"):
        if row[key] is not None:
            row[key] = int(row[key])
    return row


def row_to_game(row: dict[str, Any]) -> GameModel:
    """A dict_row from the database -> model."""
    data = {
        GAME_COLUMN_TO_FIELD[col]: value
        for col, value in row.items()
        if col in GAME_COLUMN_TO_FIELD
    }
    for key in ("homeTeamSeed", "awayTeamSeed"):
        if data.get(key) is not None:
            data[key] = str(data[key])
    return GameModel(**data)


def upsert_sql(table: str, columns: list[str], key: tuple[str, ...]) -> str:
    """INSERT ... ON CONFLICT DO UPDATE, generated from a column list.

    Key columns are excluded from the SET clause — setting them to
    themselves is pointless and reads as though they might change.
    """
    cols = ", ".join(columns)
    placeholders = ", ".join(f"%({c})s" for c in columns)
    updates = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in columns if c not in key
    )
    conflict = ", ".join(key)
    action = f"DO UPDATE SET {updates}" if updates else "DO NOTHING"
    return (
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict}) {action} "
        f"RETURNING *"
    )


def where_clause(conditions: list[str]) -> str:
    return f"WHERE {' AND '.join(conditions)}" if conditions else ""


# ---------------------------------------------------------------- leagues


class PostgresLeagueRepository:
    """Satisfies domain.repositories.LeagueRepository."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def create_league(self, league: LeagueModel) -> LeagueModel:
        sql = upsert_sql("leagues", ["id", "name"], ("id",))
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, league.model_dump())
                row = await cur.fetchone()
        assert row is not None
        return LeagueModel(**row)

    async def get_league(self, league_id: str) -> LeagueModel | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM leagues WHERE id = %s", (league_id,)
                )
                row = await cur.fetchone()
        return LeagueModel(**row) if row else None

    async def list_leagues(self) -> list[LeagueModel]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM leagues ORDER BY id")
                rows = await cur.fetchall()
        return [LeagueModel(**row) for row in rows]


# ---------------------------------------------------------------- seasons


class PostgresSeasonRepository:
    """Satisfies domain.repositories.SeasonRepository."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def create_season(self, season: SeasonModel) -> SeasonModel:
        # SeasonModel uses camelCase leagueId; the column is league_id.
        row = {
            "id": season.id,
            "league_id": season.leagueId,
            "name": season.name,
        }
        sql = upsert_sql("seasons", ["id", "league_id", "name"], ("id",))
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, row)
                created = await cur.fetchone()
        assert created is not None
        return self._to_model(created)

    async def get_season(self, season_id: str) -> SeasonModel | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM seasons WHERE id = %s", (season_id,)
                )
                row = await cur.fetchone()
        return self._to_model(row) if row else None

    async def list_seasons(
        self, league_id: str | None = None
    ) -> list[SeasonModel]:
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if league_id is not None:
            conditions.append("league_id = %(league_id)s")
            params["league_id"] = league_id

        # season ids are text but numeric in content, so cast for ordering:
        # a plain sort gives 1, 10, 2.
        sql = (
            f"SELECT * FROM seasons {where_clause(conditions)} "
            f"ORDER BY id::int"
        )
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return [self._to_model(row) for row in rows]

    @staticmethod
    def _to_model(row: dict[str, Any]) -> SeasonModel:
        return SeasonModel(
            id=row["id"], leagueId=row["league_id"], name=row["name"]
        )


# ------------------------------------------------------------------ teams


class PostgresTeamRepository:
    """Satisfies domain.repositories.TeamRepository."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def create_team(self, team: TeamModel) -> TeamModel:
        sql = upsert_sql(
            "teams", ["id", "name", "conference", "division"], ("id",)
        )
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, team.model_dump())
                row = await cur.fetchone()
        assert row is not None
        return TeamModel(**row)

    async def get_team(self, team_id: str) -> TeamModel | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM teams WHERE id = %s", (team_id,)
                )
                row = await cur.fetchone()
        return TeamModel(**row) if row else None

    async def list_teams(
        self,
        conference: str | None = None,
        division: str | None = None,
    ) -> list[TeamModel]:
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if conference is not None:
            conditions.append("conference = %(conference)s")
            params["conference"] = conference
        if division is not None:
            conditions.append("division = %(division)s")
            params["division"] = division

        sql = (
            f"SELECT * FROM teams {where_clause(conditions)} "
            f"ORDER BY conference, division, id"
        )
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return [TeamModel(**row) for row in rows]


# ---------------------------------------------------------------- players


class PostgresPlayerRepository:
    """Satisfies domain.repositories.PlayerRepository."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def create_player(self, player: PlayerModel) -> PlayerModel:
        # PlayerModel still carries teamId, but the schema moved team
        # membership to player_seasons — a player's team is per-season, not a
        # property of the player. teamId is dropped on the way in.
        row = {
            "id": player.id,
            "name": player.name,
            "position": player.position,
        }
        sql = upsert_sql("players", ["id", "name", "position"], ("id",))
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, row)
                created = await cur.fetchone()
        assert created is not None
        return PlayerModel(**created)

    async def get_player(self, player_id: str) -> PlayerModel | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM players WHERE id = %s", (player_id,)
                )
                row = await cur.fetchone()
        return PlayerModel(**row) if row else None

    async def list_players(
        self,
        team_id: str | None = None,
        season_id: str | None = None,
        position: str | None = None,
    ) -> list[PlayerModel]:
        conditions: list[str] = []
        params: dict[str, Any] = {}

        # team and season live on player_seasons, not players, so filtering
        # by either needs a join.
        needs_roster = team_id is not None or season_id is not None
        source = (
            "players p JOIN player_seasons ps ON ps.player_id = p.id"
            if needs_roster
            else "players p"
        )
        if team_id is not None:
            conditions.append("ps.team_id = %(team_id)s")
            params["team_id"] = team_id
        if season_id is not None:
            conditions.append("ps.season_id = %(season_id)s")
            params["season_id"] = season_id
        if position is not None:
            conditions.append("p.position = %(position)s")
            params["position"] = position

        # DISTINCT because a player with several season rows would otherwise
        # come back once per row when only team_id is given.
        sql = (
            f"SELECT DISTINCT p.id, p.name, p.position FROM {source} "
            f"{where_clause(conditions)} ORDER BY p.name"
        )
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return [PlayerModel(**row) for row in rows]


# ------------------------------------------------------------------ games


class PostgresGameRepository:
    """Satisfies domain.repositories.GameRepository."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def create_game(self, game: GameModel) -> GameModel:
        sql = upsert_sql("games", GAME_COLUMNS, ("id",))
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, game_to_row(game))
                created = await cur.fetchone()
        assert created is not None
        return row_to_game(created)

    async def get_game(self, game_id: str) -> GameModel | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM games WHERE id = %s", (game_id,)
                )
                row = await cur.fetchone()
        return row_to_game(row) if row else None

    async def delete_game(self, game_id: str) -> bool:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM games WHERE id = %s", (game_id,))
                # rowcount is what tells the handler whether anything was
                # actually deleted: 204 vs 404.
                return cur.rowcount > 0

    async def list_games(
        self,
        season_id: str | None = None,
        week: int | None = None,
        team_id: str | None = None,
        is_playoff: bool | None = None,
    ) -> list[GameModel]:
        conditions: list[str] = []
        params: dict[str, Any] = {}

        if season_id is not None:
            conditions.append("season_id = %(season_id)s")
            params["season_id"] = season_id
        if week is not None:
            conditions.append("week = %(week)s")
            params["week"] = week
        if is_playoff is not None:
            conditions.append("is_playoff = %(is_playoff)s")
            params["is_playoff"] = is_playoff
        if team_id is not None:
            conditions.append(
                "(home_team_id = %(team_id)s OR away_team_id = %(team_id)s)"
            )
            params["team_id"] = team_id

        sql = (
            f"SELECT * FROM games {where_clause(conditions)} "
            f"ORDER BY season_id::int, week, played_at"
        )
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return [row_to_game(row) for row in rows]


# ----------------------------------------------------------- player stats


class PostgresPlayerStatRepository:
    """Satisfies domain.repositories.PlayerStatRepository."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def create_player_stat_line(
        self, stat: PlayerGameStatModel
    ) -> PlayerGameStatModel:
        sql = upsert_sql(
            "player_game_stats", PLAYER_STAT_COLUMNS, PLAYER_STAT_KEY
        )
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # model_dump() keys already are the column names.
                await cur.execute(sql, stat.model_dump())
                row = await cur.fetchone()
        assert row is not None
        return PlayerGameStatModel(**row)

    async def get_player_stat_line(
        self, game_id: str, player_id: str
    ) -> PlayerGameStatModel | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM player_game_stats "
                    "WHERE game_id = %s AND player_id = %s",
                    (game_id, player_id),
                )
                row = await cur.fetchone()
        # Returning None rather than raising keeps HTTP concerns out of the
        # adapter. The handler decides that None means 404.
        return PlayerGameStatModel(**row) if row else None

    async def delete_player_stat_line(
        self, game_id: str, player_id: str
    ) -> bool:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM player_game_stats "
                    "WHERE game_id = %s AND player_id = %s",
                    (game_id, player_id),
                )
                return cur.rowcount > 0

    async def list_player_stat_lines(
        self,
        game_id: str | None = None,
        player_id: str | None = None,
        team_id: str | None = None,
        opponent_id: str | None = None,
        season_id: str | None = None,
    ) -> list[PlayerGameStatModel]:
        conditions: list[str] = []
        params: dict[str, Any] = {}

        for column, value in (
            ("game_id", game_id),
            ("player_id", player_id),
            ("team_id", team_id),
            ("opponent_id", opponent_id),
            ("season_id", season_id),
        ):
            if value is not None:
                conditions.append(f"{column} = %({column})s")
                params[column] = value

        # season_id is not a column on player_game_stats — it lives on games.
        # The view already joins them, which is what it is for. Columns are
        # named explicitly rather than SELECT *, because the view also
        # exposes week / is_playoff / played_at and Pydantic rejects keys the
        # model does not have.
        columns = ", ".join(PLAYER_STAT_COLUMNS)
        sql = (
            f"SELECT {columns} FROM player_game_stats_full "
            f"{where_clause(conditions)} "
            f"ORDER BY season_id::int, week, game_id, player_id"
        )
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return [PlayerGameStatModel(**row) for row in rows]

    async def player_totals(
        self,
        player_id: str,
        season_id: str | None = None,
        opponent_id: str | None = None,
    ) -> tuple[int, dict[str, int | Decimal]]:
        conditions = ["player_id = %(player_id)s"]
        params: dict[str, Any] = {"player_id": player_id}
        if season_id is not None:
            conditions.append("season_id = %(season_id)s")
            params["season_id"] = season_id
        if opponent_id is not None:
            conditions.append("opponent_id = %(opponent_id)s")
            params["opponent_id"] = opponent_id

        # COALESCE matters: SUM() over zero rows returns NULL, not 0, so a
        # player with no matching games would come back as 71 nulls.
        # count(*) does return 0 over an empty set, so it needs no wrapping.
        sums = ", ".join(
            f"COALESCE(SUM({field}), 0) AS {field}" for field in STAT_FIELDS
        )
        sql = (
            f"SELECT count(*) AS games_played, {sums} "
            f"FROM player_game_stats_full {where_clause(conditions)}"
        )

        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                row = await cur.fetchone()

        assert row is not None  # an aggregate always returns exactly one row
        games_played = int(row.pop("games_played"))
        return games_played, row


# ------------------------------------------------------------- team stats


class PostgresTeamStatRepository:
    """Satisfies domain.repositories.TeamStatRepository."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def create_team_stat_line(
        self, stat: TeamGameStatsModel
    ) -> TeamGameStatsModel:
        sql = upsert_sql("team_game_stats", TEAM_STAT_COLUMNS, TEAM_STAT_KEY)
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, stat.model_dump())
                row = await cur.fetchone()
        assert row is not None
        return TeamGameStatsModel(**row)

    async def get_team_stat_line(
        self, game_id: str, team_id: str
    ) -> TeamGameStatsModel | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM team_game_stats "
                    "WHERE game_id = %s AND team_id = %s",
                    (game_id, team_id),
                )
                row = await cur.fetchone()
        return TeamGameStatsModel(**row) if row else None

    async def delete_team_stat_line(self, game_id: str, team_id: str) -> bool:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM team_game_stats "
                    "WHERE game_id = %s AND team_id = %s",
                    (game_id, team_id),
                )
                return cur.rowcount > 0

    async def list_team_stat_lines(
        self,
        game_id: str | None = None,
        team_id: str | None = None,
        opponent_id: str | None = None,
        season_id: str | None = None,
    ) -> list[TeamGameStatsModel]:
        conditions: list[str] = []
        params: dict[str, Any] = {}

        for column, value in (
            ("game_id", game_id),
            ("team_id", team_id),
            ("opponent_id", opponent_id),
            ("season_id", season_id),
        ):
            if value is not None:
                conditions.append(f"{column} = %({column})s")
                params[column] = value

        columns = ", ".join(TEAM_STAT_COLUMNS)
        sql = (
            f"SELECT {columns} FROM team_game_stats_full "
            f"{where_clause(conditions)} "
            f"ORDER BY season_id::int, week, game_id, team_id"
        )
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return [TeamGameStatsModel(**row) for row in rows]

    async def team_totals(
        self,
        team_id: str,
        season_id: str | None = None,
        opponent_id: str | None = None,
    ) -> tuple[int, dict[str, int]]:
        conditions = ["team_id = %(team_id)s"]
        params: dict[str, Any] = {"team_id": team_id}
        if season_id is not None:
            conditions.append("season_id = %(season_id)s")
            params["season_id"] = season_id
        if opponent_id is not None:
            conditions.append("opponent_id = %(opponent_id)s")
            params["opponent_id"] = opponent_id

        stat_columns = [
            c for c in TEAM_STAT_COLUMNS if c not in TEAM_STAT_KEY + ("is_home",)
        ]
        sums = ", ".join(
            f"COALESCE(SUM({field}), 0) AS {field}" for field in stat_columns
        )
        sql = (
            f"SELECT count(*) AS games_played, {sums} "
            f"FROM team_game_stats_full {where_clause(conditions)}"
        )

        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                row = await cur.fetchone()

        assert row is not None
        games_played = int(row.pop("games_played"))
        return games_played, row