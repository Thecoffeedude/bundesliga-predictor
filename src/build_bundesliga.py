"""Build the active Bundesliga JSON payload without secrets or paid services."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import BUNDESLIGA_2026
from src.bundesliga_service import BundesligaDataService
from src.domain import CompetitionState, Fixture, Team

logger = logging.getLogger(__name__)
OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "data.json"


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fixture_status(fixture: Fixture, now: datetime) -> tuple[str, bool]:
    if fixture.finished:
        return "FINISHED", False
    if fixture.kickoff_utc > now:
        return "SCHEDULED", True
    if now - fixture.kickoff_utc <= timedelta(hours=4):
        return "LIVE_OR_ONGOING", True
    return "UNKNOWN", True


def build_payload(state: CompetitionState) -> dict:
    team_map: dict[str, Team] = {team.id: team for team in state.teams}

    def team_payload(team_id: str) -> dict:
        team = team_map[team_id]
        return {
            "id": team.id,
            "providerId": team.provider_id,
            "name": team.name,
            "shortName": team.short_name,
            "logo": team.logo_url,
        }

    matches_by_day: dict[int, list[dict]] = {day: [] for day in range(1, 35)}
    for fixture in sorted(state.fixtures, key=lambda f: f.kickoff_utc):
        status, derived = fixture_status(fixture, state.updated_at)
        matches_by_day.setdefault(fixture.matchday, []).append({
            "id": fixture.id,
            "providerId": fixture.provider_id,
            "matchday": fixture.matchday,
            "kickoff": _iso_utc(fixture.kickoff_utc),
            "status": status,
            "statusDerived": derived,
            "home": team_payload(fixture.home_team_id),
            "away": team_payload(fixture.away_team_id),
            "score": fixture.score.to_dict(),
            "venue": {"stadium": fixture.stadium, "city": fixture.city},
            "lastUpdated": _iso_utc(fixture.last_updated) if fixture.last_updated else None,
            "prediction": None,
            "odds": None,
        })

    return {
        "competition": {
            "id": BUNDESLIGA_2026.id,
            "name": BUNDESLIGA_2026.name,
            "season": BUNDESLIGA_2026.season_label,
            "seasonStartYear": BUNDESLIGA_2026.season_start_year,
            "leagueShortcut": BUNDESLIGA_2026.league_shortcut,
            "timezone": BUNDESLIGA_2026.timezone,
            "format": BUNDESLIGA_2026.format,
        },
        "updated_at": _iso_utc(state.updated_at),
        "current_matchday": state.current_matchday,
        "matchdays": [
            {"number": day, "matches": matches_by_day.get(day, [])}
            for day in range(1, 35)
        ],
        "standings": [row.to_dict() for row in state.standings],
        "teams": {team.id: team_payload(team.id) for team in state.teams},
        "features": {
            "predictions": False,
            "odds": False,
            "kicktipp": False,
        },
        "source": {
            "name": "OpenLigaDB",
            "url": "https://www.openligadb.de/",
            "license": "ODbL",
        },
    }


def build(force: bool = False, output_path: Path = OUTPUT_PATH) -> dict:
    state = BundesligaDataService().get_state(force=force)
    payload = build_payload(state)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(output_path)
    logger.info(
        "Bundesliga: wrote %s (%d teams, %d fixtures, %d matchdays)",
        output_path, len(state.teams), len(state.fixtures), len(payload["matchdays"]),
    )
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Build Bundesliga 2026/27 frontend data")
    parser.add_argument("--force", action="store_true", help="Ignore cache freshness and refresh OpenLigaDB")
    args = parser.parse_args()
    result = build(force=args.force)
    print(json.dumps({
        "competition": result["competition"],
        "teams": len(result["teams"]),
        "fixtures": sum(len(day["matches"]) for day in result["matchdays"]),
        "matchdays": len(result["matchdays"]),
        "standings": len(result["standings"]),
    }, indent=2, ensure_ascii=False))
