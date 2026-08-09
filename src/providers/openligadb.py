"""OpenLigaDB HTTP adapter and schema normalization.

Only this module understands OpenLigaDB field names.  The rest of the active
application consumes objects from :mod:`src.domain`.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

from config import CompetitionConfig
from src.domain import Fixture, Score, StandingRow, Team

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openligadb.de"
FULL_TIME_RESULT_TYPE_ID = 2


class OpenLigaDBError(RuntimeError):
    pass


class OpenLigaDBClient:
    def __init__(self, base_url: str = BASE_URL, timeout: float = 15.0,
                 session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def _get(self, path: str):
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OpenLigaDBError(f"OpenLigaDB request failed for {path}: {exc}") from exc
        if payload is None or not isinstance(payload, (list, dict, str)):
            raise OpenLigaDBError(f"OpenLigaDB returned an invalid payload for {path}")
        return payload

    def get_season_matches(self, league: str, season: int) -> list[dict]:
        data = self._get(f"getmatchdata/{league}/{season}")
        if not isinstance(data, list):
            raise OpenLigaDBError("season matches response is not a list")
        logger.info("OpenLigaDB: fetched %d fixtures for %s/%d", len(data), league, season)
        return data

    def get_matchday(self, league: str, season: int, matchday: int) -> list[dict]:
        data = self._get(f"getmatchdata/{league}/{season}/{matchday}")
        if not isinstance(data, list):
            raise OpenLigaDBError("matchday response is not a list")
        return data

    def get_teams(self, league: str, season: int) -> list[dict]:
        data = self._get(f"getavailableteams/{league}/{season}")
        if not isinstance(data, list):
            raise OpenLigaDBError("teams response is not a list")
        logger.info("OpenLigaDB: loaded %d teams for %s/%d", len(data), league, season)
        return data

    def get_groups(self, league: str, season: int) -> list[dict]:
        data = self._get(f"getavailablegroups/{league}/{season}")
        if not isinstance(data, list):
            raise OpenLigaDBError("groups response is not a list")
        return data

    def get_standings(self, league: str, season: int) -> list[dict]:
        data = self._get(f"getbltable/{league}/{season}")
        if not isinstance(data, list):
            raise OpenLigaDBError("standings response is not a list")
        return data

    def get_match(self, match_id: int) -> dict:
        data = self._get(f"getmatchdata/{match_id}")
        if not isinstance(data, dict):
            raise OpenLigaDBError("match response is not an object")
        return data

    def get_last_change(self, league: str, season: int, matchday: int) -> str:
        data = self._get(f"getlastchangedate/{league}/{season}/{matchday}")
        if not isinstance(data, str):
            raise OpenLigaDBError("last-change response is not a timestamp")
        return data


def canonical_team_id(name: str) -> str:
    """Generate the registry slug; persisted caches make it stable per season."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("ß", "ss")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not text:
        raise ValueError(f"cannot generate canonical team id from {name!r}")
    return text


def normalize_team(raw: dict, canonical_id: str | None = None) -> Team:
    provider_id = raw.get("teamId")
    name = (raw.get("teamName") or "").strip()
    if not isinstance(provider_id, int) or not name:
        raise ValueError("OpenLigaDB team is missing teamId/teamName")
    return Team(
        id=canonical_id or canonical_team_id(name),
        provider_id=provider_id,
        name=name,
        short_name=(raw.get("shortName") or None),
        logo_url=(raw.get("teamIconUrl") or None),
    )


def _parse_utc(value: str) -> datetime:
    if not value:
        raise ValueError("fixture has no UTC kickoff")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("fixture kickoff is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def _parse_provider_local(value: str | None, timezone_name: str) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.astimezone(timezone.utc)


def parse_score(raw: dict) -> Score:
    """Parse the semantic full-time result, never a positional list element."""
    results = raw.get("matchResults") or []
    full_time = next(
        (r for r in results if r.get("resultTypeID") == FULL_TIME_RESULT_TYPE_ID),
        None,
    )
    if full_time is None:
        full_time = next(
            (r for r in results
             if (r.get("resultName") or "").strip().lower() in {"endergebnis", "full time"}),
            None,
        )
    if full_time is not None:
        return Score(full_time.get("pointsTeam1"), full_time.get("pointsTeam2"))

    # During an ongoing match OpenLigaDB may expose goals but no FT result.
    goals = raw.get("goals") or []
    if goals:
        latest = max(goals, key=lambda g: (g.get("matchMinute") or 0, g.get("goalID") or 0))
        return Score(latest.get("scoreTeam1"), latest.get("scoreTeam2"))
    return Score(None, None)


def normalize_fixture(raw: dict, competition: CompetitionConfig,
                      teams_by_provider_id: dict[int, Team]) -> Fixture:
    provider_id = raw.get("matchID")
    home_provider_id = (raw.get("team1") or {}).get("teamId")
    away_provider_id = (raw.get("team2") or {}).get("teamId")
    group = raw.get("group") or {}
    matchday = group.get("groupOrderID")
    if not isinstance(provider_id, int) or not isinstance(matchday, int):
        raise ValueError("OpenLigaDB fixture is missing MatchID or matchday")
    try:
        home = teams_by_provider_id[home_provider_id]
        away = teams_by_provider_id[away_provider_id]
    except KeyError as exc:
        raise ValueError(f"fixture {provider_id} references an unknown team") from exc
    location = raw.get("location") or {}
    return Fixture(
        id=f"openligadb:{provider_id}",
        provider_id=provider_id,
        competition_id=competition.id,
        season=competition.season_start_year,
        matchday=matchday,
        kickoff_utc=_parse_utc(raw.get("matchDateTimeUTC") or ""),
        home_team_id=home.id,
        away_team_id=away.id,
        score=parse_score(raw),
        finished=bool(raw.get("matchIsFinished")),
        status="FINISHED" if raw.get("matchIsFinished") else "UNKNOWN",
        status_derived=not bool(raw.get("matchIsFinished")),
        stadium=location.get("locationStadium") or None,
        city=location.get("locationCity") or None,
        last_updated=_parse_provider_local(raw.get("lastUpdateDateTime"), competition.timezone),
    )


def normalize_standing(raw: dict, position: int,
                       teams_by_provider_id: dict[int, Team]) -> StandingRow:
    provider_id = raw.get("teamInfoId")
    try:
        team = teams_by_provider_id[provider_id]
    except KeyError as exc:
        raise ValueError(f"standing row references unknown team {provider_id!r}") from exc
    return StandingRow(
        position=position,
        team_id=team.id,
        played=int(raw.get("matches") or 0),
        won=int(raw.get("won") or 0),
        drawn=int(raw.get("draw") or 0),
        lost=int(raw.get("lost") or 0),
        goals_for=int(raw.get("goals") or 0),
        goals_against=int(raw.get("opponentGoals") or 0),
        goal_difference=int(raw.get("goalDiff") or 0),
        points=int(raw.get("points") or 0),
    )
