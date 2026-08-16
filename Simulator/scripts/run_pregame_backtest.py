"""Run a strictly time-valid historical backtest from dated pregame profiles.

Front Matter
------------
Project: NBA Simulator
File type: Python script
Status: Active
Last updated: 2026-08-14

Purpose: evaluate frozen simulator settings on chronological game records and
produce game, player, segment, structural, probability, and coverage diagnostics.
Usage: run ``python scripts/run_pregame_backtest.py`` and select a split. Holdout
results are evaluation-only and must not be used for parameter selection.
"""

from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
from typing import Any, Dict, Iterable, List, Mapping, Sequence

try:
    from ._project_paths import PROJECT_ROOT, PUBLISHED_DATA_ROOT
except ImportError:  # Direct execution
    from _project_paths import PROJECT_ROOT, PUBLISHED_DATA_ROOT
from nba_simulator.pregame_profile_loader import build_pregame_context, build_pregame_team
from scripts.run_calibration import ACTUAL_TO_SIM, PLAYER_CALIBRATION_FIELDS, _aggregate_variant, _normalized_stats, _structural_failures, _team_metrics
from scripts.run_simulation import load_simulator


DEFAULT_INPUT = PUBLISHED_DATA_ROOT / "pregame/pregame_profiles_2025-26_regular_season.json"
DEFAULT_PLAN = PROJECT_ROOT / "configs/calibration_plan.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/pregame_backtest"


def _mean(values: Iterable[float]) -> float:
    observed = list(values)
    return statistics.fmean(observed) if observed else 0.0


def _segment_summary(games: Sequence[Mapping[str, Any]], key: str) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Mapping[str, Any]]] = {}
    for game in games:
        grouped.setdefault(str(game[key]), []).append(game)
    return [{
        "segment": key, "value": value, "games": len(rows),
        "team_score_mae": round(_mean([abs(row["mean_home_score"] - row["actual_home_score"]) for row in rows] + [abs(row["mean_away_score"] - row["actual_away_score"]) for row in rows]), 6),
        "margin_mae": round(_mean(abs(row["mean_margin"] - row["actual_margin"]) for row in rows), 6),
        "total_mae": round(_mean(abs(row["mean_total"] - row["actual_total"]) for row in rows), 6),
        "winner_brier": round(_mean((row["home_win_probability"] - row["home_win_actual"]) ** 2 for row in rows), 6),
    } for value, rows in sorted(grouped.items())]


def _forecast_summaries(rows: Sequence[Mapping[str, Any]], source_games: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["game_id"]), []).append(row)
    result = []
    for game_id, simulations in grouped.items():
        source = source_games[game_id]
        home_score, away_score = source["actual"]["home_score"], source["actual"]["away_score"]
        expected_total = source["pregame"]["expected_game"]["expected_total"]
        home_rest = source["pregame"]["teams"][source["home_team"]]["rest_days"]
        away_rest = source["pregame"]["teams"][source["away_team"]]["rest_days"]
        mean_home = _mean(float(row["sim_home_score"]) for row in simulations)
        mean_away = _mean(float(row["sim_away_score"]) for row in simulations)
        home_probability = _mean(1.0 if row["sim_winner"] == source["home_team"] else 0.0 for row in simulations)
        result.append({
            "game_id": game_id, "game_date": source["game_date"], "split": source["split"], "month": source["game_date"][:7],
            "home_team": source["home_team"], "away_team": source["away_team"], "actual_home_score": home_score, "actual_away_score": away_score,
            "actual_margin": home_score - away_score, "actual_total": home_score + away_score, "mean_home_score": round(mean_home, 5), "mean_away_score": round(mean_away, 5),
            "mean_margin": round(mean_home - mean_away, 5), "mean_total": round(mean_home + mean_away, 5), "home_win_probability": round(home_probability, 6),
            "home_win_actual": int(home_score > away_score), "expected_total": expected_total,
            "expected_total_band": "under_220" if expected_total < 220 else ("220_to_230" if expected_total < 230 else "over_230"),
            "rest_situation": "back_to_back" if min(home_rest, away_rest) == 0 else ("rest_advantage_home" if home_rest > away_rest else ("rest_advantage_away" if away_rest > home_rest else "equal_rest")),
            "projected_favorite": source["home_team"] if source["pregame"]["expected_game"]["home_offensive_rating"] >= source["pregame"]["expected_game"]["away_offensive_rating"] else source["away_team"],
        })
    return result


