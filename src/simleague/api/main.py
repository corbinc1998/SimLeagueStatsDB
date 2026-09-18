"""HTTP layer.

Handlers translate between HTTP and the domain and do nothing else. They
depend on the repository ports, never on a concrete adapter — there is no
psycopg import in this file and no SQL. Swapping storage is a change in
dependencies.py, not here.

Repositories return None for a miss rather than raising. Turning that into
a 404 is an HTTP decision, so it happens here.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Response, status
from pydantic.alias_generators import to_camel
from fastapi.middleware.cors import CORSMiddleware

from simleague.api.dependencies import (
    GameRepo,
    LeagueRepo,
    PlayerRepo,
    PlayerSeasonRepo,
    PlayerStatRepo,
    SeasonRepo,
    TeamRepo,
    TeamStatRepo,
    lifespan,
)
from simleague.domain.models import (
    GameModel,
    LeagueModel,
    PlayerGameStatModel,
    PlayerModel,
    PlayerSeasonModel,
    ResolvedPlayer,
    ResolvePlayerRequest,
    SeasonModel,
    TeamGameStatsModel,
    TeamModel,
)

app = FastAPI(
    title="SimLeague",
    version="0.1.0",
    description="Simulation results, stats, and standings",
    lifespan=lifespan,
)

# The React dev server runs on a different port, which the browser treats
# as a different origin and blocks by default. This tells it those origins
# are allowed to read responses from this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
            "http://localhost:3000",
    "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- helpers


def not_found(label: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found"
    )


def check_matchup(
    game: GameModel, team_id: str, opponent_id: str, is_home: bool
) -> None:
    """Reject a stat line that claims a matchup the game does not support.

    The database has the same rule as a trigger. Checking it here too means
    the client gets a clear 422 instead of a 500 wrapping a database error.
    """
    if team_id == game.homeTeamId:
        expected_opponent, expected_home = game.awayTeamId, True
    elif team_id == game.awayTeamId:
        expected_opponent, expected_home = game.homeTeamId, False
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"team {team_id} did not play in game {game.id}",
        )

    if opponent_id != expected_opponent or is_home != expected_home:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"game {game.id}: team {team_id} plays {expected_opponent} "
                f"with isHome={expected_home}"
            ),
        )


# ---------------------------------------------------------------- root


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "SimLeague", "docs": "/docs"}


# ---------------------------------------------------------------- leagues


@app.post("/leagues", status_code=status.HTTP_201_CREATED)
async def create_league(league: LeagueModel, repo: LeagueRepo) -> LeagueModel:
    return await repo.create_league(league)


@app.get("/leagues")
async def list_leagues(repo: LeagueRepo) -> list[LeagueModel]:
    return await repo.list_leagues()


@app.get("/leagues/{league_id}")
async def get_league(league_id: str, repo: LeagueRepo) -> LeagueModel:
    league = await repo.get_league(league_id)
    if league is None:
        raise not_found("League")
    return league


# ---------------------------------------------------------------- seasons


@app.post("/seasons", status_code=status.HTTP_201_CREATED)
async def create_season(
    season: SeasonModel, repo: SeasonRepo, leagues: LeagueRepo
) -> SeasonModel:
    if await leagues.get_league(season.leagueId) is None:
        raise not_found("League")
    return await repo.create_season(season)


@app.get("/seasons")
async def list_seasons(
    repo: SeasonRepo, leagueId: str | None = None
) -> list[SeasonModel]:
    return await repo.list_seasons(league_id=leagueId)


@app.get("/seasons/{season_id}")
async def get_season(season_id: str, repo: SeasonRepo) -> SeasonModel:
    season = await repo.get_season(season_id)
    if season is None:
        raise not_found("Season")
    return season


# ---------------------------------------------------------------- teams


@app.post("/teams", status_code=status.HTTP_201_CREATED)
async def create_team(team: TeamModel, repo: TeamRepo) -> TeamModel:
    return await repo.create_team(team)


@app.get("/teams")
async def list_teams(
    repo: TeamRepo,
    conference: str | None = None,
    division: str | None = None,
) -> list[TeamModel]:
    return await repo.list_teams(conference=conference, division=division)


@app.get("/teams/{team_id}")
async def get_team(team_id: str, repo: TeamRepo) -> TeamModel:
    team = await repo.get_team(team_id)
    if team is None:
        raise not_found("Team")
    return team


# ---------------------------------------------------------------- games


@app.post("/games", status_code=status.HTTP_201_CREATED)
async def create_game(game: GameModel, repo: GameRepo) -> GameModel:
    return await repo.create_game(game)


@app.get("/games")
async def list_games(
    repo: GameRepo,
    seasonId: str | None = None,
    week: int | None = None,
    teamId: str | None = None,
    isPlayoff: bool | None = None,
) -> list[GameModel]:
    # Query parameters are camelCase to match the JSON; the port speaks
    # snake_case. The translation happens here, at the boundary.
    return await repo.list_games(
        season_id=seasonId,
        week=week,
        team_id=teamId,
        is_playoff=isPlayoff,
    )


@app.get("/games/{game_id}")
async def get_game(game_id: str, repo: GameRepo) -> GameModel:
    game = await repo.get_game(game_id)
    if game is None:
        raise not_found("Game")
    return game


@app.delete("/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(game_id: str, repo: GameRepo) -> None:
    # The repository reports whether a row was actually removed, which is
    # what distinguishes 204 from 404 without a separate lookup first.
    if not await repo.delete_game(game_id):
        raise not_found("Game")


# ---------------------------------------------------------------- players


@app.post("/players", status_code=status.HTTP_201_CREATED)
async def create_player(player: PlayerModel, repo: PlayerRepo) -> PlayerModel:
    return await repo.create_player(player)


@app.get("/players")
async def list_players(
    repo: PlayerRepo,
    teamId: str | None = None,
    seasonId: str | None = None,
    position: str | None = None,
) -> list[PlayerModel]:
    return await repo.list_players(
        team_id=teamId, season_id=seasonId, position=position
    )


@app.get("/players/{player_id}")
async def get_player(player_id: str, repo: PlayerRepo) -> PlayerModel:
    player = await repo.get_player(player_id)
    if player is None:
        raise not_found("Player")
    return player


@app.post("/players/resolve")
async def resolve_player(
    request: ResolvePlayerRequest,
    players: PlayerRepo,
    rosters: PlayerSeasonRepo,
    seasons: SeasonRepo,
    teams: TeamRepo,
    response: Response,
) -> ResolvedPlayer:
    """Find a player by name or create him, and put him on a roster.

    The entry form calls this when a typed name does not match anything in
    the autocomplete list. One call instead of three, and the form never has
    to invent a player id.

    Ambiguity is surfaced, not guessed at: if the name matches more than one
    existing player, this returns 409 with the candidates so the caller can
    ask which one. The caller then retries with playerId set, or with
    forceNew to say none of them is the right man.
    """
    if await seasons.get_season(request.season_id) is None:
        raise not_found("Season")
    if await teams.get_team(request.team_id) is None:
        raise not_found("Team")

    player: PlayerModel | None = None
    created = False

    if request.player_id is not None:
        # The caller already disambiguated.
        player = await players.get_player(request.player_id)
        if player is None:
            raise not_found("Player")
    elif not request.force_new:
        matches = await players.find_players_by_name(request.name)
        if len(matches) == 1:
            player = matches[0]
        elif len(matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        f"{len(matches)} players are named {request.name!r}. "
                        "Retry with playerId to pick one, or forceNew to "
                        "create another."
                    ),
                    "candidates": [
                        p.model_dump(by_alias=True) for p in matches
                    ],
                },
            )

    if player is None:
        # uuid rather than a slug: names are not unique, and a slug would
        # collide exactly where the data is already ambiguous.
        player = await players.create_player(
            PlayerModel(
                id=str(uuid.uuid4()),
                name=request.name.strip(),
                position=request.position,
            )
        )
        created = True

    # Upsert, so resolving the same player twice in a session is harmless
    # and a mid-season correction just moves him.
    season = await rosters.set_player_season(
        PlayerSeasonModel(
            player_id=player.id,
            season_id=request.season_id,
            team_id=request.team_id,
            position=request.position,
        )
    )

    response.status_code = (
        status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )
    return ResolvedPlayer(player=player, season=season, created=created)


# --------------------------------------------------------- player seasons


@app.put("/players/{player_id}/seasons/{season_id}")
async def set_player_season(
    player_id: str,
    season_id: str,
    entry: PlayerSeasonModel,
    repo: PlayerSeasonRepo,
    players: PlayerRepo,
    seasons: SeasonRepo,
    teams: TeamRepo,
) -> PlayerSeasonModel:
    """Put a player on a team's roster for a season.

    PUT rather than POST because it is idempotent: assigning a player who
    already has a row for that season moves him rather than failing.
    """
    if entry.player_id != player_id or entry.season_id != season_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="body must match the path player and season",
        )
    if await players.get_player(player_id) is None:
        raise not_found("Player")
    if await seasons.get_season(season_id) is None:
        raise not_found("Season")
    if await teams.get_team(entry.team_id) is None:
        raise not_found("Team")
    return await repo.set_player_season(entry)


@app.get("/player-seasons")
async def list_player_seasons(
    repo: PlayerSeasonRepo,
    playerId: str | None = None,
    seasonId: str | None = None,
    teamId: str | None = None,
) -> list[PlayerSeasonModel]:
    return await repo.list_player_seasons(
        player_id=playerId, season_id=seasonId, team_id=teamId
    )


@app.delete(
    "/players/{player_id}/seasons/{season_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_player_season(
    player_id: str, season_id: str, repo: PlayerSeasonRepo
) -> None:
    if not await repo.delete_player_season(player_id, season_id):
        raise not_found("Roster entry")


# ----------------------------------------------------------- player stats


@app.post("/stats/players", status_code=status.HTTP_201_CREATED)
async def create_player_stat_line(
    stat: PlayerGameStatModel,
    repo: PlayerStatRepo,
    games: GameRepo,
    players: PlayerRepo,
    teams: TeamRepo,
) -> PlayerGameStatModel:
    game = await games.get_game(stat.game_id)
    if game is None:
        raise not_found("Game")
    if await players.get_player(stat.player_id) is None:
        raise not_found("Player")
    if await teams.get_team(stat.team_id) is None:
        raise not_found("Team")
    check_matchup(game, stat.team_id, stat.opponent_id, stat.is_home)
    return await repo.create_player_stat_line(stat)


@app.get("/stats/players")
async def list_player_stat_lines(
    repo: PlayerStatRepo,
    gameId: str | None = None,
    playerId: str | None = None,
    teamId: str | None = None,
    opponentId: str | None = None,
    seasonId: str | None = None,
) -> list[PlayerGameStatModel]:
    return await repo.list_player_stat_lines(
        game_id=gameId,
        player_id=playerId,
        team_id=teamId,
        opponent_id=opponentId,
        season_id=seasonId,
    )


@app.get("/stats/players/{game_id}/{player_id}")
async def get_player_stat_line(
    game_id: str, player_id: str, repo: PlayerStatRepo
) -> PlayerGameStatModel:
    stat = await repo.get_player_stat_line(game_id, player_id)
    if stat is None:
        raise not_found("Stat line")
    return stat


@app.delete(
    "/stats/players/{game_id}/{player_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_player_stat_line(
    game_id: str, player_id: str, repo: PlayerStatRepo
) -> None:
    if not await repo.delete_player_stat_line(game_id, player_id):
        raise not_found("Stat line")


# ------------------------------------------------------------- team stats


@app.post("/stats/teams", status_code=status.HTTP_201_CREATED)
async def create_team_stat_line(
    stat: TeamGameStatsModel,
    repo: TeamStatRepo,
    games: GameRepo,
    teams: TeamRepo,
) -> TeamGameStatsModel:
    game = await games.get_game(stat.game_id)
    if game is None:
        raise not_found("Game")
    if await teams.get_team(stat.team_id) is None:
        raise not_found("Team")
    check_matchup(game, stat.team_id, stat.opponent_id, stat.is_home)
    return await repo.create_team_stat_line(stat)


@app.get("/stats/teams")
async def list_team_stat_lines(
    repo: TeamStatRepo,
    gameId: str | None = None,
    teamId: str | None = None,
    opponentId: str | None = None,
    seasonId: str | None = None,
) -> list[TeamGameStatsModel]:
    return await repo.list_team_stat_lines(
        game_id=gameId,
        team_id=teamId,
        opponent_id=opponentId,
        season_id=seasonId,
    )


@app.get("/stats/teams/{game_id}/{team_id}")
async def get_team_stat_line(
    game_id: str, team_id: str, repo: TeamStatRepo
) -> TeamGameStatsModel:
    stat = await repo.get_team_stat_line(game_id, team_id)
    if stat is None:
        raise not_found("Stat line")
    return stat


@app.delete(
    "/stats/teams/{game_id}/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_team_stat_line(
    game_id: str, team_id: str, repo: TeamStatRepo
) -> None:
    if not await repo.delete_team_stat_line(game_id, team_id):
        raise not_found("Stat line")


# ---------------------------------------------------------------- totals


@app.get("/players/{player_id}/totals")
async def player_totals(
    player_id: str,
    repo: PlayerStatRepo,
    players: PlayerRepo,
    seasonId: str | None = None,
    opponentId: str | None = None,
) -> dict[str, Any]:
    """Career totals, one season's, or one matchup's.

    The summing happens in the adapter — a single GROUP BY against Postgres
    rather than shipping every row here to be added up.
    """
    if await players.get_player(player_id) is None:
        raise not_found("Player")

    games_played, totals = await repo.player_totals(
        player_id, season_id=seasonId, opponent_id=opponentId
    )
    return {
        "playerId": player_id,
        "seasonId": seasonId,
        "opponentId": opponentId,
        "gamesPlayed": games_played,
        # STAT_FIELDS are snake_case attribute names; every other response
        # in this API is camelCase.
        "totals": {to_camel(f): v for f, v in totals.items()},
    }


@app.get("/teams/{team_id}/totals")
async def team_totals(
    team_id: str,
    repo: TeamStatRepo,
    teams: TeamRepo,
    seasonId: str | None = None,
    opponentId: str | None = None,
) -> dict[str, Any]:
    if await teams.get_team(team_id) is None:
        raise not_found("Team")

    games_played, totals = await repo.team_totals(
        team_id, season_id=seasonId, opponent_id=opponentId
    )
    return {
        "teamId": team_id,
        "seasonId": seasonId,
        "opponentId": opponentId,
        "gamesPlayed": games_played,
        "totals": {to_camel(f): v for f, v in totals.items()},
    }