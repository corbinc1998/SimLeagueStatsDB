from __future__ import annotations

from fastapi import FastAPI, HTTPException, status

from simleague.domain.models import (
    STAT_FIELDS,
    GameModel,
    LeagueModel,
    PlayerGameStatModel,
    PlayerModel,
    SeasonModel,
    TeamModel,
)

app = FastAPI(
    title="SimLeague",
    version="0.1.0",
    description="Simulation results, stats, and standings",
)

# ---------------------------------------------------------------- storage
# Keyed by id instead of a list: lookup is O(1) and mirrors a primary key.
# Each of these becomes a table when you move to Postgres.

leagues: dict[str, dict] = {}
seasons: dict[str, dict] = {}
teams: dict[str, dict] = {}
games: dict[str, dict] = {}
players: dict[str, dict] = {}
player_game_stats: dict[str, dict] = {}


# ---------------------------------------------------------------- helpers


def require(store: dict[str, dict], key: str, label: str) -> dict:
    record = store.get(key)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return record


def reject_duplicate(store: dict[str, dict], key: str, label: str) -> None:
    if key in store:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{label} {key} already exists",
        )


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


# ---------------------------------------------------------------- stats


@app.post("/stats", status_code=status.HTTP_201_CREATED)
def create_stat_line(stat: PlayerGameStatModel) -> PlayerGameStatModel:
    reject_duplicate(player_game_stats, stat.id, "Stat line")
    require(games, stat.gameId, "Game")
    require(players, stat.playerId, "Player")
    player_game_stats[stat.id] = stat.model_dump()
    return stat


@app.get("/stats")
def list_stat_lines(
    gameId: str | None = None,
    playerId: str | None = None,
    seasonId: str | None = None,
) -> list[PlayerGameStatModel]:
    rows = list(player_game_stats.values())
    if gameId is not None:
        rows = [r for r in rows if r["gameId"] == gameId]
    if playerId is not None:
        rows = [r for r in rows if r["playerId"] == playerId]
    if seasonId is not None:
        season_game_ids = {
            g["id"] for g in games.values() if g["seasonId"] == seasonId
        }
        rows = [r for r in rows if r["gameId"] in season_game_ids]
    return [PlayerGameStatModel(**row) for row in rows]


@app.get("/players/{player_id}/totals")
def player_totals(player_id: str, seasonId: str | None = None) -> dict:
    """Career totals, or one season's, by summing the join table.

    This is the payoff for the flat design: no tree walking, and in Postgres
    it becomes a single GROUP BY.
    """
    require(players, player_id, "Player")
    lines = list_stat_lines(playerId=player_id, seasonId=seasonId)
    totals = {field: 0 for field in STAT_FIELDS}
    for line in lines:
        for field in STAT_FIELDS:
            totals[field] += getattr(line, field)
    return {
        "playerId": player_id,
        "seasonId": seasonId,
        "gamesPlayed": len(lines),
        "totals": totals,
    }