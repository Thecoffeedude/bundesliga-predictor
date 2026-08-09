"""Bundesliga Predictor configuration and inactive generic utility defaults."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class CompetitionConfig:
    id: str
    name: str
    season_label: str
    season_start_year: int
    league_shortcut: str
    timezone: str
    format: str


BUNDESLIGA_2026 = CompetitionConfig(
    id="bundesliga",
    name="Bundesliga",
    season_label="2026/27",
    season_start_year=2026,
    league_shortcut="bl1",
    timezone="Europe/Berlin",
    format="league",
)

COMPETITION = BUNDESLIGA_2026


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Optional future/downstream systems are deliberately off in the baseline app.
KICKTIPP_ENABLED = _env_bool("KICKTIPP_ENABLED", False)
ODDS_ENABLED = _env_bool("ODDS_ENABLED", False)
EXTERNAL_PREDICTIONS_ENABLED = _env_bool("EXTERNAL_PREDICTIONS_ENABLED", False)

# Retained for the inactive provider-neutral probability normalization helper.
BOOKMAKER_WEIGHTS: dict[str, float] = {
    "pinnacle": 3.0,
    "betfair_ex_eu": 2.5,
    "betfair_ex_uk": 2.5,
    "sport888": 1.5,
    "unibet_eu": 1.2,
}
DEFAULT_BOOKMAKER_WEIGHT = 1.0

# Retained, inactive Kicktipp scoring/scoreline optimization utility.
KICKTIPP_POINTS = {
    "win":  {"tendency": 2, "goal_diff": 3, "exact": 4},
    "draw": {"tendency": 2, "exact": 4},  # keine goal_diff-Stufe bei Remis
}


def kicktipp_points(tip: tuple[int, int], real: tuple[int, int],
                    rules: dict = KICKTIPP_POINTS) -> int:
    """Return points for `(home, away)` tip and actual score tuples."""
    ta, tb = tip
    ra, rb = real
    tip_sign  = (ta > tb) - (ta < tb)
    real_sign = (ra > rb) - (ra < rb)
    if tip_sign != real_sign:
        return 0                      # falsche Tendenz
    if real_sign == 0:                # reales Remis
        return rules["draw"]["exact"] if (ta, tb) == (ra, rb) else rules["draw"]["tendency"]
    # realer Sieg, Tendenz stimmt
    if (ta, tb) == (ra, rb):
        return rules["win"]["exact"]
    if (ta - tb) == (ra - rb):
        return rules["win"]["goal_diff"]
    return rules["win"]["tendency"]

# Poisson matrix upper bound per team (scores 0..MAX_GOALS inclusive)
MAX_GOALS = 7
