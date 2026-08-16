"""Batch, export, and nested-season orchestration for the possession simulator.

Front Matter
------------
Project: NBA Simulator
File type: Python module
Status: Active
Last updated: 2026-08-01

Purpose: repeat individual matchups or schedules, retain raw draws, summarize
distributions, select unbiased nested results for standings, and write CSVs.
Usage: ``simulator_core`` exposes these functions through its public API; callers
normally use ``simulate_game_batch_robust`` or ``simulate_season_robust``.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
import csv
from datetime import date
import json
from pathlib import Path
import statistics
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
import random


GameRunner = Callable[[Any, Any, Any], Dict[str, Any]]
ScheduleEntry = Tuple[Any, Any]


def _positive_int(value: Optional[int], default: int, field_name: str) -> int:
    resolved = default if value is None else value
    if not isinstance(resolved, int) or resolved < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return resolved


def run_game_batch(
    home: Any,
    away: Any,
    game_runner: GameRunner,
    config: Any,
    game_runs: Optional[int] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Run one matchup repeatedly and retain every detailed game result."""
    runs = _positive_int(game_runs, config.game_runs, "game_runs")
    base_seed = config.seed if seed is None else seed
    base_seed = 0 if base_seed is None else base_seed
    results = []
    home_wins = 0

    for run_index in range(runs):
        game = game_runner(home, away, replace(config, seed=base_seed + run_index))
        results.append(game)
        home_wins += int(game["winner"] == home.name)

    avg_score = {
        home.name: round(sum(game["final_score"][home.name] for game in results) / runs, 1),
        away.name: round(sum(game["final_score"][away.name] for game in results) / runs, 1),
    }
    calib_keys = ("pace_delta", "ortg_delta", "tov_pct_delta", "ftr_delta", "orb_pct_delta")
    avg_calibration = {}
    for team_name in (home.name, away.name):
        rows = [row for game in results for row in game["calibration"]["teams"] if row["team"] == team_name]
        avg_calibration[team_name] = {
            key: round(sum(row[key] for row in rows) / max(1, len(rows)), 3)
            for key in calib_keys
        }

    return {
        "games": runs,
        "home_win_pct": round(home_wins / runs, 3),
        "away_win_pct": round(1 - home_wins / runs, 3),
        "avg_score": avg_score,
        "avg_total_possessions": round(sum(game["possessions"] for game in results) / runs, 1),
        "avg_calibration_deltas": avg_calibration,
        "results": results,
    }


def _schedule_entry(entry: Sequence[Any], index: int) -> Tuple[str, Any, Any]:
    if len(entry) == 2:
        home, away = entry
        return f"game_{index + 1}_{home.name}_vs_{away.name}", home, away
    if len(entry) == 3:
        game_id, home, away = entry
        return str(game_id), home, away
    raise ValueError("Each schedule entry must be (home, away) or (game_id, home, away)")


def _empty_standings(team_names: Sequence[str]) -> Dict[str, Dict[str, float]]:
    return {name: {"W": 0, "L": 0, "PF": 0, "PA": 0} for name in team_names}


def _record_game(standings: Dict[str, Dict[str, float]], game: Dict[str, Any], home_name: str, away_name: str) -> None:
    home_points = game["final_score"][home_name]
    away_points = game["final_score"][away_name]
    standings[home_name]["PF"] += home_points
    standings[home_name]["PA"] += away_points
    standings[away_name]["PF"] += away_points
    standings[away_name]["PA"] += home_points
    winner = game["winner"]
    loser = away_name if winner == home_name else home_name
    standings[winner]["W"] += 1
    standings[loser]["L"] += 1


