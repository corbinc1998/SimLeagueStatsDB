from __future__ import annotations

from typing import Any, Hashable

from pydantic.alias_generators import to_camel

from fastapi import FastAPI, HTTPException, status

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

app = FastAPI(
    title="SimLeague",
    version="0.1.0",
    description="Simulation results, stats, and standings",
)

# ---------------------------------------------------------------- storage
# Keyed by id instead of a list: lookup is O(1) and mirrors a primary key.
#
# The two stat stores are keyed by a tuple, mirroring the composite primary
# keys in the schema: (game_id, player_id) and (game_id, team_id). That is
# what makes "one row per player per game" structural rather than a rule
# the application has to remember to enforce.

leagues: dict[str, dict] = {}
seasons: dict[str, dict] = {}
teams: dict[str, dict] = {}
games: dict[str, dict] = {}
players: dict[str, dict] = {}
player_game_stats: dict[tuple[str, str], dict] = {}
team_game_stats: dict[tuple[str, str], dict] = {}


# ---------------------------------------------------------------- helpers


def require(store: dict[Any, dict], key: Hashable, label: str) -> dict:
    record = store.get(key)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return record


def reject_duplicate(store: dict[Any, dict], key: Hashable, label: str) -> None:
    if key in store:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{label} {key} already exists",
        )


def check_matchup(game: dict, team_id: str, opponent_id: str, is_home: bool) -> None:
    """Reject a stat line that claims a matchup the game does not support.

    Mirrors the assert_stat_matchup trigger in the schema. opponent_id and
    is_home are denormalized onto the stat row so splits queries are a
    single index scan; this is what keeps that copy honest.
    """
    if team_id == game["homeTeamId"]:
        expected_opponent, expected_home = game["awayTeamId"], True
    elif team_id == game["awayTeamId"]:
        expected_opponent, expected_home = game["homeTeamId"], False
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"team {team_id} did not play in game {game['id']}",
        )

    if opponent_id != expected_opponent or is_home != expected_home:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"game {game['id']}: team {team_id} plays {expected_opponent} "
                f"with isHome={expected_home}"
            ),
        )


def season_game_ids(season_id: str) -> set[str]:
    return {g["id"] for g in games.values() if g["seasonId"] == season_id}


# ---------------------------------------------------------------- root


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "SimLeague", "docs": "/docs"}


# ---------------------------------------------------------------- leagues


@app.post("/leagues", status_code=status.HTTP_201_CREATED)
def create_league(league: LeagueModel) -> LeagueModel:
    reject_duplicate(leagues, league.id, "League")
    leagues[league.id] = league.model_dump()
    return league


@app.get("/leagues")
def list_leagues() -> list[LeagueModel]:
    return [LeagueModel(**row) for row in leagues.values()]


@app.get("/leagues/{league_id}")
def get_league(league_id: str) -> LeagueModel:
    return LeagueModel(**require(leagues, league_id, "League"))


# ---------------------------------------------------------------- seasons


@app.post("/seasons", status_code=status.HTTP_201_CREATED)
def create_season(season: SeasonModel) -> SeasonModel:
    reject_duplicate(seasons, season.id, "Season")
    require(leagues, season.leagueId, "League")
    seasons[season.id] = season.model_dump()
    return season


@app.get("/seasons")
def list_seasons(leagueId: str | None = None) -> list[SeasonModel]:
    rows = list(seasons.values())
    if leagueId is not None:
        rows = [r for r in rows if r["leagueId"] == leagueId]
    return [SeasonModel(**row) for row in rows]


@app.get("/seasons/{season_id}")
def get_season(season_id: str) -> SeasonModel:
    return SeasonModel(**require(seasons, season_id, "Season"))


# ---------------------------------------------------------------- teams


@app.post("/teams", status_code=status.HTTP_201_CREATED)
def create_team(team: TeamModel) -> TeamModel:
    reject_duplicate(teams, team.id, "Team")
    teams[team.id] = team.model_dump()
    return team


@app.get("/teams")
def list_teams() -> list[TeamModel]:
    return [TeamModel(**row) for row in teams.values()]


@app.get("/teams/{team_id}")
def get_team(team_id: str) -> TeamModel:
    return TeamModel(**require(teams, team_id, "Team"))


# ---------------------------------------------------------------- games


@app.post("/games", status_code=status.HTTP_201_CREATED)
def create_game(game: GameModel) -> GameModel:
    reject_duplicate(games, game.id, "Game")
    games[game.id] = game.model_dump()
    return game


@app.get("/games")
def list_games(
    seasonId: str | None = None,
    week: int | None = None,
    teamId: str | None = None,
    isPlayoff: bool | None = None,
) -> list[GameModel]:
    rows = list(games.values())
    if seasonId is not None:
        rows = [r for r in rows if r["seasonId"] == seasonId]
    if week is not None:
        rows = [r for r in rows if r["week"] == week]
    if isPlayoff is not None:
        rows = [r for r in rows if r["isPlayoff"] == isPlayoff]
    if teamId is not None:
        rows = [
            r for r in rows
            if r["homeTeamId"] == teamId or r["awayTeamId"] == teamId
        ]
    rows.sort(key=lambda r: (r["seasonId"], r["week"], r["date"]))
    return [GameModel(**row) for row in rows]


@app.get("/games/{game_id}")
def get_game(game_id: str) -> GameModel:
    return GameModel(**require(games, game_id, "Game"))


