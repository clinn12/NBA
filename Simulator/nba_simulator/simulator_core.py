"""Canonical NBA possession-by-possession simulation engine.

Front Matter
------------
Project: NBA Simulator
File type: Python module
Status: Active
Last updated: 2026-08-14

Purpose: own the production game state, NBA event resolution, substitutions,
box-score construction, and Monte Carlo APIs used by every project interface.
Usage: import this module from Python or the active notebook, or invoke it through
``scripts/run_simulation.py``. This module is authoritative; notebook cells do
not contain a second production implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple
import copy
import math
import random
from .season_simulation import (
    export_single_game_possession_log_csv,
    export_matchup_results_csv,
    export_season_results_csv,
    export_simulation_audit_csv,
    run_game_batch,
    run_season_simulations,
)
from .game_context import GameContext, PlayerGameOverride, SeasonState, normalize_game_context, prepare_game
from .historical_validation import validate_historical_game_distribution

# -------------------------------
# Robust simulator configuration
# -------------------------------
@dataclass(frozen=True)
class SimConfig:
    """Versionable simulation rules, calibration controls, and run-count defaults."""

    regulation_minutes: int = 48
    overtime_minutes: int = 5
    quarter_minutes: int = 12
    shot_clock_seconds: int = 24
    seed: Optional[int] = 7
    game_runs: int = 10
    season_runs: int = 10
    season_game_runs: int = 1
    average_possession_seconds: float = 13.50
    possession_time_sd: float = 4.25
    max_fouls: int = 6
    free_throw_rebound_live_probability: float = 0.14
    assist_probability_on_made_fg: float = 0.62
    shot_accuracy_adjustment: float = -0.020
    three_point_attempt_weight_multiplier: float = 0.75
    offensive_rebound_probability_multiplier: float = 1.40
    and_one_rate: float = 0.035
    shooting_foul_rate: float = 0.085
    non_shooting_foul_rate: float = 0.050
    steal_turnover_share: float = 0.53
    block_rate_on_miss: float = 0.075
    late_game_foul_seconds: int = 32
    late_game_foul_deficit_min: int = 3
    timeout_rate_per_possession: float = 0.028
    offensive_foul_rate: float = 0.014
    fatigue_stint_grace_minutes: float = 7.0
    fatigue_stint_penalty_per_minute: float = 0.045
    rotation_minimum_elapsed_minutes: float = 6.0
    rotation_minutes_buffer: float = 2.5
    max_rotation_substitutions_per_stoppage: int = 5
    minimum_bench_rest_seconds: int = 120
    performance_substitution_weight: float = 1.25
    performance_swap_threshold: float = 1.25
    minimum_minutes_for_performance_signal: float = 6.0
    max_team_disqualifications: int = 5
    team_disqualification_warning_threshold: int = 4
    timeout_recovery_seconds: int = 120
    period_break_recovery_seconds: int = 420
    team_foul_bonus_limit: int = 5
    final_two_minute_bonus_limit: int = 2
    switch_rate_base: float = 0.16
    help_defense_rate_base: float = 0.22
    fatigue_back_to_back_load: float = 0.0
    target_pace: float = 99.0
    target_offensive_rating: float = 114.0
    target_turnover_pct: float = 13.0
    target_free_throw_rate: float = 0.245
    target_offensive_rebound_pct: float = 27.0

BASIC_STAT_KEYS = (
    "MIN", "PTS", "FGM", "FGA", "3PM", "3PA", "FTM", "FTA", "ORB", "DRB", "TRB",
    "AST", "STL", "BLK", "TOV", "PF", "+/-", "POSS_ON", "POSS_USED",
    "PTS_2PT", "PTS_2PT_MR", "PTS_3PT", "PTS_FB", "PTS_FT", "PTS_OFF_TOV", "PTS_PAINT",
    "AST_2PM", "UAST_2PM", "AST_3PM", "UAST_3PM",
    "DEF_POSS", "DEF_PTS", "DEF_AST", "DEF_TOV", "DEF_FGM", "DEF_FGA", "DEF_3PM", "DEF_3PA", "SWITCHES_ON", "HELP_DEF",
    "SPACING_ON", "RIM_PRESSURE_ON", "LINEUP_DEF_ON",
    "MAX_FATIGUE", "MAX_STINT_MIN"
)

PLAY_TYPES = {
    "transition": {"weight": 0.12, "rim": 0.46, "mid": 0.12, "three": 0.42, "to_mult": 1.08, "foul_mult": 1.14},
    "pnr":        {"weight": 0.30, "rim": 0.34, "mid": 0.20, "three": 0.46, "to_mult": 1.00, "foul_mult": 1.00},
    "iso":        {"weight": 0.17, "rim": 0.31, "mid": 0.33, "three": 0.36, "to_mult": 0.95, "foul_mult": 1.12},
    "spotup":     {"weight": 0.24, "rim": 0.08, "mid": 0.08, "three": 0.84, "to_mult": 0.70, "foul_mult": 0.58},
    "post":       {"weight": 0.08, "rim": 0.42, "mid": 0.46, "three": 0.12, "to_mult": 1.03, "foul_mult": 1.18},
    "handoff":    {"weight": 0.09, "rim": 0.22, "mid": 0.16, "three": 0.62, "to_mult": 0.92, "foul_mult": 0.82},
}

SHOT_BASE_EFG = {"rim": 0.645, "mid": 0.425, "three": 0.365}


# Simplified event taxonomy requested by the project owner.
# The simulator records shots as 2PT, 3PT, or free throws, and treats all turnovers generically.
def _shot_label(zone: str) -> str:
    return "3PT Field Goal" if zone == "three" else "2PT Field Goal"

TURNOVER_LABEL = "Turnover"

@dataclass
class PlayerProfile:
    """Player tendencies, rotation state, fatigue state, and accumulated box stats."""

    name: str
    role: str = "wing"
    mpg: float = 28.0
    usage: float = 20.0
    two_pct: float = 0.525
    three_pct: float = 0.360
    ft_pct: float = 0.780
    three_rate: float = 0.38
    ftr: float = 0.245
    ast_rate: float = 0.16
    tov_rate: float = 0.115
    orb_rate: float = 0.045
    drb_rate: float = 0.135
    stl_rate: float = 0.016
    blk_rate: float = 0.018
    foul_rate: float = 0.045
    defense: float = 0.0       # positive is better, roughly -2.0 to +2.0
    stamina: float = 0.86      # higher stamina means slower fatigue accumulation
    clutch: float = 0.0        # late-game shot-making bump, roughly -1.0 to +1.0
    rim_pressure: float = 0.0  # positive attacks rim and bends defense
    off_ball_gravity: float = 0.0
    switchability: float = 0.0
    help_defense: float = 0.0
    stats: Dict[str, float] = field(default_factory=dict)
    fouls: int = 0
    disqualified: bool = False
    fatigue: float = 0.0
    consecutive_seconds: float = 0.0
    rest_eligible_after_elapsed_seconds: float = 0.0

    def reset_for_game(self) -> None:
        self.stats = {k: 0 for k in BASIC_STAT_KEYS}
        self.fouls = 0
        self.disqualified = False
        self.fatigue = 0.0
        self.consecutive_seconds = 0.0
        self.rest_eligible_after_elapsed_seconds = 0.0

@dataclass
class TeamState:
    """Mutable team roster, lineup, score, fouls, timeouts, and team statistics."""

    name: str
    roster: List[PlayerProfile]
    score: int = 0
    lineup: List[PlayerProfile] = field(default_factory=list)
    bench: List[PlayerProfile] = field(default_factory=list)
    team_stats: Dict[str, float] = field(default_factory=dict)

    def reset_for_game(self) -> None:
        for player in self.roster:
            player.reset_for_game()
        self.roster.sort(key=lambda p: (p.mpg, p.usage), reverse=True)
        self.lineup = self.roster[:5]
        self.bench = self.roster[5:]
        self.score = 0
        self.team_stats = {
            "PTS": 0, "POSS": 0, "FGM": 0, "FGA": 0, "3PM": 0, "3PA": 0, "FTM": 0, "FTA": 0,
            "ORB": 0, "DRB": 0, "TRB": 0, "AST": 0, "STL": 0, "BLK": 0, "TOV": 0, "PF": 0,
            "PLUS_MINUS": 0, "SECONDS": 0, "TIMEOUTS": 0, "OFF_TOV_FLAG": 0,
            "PTS_2PT": 0, "PTS_2PT_MR": 0, "PTS_3PT": 0, "PTS_FB": 0, "PTS_FT": 0, "PTS_OFF_TOV": 0, "PTS_PAINT": 0,
            "AST_2PM": 0, "UAST_2PM": 0, "AST_3PM": 0, "UAST_3PM": 0,
            "DEF_PTS": 0, "DEF_AST": 0, "DEF_TOV": 0, "DEF_FGM": 0, "DEF_FGA": 0, "DEF_3PM": 0, "DEF_3PA": 0,
            "TEAM_FOULS_PERIOD": 0, "BONUS_FTA": 0, "FASTBREAK_CHANCES": 0, "CLUTCH_POSSESSIONS": 0,
            "AVG_SPACING": 0, "AVG_RIM_PRESSURE": 0, "AVG_LINEUP_DEFENSE": 0, "CHEM_SAMPLES": 0,
        }

def create_nba_player(name: str, role: str = "wing", **overrides) -> PlayerProfile:
    """Create a plausible NBA player profile. Override any field with real player data as it becomes available."""
    archetypes = {
        "pg": dict(usage=23, three_rate=0.42, ast_rate=0.31, tov_rate=0.13, orb_rate=0.018, drb_rate=0.095, stl_rate=0.021, blk_rate=0.004, rim_pressure=0.55, off_ball_gravity=0.35, switchability=-0.10, help_defense=-0.15),
        "guard": dict(usage=21, three_rate=0.47, ast_rate=0.21, tov_rate=0.11, orb_rate=0.024, drb_rate=0.105, stl_rate=0.018, blk_rate=0.006, rim_pressure=0.25, off_ball_gravity=0.65, switchability=0.00, help_defense=-0.10),
        "wing": dict(usage=20, three_rate=0.43, ast_rate=0.15, tov_rate=0.10, orb_rate=0.038, drb_rate=0.135, stl_rate=0.016, blk_rate=0.013, rim_pressure=0.10, off_ball_gravity=0.55, switchability=0.55, help_defense=0.15),
        "forward": dict(usage=20, three_rate=0.32, ast_rate=0.13, tov_rate=0.11, orb_rate=0.060, drb_rate=0.170, stl_rate=0.014, blk_rate=0.025, rim_pressure=0.20, off_ball_gravity=0.20, switchability=0.65, help_defense=0.55),
        "big": dict(usage=19, three_rate=0.14, ast_rate=0.10, tov_rate=0.12, orb_rate=0.105, drb_rate=0.235, stl_rate=0.011, blk_rate=0.052, rim_pressure=0.75, off_ball_gravity=-0.10, switchability=0.15, help_defense=0.85),
    }
    data = dict(role=role, mpg=28, usage=20, two_pct=0.525, three_pct=0.360, ft_pct=0.780, ftr=0.245,
                defense=0.0, stamina=0.86, clutch=0.0, rim_pressure=0.0, off_ball_gravity=0.0,
                switchability=0.0, help_defense=0.0)
    data.update(archetypes.get(role, archetypes["wing"]))
    data.update(overrides)
    return PlayerProfile(name=name, **data)

def create_team(name: str, roster_specs: List[Tuple[str, str, Dict]]) -> TeamState:
    """Create a ``TeamState`` from ``(player name, role, overrides)`` entries."""

    return TeamState(name=name, roster=[create_nba_player(player_name, role, **attrs) for player_name, role, attrs in roster_specs])

def create_placeholder_team(name: str, seed: Optional[int] = None, rotation_size: int = 10) -> TeamState:
    """Generate placeholder inputs for possession probabilities until real player averages are wired in."""
    rng = random.Random(seed)
    roles = ["pg", "guard", "wing", "forward", "big", "guard", "wing", "forward", "big", "wing"]
    specs = []
    for idx in range(rotation_size):
        role = roles[idx % len(roles)]
        mpg = max(8, rng.gauss(30 if idx < 5 else 17, 4))
        usage = max(8, min(36, rng.gauss({"pg": 23, "guard": 21, "wing": 20, "forward": 19, "big": 18}[role], 4)))
        specs.append((f"{name} Player {idx + 1}", role, {
            "mpg": mpg, "usage": usage, "two_pct": max(0.42, min(0.68, rng.gauss(0.53, 0.045))),
            "three_pct": max(0.27, min(0.45, rng.gauss(0.36, 0.035))),
            "ft_pct": max(0.58, min(0.93, rng.gauss(0.78, 0.07))),
            "three_rate": max(0.05, min(0.75, rng.gauss(0.38, 0.15))),
            "ftr": max(0.08, min(0.55, rng.gauss(0.25, 0.09))),
            "ast_rate": max(0.03, min(0.42, rng.gauss(0.20 if role in {"pg", "guard"} else 0.12, 0.07))),
            "tov_rate": max(0.05, min(0.22, rng.gauss(0.115, 0.03))),
            "orb_rate": max(0.005, min(0.16, rng.gauss(0.025 if role in {"pg", "guard"} else 0.075, 0.025))),
            "drb_rate": max(0.04, min(0.30, rng.gauss(0.10 if role in {"pg", "guard"} else 0.18, 0.045))),
            "stl_rate": max(0.004, min(0.035, rng.gauss(0.016, 0.006))),
            "blk_rate": max(0.001, min(0.08, rng.gauss(0.008 if role in {"pg", "guard"} else 0.03, 0.018))),
            "foul_rate": max(0.015, min(0.08, rng.gauss(0.045, 0.012))),
            "defense": max(-2.0, min(2.0, rng.gauss(0.0, 0.65))),
            "stamina": max(0.70, min(0.98, rng.gauss(0.86, 0.06))),
            "clutch": max(-1.0, min(1.0, rng.gauss(0.0, 0.35))),
            "rim_pressure": max(-1.0, min(2.0, rng.gauss(0.5 if role in {"pg", "guard", "big"} else 0.0, 0.45))),
            "off_ball_gravity": max(-1.0, min(2.0, rng.gauss(0.6 if role in {"guard", "wing"} else 0.1, 0.45))),
            "switchability": max(-1.0, min(2.0, rng.gauss(0.4 if role in {"wing", "forward"} else 0.0, 0.50))),
            "help_defense": max(-1.0, min(2.0, rng.gauss(0.5 if role in {"forward", "big"} else 0.0, 0.50))),
        }))
    return create_team(name, specs)

def _weighted_choice(items, weights, rng: random.Random):
    total = sum(max(0, w) for w in weights)
    if total <= 0:
        return rng.choice(list(items))
    point = rng.random() * total
    running = 0.0
    for item, weight in zip(items, weights):
        running += max(0, weight)
        if running >= point:
            return item
    return list(items)[-1]

def _lineup_strength(players: List[PlayerProfile], attr: str) -> float:
    return sum(getattr(p, attr) for p in players) / max(1, len(players))

def _score_state(team_a: TeamState, team_b: TeamState) -> Dict[str, int]:
    return {team_a.name: team_a.score, team_b.name: team_b.score}

def _lineup_spacing(team: TeamState) -> float:
    if not team.lineup:
        return 0.0
    shooting = sum((p.three_rate * max(0.0, p.three_pct - 0.30) + p.off_ball_gravity * 0.08) for p in team.lineup)
    return max(-1.5, min(2.5, shooting / len(team.lineup) * 8))

def _lineup_rim_pressure(team: TeamState) -> float:
    if not team.lineup:
        return 0.0
    return max(-1.5, min(2.5, sum(p.rim_pressure for p in team.lineup) / len(team.lineup)))

def _lineup_defense(team: TeamState) -> float:
    if not team.lineup:
        return 0.0
    return max(-2.5, min(2.5, sum(p.defense + 0.35 * p.switchability + 0.25 * p.help_defense for p in team.lineup) / len(team.lineup)))

def _sample_lineup_chemistry(team: TeamState) -> Dict[str, float]:
    spacing = _lineup_spacing(team)
    rim_pressure = _lineup_rim_pressure(team)
    lineup_def = _lineup_defense(team)
    team.team_stats["AVG_SPACING"] += spacing
    team.team_stats["AVG_RIM_PRESSURE"] += rim_pressure
    team.team_stats["AVG_LINEUP_DEFENSE"] += lineup_def
    team.team_stats["CHEM_SAMPLES"] += 1
    for p in team.lineup:
        p.stats["SPACING_ON"] += spacing
        p.stats["RIM_PRESSURE_ON"] += rim_pressure
        p.stats["LINEUP_DEF_ON"] += lineup_def
    return {"spacing": spacing, "rim_pressure": rim_pressure, "lineup_defense": lineup_def}

def _is_bonus(team: TeamState, clock: int, config: SimConfig) -> bool:
    if team.team_stats.get("TEAM_FOULS_PERIOD", 0) >= config.team_foul_bonus_limit:
        return True
    return clock <= 120 and team.team_stats.get("TEAM_FOULS_PERIOD", 0) >= config.final_two_minute_bonus_limit

def _choose_shooter(offense: TeamState, config: SimConfig, rng: random.Random) -> PlayerProfile:
    weights = [max(1.0, p.usage) * max(0.50, 1.0 - _total_fatigue(p, config) * 0.22) for p in offense.lineup]
    return _weighted_choice(offense.lineup, weights, rng)

def _choose_rebounder(team: TeamState, offensive: bool, config: SimConfig, rng: random.Random) -> PlayerProfile:
    attr = "orb_rate" if offensive else "drb_rate"
    weights = [max(0.005, getattr(p, attr)) * max(0.55, 1.0 - _total_fatigue(p, config) * 0.14) for p in team.lineup]
    return _weighted_choice(team.lineup, weights, rng)

def _choose_primary_defender(defense: TeamState, config: SimConfig, rng: random.Random) -> PlayerProfile:
    weights = [max(0.05, 1.0 + p.defense * 0.25 - _total_fatigue(p, config) * 0.08) for p in defense.lineup]
    return _weighted_choice(defense.lineup, weights, rng)

def _maybe_help_defender(defense: TeamState, primary: PlayerProfile, zone: str, config: SimConfig, rng: random.Random) -> Optional[PlayerProfile]:
    candidates = [p for p in defense.lineup if p is not primary]
    if not candidates:
        return None
    help_rate = config.help_defense_rate_base + max(0, _lineup_defense(defense)) * 0.025
    if zone == "rim":
        help_rate += 0.10
    if rng.random() >= min(0.62, max(0.02, help_rate)):
        return None
    helper = _weighted_choice(candidates, [max(0.01, p.help_defense + p.defense * 0.4 + 1.0) for p in candidates], rng)
    helper.stats["HELP_DEF"] += 1
    return helper

def _choose_play_type(offense: TeamState, defense: TeamState, seconds_left: int, period: int, config: SimConfig, rng: random.Random) -> str:
    weights = {play: meta["weight"] for play, meta in PLAY_TYPES.items()}
    margin = offense.score - defense.score
    minutes_left = seconds_left / 60
    spacing = _lineup_spacing(offense)
    rim_pressure = _lineup_rim_pressure(offense)
    defense_strength = _lineup_defense(defense)
    if seconds_left <= 7:
        weights["iso"] *= 1.45
        weights["pnr"] *= 1.15
        weights["transition"] *= 0.25
    late_game = period >= 4
    if late_game and margin < -8 and minutes_left < 6:
        weights["spotup"] *= 1.30 + max(0, spacing) * 0.06
        weights["transition"] *= 1.20
        weights["post"] *= 0.70
    elif late_game and margin > 10 and minutes_left < 5:
        weights["transition"] *= 0.72
        weights["post"] *= 1.12
        weights["pnr"] *= 1.10
    if rim_pressure > 0.4:
        weights["pnr"] *= 1.0 + rim_pressure * 0.08
        weights["transition"] *= 1.0 + rim_pressure * 0.04
    if spacing > 0.4:
        weights["spotup"] *= 1.0 + spacing * 0.07
        weights["handoff"] *= 1.0 + spacing * 0.04
    if defense_strength > 0.8:
        weights["iso"] *= 0.90
        weights["pnr"] *= 1.08
    if 28 <= seconds_left <= 40:
        weights["transition"] *= 1.22
        weights["pnr"] *= 1.12
    return _weighted_choice(list(weights), list(weights.values()), rng)

def _choose_shot_zone(play_type: str, shooter: PlayerProfile, offense: TeamState, defense: TeamState, config: SimConfig, rng: random.Random) -> str:
    meta = PLAY_TYPES[play_type]
    three_bias = max(0.05, min(0.85, shooter.three_rate))
    spacing = _lineup_spacing(offense)
    rim_pressure = _lineup_rim_pressure(offense)
    defense_strength = _lineup_defense(defense)
    weights = {
        "rim": meta["rim"] * (1.20 - three_bias * 0.35) * (1.0 + rim_pressure * 0.06 - defense_strength * 0.03),
        "mid": meta["mid"] * (1.0 - max(0, spacing) * 0.04),
        "three": meta["three"] * (0.55 + three_bias) * (1.0 + spacing * 0.08) * config.three_point_attempt_weight_multiplier,
    }
    return _weighted_choice(list(weights), list(weights.values()), rng)

def _choose_shot_type(zone: str, play_type: str, rng: random.Random, putback: bool = False) -> str:
    return _shot_label(zone)

def _choose_turnover_type(rng: random.Random) -> str:
    return TURNOVER_LABEL

def _stint_fatigue(player: PlayerProfile, config: SimConfig) -> float:
    extra_minutes = max(0.0, player.consecutive_seconds / 60 - config.fatigue_stint_grace_minutes)
    return extra_minutes * config.fatigue_stint_penalty_per_minute

def _total_fatigue(player: PlayerProfile, config: SimConfig) -> float:
    return player.fatigue + _stint_fatigue(player, config)

def _shot_probability(shooter: PlayerProfile, primary_defender: PlayerProfile, help_defender: Optional[PlayerProfile],
                      lineup_context: Dict[str, float], zone: str, clutch_time: bool, config: SimConfig) -> float:
    if zone == "three":
        base = shooter.three_pct
    elif zone == "rim":
        base = min(0.74, shooter.two_pct + 0.105)
    else:
        base = max(0.34, shooter.two_pct - 0.095)
    fatigue_penalty = _total_fatigue(shooter, config) * 0.020
    primary_defense = primary_defender.defense + 0.25 * primary_defender.switchability
    help_defense = (help_defender.help_defense + 0.35 * help_defender.defense) if help_defender else 0.0
    defense_penalty = primary_defense * 0.013 + help_defense * (0.010 if zone == "rim" else 0.004)
    spacing_bonus = lineup_context["spacing"] * (0.006 if zone == "three" else 0.003)
    rim_bonus = lineup_context["rim_pressure"] * (0.007 if zone == "rim" else 0.001)
    clutch_bonus = shooter.clutch * 0.010 if clutch_time else 0.0
    return max(0.18, min(0.82, base + config.shot_accuracy_adjustment - fatigue_penalty - defense_penalty + spacing_bonus + rim_bonus + clutch_bonus))

def _commit_foul(team: TeamState, rng: random.Random) -> PlayerProfile:
    eligible = [p for p in team.lineup if not p.disqualified]
    if not eligible:
        eligible = team.lineup or team.roster
    weights = [max(0.01, p.foul_rate) * (1.0 + max(0, p.fouls - 3) * 0.08) for p in eligible]
    return _weighted_choice(eligible, weights, rng)

def _substitute(team: TeamState, elapsed_seconds: int, config: SimConfig, log: Optional[List[Dict]] = None, clock: Optional[int] = None, period: Optional[int] = None, opponent_score: Optional[int] = None, reason: str = "rotation") -> None:
    """Make a frozen-snapshot rotation decision at one dead-ball stoppage."""
    lineup_before = list(team.lineup)
    bench_before = list(team.bench)
    if not bench_before:
        return
    game_minutes_elapsed = elapsed_seconds / 60
    late_period_window = bool(period and clock is not None and (period in {2, 4} or period > 4) and clock <= 5 * 60)
    score_margin = team.score - opponent_score if opponent_score is not None else 0
    close_game = bool(period and period >= 4 and clock is not None and clock <= 5 * 60 and abs(score_margin) <= 10)
    blowout = bool(period and period >= 4 and clock is not None and clock <= 8 * 60 and abs(score_margin) >= 20)
    candidates = [player for player in bench_before if not player.disqualified and
                  (late_period_window or elapsed_seconds >= player.rest_eligible_after_elapsed_seconds)]
    if not candidates and any(player.disqualified for player in lineup_before):
        # A disqualified player must be replaced even if every available bench player is mid-rest.
        candidates = [player for player in bench_before if not player.disqualified]
    if not candidates:
        return
    def performance_index(player: PlayerProfile) -> float:
        """Small-sample in-game impact signal; deliberately bounded for rotation use."""
        minutes = player.stats["MIN"]
        if minutes < config.minimum_minutes_for_performance_signal:
            return 0.0
        misses = player.stats["FGA"] - player.stats["FGM"]
        missed_fts = player.stats["FTA"] - player.stats["FTM"]
        impact = (player.stats["PTS"] + 0.8 * player.stats["TRB"] + 1.2 * player.stats["AST"] +
                  1.5 * (player.stats["STL"] + player.stats["BLK"]) - 0.9 * misses -
                  0.45 * missed_fts - 1.3 * player.stats["TOV"] - 0.35 * player.stats["PF"])
        return max(-3.0, min(3.0, impact / minutes))

    best_bench_form = max((performance_index(player) for player in candidates), default=0.0)
    decisions = []
    for player in lineup_before:
        expected_minutes = game_minutes_elapsed * min(1.0, player.mpg / config.regulation_minutes)
        minutes_over_target = player.stats["MIN"] - expected_minutes
        foul_trouble = player.fouls >= 5 or (player.fouls >= 3 and elapsed_seconds < 24 * 60)
        tired = _total_fatigue(player, config) > 1.25
        rotation_due = (game_minutes_elapsed >= config.rotation_minimum_elapsed_minutes and
                        minutes_over_target >= config.rotation_minutes_buffer)
        performance_swap = (player.stats["MIN"] >= config.minimum_minutes_for_performance_signal and
                            best_bench_form - performance_index(player) >= config.performance_swap_threshold)
        expected_starters = set(getattr(team, "expected_starters", []))
        closing_due = close_game and player.name not in expected_starters and any(candidate.name in expected_starters for candidate in candidates)
        blowout_due = blowout and player.name in expected_starters and any(candidate.name not in expected_starters for candidate in candidates)
        if player.disqualified:
            decisions.append((4, minutes_over_target, player, "disqualified"))
        elif foul_trouble:
            decisions.append((3, minutes_over_target, player, "foul_trouble"))
        elif tired:
            decisions.append((2, minutes_over_target, player, "fatigue"))
        elif blowout_due:
            decisions.append((2.6, player.mpg, player, "blowout"))
        elif closing_due:
            decisions.append((2.5, player.mpg, player, "closing_lineup"))
        elif performance_swap:
            decisions.append((1.5, best_bench_form - performance_index(player), player, "performance"))
        elif rotation_due:
            decisions.append((1, minutes_over_target, player, reason))
    if not decisions:
        return
    decisions.sort(key=lambda item: (item[0], item[1], item[2].mpg), reverse=True)
    max_changes = max(1, config.max_rotation_substitutions_per_stoppage)
    selected_out = decisions[:max_changes]
    selected_in = []
    available = list(candidates)
    for _, _, _, _ in selected_out:
        replacement = max(available, key=lambda bench_player: (
            (2.0 if close_game and bench_player.name in getattr(team, "expected_starters", []) else 0.0) +
            (1.5 if blowout and bench_player.name not in getattr(team, "expected_starters", []) else 0.0) +
            game_minutes_elapsed * min(1.0, bench_player.mpg / config.regulation_minutes) - bench_player.stats["MIN"] +
            config.performance_substitution_weight * performance_index(bench_player),
            (-bench_player.mpg if blowout else bench_player.mpg), -_total_fatigue(bench_player, config), bench_player.usage))
        selected_in.append(replacement)
        available.remove(replacement)
        if not available:
            break
    selected_out = selected_out[:len(selected_in)]
    outgoing = [decision[2] for decision in selected_out]
    team.lineup = [player for player in lineup_before if all(player is not outgoing_player for outgoing_player in outgoing)] + selected_in
    team.bench = [player for player in bench_before if all(player is not incoming_player for incoming_player in selected_in)] + outgoing
    for player in outgoing:
        player.consecutive_seconds = 0.0
        player.rest_eligible_after_elapsed_seconds = elapsed_seconds if late_period_window else elapsed_seconds + config.minimum_bench_rest_seconds
    for player in selected_in:
        player.consecutive_seconds = 0.0
    if log is not None:
        for (_, _, player_out, substitution_reason), player_in in zip(selected_out, selected_in):
            log.append({"clock": clock, "period": period, "team": team.name, "event": "substitution", "espn_type": "Substitution",
                        "player_in": player_in.name, "player_out": player_out.name, "reason": substitution_reason})

def _replace_disqualified_players(team: TeamState, elapsed_seconds: int, config: SimConfig, log: List[Dict], clock: int, period: Optional[int]) -> None:
    """Immediately replace every disqualified active player before play resumes."""
    outgoing = [player for player in team.lineup if player.disqualified]
    if not outgoing:
        return
    available = [player for player in team.bench if not player.disqualified]
    if not available:
        return
    game_minutes_elapsed = elapsed_seconds / 60
    incoming = []
    for _ in outgoing:
        if not available:
            break
        replacement = max(available, key=lambda player: (
            game_minutes_elapsed * min(1.0, player.mpg / config.regulation_minutes) - player.stats["MIN"],
            player.mpg, -_total_fatigue(player, config), player.usage))
        incoming.append(replacement)
        available.remove(replacement)
    outgoing = outgoing[:len(incoming)]
    if not outgoing:
        return
    lineup_before = list(team.lineup)
    bench_before = list(team.bench)
    team.lineup = [player for player in lineup_before if all(player is not player_out for player_out in outgoing)] + incoming
    team.bench = [player for player in bench_before if all(player is not player_in for player_in in incoming)] + outgoing
    for player in outgoing + incoming:
        player.consecutive_seconds = 0.0
    for player_out, player_in in zip(outgoing, incoming):
        log.append({"clock": clock, "period": period, "team": team.name, "event": "substitution", "espn_type": "Substitution",
                    "player_in": player_in.name, "player_out": player_out.name, "reason": "disqualification"})

def _apply_disqualification(player: PlayerProfile, team: TeamState, config: SimConfig, log: List[Dict], clock: int, period: Optional[int]) -> None:
    """Apply a foul-out with team-level calibration safeguards."""
    if player.fouls < config.max_fouls or player.disqualified:
        return
    current_count = sum(roster_player.disqualified for roster_player in team.roster)
    if current_count >= config.max_team_disqualifications:
        raise RuntimeError(f"Calibration error: {team.name} would exceed {config.max_team_disqualifications} disqualified players.")
    player.disqualified = True
    new_count = current_count + 1
    if new_count >= config.team_disqualification_warning_threshold:
        log.append({"clock": clock, "period": period, "team": team.name, "event": "calibration_warning",
                    "warning": "team_disqualification_threshold", "disqualified_players": new_count,
                    "threshold": config.team_disqualification_warning_threshold})

def _award_free_throws(offense: TeamState, defense: TeamState, shooter: PlayerProfile, attempts: int, rng: random.Random, log: List[Dict], clock: int, espn_type: Optional[str] = None) -> Dict[str, float]:
    made = 0
    final_missed = False
    for attempt in range(1, attempts + 1):
        is_make = rng.random() < shooter.ft_pct
        shooter.stats["FTA"] += 1
        offense.team_stats["FTA"] += 1
        if is_make:
            made += 1
            shooter.stats["FTM"] += 1
            shooter.stats["PTS"] += 1
            shooter.stats["PTS_FT"] += 1
            offense.team_stats["FTM"] += 1
            offense.team_stats["PTS_FT"] += 1
            offense.score += 1
            offense.team_stats["PTS"] += 1
            _record_plus_minus(offense, defense, 1)
        elif attempt == attempts:
            final_missed = True
        ft_type = espn_type or "Free Throw"
        log.append({"clock": clock, "team": offense.name, "event": "free_throw", "espn_type": ft_type, "player": shooter.name,
                    "attempt": attempt, "attempts": attempts, "made": is_make, "score": _score_state(offense, defense)})
    return {"made": made, "attempts": attempts, "final_missed": final_missed}

def _resolve_final_free_throw_miss(offense: TeamState, defense: TeamState, shooter: PlayerProfile, config: SimConfig, rng: random.Random, log: List[Dict], clock: int) -> Tuple[TeamState, TeamState, bool]:
    """Resolve the live rebound that only exists after a missed final free throw."""
    if rng.random() < config.free_throw_rebound_live_probability:
        rebounder = _choose_rebounder(offense, True, config, rng)
        rebounder.stats["ORB"] += 1
        rebounder.stats["TRB"] += 1
        offense.team_stats["ORB"] += 1
        offense.team_stats["TRB"] += 1
        log.append({"clock": clock, "team": offense.name, "event": "offensive_rebound", "espn_type": "Offensive Rebound",
                    "player": rebounder.name, "after_shot_by": shooter.name, "source": "free_throw",
                    "score": _score_state(offense, defense)})
        return offense, defense, False

    rebounder = _choose_rebounder(defense, False, config, rng)
    rebounder.stats["DRB"] += 1
    rebounder.stats["TRB"] += 1
    defense.team_stats["DRB"] += 1
    defense.team_stats["TRB"] += 1
    log.append({"clock": clock, "team": defense.name, "event": "defensive_rebound", "espn_type": "Defensive Rebound",
                "player": rebounder.name, "after_shot_by": shooter.name, "source": "free_throw",
                "score": _score_state(offense, defense)})
    _finish_possession(offense, defense)
    return defense, offense, True

def _record_lineup_seconds(team: TeamState, seconds: float, config: SimConfig) -> None:
    team.team_stats["SECONDS"] += seconds
    for player in team.lineup:
        player.stats["MIN"] += seconds / 60
        player.consecutive_seconds += seconds
        base_load = seconds / 60 * (1.0 - player.stamina) * 0.18
        stint_load = max(0.0, player.consecutive_seconds / 60 - config.fatigue_stint_grace_minutes) * 0.0025
        player.fatigue = max(0.0, player.fatigue + base_load + stint_load)
        player.stats["MAX_FATIGUE"] = max(player.stats.get("MAX_FATIGUE", 0), _total_fatigue(player, config))
        player.stats["MAX_STINT_MIN"] = max(player.stats.get("MAX_STINT_MIN", 0), player.consecutive_seconds / 60)
    for player in team.bench:
        player.consecutive_seconds = 0.0
        player.fatigue = max(0.0, player.fatigue - seconds / 60 * 0.09)

def _rest_lineup(team: TeamState, recovery_seconds: float) -> None:
    for player in team.lineup:
        player.consecutive_seconds = max(0.0, player.consecutive_seconds - recovery_seconds)
        player.fatigue = max(0.0, player.fatigue - recovery_seconds / 60 * 0.08)
    for player in team.bench:
        player.consecutive_seconds = 0.0
        player.fatigue = max(0.0, player.fatigue - recovery_seconds / 60 * 0.10)

def _record_plus_minus(scoring_team: TeamState, defending_team: TeamState, points: int) -> None:
    for player in scoring_team.lineup:
        player.stats["+/-"] += points
    for player in defending_team.lineup:
        player.stats["+/-"] -= points
    scoring_team.team_stats["PLUS_MINUS"] += points
    defending_team.team_stats["PLUS_MINUS"] -= points

def _finish_possession(offense: TeamState, defense: TeamState) -> None:
    offense.team_stats["POSS"] += 1
    offense.team_stats["OFF_TOV_FLAG"] = 0
    for player in offense.lineup:
        player.stats["POSS_ON"] += 1
    for player in defense.lineup:
        player.stats["POSS_ON"] += 1

def _maybe_dead_ball_event(offense: TeamState, defense: TeamState, clock: int, period: int, config: SimConfig, rng: random.Random, log: List[Dict]) -> Tuple[TeamState, TeamState, bool]:
    """Generate retained dead-ball events: timeouts only. Timeouts relieve consecutive-minute fatigue."""
    if rng.random() < config.timeout_rate_per_possession:
        caller = offense if rng.random() < 0.58 else defense
        caller.team_stats["TIMEOUTS"] += 1
        _rest_lineup(offense, config.timeout_recovery_seconds)
        _rest_lineup(defense, config.timeout_recovery_seconds)
        log.append({"clock": clock, "period": period, "team": caller.name, "event": "timeout", "espn_type": "Full Timeout",
                    "score": _score_state(offense, defense)})
    return offense, defense, False

def simulate_possession_robust(offense: TeamState, defense: TeamState, clock: int, elapsed: int, config: SimConfig, rng: random.Random, log: List[Dict], period: Optional[int] = None) -> Tuple[TeamState, TeamState, int]:
    """Resolve one possession, mutate game state, and return next possession.

    Offensive-rebound continuations remain within this call. The returned team
    order identifies next possession ownership; the integer is elapsed seconds.
    """

    seconds_left = clock
    clutch_time = bool(period and period >= 4 and seconds_left <= 300 and abs(offense.score - defense.score) <= 8)
    offense_context = _sample_lineup_chemistry(offense)
    _sample_lineup_chemistry(defense)
    if clutch_time:
        offense.team_stats["CLUTCH_POSSESSIONS"] += 1
    play_type = _choose_play_type(offense, defense, seconds_left, period or 1, config, rng)
    shooter = _choose_shooter(offense, config, rng)
    possession_target = rng.gauss(config.average_possession_seconds, config.possession_time_sd)
    if period and period >= 4 and seconds_left <= 120:
        margin = offense.score - defense.score
        if margin > 0:
            possession_target = max(possession_target, rng.gauss(20.5, 2.0))
        elif margin < 0:
            possession_target = min(possession_target, rng.gauss(8.0, 2.2))
    possession_seconds = min(seconds_left, int(max(4, min(config.shot_clock_seconds, possession_target))))

    # Late-game intentional fouling.
    if period and period >= 4 and seconds_left <= config.late_game_foul_seconds and defense.score + config.late_game_foul_deficit_min <= offense.score:
        fouler = _commit_foul(defense, rng)
        fouler.fouls += 1
        fouler.stats["PF"] += 1
        defense.team_stats["PF"] += 1
        defense.team_stats["TEAM_FOULS_PERIOD"] += 1
        _apply_disqualification(fouler, defense, config, log, clock, period)
        log.append({"clock": clock, "period": period, "team": defense.name, "event": "personal_foul", "espn_type": "Personal Foul",
                    "player": fouler.name, "drawn_by": shooter.name, "intentional": True, "free_throws": 2,
                    "team_fouls": int(defense.team_stats["TEAM_FOULS_PERIOD"]), "score": _score_state(offense, defense)})
        _replace_disqualified_players(defense, elapsed, config, log, clock, period)
        ft_result = _award_free_throws(offense, defense, shooter, 2, rng, log, clock)
        if ft_result["final_missed"]:
            next_offense, next_defense, finished = _resolve_final_free_throw_miss(offense, defense, shooter, config, rng, log, clock)
            return next_offense, next_defense, possession_seconds
        _finish_possession(offense, defense)
        return defense, offense, possession_seconds

    turnover_chance = max(0.035, min(0.300, shooter.tov_rate * PLAY_TYPES[play_type]["to_mult"] + _total_fatigue(shooter, config) * 0.012 + max(0, _lineup_defense(defense)) * 0.006 - offense_context["spacing"] * 0.002))
    if rng.random() < turnover_chance:
        shooter.stats["TOV"] += 1
        shooter.stats["POSS_USED"] += 1
        offense.team_stats["TOV"] += 1
        if rng.random() < config.steal_turnover_share:
            thief = _weighted_choice(defense.lineup, [max(0.001, p.stl_rate) for p in defense.lineup], rng)
            thief.stats["STL"] += 1
            thief.stats["DEF_TOV"] += 1
            defense.team_stats["STL"] += 1
            defense.team_stats["DEF_TOV"] += 1
            defender = thief.name
        else:
            defender = None
        log.append({"clock": clock, "team": offense.name, "event": "turnover", "espn_type": TURNOVER_LABEL, "player": shooter.name, "defender": defender,
                    "play_type": play_type, "score": _score_state(offense, defense)})
        defense.team_stats["OFF_TOV_FLAG"] = 1
        _finish_possession(offense, defense)
        return defense, offense, possession_seconds

    if rng.random() < config.offensive_foul_rate:
        shooter.fouls += 1
        shooter.stats["PF"] += 1
        shooter.stats["TOV"] += 1
        shooter.stats["POSS_USED"] += 1
        offense.team_stats["PF"] += 1
        offense.team_stats["TOV"] += 1
        _apply_disqualification(shooter, offense, config, log, clock, period)
        _replace_disqualified_players(offense, elapsed, config, log, clock, period)
        log.append({"clock": clock, "team": offense.name, "event": "turnover", "espn_type": TURNOVER_LABEL,
                    "player": shooter.name, "play_type": play_type, "score": _score_state(offense, defense)})
        defense.team_stats["OFF_TOV_FLAG"] = 1
        _finish_possession(offense, defense)
        return defense, offense, possession_seconds

    if rng.random() < config.non_shooting_foul_rate:
        fouler = _commit_foul(defense, rng)
        fouler.fouls += 1
        fouler.stats["PF"] += 1
        defense.team_stats["PF"] += 1
        defense.team_stats["TEAM_FOULS_PERIOD"] += 1
        _apply_disqualification(fouler, defense, config, log, clock, period)
        log.append({"clock": clock, "team": defense.name, "event": "personal_foul", "espn_type": "Personal Foul",
                    "player": fouler.name, "drawn_by": shooter.name, "team_fouls": int(defense.team_stats["TEAM_FOULS_PERIOD"]),
                    "in_bonus": _is_bonus(defense, clock, config), "score": _score_state(offense, defense)})
        _replace_disqualified_players(defense, elapsed, config, log, clock, period)
        if _is_bonus(defense, clock, config):
            defense.team_stats["BONUS_FTA"] += 2
            ft_result = _award_free_throws(offense, defense, shooter, 2, rng, log, clock)
            if ft_result["final_missed"]:
                next_offense, next_defense, finished = _resolve_final_free_throw_miss(offense, defense, shooter, config, rng, log, clock)
                return next_offense, next_defense, possession_seconds
            _finish_possession(offense, defense)
            return defense, offense, possession_seconds
        return offense, defense, max(2, possession_seconds // 3)

    shooting_foul_chance = config.shooting_foul_rate * PLAY_TYPES[play_type]["foul_mult"] * (0.70 + shooter.ftr * 1.25)
    if rng.random() < shooting_foul_chance:
        fouler = _commit_foul(defense, rng)
        fouler.fouls += 1
        fouler.stats["PF"] += 1
        defense.team_stats["PF"] += 1
        defense.team_stats["TEAM_FOULS_PERIOD"] += 1
        _apply_disqualification(fouler, defense, config, log, clock, period)
        zone = _choose_shot_zone(play_type, shooter, offense, defense, config, rng)
        attempts = 3 if zone == "three" else 2
        log.append({"clock": clock, "team": defense.name, "event": "shooting_foul", "espn_type": "Shooting Foul", "player": fouler.name,
                    "drawn_by": shooter.name, "free_throws": attempts, "score": _score_state(offense, defense)})
        _replace_disqualified_players(defense, elapsed, config, log, clock, period)
        ft_result = _award_free_throws(offense, defense, shooter, attempts, rng, log, clock)
        shooter.stats["POSS_USED"] += 1
        if ft_result["final_missed"]:
            next_offense, next_defense, finished = _resolve_final_free_throw_miss(offense, defense, shooter, config, rng, log, clock)
            return next_offense, next_defense, possession_seconds
        _finish_possession(offense, defense)
        return defense, offense, possession_seconds

    zone = _choose_shot_zone(play_type, shooter, offense, defense, config, rng)
    shot_type = _shot_label(zone)
    shot_value = 3 if zone == "three" else 2
    primary_defender = _choose_primary_defender(defense, config, rng)
    switched = rng.random() < min(0.55, max(0.02, config.switch_rate_base + _lineup_defense(defense) * 0.025 + (0.08 if play_type in {"pnr", "handoff"} else 0)))
    if switched:
        primary_defender.stats["SWITCHES_ON"] += 1
    help_defender = _maybe_help_defender(defense, primary_defender, zone, config, rng)
    primary_defender.stats["DEF_FGA"] += 1
    primary_defender.stats["DEF_POSS"] += 1
    defense.team_stats["DEF_FGA"] += 1
    if shot_value == 3:
        primary_defender.stats["DEF_3PA"] += 1
        defense.team_stats["DEF_3PA"] += 1
    make_prob = _shot_probability(shooter, primary_defender, help_defender, offense_context, zone, clutch_time, config)
    made = rng.random() < make_prob

    shooter.stats["FGA"] += 1
    shooter.stats["POSS_USED"] += 1
    offense.team_stats["FGA"] += 1
    if shot_value == 3:
        shooter.stats["3PA"] += 1
        offense.team_stats["3PA"] += 1

    if made:
        shooter.stats["FGM"] += 1
        shooter.stats["PTS"] += shot_value
        offense.team_stats["FGM"] += 1
        offense.team_stats["PTS"] += shot_value
        offense.score += shot_value
        primary_defender.stats["DEF_FGM"] += 1
        primary_defender.stats["DEF_PTS"] += shot_value
        defense.team_stats["DEF_FGM"] += 1
        defense.team_stats["DEF_PTS"] += shot_value
        if offense.team_stats.get("OFF_TOV_FLAG", 0):
            shooter.stats["PTS_OFF_TOV"] += shot_value
            offense.team_stats["PTS_OFF_TOV"] += shot_value
        if play_type == "transition":
            shooter.stats["PTS_FB"] += shot_value
            offense.team_stats["PTS_FB"] += shot_value
        if shot_value == 3:
            shooter.stats["3PM"] += 1
            shooter.stats["PTS_3PT"] += 3
            offense.team_stats["3PM"] += 1
            offense.team_stats["PTS_3PT"] += 3
            primary_defender.stats["DEF_3PM"] += 1
            defense.team_stats["DEF_3PM"] += 1
        else:
            shooter.stats["PTS_2PT"] += 2
            offense.team_stats["PTS_2PT"] += 2
            if zone == "rim":
                shooter.stats["PTS_PAINT"] += 2
                offense.team_stats["PTS_PAINT"] += 2
            else:
                shooter.stats["PTS_2PT_MR"] += 2
                offense.team_stats["PTS_2PT_MR"] += 2
        _record_plus_minus(offense, defense, shot_value)
        assister_name = None
        assisted = rng.random() < config.assist_probability_on_made_fg
        if assisted:
            passers = [p for p in offense.lineup if p is not shooter]
            assister = _weighted_choice(passers, [max(0.01, p.ast_rate) for p in passers], rng)
            assister.stats["AST"] += 1
            offense.team_stats["AST"] += 1
            primary_defender.stats["DEF_AST"] += 1
            defense.team_stats["DEF_AST"] += 1
            assister_name = assister.name
            if shot_value == 3:
                shooter.stats["AST_3PM"] += 1
                offense.team_stats["AST_3PM"] += 1
            else:
                shooter.stats["AST_2PM"] += 1
                offense.team_stats["AST_2PM"] += 1
        else:
            if shot_value == 3:
                shooter.stats["UAST_3PM"] += 1
                offense.team_stats["UAST_3PM"] += 1
            else:
                shooter.stats["UAST_2PM"] += 1
                offense.team_stats["UAST_2PM"] += 1
        made_event = {"clock": clock, "team": offense.name, "event": "made_fg", "espn_type": shot_type, "player": shooter.name,
                      "points": shot_value, "zone": zone, "play_type": play_type, "primary_defender": primary_defender.name, "help_defender": help_defender.name if help_defender else None, "switched": switched,
                      "lineup_context": offense_context, "score": _score_state(offense, defense)}
        if assister_name is not None:
            made_event["assist"] = assister_name
        log.append(made_event)
        if rng.random() < config.and_one_rate:
            fouler = _commit_foul(defense, rng)
            fouler.fouls += 1
            fouler.stats["PF"] += 1
            defense.team_stats["PF"] += 1
            defense.team_stats["TEAM_FOULS_PERIOD"] += 1
            _apply_disqualification(fouler, defense, config, log, clock, period)
            log.append({"clock": clock, "period": period, "team": defense.name, "event": "personal_foul", "espn_type": "Personal Foul",
                        "player": fouler.name, "drawn_by": shooter.name, "and_one": True, "free_throws": 1,
                        "team_fouls": int(defense.team_stats["TEAM_FOULS_PERIOD"]), "score": _score_state(offense, defense)})
            _replace_disqualified_players(defense, elapsed, config, log, clock, period)
            ft_result = _award_free_throws(offense, defense, shooter, 1, rng, log, clock)
            if ft_result["final_missed"]:
                next_offense, next_defense, finished = _resolve_final_free_throw_miss(offense, defense, shooter, config, rng, log, clock)
                return next_offense, next_defense, possession_seconds
        _finish_possession(offense, defense)
        return defense, offense, possession_seconds

    block_context = 1.0 + _lineup_strength(defense.lineup, "blk_rate") * 12 + (help_defender.help_defense * 0.12 if help_defender else 0)
    blocked = rng.random() < config.block_rate_on_miss * block_context
    blocker_name = None
    if blocked:
        blocker = _weighted_choice(defense.lineup, [max(0.001, p.blk_rate) for p in defense.lineup], rng)
        blocker.stats["BLK"] += 1
        defense.team_stats["BLK"] += 1
        blocker_name = blocker.name
        log.append({"clock": clock, "team": defense.name, "event": "block", "espn_type": "Block",
                    "player": blocker.name, "shooter": shooter.name, "score": _score_state(offense, defense)})

    offense_rebound_strength = sum(p.orb_rate for p in offense.lineup)
    defense_rebound_strength = sum(p.drb_rate for p in defense.lineup)
    orb_probability = max(0.12, min(0.45, offense_rebound_strength / max(0.01, offense_rebound_strength + defense_rebound_strength) * 0.70 * config.offensive_rebound_probability_multiplier))
    if rng.random() < orb_probability:
        rebounder = _choose_rebounder(offense, True, config, rng)
        rebounder.stats["ORB"] += 1
        rebounder.stats["TRB"] += 1
        offense.team_stats["ORB"] += 1
        offense.team_stats["TRB"] += 1
        log.append({"clock": clock, "team": offense.name, "event": "offensive_rebound", "espn_type": "Offensive Rebound", "player": rebounder.name,
                    "after_shot_by": shooter.name, "blocked": blocked, "blocker": blocker_name, "score": _score_state(offense, defense)})
        if rng.random() < 0.28:
            putback_type = "2PT Field Goal"
            rebounder.stats["FGA"] += 1
            rebounder.stats["POSS_USED"] += 1
            offense.team_stats["FGA"] += 1
            if rng.random() < 0.56:
                rebounder.stats["FGM"] += 1
                rebounder.stats["PTS"] += 2
                rebounder.stats["PTS_2PT"] += 2
                rebounder.stats["PTS_PAINT"] += 2
                rebounder.stats["UAST_2PM"] += 1
                offense.team_stats["FGM"] += 1
                offense.team_stats["PTS"] += 2
                offense.team_stats["PTS_2PT"] += 2
                offense.team_stats["PTS_PAINT"] += 2
                offense.team_stats["UAST_2PM"] += 1
                offense.score += 2
                _record_plus_minus(offense, defense, 2)
                log.append({"clock": clock, "team": offense.name, "event": "made_fg", "espn_type": putback_type,
                            "player": rebounder.name, "points": 2, "zone": "rim", "play_type": "putback",
                            "score": _score_state(offense, defense)})
                _finish_possession(offense, defense)
                return defense, offense, possession_seconds
            defender_board = _choose_rebounder(defense, False, config, rng)
            defender_board.stats["DRB"] += 1
            defender_board.stats["TRB"] += 1
            defense.team_stats["DRB"] += 1
            defense.team_stats["TRB"] += 1
            log.append({"clock": clock, "team": offense.name, "event": "missed_fg", "espn_type": putback_type,
                        "player": rebounder.name, "zone": "rim", "play_type": "putback", "blocked": False,
                        "score": _score_state(offense, defense)})
            log.append({"clock": clock, "team": defense.name, "event": "defensive_rebound", "espn_type": "Defensive Rebound",
                        "player": defender_board.name, "after_shot_by": rebounder.name, "source": "field_goal",
                        "score": _score_state(offense, defense)})
            _finish_possession(offense, defense)
            return defense, offense, possession_seconds
        # Offensive rebounds continue the same team's possession with a shorter reset.
        return offense, defense, possession_seconds

    rebounder = _choose_rebounder(defense, False, config, rng)
    rebounder.stats["DRB"] += 1
    rebounder.stats["TRB"] += 1
    defense.team_stats["DRB"] += 1
    defense.team_stats["TRB"] += 1
    log.append({"clock": clock, "team": offense.name, "event": "missed_fg", "espn_type": shot_type, "player": shooter.name,
                "zone": zone, "play_type": play_type, "blocked": blocked, "blocker": blocker_name, "primary_defender": primary_defender.name, "help_defender": help_defender.name if help_defender else None,
                "switched": switched, "lineup_context": offense_context, "score": _score_state(offense, defense)})
    log.append({"clock": clock, "team": defense.name, "event": "defensive_rebound", "espn_type": "Defensive Rebound",
                "player": rebounder.name, "after_shot_by": shooter.name, "source": "field_goal",
                "score": _score_state(offense, defense)})
    _finish_possession(offense, defense)
    return defense, offense, possession_seconds

def simulate_game_robust(home: TeamState, away: TeamState, config: SimConfig = SimConfig(), game_context: Optional[GameContext | Dict[str, Any]] = None, season_state: Optional[SeasonState] = None) -> Dict:
    """Simulate a complete regulation/overtime game and return all result views.

    Baseline teams are deep-copied. Results include play-by-play, possessions,
    box scores, calibration diagnostics, and reproducible input audits.
    """

    rng = random.Random(config.seed)
    if game_context is None and hasattr(home, "dataset_metadata"):
        metadata = getattr(home, "dataset_metadata", {})
        source_type = metadata.get("source_type", "historical")
        game_context = GameContext(
            dataset_id=metadata.get("dataset_id", "historical_default"),
            source_type=source_type,
            profile_mode="predicted" if source_type == "predicted" else "historical",
            variability_path=getattr(home, "default_variability_path", None),
        )
    home = copy.deepcopy(home)
    away = copy.deepcopy(away)
    home.reset_for_game()
    away.reset_for_game()
    simulation_audit = prepare_game(home, away, game_context, season_state, 0 if config.seed is None else config.seed)
    environment = simulation_audit["environment"]
    pregame_pace_multiplier = simulation_audit.get("pregame_team_context", {}).get("pace_multiplier", 1.0)
    config = replace(config,
                     average_possession_seconds=config.average_possession_seconds / (environment["pace_multiplier"] * pregame_pace_multiplier),
                     shooting_foul_rate=config.shooting_foul_rate * environment["foul_multiplier"],
                     non_shooting_foul_rate=config.non_shooting_foul_rate * environment["foul_multiplier"])
    for player in home.roster + away.roster:
        player.two_pct = max(0.30, min(0.80, player.two_pct + environment["shooting_shift"]))
        player.three_pct = max(0.18, min(0.60, player.three_pct + environment["shooting_shift"]))
        player.tov_rate = max(0.025, min(0.30, player.tov_rate * environment["turnover_multiplier"]))
        player.orb_rate = max(0.005, min(0.20, player.orb_rate + environment["rebound_shift"] * 0.35))
        player.drb_rate = max(0.02, min(0.35, player.drb_rate - environment["rebound_shift"] * 0.35))
    if config.fatigue_back_to_back_load:
        for player in home.roster + away.roster:
            player.fatigue = max(0.0, player.fatigue + config.fatigue_back_to_back_load * (1.0 - player.stamina + 0.25))
    opening_offense = home if rng.random() < 0.5 else away
    offense, defense = opening_offense, (away if opening_offense is home else home)
    log: List[Dict] = []
    possession_log: List[Dict] = []
    active_possession: Optional[Dict] = None
    possession_id = 0
    elapsed = 0
    period = 1
    regulation_seconds = config.regulation_minutes * 60

    while True:
        period_length = config.quarter_minutes * 60 if period <= 4 else config.overtime_minutes * 60
        if period in {1, 4}:
            offense = opening_offense
            opening_method = "opening_jump_ball_rule"
        elif period in {2, 3}:
            offense = away if opening_offense is home else home
            opening_method = "scheduled_regulation_period_rule"
        else:
            offense = home if rng.random() < 0.5 else away
            opening_method = "overtime_jump_ball_random"
        defense = away if offense is home else home
        for player in home.roster + away.roster:
            player.rest_eligible_after_elapsed_seconds = 0.0
        home.team_stats["TEAM_FOULS_PERIOD"] = 0
        away.team_stats["TEAM_FOULS_PERIOD"] = 0
        period_clock = period_length
        log.append({"clock": period_clock, "period": period, "event": "period_start",
                    "opening_possession_team": offense.name, "opening_method": opening_method, "score": _score_state(home, away)})
        while period_clock > 0:
            offense, defense, dead_ball_used_possession = _maybe_dead_ball_event(offense, defense, period_clock, period, config, rng, log)
            if dead_ball_used_possession:
                used_seconds = 2
            else:
                if active_possession is None:
                    possession_id += 1
                    active_possession = {"possession_id": possession_id, "period": period, "offense_team": offense.name, "defense_team": defense.name,
                                         "start_clock_seconds": period_clock, "start_score": _score_state(home, away), "duration_seconds": 0, "events": []}
                event_start = len(log)
                offense, defense, used_seconds = simulate_possession_robust(offense, defense, period_clock, elapsed, config, rng, log, period)
                recorded_seconds = min(period_clock, used_seconds)
                active_possession["events"].extend(copy.deepcopy(log[event_start:]))
                active_possession["duration_seconds"] += recorded_seconds
                active_possession["end_clock_seconds"] = max(0, period_clock - recorded_seconds)
                if offense.name != active_possession["offense_team"]:
                    active_possession["end_score"] = _score_state(home, away)
                    active_possession["ended_by"] = "change_of_possession"
                    possession_log.append(active_possession)
                    active_possession = None
            recorded_seconds = min(period_clock, used_seconds)
            for team in (home, away):
                _record_lineup_seconds(team, recorded_seconds, config)
            period_clock = max(0, period_clock - recorded_seconds)
            elapsed += recorded_seconds
            if offense.team_stats["POSS"] % 4 == 0:
                _substitute(home, elapsed, config, log, period_clock, period, away.score)
                _substitute(away, elapsed, config, log, period_clock, period, home.score)
        if active_possession is not None:
            active_possession["end_clock_seconds"] = 0
            active_possession["end_score"] = _score_state(home, away)
            active_possession["ended_by"] = "period_end"
            possession_log.append(active_possession)
            active_possession = None
        _rest_lineup(home, config.period_break_recovery_seconds)
        _rest_lineup(away, config.period_break_recovery_seconds)
        if period < 4:
            next_period_team = opening_offense if period + 1 == 4 else (away if opening_offense is home else home)
            next_period_method = "scheduled_regulation_period_rule"
        else:
            next_period_team = None
            next_period_method = "overtime_jump_ball_random" if home.score == away.score else None
        log.append({"clock": 0, "period": period, "event": "period_end", "possession_team_at_end": offense.name,
                    "next_period_opening_team": next_period_team.name if next_period_team else None,
                    "next_period_opening_method": next_period_method, "score": _score_state(home, away)})
        if period >= 4 and home.score != away.score:
            break
        period += 1

    return {
        "home": home,
        "away": away,
        "winner": home.name if home.score > away.score else away.name,
        "final_score": {home.name: home.score, away.name: away.score},
        "periods": period,
        "possessions": int(home.team_stats["POSS"] + away.team_stats["POSS"]),
        "play_by_play": log,
        "possession_log": possession_log,
        "team_table": summarize_team_table(home, away),
        "player_table": summarize_player_table(home) + summarize_player_table(away),
        "box_score_views": build_nba_box_score_views(home, away),
        "calibration": calibration_report({"team_table": summarize_team_table(home, away)}, config),
        "simulation_audit": simulation_audit,
    }

def simulate_single_game_robust(home: TeamState, away: TeamState, config: Optional[SimConfig] = None, output_dir: Optional[str] = "outputs", game_id: str = "single_game", game_context: Optional[GameContext | Dict[str, Any]] = None, season_state: Optional[SeasonState] = None) -> Dict:
    """Run one game and, by default, save its possession-by-possession CSV log."""
    game = simulate_game_robust(home, away, config or SimConfig(), game_context=game_context, season_state=season_state)
    if output_dir is not None:
        game["possession_log_csv"] = export_single_game_possession_log_csv(game, output_dir=output_dir, game_id=game_id)
        game["audit_csv_exports"] = export_simulation_audit_csv([(game, {"simulation_scope": "single_game", "game_id": game_id, "game_run": 1})], output_dir, "single_game")
    return game

def _safe_div(num: float, den: float) -> float:
    return 0.0 if den == 0 else num / den

def summarize_player_table(team: TeamState) -> List[Dict]:
    """Return completed-game box-score rows for every rostered player."""

    team_poss = max(1, team.team_stats["POSS"])
    rows = []
    for p in team.roster:
        s = p.stats
        tsa = s["FGA"] + 0.44 * s["FTA"]
        rows.append({
            "team": team.name,
            "player": p.name,
            "MIN": round(s["MIN"], 1),
            "PTS": int(s["PTS"]), "REB": int(s["TRB"]), "AST": int(s["AST"]), "STL": int(s["STL"]), "BLK": int(s["BLK"]),
            "TOV": int(s["TOV"]), "PF": int(s["PF"]), "+/-": int(s["+/-"]),
            "FG": f"{int(s['FGM'])}-{int(s['FGA'])}", "3P": f"{int(s['3PM'])}-{int(s['3PA'])}", "FT": f"{int(s['FTM'])}-{int(s['FTA'])}",
            "TS%": round(_safe_div(s["PTS"], 2 * tsa), 3),
            "eFG%": round(_safe_div(s["FGM"] + 0.5 * s["3PM"], s["FGA"]), 3),
            "USG%": round(100 * _safe_div(s["POSS_USED"], team_poss), 1),
            "AST%": round(100 * _safe_div(s["AST"], max(1, team.team_stats["FGM"])), 1),
            "TOV%": round(100 * _safe_div(s["TOV"], max(1, s["POSS_USED"])), 1),
            "REB%": round(100 * _safe_div(s["TRB"], max(1, s["POSS_ON"])), 1),
            "PeakFatigue": round(s.get("MAX_FATIGUE", 0), 3),
            "LongStint": round(s.get("MAX_STINT_MIN", 0), 1),
        })
    return sorted(rows, key=lambda r: (r["team"], -r["MIN"], -r["PTS"]))

def summarize_team_table(home: TeamState, away: TeamState) -> List[Dict]:
    """Return one completed-game totals row for each team."""

    rows = []
    for team, opponent in ((home, away), (away, home)):
        s = team.team_stats
        opp = opponent.team_stats
        possessions = s["POSS"]
        rows.append({
            "team": team.name,
            "PTS": int(s["PTS"]),
            "POSS": int(possessions),
            "PACE": round(48 * _safe_div(possessions, max(1, s["SECONDS"] / 60)), 1),
            "ORTG": round(100 * _safe_div(s["PTS"], possessions), 1),
            "DRTG": round(100 * _safe_div(opp["PTS"], max(1, opp["POSS"])), 1),
            "eFG%": round(_safe_div(s["FGM"] + 0.5 * s["3PM"], s["FGA"]), 3),
            "TS%": round(_safe_div(s["PTS"], 2 * (s["FGA"] + 0.44 * s["FTA"])), 3),
            "TOV%": round(100 * _safe_div(s["TOV"], possessions), 1),
            "ORB%": round(100 * _safe_div(s["ORB"], s["ORB"] + opp["DRB"]), 1),
            "FTr": round(_safe_div(s["FTA"], s["FGA"]), 3),
            "AST%": round(100 * _safe_div(s["AST"], s["FGM"]), 1),
            "TIMEOUTS": int(s.get("TIMEOUTS", 0)),
            "BONUS_FTA": int(s.get("BONUS_FTA", 0)),
            "AVG_SPACING": round(_safe_div(s.get("AVG_SPACING", 0), s.get("CHEM_SAMPLES", 0)), 3),
            "AVG_RIM_PRESSURE": round(_safe_div(s.get("AVG_RIM_PRESSURE", 0), s.get("CHEM_SAMPLES", 0)), 3),
            "AVG_LINEUP_DEFENSE": round(_safe_div(s.get("AVG_LINEUP_DEFENSE", 0), s.get("CHEM_SAMPLES", 0)), 3),
            "+/-": int(s["PLUS_MINUS"]),
        })
    return rows

def _pct(num: float, den: float) -> float:
    return round(_safe_div(num, den), 3)

def _player_name_parts(name: str) -> Tuple[str, str]:
    parts = name.split()
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]

def _identity(team: TeamState, player: Optional[PlayerProfile] = None, idx: int = 0) -> Dict:
    city, name = (team.name, team.name)
    if " " in team.name:
        city, name = team.name.rsplit(" ", 1)
    base = {"gameId": "SIM_GAME", "teamId": abs(hash(team.name)) % 100000, "teamCity": city,
            "teamName": name, "teamTricode": team.name[:3].upper(), "teamSlug": team.name.lower().replace(" ", "-")}
    if player is not None:
        first, family = _player_name_parts(player.name)
        base.update({"personId": abs(hash((team.name, player.name))) % 10000000, "firstName": first, "familyName": family,
                     "nameI": (first[:1] + ". " + family).strip(), "playerSlug": player.name.lower().replace(" ", "-"),
                     "position": player.role.upper(), "comment": "", "jerseyNum": str(idx + 1)})
    return base

def nba_traditional_view(team: TeamState, players: bool = True) -> List[Dict]:
    """Build NBA-style traditional player or team box-score rows."""

    rows = []
    source = team.roster if players else [None]
    for idx, p in enumerate(source):
        s = p.stats if p else team.team_stats
        row = _identity(team, p, idx) if p else _identity(team)
        row.update({"minutes": round(s.get("MIN", 240 if not p else 0), 1),
                    "fieldGoalsMade": int(s["FGM"]), "fieldGoalsAttempted": int(s["FGA"]), "fieldGoalsPercentage": _pct(s["FGM"], s["FGA"]),
                    "threePointersMade": int(s["3PM"]), "threePointersAttempted": int(s["3PA"]), "threePointersPercentage": _pct(s["3PM"], s["3PA"]),
                    "freeThrowsMade": int(s["FTM"]), "freeThrowsAttempted": int(s["FTA"]), "freeThrowsPercentage": _pct(s["FTM"], s["FTA"]),
                    "reboundsOffensive": int(s["ORB"]), "reboundsDefensive": int(s["DRB"]), "reboundsTotal": int(s["TRB"]),
                    "assists": int(s["AST"]), "steals": int(s["STL"]), "blocks": int(s["BLK"]), "turnovers": int(s["TOV"]),
                    "foulsPersonal": int(s["PF"]), "points": int(s["PTS"]), "plusMinusPoints": int(s.get("+/-", s.get("PLUS_MINUS", 0)))})
        rows.append(row)
    return rows

def nba_advanced_view(team: TeamState, opponent: TeamState, players: bool = True) -> List[Dict]:
    """Build NBA-style advanced efficiency rows from completed statistics."""

    rows = []
    source = team.roster if players else [None]
    team_poss = max(1, team.team_stats["POSS"])
    opp_poss = max(1, opponent.team_stats["POSS"])
    for idx, p in enumerate(source):
        s = p.stats if p else team.team_stats
        poss = max(1, s.get("POSS_ON", team_poss))
        tsa = s["FGA"] + 0.44 * s["FTA"]
        off_rating = 100 * _safe_div(s["PTS"], max(1, s.get("POSS_USED", team_poss))) if p else 100 * _safe_div(s["PTS"], team_poss)
        def_rating = 100 * _safe_div(opponent.team_stats["PTS"], opp_poss)
        row = _identity(team, p, idx) if p else _identity(team)
        row.update({"minutes": round(s.get("MIN", 240 if not p else 0), 1),
                    "estimatedOffensiveRating": round(off_rating, 1), "offensiveRating": round(off_rating, 1),
                    "estimatedDefensiveRating": round(def_rating, 1), "defensiveRating": round(def_rating, 1),
                    "estimatedNetRating": round(off_rating - def_rating, 1), "netRating": round(off_rating - def_rating, 1),
                    "assistPercentage": round(_safe_div(s["AST"], max(1, team.team_stats["FGM"])), 3),
                    "assistToTurnover": round(_safe_div(s["AST"], s["TOV"]), 3),
                    "assistRatio": round(100 * _safe_div(s["AST"], max(1, s.get("POSS_USED", team_poss))), 1),
                    "offensiveReboundPercentage": round(_safe_div(s["ORB"], max(1, s["ORB"] + opponent.team_stats["DRB"])), 3),
                    "defensiveReboundPercentage": round(_safe_div(s["DRB"], max(1, s["DRB"] + opponent.team_stats["ORB"])), 3),
                    "reboundPercentage": round(_safe_div(s["TRB"], max(1, team.team_stats["TRB"] + opponent.team_stats["TRB"])), 3),
                    "turnoverRatio": round(100 * _safe_div(s["TOV"], max(1, s.get("POSS_USED", team_poss))), 1),
                    "effectiveFieldGoalPercentage": _pct(s["FGM"] + 0.5 * s["3PM"], s["FGA"]),
                    "trueShootingPercentage": _pct(s["PTS"], 2 * tsa),
                    "usagePercentage": round(_safe_div(s.get("POSS_USED", team_poss), team_poss), 3),
                    "estimatedUsagePercentage": round(_safe_div(s.get("POSS_USED", team_poss), team_poss), 3),
                    "estimatedPace": round(48 * _safe_div(team_poss, max(1, team.team_stats["SECONDS"] / 60)), 1),
                    "pace": round(48 * _safe_div(team_poss, max(1, team.team_stats["SECONDS"] / 60)), 1),
                    "pacePer40": round(40 * _safe_div(team_poss, max(1, team.team_stats["SECONDS"] / 60)), 1),
                    "possessions": int(poss), "PIE": round(_safe_div(s["PTS"] + s["TRB"] + s["AST"] + s["STL"] + s["BLK"] - s["FGA"] - s["TOV"] - s["PF"], max(1, team.team_stats["PTS"] + opponent.team_stats["PTS"])), 3)})
        rows.append(row)
    return rows

def nba_scoring_view(team: TeamState, players: bool = True) -> List[Dict]:
    """Build NBA-style scoring-composition rows for players or a team."""

    rows = []
    source = team.roster if players else [None]
    for idx, p in enumerate(source):
        s = p.stats if p else team.team_stats
        two_fga = s["FGA"] - s["3PA"]
        two_pm = s["FGM"] - s["3PM"]
        pts = max(1, s["PTS"])
        row = _identity(team, p, idx) if p else _identity(team)
        row.update({"minutes": round(s.get("MIN", 240 if not p else 0), 1),
                    "percentageFieldGoalsAttempted2pt": _pct(two_fga, s["FGA"]),
                    "percentageFieldGoalsAttempted3pt": _pct(s["3PA"], s["FGA"]),
                    "percentagePoints2pt": _pct(s["PTS_2PT"], pts),
                    "percentagePointsMidrange2pt": _pct(s["PTS_2PT_MR"], pts),
                    "percentagePoints3pt": _pct(s["PTS_3PT"], pts),
                    "percentagePointsFastBreak": _pct(s["PTS_FB"], pts),
                    "percentagePointsFreeThrow": _pct(s["PTS_FT"], pts),
                    "percentagePointsOffTurnovers": _pct(s["PTS_OFF_TOV"], pts),
                    "percentagePointsPaint": _pct(s["PTS_PAINT"], pts),
                    "percentageAssisted2pt": _pct(s["AST_2PM"], two_pm),
                    "percentageUnassisted2pt": _pct(s["UAST_2PM"], two_pm),
                    "percentageAssisted3pt": _pct(s["AST_3PM"], s["3PM"]),
                    "percentageUnassisted3pt": _pct(s["UAST_3PM"], s["3PM"]),
                    "percentageAssistedFGM": _pct(s["AST_2PM"] + s["AST_3PM"], s["FGM"]),
                    "percentageUnassistedFGM": _pct(s["UAST_2PM"] + s["UAST_3PM"], s["FGM"])})
        rows.append(row)
    return rows

def nba_defense_view(team: TeamState, players: bool = True) -> List[Dict]:
    """Build simplified NBA-style defensive event rows for players or a team."""

    rows = []
    source = team.roster if players else [None]
    for idx, p in enumerate(source):
        s = p.stats if p else team.team_stats
        row = _identity(team, p, idx) if p else _identity(team)
        row.update({"matchupMinutes": round(s.get("MIN", 240 if not p else 0), 1),
                    "partialPossessions": int(s.get("DEF_POSS", team.team_stats["POSS"])),
                    "switchesOn": int(s.get("SWITCHES_ON", 0)),
                    "playerPoints": int(s.get("DEF_PTS", 0)),
                    "defensiveRebounds": int(s["DRB"]),
                    "matchupAssists": int(s.get("DEF_AST", 0)),
                    "matchupTurnovers": int(s.get("DEF_TOV", 0)),
                    "steals": int(s["STL"]), "blocks": int(s["BLK"]),
                    "matchupFieldGoalsMade": int(s.get("DEF_FGM", 0)),
                    "matchupFieldGoalsAttempted": int(s.get("DEF_FGA", 0)),
                    "matchupFieldGoalPercentage": _pct(s.get("DEF_FGM", 0), s.get("DEF_FGA", 0)),
                    "matchupThreePointersMade": int(s.get("DEF_3PM", 0)),
                    "matchupThreePointersAttempted": int(s.get("DEF_3PA", 0)),
                    "matchupThreePointerPercentage": _pct(s.get("DEF_3PM", 0), s.get("DEF_3PA", 0))})
        rows.append(row)
    return rows

def build_nba_box_score_views(home: TeamState, away: TeamState) -> Dict:
    """Return traditional, advanced, scoring, and defense views for both teams."""

    return {
        "traditional": {"players": nba_traditional_view(home) + nba_traditional_view(away),
                         "teams": nba_traditional_view(home, players=False) + nba_traditional_view(away, players=False)},
        "advanced": {"players": nba_advanced_view(home, away) + nba_advanced_view(away, home),
                     "teams": nba_advanced_view(home, away, players=False) + nba_advanced_view(away, home, players=False)},
        "scoring": {"players": nba_scoring_view(home) + nba_scoring_view(away),
                    "teams": nba_scoring_view(home, players=False) + nba_scoring_view(away, players=False)},
        "defense": {"players": nba_defense_view(home) + nba_defense_view(away),
                    "teams": nba_defense_view(home, players=False) + nba_defense_view(away, players=False)},
    }

def calibration_report(game: Dict, config: SimConfig = SimConfig()) -> Dict:
    """Compare one simulated game's aggregate rates with configured NBA targets."""

    rows = []
    for row in game["team_table"]:
        rows.append({
            "team": row["team"],
            "pace_delta": round(row["PACE"] - config.target_pace, 1),
            "ortg_delta": round(row["ORTG"] - config.target_offensive_rating, 1),
            "tov_pct_delta": round(row["TOV%"] - config.target_turnover_pct, 1),
            "ftr_delta": round(row["FTr"] - config.target_free_throw_rate, 3),
            "orb_pct_delta": round(row["ORB%"] - config.target_offensive_rebound_pct, 1),
        })
    return {"targets": {"pace": config.target_pace, "offensive_rating": config.target_offensive_rating,
                          "turnover_pct": config.target_turnover_pct, "free_throw_rate": config.target_free_throw_rate,
                          "offensive_rebound_pct": config.target_offensive_rebound_pct},
            "teams": rows,
            "notes": "Use deltas over many simulations, not one game, to tune possession time, shot quality, foul, turnover, and rebound parameters."}

