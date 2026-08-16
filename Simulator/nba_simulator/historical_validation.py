"""Distribution-based validation helpers for historical NBA games.

Front Matter
------------
Project: NBA Simulator
File type: Python module
Status: Active
Last updated: 2026-08-01

Purpose: compare an observed game with a Monte Carlo distribution using ranks,
coverage, winner probability, margin, total, and optional player statistics.
Usage: pass a completed matchup batch to
``validate_historical_game_distribution``; no files are read or written.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence


def _percentile_rank(values: Sequence[float], actual: float) -> float:
    if not values:
        return 0.0
    below = sum(value < actual for value in values)
    equal = sum(value == actual for value in values)
    return round((below + 0.5 * equal) / len(values), 4)


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


def validate_historical_game_distribution(
    batch: Mapping[str, Any],
    actual_score: Mapping[str, int],
    actual_player_stats: Optional[Mapping[str, Mapping[str, float]]] = None,
) -> Dict[str, Any]:
    """Compare one real outcome with a batch of simulated outcomes.

    The real result is evaluated as a percentile of the simulated distribution;
    exact-score matching is deliberately not treated as the objective.
    """
    games = list(batch.get("results", []))
    if not games:
        raise ValueError("batch must contain at least one result")
    teams = list(actual_score)
    if len(teams) != 2:
        raise ValueError("actual_score must contain exactly two teams")
    for team in teams:
        if team not in games[0]["final_score"]:
            raise KeyError(f"{team} is missing from simulated final scores")
    score_rows: Dict[str, Any] = {}
    for team in teams:
        values = [game["final_score"][team] for game in games]
        score_rows[team] = {
            "actual": actual_score[team],
            "percentile": _percentile_rank(values, actual_score[team]),
            "simulated_mean": round(sum(values) / len(values), 3),
            "p05": _quantile(values, 0.05),
            "p25": _quantile(values, 0.25),
            "p50": _quantile(values, 0.50),
            "p75": _quantile(values, 0.75),
            "p95": _quantile(values, 0.95),
        }
    first, second = teams
    margins = [game["final_score"][first] - game["final_score"][second] for game in games]
    totals = [game["final_score"][first] + game["final_score"][second] for game in games]
    actual_margin = actual_score[first] - actual_score[second]
    actual_total = actual_score[first] + actual_score[second]
    actual_winner = first if actual_margin > 0 else second
    winner_probability = sum(game["winner"] == actual_winner for game in games) / len(games)
    player_rows = []
    if actual_player_stats:
        simulated_by_player: Dict[str, Dict[str, list]] = {}
        for game in games:
            for side in ("home", "away"):
                for player in game[side].roster:
                    fields = simulated_by_player.setdefault(player.name, {})
                    for stat, value in player.stats.items():
                        if isinstance(value, (int, float)):
                            fields.setdefault(stat, []).append(float(value))
        for player, actual_stats in actual_player_stats.items():
            for stat, actual in actual_stats.items():
                values = simulated_by_player.get(player, {}).get(stat, [])
                player_rows.append({
                    "player": player,
                    "stat": stat,
                    "actual": actual,
                    "simulated_observations": len(values),
                    "percentile": _percentile_rank(values, float(actual)) if values else None,
                    "simulated_mean": round(sum(values) / len(values), 3) if values else None,
                    "p05": _quantile(values, 0.05) if values else None,
                    "p50": _quantile(values, 0.50) if values else None,
                    "p95": _quantile(values, 0.95) if values else None,
                })
    return {
        "simulations": len(games),
        "actual_winner": actual_winner,
        "actual_winner_simulated_probability": round(winner_probability, 4),
        "team_scores": score_rows,
        "margin": {
            "perspective_team": first,
            "actual": actual_margin,
            "percentile": _percentile_rank(margins, actual_margin),
            "p05": _quantile(margins, 0.05),
            "p50": _quantile(margins, 0.50),
            "p95": _quantile(margins, 0.95),
        },
        "total_points": {
            "actual": actual_total,
            "percentile": _percentile_rank(totals, actual_total),
            "p05": _quantile(totals, 0.05),
            "p50": _quantile(totals, 0.50),
            "p95": _quantile(totals, 0.95),
        },
        "player_stats": player_rows,
        "interpretation": "Evaluate calibration and coverage across many historical games; one real outcome need not equal the simulated mean.",
    }
