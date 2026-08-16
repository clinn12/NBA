"""Run the frozen, resumable final holdout evaluation for NBA Simulator.

Front Matter
------------
Project: NBA Simulator
File type: Python script
Status: Active
Last updated: 2026-08-14

Purpose: evaluate only the explicitly frozen, previously unexamined holdout games
at high Monte Carlo depth while preserving deterministic seeds, compressed raw
diagnostics, checkpoints, and a single governed acceptance report.
Usage: verify with ``python scripts/run_formal_holdout.py --dry-run`` and then
run without ``--dry-run``. Never change the frozen manifest after outcomes are
observed and never tune simulator settings from the resulting report.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import multiprocessing
from pathlib import Path
from queue import Empty
import statistics
import time
from typing import Any, Dict, Iterable, List, Mapping, Sequence

try:
    from ._project_paths import PROJECT_ROOT
except ImportError:  # Direct execution
    from _project_paths import PROJECT_ROOT

from scripts.run_pregame_backtest import run_backtest


DEFAULT_MANIFEST = PROJECT_ROOT / "configs/formal_holdout_v2.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/formal_holdout_v2"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mean(values: Iterable[float]) -> float:
    observed = list(values)
    return statistics.fmean(observed) if observed else 0.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _game_seed(base_seed: int, original_holdout_index: int) -> int:
    """Return the stable seed used by a monolithic ordered holdout run."""

    return int(base_seed) + int(original_holdout_index) * 100_000


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(dict(payload), indent=2), encoding="utf-8")
    temporary.replace(path)


def _write_gzip_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    with gzip.open(temporary, "wt", newline="", encoding="utf-8") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    temporary.replace(path)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    temporary.replace(path)


def _resolve_project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_and_verify_manifest(path: Path) -> tuple[Dict[str, Any], Dict[str, Path]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = {"dataset", "sim_config", "calibration_plan", "simulator_core", "backtest_harness"}
    artifacts: Dict[str, Path] = {}
    for name in required:
        entry = manifest["artifacts"][name]
        artifact = _resolve_project_path(entry["path"]).resolve()
        if not artifact.is_file():
            raise FileNotFoundError(f"Frozen artifact missing: {artifact}")
        observed = _sha256(artifact)
        if observed.lower() != str(entry["sha256"]).lower():
            raise ValueError(f"Frozen artifact hash mismatch for {name}: {observed}")
        artifacts[name] = artifact
    if int(manifest["simulations_per_game"]) < 500:
        raise ValueError("Formal holdout manifest requires at least 500 simulations per game")
    return manifest, artifacts


def _select_games(payload: Mapping[str, Any], manifest: Mapping[str, Any]) -> List[Dict[str, Any]]:
    holdout = {str(game["game_id"]): game for game in payload["games"] if game["split"] == "holdout"}
    exposed = set(str(game_id) for game_id in manifest["exposed_game_ids"])
    evaluation_ids = [str(game_id) for game_id in manifest["evaluation_game_ids"]]
    if exposed & set(evaluation_ids):
        raise ValueError("Exposed and formal evaluation IDs overlap")
    missing = [game_id for game_id in evaluation_ids if game_id not in holdout]
    if missing:
        raise ValueError(f"Frozen evaluation IDs missing from holdout split: {missing[:5]}")
    if len(exposed) != int(manifest["expected_exposed_games"]):
        raise ValueError("Exposed game count does not match the frozen manifest")
    if len(evaluation_ids) != int(manifest["expected_evaluation_games"]):
        raise ValueError("Evaluation game count does not match the frozen manifest")
    if set(holdout) != exposed | set(evaluation_ids):
        raise ValueError("Frozen exposed/evaluation IDs do not partition the holdout split")
    return [holdout[game_id] for game_id in evaluation_ids]


def _evaluate_game(task: Mapping[str, Any]) -> Dict[str, Any]:
    game = task["game"]
    game_id = str(game["game_id"])
    destination = Path(task["destination"])
    report = run_backtest(
        {"games": [game]}, task["plan"], "holdout",
        int(task["simulations_per_game"]), int(task["seed"]),
        sim_config_overrides=task["sim_config"],
    )
    simulation_path = destination / "simulation_rows.csv.gz"
    player_path = destination / "player_stat_rows.csv.gz"
    _write_gzip_csv(simulation_path, report["simulation_rows"])
    _write_gzip_csv(player_path, report["player_rows"])
    compact = {
        "artifact_hashes": {
            "player_stat_rows.csv.gz": _sha256(player_path),
            "simulation_rows.csv.gz": _sha256(simulation_path),
        },
        "completed_at_utc": _utc_now(),
        "errors": report["errors"],
        "forecast": report["forecast_rows"][0] if report["forecast_rows"] else None,
        "game_id": game_id,
        "manifest_id": task["manifest_id"],
        "seed": int(task["seed"]),
        "segments": report["segments"],
        "simulations_per_game": int(task["simulations_per_game"]),
        "summary": report["summary"],
    }
    result_path = destination / "result.json"
    _atomic_json(result_path, compact)
    return {"game_id": game_id, "result_path": str(result_path)}


def _worker_entry(task: Mapping[str, Any], result_queue: Any) -> None:
    """Run one isolated game and return only its compact completion status."""

    try:
        result_queue.put({"status": "success", **_evaluate_game(task)})
    except Exception as error:
        result_queue.put({
            "status": "failure", "game_id": str(task["game"]["game_id"]),
            "error": f"{type(error).__name__}: {error}",
        })


def _weighted(rows: Sequence[Mapping[str, Any]], field: str, weight: str = "games") -> float:
    numerator = sum(float(row[field]) * int(row[weight]) for row in rows)
    denominator = sum(int(row[weight]) for row in rows)
    return numerator / denominator if denominator else 0.0


def _acceptance_checks(summary: Dict[str, Any], thresholds: Mapping[str, Any]) -> None:
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
    checks = []
    for name, (observed, direction) in mappings.items():
        threshold = float(thresholds[name])
        passed = observed <= threshold if direction == "max" else observed >= threshold
        checks.append({"check": name, "observed": observed, "threshold": threshold, "pass": passed})
    for metric, maximum in thresholds.get("metric_absolute_bias_max", {}).items():
        observed = abs(float(summary["metrics"][metric]["bias"]))
        checks.append({"check": f"{metric}_absolute_bias_max", "observed": observed, "threshold": maximum, "pass": observed <= float(maximum)})
    summary["acceptance_checks"] = checks
    summary["acceptance_status"] = "pass" if checks and all(check["pass"] for check in checks) else "fail"


def _aggregate_results(results: Sequence[Mapping[str, Any]], thresholds: Mapping[str, Any]) -> Dict[str, Any]:
    summaries = [result["summary"] for result in results]
    games = sum(int(summary["games"]) for summary in summaries)
    summary: Dict[str, Any] = {
        "variant": "pregame_context",
        "games": games,
        "simulation_rows": sum(int(row["simulation_rows"]) for row in summaries),
        "simulation_error_count": sum(int(row["simulation_error_count"]) for row in summaries),
        "structural_failure_count": sum(int(row["structural_failure_count"]) for row in summaries),
    }
    for field in (
        "team_score_mae", "margin_mae", "total_points_mae", "winner_brier_score",
        "score_p05_p95_coverage", "score_p25_p75_coverage",
    ):
        summary[field] = round(_weighted(summaries, field), 6)
    player_groups = sum(int(row["player_stat_groups"]) for row in summaries)
    summary["player_stat_groups"] = player_groups
    for field in ("player_stat_p05_p95_coverage", "player_stat_p25_p75_coverage"):
        numerator = sum(float(row[field]) * int(row["player_stat_groups"]) for row in summaries)
        summary[field] = round(numerator / player_groups if player_groups else 0.0, 6)
    by_stat: Dict[str, Dict[str, float]] = {}
    for source in summaries:
        for stat, bucket in source["player_stat_coverage_by_stat"].items():
            target = by_stat.setdefault(stat, {"groups": 0, "cover90": 0.0, "cover50": 0.0})
            groups = int(bucket["groups"])
            target["groups"] += groups
            target["cover90"] += float(bucket["p05_p95_coverage"]) * groups
            target["cover50"] += float(bucket["p25_p75_coverage"]) * groups
    summary["player_stat_coverage_by_stat"] = {
        stat: {
            "groups": int(bucket["groups"]),
            "p05_p95_coverage": round(bucket["cover90"] / bucket["groups"], 6),
            "p25_p75_coverage": round(bucket["cover50"] / bucket["groups"], 6),
        }
        for stat, bucket in sorted(by_stat.items())
    }
    summary["metrics"] = {}
    for metric in thresholds.get("metric_absolute_bias_max", {}):
        actual = _mean(float(row["metrics"][metric]["actual_mean"]) for row in summaries)
        simulated = _mean(float(row["metrics"][metric]["simulated_mean"]) for row in summaries)
        summary["metrics"][metric] = {
            "actual_mean": round(actual, 6),
            "simulated_mean": round(simulated, 6),
            "bias": round(simulated - actual, 6),
        }
    _acceptance_checks(summary, thresholds)
    return summary


def _aggregate_segments(results: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple[str, str], List[Mapping[str, Any]]] = {}
    for result in results:
        for segment in result["segments"]:
            grouped.setdefault((str(segment["segment"]), str(segment["value"])), []).append(segment)
    output = []
    for (name, value), rows in sorted(grouped.items()):
        output.append({
            "segment": name, "value": value,
            "games": sum(int(row["games"]) for row in rows),
            "team_score_mae": round(_weighted(rows, "team_score_mae"), 6),
            "margin_mae": round(_weighted(rows, "margin_mae"), 6),
            "total_mae": round(_weighted(rows, "total_mae"), 6),
            "winner_brier": round(_weighted(rows, "winner_brier"), 6),
        })
    return output


def _completed_results(output: Path, game_ids: Sequence[str], manifest_id: str) -> Dict[str, Dict[str, Any]]:
    completed = {}
    for game_id in game_ids:
        path = output / "games" / game_id / "result.json"
        if not path.is_file():
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("manifest_id") != manifest_id:
            raise ValueError(f"Completed result uses another manifest: {path}")
        completed[game_id] = result
    return completed


def main() -> None:
    """Verify the freeze, resume pending games, and write formal acceptance outputs."""

    parser = argparse.ArgumentParser(description="Run the frozen resumable v2 holdout evaluation.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--game-timeout-seconds", type=float, default=300.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    manifest_path = Path(args.manifest).resolve()
    output = Path(args.output_dir).resolve()
    manifest, artifacts = _load_and_verify_manifest(manifest_path)
    manifest_id = str(manifest["manifest_id"])
    payload = json.loads(artifacts["dataset"].read_text(encoding="utf-8"))
    games = _select_games(payload, manifest)
    game_ids = [str(game["game_id"]) for game in games]
    completed = _completed_results(output, game_ids, manifest_id) if output.exists() else {}
    state_path = output / "progress.json"
    prior_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    if prior_state and prior_state.get("manifest_id") != manifest_id:
        raise ValueError("Progress checkpoint belongs to another frozen manifest")
    failures: Dict[str, str] = dict(prior_state.get("failures", {}))
    pending = [
        game for game in games
        if str(game["game_id"]) not in completed and str(game["game_id"]) not in failures
    ]
    preview = {
        "manifest_id": manifest_id,
        "evaluation_games": len(games),
        "completed_games": len(completed),
        "failed_games": len(failures),
        "pending_games": len(pending),
        "simulations_per_game": int(manifest["simulations_per_game"]),
        "total_planned_simulations": len(games) * int(manifest["simulations_per_game"]),
        "workers": args.workers,
        "game_timeout_seconds": args.game_timeout_seconds,
    }
    print(json.dumps(preview, indent=2), flush=True)
    if args.dry_run:
        return
    if args.workers < 1 or args.game_timeout_seconds <= 0:
        parser.error("--workers and --game-timeout-seconds must be positive")

    output.mkdir(parents=True, exist_ok=True)
    run_manifest_path = output / "run_manifest.json"
    run_manifest = {
        "frozen_manifest": str(manifest_path),
        "frozen_manifest_sha256": _sha256(manifest_path),
        "manifest_id": manifest_id,
        "runner": str(Path(__file__).resolve()),
        "runner_sha256": _sha256(Path(__file__).resolve()),
        "started_at_utc": _utc_now(),
    }
    if run_manifest_path.exists():
        existing = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        if existing["frozen_manifest_sha256"] != run_manifest["frozen_manifest_sha256"]:
            raise ValueError("Output directory belongs to a different frozen manifest")
        history = list(existing.get("runner_history", []))
        if not any(row.get("runner_sha256") == run_manifest["runner_sha256"] for row in history):
            history.append({
                "activated_at_utc": _utc_now(),
                "note": "Resume orchestration version; frozen simulation artifacts unchanged.",
                "runner_sha256": run_manifest["runner_sha256"],
            })
            existing["runner_history"] = history
            existing["runner"] = run_manifest["runner"]
            existing["runner_sha256"] = run_manifest["runner_sha256"]
            _atomic_json(run_manifest_path, existing)
    else:
        run_manifest["runner_history"] = [{
            "activated_at_utc": run_manifest["started_at_utc"],
            "note": "Initial formal runner.",
            "runner_sha256": run_manifest["runner_sha256"],
        }]
        _atomic_json(run_manifest_path, run_manifest)

    plan = json.loads(artifacts["calibration_plan"].read_text(encoding="utf-8"))
    sim_config = json.loads(artifacts["sim_config"].read_text(encoding="utf-8"))
    original_index = {game_id: index for index, game_id in enumerate(
        str(game["game_id"]) for game in payload["games"] if game["split"] == "holdout"
    )}
    tasks = []
    for game in pending:
        game_id = str(game["game_id"])
        tasks.append({
            "destination": str(output / "games" / game_id),
            "game": game,
            "manifest_id": manifest_id,
            "plan": plan,
            "seed": _game_seed(int(manifest["base_seed"]), original_index[game_id]),
            "sim_config": sim_config,
            "simulations_per_game": int(manifest["simulations_per_game"]),
        })
    if tasks:
        # A fresh process per game lets the parent terminate a pathological
        # simulation without changing the frozen engine or losing other games.
        context = multiprocessing.get_context("spawn")
        queued = list(tasks)
        active: Dict[str, Dict[str, Any]] = {}
        while queued or active:
            while queued and len(active) < args.workers:
                task = queued.pop(0)
                game_id = str(task["game"]["game_id"])
                result_queue = context.Queue()
                process = context.Process(target=_worker_entry, args=(task, result_queue))
                process.start()
                active[game_id] = {
                    "process": process, "queue": result_queue,
                    "started": time.monotonic(),
                }
            any_changed = False
            for game_id, worker in list(active.items()):
                process = worker["process"]
                message = None
                worker_changed = False
                try:
                    message = worker["queue"].get_nowait()
                except Empty:
                    pass
                if message is not None:
                    process.join(timeout=5)
                    if message["status"] == "success":
                        completed[game_id] = json.loads((output / "games" / game_id / "result.json").read_text(encoding="utf-8"))
                    else:
                        failures[game_id] = str(message["error"])
                    del active[game_id]
                    worker_changed = any_changed = True
                elif time.monotonic() - float(worker["started"]) > args.game_timeout_seconds:
                    process.terminate()
                    process.join(timeout=10)
                    failures[game_id] = f"TimeoutError: exceeded {args.game_timeout_seconds} seconds"
                    del active[game_id]
                    worker_changed = any_changed = True
                elif not process.is_alive():
                    process.join(timeout=5)
                    failures[game_id] = f"WorkerExitError: exit code {process.exitcode} without result"
                    del active[game_id]
                    worker_changed = any_changed = True
                if not worker_changed:
                    continue
                _atomic_json(state_path, {
                    "completed_game_ids": [game for game in game_ids if game in completed],
                    "failures": failures,
                    "manifest_id": manifest_id,
                    "updated_at_utc": _utc_now(),
                })
                print(f"completed={len(completed)}/{len(game_ids)} failures={len(failures)} game={game_id}", flush=True)
            if not any_changed:
                time.sleep(0.25)

    ordered_results = [completed[game_id] for game_id in game_ids if game_id in completed]
    summary = _aggregate_results(ordered_results, plan["acceptance_thresholds"])
    summary["simulation_error_count"] += len(failures)
    summary["expected_games"] = len(game_ids)
    summary["missing_or_failed_games"] = len(game_ids) - len(ordered_results)
    _acceptance_checks(summary, plan["acceptance_thresholds"])
    segments = _aggregate_segments(ordered_results)
    forecasts = [result["forecast"] for result in ordered_results if result.get("forecast")]
    final_report = {
        "metadata": {
            "completed_at_utc": _utc_now(),
            "evaluation_game_ids": game_ids,
            "features_time_valid": True,
            "formal_holdout": True,
            "failed_games": failures,
            "manifest_id": manifest_id,
            "simulations_per_game": int(manifest["simulations_per_game"]),
            "tuning_from_results_prohibited": True,
        },
        "summary": summary,
        "segments": segments,
    }
    _atomic_json(output / "formal_holdout_report.json", final_report)
    _write_csv(output / "formal_holdout_game_results.csv", forecasts)
    _write_csv(output / "formal_holdout_segments.csv", segments)
    print(json.dumps({"status": summary["acceptance_status"], "summary": summary}, indent=2), flush=True)


if __name__ == "__main__":
    main()
