"""Historical-game Monte Carlo calibration, ablation, and acceptance harness.

Front Matter
------------
Project: NBA Simulator
File type: Python script
Status: Active
Last updated: 2026-08-14

Purpose: compare simulator variants against governed targets while retaining raw
draws, player coverage, structural failures, seeds, and pass/fail decisions.
Usage: run ``python scripts/run_calibration.py`` with a calibration dataset and
plan; predictive mode rejects records labeled with look-ahead information.
"""

from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
from typing import Any, Dict, Iterable, List, Mapping, Sequence

try:
    from ._project_paths import PROJECT_ROOT, PUBLISHED_DATA_ROOT
except ImportError:  # Direct execution
    from _project_paths import PROJECT_ROOT, PUBLISHED_DATA_ROOT
from nba_simulator.real_team_loader import build_real_team, load_real_team_payload
from scripts.run_simulation import load_simulator


DEFAULT_GAMES = PUBLISHED_DATA_ROOT / "calibration/pilot_games_2025-26_regular_season.json"
DEFAULT_TEAMS = PUBLISHED_DATA_ROOT / "real_teams_2025-26_regular_season.json"
DEFAULT_PLAN = PROJECT_ROOT / "configs/calibration_plan.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/calibration"
ACTUAL_TO_SIM = {"FG3M": "3PM", "FG3A": "3PA", "OREB": "ORB", "DREB": "DRB", "REB": "TRB"}
PLAYER_CALIBRATION_FIELDS = ("MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M", "FG3A", "FTA")