def run_monte_carlo_robust(home: TeamState, away: TeamState, n_games: Optional[int] = None, seed: Optional[int] = None, config: Optional[SimConfig] = None, game_context: Optional[GameContext | Dict[str, Any]] = None) -> Dict:
    """Run a reproducible matchup distribution without writing output files."""

    results = []
    home_wins = 0
    base_config = config or SimConfig(seed=seed)
    n_games = base_config.game_runs if n_games is None else n_games
    if not isinstance(n_games, int) or n_games < 1:
        raise ValueError("n_games must be a positive integer")
    base_seed = base_config.seed if seed is None else seed
    base_seed = 0 if base_seed is None else base_seed
    for i in range(n_games):
        game_config = SimConfig(**{**base_config.__dict__, "seed": base_seed + i})
        game = simulate_game_robust(home, away, game_config, game_context=game_context)
        results.append(game)
        home_wins += int(game["winner"] == home.name)
    avg_home = sum(g["final_score"][home.name] for g in results) / n_games
    avg_away = sum(g["final_score"][away.name] for g in results) / n_games
    avg_poss = sum(g["possessions"] for g in results) / n_games
    calib_keys = ["pace_delta", "ortg_delta", "tov_pct_delta", "ftr_delta", "orb_pct_delta"]
    avg_calibration = {}
    for team_name in (home.name, away.name):
        rows = [row for g in results for row in g["calibration"]["teams"] if row["team"] == team_name]
        avg_calibration[team_name] = {k: round(sum(r[k] for r in rows) / max(1, len(rows)), 3) for k in calib_keys}
    return {
        "games": n_games,
        "home_win_pct": round(home_wins / n_games, 3),
        "away_win_pct": round(1 - home_wins / n_games, 3),
        "avg_score": {home.name: round(avg_home, 1), away.name: round(avg_away, 1)},
        "avg_total_possessions": round(avg_poss, 1),
        "avg_calibration_deltas": avg_calibration,
        "results": results,
    }

