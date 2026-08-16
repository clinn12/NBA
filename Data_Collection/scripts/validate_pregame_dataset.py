"""Validate dated pregame profiles, chronology, roster shape, and provenance.

Front Matter
------------
Project: NBA Data Collection
File type: Python script
Status: Active
Last updated: 2026-08-14

Purpose: prevent leakage, malformed rosters/starters, duplicate games, split
overlap, invalid expected context, and hidden source limitations.
Usage: run ``python scripts/validate_pregame_dataset.py`` after building profiles;
the command writes a JSON QA report and exits nonzero on validation errors.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

try:
    from ._project_paths import PROJECT_ROOT
except ImportError:  # Direct execution
    from _project_paths import PROJECT_ROOT


DEFAULT_INPUT = PROJECT_ROOT / "data/published/pregame/pregame_profiles_2025-26_regular_season.json"
DEFAULT_REPORT = PROJECT_ROOT / "data/published/pregame/pregame_profiles_2025-26_regular_season_qa.json"


def validate(payload: Mapping[str, Any], expected_teams: int = 30) -> Dict[str, Any]:
    """Return blocking errors, coverage warnings, and dataset summary metrics."""

    errors: List[str] = []
    warnings: List[str] = []
    games = list(payload.get("games", []))
    metadata = payload.get("metadata", {})
    game_ids = [str(game.get("game_id")) for game in games]
    teams = {str(team) for game in games for team in (game.get("home_team"), game.get("away_team"))}
    if len(game_ids) != len(set(game_ids)):
        errors.append("Duplicate game_id values found")
    if metadata.get("games") != len(games):
        errors.append("metadata.games does not equal the game-record count")
    if len(teams) != expected_teams:
        errors.append(f"Expected {expected_teams} teams, found {len(teams)}")
    if not metadata.get("features_time_valid"):
        errors.append("Dataset metadata is not marked features_time_valid")

    exact_starter_games = 0
    official_injury_games = 0
    starter_source_counts: Dict[str, int] = {}
    split_dates: Dict[str, List[str]] = {name: [] for name in ("calibration", "validation", "holdout")}
    for game in games:
        game_id = str(game.get("game_id"))
        game_date = str(game.get("game_date"))
        split = str(game.get("split"))
        if split not in split_dates:
            errors.append(f"{game_id}: invalid split {split}")
        else:
            split_dates[split].append(game_date)
        labels = game.get("evaluation_labels", {})
        if labels.get("features_cutoff") != "strictly_before_game_date" or not labels.get("predictive_backtest_eligible"):
            errors.append(f"{game_id}: predictive time-valid labels are missing")
        exact_starter_games += int(bool(labels.get("exact_actual_starters_available")))
        official_injury_games += int(bool(labels.get("official_injury_report_available")))
        expected_team_keys = {str(game.get("home_team")), str(game.get("away_team"))}
        pregame_teams = game.get("pregame", {}).get("teams", {})
        if set(pregame_teams) != expected_team_keys:
            errors.append(f"{game_id}: pregame teams do not match home/away teams")
            continue
        for abbreviation, team in pregame_teams.items():
            roster = list(team.get("expected_active_roster", []))
            starters = list(team.get("expected_starters", []))
            players = list(team.get("players", []))
            if not 5 <= len(roster) <= 12:
                errors.append(f"{game_id}/{abbreviation}: expected roster size {len(roster)} is outside 5-12")
            if len(starters) != 5 or len(set(starters)) != 5:
                errors.append(f"{game_id}/{abbreviation}: expected starters are not five unique players")
            if not set(starters).issubset(set(roster)):
                errors.append(f"{game_id}/{abbreviation}: expected starters are not a roster subset")
            if len(players) != len(roster):
                errors.append(f"{game_id}/{abbreviation}: player profiles do not match roster size")
            source = str(team.get("starter_source"))
            starter_source_counts[source] = starter_source_counts.get(source, 0) + 1
            for player in players:
                if str(player.get("last_appearance_date")) >= game_date:
                    errors.append(f"{game_id}/{abbreviation}/{player.get('player')}: feature leakage from {player.get('last_appearance_date')}")
        expected = game.get("pregame", {}).get("expected_game", {})
        for field in ("pace", "home_offensive_rating", "away_offensive_rating", "expected_total"):
            value = expected.get(field)
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"{game_id}: invalid expected_game.{field}")

    ordered_splits = ("calibration", "validation", "holdout")
    for earlier, later in zip(ordered_splits, ordered_splits[1:]):
        if split_dates[earlier] and split_dates[later] and max(split_dates[earlier]) >= min(split_dates[later]):
            errors.append(f"Split dates overlap or are out of order: {earlier} vs {later}")
    exact_coverage = exact_starter_games / len(games) if games else 0.0
    if exact_coverage < 0.95:
        warnings.append(f"Exact actual-starter coverage is {exact_coverage:.1%}; starter inference remains active")
    if official_injury_games < len(games):
        warnings.append("Official pregame injury/availability reports are not yet supplied; prior-appearance inference is active")
    return {
        "report_version": "pregame_dataset_qa_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not errors else "fail",
        "games": len(games),
        "teams": len(teams),
        "split_counts": {name: len(dates) for name, dates in split_dates.items()},
        "exact_actual_starter_games": exact_starter_games,
        "exact_actual_starter_coverage": round(exact_coverage, 6),
        "official_injury_report_games": official_injury_games,
        "starter_source_counts": starter_source_counts,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    """Validate the configured dataset, write its report, and set process status."""

    parser = argparse.ArgumentParser(description="Validate a dated pregame profile dataset.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--expected-teams", type=int, default=30)
    args = parser.parse_args()
    report = validate(json.loads(Path(args.input).read_text(encoding="utf-8")), args.expected_teams)
    destination = Path(args.report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
