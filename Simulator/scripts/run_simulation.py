"""Command-line entry point for games, matchup batches, and season simulations.

Front Matter
------------
Project: NBA Simulator
File type: Python script
Status: Active
Last updated: 2026-08-01

Purpose: expose the canonical engine without requiring Jupyter and handle JSON
team/context inputs, run counts, dated CSV exports, and concise terminal results.
Usage: run ``python scripts/run_simulation.py <game|matchup|season>``. For example,
``python scripts/run_simulation.py matchup --home-name Knicks --away-name Celtics``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from ._project_paths import PROJECT_ROOT
except ImportError:  # Direct execution
    from _project_paths import PROJECT_ROOT

def load_simulator() -> Dict[str, Any]:
    """Load the canonical Python simulator module without requiring Jupyter."""
    from nba_simulator import simulator_core

    return vars(simulator_core)


def stable_seed(name: str) -> int:
    """Derive a deterministic placeholder-team seed from its display name."""

    return sum((index + 1) * ord(character) for index, character in enumerate(name)) % 1_000_000


def create_team(spec: Any, simulator: Dict[str, Any], dataset_payload: Any = None):
    """Create a placeholder team from a name or {name, seed, rotation_size} spec."""
    if isinstance(spec, str):
        spec = {"name": spec}
    if not isinstance(spec, dict) or not spec.get("name"):
        if not isinstance(spec, dict) or not spec.get("abbreviation"):
            raise ValueError("A team must provide a name or abbreviation")
    if dataset_payload is not None:
        from nba_simulator.real_team_loader import build_real_team
        abbreviation = spec.get("abbreviation")
        if not abbreviation:
            raise ValueError("Dataset-backed teams require an abbreviation")
        return build_real_team(dataset_payload, abbreviation, simulator["create_team"])
    name = str(spec["name"])
    return simulator["create_placeholder_team"](
        name,
        seed=int(spec.get("seed", stable_seed(name))),
        rotation_size=int(spec.get("rotation_size", 10)),
    )


def load_schedule(path: str, simulator: Dict[str, Any], dataset_payload: Any = None) -> List[Tuple[str, Any, Any]]:
    """Read a schedule JSON file containing {game_id, home, away} objects."""
    with Path(path).open(encoding="utf-8") as handle:
        schedule_data = json.load(handle)
    if not isinstance(schedule_data, list):
        raise ValueError("schedule JSON must be a list")
    schedule = []
    for index, fixture in enumerate(schedule_data, start=1):
        if not isinstance(fixture, dict) or "home" not in fixture or "away" not in fixture:
            raise ValueError("Each schedule item must contain home and away")
        home = create_team(fixture["home"], simulator, dataset_payload)
        away = create_team(fixture["away"], simulator, dataset_payload)
        schedule.append((str(fixture.get("game_id", f"game_{index}")), home, away))
    return schedule


def load_context(path: str | None) -> Any:
    """Load one GameContext mapping or a game-id-to-context mapping for seasons."""
    if not path:
        return None
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def parser() -> argparse.ArgumentParser:
    """Build the CLI parser shared by game, matchup, and season modes."""

    command = argparse.ArgumentParser(description="Run the robust NBA possession simulator.")
    subparsers = command.add_subparsers(dest="mode", required=True)

    matchup = subparsers.add_parser("matchup", help="Simulate one matchup repeatedly.")
    matchup.add_argument("--home-name", default="Home Team")
    matchup.add_argument("--away-name", default="Away Team")
    matchup.add_argument("--home-abbr")
    matchup.add_argument("--away-abbr")
    matchup.add_argument("--home-seed", type=int, default=1)
    matchup.add_argument("--away-seed", type=int, default=2)
    matchup.add_argument("--game-id", default="matchup")
    matchup.add_argument("--game-runs", type=int, default=10)

    game = subparsers.add_parser("game", help="Simulate one game and export its possession log.")
    game.add_argument("--home-name", default="Home Team")
    game.add_argument("--away-name", default="Away Team")
    game.add_argument("--home-abbr")
    game.add_argument("--away-abbr")
    game.add_argument("--home-seed", type=int, default=1)
    game.add_argument("--away-seed", type=int, default=2)
    game.add_argument("--game-id", default="single_game")

    season = subparsers.add_parser("season", help="Simulate a schedule as one or more seasons.")
    season.add_argument("--schedule", required=True, help="Path to a schedule JSON file.")
    season.add_argument("--season-runs", type=int, default=10)
    season.add_argument("--season-game-runs", type=int, default=1)

    for subparser in (matchup, game, season):
        subparser.add_argument("--seed", type=int, default=7)
        subparser.add_argument("--output-dir", default="outputs", help="Parent directory; a YYYYMMDD folder is added automatically.")
        subparser.add_argument("--no-export", action="store_true", help="Do not write CSV files.")
        subparser.add_argument("--context", help="JSON GameContext; season mode accepts a game-id-to-context mapping.")
        subparser.add_argument("--team-data", help="Canonical team-profile JSON; dataset-backed teams use abbreviations.")
    return command


def main() -> None:
    """Load requested inputs, execute the selected mode, and print a JSON summary."""

    args = parser().parse_args()
    simulator = load_simulator()
    SimConfig = simulator["SimConfig"]
    output_dir = None if args.no_export else args.output_dir
    context = load_context(args.context)
    dataset_payload = None
    if args.team_data:
        from nba_simulator.real_team_loader import load_real_team_payload
        dataset_payload = load_real_team_payload(args.team_data)

    if args.mode == "game":
        result = simulator["simulate_single_game_robust"](
            create_team({"name": args.home_name, "abbreviation": args.home_abbr, "seed": args.home_seed}, simulator, dataset_payload),
            create_team({"name": args.away_name, "abbreviation": args.away_abbr, "seed": args.away_seed}, simulator, dataset_payload),
            config=SimConfig(seed=args.seed),
            output_dir=output_dir,
            game_id=args.game_id,
            game_context=context,
        )
        print(json.dumps({
            "game_id": args.game_id,
            "winner": result["winner"],
            "final_score": result["final_score"],
            "possessions": len(result["possession_log"]),
            "possession_log_csv": result.get("possession_log_csv"),
        }, indent=2))
        return

    if args.mode == "matchup":
        config = SimConfig(seed=args.seed, game_runs=args.game_runs)
        result = simulator["simulate_game_batch_robust"](
            create_team({"name": args.home_name, "abbreviation": args.home_abbr, "seed": args.home_seed}, simulator, dataset_payload),
            create_team({"name": args.away_name, "abbreviation": args.away_abbr, "seed": args.away_seed}, simulator, dataset_payload),
            config=config,
            output_dir=output_dir,
            game_id=args.game_id,
            game_context=context,
        )
        print(json.dumps({
            "game_id": args.game_id,
            "games": result["games"],
            "home_win_pct": result["home_win_pct"],
            "away_win_pct": result["away_win_pct"],
            "avg_score": result["avg_score"],
            "csv_exports": result.get("csv_exports", {}),
        }, indent=2))
        return

    config = SimConfig(seed=args.seed, season_runs=args.season_runs, season_game_runs=args.season_game_runs)
    result = simulator["simulate_season_robust"](
        load_schedule(args.schedule, simulator, dataset_payload),
        config=config,
        output_dir=output_dir,
        game_contexts=context,
    )
    print(json.dumps({
        "season_runs": result["season_runs"],
        "season_game_runs": result["season_game_runs"],
        "schedule_games": result["schedule_games"],
        "standing_distribution": result["standing_distribution"],
        "csv_exports": result.get("csv_exports", {}),
    }, indent=2))


if __name__ == "__main__":
    main()
