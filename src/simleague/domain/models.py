"""Domain models.

Deliberately free of any FastAPI import. These describe the shape of the
data and nothing about how it is transported, which is what lets the seed
script, a future ETL flow, and the test suite use them without pulling in a
web framework.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel

PlayoffRound = Literal["wildcard", "divisional", "conference", "superbowl"]
Conference = Literal["AFC", "NFC"]


class LeagueModel(BaseModel):
    id: str
    name: str


class SeasonModel(BaseModel):
    id: str
    leagueId: str
    name: str


class TeamModel(BaseModel):
    id: str
    name: str
    conference: Conference | None = None
    division: str | None = None


class GameModel(BaseModel):
    id: str
    seasonId: str
    week: int
    homeTeamId: str
    awayTeamId: str
    homeScore: int
    awayScore: int
    date: datetime
    completed: bool = False

    # Playoff-only. Absent on the regular season records in the export.
    isPlayoff: bool = False
    round: PlayoffRound | None = None
    conference: Conference | None = None
    matchup: int | None = None
    homeTeamSeed: str | None = None
    awayTeamSeed: str | None = None

    @field_validator("date")
    @classmethod
    def to_utc(cls, value: datetime) -> datetime:
        """The export mixes naive and Z-suffixed timestamps. Force one shape
        so comparisons between two games never raise TypeError."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class PlayerModel(BaseModel):
    """A player's unchanging facts.

    Deliberately no teamId. A player does not have a team — he has a team
    in a season (see PlayerSeasonModel) and a team in a given game (the
    team_id on each stat line). Collapsing that into one field would make
    "his Colts years" unanswerable the first time he is traded.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    name: str
    position: str


class ResolvePlayerRequest(BaseModel):
    """Find a player by name, or create him, in one call.

    Entering a box score for a season with no players yet would otherwise
    mean three round trips and two ids for the form to track. This collapses
    it: type a name, get back a player who is on the right roster.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str
    season_id: str
    team_id: str
    position: str

    # Set when the caller has already disambiguated — either by picking one
    # of the candidates from a 409, or by deciding none of them is the right
    # man and a new record is wanted.
    player_id: str | None = None
    force_new: bool = False


class ResolvedPlayer(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    player: PlayerModel
    season: PlayerSeasonModel
    created: bool


class PlayerSeasonModel(BaseModel):
    """Roster membership: which team a player was on in a given season.

    Keyed on (player_id, season_id), matching the table. That means one
    team per player per season — a mid-season trade is not representable
    here, and does not need to be: each stat line carries its own team_id,
    which is what keeps game-level attribution correct regardless of what
    this row says.

    This is the table autocomplete queries. "Who was on Indianapolis in
    season 4" is a lookup here, not on players.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    player_id: str
    season_id: str
    team_id: str
    position: str | None = None
    jersey_number: int | None = None


class PlayerGameStatModel(BaseModel):
    """One row per player per game.

    The primary key is (game_id, player_id) — there is no id column. That
    composite key is what makes "one stat line per player per game" a
    database guarantee rather than something the application has to check.

    team_id is on the row rather than looked up from the player, because
    players change teams. This is what keeps historical totals correct after
    a trade.

    Every stat defaults to 0, so a player who only recorded a tackle sends
    two numbers and the other 66 fill themselves in.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    game_id: str
    player_id: str
    team_id: str
    opponent_id: str
    is_home: bool

    # passing
    pass_attempts: int = 0
    pass_completions: int = 0
    pass_yards: int = 0
    pass_touchdowns: int = 0
    interceptions: int = 0
    sacks_taken: int = 0
    pass_long: int = 0

    # rushing
    rush_attempts: int = 0
    rush_yards: int = 0
    rush_touchdowns: int = 0
    fumbles: int = 0
    fumbles_lost: int = 0
    broken_tackles: int = 0
    yards_after_first_hit: int = 0
    rushes_20_plus: int = 0
    rush_long: int = 0

    # receiving
    targets: int = 0
    receptions: int = 0
    receiving_yards: int = 0
    receiving_touchdowns: int = 0
    yards_after_catch: int = 0
    drops: int = 0
    reception_long: int = 0

    # blocking
    pancakes: int = 0
    sacks_allowed: int = 0

    # defense
    solo_tackles: int = 0
    assisted_tackles: int = 0
    tackles_for_loss: int = 0
    sacks: Decimal = Decimal("0.0")
    interceptions_made: int = 0
    interception_yards: int = 0
    interception_long: int = 0
    passes_defended: int = 0
    forced_fumbles: int = 0
    fumbles_recovered: int = 0
    fumble_return_yards: int = 0
    blocked_kicks: int = 0
    safeties: int = 0
    defensive_touchdowns: int = 0

    # kicking
    field_goals_made: int = 0
    field_goals_attempted: int = 0
    field_goal_long: int = 0
    field_goals_blocked: int = 0
    extra_points_made: int = 0
    extra_points_attempted: int = 0
    extra_points_blocked: int = 0
    fga_29: int = 0
    fgm_29: int = 0
    fga_39: int = 0
    fgm_39: int = 0
    fga_49: int = 0
    fgm_49: int = 0
    fga_50_plus: int = 0
    fgm_50_plus: int = 0
    kickoffs: int = 0
    touchbacks: int = 0

    # punting
    punts: int = 0
    punt_yards: int = 0
    punt_net_yards: int = 0
    punts_blocked: int = 0
    punts_inside_20: int = 0
    punt_touchbacks: int = 0
    punt_long: int = 0

    # returns
    kick_returns: int = 0
    kick_return_yards: int = 0
    kick_return_long: int = 0
    kick_return_touchdowns: int = 0
    punt_returns: int = 0
    punt_return_yards: int = 0
    punt_return_long: int = 0
    punt_return_touchdowns: int = 0


class TeamGameStatsModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    game_id: str
    team_id: str
    opponent_id: str
    is_home: bool
    points: int
    first_downs: int = 0
    third_down_att: int = 0
    third_down_conv: int = 0
    fourth_down_att: int = 0
    fourth_down_conv: int = 0
    total_yards: int = 0
    total_offense: int = 0
    pass_yards: int = 0
    pass_attempts: int = 0
    pass_completions: int = 0
    rush_yards: int = 0
    rush_attempts: int = 0
    kick_return_yards: int = 0
    punt_return_yards: int = 0
    sacks_allowed: int = 0
    sack_yards_lost: int = 0
    turnovers: int = 0
    interceptions_lost: int = 0
    fumbles_lost: int = 0
    penalties: int = 0
    penalty_yards: int = 0
    two_point_conversions_made: int = 0
    two_point_conversions_attempted: int = 0
    redzone_trips: int = 0
    redzone_touchdowns: int = 0
    redzone_field_goals: int = 0
    time_of_possession: int = 0


# Everything on a stat line that is a number to be summed. Defined by
# excluding the five identity fields rather than by filtering on type: a
# type filter silently drops sacks the moment it becomes Decimal.
STAT_IDENTITY_FIELDS = {
    "game_id", "player_id", "team_id", "opponent_id", "is_home",
}

STAT_FIELDS = [
    name
    for name in PlayerGameStatModel.model_fields
    if name not in STAT_IDENTITY_FIELDS
]

TEAM_STAT_IDENTITY_FIELDS = {"game_id", "team_id", "opponent_id", "is_home"}

TEAM_STAT_FIELDS = [
    name
    for name in TeamGameStatsModel.model_fields
    if name not in TEAM_STAT_IDENTITY_FIELDS
]