def _finalize_standings(standings: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
    rows = []
    for team, row in standings.items():
        games = row["W"] + row["L"]
        rows.append({
            "team": team,
            "W": int(row["W"]),
            "L": int(row["L"]),
            "WIN_PCT": round(row["W"] / games, 3) if games else 0.0,
            "PF": int(row["PF"]),
            "PA": int(row["PA"]),
            "DIFF": int(row["PF"] - row["PA"]),
        })
    return sorted(rows, key=lambda row: (-row["W"], -row["DIFF"], -row["PF"], row["team"]))


def run_season_simulations(
    schedule: Sequence[Sequence[Any]],
    game_batch_runner: Callable[[Any, Any, int, int], Dict[str, Any]],
    config: Any,
    season_runs: Optional[int] = None,
    season_game_runs: Optional[int] = None,
    seed: Optional[int] = None,
    game_contexts: Optional[Mapping[str, Any]] = None,
    season_state_factory: Optional[Callable[[int], Any]] = None,
) -> Dict[str, Any]:
    """Repeat seasons while optionally nesting multiple simulations per scheduled game.

    A single raw game is sampled from each nested batch for that season's standings.
    The full batch, its summary, and the selected index are retained for auditability.
    """
    seasons = _positive_int(season_runs, config.season_runs, "season_runs")
    games_per_fixture = _positive_int(season_game_runs, config.season_game_runs, "season_game_runs")
    normalized_schedule = [_schedule_entry(entry, index) for index, entry in enumerate(schedule)]
    if not normalized_schedule:
        raise ValueError("schedule must contain at least one game")
    team_names = sorted({team.name for _, home, away in normalized_schedule for team in (home, away)})
    base_seed = config.seed if seed is None else seed
    base_seed = 0 if base_seed is None else base_seed
    season_results = []

    for season_index in range(seasons):
        season_state = season_state_factory(season_index + 1) if season_state_factory else None
        season_rng = random.Random(base_seed + season_index * 1_000_003)
        standings = _empty_standings(team_names)
        fixture_results = []
        for fixture_index, (game_id, home, away) in enumerate(normalized_schedule):
            fixture_seed = base_seed + season_index * 1_000_003 + fixture_index * max(1, games_per_fixture)
            game_context = game_contexts.get(game_id) if game_contexts else None
            pregame_state = asdict(season_state) if season_state is not None and is_dataclass(season_state) else None
            if game_contexts is not None or season_state is not None:
                batch = game_batch_runner(home, away, games_per_fixture, fixture_seed, game_context, season_state)
            else:
                batch = game_batch_runner(home, away, games_per_fixture, fixture_seed)
            selected_run_index = season_rng.randrange(games_per_fixture)
            standings_game = batch["results"][selected_run_index]
            _record_game(standings, standings_game, home.name, away.name)
            if season_state is not None and hasattr(season_state, "update_after_game"):
                season_state.update_after_game(standings_game)
            fixture_results.append({
                "game_id": game_id,
                "home_team": home.name,
                "away_team": away.name,
                "nested_game_runs": games_per_fixture,
                "batch_summary": {key: value for key, value in batch.items() if key != "results"},
                "selected_run_index": selected_run_index,
                "standings_game": standings_game,
                "all_game_results": batch["results"],
                "game_context": game_context,
                "pregame_season_state": pregame_state,
            })
        season_results.append({
            "season_run": season_index + 1,
            "standings": _finalize_standings(standings),
            "fixtures": fixture_results,
            "final_season_state": asdict(season_state) if season_state is not None and is_dataclass(season_state) else None,
        })

    standing_distribution = {}
    for team_name in team_names:
        team_rows = [next(row for row in season["standings"] if row["team"] == team_name) for season in season_results]
        standing_distribution[team_name] = {
            "avg_wins": round(sum(row["W"] for row in team_rows) / seasons, 2),
            "avg_losses": round(sum(row["L"] for row in team_rows) / seasons, 2),
            "avg_win_pct": round(sum(row["WIN_PCT"] for row in team_rows) / seasons, 3),
            "avg_point_diff": round(sum(row["DIFF"] for row in team_rows) / seasons, 2),
            "season_standings": team_rows,
        }

    return {
        "season_runs": seasons,
        "season_game_runs": games_per_fixture,
        "schedule_games": len(normalized_schedule),
        "season_results": season_results,
        "standing_distribution": standing_distribution,
    }


SUMMARY_SUFFIXES = ("mean", "min", "max", "std", "p05", "p25", "p50", "p75", "p95")


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Linear-interpolated percentile without a third-party dependency."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = []
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def _dated_output_dir(output_dir: str, date_folder: Optional[str] = None) -> Path:
    """Place each export batch in an ISO-sortable YYYYMMDD subfolder."""
    folder_name = date_folder or date.today().strftime("%Y%m%d")
    if len(folder_name) != 8 or not folder_name.isdigit():
        raise ValueError("date_folder must use YYYYMMDD format")
    return Path(output_dir) / folder_name


def _game_rows(game: Dict[str, Any], metadata: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    player_rows, team_rows = [], []
    for side in ("home", "away"):
        team = game[side]
        for player in team.roster:
            player_rows.append({
                **metadata,
                "row_type": "player",
                "team": team.name,
                "player": player.name,
                "role": player.role,
                **player.stats,
            })
        team_rows.append({
            **metadata,
            "row_type": "team",
            "team": team.name,
            "player": "",
            **team.team_stats,
            "periods": game["periods"],
            "total_game_possessions": game["possessions"],
        })
    return player_rows, team_rows


def _summary_rows(rows: Sequence[Dict[str, Any]], group_columns: Sequence[str]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(tuple(row.get(column) for column in group_columns), []).append(row)
    summaries = []
    for group_key, group_rows in groups.items():
        summary = dict(zip(group_columns, group_key))
        numeric_columns = sorted({column for row in group_rows for column, value in row.items() if _numeric(value)})
        summary["observations"] = len(group_rows)
        for column in numeric_columns:
            values = [float(row[column]) for row in group_rows if _numeric(row.get(column))]
            if not values:
                continue
            summary.update({
                f"{column}_mean": round(statistics.fmean(values), 4),
                f"{column}_min": round(min(values), 4),
                f"{column}_max": round(max(values), 4),
                f"{column}_std": round(statistics.pstdev(values), 4),
                f"{column}_p05": round(_percentile(values, 0.05), 4),
                f"{column}_p25": round(_percentile(values, 0.25), 4),
                f"{column}_p50": round(_percentile(values, 0.50), 4),
                f"{column}_p75": round(_percentile(values, 0.75), 4),
                f"{column}_p95": round(_percentile(values, 0.95), 4),
            })
        summaries.append(summary)
    return summaries


def _export_game_rows(player_rows: List[Dict[str, Any]], team_rows: List[Dict[str, Any]], output_dir: str, prefix: str, date_folder: Optional[str] = None) -> Dict[str, str]:
    directory = _dated_output_dir(output_dir, date_folder)
    return {
        "player_game_results": _write_csv(directory / f"{prefix}_player_game_results.csv", player_rows),
        "team_game_results": _write_csv(directory / f"{prefix}_team_game_results.csv", team_rows),
        "player_summary": _write_csv(directory / f"{prefix}_player_summary.csv", _summary_rows(player_rows, ("game_id", "team", "player", "role"))),
        "team_summary": _write_csv(directory / f"{prefix}_team_summary.csv", _summary_rows(team_rows, ("game_id", "team"))),
    }


def _audit_rows(game: Dict[str, Any], metadata: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    audit = game.get("simulation_audit", {})
    context = audit.get("context", {})
    environment_rows = [{
        **metadata,
        "dataset_id": context.get("dataset_id", ""),
        "source_type": context.get("source_type", ""),
        "profile_mode": context.get("profile_mode", ""),
        "context_json": json.dumps(context, separators=(",", ":"), default=str),
        **audit.get("environment", {}),
    }]
    player_rows = [{**metadata, **row} for row in audit.get("player_profiles", [])]
    team_rows = [{
        **metadata,
        **row,
        "matchup_adjustment_json": json.dumps(audit.get("matchup_adjustments", {}).get(row.get("team"), {}), separators=(",", ":")),
    } for row in audit.get("team_profiles", [])]
    return environment_rows, player_rows, team_rows


def export_simulation_audit_csv(games: Sequence[Tuple[Dict[str, Any], Dict[str, Any]]], output_dir: str, prefix: str, date_folder: Optional[str] = None) -> Dict[str, str]:
    """Export context/environment, sampled player profiles, and team matchup inputs."""
    environments: List[Dict[str, Any]] = []
    players: List[Dict[str, Any]] = []
    teams: List[Dict[str, Any]] = []
    for game, metadata in games:
        environment_rows, player_rows, team_rows = _audit_rows(game, metadata)
        environments.extend(environment_rows)
        players.extend(player_rows)
        teams.extend(team_rows)
    directory = _dated_output_dir(output_dir, date_folder)
    return {
        "simulation_context": _write_csv(directory / f"{prefix}_simulation_context.csv", environments),
        "sampled_player_profiles": _write_csv(directory / f"{prefix}_sampled_player_profiles.csv", players),
        "team_matchup_inputs": _write_csv(directory / f"{prefix}_team_matchup_inputs.csv", teams),
    }


def export_matchup_results_csv(batch: Dict[str, Any], output_dir: str = "outputs", game_id: str = "matchup", date_folder: Optional[str] = None) -> Dict[str, str]:
    """Export all raw and summarized player/team results for a matchup batch."""
    player_rows, team_rows = [], []
    audit_games = []
    for game_run, game in enumerate(batch["results"], start=1):
        metadata = {
            "simulation_scope": "matchup",
            "season_run": "",
            "game_id": game_id,
            "game_run": game_run,
            "nested_game_run": "",
            "standings_selected": "",
        }
        players, teams = _game_rows(game, metadata)
        player_rows.extend(players)
        team_rows.extend(teams)
        audit_games.append((game, metadata))
    exports = _export_game_rows(player_rows, team_rows, output_dir, "matchup", date_folder)
    exports.update(export_simulation_audit_csv(audit_games, output_dir, "matchup", date_folder))
    return exports


def export_single_game_possession_log_csv(game: Dict[str, Any], output_dir: str = "outputs", game_id: str = "single_game", date_folder: Optional[str] = None) -> str:
    """Export a possession-level game log for one completed simulation."""
    directory = _dated_output_dir(output_dir, date_folder)
    home_name, away_name = game["home"].name, game["away"].name
    rows = []
    for possession in game.get("possession_log", []):
        events = possession["events"]
        event_types = [event.get("event", "") for event in events]
        terminal_event = next((event for event in reversed(events) if event.get("event") not in {"substitution", "full_timeout"}), {})
        start_score, end_score = possession["start_score"], possession["end_score"]
        offense = possession["offense_team"]
        rows.append({
            "game_id": game_id,
            "possession_id": possession["possession_id"],
            "period": possession["period"],
            "offense_team": offense,
            "defense_team": possession["defense_team"],
            "start_clock_seconds": possession["start_clock_seconds"],
            "end_clock_seconds": possession["end_clock_seconds"],
            "duration_seconds": possession["duration_seconds"],
            "home_team": home_name,
            "away_team": away_name,
            "home_score_start": start_score[home_name],
            "away_score_start": start_score[away_name],
            "home_score_end": end_score[home_name],
            "away_score_end": end_score[away_name],
            "points_scored": end_score[offense] - start_score[offense],
            "ended_by": possession["ended_by"],
            "terminal_event": terminal_event.get("event", ""),
            "event_types": "|".join(event_types),
            "shot_attempted": any(event in {"made_fg", "missed_fg"} for event in event_types),
            "turnover": "turnover" in event_types,
            "offensive_rebounds": event_types.count("offensive_rebound"),
            "free_throw_attempts": event_types.count("free_throw"),
            "event_details": json.dumps(events, separators=(",", ":")),
        })
    return _write_csv(directory / "single_game_possession_log.csv", rows)


def export_season_results_csv(season: Dict[str, Any], output_dir: str = "outputs", date_folder: Optional[str] = None) -> Dict[str, str]:
    """Export all nested game results plus season standings and their summaries."""
    player_rows, team_rows, standings_rows, audit_games = [], [], [], []
    for season_result in season["season_results"]:
        season_run = season_result["season_run"]
        for fixture in season_result["fixtures"]:
            for game_run, game in enumerate(fixture["all_game_results"], start=1):
                metadata = {
                    "simulation_scope": "season",
                    "season_run": season_run,
                    "game_id": fixture["game_id"],
                    "game_run": game_run,
                    "nested_game_run": game_run,
                    "standings_selected": game_run - 1 == fixture["selected_run_index"],
                }
                players, teams = _game_rows(game, metadata)
                player_rows.extend(players)
                team_rows.extend(teams)
                audit_games.append((game, metadata))
        for row in season_result["standings"]:
            standings_rows.append({"season_run": season_run, **row})
    exports = _export_game_rows(player_rows, team_rows, output_dir, "season", date_folder)
    directory = _dated_output_dir(output_dir, date_folder)
    exports.update({
        "season_standings": _write_csv(directory / "season_standings.csv", standings_rows),
        "season_standings_summary": _write_csv(directory / "season_standings_summary.csv", _summary_rows(standings_rows, ("team",))),
    })
    exports.update(export_simulation_audit_csv(audit_games, output_dir, "season", date_folder))
    return exports
