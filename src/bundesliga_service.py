"""Cached Bundesliga data service backed exclusively by OpenLigaDB."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from config import BUNDESLIGA_2026, CompetitionConfig
from src.domain import CompetitionState, Fixture, StandingRow, Team
from src.providers.openligadb import (
    OpenLigaDBClient,
    canonical_team_id,
    normalize_fixture,
    normalize_standing,
    normalize_team,
)

logger = logging.getLogger(__name__)

CACHE_ROOT = Path(__file__).parent.parent / "data" / "cache" / "openligadb"


class JsonCache:
    def __init__(self, root: Path = CACHE_ROOT):
        self.root = root

    def path(self, name: str) -> Path:
        return self.root / f"{name}.json"

    def load(self, name: str):
        path = self.path(name)
        if not path.exists():
            return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(envelope, dict) or "data" not in envelope:
                raise ValueError("missing cache envelope")
            return envelope
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("OpenLigaDB: ignoring invalid cache %s: %s", path, exc)
            return None

    def fresh(self, envelope: dict, ttl: timedelta, now: datetime) -> bool:
        try:
            fetched = datetime.fromisoformat(envelope["fetched_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            return False
        return now - fetched <= ttl

    def save(self, name: str, data) -> None:
        if not isinstance(data, (list, dict)) or not data:
            raise ValueError(f"refusing to cache empty/invalid OpenLigaDB {name} payload")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(name)
        temp = path.with_suffix(".tmp")
        envelope = {
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": data,
        }
        temp.write_text(json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, path)


class BundesligaDataService:
    def __init__(self, client: OpenLigaDBClient | None = None,
                 cache: JsonCache | None = None,
                 competition: CompetitionConfig = BUNDESLIGA_2026):
        self.client = client or OpenLigaDBClient()
        self.cache = cache or JsonCache()
        self.competition = competition

    def _cached_fetch(self, name: str, ttl: timedelta, fetch: Callable,
                      force: bool, now: datetime, validator: Callable | None = None):
        cached = self.cache.load(name)
        if cached and validator:
            try:
                validator(cached["data"])
            except (TypeError, ValueError) as exc:
                logger.warning("OpenLigaDB: ignoring structurally invalid %s cache: %s", name, exc)
                cached = None
        if cached and not force and self.cache.fresh(cached, ttl, now):
            logger.info("OpenLigaDB: using fresh %s cache", name)
            return cached["data"]
        try:
            data = fetch()
            if not isinstance(data, (list, dict)) or not data:
                raise ValueError(f"empty or malformed {name} response")
            if validator:
                validator(data)
            self.cache.save(name, data)
            return data
        except Exception as exc:
            if cached:
                logger.warning(
                    "OpenLigaDB unavailable for %s; using cache from %s (%s)",
                    name, cached.get("fetched_at", "unknown"), exc,
                )
                return cached["data"]
            raise

    def get_state(self, force: bool = False, now: datetime | None = None) -> CompetitionState:
        now = now or datetime.now(timezone.utc)
        league = self.competition.league_shortcut
        season = self.competition.season_start_year
        suffix = f"{league}_{season}"

        raw_teams = self._cached_fetch(
            f"teams_{suffix}", timedelta(days=7),
            lambda: self.client.get_teams(league, season), force, now,
            _validate_raw_teams,
        )
        raw_fixtures = self._cached_fetch(
            f"fixtures_{suffix}", timedelta(days=7),
            lambda: self.client.get_season_matches(league, season), force, now,
            _validate_raw_fixtures,
        )

        teams = self._normalize_teams(raw_teams, suffix)
        by_provider = {team.provider_id: team for team in teams}
        preliminary = tuple(
            normalize_fixture(row, self.competition, by_provider)
            for row in raw_fixtures
        )
        relevant_matchday = derive_current_matchday(preliminary, now)
        if not force:
            raw_fixtures = self._refresh_matchday_if_changed(
                raw_fixtures, relevant_matchday, suffix, now,
            )
        fixtures = tuple(
            normalize_fixture(row, self.competition, by_provider)
            for row in raw_fixtures
        )
        raw_standings = self._cached_fetch(
            f"standings_{suffix}", timedelta(minutes=15),
            lambda: self.client.get_standings(league, season), force, now,
            _validate_raw_standings,
        )
        standings = tuple(
            normalize_standing(row, position, by_provider)
            for position, row in enumerate(raw_standings, 1)
        )
        warnings = validate_league(teams, fixtures, standings)
        for warning in warnings:
            logger.warning("Bundesliga validation: %s", warning)
        return CompetitionState(
            teams=teams,
            fixtures=fixtures,
            standings=standings,
            current_matchday=derive_current_matchday(fixtures, now),
            updated_at=now,
        )

    def _normalize_teams(self, raw_teams: list[dict], suffix: str) -> tuple[Team, ...]:
        """Bootstrap and preserve provider-ID → canonical-ID mappings."""
        registry_name = f"team_registry_{suffix}"
        cached = self.cache.load(registry_name)
        registry = dict((cached or {}).get("data") or {})
        teams: list[Team] = []
        changed = False
        for row in raw_teams:
            provider_id = row.get("teamId")
            key = str(provider_id)
            canonical_id = registry.get(key)
            if canonical_id is None:
                canonical_id = canonical_team_id(row.get("teamName") or "")
                registry[key] = canonical_id
                changed = True
            teams.append(normalize_team(row, canonical_id=canonical_id))
        if changed or not cached:
            self.cache.save(registry_name, registry)
        return tuple(teams)

    def _refresh_matchday_if_changed(self, raw_fixtures: list[dict], matchday: int,
                                     suffix: str, now: datetime) -> list[dict]:
        """Use OpenLigaDB's lightweight change marker before fetching a matchday."""
        league = self.competition.league_shortcut
        season = self.competition.season_start_year
        marker_name = f"last_change_{suffix}_{matchday:02d}"
        marker = self.cache.load(marker_name)
        try:
            remote = self.client.get_last_change(league, season, matchday)
            if marker and marker.get("data", {}).get("value") == remote:
                logger.info("OpenLigaDB: matchday %d cache unchanged", matchday)
                return raw_fixtures
            changed = self.client.get_matchday(league, season, matchday)
            _validate_raw_fixtures(changed)
            changed_ids = {row.get("matchID") for row in changed}
            merged = [row for row in raw_fixtures if row.get("matchID") not in changed_ids]
            merged.extend(changed)
            merged.sort(key=lambda row: row.get("matchDateTimeUTC") or "")
            self.cache.save(f"fixtures_{suffix}", merged)
            self.cache.save(marker_name, {"value": remote})
            logger.info("OpenLigaDB: refreshed changed matchday %d", matchday)
            return merged
        except Exception as exc:
            logger.warning(
                "OpenLigaDB: matchday %d refresh failed; using season cache (%s)",
                matchday, exc,
            )
            return raw_fixtures

    def get_teams(self, force: bool = False) -> tuple[Team, ...]:
        return self.get_state(force=force).teams

    def get_fixtures(self, force: bool = False) -> tuple[Fixture, ...]:
        return self.get_state(force=force).fixtures

    def get_matchday(self, matchday: int, force: bool = False) -> tuple[Fixture, ...]:
        return tuple(f for f in self.get_fixtures(force=force) if f.matchday == matchday)

    def get_standings(self, force: bool = False) -> tuple[StandingRow, ...]:
        return self.get_state(force=force).standings


