"""Repository ports.

Interfaces only — no SQL, no psycopg, no FastAPI. Each Protocol is a
checklist of what the application needs storage to do; the adapters in
simleague.adapters satisfy them.

Protocols are structural, so an adapter does NOT inherit from these. A
class with matching method names and signatures satisfies the protocol,
and mypy is what verifies it. That keeps the dependency arrow pointing
one way: adapters know about the domain, the domain knows nothing about
adapters.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from simleague.domain.models import (
    GameModel,
    LeagueModel,
    PlayerGameStatModel,
    PlayerModel,
    PlayerSeasonModel,
    SeasonModel,
    TeamGameStatsModel,
    TeamModel,
)


class LeagueRepository(Protocol):
    async def create_league(self, league: LeagueModel) -> LeagueModel: ...
    async def get_league(self, league_id: str) -> LeagueModel | None: ...
    async def list_leagues(self) -> list[LeagueModel]: ...


class SeasonRepository(Protocol):
    async def create_season(self, season: SeasonModel) -> SeasonModel: ...
    async def get_season(self, season_id: str) -> SeasonModel | None: ...
    async def list_seasons(
        self,
        league_id: str | None = None,
    ) -> list[SeasonModel]: ...


class TeamRepository(Protocol):
    async def create_team(self, team: TeamModel) -> TeamModel: ...
    async def get_team(self, team_id: str) -> TeamModel | None: ...
    async def list_teams(
        self,
        conference: str | None = None,
        division: str | None = None,
    ) -> list[TeamModel]: ...


class PlayerRepository(Protocol):
    async def create_player(self, player: PlayerModel) -> PlayerModel: ...
    async def get_player(self, player_id: str) -> PlayerModel | None: ...
    async def list_players(
        self,
        team_id: str | None = None,
        season_id: str | None = None,
        position: str | None = None,
    ) -> list[PlayerModel]: ...

    async def find_players_by_name(self, name: str) -> list[PlayerModel]: ...
    """Exact name match, case-insensitive. Returns a list because names are
    not unique — two players over nine seasons can share one, and silently
    picking the first would merge two careers."""


class PlayerSeasonRepository(Protocol):
    """Roster membership: which team a player was on in a given season.

    Keyed on (player_id, season_id), so one team per player per season. A
    mid-season trade is not representable here and does not need to be —
    each stat line carries its own team_id, which is what keeps game-level
    attribution correct.

    set_ rather than create_ because the operation is an upsert: assigning
    a player to a team for a season he already has a row for should move
    him, not fail.
    """

    async def set_player_season(
        self, entry: PlayerSeasonModel
    ) -> PlayerSeasonModel: ...

    async def get_player_season(
        self, player_id: str, season_id: str
    ) -> PlayerSeasonModel | None: ...

    async def delete_player_season(
        self, player_id: str, season_id: str
    ) -> bool: ...

    async def list_player_seasons(
        self,
        player_id: str | None = None,
        season_id: str | None = None,
        team_id: str | None = None,
    ) -> list[PlayerSeasonModel]: ...


class GameRepository(Protocol):
    async def create_game(self, game: GameModel) -> GameModel: ...
    async def get_game(self, game_id: str) -> GameModel | None: ...
    async def delete_game(self, game_id: str) -> bool: ...
    async def list_games(
        self,
        season_id: str | None = None,
        week: int | None = None,
        team_id: str | None = None,
        is_playoff: bool | None = None,
    ) -> list[GameModel]: ...


class PlayerStatRepository(Protocol):
    async def create_player_stat_line(
        self,
        stat: PlayerGameStatModel,
    ) -> PlayerGameStatModel: ...

    async def get_player_stat_line(
        self,
        game_id: str,
        player_id: str,
    ) -> PlayerGameStatModel | None: ...

    async def delete_player_stat_line(
        self,
        game_id: str,
        player_id: str,
    ) -> bool: ...

    async def list_player_stat_lines(
        self,
        game_id: str | None = None,
        player_id: str | None = None,
        team_id: str | None = None,
        opponent_id: str | None = None,
        season_id: str | None = None,
    ) -> list[PlayerGameStatModel]: ...

    async def player_totals(
        self,
        player_id: str,
        season_id: str | None = None,
        opponent_id: str | None = None,
    ) -> tuple[int, dict[str, int | Decimal]]: ...
    """Summed stat columns plus the number of games they cover.

    Exists as its own method so the adapter can answer it with a single
    SELECT SUM(...) GROUP BY instead of shipping every matching row to
    Python to be added up. Returns (games_played, totals).
    """


class TeamStatRepository(Protocol):
    async def create_team_stat_line(
        self,
        stat: TeamGameStatsModel,
    ) -> TeamGameStatsModel: ...

    async def get_team_stat_line(
        self,
        game_id: str,
        team_id: str,
    ) -> TeamGameStatsModel | None: ...

    async def delete_team_stat_line(
        self,
        game_id: str,
        team_id: str,
    ) -> bool: ...

    async def list_team_stat_lines(
        self,
        game_id: str | None = None,
        team_id: str | None = None,
        opponent_id: str | None = None,
        season_id: str | None = None,
    ) -> list[TeamGameStatsModel]: ...

    async def team_totals(
        self,
        team_id: str,
        season_id: str | None = None,
        opponent_id: str | None = None,
    ) -> tuple[int, dict[str, int]]: ...