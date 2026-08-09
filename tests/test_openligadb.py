import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from config import BUNDESLIGA_2026
from src.build_bundesliga import build_payload, fixture_status
from src.bundesliga_service import BundesligaDataService, JsonCache
from src.domain import CompetitionState
from src.providers.openligadb import (
    OpenLigaDBClient,
    OpenLigaDBError,
    canonical_team_id,
    normalize_fixture,
    normalize_standing,
    normalize_team,
    parse_score,
)

FIXTURES = Path(__file__).parent / "fixtures" / "openligadb"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_team_normalization_retains_provider_identity_and_logo():
    raw = load("teams_2026.json")[0]
    team = normalize_team(raw)
    assert team.id == "fc-bayern-munchen"
    assert team.provider_id == 40
    assert team.name == "FC Bayern München"
    assert team.short_name == "Bayern"
    assert team.logo_url.endswith(".svg")


def test_team_normalization_handles_missing_optional_values():
    team = normalize_team({"teamId": 1, "teamName": "Test FC", "shortName": None, "teamIconUrl": ""})
    assert team.short_name is None
    assert team.logo_url is None
    assert canonical_team_id("1. FC Köln") == "1-fc-koln"


def test_fixture_normalization_keeps_match_id_utc_and_matchday():
    teams = [normalize_team(row) for row in load("teams_2026.json")]
    raw = load("fixture_scheduled_2026.json")
    fixture = normalize_fixture(raw, BUNDESLIGA_2026, {t.provider_id: t for t in teams})
    assert fixture.id == "openligadb:83156"
    assert fixture.provider_id == 83156
    assert fixture.matchday == 1
    assert fixture.kickoff_utc.isoformat() == "2026-08-28T18:30:00+00:00"
    assert fixture.score.home is None
    assert fixture.finished is False
    assert fixture.status == "UNKNOWN"
    assert fixture.status_derived is True
    assert fixture.stadium is None


def test_score_uses_semantic_full_time_result_not_first_element():
    score = parse_score(load("fixture_finished_2025.json"))
    assert (score.home, score.away) == (6, 0)


def test_completed_fixture_normalization_retains_final_score_and_status():
    raw = load("fixture_finished_2025.json")
    teams = [normalize_team(raw[side]) for side in ("team1", "team2")]
    fixture = normalize_fixture(raw, BUNDESLIGA_2026, {t.provider_id: t for t in teams})
    assert fixture.finished is True
    assert fixture.status == "FINISHED"
    assert fixture.status_derived is False
    assert (fixture.score.home, fixture.score.away) == (6, 0)


def test_standing_normalization_uses_response_order_as_position():
    teams = [normalize_team(row) for row in load("teams_2026.json")]
    by_provider = {t.provider_id: t for t in teams}
    row = normalize_standing(load("standings_2026.json")[1], 2, by_provider)
    assert row.position == 2
    assert row.team_id == "vfb-stuttgart"
    assert row.points == 0
    assert row.goal_difference == 0
    assert row.played == row.won == row.drawn == row.lost == 0
    assert row.goals_for == row.goals_against == 0


def test_fixture_rejects_unknown_team_reference():
    raw = load("fixture_scheduled_2026.json")
    with pytest.raises(ValueError, match="unknown team"):
        normalize_fixture(raw, BUNDESLIGA_2026, {})


def test_payload_contains_league_shape_and_no_fake_prediction():
    teams = tuple(normalize_team(row) for row in load("teams_2026.json"))
    by_provider = {t.provider_id: t for t in teams}
    fixture = normalize_fixture(load("fixture_scheduled_2026.json"), BUNDESLIGA_2026, by_provider)
    standings = tuple(
        normalize_standing(row, pos, by_provider)
        for pos, row in enumerate(load("standings_2026.json"), 1)
    )
    state = CompetitionState(
        teams=teams,
        fixtures=(fixture,),
        standings=standings,
        current_matchday=1,
        updated_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )
    payload = build_payload(state)
    match = payload["matchdays"][0]["matches"][0]
    assert payload["competition"]["id"] == "bundesliga"
    assert len(payload["matchdays"]) == 34
    assert match["id"] == "openligadb:83156"
    assert match["prediction"] is None
    assert match["odds"] is None
    assert match["status"] == "SCHEDULED"