def derive_current_matchday(fixtures: tuple[Fixture, ...] | list[Fixture],
                            now: datetime) -> int:
    unfinished = [f for f in fixtures if not f.finished]
    if not unfinished:
        return max((f.matchday for f in fixtures), default=34)
    next_fixture = min(unfinished, key=lambda f: f.kickoff_utc)
    if now <= next_fixture.kickoff_utc:
        return next_fixture.matchday
    recent = [f for f in unfinished if f.kickoff_utc <= now]
    if recent:
        return max(recent, key=lambda f: f.kickoff_utc).matchday
    return next_fixture.matchday


def _validate_raw_teams(data) -> None:
    if not isinstance(data, list) or not data:
        raise ValueError("teams payload must be a non-empty list")
    if any(not isinstance(row.get("teamId"), int) or not row.get("teamName") for row in data):
        raise ValueError("team payload is missing teamId/teamName")


def _validate_raw_fixtures(data) -> None:
    if not isinstance(data, list) or not data:
        raise ValueError("fixture payload must be a non-empty list")
    required = lambda row: (
        isinstance(row.get("matchID"), int)
        and bool(row.get("matchDateTimeUTC"))
        and isinstance((row.get("group") or {}).get("groupOrderID"), int)
        and isinstance((row.get("team1") or {}).get("teamId"), int)
        and isinstance((row.get("team2") or {}).get("teamId"), int)
    )
    if any(not required(row) for row in data):
        raise ValueError("fixture payload is missing required identity/time fields")


