"""Optional live schema/invariant diagnostic. Not part of unit tests."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bundesliga_service import BundesligaDataService, validate_league


def run() -> int:
    state = BundesligaDataService().get_state(force=True)
    warnings = validate_league(state.teams, state.fixtures, state.standings)
    logos = sum(bool(team.logo_url) for team in state.teams)
    sample = min(state.fixtures, key=lambda fixture: fixture.kickoff_utc)
    teams = {team.id: team for team in state.teams}
    print("Bundesliga 2026/27\n")
    print(f"Teams:      {len(state.teams)}")
    print(f"Fixtures:   {len(state.fixtures)}")
    print(f"Matchdays:  {len({fixture.matchday for fixture in state.fixtures})}")
    print(f"Standings:  {len(state.standings)} rows")
    print(f"Team logos: {logos}/{len(state.teams)} populated")
    print(f"Sample:     {teams[sample.home_team_id].name} – {teams[sample.away_team_id].name} "
          f"({sample.kickoff_utc.isoformat()})")
    if warnings:
        print("API:        SCHEMA OK, invariant warnings present")
        for warning in warnings:
            print(f"- {warning}")
        return 1
    print("API:        OK")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(run())
