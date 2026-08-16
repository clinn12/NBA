"""Create dated, pregame-only rolling NBA profiles and historical labels.

Front Matter
------------
Project: NBA Data Collection
File type: Python script
Status: Active
Last updated: 2026-08-14

Purpose: build time-valid team/player inputs, expected rotations, rest, and
transparent expected-game context for calibration and predictive backtests.
Usage: run ``python scripts/pregame_dataset.py`` after full-league logs exist.
Features are calculated before current-game rows enter history; completed-game
values are retained only under ``actual`` for evaluation.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
import json
from pathlib import Path
import statistics
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

try:
    from ._project_paths import PROJECT_ROOT
except ImportError:  # Direct execution
    from _project_paths import PROJECT_ROOT


DEFAULT_PLAYER_LOGS = PROJECT_ROOT / "data/raw/player_game_logs_2025-26_regular_season_all.json"
DEFAULT_TEAM_LOGS = PROJECT_ROOT / "data/raw/team_game_logs_2025-26_regular_season_all.json"
DEFAULT_STARTERS = PROJECT_ROOT / "data/raw/game_starters_2025-26_regular_season_all.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data/published/pregame/pregame_profiles_2025-26_regular_season.json"
STAT_FIELDS = ("MIN", "PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF")
TEAM_FIELDS = ("PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "POSS_EST")


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mean(rows: Sequence[Mapping[str, Any]], field: str) -> float:
    return statistics.fmean(_num(row.get(field)) for row in rows) if rows else 0.0


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    return {field: round(_mean(rows, field), 6) for field in STAT_FIELDS}


def _split_by_date(games: List[Dict[str, Any]], calibration_share: float, validation_share: float) -> None:
    ordered_dates = sorted({game["game_date"] for game in games})
    if not ordered_dates:
        return
    calibration_index = min(len(ordered_dates) - 1, int(len(ordered_dates) * calibration_share))
    validation_index = min(len(ordered_dates) - 1, int(len(ordered_dates) * (calibration_share + validation_share)))
    calibration_end, validation_end = ordered_dates[calibration_index], ordered_dates[validation_index]
    for game in games:
        game["split"] = "calibration" if game["game_date"] <= calibration_end else ("validation" if game["game_date"] <= validation_end else "holdout")


def _rolling_team(history: Sequence[Mapping[str, Any]], opponent_history: Sequence[Mapping[str, Any]], windows: Sequence[int]) -> Dict[str, Any]:
    def split_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        possessions = _mean(rows, "POSS_EST")
        return {"games": len(rows), "points": round(_mean(rows, "PTS"), 4), "possessions": round(possessions, 4), "offensive_rating": round(100 * _mean(rows, "PTS") / possessions, 4) if possessions else None}
    result: Dict[str, Any] = {
        "games_before": len(history),
        "season_to_date": split_summary(history),
        "home_split": split_summary([row for row in history if row.get("HOME")]),
        "away_split": split_summary([row for row in history if not row.get("HOME")]),
    }
    for window in windows:
        rows = list(history[-window:])
        opponent_rows = list(opponent_history[-window:])
        possessions = _mean(rows, "POSS_EST")
        result[f"last_{window}"] = {
            "games": len(rows), "points": round(_mean(rows, "PTS"), 4), "possessions": round(possessions, 4),
            "offensive_rating": round(100 * _mean(rows, "PTS") / possessions, 4) if possessions else None,
            "defensive_rating": round(100 * _mean(opponent_rows, "PTS") / _mean(opponent_rows, "POSS_EST"), 4) if opponent_rows and _mean(opponent_rows, "POSS_EST") else None,
            "three_attempt_rate": round(_mean(rows, "FG3A") / _mean(rows, "FGA"), 5) if _mean(rows, "FGA") else None,
            "free_throw_rate": round(_mean(rows, "FTA") / _mean(rows, "FGA"), 5) if _mean(rows, "FGA") else None,
        }
    return result


def _player_profile(player_rows: Sequence[Mapping[str, Any]], team_game_ids: Sequence[str], starter_counts: Mapping[str, int], windows: Sequence[int]) -> Dict[str, Any]:
    recent_team_games = list(team_game_ids[-max(windows):])
    recent_set = set(recent_team_games)
    recent = [row for row in player_rows if row["GAME_ID"] in recent_set]
    last10_ids = set(team_game_ids[-10:])
    last10 = [row for row in player_rows if row["GAME_ID"] in last10_ids]
    source = last10 if len(last10) >= 3 else list(player_rows)
    totals = {field: sum(_num(row.get(field)) for row in source) for field in STAT_FIELDS}
    fga, fg3a, fgm, fg3m, fta = totals["FGA"], totals["FG3A"], totals["FGM"], totals["FG3M"], totals["FTA"]
    minutes = totals["MIN"]
    team_games = max(1, min(10, len(team_game_ids)))
    events = max(1.0, fga + 0.44 * fta + totals["TOV"])
    overrides = {
        "mpg": round(minutes / team_games, 4),
        "usage": 20.0,
        "two_pct": round(_clamp((fgm - fg3m) / max(1.0, fga - fg3a), 0.30, 0.80), 5),
        "three_pct": round(_clamp(fg3m / max(1.0, fg3a), 0.20, 0.60), 5),
        "ft_pct": round(_clamp(totals["FTM"] / max(1.0, fta), 0.40, 1.00), 5),
        "three_rate": round(_clamp(fg3a / max(1.0, fga), 0.02, 0.85), 5),
        "ftr": round(_clamp(fta / max(1.0, fga), 0.02, 0.80), 5),
        "ast_rate": round(_clamp(totals["AST"] / max(1.0, fgm + totals["AST"]), 0.02, 0.45), 5),
        "tov_rate": round(_clamp(totals["TOV"] / events, 0.02, 0.30), 5),
        "orb_rate": round(_clamp(totals["OREB"] / max(1.0, minutes * 2.25), 0.005, 0.18), 5),
        "drb_rate": round(_clamp(totals["DREB"] / max(1.0, minutes * 2.25), 0.04, 0.32), 5),
        "stl_rate": round(_clamp(totals["STL"] / max(1.0, minutes * 2.25), 0.002, 0.05), 5),
        "blk_rate": round(_clamp(totals["BLK"] / max(1.0, minutes * 2.25), 0.001, 0.10), 5),
        "foul_rate": round(_clamp(totals["PF"] / max(1.0, minutes * 2.25), 0.01, 0.12), 5),
        "defense": 0.0, "stamina": 0.86, "clutch": 0.0, "rim_pressure": 0.0,
        "off_ball_gravity": 0.0, "switchability": 0.0, "help_defense": 0.0,
    }
    return {
        "player_id": player_rows[-1]["PLAYER_ID"], "player": player_rows[-1]["PLAYER_NAME"],
        "last_appearance_date": player_rows[-1]["GAME_DATE"], "appearances_before": len(player_rows),
        "appearances_last_10_team_games": len(last10), "starts_last_10_team_games": starter_counts.get(str(player_rows[-1]["PLAYER_ID"]), 0),
        "expected_active": bool(last10), "rolling": {f"last_{window}": {"appearances": len([row for row in recent if row["GAME_ID"] in set(team_game_ids[-window:])]), **_aggregate([row for row in recent if row["GAME_ID"] in set(team_game_ids[-window:])])} for window in windows},
        "overrides": overrides,
    }


def build_pregame_dataset(player_logs: Sequence[Mapping[str, Any]], team_logs: Sequence[Mapping[str, Any]], starters: Mapping[str, Any] | None = None, min_prior_games: int = 10, windows: Sequence[int] = (5, 10, 20), calibration_share: float = 0.60, validation_share: float = 0.20) -> Dict[str, Any]:
    """Build chronological game records using only information known pre-tipoff.

    Histories are updated after each game's feature record is produced. Actual
    outcomes are isolated under ``actual`` and chronological splits use whole
    dates so calibration, validation, and holdout cannot overlap.
    """

    starter_games = (starters or {}).get("games", {})
    players_by_game_team: Dict[tuple[str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for row in player_logs:
        players_by_game_team[(str(row["GAME_ID"]), str(row["TEAM_ABBREVIATION"]))].append(row)
    team_by_game: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in team_logs:
        team_by_game[str(row["GAME_ID"])].append(row)
    team_history: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    opponent_history: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    player_history: Dict[tuple[str, str], List[Mapping[str, Any]]] = defaultdict(list)
    team_game_ids: Dict[str, List[str]] = defaultdict(list)
    starter_history: Dict[str, List[tuple[str, set[str]]]] = defaultdict(list)
    completed_league_rows: List[Mapping[str, Any]] = []
    games: List[Dict[str, Any]] = []
    for game_id, pair in sorted(team_by_game.items(), key=lambda item: (item[1][0]["GAME_DATE"], item[0])):
        if len(pair) != 2:
            continue
        home = next((row for row in pair if row["HOME"]), None)
        away = next((row for row in pair if not row["HOME"]), None)
        if not home or not away:
            continue
        home_abbr, away_abbr = str(home["TEAM_ABBREVIATION"]), str(away["TEAM_ABBREVIATION"])
        if min(len(team_history[home_abbr]), len(team_history[away_abbr])) < min_prior_games:
            # Update histories below even when the game is too early for a profile.
            pass
        else:
            prior = completed_league_rows
            league_pace = _mean(prior, "POSS_EST") if prior else 99.0
            league_ortg = 100 * _mean(prior, "PTS") / league_pace if league_pace else 114.0
            pregame_teams: Dict[str, Any] = {}
            for abbr, opponent_abbr in ((home_abbr, away_abbr), (away_abbr, home_abbr)):
                rolling = _rolling_team(team_history[abbr], opponent_history[abbr], windows)
                ids = team_game_ids[abbr]
                candidates = []
                starter_counts: Dict[str, int] = defaultdict(int)
                for _, ids_started in starter_history[abbr][-10:]:
                    for player_id in ids_started:
                        starter_counts[player_id] += 1
                has_prior_exact_starters = any(ids_started for _, ids_started in starter_history[abbr][-10:])
                for (team, player_id), history in player_history.items():
                    if team == abbr and any(row["GAME_ID"] in set(ids[-10:]) for row in history):
                        candidates.append(_player_profile(history, ids, starter_counts, windows))
                candidates.sort(key=lambda player: (player["overrides"]["mpg"], player["starts_last_10_team_games"]), reverse=True)
                rotation = candidates[:max(5, min(12, len(candidates)))]
                event_total = sum(max(0.1, player["overrides"]["mpg"] * (player["overrides"]["ftr"] + player["overrides"]["three_rate"] + 0.8)) for player in rotation)
                for player in rotation:
                    event_weight = player["overrides"]["mpg"] * (player["overrides"]["ftr"] + player["overrides"]["three_rate"] + 0.8)
                    player["overrides"]["usage"] = round(_clamp(100 * event_weight / max(0.1, event_total), 5.0, 42.0), 4)
                expected_starters = [player["player"] for player in sorted(rotation, key=lambda item: (item["starts_last_10_team_games"], item["overrides"]["mpg"]), reverse=True)[:5]]
                pregame_teams[abbr] = {
                    "team_name": (home if abbr == home_abbr else away)["TEAM_NAME"], "opponent": opponent_abbr,
                    "rolling_team": rolling, "expected_active_roster": [player["player"] for player in rotation],
                    "expected_starters": expected_starters, "expected_rotation_size": len(rotation), "players": rotation,
                    "rest_days": max(0, (date.fromisoformat(str(home["GAME_DATE"])) - date.fromisoformat(str(team_history[abbr][-1]["GAME_DATE"]))).days - 1),
                    "travel_miles": 0.0,
                    "availability_source": "rolling_prior_appearances_not_official_injury_report",
                    "starter_source": "prior_10_game_start_frequency" if has_prior_exact_starters else "prior_minutes_proxy",
                }
            h10, a10 = pregame_teams[home_abbr]["rolling_team"]["last_10"], pregame_teams[away_abbr]["rolling_team"]["last_10"]
            expected_pace = statistics.fmean(value for value in (h10.get("possessions"), a10.get("possessions")) if value)
            home_expected_ortg = statistics.fmean(value for value in (h10.get("offensive_rating"), a10.get("defensive_rating")) if value is not None) + 1.0
            away_expected_ortg = statistics.fmean(value for value in (a10.get("offensive_rating"), h10.get("defensive_rating")) if value is not None) - 1.0
            actual_starters = starter_games.get(game_id, {}).get("teams", {})
            exact_actual_starters = (
                set(actual_starters) == {home_abbr, away_abbr}
                and all(len(actual_starters[abbr].get("starters", [])) == 5 for abbr in (home_abbr, away_abbr))
            )
            games.append({
                "game_id": game_id, "game_date": home["GAME_DATE"], "home_team": home_abbr, "away_team": away_abbr,
                "pregame": {"teams": pregame_teams, "league_context": {"pace": round(league_pace, 4), "offensive_rating": round(league_ortg, 4)},
                            "expected_game": {"pace": round(expected_pace, 4), "home_offensive_rating": round(home_expected_ortg, 4), "away_offensive_rating": round(away_expected_ortg, 4), "expected_total": round(expected_pace * (home_expected_ortg + away_expected_ortg) / 100, 4)}},
                "actual": {"home_score": int(home["PTS"]), "away_score": int(away["PTS"]), "winner": home_abbr if home["PTS"] > away["PTS"] else away_abbr,
                           "teams": {home_abbr: {"team_box_score": {field: home[field] for field in TEAM_FIELDS}, "players": players_by_game_team[(game_id, home_abbr)], "actual_starters": actual_starters.get(home_abbr, {}).get("starters")},
                                     away_abbr: {"team_box_score": {field: away[field] for field in TEAM_FIELDS}, "players": players_by_game_team[(game_id, away_abbr)], "actual_starters": actual_starters.get(away_abbr, {}).get("starters")}}},
                "evaluation_labels": {"predictive_backtest_eligible": True, "features_cutoff": "strictly_before_game_date", "official_injury_report_available": False, "exact_actual_starters_available": exact_actual_starters},
            })
        starter_record = starter_games.get(game_id, {}).get("teams", {})
        for current, opponent in ((home, away), (away, home)):
            abbr = str(current["TEAM_ABBREVIATION"])
            team_history[abbr].append(current); opponent_history[abbr].append(opponent); team_game_ids[abbr].append(game_id)
            started_ids = {str(player.get("player_id")) for player in starter_record.get(abbr, {}).get("players", []) if player.get("starter")}
            starter_history[abbr].append((game_id, started_ids))
            for row in players_by_game_team[(game_id, abbr)]:
                player_history[(abbr, str(row["PLAYER_ID"]))].append(row)
        completed_league_rows.extend(pair)
    _split_by_date(games, calibration_share, validation_share)
    exact_starter_games = sum(game["evaluation_labels"]["exact_actual_starters_available"] for game in games)
    return {"metadata": {"schema_version": "pregame_profiles_v1", "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_type": "historical_pregame_calculated", "features_time_valid": True, "games": len(games), "teams": len({team for game in games for team in (game["home_team"], game["away_team"])}), "min_prior_games": min_prior_games, "rolling_windows": list(windows), "exact_actual_starter_games": exact_starter_games, "exact_actual_starter_coverage": round(exact_starter_games / len(games), 6) if games else 0.0, "availability_caveat": "Expected availability is inferred from prior appearances until an upstream official injury-report dataset is supplied.", "lineup_caveat": "Exact starters are retained when the official box-score cache contains the game; remaining records use prior-minute and prior-starter-frequency fallbacks."}, "games": games}


def main() -> None:
    """Load retained logs, build dated profiles, and write the JSON dataset."""

    parser = argparse.ArgumentParser(description="Build full-league dated pregame rolling profiles.")
    parser.add_argument("--player-logs", default=str(DEFAULT_PLAYER_LOGS))
    parser.add_argument("--team-logs", default=str(DEFAULT_TEAM_LOGS))
    parser.add_argument("--starters", default=str(DEFAULT_STARTERS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-prior-games", type=int, default=10)
    parser.add_argument("--windows", nargs="+", type=int, default=[5, 10, 20])
    parser.add_argument("--calibration-share", type=float, default=0.60)
    parser.add_argument("--validation-share", type=float, default=0.20)
    args = parser.parse_args()
    starter_path = Path(args.starters)
    starters = json.loads(starter_path.read_text(encoding="utf-8")) if starter_path.exists() else None
    payload = build_pregame_dataset(json.loads(Path(args.player_logs).read_text(encoding="utf-8")), json.loads(Path(args.team_logs).read_text(encoding="utf-8")), starters, args.min_prior_games, args.windows, args.calibration_share, args.validation_share)
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    splits = {split: sum(game["split"] == split for game in payload["games"]) for split in ("calibration", "validation", "holdout")}
    print(json.dumps({"output": str(output), "games": payload["metadata"]["games"], "teams": payload["metadata"]["teams"], "splits": splits}, indent=2))


if __name__ == "__main__":
    main()
