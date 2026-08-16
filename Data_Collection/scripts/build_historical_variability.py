"""Build descriptive player variability profiles from regular-season game logs.

Front Matter
------------
Project: NBA Data Collection
File type: Python script
Status: Active
Last updated: 2026-08-14

Purpose: summarize game totals, per-36 rates, shooting rates, availability, and
home/away variation without training a predictive player model.
Usage: run ``python scripts/build_historical_variability.py``; the command may
reuse retained logs or retrieve official NBA Stats logs and writes JSON output.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
from typing import Any, Dict, Iterable, List, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from ._project_paths import PROJECT_ROOT
except ImportError:  # Direct execution: python scripts/build_historical_variability.py
    from _project_paths import PROJECT_ROOT

NBA_STATS_URL = "https://stats.nba.com/stats/leaguegamelog"
INITIAL_TEAMS = ("NYK", "SAS", "BOS", "LAL")
RAW_OUTPUT = PROJECT_ROOT / "data/raw/player_game_logs_2025-26_regular_season_nyk_sas_bos_lal.json"
PROFILE_OUTPUT = PROJECT_ROOT / "data/published/historical_variability_2025-26_regular_season.json"
HEADERS = {"Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Origin": "https://www.nba.com", "Referer": "https://www.nba.com/", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"}
RAW_STATS = ("MIN", "PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "PLUS_MINUS")
PER_36_STATS = ("PTS", "FGA", "FG3A", "FTA", "REB", "AST", "STL", "BLK", "TOV", "PF")


def fetch_game_logs(season: str) -> List[Dict[str, Any]]:
    """Retrieve league player game logs for one NBA regular season."""

    params = {"Counter": 0, "DateFrom": "", "DateTo": "", "Direction": "DESC", "LeagueID": "00", "PlayerOrTeam": "P", "Season": season, "SeasonType": "Regular Season", "Sorter": "DATE"}
    try:
        with urlopen(Request(f"{NBA_STATS_URL}?{urlencode(params)}", headers=HEADERS), timeout=90) as response:
            payload = json.load(response)
    except Exception as error:
        raise RuntimeError("NBA Stats game-log request failed. The public dashboard can rate-limit requests; retry later.") from error
    result_set = payload.get("resultSets", [None])[0]
    if not result_set:
        raise RuntimeError("NBA Stats returned no player game-log result set")
    return [dict(zip(result_set["headers"], row)) for row in result_set["rowSet"]]


def numeric(value: Any) -> float:
    """Convert an NBA Stats value to float, treating missing values as zero."""

    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def percentile(values: Sequence[float], probability: float) -> float:
    """Return a linearly interpolated quantile for a numeric sequence."""

    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * probability
    lower, upper = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values: Iterable[float]) -> Dict[str, float | int]:
    """Summarize a sample with count, spread, range, and governed percentiles."""

    observed = [float(value) for value in values]
    if not observed:
        return {"n": 0, "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "p05": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0}
    return {"n": len(observed), "mean": round(statistics.fmean(observed), 4), "std": round(statistics.stdev(observed), 4) if len(observed) > 1 else 0.0, "min": round(min(observed), 4), "max": round(max(observed), 4), "p05": round(percentile(observed, .05), 4), "p25": round(percentile(observed, .25), 4), "p50": round(percentile(observed, .50), 4), "p75": round(percentile(observed, .75), 4), "p95": round(percentile(observed, .95), 4)}


def derived(row: Dict[str, Any]) -> Dict[str, float | None]:
    """Calculate opportunity-adjusted and shooting-rate fields for one game row."""

    minutes = numeric(row["MIN"])
    fga, fgm, fg3a, fg3m, fta = (numeric(row[key]) for key in ("FGA", "FGM", "FG3A", "FG3M", "FTA"))
    result: Dict[str, float | None] = {"FG_PCT": fgm / fga if fga else None, "FG3_PCT": fg3m / fg3a if fg3a else None, "FT_PCT": numeric(row["FTM"]) / fta if fta else None, "TWO_PCT": (fgm - fg3m) / (fga - fg3a) if fga > fg3a else None, "THREE_RATE": fg3a / fga if fga else None, "FTR": fta / fga if fga else None}
    result.update({f"{key}_PER_36": numeric(row[key]) * 36 / minutes if minutes else None for key in PER_36_STATS})
    return result


def summarize_player(rows: List[Dict[str, Any]], team_games: int) -> Dict[str, Any]:
    """Build one player's descriptive distributions and availability proxies."""

    first = rows[0]
    measures = ("FG_PCT", "FG3_PCT", "FT_PCT", "TWO_PCT", "THREE_RATE", "FTR", *(f"{key}_PER_36" for key in PER_36_STATS))
    home = [row for row in rows if "@" not in str(row["MATCHUP"])]
    away = [row for row in rows if "@" in str(row["MATCHUP"])]
    return {"player_id": first["PLAYER_ID"], "player": first["PLAYER_NAME"], "team": first["TEAM_ABBREVIATION"], "games_played": len(rows), "team_games_observed": team_games, "availability_proxy": {"games_played_share": round(len(rows) / max(1, team_games), 4)}, "raw_game_distributions": {key: distribution(numeric(row[key]) for row in rows) for key in RAW_STATS}, "per_opportunity_distributions": {key: distribution(value for row in rows if (value := derived(row)[key]) is not None) for key in measures}, "context_splits": {"home": {"games": len(home), "points": distribution(numeric(row["PTS"]) for row in home), "minutes": distribution(numeric(row["MIN"]) for row in home)}, "away": {"games": len(away), "points": distribution(numeric(row["PTS"]) for row in away), "minutes": distribution(numeric(row["MIN"]) for row in away)}}}


