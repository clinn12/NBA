"""Dataset-neutral game context, season state, and pregame profile sampling.

Front Matter
------------
Project: NBA Simulator
File type: Python module
Status: Active
Last updated: 2026-08-01

Purpose: apply roster, availability, workload, profile, environment, and
matchup assumptions before a game without coupling the engine to one dataset.
Usage: construct ``GameContext``/``SeasonState`` directly or call
``prepare_game`` through the canonical simulator. Duck typing avoids circular
imports between context preparation and simulator team/player classes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import copy
import json
from pathlib import Path
import random
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


PROFILE_FIELDS = (
    "mpg", "usage", "two_pct", "three_pct", "ft_pct", "three_rate", "ftr",
    "ast_rate", "tov_rate", "orb_rate", "drb_rate", "stl_rate", "blk_rate",
    "foul_rate", "defense", "stamina", "clutch", "rim_pressure",
    "off_ball_gravity", "switchability", "help_defense",
)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _stable_seed(base_seed: int, *parts: str) -> int:
    value = int(base_seed) & 0xFFFFFFFF
    for part in parts:
        for index, character in enumerate(str(part), start=1):
            value = (value * 1_000_003 + index * ord(character)) & 0xFFFFFFFF
    return value


@dataclass
class PlayerGameOverride:
    """Optional per-game roster, minutes, usage, and role changes for one player."""

    excluded: bool = False
    starter: Optional[bool] = None
    expected_minutes: Optional[float] = None
    minutes_limit: Optional[float] = None
    usage: Optional[float] = None
    role: Optional[str] = None


@dataclass
class GameContext:
    """Auditable game-specific assumptions layered over a baseline team dataset."""

    game_id: str = "single_game"
    dataset_id: str = "unspecified"
    source_type: str = "historical"
    profile_mode: str = "historical"  # baseline, historical, predicted, blended
    variability_path: Optional[str] = None
    excluded_players: Dict[str, List[str]] = field(default_factory=dict)
    player_overrides: Dict[str, Dict[str, PlayerGameOverride | Dict[str, Any]]] = field(default_factory=dict)
    starters: Dict[str, List[str]] = field(default_factory=dict)
    rotation_size: Dict[str, int] = field(default_factory=dict)
    home_rest_days: int = 1
    away_rest_days: int = 1
    home_travel_miles: float = 0.0
    away_travel_miles: float = 0.0
    home_court_points: float = 2.0
    enable_profile_sampling: bool = True
    enable_shared_environment: bool = True
    enable_matchup_adjustments: bool = True
    enable_pregame_team_context: bool = False
    expected_pace: Optional[float] = None
    league_pace: Optional[float] = None
    home_expected_offensive_rating: Optional[float] = None
    away_expected_offensive_rating: Optional[float] = None
    league_offensive_rating: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamSeasonState:
    """Mutable workload and availability history for one team in a season run."""

    games_played: int = 0
    unavailable_players: List[str] = field(default_factory=list)
    player_fatigue_load: Dict[str, float] = field(default_factory=dict)
    cumulative_minutes: Dict[str, float] = field(default_factory=dict)


@dataclass
class SeasonState:
    """Team workload state shared sequentially across one simulated season run."""

    season_run: int = 1
    teams: Dict[str, TeamSeasonState] = field(default_factory=dict)

    def team(self, team_name: str) -> TeamSeasonState:
        return self.teams.setdefault(team_name, TeamSeasonState())

    def update_after_game(self, game: Mapping[str, Any]) -> None:
        """Advance workload state using the one result selected for standings."""
        for side in ("home", "away"):
            team = game[side]
            state = self.team(team.name)
            state.games_played += 1
            active_names = {player.name for player in team.roster}
            for player_name in list(state.player_fatigue_load):
                if player_name not in active_names:
                    state.player_fatigue_load[player_name] *= 0.72
            for player in team.roster:
                minutes = float(player.stats.get("MIN", 0.0))
                prior = state.player_fatigue_load.get(player.name, 0.0)
                state.player_fatigue_load[player.name] = _clamp(prior * 0.58 + minutes / 48 * 0.42, 0.0, 1.5)
                state.cumulative_minutes[player.name] = state.cumulative_minutes.get(player.name, 0.0) + minutes


def normalize_game_context(value: Optional[GameContext | Mapping[str, Any]]) -> GameContext:
    """Return an isolated ``GameContext`` from a dataclass, mapping, or ``None``."""

    if value is None:
        return GameContext(enable_profile_sampling=False, enable_shared_environment=False, enable_matchup_adjustments=False)
    if isinstance(value, GameContext):
        return copy.deepcopy(value)
    if not isinstance(value, Mapping):
        raise TypeError("game_context must be a GameContext, mapping, or None")
    data = dict(value)
    return GameContext(**data)


def game_context_to_dict(context: GameContext) -> Dict[str, Any]:
    """Serialize a game context and nested player overrides for audit output."""

    return asdict(context)


def _load_variability(path: Optional[str]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    if not path:
        return {}, {}
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"variability dataset not found: {source}")
    with source.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    players: Dict[str, Dict[str, Any]] = {}
    for team in payload.get("teams", []):
        for player in team.get("players", []):
            players[player["player"]] = player
    return players, dict(payload.get("metadata", {}))


def _override_for(context: GameContext, team_name: str, player_name: str) -> PlayerGameOverride:
    raw = context.player_overrides.get(team_name, {}).get(player_name, {})
    if isinstance(raw, PlayerGameOverride):
        return copy.deepcopy(raw)
    return PlayerGameOverride(**raw)


def _distribution(profile: Optional[Mapping[str, Any]], group: str, field_name: str) -> Mapping[str, Any]:
    if not profile:
        return {}
    return profile.get(group, {}).get(field_name, {})


def _relative_sd(distribution: Mapping[str, Any], default: float, maximum: float) -> float:
    mean = abs(float(distribution.get("mean", 0.0)))
    std = float(distribution.get("std", 0.0))
    if mean <= 1e-9 or std <= 0:
        return default
    return _clamp(std / mean, 0.01, maximum)


def _sample_environment(context: GameContext, seed: int) -> Dict[str, float]:
    if not context.enable_shared_environment:
        return {
            "pace_multiplier": 1.0, "shooting_shift": 0.0, "foul_multiplier": 1.0,
            "turnover_multiplier": 1.0, "rebound_shift": 0.0, "environment_seed": seed,
        }
    rng = random.Random(_stable_seed(seed, context.game_id, "environment"))
    pace_z = rng.gauss(0.0, 1.0)
    shooting_z = rng.gauss(0.0, 1.0)
    physicality_z = rng.gauss(0.0, 1.0)
    turnover_z = 0.35 * pace_z + rng.gauss(0.0, 0.94)
    return {
        "pace_multiplier": _clamp(1.0 + pace_z * 0.025, 0.93, 1.08),
        "shooting_shift": _clamp(shooting_z * 0.012, -0.035, 0.035),
        "foul_multiplier": _clamp(1.0 + physicality_z * 0.09, 0.75, 1.28),
        "turnover_multiplier": _clamp(1.0 + turnover_z * 0.06, 0.82, 1.20),
        "rebound_shift": _clamp(rng.gauss(0.0, 0.015), -0.04, 0.04),
        "environment_seed": _stable_seed(seed, context.game_id, "environment"),
    }


def _normalize_minutes(players: Sequence[Any], overrides: Mapping[str, PlayerGameOverride], target: float = 240.0) -> Dict[str, float]:
    if len(players) < 5:
        raise ValueError("A team must have at least five available players")
    desired: Dict[str, float] = {}
    caps: Dict[str, float] = {}
    for player in players:
        override = overrides[player.name]
        desired[player.name] = max(0.0, float(override.expected_minutes if override.expected_minutes is not None else player.mpg))
        caps[player.name] = _clamp(float(override.minutes_limit if override.minutes_limit is not None else 48.0), 0.0, 48.0)
        desired[player.name] = min(desired[player.name], caps[player.name])
    if sum(caps.values()) < target - 1e-6:
        raise ValueError("Available-player minute limits cannot cover 240 team minutes")
    allocated = {name: 0.0 for name in desired}
    remaining = target
    pool = set(desired)
    for _ in range(len(players) + 2):
        if remaining <= 1e-8 or not pool:
            break
        weight_sum = sum(max(0.25, desired[name] - allocated[name]) for name in pool)
        changed = False
        for name in list(pool):
            proposal = remaining * max(0.25, desired[name] - allocated[name]) / weight_sum
            room = caps[name] - allocated[name]
            addition = min(proposal, room)
            allocated[name] += addition
            changed = changed or addition > 0
            if room - addition <= 1e-8:
                pool.remove(name)
        remaining = target - sum(allocated.values())
        if not changed:
            break
    if remaining > 1e-5:
        for name in sorted(allocated, key=lambda item: desired[item], reverse=True):
            addition = min(remaining, caps[name] - allocated[name])
            allocated[name] += addition
            remaining -= addition
            if remaining <= 1e-8:
                break
    return allocated


def _sample_player(player: Any, variability: Optional[Mapping[str, Any]], team_z: Dict[str, float], seed: int) -> Dict[str, Any]:
    baseline = {field_name: float(getattr(player, field_name)) for field_name in PROFILE_FIELDS}
    rng = random.Random(seed)
    opportunity_z = 0.55 * team_z["pace"] + rng.gauss(0.0, 0.835)
    form_z = 0.45 * team_z["shooting"] + rng.gauss(0.0, 0.893)
    creation_z = 0.35 * opportunity_z + rng.gauss(0.0, 0.937)
    raw_min = _distribution(variability, "raw_game_distributions", "MIN")
    per = variability.get("per_opportunity_distributions", {}) if variability else {}
    minute_sd = min(7.0, float(raw_min.get("std", 3.0)) * 0.35)
    sampled = dict(baseline)
    sampled["mpg"] = _clamp(baseline["mpg"] + opportunity_z * minute_sd, 1.0, 48.0)
    usage_cv = _relative_sd(per.get("FGA_PER_36", {}), 0.08, 0.24)
    sampled["usage"] = _clamp(baseline["usage"] * (1.0 + creation_z * usage_cv * 0.55), 5.0, 42.0)
    two_sd = float(per.get("TWO_PCT", {}).get("std", 0.075))
    three_sd = float(per.get("FG3_PCT", {}).get("std", 0.105))
    ft_sd = float(per.get("FT_PCT", {}).get("std", 0.08))
    sampled["two_pct"] = _clamp(baseline["two_pct"] + form_z * min(0.045, two_sd * 0.40), 0.35, 0.75)
    sampled["three_pct"] = _clamp(baseline["three_pct"] + form_z * min(0.055, three_sd * 0.38), 0.20, 0.55)
    sampled["ft_pct"] = _clamp(baseline["ft_pct"] + form_z * min(0.035, ft_sd * 0.30), 0.45, 0.98)
    rate_map = {
        "three_rate": ("THREE_RATE", 0.12, 0.04, 0.90),
        "ftr": ("FTR", 0.14, 0.03, 0.80),
        "ast_rate": ("AST_PER_36", 0.10, 0.01, 0.55),
        "tov_rate": ("TOV_PER_36", 0.09, 0.025, 0.30),
        "foul_rate": ("PF_PER_36", 0.08, 0.01, 0.12),
    }
    for attr, (source, default_cv, lower, upper) in rate_map.items():
        cv = _relative_sd(per.get(source, {}), default_cv, 0.35)
        signal = creation_z if attr in {"three_rate", "ftr", "ast_rate", "tov_rate"} else opportunity_z
        sampled[attr] = _clamp(baseline[attr] * (1.0 + signal * cv * 0.35), lower, upper)
    for field_name, value in sampled.items():
        setattr(player, field_name, value)
    return {
        "player": player.name,
        "profile_seed": seed,
        "opportunity_z": round(opportunity_z, 5),
        "efficiency_z": round(form_z, 5),
        **{f"baseline_{name}": round(value, 6) for name, value in baseline.items()},
        **{f"sampled_{name}": round(value, 6) for name, value in sampled.items()},
    }


def _team_defense(players: Iterable[Any]) -> float:
    values = [player.defense + 0.35 * player.switchability + 0.25 * player.help_defense for player in players]
    return sum(values) / max(1, len(values))


def _prepare_team(team: Any, context: GameContext, state: Optional[TeamSeasonState], variability: Mapping[str, Any], seed: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    original_roster = list(team.roster)
    excluded = set(context.excluded_players.get(team.name, []))
    if state:
        excluded.update(state.unavailable_players)
    overrides = {player.name: _override_for(context, team.name, player.name) for player in original_roster}
    excluded.update(name for name, override in overrides.items() if override.excluded)
    active = [player for player in original_roster if player.name not in excluded]
    rotation_size = context.rotation_size.get(team.name)
    if rotation_size is not None:
        if rotation_size < 5:
            raise ValueError(f"rotation_size for {team.name} must be at least five")
        active = sorted(active, key=lambda player: (player.mpg, player.usage), reverse=True)[:rotation_size]
    if len(active) < 5:
        raise ValueError(f"{team.name} has fewer than five available players")
    for player in active:
        override = overrides[player.name]
        if override.usage is not None:
            player.usage = float(override.usage)
        if override.role is not None:
            player.role = override.role
        if state:
            player.fatigue = _clamp(state.player_fatigue_load.get(player.name, 0.0) * 0.35, 0.0, 0.65)
    minute_targets = _normalize_minutes(active, overrides)
    for player in active:
        player.mpg = minute_targets[player.name]
    explicit_starters = list(context.starters.get(team.name, []))
    explicit_starters.extend(name for name, override in overrides.items() if override.starter is True and name not in explicit_starters)
    starters = [next(player for player in active if player.name == name) for name in explicit_starters if any(player.name == name for player in active)]
    for player in sorted(active, key=lambda item: (item.mpg, item.usage), reverse=True):
        if len(starters) >= 5:
            break
        if player not in starters and overrides[player.name].starter is not False:
            starters.append(player)
    if len(starters) < 5:
        for player in sorted(active, key=lambda item: (item.mpg, item.usage), reverse=True):
            if player not in starters:
                starters.append(player)
            if len(starters) == 5:
                break
    team.roster = active
    team.lineup = starters[:5]
    team.bench = [player for player in active if player not in team.lineup]
    team.expected_starters = [player.name for player in team.lineup]
    team.excluded_players = sorted(excluded)
    team.baseline_roster_defense = _team_defense(sorted(original_roster, key=lambda player: player.mpg, reverse=True)[:5])
    team.active_roster_defense = _team_defense(sorted(active, key=lambda player: player.mpg, reverse=True)[:5])
    rng = random.Random(_stable_seed(seed, team.name, "team_factors"))
    team_z = {"pace": rng.gauss(0.0, 1.0), "shooting": rng.gauss(0.0, 1.0)}
    profiles = []
    if context.enable_profile_sampling and context.profile_mode != "baseline":
        for player in active:
            profiles.append(_sample_player(player, variability.get(player.name), team_z, _stable_seed(seed, team.name, player.name, "profile")))
        sampled_targets = _normalize_minutes(active, overrides)
        for player in active:
            player.mpg = sampled_targets[player.name]
            row = next(row for row in profiles if row["player"] == player.name)
            row["sampled_mpg_after_team_normalization"] = round(player.mpg, 6)
    else:
        for player in active:
            baseline = {field_name: float(getattr(player, field_name)) for field_name in PROFILE_FIELDS}
            profiles.append({"player": player.name, "profile_seed": None, **{f"baseline_{name}": value for name, value in baseline.items()}, **{f"sampled_{name}": value for name, value in baseline.items()}})
    for row in profiles:
        row.update({"team": team.name, "excluded": False, "starter": row["player"] in team.expected_starters})
    for player in original_roster:
        if player.name in excluded:
            profiles.append({"team": team.name, "player": player.name, "excluded": True, "starter": False, "profile_seed": None})
    return profiles, {
        "team": team.name,
        "available_players": len(active),
        "excluded_players": sorted(excluded),
        "starters": list(team.expected_starters),
        "minute_target_total": round(sum(player.mpg for player in active), 6),
        "baseline_roster_defense": round(team.baseline_roster_defense, 6),
        "active_roster_defense": round(team.active_roster_defense, 6),
    }


def prepare_game(home: Any, away: Any, context_value: Optional[GameContext | Mapping[str, Any]], season_state: Optional[SeasonState], seed: int) -> Dict[str, Any]:
    """Apply pregame assumptions in place and return the complete input audit.

    The game runner supplies isolated team copies. This function may change
    active rosters, starters, minutes, sampled profiles, and matchup efficiency
    for that game without mutating the caller's baseline teams.
    """

    context = normalize_game_context(context_value)
    variability, variability_metadata = _load_variability(context.variability_path) if context.profile_mode in {"historical", "blended"} else ({}, {})
    environment = _sample_environment(context, seed)
    player_profiles: List[Dict[str, Any]] = []
    team_profiles: List[Dict[str, Any]] = []
    for team in (home, away):
        state = season_state.team(team.name) if season_state else None
        rows, team_row = _prepare_team(team, context, state, variability, seed)
        player_profiles.extend(rows)
        team_profiles.append(team_row)
    if context.enable_matchup_adjustments:
        home_bonus = _clamp(context.home_court_points / 100.0 * 0.42, -0.02, 0.02)
        home_availability = _clamp((away.baseline_roster_defense - away.active_roster_defense) * 0.008, -0.025, 0.025)
        away_availability = _clamp((home.baseline_roster_defense - home.active_roster_defense) * 0.008, -0.025, 0.025)
        for player in home.roster:
            player.two_pct = _clamp(player.two_pct + home_bonus + home_availability, 0.30, 0.80)
            player.three_pct = _clamp(player.three_pct + home_bonus * 0.75 + home_availability, 0.18, 0.60)
        for player in away.roster:
            player.two_pct = _clamp(player.two_pct + away_availability, 0.30, 0.80)
            player.three_pct = _clamp(player.three_pct + away_availability, 0.18, 0.60)
        matchup = {
            home.name: {"home_court_efficiency_bonus": round(home_bonus, 6), "opponent_availability_efficiency_bonus": round(home_availability, 6)},
            away.name: {"home_court_efficiency_bonus": 0.0, "opponent_availability_efficiency_bonus": round(away_availability, 6)},
        }
    else:
        matchup = {home.name: {}, away.name: {}}
    pregame_team_context = {
        "enabled": bool(context.enable_pregame_team_context),
        "pace_multiplier": 1.0,
        "home_efficiency_adjustment": 0.0,
        "away_efficiency_adjustment": 0.0,
    }
    if context.enable_pregame_team_context:
        league_pace = float(context.league_pace or 99.0)
        league_ortg = float(context.league_offensive_rating or 114.0)
        expected_pace = float(context.expected_pace or league_pace)
        pace_multiplier = _clamp(expected_pace / max(1.0, league_pace), 0.92, 1.08)
        home_adjustment = _clamp((float(context.home_expected_offensive_rating or league_ortg) - league_ortg) / 500.0, -0.03, 0.03)
        away_adjustment = _clamp((float(context.away_expected_offensive_rating or league_ortg) - league_ortg) / 500.0, -0.03, 0.03)
        for player in home.roster:
            player.two_pct = _clamp(player.two_pct + home_adjustment, 0.30, 0.80)
            player.three_pct = _clamp(player.three_pct + home_adjustment * 0.75, 0.18, 0.60)
        for player in away.roster:
            player.two_pct = _clamp(player.two_pct + away_adjustment, 0.30, 0.80)
            player.three_pct = _clamp(player.three_pct + away_adjustment * 0.75, 0.18, 0.60)
        pregame_team_context = {
            "enabled": True,
            "expected_pace": round(expected_pace, 6),
            "league_pace": round(league_pace, 6),
            "pace_multiplier": round(pace_multiplier, 6),
            "league_offensive_rating": round(league_ortg, 6),
            "home_expected_offensive_rating": context.home_expected_offensive_rating,
            "away_expected_offensive_rating": context.away_expected_offensive_rating,
            "home_efficiency_adjustment": round(home_adjustment, 6),
            "away_efficiency_adjustment": round(away_adjustment, 6),
            "method": "Transparent rolling pregame pace ratio and expected-rating difference; no fitted model.",
        }
    rest_data = ((home, context.home_rest_days, context.home_travel_miles), (away, context.away_rest_days, context.away_travel_miles))
    for team, rest_days, travel_miles in rest_data:
        workload = max(0.0, 1 - rest_days) * 0.12 + min(0.10, max(0.0, travel_miles) / 12_000)
        for player in team.roster:
            player.fatigue = _clamp(player.fatigue + workload * (1.15 - player.stamina), 0.0, 1.5)
    return {
        "context": game_context_to_dict(context),
        "dataset_metadata": variability_metadata,
        "environment": environment,
        "team_profiles": team_profiles,
        "player_profiles": player_profiles,
        "matchup_adjustments": matchup,
        "pregame_team_context": pregame_team_context,
        "scenario_seed": seed,
    }