def run_backtest(
    payload: Mapping[str, Any],
    plan: Mapping[str, Any],
    split: str,
    simulations_per_game: int,
    seed: int,
    max_games: int | None = None,
    sim_config_overrides: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Simulate a chronological dataset split and return predictive diagnostics."""

    simulator = load_simulator(); SimConfig = simulator["SimConfig"]
    overrides = dict(sim_config_overrides or {})
    protected = {"seed", "game_runs", "season_runs", "season_game_runs"}
    invalid = sorted((set(overrides) - set(SimConfig.__dataclass_fields__)) | (set(overrides) & protected))
    if invalid:
        raise ValueError(f"Unsupported or run-controlled SimConfig overrides: {invalid}")
    selected = [game for game in payload["games"] if split == "all" or game["split"] == split]
    if max_games is not None:
        selected = selected[:max_games]
    rows: List[Dict[str, Any]] = []; player_rows: List[Dict[str, Any]] = []; errors: List[Dict[str, Any]] = []
    for game_index, source in enumerate(selected):
        try:
            home_abbr, away_abbr = source["home_team"], source["away_team"]
            home = build_pregame_team(source, home_abbr, simulator["create_team"]); away = build_pregame_team(source, away_abbr, simulator["create_team"])
            config_values = {**overrides, "seed": seed + game_index * 100_000, "game_runs": simulations_per_game}
            batch = simulator["simulate_game_batch_robust"](home, away, config=SimConfig(**config_values), output_dir=None, game_id=source["game_id"], game_context=build_pregame_context(source))
            actual_stats = {abbr: _normalized_stats(source["actual"]["teams"][abbr]["team_box_score"], False) for abbr in (home_abbr, away_abbr)}
            actual_metrics = {home_abbr: _team_metrics(actual_stats[home_abbr], actual_stats[away_abbr]), away_abbr: _team_metrics(actual_stats[away_abbr], actual_stats[home_abbr])}
            for run_index, game in enumerate(batch["results"], start=1):
                sim_stats = {home_abbr: _normalized_stats(game["home"].team_stats, True), away_abbr: _normalized_stats(game["away"].team_stats, True)}
                sim_metrics = {home_abbr: _team_metrics(sim_stats[home_abbr], sim_stats[away_abbr]), away_abbr: _team_metrics(sim_stats[away_abbr], sim_stats[home_abbr])}
                failures = _structural_failures(game)
                row: Dict[str, Any] = {"variant": "pregame_context", "evaluation_mode": "predictive_backtest", "game_id": source["game_id"], "game_date": source["game_date"], "simulation_run": run_index, "home_team": home_abbr, "away_team": away_abbr,
                    "actual_winner": source["actual"]["winner"], "sim_winner": home_abbr if game["winner"] == game["home"].name else away_abbr,
                    "actual_home_score": source["actual"]["home_score"], "actual_away_score": source["actual"]["away_score"], "sim_home_score": game["final_score"][game["home"].name], "sim_away_score": game["final_score"][game["away"].name],
                    "structural_failures": len(failures), "structural_failure_details": " | ".join(failures)}
                for side, abbr in (("home", home_abbr), ("away", away_abbr)):
                    for metric, value in actual_metrics[abbr].items(): row[f"actual_{side}_{metric}"] = round(value, 6)
                    for metric, value in sim_metrics[abbr].items(): row[f"sim_{side}_{metric}"] = round(value, 6)
                rows.append(row)
                simulated_players = {player.name: player for side in ("home", "away") for player in game[side].roster}
                for abbr in (home_abbr, away_abbr):
                    for actual_player in source["actual"]["teams"][abbr]["players"]:
                        player = simulated_players.get(actual_player["PLAYER_NAME"])
                        if not player: continue
                        for stat in PLAYER_CALIBRATION_FIELDS:
                            player_rows.append({"variant": "pregame_context", "game_id": source["game_id"], "team": abbr, "player": actual_player["PLAYER_NAME"], "stat": stat,
                                "actual": float(actual_player.get(stat, 0.0)), "simulated": float(player.stats.get(ACTUAL_TO_SIM.get(stat, stat), 0.0))})
        except Exception as error:
            errors.append({"game_id": source["game_id"], "error": f"{type(error).__name__}: {error}"})
    summary = _aggregate_variant(rows, player_rows, "pregame_context", plan["acceptance_thresholds"], len(errors))
    source_by_id = {game["game_id"]: game for game in selected}; forecasts = _forecast_summaries(rows, source_by_id)
    segments = [row for key in ("month", "expected_total_band", "rest_situation", "projected_favorite") for row in _segment_summary(forecasts, key)]
    return {"metadata": {"report_version": "pregame_backtest_v1", "created_at_utc": datetime.now(timezone.utc).isoformat(), "split": split, "simulations_per_game": simulations_per_game, "seed": seed, "games_requested": len(selected), "features_time_valid": True, "sim_config_overrides": overrides}, "summary": summary, "segments": segments, "errors": errors, "forecast_rows": forecasts, "simulation_rows": rows, "player_rows": player_rows}


def write_outputs(report: Mapping[str, Any], output_root: Path) -> Dict[str, str]:
    """Write a dated backtest report plus raw, forecast, player, and segment CSVs."""

    destination = output_root / datetime.now().strftime("%Y%m%d") / datetime.now().strftime("backtest_%H%M%S"); destination.mkdir(parents=True, exist_ok=True)
    serializable = copy.deepcopy(dict(report)); forecasts = serializable.pop("forecast_rows"); simulations = serializable.pop("simulation_rows"); players = serializable.pop("player_rows")
    report_path = destination / "pregame_backtest_report.json"; report_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    paths = {"directory": str(destination), "report": str(report_path)}
    for name, rows in (("game_forecasts.csv", forecasts), ("simulation_rows.csv", simulations), ("player_stat_rows.csv", players), ("segments.csv", report["segments"])):
        path = destination / name
        if rows:
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        paths[name] = str(path)
    return paths


def main() -> None:
    """Parse backtest options, run the selected split, and print saved paths."""

    parser = argparse.ArgumentParser(description="Run the time-valid pregame historical backtest.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT)); parser.add_argument("--plan", default=str(DEFAULT_PLAN)); parser.add_argument("--split", choices=["calibration", "validation", "holdout", "all"], default="holdout")
    parser.add_argument("--simulations-per-game", type=int, default=500); parser.add_argument("--seed", type=int, default=20260801); parser.add_argument("--max-games", type=int); parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--sim-config-file", help="JSON object containing governed SimConfig overrides for a calibration candidate.")
    args = parser.parse_args(); payload = json.loads(Path(args.input).read_text(encoding="utf-8")); plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    overrides = json.loads(Path(args.sim_config_file).read_text(encoding="utf-8")) if args.sim_config_file else {}
    if not isinstance(overrides, dict):
        parser.error("--sim-config-file must contain a JSON object")
    report = run_backtest(payload, plan, args.split, args.simulations_per_game, args.seed, args.max_games, overrides); paths = write_outputs(report, Path(args.output_dir))
    print(json.dumps({"paths": paths, "games": report["summary"]["games"], "status": report["summary"]["acceptance_status"], "errors": len(report["errors"])}, indent=2))


if __name__ == "__main__":
    main()
