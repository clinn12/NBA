"""Build a labeled structural-calibration pilot from official player game logs.

Front Matter
------------
Project: NBA Data Collection
File type: Python script
Status: Active
Last updated: 2026-08-15

Purpose: reconstruct a small auditable historical game set for mechanics tests
while explicitly preventing look-ahead records from being called predictions.
Usage: run ``python scripts/build_pilot_calibration_dataset.py`` after retaining
the four-team player logs. The output is a governed structural-only publication.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOGS = PROJECT_ROOT / "data/raw/player_game_logs_2025-26_regular_season_nyk_sas_bos_lal.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data/published/calibration/pilot_games_2025-26_regular_season.json"
DEFAULT_MANIFEST = PROJECT_ROOT / "data/manifests/pilot_calibration_games.json"
DEFAULT_TEAMS = ("NYK", "SAS", "BOS", "LAL")
TEAM_STAT_FIELDS = ("FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "PTS")
PLAYER_STAT_FIELDS = ("MIN",) + TEAM_STAT_FIELDS


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _sum_stats(rows: Iterable[Mapping[str, Any]], fields: Sequence[str]) -> Dict[str, float]:
    return {field: round(sum(_number(row.get(field)) for row in rows), 4) for field in fields}


def _possessions(stats: Mapping[str, float]) -> float:
    return round(stats["FGA"] + 0.44 * stats["FTA"] - stats["OREB"] + stats["TOV"], 4)


def _team_dates(rows: Sequence[Mapping[str, Any]]) -> Dict[str, List[date]]:
    dates: Dict[str, set[date]] = defaultdict(set)
    for row in rows:
        dates[str(row["TEAM_ABBREVIATION"])].add(date.fromisoformat(str(row["GAME_DATE"])))
    return {team: sorted(values) for team, values in dates.items()}


def _rest_days(team: str, game_date: date, dates: Mapping[str, Sequence[date]]) -> int | None:
    prior = [value for value in dates.get(team, []) if value < game_date]
    return (game_date - prior[-1]).days - 1 if prior else None


def build_pilot(rows: Sequence[Mapping[str, Any]], teams: Sequence[str], limit: int | None = None) -> Dict[str, Any]:
    """Construct labeled historical games where both opponents are in scope.

    The returned records intentionally contain completed-game participant data
    and are labeled structural-only so predictive evaluation rejects them.
    """

    team_set = {team.upper() for team in teams}
    by_game: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("TEAM_ABBREVIATION") in team_set:
            by_game[str(row["GAME_ID"])].append(row)
    dates = _team_dates(rows)
    games: List[Dict[str, Any]] = []
    for game_id, game_rows in by_game.items():
        represented = {str(row["TEAM_ABBREVIATION"]) for row in game_rows}
        if len(represented) != 2 or not represented.issubset(team_set):
            continue
        home_rows = [row for row in game_rows if " vs. " in str(row.get("MATCHUP", ""))]
        if not home_rows:
            continue
        home_abbr = str(home_rows[0]["TEAM_ABBREVIATION"])
        away_abbr = next(team for team in represented if team != home_abbr)
        team_rows = {abbr: [row for row in game_rows if row["TEAM_ABBREVIATION"] == abbr] for abbr in represented}
        game_date = date.fromisoformat(str(game_rows[0]["GAME_DATE"]))
        team_payload: Dict[str, Any] = {}
        for abbr in (home_abbr, away_abbr):
            ordered = sorted(team_rows[abbr], key=lambda row: _number(row.get("MIN")), reverse=True)
            totals = _sum_stats(ordered, TEAM_STAT_FIELDS)
            players = [
                {
                    "player_id": row.get("PLAYER_ID"),
                    "player": row.get("PLAYER_NAME"),
                    "stats": {field: _number(row.get(field)) for field in PLAYER_STAT_FIELDS},
                }
                for row in ordered
            ]
            team_payload[abbr] = {
                "name": ordered[0].get("TEAM_NAME"),
                "score": int(round(totals["PTS"])),
                "team_box_score": totals,
                "estimated_possessions": _possessions(totals),
                "players_appeared": [row["player"] for row in players],
                "expected_starters_proxy": [row["player"] for row in players[:5]],
                "actual_starters": None,
                "rest_days": _rest_days(abbr, game_date, dates),
                "players": players,
            }
        games.append({
            "game_id": game_id,
            "game_date": game_date.isoformat(),
            "home_team": home_abbr,
            "away_team": away_abbr,
            "home_score": team_payload[home_abbr]["score"],
            "away_score": team_payload[away_abbr]["score"],
            "winner": home_abbr if team_payload[home_abbr]["score"] > team_payload[away_abbr]["score"] else away_abbr,
            "teams": team_payload,
            "evaluation_labels": {
                "structural_reconstruction_eligible": True,
                "predictive_backtest_eligible": False,
                "lookahead_inputs": True,
                "availability_source": "players_who_appeared_in_completed_game",
                "starter_source": "top_five_minutes_proxy_not_actual_starters",
                "period_scores_available": False,
                "pregame_injury_report_available": False,
            },
        })
    games.sort(key=lambda game: (game["game_date"], game["game_id"]))
    if limit is not None:
        games = games[:limit]
    return {
        "metadata": {
            "schema_version": "pilot_calibration_games_v1",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "season": "2025-26",
            "season_type": "Regular Season",
            "teams": list(teams),
            "games": len(games),
            "source": "Retained NBA Stats player game logs",
            "purpose": "Structural reconstruction and descriptive calibration only.",
            "predictive_backtest_warning": "Completed-season profiles and actual players-who-appeared are look-ahead inputs. These records must not be reported as pregame predictive backtests.",
            "possessions_formula": "FGA + 0.44*FTA - OREB + TOV (team estimate)",
        },
        "games": games,
    }


def write_pilot_manifest(output: Path, payload: Mapping[str, Any], manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    """Write an atomic hash manifest for one structural pilot publication."""

    manifest = {
        "manifest_version": "pilot_calibration_games_manifest_v1",
        "dataset_schema": payload["metadata"]["schema_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "publication_path": output.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "games": len(payload["games"]),
        "predictive_backtest_eligible": False,
        "consumer": "NBA Simulator structural calibration harness",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    return manifest


def main() -> None:
    """Parse CLI inputs and write the structural pilot dataset."""

    parser = argparse.ArgumentParser(description="Build the pilot historical-game calibration dataset.")
    parser.add_argument("--logs", default=str(DEFAULT_LOGS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--manifest-output", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--teams", nargs="+", default=list(DEFAULT_TEAMS))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    rows = json.loads(Path(args.logs).read_text(encoding="utf-8"))
    payload = build_pilot(rows, [team.upper() for team in args.teams], args.limit)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_pilot_manifest(output, payload, Path(args.manifest_output))
    print(json.dumps({"games": len(payload["games"]), "output": str(output), "predictive_backtest_eligible": False}, indent=2))


if __name__ == "__main__":
    main()