def _mean(values: Iterable[float]) -> float:
    observed = list(values)
    return statistics.fmean(observed) if observed else 0.0


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _normalized_stats(stats: Mapping[str, Any], simulated: bool) -> Dict[str, float]:
    result: Dict[str, float] = {}
    fields = ("FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "PTS")
    for field in fields:
        key = ACTUAL_TO_SIM.get(field, field) if simulated else field
        result[field] = float(stats.get(key, 0.0))
    result["POSS"] = float(stats.get("POSS", 0.0)) if simulated else result["FGA"] + 0.44 * result["FTA"] - result["OREB"] + result["TOV"]
    return result


def _team_metrics(team: Mapping[str, float], opponent: Mapping[str, float]) -> Dict[str, float]:
    two_attempts_against = max(1.0, opponent["FGA"] - opponent["FG3A"])
    return {
        "pace": team["POSS"],
        "offensive_rating": 100 * _safe_ratio(team["PTS"], team["POSS"]),
        "effective_fg_pct": _safe_ratio(team["FGM"] + 0.5 * team["FG3M"], team["FGA"]),
        "three_attempt_rate": _safe_ratio(team["FG3A"], team["FGA"]),
        "free_throw_rate": _safe_ratio(team["FTA"], team["FGA"]),
        "turnover_pct": 100 * _safe_ratio(team["TOV"], team["FGA"] + 0.44 * team["FTA"] + team["TOV"]),
        "offensive_rebound_pct": 100 * _safe_ratio(team["OREB"], team["OREB"] + opponent["DREB"]),
        "assist_rate": _safe_ratio(team["AST"], team["FGM"]),
        "block_rate": _safe_ratio(team["BLK"], two_attempts_against),
        "steal_rate": _safe_ratio(team["STL"], opponent["POSS"]),
    }


def _structural_failures(game: Mapping[str, Any]) -> List[str]:
    failures: List[str] = []
    for side in ("home", "away"):
        team = game[side]
        if int(round(team.team_stats.get("PTS", 0))) != int(game["final_score"][team.name]):
            failures.append(f"{team.name}: final score differs from team PTS")
        expected_minutes = 240 + 25 * max(0, int(game.get("periods", 4)) - 4)
        player_minutes = sum(float(player.stats.get("MIN", 0.0)) for player in team.roster)
        if abs(player_minutes - expected_minutes) > 0.02:
            failures.append(f"{team.name}: player minutes {player_minutes:.3f} != {expected_minutes}")
        if sum(bool(player.disqualified) for player in team.roster) > 5:
            failures.append(f"{team.name}: more than five disqualifications")
        for field in ("FGM", "FGA", "3PM", "3PA", "FTM", "FTA", "ORB", "DRB", "TRB", "AST", "STL", "BLK", "TOV", "PF", "PTS"):
            player_total = sum(float(player.stats.get(field, 0.0)) for player in team.roster)
            if abs(player_total - float(team.team_stats.get(field, 0.0))) > 0.02:
                failures.append(f"{team.name}: {field} player/team mismatch")
    return failures


def _context(game: Mapping[str, Any], team_objects: Mapping[str, Any], dataset: Mapping[str, Any], variant: Mapping[str, bool], mode: str, variability_path: str) -> Dict[str, Any]:
    if mode == "predictive_backtest" and not game["evaluation_labels"].get("predictive_backtest_eligible"):
        raise ValueError(f"{game['game_id']} is not predictive-backtest eligible because it contains look-ahead inputs")
    context: Dict[str, Any] = {
        "game_id": game["game_id"],
        "dataset_id": dataset.get("metadata", {}).get("dataset_id", "unknown"),
        "source_type": dataset.get("metadata", {}).get("source_type", "historical"),
        "profile_mode": "historical",
        "variability_path": variability_path,
        "home_rest_days": game["teams"][game["home_team"]].get("rest_days") if game["teams"][game["home_team"]].get("rest_days") is not None else 1,
        "away_rest_days": game["teams"][game["away_team"]].get("rest_days") if game["teams"][game["away_team"]].get("rest_days") is not None else 1,
        **variant,
        "metadata": {"evaluation_mode": mode, "lookahead_inputs": game["evaluation_labels"].get("lookahead_inputs", False)},
    }
    if mode == "structural_reconstruction":
        excluded: Dict[str, List[str]] = {}
        starters: Dict[str, List[str]] = {}
        for abbreviation in (game["home_team"], game["away_team"]):
            team = team_objects[abbreviation]
            appeared = set(game["teams"][abbreviation]["players_appeared"])
            available = [player.name for player in team.roster if player.name in appeared]
            if len(available) >= 5:
                excluded[team.name] = [player.name for player in team.roster if player.name not in appeared]
                starters[team.name] = [name for name in game["teams"][abbreviation]["expected_starters_proxy"] if name in available][:5]
        context["excluded_players"] = excluded
        context["starters"] = starters
    return context


def _aggregate_variant(rows: Sequence[Mapping[str, Any]], player_rows: Sequence[Mapping[str, Any]], variant: str, thresholds: Mapping[str, Any], errors: int) -> Dict[str, Any]:
    selected = [row for row in rows if row["variant"] == variant]
    game_groups: Dict[str, List[Mapping[str, Any]]] = {}
    for row in selected:
        game_groups.setdefault(str(row["game_id"]), []).append(row)
    score_errors: List[float] = []
    margin_errors: List[float] = []
    total_errors: List[float] = []
    brier: List[float] = []
    cover90: List[bool] = []
    cover50: List[bool] = []
    metric_actual: Dict[str, List[float]] = {}
    metric_simulated: Dict[str, List[float]] = {}
    structural_failures = sum(int(row["structural_failures"]) for row in selected)
    for game_rows in game_groups.values():
        for side in ("home", "away"):
            scores = [float(row[f"sim_{side}_score"]) for row in game_rows]
            actual = float(game_rows[0][f"actual_{side}_score"])
            score_errors.append(abs(_mean(scores) - actual))
            cover90.append(_quantile(scores, 0.05) <= actual <= _quantile(scores, 0.95))
            cover50.append(_quantile(scores, 0.25) <= actual <= _quantile(scores, 0.75))
        sim_margins = [float(row["sim_home_score"]) - float(row["sim_away_score"]) for row in game_rows]
        sim_totals = [float(row["sim_home_score"]) + float(row["sim_away_score"]) for row in game_rows]
        actual_margin = float(game_rows[0]["actual_home_score"]) - float(game_rows[0]["actual_away_score"])
        actual_total = float(game_rows[0]["actual_home_score"]) + float(game_rows[0]["actual_away_score"])
        margin_errors.append(abs(_mean(sim_margins) - actual_margin))
        total_errors.append(abs(_mean(sim_totals) - actual_total))
        home_probability = _mean(1.0 if row["sim_winner"] == row["home_team"] else 0.0 for row in game_rows)
        outcome = 1.0 if game_rows[0]["actual_winner"] == game_rows[0]["home_team"] else 0.0
        brier.append((home_probability - outcome) ** 2)
        first = game_rows[0]
        for side in ("home", "away"):
            for metric in thresholds.get("metric_absolute_bias_max", {}):
                metric_actual.setdefault(metric, []).append(float(first[f"actual_{side}_{metric}"]))
                metric_simulated.setdefault(metric, []).append(_mean(float(row[f"sim_{side}_{metric}"]) for row in game_rows))
    metrics = {
        metric: {
            "actual_mean": round(_mean(metric_actual.get(metric, [])), 6),
            "simulated_mean": round(_mean(metric_simulated.get(metric, [])), 6),
            "bias": round(_mean(metric_simulated.get(metric, [])) - _mean(metric_actual.get(metric, [])), 6),
        }
        for metric in thresholds.get("metric_absolute_bias_max", {})
    }
    player_groups: Dict[tuple, List[Mapping[str, Any]]] = {}
    for row in player_rows:
        if row["variant"] == variant:
            player_groups.setdefault((row["game_id"], row["team"], row["player"], row["stat"]), []).append(row)
    player_cover90: List[bool] = []
    player_cover50: List[bool] = []
    player_coverage_by_stat: Dict[str, Dict[str, Any]] = {}
    for (_, _, _, stat), group in player_groups.items():
        actual = float(group[0]["actual"])
        values = [float(row["simulated"]) for row in group]
        covered90 = _quantile(values, 0.05) <= actual <= _quantile(values, 0.95)
        covered50 = _quantile(values, 0.25) <= actual <= _quantile(values, 0.75)
        player_cover90.append(covered90); player_cover50.append(covered50)
        bucket = player_coverage_by_stat.setdefault(stat, {"groups": 0, "p05_p95_covered": 0, "p25_p75_covered": 0})
        bucket["groups"] += 1
        bucket["p05_p95_covered"] += int(covered90)
        bucket["p25_p75_covered"] += int(covered50)
    for bucket in player_coverage_by_stat.values():
        bucket["p05_p95_coverage"] = round(_safe_ratio(bucket.pop("p05_p95_covered"), bucket["groups"]), 6)
        bucket["p25_p75_coverage"] = round(_safe_ratio(bucket.pop("p25_p75_covered"), bucket["groups"]), 6)
    summary = {
        "variant": variant,
        "games": len(game_groups),
        "simulation_rows": len(selected),
        "simulation_error_count": errors,
        "structural_failure_count": structural_failures,
        "team_score_mae": round(_mean(score_errors), 6),
        "margin_mae": round(_mean(margin_errors), 6),
        "total_points_mae": round(_mean(total_errors), 6),
        "winner_brier_score": round(_mean(brier), 6),
        "score_p05_p95_coverage": round(_mean(float(value) for value in cover90), 6),
        "score_p25_p75_coverage": round(_mean(float(value) for value in cover50), 6),
        "player_stat_groups": len(player_groups),
        "player_stat_p05_p95_coverage": round(_mean(float(value) for value in player_cover90), 6),
        "player_stat_p25_p75_coverage": round(_mean(float(value) for value in player_cover50), 6),
        "player_stat_coverage_by_stat": player_coverage_by_stat,
        "metrics": metrics,
    }
    checks: List[Dict[str, Any]] = []
    mappings = {
        "structural_failure_count_max": (summary["structural_failure_count"], "max"),
        "simulation_error_count_max": (summary["simulation_error_count"], "max"),
        "team_score_mae_max": (summary["team_score_mae"], "max"),
        "margin_mae_max": (summary["margin_mae"], "max"),
        "total_points_mae_max": (summary["total_points_mae"], "max"),
        "winner_brier_score_max": (summary["winner_brier_score"], "max"),
        "score_p05_p95_coverage_min": (summary["score_p05_p95_coverage"], "min"),
        "score_p05_p95_coverage_max": (summary["score_p05_p95_coverage"], "max"),
        "score_p25_p75_coverage_min": (summary["score_p25_p75_coverage"], "min"),
        "score_p25_p75_coverage_max": (summary["score_p25_p75_coverage"], "max"),
        "player_stat_p05_p95_coverage_min": (summary["player_stat_p05_p95_coverage"], "min"),
        "player_stat_p05_p95_coverage_max": (summary["player_stat_p05_p95_coverage"], "max"),
        "player_stat_p25_p75_coverage_min": (summary["player_stat_p25_p75_coverage"], "min"),
        "player_stat_p25_p75_coverage_max": (summary["player_stat_p25_p75_coverage"], "max"),
    }
    for name, (observed, direction) in mappings.items():
        threshold = float(thresholds[name])
        passed = observed <= threshold if direction == "max" else observed >= threshold
        checks.append({"check": name, "observed": observed, "threshold": threshold, "pass": passed})
    for metric, maximum in thresholds.get("metric_absolute_bias_max", {}).items():
        observed = abs(float(metrics[metric]["bias"]))
        checks.append({"check": f"{metric}_absolute_bias_max", "observed": observed, "threshold": maximum, "pass": observed <= float(maximum)})
    summary["acceptance_checks"] = checks
    summary["acceptance_status"] = "pass" if checks and all(check["pass"] for check in checks) else "fail"
    return summary


def run_calibration(games_payload: Mapping[str, Any], team_payload: Mapping[str, Any], plan: Mapping[str, Any], simulations_per_game: int, seed: int, variants: Sequence[str], mode: str, max_games: int | None = None, sim_config_overrides: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Run selected variants with common seeds and aggregate governed metrics.

    Predictive mode validates each game's eligibility before simulation. Runtime
    errors and structural failures are retained in the returned report rather
    than silently dropped.
    """

    simulator = load_simulator()
    SimConfig = simulator["SimConfig"]
    allowed_config = set(SimConfig.__dataclass_fields__)
    overrides = dict(sim_config_overrides or {})
    unknown = set(overrides) - allowed_config
    if unknown:
        raise ValueError(f"Unknown SimConfig overrides: {sorted(unknown)}")
    selected_games = list(games_payload.get("games", []))[:max_games]
    rows: List[Dict[str, Any]] = []
    player_rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    team_defs = {team["abbreviation"]: team for team in team_payload["teams"]}
    source_path = Path(str(team_payload.get("_source_path", DEFAULT_TEAMS))).resolve()
    variability_path = str((source_path.parent / "historical_variability_2025-26_regular_season.json").resolve())
    for variant_index, variant_name in enumerate(variants):
        if variant_name not in plan["ablation_variants"]:
            raise KeyError(f"Unknown ablation variant: {variant_name}")
        variant = plan["ablation_variants"][variant_name]
        for game_index, actual_game in enumerate(selected_games):
            home_abbr, away_abbr = actual_game["home_team"], actual_game["away_team"]
            if home_abbr not in team_defs or away_abbr not in team_defs:
                errors.append({"variant": variant_name, "game_id": actual_game["game_id"], "error": "Team missing from simulator dataset"})
                continue
            try:
                home = build_real_team(team_payload, home_abbr, simulator["create_team"])
                away = build_real_team(team_payload, away_abbr, simulator["create_team"])
                team_objects = {home_abbr: home, away_abbr: away}
                context = _context(actual_game, team_objects, team_payload, variant, mode, variability_path)
                game_seed = seed + variant_index * 10_000_000 + game_index * 100_000
                config = SimConfig(seed=game_seed, game_runs=simulations_per_game, **overrides)
                batch = simulator["simulate_game_batch_robust"](home, away, config=config, output_dir=None, game_id=actual_game["game_id"], game_context=context)
                actual_stats = {abbr: _normalized_stats(actual_game["teams"][abbr]["team_box_score"], False) for abbr in (home_abbr, away_abbr)}
                actual_metrics = {
                    home_abbr: _team_metrics(actual_stats[home_abbr], actual_stats[away_abbr]),
                    away_abbr: _team_metrics(actual_stats[away_abbr], actual_stats[home_abbr]),
                }
                for run_index, result in enumerate(batch["results"], start=1):
                    sim_stats = {
                        home_abbr: _normalized_stats(result["home"].team_stats, True),
                        away_abbr: _normalized_stats(result["away"].team_stats, True),
                    }
                    sim_metrics = {
                        home_abbr: _team_metrics(sim_stats[home_abbr], sim_stats[away_abbr]),
                        away_abbr: _team_metrics(sim_stats[away_abbr], sim_stats[home_abbr]),
                    }
                    failures = _structural_failures(result)
                    row: Dict[str, Any] = {
                        "variant": variant_name, "evaluation_mode": mode, "game_id": actual_game["game_id"], "game_date": actual_game["game_date"], "simulation_run": run_index,
                        "home_team": home_abbr, "away_team": away_abbr, "actual_winner": actual_game["winner"],
                        "sim_winner": home_abbr if result["winner"] == result["home"].name else away_abbr,
                        "actual_home_score": actual_game["home_score"], "actual_away_score": actual_game["away_score"],
                        "sim_home_score": result["final_score"][result["home"].name], "sim_away_score": result["final_score"][result["away"].name],
                        "structural_failures": len(failures), "structural_failure_details": " | ".join(failures),
                    }
                    for side, abbr in (("home", home_abbr), ("away", away_abbr)):
                        for metric, value in actual_metrics[abbr].items():
                            row[f"actual_{side}_{metric}"] = round(value, 6)
                        for metric, value in sim_metrics[abbr].items():
                            row[f"sim_{side}_{metric}"] = round(value, 6)
                    rows.append(row)
                    for side, abbr in (("home", home_abbr), ("away", away_abbr)):
                        simulated_players = {player.name: player for player in result[side].roster}
                        for actual_player in actual_game["teams"][abbr].get("players", []):
                            player = simulated_players.get(actual_player["player"])
                            if player is None:
                                continue
                            for stat in PLAYER_CALIBRATION_FIELDS:
                                simulated_key = ACTUAL_TO_SIM.get(stat, stat)
                                player_rows.append({
                                    "variant": variant_name, "evaluation_mode": mode, "game_id": actual_game["game_id"], "game_date": actual_game["game_date"],
                                    "simulation_run": run_index, "team": abbr, "player": actual_player["player"], "stat": stat,
                                    "actual": float(actual_player["stats"].get(stat, 0.0)), "simulated": float(player.stats.get(simulated_key, 0.0)),
                                })
            except Exception as error:
                errors.append({"variant": variant_name, "game_id": actual_game["game_id"], "error": f"{type(error).__name__}: {error}"})
    summaries = [
        _aggregate_variant(rows, player_rows, variant, plan["acceptance_thresholds"], sum(error["variant"] == variant for error in errors))
        for variant in variants
    ]
    return {
        "metadata": {
            "report_version": "historical_calibration_v1", "created_at_utc": datetime.now(timezone.utc).isoformat(), "evaluation_mode": mode,
            "simulations_per_game": simulations_per_game, "seed": seed, "games_requested": len(selected_games), "variants": list(variants),
            "dataset_id": team_payload.get("metadata", {}).get("dataset_id"), "lookahead_inputs": mode == "structural_reconstruction",
        },
        "variant_summaries": summaries,
        "errors": errors,
        "rows": rows,
        "player_rows": player_rows,
        "calibration_stages": plan.get("calibration_stages", []),
        "decision_rule": plan.get("decision_rule"),
    }


def write_outputs(report: Mapping[str, Any], output_root: Path) -> Dict[str, str]:
    """Write dated raw calibration rows, summaries, failures, and JSON report."""

    stamp = datetime.now().strftime("%Y%m%d")
    run_id = datetime.now().strftime("%H%M%S")
    destination = output_root / stamp / f"calibration_{run_id}"
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "calibration_report.json"
    csv_path = destination / "calibration_simulation_rows.csv"
    summary_path = destination / "calibration_variant_summary.csv"
    player_path = destination / "calibration_player_stat_rows.csv"
    serializable = copy.deepcopy(dict(report))
    rows = serializable.pop("rows")
    player_rows = serializable.pop("player_rows")
    json_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    if player_rows:
        with player_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(player_rows[0]))
            writer.writeheader(); writer.writerows(player_rows)
    summary_rows = []
    for summary in report["variant_summaries"]:
        summary_rows.append({key: value for key, value in summary.items() if key not in {"metrics", "acceptance_checks"}})
    if summary_rows:
        with summary_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
            writer.writeheader(); writer.writerows(summary_rows)
    return {"directory": str(destination), "report_json": str(json_path), "simulation_csv": str(csv_path), "player_stat_csv": str(player_path), "summary_csv": str(summary_path)}


def main() -> None:
    """Parse calibration options, run the harness, and print output locations."""

    parser = argparse.ArgumentParser(description="Run historical-game calibration and ablation analysis.")
    parser.add_argument("--games", default=str(DEFAULT_GAMES))
    parser.add_argument("--team-data", default=str(DEFAULT_TEAMS))
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--simulations-per-game", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260731)
    parser.add_argument("--variants", nargs="+", default=["averages_only", "game_form", "full_context"])
    parser.add_argument("--mode", choices=["structural_reconstruction", "predictive_backtest"], default="structural_reconstruction")
    parser.add_argument("--max-games", type=int)
    parser.add_argument("--sim-config", help="Optional JSON object of SimConfig overrides.")
    parser.add_argument("--sim-config-file", help="Optional JSON file of SimConfig overrides; recommended for PowerShell.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    games_payload = json.loads(Path(args.games).read_text(encoding="utf-8"))
    team_payload = load_real_team_payload(args.team_data)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    if args.sim_config and args.sim_config_file:
        parser.error("Use either --sim-config or --sim-config-file, not both")
    overrides = json.loads(Path(args.sim_config_file).read_text(encoding="utf-8")) if args.sim_config_file else (json.loads(args.sim_config) if args.sim_config else {})
    report = run_calibration(games_payload, team_payload, plan, args.simulations_per_game, args.seed, args.variants, args.mode, args.max_games, overrides)
    paths = write_outputs(report, Path(args.output_dir))
    print(json.dumps({"paths": paths, "summaries": [{"variant": row["variant"], "games": row["games"], "status": row["acceptance_status"]} for row in report["variant_summaries"]], "errors": len(report["errors"])}, indent=2))


if __name__ == "__main__":
    main()