def simulate_game_batch_robust(home: TeamState, away: TeamState, config: Optional[SimConfig] = None, game_runs: Optional[int] = None, seed: Optional[int] = None, output_dir: Optional[str] = "outputs", game_id: str = "matchup", game_context: Optional[GameContext | Dict[str, Any]] = None, season_state: Optional[SeasonState] = None) -> Dict:
    """Simulate one matchup repeatedly; defaults to config.game_runs (10)."""
    base_config = config or SimConfig()
    def contextual_runner(context_home, context_away, context_config):
        return simulate_game_robust(context_home, context_away, context_config, game_context=game_context, season_state=season_state)
    result = run_game_batch(home, away, contextual_runner, base_config, game_runs=game_runs, seed=seed)
    if output_dir is not None:
        result["csv_exports"] = export_matchup_results_csv(result, output_dir=output_dir, game_id=game_id)
    return result

def simulate_season_robust(schedule, config: Optional[SimConfig] = None, season_runs: Optional[int] = None, season_game_runs: Optional[int] = None, seed: Optional[int] = None, output_dir: Optional[str] = "outputs", game_contexts: Optional[Dict[str, GameContext | Dict[str, Any]]] = None) -> Dict:
    """Run full seasons, optionally with repeated simulations of every scheduled game.

    Schedule entries are (home_team, away_team) or (game_id, home_team, away_team).
    Nested batches preserve every game result; one randomly selected result per fixture
    is used for each season iteration's discrete standings.
    """
    base_config = config or SimConfig()
    def batch_runner(home, away, runs, batch_seed, game_context=None, season_state=None):
        return simulate_game_batch_robust(home, away, base_config, game_runs=runs, seed=batch_seed, output_dir=None, game_context=game_context, season_state=season_state)
    result = run_season_simulations(schedule, batch_runner, base_config, season_runs=season_runs, season_game_runs=season_game_runs, seed=seed,
                                    game_contexts=game_contexts, season_state_factory=lambda season_run: SeasonState(season_run=season_run))
    if output_dir is not None:
        result["csv_exports"] = export_season_results_csv(result, output_dir=output_dir)
    return result
