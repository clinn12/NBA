"""Convert one dated pregame record into simulator teams and game context.

Front Matter
------------
Project: NBA Simulator
File type: Python module
Status: Active
Last updated: 2026-08-01

Purpose: adapt the time-valid pregame dataset schema to the canonical simulator
without placing retrieval or feature-building logic inside the engine.
Usage: backtests call ``build_pregame_team`` for each side and
``build_pregame_context`` once per dated game record.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping


def infer_role(overrides: Mapping[str, float]) -> str:
    """Infer a coarse simulator role from pregame assist, block, and rebound rates."""

    if float(overrides.get("blk_rate", 0.0)) >= 0.025 or float(overrides.get("drb_rate", 0.0)) >= 0.18:
        return "big"
    if float(overrides.get("ast_rate", 0.0)) >= 0.24:
        return "pg"
    if float(overrides.get("orb_rate", 0.0)) >= 0.06:
        return "forward"
    if float(overrides.get("ast_rate", 0.0)) >= 0.17:
        return "guard"
    return "wing"


def build_pregame_team(game: Mapping[str, Any], abbreviation: str, create_team: Callable[..., Any]) -> Any:
    """Build one simulator team from a dated record's expected pregame rotation."""

    profile = game["pregame"]["teams"][abbreviation]
    players = profile.get("players", [])
    if len(players) < 5:
        raise ValueError(f"{game['game_id']} {abbreviation} has fewer than five pregame players")
    roster_specs = []
    for player in players:
        overrides = dict(player["overrides"])
        roster_specs.append((player["player"], infer_role(overrides), overrides))
    team = create_team(profile["team_name"], roster_specs)
    team.dataset_metadata = {
        "dataset_id": "pregame_profiles_v1",
        "source_type": "historical_pregame_calculated",
        "default_simulator_input": False,
        "game_id": game["game_id"],
        "features_cutoff": game["evaluation_labels"]["features_cutoff"],
    }
    return team


def build_pregame_context(game: Mapping[str, Any]) -> Dict[str, Any]:
    """Translate dated team/rest/expected-total features into game-context data."""

    home_abbr, away_abbr = game["home_team"], game["away_team"]
    home = game["pregame"]["teams"][home_abbr]
    away = game["pregame"]["teams"][away_abbr]
    league = game["pregame"]["league_context"]
    expected = game["pregame"]["expected_game"]
    return {
        "game_id": game["game_id"],
        "dataset_id": "pregame_profiles_v1",
        "source_type": "historical_pregame_calculated",
        "profile_mode": "baseline",
        "starters": {home["team_name"]: list(home["expected_starters"]), away["team_name"]: list(away["expected_starters"])},
        "rotation_size": {home["team_name"]: int(home["expected_rotation_size"]), away["team_name"]: int(away["expected_rotation_size"])},
        "home_rest_days": int(home["rest_days"]), "away_rest_days": int(away["rest_days"]),
        "home_travel_miles": float(home.get("travel_miles", 0.0)), "away_travel_miles": float(away.get("travel_miles", 0.0)),
        "home_court_points": 0.0,
        "enable_profile_sampling": False,
        "enable_shared_environment": True,
        "enable_matchup_adjustments": False,
        "enable_pregame_team_context": True,
        "expected_pace": expected["pace"], "league_pace": league["pace"],
        "home_expected_offensive_rating": expected["home_offensive_rating"],
        "away_expected_offensive_rating": expected["away_offensive_rating"],
        "league_offensive_rating": league["offensive_rating"],
        "metadata": {
            "evaluation_mode": "predictive_backtest", "features_cutoff": game["evaluation_labels"]["features_cutoff"],
            "availability_source": "rolling_prior_appearances_not_official_injury_report",
            "expected_total": expected["expected_total"],
        },
    }
