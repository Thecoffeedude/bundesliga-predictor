"""Provider-neutral football domain objects used by the active application."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class Team:
    id: str
    provider_id: int
    name: str
    short_name: str | None
    logo_url: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Score:
    home: int | None
    away: int | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Fixture:
    id: str
    provider_id: int
    competition_id: str
    season: int
    matchday: int
    kickoff_utc: datetime
    home_team_id: str
    away_team_id: str
    score: Score
    finished: bool
    status: str
    status_derived: bool
    stadium: str | None
    city: str | None
    last_updated: datetime | None


@dataclass(frozen=True)
class StandingRow:
    position: int
    team_id: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MatchPrediction:
    """Interface reserved for the later, free statistical prediction phase."""

    home_win: float
    draw: float
    away_win: float
    expected_home_goals: float | None = None
    expected_away_goals: float | None = None
    score_probabilities: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if abs(self.home_win + self.draw + self.away_win - 1.0) >= 1e-6:
            raise ValueError("1X2 probabilities must sum to 1")


@dataclass(frozen=True)
class CompetitionState:
    teams: tuple[Team, ...]
    fixtures: tuple[Fixture, ...]
    standings: tuple[StandingRow, ...]
    current_matchday: int
    updated_at: datetime