def test_status_never_invents_a_live_minute():
    teams = [normalize_team(row) for row in load("teams_2026.json")]
    fixture = normalize_fixture(
        load("fixture_scheduled_2026.json"), BUNDESLIGA_2026,
        {t.provider_id: t for t in teams},
    )
    status, derived = fixture_status(fixture, datetime(2026, 8, 28, 19, 0, tzinfo=timezone.utc))
    assert status == "LIVE_OR_ONGOING"
    assert derived is True


def test_service_uses_last_valid_cache_when_provider_is_unavailable(tmp_path):
    class OfflineClient:
        def get_teams(self, *_): raise RuntimeError("offline")
        def get_season_matches(self, *_): raise RuntimeError("offline")
        def get_standings(self, *_): raise RuntimeError("offline")

    cache = JsonCache(tmp_path)
    cache.save("teams_bl1_2026", load("teams_2026.json"))
    cache.save("fixtures_bl1_2026", [load("fixture_scheduled_2026.json")])
    cache.save("standings_bl1_2026", load("standings_2026.json"))
    state = BundesligaDataService(client=OfflineClient(), cache=cache).get_state(force=True)
    assert len(state.teams) == 2
    assert len(state.fixtures) == 1
    assert len(state.standings) == 2


def test_http_timeout_is_wrapped_with_endpoint_context():
    class TimeoutSession:
        def get(self, *_args, **_kwargs):
            raise requests.Timeout("too slow")

    client = OpenLigaDBClient(session=TimeoutSession())
    with pytest.raises(OpenLigaDBError, match="getavailableteams/bl1/2026"):
        client.get_teams("bl1", 2026)


def test_invalid_json_is_rejected():
    class BadResponse:
        def raise_for_status(self): pass
        def json(self): raise ValueError("not json")
    class BadSession:
        def get(self, *_args, **_kwargs): return BadResponse()

    with pytest.raises(OpenLigaDBError, match="request failed"):
        OpenLigaDBClient(session=BadSession()).get_teams("bl1", 2026)


def test_invalid_remote_payload_never_replaces_valid_cache(tmp_path):
    class PartialClient:
        def get_teams(self, *_): return [{"unexpected": "partial"}]
        def get_season_matches(self, *_): raise AssertionError("not reached")
        def get_standings(self, *_): raise AssertionError("not reached")

    cache = JsonCache(tmp_path)
    original = load("teams_2026.json")
    cache.save("teams_bl1_2026", original)
    cache.save("fixtures_bl1_2026", [load("fixture_scheduled_2026.json")])
    cache.save("standings_bl1_2026", load("standings_2026.json"))
    state = BundesligaDataService(client=PartialClient(), cache=cache).get_state(force=True)
    assert len(state.teams) == 2
    assert cache.load("teams_bl1_2026")["data"] == original


def test_atomic_cache_write_leaves_no_temp_file(tmp_path):
    cache = JsonCache(tmp_path)
    cache.save("teams", load("teams_2026.json"))
    assert cache.path("teams").exists()
    assert not cache.path("teams").with_suffix(".tmp").exists()


def test_stale_cache_is_refreshed(tmp_path):
    cache = JsonCache(tmp_path)
    cache.save("item", {"version": 1})
    envelope = cache.load("item")
    envelope["fetched_at"] = "2000-01-01T00:00:00Z"
    cache.path("item").write_text(json.dumps(envelope), encoding="utf-8")
    calls = []
    service = BundesligaDataService(cache=cache)
    result = service._cached_fetch(
        "item", timedelta(minutes=1),
        lambda: calls.append(True) or {"version": 2},
        False, datetime.now(timezone.utc),
    )
    assert result == {"version": 2}
    assert calls == [True]


def test_empty_response_without_cache_is_rejected(tmp_path):
    service = BundesligaDataService(cache=JsonCache(tmp_path))
    with pytest.raises(ValueError, match="empty or malformed"):
        service._cached_fetch(
            "empty", timedelta(minutes=1), lambda: [], False,
            datetime.now(timezone.utc),
        )


def test_committed_deployment_payload_satisfies_full_season_invariants():
    payload_path = Path(__file__).parent.parent / "docs" / "data.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    matchdays = payload["matchdays"]
    matches = [match for day in matchdays for match in day["matches"]]

    assert payload["competition"]["id"] == "bundesliga"
    assert len(payload["teams"]) == 18
    assert len(payload["standings"]) == 18
    assert [day["number"] for day in matchdays] == list(range(1, 35))
    assert all(len(day["matches"]) == 9 for day in matchdays)
    assert len(matches) == 306
    assert len({match["providerId"] for match in matches}) == 306
    assert all(match["prediction"] is None and match["odds"] is None for match in matches)