def build_profiles(logs: List[Dict[str, Any]], season: str, teams: List[str]) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Filter logs and assemble the versioned team/player variability payload."""

    filtered = [row for row in logs if row["TEAM_ABBREVIATION"] in teams]
    if not filtered:
        raise RuntimeError("No selected-team player game logs were found")
    team_games = {team: len({row["GAME_ID"] for row in filtered if row["TEAM_ABBREVIATION"] == team}) for team in teams}
    grouped: Dict[tuple[int, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in filtered:
        grouped[(row["PLAYER_ID"], row["TEAM_ABBREVIATION"])].append(row)
    team_names = {row["TEAM_ABBREVIATION"]: row["TEAM_NAME"] for row in filtered}
    players_by_team: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for (_, team), rows in grouped.items():
        players_by_team[team].append(summarize_player(rows, team_games[team]))
    profiles = {"metadata": {"dataset_id": f"historical_variability_{season.replace('-', '_')}_regular_season", "source_type": "actual", "season": season, "season_type": "Regular Season", "teams": teams, "source": "NBA Stats league player game log dashboard endpoint", "created_at_utc": datetime.now(timezone.utc).isoformat(), "method": "Descriptive player game-log distributions; sample standard deviation and linear-interpolated percentiles.", "interpretation": "Upstream descriptive dataset, not yet a game-form prediction model or direct simulator input."}, "teams": [{"abbreviation": team, "name": team_names[team], "games_observed": team_games[team], "players": sorted(players_by_team[team], key=lambda item: item["player"])} for team in teams]}
    return profiles, filtered


def main() -> None:
    """Parse CLI options, retrieve or reuse logs, and write variability JSON."""

    command = argparse.ArgumentParser(description="Build historical NBA player-variability profiles.")
    command.add_argument("--season", default="2025-26")
    command.add_argument("--teams", nargs="+", default=list(INITIAL_TEAMS), metavar="ABBREVIATION")
    command.add_argument("--all-teams", action="store_true", help="Build variability profiles for every team present in the source logs.")
    command.add_argument("--reuse-raw", action="store_true", help="Read existing --raw-output instead of downloading game logs.")
    command.add_argument("--raw-output", default=str(RAW_OUTPUT))
    command.add_argument("--output", default=str(PROFILE_OUTPUT))
    args = command.parse_args()
    raw_output, output = Path(args.raw_output), Path(args.output)
    logs = json.loads(raw_output.read_text(encoding="utf-8")) if args.reuse_raw else fetch_game_logs(args.season)
    teams = sorted({row["TEAM_ABBREVIATION"] for row in logs}) if args.all_teams else [team.upper() for team in args.teams]
    profiles, filtered_logs = build_profiles(logs, args.season, teams)
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_text(json.dumps(filtered_logs, indent=2), encoding="utf-8")
    output.write_text(json.dumps(profiles, indent=2), encoding="utf-8")
    print(f"Saved {len(filtered_logs)} game logs and {sum(len(team['players']) for team in profiles['teams'])} player profiles")


if __name__ == "__main__":
    main()
