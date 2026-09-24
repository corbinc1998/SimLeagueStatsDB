"""In-memory adapters.

The same seven protocols as adapters/postgres.py, backed by dicts. These
exist so the API can be tested without a database: a TestClient plus these
repositories gives you fast tests with no fixtures and nothing to clean up
between them.

They are also the check on whether the protocols were designed well. An
interface with one implementation is not an interface, it is indirection.

Storage is keyed the way the schema is keyed — a single id for most tables,
a tuple for the two stat tables, mirroring their composite primary keys.
That is what makes "one row per player per game" structural here too.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from simleague.domain.models import (
    STAT_FIELDS,
    TEAM_STAT_FIELDS,
    GameModel,
    LeagueModel,
    PlayerGameStatModel,
    PlayerModel,
    PlayerSeasonModel,
    SeasonModel,
    TeamGameStatsModel,
    TeamModel,
)

class InMemoryStore:
    """Shared state for a set of in-memory repositories.

    One store handed to several repositories keeps them consistent with each
    other — a stat repository can see the games a game repository wrote,
    the same way separate Postgres repositories share one database.
    """

    def __init__(self) -> None:
        self.leagues: dict[str, LeagueModel] = {}
        self.seasons: dict[str, SeasonModel] = {}
        self.teams: dict[str, TeamModel] = {}
        self.players: dict[str, PlayerModel] = {}
        self.player_seasons: dict[tuple[str, str], PlayerSeasonModel] = {}
        self.games: dict[str, GameModel] = {}
        self.player_stats: dict[tuple[str, str], PlayerGameStatModel] = {}
        self.team_stats: dict[tuple[str, str], TeamGameStatsModel] = {}

    def clear(self) -> None:
        for store in (
            self.leagues, self.seasons, self.teams, self.players,
            self.player_seasons, self.games, self.player_stats,
            self.team_stats,
        ):
            store.clear()


class InMemoryLeagueRepository:
    """Satisfies domain.repositories.LeagueRepository."""

    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def create_league(self, league: LeagueModel) -> LeagueModel:
        self.store.leagues[league.id] = league
        return league

    async def get_league(self, league_id: str) -> LeagueModel | None:
        return self.store.leagues.get(league_id)

    async def list_leagues(self) -> list[LeagueModel]:
        return sorted(self.store.leagues.values(), key=lambda x: x.id)


class InMemorySeasonRepository:
    """Satisfies domain.repositories.SeasonRepository."""

    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def create_season(self, season: SeasonModel) -> SeasonModel:
        self.store.seasons[season.id] = season
        return season

    async def get_season(self, season_id: str) -> SeasonModel | None:
        return self.store.seasons.get(season_id)

    async def list_seasons(
        self, league_id: str | None = None
    ) -> list[SeasonModel]:
        rows = list(self.store.seasons.values())
        if league_id is not None:
            rows = [r for r in rows if r.leagueId == league_id]
        # Sort numerically, matching the ORDER BY id::int in the Postgres
        # adapter: a plain string sort gives 1, 10, 2.
        return sorted(rows, key=lambda x: int(x.id) if x.id.isdigit() else 0)


class InMemoryTeamRepository:
    """Satisfies domain.repositories.TeamRepository."""

    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def create_team(self, team: TeamModel) -> TeamModel:
        self.store.teams[team.id] = team
        return team

    async def get_team(self, team_id: str) -> TeamModel | None:
        return self.store.teams.get(team_id)

    async def list_teams(
        self,
        conference: str | None = None,
        division: str | None = None,
    ) -> list[TeamModel]:
        rows = list(self.store.teams.values())
        if conference is not None:
            rows = [r for r in rows if r.conference == conference]
        if division is not None:
            rows = [r for r in rows if r.division == division]
        return sorted(
            rows, key=lambda x: (x.conference or "", x.division or "", x.id)
        )


class InMemoryPlayerRepository:
    """Satisfies domain.repositories.PlayerRepository."""

    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def create_player(self, player: PlayerModel) -> PlayerModel:
        self.store.players[player.id] = player
        return player

    async def get_player(self, player_id: str) -> PlayerModel | None:
        return self.store.players.get(player_id)

    async def list_players(
        self,
        team_id: str | None = None,
        season_id: str | None = None,
        position: str | None = None,
    ) -> list[PlayerModel]:
        rows = list(self.store.players.values())
        if position is not None:
            rows = [r for r in rows if r.position == position]
        if team_id is not None or season_id is not None:
            # Team and season live on the roster, not on the player — the
            # same join the Postgres adapter does against player_seasons.
            allowed = {
                entry.player_id
                for entry in self.store.player_seasons.values()
                if (team_id is None or entry.team_id == team_id)
                and (season_id is None or entry.season_id == season_id)
            }
            rows = [r for r in rows if r.id in allowed]
        return sorted(rows, key=lambda x: x.name)


    async def find_players_by_name(self, name: str) -> list[PlayerModel]:
        target = name.strip().lower()
        return sorted(
            (
                p for p in self.store.players.values()
                if p.name.strip().lower() == target
            ),
            key=lambda x: x.id,
        )


class InMemoryPlayerSeasonRepository:
    """Satisfies domain.repositories.PlayerSeasonRepository."""

    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def set_player_season(
        self, entry: PlayerSeasonModel
    ) -> PlayerSeasonModel:
        self.store.player_seasons[(entry.player_id, entry.season_id)] = entry
        return entry

    async def get_player_season(
        self, player_id: str, season_id: str
    ) -> PlayerSeasonModel | None:
        return self.store.player_seasons.get((player_id, season_id))

    async def delete_player_season(
        self, player_id: str, season_id: str
    ) -> bool:
        return (
            self.store.player_seasons.pop((player_id, season_id), None)
            is not None
        )

    async def list_player_seasons(
        self,
        player_id: str | None = None,
        season_id: str | None = None,
        team_id: str | None = None,
    ) -> list[PlayerSeasonModel]:
        rows = list(self.store.player_seasons.values())
        if player_id is not None:
            rows = [r for r in rows if r.player_id == player_id]
        if season_id is not None:
            rows = [r for r in rows if r.season_id == season_id]
        if team_id is not None:
            rows = [r for r in rows if r.team_id == team_id]
        return sorted(
            rows,
            key=lambda x: (
                int(x.season_id) if x.season_id.isdigit() else 0,
                x.team_id,
                x.player_id,
            ),
        )


class InMemoryGameRepository:
    """Satisfies domain.repositories.GameRepository."""

    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def create_game(self, game: GameModel) -> GameModel:
        self.store.games[game.id] = game
        return game

    async def get_game(self, game_id: str) -> GameModel | None:
        return self.store.games.get(game_id)

    async def delete_game(self, game_id: str) -> bool:
        existed = self.store.games.pop(game_id, None) is not None
        if existed:
            # Mirrors ON DELETE CASCADE on the stat tables' game_id
            # foreign key.
            for key in [k for k in self.store.player_stats if k[0] == game_id]:
                del self.store.player_stats[key]
            for key in [k for k in self.store.team_stats if k[0] == game_id]:
                del self.store.team_stats[key]
        return existed

    async def list_games(
        self,
        season_id: str | None = None,
        week: int | None = None,
        team_id: str | None = None,
        is_playoff: bool | None = None,
    ) -> list[GameModel]:
        rows = list(self.store.games.values())
        if season_id is not None:
            rows = [r for r in rows if r.seasonId == season_id]
        if week is not None:
            rows = [r for r in rows if r.week == week]
        if is_playoff is not None:
            rows = [r for r in rows if r.isPlayoff == is_playoff]
        if team_id is not None:
            rows = [
                r for r in rows
                if team_id in (r.homeTeamId, r.awayTeamId)
            ]
        return sorted(
            rows,
            key=lambda x: (
                int(x.seasonId) if x.seasonId.isdigit() else 0,
                x.week,
                x.date,
                x.id,
            ),
        )


class InMemoryPlayerStatRepository:
    """Satisfies domain.repositories.PlayerStatRepository."""

    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def create_player_stat_line(
        self, stat: PlayerGameStatModel
    ) -> PlayerGameStatModel:
        self.store.player_stats[(stat.game_id, stat.player_id)] = stat
        return stat

    async def get_player_stat_line(
        self, game_id: str, player_id: str
    ) -> PlayerGameStatModel | None:
        return self.store.player_stats.get((game_id, player_id))

    async def delete_player_stat_line(
        self, game_id: str, player_id: str
    ) -> bool:
        return self.store.player_stats.pop((game_id, player_id), None) is not None

    async def list_player_stat_lines(
        self,
        game_id: str | None = None,
        player_id: str | None = None,
        team_id: str | None = None,
        opponent_id: str | None = None,
        season_id: str | None = None,
    ) -> list[PlayerGameStatModel]:
        rows = list(self.store.player_stats.values())
        if game_id is not None:
            rows = [r for r in rows if r.game_id == game_id]
        if player_id is not None:
            rows = [r for r in rows if r.player_id == player_id]
        if team_id is not None:
            rows = [r for r in rows if r.team_id == team_id]
        if opponent_id is not None:
            rows = [r for r in rows if r.opponent_id == opponent_id]
        if season_id is not None:
            # The season lives on the game, which is what the
            # player_game_stats_full view joins for in Postgres.
            allowed = {
                g.id for g in self.store.games.values()
                if g.seasonId == season_id
            }
            rows = [r for r in rows if r.game_id in allowed]
        return sorted(rows, key=lambda x: (x.game_id, x.player_id))

    async def player_totals(
        self,
        player_id: str,
        season_id: str | None = None,
        opponent_id: str | None = None,
    ) -> tuple[int, dict[str, int | Decimal]]:
        lines = await self.list_player_stat_lines(
            player_id=player_id, season_id=season_id, opponent_id=opponent_id
        )
        # Seed from a blank model so Decimal fields start as Decimal.
        blank = PlayerGameStatModel(
            game_id="", player_id="", team_id="", opponent_id="x", is_home=True
        )
        totals: dict[str, int | Decimal] = {
            f: getattr(blank, f) for f in STAT_FIELDS
        }
        for line in lines:
            for field in STAT_FIELDS:
                totals[field] += getattr(line, field)
        return len(lines), totals


class InMemoryTeamStatRepository:
    """Satisfies domain.repositories.TeamStatRepository."""

    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def create_team_stat_line(
        self, stat: TeamGameStatsModel
    ) -> TeamGameStatsModel:
        self.store.team_stats[(stat.game_id, stat.team_id)] = stat
        return stat

    async def get_team_stat_line(
        self, game_id: str, team_id: str
    ) -> TeamGameStatsModel | None:
        return self.store.team_stats.get((game_id, team_id))

    async def delete_team_stat_line(self, game_id: str, team_id: str) -> bool:
        return self.store.team_stats.pop((game_id, team_id), None) is not None

    async def list_team_stat_lines(
        self,
        game_id: str | None = None,
        team_id: str | None = None,
        opponent_id: str | None = None,
        season_id: str | None = None,
    ) -> list[TeamGameStatsModel]:
        rows = list(self.store.team_stats.values())
        if game_id is not None:
            rows = [r for r in rows if r.game_id == game_id]
        if team_id is not None:
            rows = [r for r in rows if r.team_id == team_id]
        if opponent_id is not None:
            rows = [r for r in rows if r.opponent_id == opponent_id]
        if season_id is not None:
            allowed = {
                g.id for g in self.store.games.values()
                if g.seasonId == season_id
            }
            rows = [r for r in rows if r.game_id in allowed]
        return sorted(rows, key=lambda x: (x.game_id, x.team_id))

    async def team_totals(
        self,
        team_id: str,
        season_id: str | None = None,
        opponent_id: str | None = None,
    ) -> tuple[int, dict[str, int]]:
        lines = await self.list_team_stat_lines(
            team_id=team_id, season_id=season_id, opponent_id=opponent_id
        )
        totals: dict[str, int] = {f: 0 for f in TEAM_STAT_FIELDS}
        for line in lines:
            for field in TEAM_STAT_FIELDS:
                totals[field] += getattr(line, field)
        return len(lines), totals


def build_repositories(store: InMemoryStore) -> dict[str, Any]:
    """All seven, sharing one store. Convenient for tests."""
    return {
        "leagues": InMemoryLeagueRepository(store),
        "seasons": InMemorySeasonRepository(store),
        "teams": InMemoryTeamRepository(store),
        "players": InMemoryPlayerRepository(store),
        "player_seasons": InMemoryPlayerSeasonRepository(store),
        "games": InMemoryGameRepository(store),
        "player_stats": InMemoryPlayerStatRepository(store),
        "team_stats": InMemoryTeamStatRepository(store),
    }