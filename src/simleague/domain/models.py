"""Domain models.

Deliberately free of any FastAPI import. These describe the shape of the
data and nothing about how it is transported, which is what lets the seed
script, a future ETL flow, and the test suite use them without pulling in a
web framework.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, field_validator

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
    id: str
    name: str
    position: str
    teamId: str | None = None


class PlayerGameStatModel(BaseModel):
    """One row per player per game. This is the join table that makes players
    work: a player is not owned by a game, he appears in many."""

    id: str
    gameId: str
    playerId: str
    teamId: str

    passAttempts: int = 0
    passCompletions: int = 0
    passYards: int = 0
    passTouchdowns: int = 0
    interceptions: int = 0

    rushAttempts: int = 0
    rushYards: int = 0
    rushTouchdowns: int = 0

    receptions: int = 0
    receivingYards: int = 0
    receivingTouchdowns: int = 0

    tackles: int = 0
    sacks: float = 0.0


STAT_FIELDS = [
    name
    for name, field in PlayerGameStatModel.model_fields.items()
    if field.annotation in (int, float)
]