@app.delete("/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game(game_id: str) -> None:
    require(games, game_id, "Game")
    del games[game_id]


# ---------------------------------------------------------------- players


@app.post("/players", status_code=status.HTTP_201_CREATED)
def create_player(player: PlayerModel) -> PlayerModel:
    reject_duplicate(players, player.id, "Player")
    players[player.id] = player.model_dump()
    return player


@app.get("/players")
def list_players(teamId: str | None = None) -> list[PlayerModel]:
    rows = list(players.values())
    if teamId is not None:
        rows = [r for r in rows if r["teamId"] == teamId]
    return [PlayerModel(**row) for row in rows]


@app.get("/players/{player_id}")
def get_player(player_id: str) -> PlayerModel:
    return PlayerModel(**require(players, player_id, "Player"))


# ----------------------------------------------------------- player stats


@app.post("/stats/players", status_code=status.HTTP_201_CREATED)
def create_player_stat_line(stat: PlayerGameStatModel) -> PlayerGameStatModel:
    game = require(games, stat.game_id, "Game")
    require(players, stat.player_id, "Player")
    require(teams, stat.team_id, "Team")
    check_matchup(game, stat.team_id, stat.opponent_id, stat.is_home)
    key = (stat.game_id, stat.player_id)
    reject_duplicate(player_game_stats, key, "Stat line")
    player_game_stats[key] = stat.model_dump()
    return stat


@app.get("/stats/players")
def list_player_stat_lines(
    gameId: str | None = None,
    playerId: str | None = None,
    teamId: str | None = None,
    opponentId: str | None = None,
    seasonId: str | None = None,
) -> list[PlayerGameStatModel]:
    rows = list(player_game_stats.values())
    if gameId is not None:
        rows = [r for r in rows if r["game_id"] == gameId]
    if playerId is not None:
        rows = [r for r in rows if r["player_id"] == playerId]
    if teamId is not None:
        rows = [r for r in rows if r["team_id"] == teamId]
    if opponentId is not None:
        rows = [r for r in rows if r["opponent_id"] == opponentId]
    if seasonId is not None:
        allowed = season_game_ids(seasonId)
        rows = [r for r in rows if r["game_id"] in allowed]
    return [PlayerGameStatModel(**row) for row in rows]


@app.get("/stats/players/{game_id}/{player_id}")
def get_player_stat_line(game_id: str, player_id: str) -> PlayerGameStatModel:
    row = require(player_game_stats, (game_id, player_id), "Stat line")
    return PlayerGameStatModel(**row)


@app.delete(
    "/stats/players/{game_id}/{player_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_player_stat_line(game_id: str, player_id: str) -> None:
    require(player_game_stats, (game_id, player_id), "Stat line")
    del player_game_stats[(game_id, player_id)]


# ------------------------------------------------------------- team stats


@app.post("/stats/teams", status_code=status.HTTP_201_CREATED)
def create_team_stat_line(stat: TeamGameStatsModel) -> TeamGameStatsModel:
    game = require(games, stat.game_id, "Game")
    require(teams, stat.team_id, "Team")
    check_matchup(game, stat.team_id, stat.opponent_id, stat.is_home)
    key = (stat.game_id, stat.team_id)
    reject_duplicate(team_game_stats, key, "Team stat line")
    team_game_stats[key] = stat.model_dump()
    return stat


@app.get("/stats/teams")
def list_team_stat_lines(
    gameId: str | None = None,
    teamId: str | None = None,
    opponentId: str | None = None,
    seasonId: str | None = None,
) -> list[TeamGameStatsModel]:
    rows = list(team_game_stats.values())
    if gameId is not None:
        rows = [r for r in rows if r["game_id"] == gameId]
    if teamId is not None:
        rows = [r for r in rows if r["team_id"] == teamId]
    if opponentId is not None:
        rows = [r for r in rows if r["opponent_id"] == opponentId]
    if seasonId is not None:
        allowed = season_game_ids(seasonId)
        rows = [r for r in rows if r["game_id"] in allowed]
    return [TeamGameStatsModel(**row) for row in rows]


@app.get("/stats/teams/{game_id}/{team_id}")
def get_team_stat_line(game_id: str, team_id: str) -> TeamGameStatsModel:
    row = require(team_game_stats, (game_id, team_id), "Team stat line")
    return TeamGameStatsModel(**row)


@app.delete(
    "/stats/teams/{game_id}/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_team_stat_line(game_id: str, team_id: str) -> None:
    require(team_game_stats, (game_id, team_id), "Team stat line")
    del team_game_stats[(game_id, team_id)]


# ---------------------------------------------------------------- totals


@app.get("/players/{player_id}/totals")
def player_totals(
    player_id: str,
    seasonId: str | None = None,
    opponentId: str | None = None,
) -> dict:
    """Career totals, one season's, or one matchup's, by summing stat lines.

    The opponentId filter is the reason opponent_id sits on the stat row
    rather than being derived from the game on every query. In Postgres this
    whole handler becomes a single GROUP BY.
    """
    require(players, player_id, "Player")
    lines = list_player_stat_lines(
        playerId=player_id, seasonId=seasonId, opponentId=opponentId
    )

    # Seed each total from the model's own default so a Decimal field starts
    # as a Decimal rather than an int.
    blank = PlayerGameStatModel(
        game_id="", player_id="", team_id="", opponent_id="x", is_home=True
    )
    totals: dict[str, Any] = {f: getattr(blank, f) for f in STAT_FIELDS}

    for line in lines:
        for field in STAT_FIELDS:
            totals[field] += getattr(line, field)

    return {
        "playerId": player_id,
        "seasonId": seasonId,
        "opponentId": opponentId,
        "gamesPlayed": len(lines),
        # camelCase to match every other response; STAT_FIELDS are the
        # snake_case attribute names.
        "totals": {to_camel(f): v for f, v in totals.items()},
    }