def _validate_raw_standings(data) -> None:
    if not isinstance(data, list) or not data:
        raise ValueError("standings payload must be a non-empty list")
    if any(not isinstance(row.get("teamInfoId"), int) for row in data):
        raise ValueError("standings payload is missing teamInfoId")


def validate_league(teams: tuple[Team, ...], fixtures: tuple[Fixture, ...],
                    standings: tuple[StandingRow, ...]) -> list[str]:
    """Return prominent structural warnings without rejecting schedule changes."""
    warnings: list[str] = []
    if len(teams) != 18:
        warnings.append(f"expected 18 teams, received {len(teams)}")
    if len(fixtures) != 306:
        warnings.append(f"expected 306 fixtures, received {len(fixtures)}")
    matchdays = {f.matchday for f in fixtures}
    if matchdays != set(range(1, 35)):
        warnings.append(f"expected matchdays 1..34, received {sorted(matchdays)}")
    matchday_counts = {
        day: sum(1 for fixture in fixtures if fixture.matchday == day)
        for day in matchdays
    }
    irregular = {day: count for day, count in matchday_counts.items() if count != 9}
    if irregular:
        warnings.append(f"expected 9 fixtures per matchday, received {irregular}")
    ids = [f.id for f in fixtures]
    if len(ids) != len(set(ids)):
        warnings.append("fixture IDs are not unique")
    team_ids = {t.id for t in teams}
    for fixture in fixtures:
        if fixture.home_team_id == fixture.away_team_id:
            warnings.append(f"{fixture.id} has identical home and away team")
        if fixture.home_team_id not in team_ids or fixture.away_team_id not in team_ids:
            warnings.append(f"{fixture.id} references an unknown team")
        if fixture.kickoff_utc.tzinfo is None:
            warnings.append(f"{fixture.id} has a naive kickoff")
    if standings and len(standings) != len(teams):
        warnings.append(f"expected {len(teams)} standing rows, received {len(standings)}")
    return warnings


def recalculate_table(fixtures: tuple[Fixture, ...] | list[Fixture]) -> dict[str, dict]:
    """Diagnostic table calculation from completed fixtures only."""
    table: dict[str, dict] = {}
    for fixture in fixtures:
        if not fixture.finished or fixture.score.home is None or fixture.score.away is None:
            continue
        home = table.setdefault(fixture.home_team_id, _blank_table_row())
        away = table.setdefault(fixture.away_team_id, _blank_table_row())
        home["played"] += 1
        away["played"] += 1
        home["goals_for"] += fixture.score.home
        home["goals_against"] += fixture.score.away
        away["goals_for"] += fixture.score.away
        away["goals_against"] += fixture.score.home
        if fixture.score.home > fixture.score.away:
            home["won"] += 1; home["points"] += 3; away["lost"] += 1
        elif fixture.score.home < fixture.score.away:
            away["won"] += 1; away["points"] += 3; home["lost"] += 1
        else:
            home["drawn"] += 1; away["drawn"] += 1
            home["points"] += 1; away["points"] += 1
    for row in table.values():
        row["goal_difference"] = row["goals_for"] - row["goals_against"]
    return table


def _blank_table_row() -> dict:
    return {"played": 0, "won": 0, "drawn": 0, "lost": 0,
            "goals_for": 0, "goals_against": 0, "goal_difference": 0, "points": 0}
