"""Dependency wiring.

This is where the application decides which adapter satisfies each port.
It is the only module that imports both the ports and a concrete adapter —
handlers import the ports only, so swapping storage is a change here and
nowhere else.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from simleague.adapters.postgres import (
    PostgresGameRepository,
    PostgresLeagueRepository,
    PostgresPlayerRepository,
    PostgresPlayerSeasonRepository,
    PostgresPlayerStatRepository,
    PostgresSeasonRepository,
    PostgresTeamRepository,
    PostgresTeamStatRepository,
)
from simleague.domain.repositories import (
    GameRepository,
    LeagueRepository,
    PlayerRepository,
    PlayerSeasonRepository,
    PlayerStatRepository,
    SeasonRepository,
    TeamRepository,
    TeamStatRepository,
)

DSN = os.environ.get("DATABASE_URL", "postgresql:///simleague")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the pool at startup, close it at shutdown.

    Everything before the yield runs once when the app starts; everything
    after runs at shutdown. The pool is created here rather than at import
    time so that importing this module never touches the network — which is
    what lets tests import the app without a database running.

    open=False plus an explicit await pool.open() is deliberate: opening an
    async pool in its constructor is deprecated and will eventually be an
    error.
    """
    pool = AsyncConnectionPool(
        DSN,
        open=False,
        # Every cursor returns dicts keyed by column name. Without this you
        # get tuples and have to index by position, which breaks silently
        # the moment a column is added.
        kwargs={"row_factory": dict_row},
    )
    await pool.open()
    app.state.pool = pool
    try:
        yield
    finally:
        await pool.close()


def _pool(request: Request) -> AsyncConnectionPool[Any]:
    pool: AsyncConnectionPool[Any] | None = getattr(
        request.app.state, "pool", None
    )
    if pool is None:  # pragma: no cover - only if lifespan did not run
        raise RuntimeError("connection pool is not available")
    return pool


# One provider per port. Each returns a concrete adapter, but the annotated
# return type is the protocol — so a handler that depends on one of these
# sees only the interface.


def get_league_repo(request: Request) -> LeagueRepository:
    return PostgresLeagueRepository(_pool(request))


def get_season_repo(request: Request) -> SeasonRepository:
    return PostgresSeasonRepository(_pool(request))


def get_team_repo(request: Request) -> TeamRepository:
    return PostgresTeamRepository(_pool(request))


def get_player_repo(request: Request) -> PlayerRepository:
    return PostgresPlayerRepository(_pool(request))


def get_player_season_repo(request: Request) -> PlayerSeasonRepository:
    return PostgresPlayerSeasonRepository(_pool(request))


def get_game_repo(request: Request) -> GameRepository:
    return PostgresGameRepository(_pool(request))


def get_player_stat_repo(request: Request) -> PlayerStatRepository:
    return PostgresPlayerStatRepository(_pool(request))


def get_team_stat_repo(request: Request) -> TeamStatRepository:
    return PostgresTeamStatRepository(_pool(request))


# Annotated aliases, so a handler signature reads
#
#     async def get_game(game_id: str, games: GameRepo) -> GameModel:
#
# instead of repeating Depends(get_game_repo) in every one.

LeagueRepo = Annotated[LeagueRepository, Depends(get_league_repo)]
SeasonRepo = Annotated[SeasonRepository, Depends(get_season_repo)]
TeamRepo = Annotated[TeamRepository, Depends(get_team_repo)]
PlayerRepo = Annotated[PlayerRepository, Depends(get_player_repo)]
PlayerSeasonRepo = Annotated[
    PlayerSeasonRepository, Depends(get_player_season_repo)
]
GameRepo = Annotated[GameRepository, Depends(get_game_repo)]
PlayerStatRepo = Annotated[PlayerStatRepository, Depends(get_player_stat_repo)]
TeamStatRepo = Annotated[TeamStatRepository, Depends(get_team_stat_repo)]