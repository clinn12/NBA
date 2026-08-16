"""Pull and map regular-season NBA profiles for simulator team inputs.

Front Matter
------------
Project: NBA Data Collection
File type: Python script
Status: Active
Last updated: 2026-08-14

Purpose: retrieve NBA Stats aggregates, preserve raw source components, and
publish canonical historical player/team profiles with transparent enrichment.
Usage: run ``python scripts/pull_real_team_data.py`` for the pilot or pass
``--all-teams`` for league coverage. Network access is required; no model is fit.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from ._project_paths import PROJECT_ROOT
except ImportError:  # Direct execution
    from _project_paths import PROJECT_ROOT
from data_collection.historical_enrichment import calculate_historical_enrichment, fetch_enrichment_feeds


NBA_STATS_BASE = "https://stats.nba.com/stats/"
INITIAL_TEAMS = ("NYK", "SAS", "BOS", "LAL")
NBA_TEAMS = ("ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW", "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS")
DEFAULT_OUTPUT = PROJECT_ROOT / "data/published/real_teams_2025-26_regular_season.json"
DEFAULT_ENRICHMENT_RAW_OUTPUT = PROJECT_ROOT / "data/raw/historical_enrichment_2025-26_regular_season.json"
REQUEST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
}


def dashboard_params(season: str, measure_type: str) -> Dict[str, Any]:
    """Return shared NBA Stats dashboard parameters for a regular season."""

    return {
        "College": "", "Conference": "", "Country": "", "DateFrom": "", "DateTo": "", "Division": "",
        "DraftPick": "", "DraftYear": "", "GameScope": "", "GameSegment": "", "Height": "", "LastNGames": 0,
        "LeagueID": "00", "Location": "", "MeasureType": measure_type, "Month": 0, "OpponentTeamID": 0,
        "Outcome": "", "PORound": 0, "PaceAdjust": "N", "PerMode": "PerGame", "Period": 0,
        "PlayerExperience": "", "PlayerPosition": "", "PlusMinus": "N", "Rank": "N", "Season": season,
        "SeasonSegment": "", "SeasonType": "Regular Season", "ShotClockRange": "", "StarterBench": "",
        "TeamID": 0, "VsConference": "", "VsDivision": "", "Weight": "",
    }


def fetch_table(endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Request one NBA Stats result set and return rows keyed by response headers."""

    request = Request(f"{NBA_STATS_BASE}{endpoint}?{urlencode(params)}", headers=REQUEST_HEADERS)
    try:
        with urlopen(request, timeout=45) as response:
            payload = json.load(response)
    except Exception as error:
        raise RuntimeError(
            f"NBA Stats request failed for {endpoint}. The public dashboard can rate-limit requests; retry later."
        ) from error
    result_sets = payload.get("resultSets") or payload.get("resultSet")
    if isinstance(result_sets, dict):
        result_sets = [result_sets]
    if not result_sets:
        raise RuntimeError(f"NBA Stats returned no result set for {endpoint}")
    result_set = result_sets[0]
    headers = result_set.get("headers") or result_set.get("Headers")
    rows = result_set.get("rowSet") or result_set.get("RowSet")
    if not headers or rows is None:
        raise RuntimeError(f"Unexpected NBA Stats response shape for {endpoint}")
    return [dict(zip(headers, row)) for row in rows]


def number(row: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """Read a numeric source field with a safe fallback for missing values."""

    value = row.get(key, default)
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def bounded(value: float, low: float, high: float) -> float:
    """Clamp a calculated simulator input to its documented valid range."""

    return max(low, min(high, value))


def rate(row: Dict[str, Any], key: str, fallback: float = 0.0) -> float:
    """Convert a percentage-like NBA Stats field to a zero-to-one rate."""

    value = number(row, key, fallback)
    return value / 100 if value > 1 else value


def infer_role(advanced: Dict[str, Any]) -> str:
    """Temporary role classification until official position/rotation inputs are added."""
    if rate(advanced, "BLK_PCT") >= 0.030 or rate(advanced, "DREB_PCT") >= 0.180:
        return "big"
    if rate(advanced, "AST_PCT") >= 0.240:
        return "pg"
    if rate(advanced, "OREB_PCT") >= 0.060:
        return "forward"
    if rate(advanced, "AST_PCT") >= 0.170:
        return "guard"
    return "wing"


def map_player_profile(base: Dict[str, Any], advanced: Dict[str, Any]) -> Dict[str, Any]:
    """Map traditional and advanced source rows to canonical simulator fields."""

    fga, fg3a, fta = number(base, "FGA"), number(base, "FG3A"), number(base, "FTA")
    fgm, fg3m = number(base, "FGM"), number(base, "FG3M")
    two_attempts, two_makes = fga - fg3a, fgm - fg3m
    events = max(1.0, fga + 0.44 * fta + number(base, "TOV"))
    minutes = max(1.0, number(base, "MIN"))
    possessions_per_minute = 2.25
    return {
        "name": base["PLAYER_NAME"],
        "role": infer_role(advanced),
        "role_source": "heuristic_from_2025_26_advanced_rates",
        "overrides": {
            "mpg": round(minutes, 3),
            "usage": round(rate(advanced, "USG_PCT", 0.20) * 100, 3),
            "two_pct": round(bounded(two_makes / max(1.0, two_attempts), 0.30, 0.80), 4),
            "three_pct": round(bounded(number(base, "FG3_PCT"), 0.20, 0.60), 4),
            "ft_pct": round(bounded(number(base, "FT_PCT"), 0.40, 1.00), 4),
            "three_rate": round(bounded(fg3a / max(1.0, fga), 0.02, 0.85), 4),
            "ftr": round(bounded(fta / max(1.0, fga), 0.02, 0.80), 4),
            "ast_rate": round(bounded(rate(advanced, "AST_PCT", 0.12), 0.02, 0.45), 4),
            "tov_rate": round(bounded(number(base, "TOV") / events, 0.02, 0.30), 4),
            "orb_rate": round(bounded(rate(advanced, "OREB_PCT", 0.04), 0.005, 0.18), 4),
            "drb_rate": round(bounded(rate(advanced, "DREB_PCT", 0.12), 0.04, 0.32), 4),
            "stl_rate": round(bounded(number(base, "STL") / (minutes * possessions_per_minute), 0.002, 0.05), 4),
            "blk_rate": round(bounded(number(base, "BLK") / (minutes * possessions_per_minute), 0.001, 0.10), 4),
            "foul_rate": round(bounded(number(base, "PF") / (minutes * possessions_per_minute), 0.01, 0.12), 4),
        },
        "source_stats": {"traditional_per_game": base, "advanced_per_game": advanced},
    }


def target_rows(rows: Iterable[Dict[str, Any]], teams: Iterable[str]) -> List[Dict[str, Any]]:
    """Filter source rows to selected team abbreviations."""

    team_set = set(teams)
    return [row for row in rows if row.get("TEAM_ABBREVIATION") in team_set and number(row, "GP") > 0]


def build_payload(season: str, teams: List[str]) -> Dict[str, Any]:
    """Retrieve source feeds and build one versioned canonical team payload."""

    base_rows = target_rows(fetch_table("leaguedashplayerstats", dashboard_params(season, "Base")), teams)
    advanced_rows = target_rows(fetch_table("leaguedashplayerstats", dashboard_params(season, "Advanced")), teams)
    all_team_rows = fetch_table("leaguedashteamstats", dashboard_params(season, "Advanced"))
    advanced_by_key = {(row["PLAYER_ID"], row["TEAM_ID"]): row for row in advanced_rows}
    team_code_by_id = {row["TEAM_ID"]: row["TEAM_ABBREVIATION"] for row in base_rows}
    team_rows = [row for row in all_team_rows if row["TEAM_ID"] in team_code_by_id]
    players_by_team: Dict[str, List[Dict[str, Any]]] = {team: [] for team in teams}
    for base in base_rows:
        advanced = advanced_by_key.get((base["PLAYER_ID"], base["TEAM_ID"]))
        if advanced is not None:
            players_by_team[base["TEAM_ABBREVIATION"]].append(map_player_profile(base, advanced))

    team_by_code = {team_code_by_id[row["TEAM_ID"]]: row for row in team_rows}
    missing = [team for team in teams if not players_by_team[team] or team not in team_by_code]
    if missing:
        raise RuntimeError(f"Missing player or team rows for: {', '.join(missing)}")
    return {
        "metadata": {
            "dataset_id": f"historical_base_{season.replace('-', '_')}_regular_season",
            "source_type": "historical",
            "default_simulator_input": True,
            "season": season,
            "season_type": "Regular Season",
            "teams": teams,
            "source": "NBA Stats dashboard endpoints",
            "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
            "mapping_note": "Raw source fields are retained. Simulator-only fields are calculated by the optional historical enrichment layer without predictive modeling.",
        },
        "teams": [
            {
                "abbreviation": team,
                "name": team_by_code[team]["TEAM_NAME"],
                "team_advanced_stats": team_by_code[team],
                "roster": sorted(players_by_team[team], key=lambda player: player["overrides"]["mpg"], reverse=True),
            }
            for team in teams
        ],
    }


def main() -> None:
    """Parse pull options, build historical profiles, and write JSON outputs."""

    command = argparse.ArgumentParser(description="Pull NBA regular-season data for real simulator teams.")
    command.add_argument("--season", default="2025-26")
    command.add_argument("--teams", nargs="+", default=list(INITIAL_TEAMS), metavar="ABBREVIATION")
    command.add_argument("--all-teams", action="store_true", help="Build profiles for all 30 NBA teams.")
    command.add_argument("--output", default=str(DEFAULT_OUTPUT))
    command.add_argument("--enrichment-raw-output", default=str(DEFAULT_ENRICHMENT_RAW_OUTPUT))
    command.add_argument("--skip-enrichment", action="store_true", help="Pull only traditional and advanced historical profiles.")
    command.add_argument("--strict-enrichment", action="store_true", help="Fail if any official enrichment feed is unavailable.")
    command.add_argument("--rebuild-enrichment-from-existing", action="store_true", help="Recalculate enrichment from the existing output and retained raw feeds without making network requests.")
    args = command.parse_args()
    output = Path(args.output)
    if args.rebuild_enrichment_from_existing:
        if not output.exists():
            raise FileNotFoundError(f"Existing team payload not found: {output}")
        raw_output = Path(args.enrichment_raw_output)
        if not raw_output.exists():
            raise FileNotFoundError(f"Retained enrichment feeds not found: {raw_output}")
        payload = json.loads(output.read_text(encoding="utf-8"))
        feeds = json.loads(raw_output.read_text(encoding="utf-8"))
        payload = calculate_historical_enrichment(payload, feeds)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Rebuilt historical enrichment for {len(payload['teams'])} teams at {output}")
        return
    selected_teams = list(NBA_TEAMS) if args.all_teams else [team.upper() for team in args.teams]
    payload = build_payload(args.season, selected_teams)
    if not args.skip_enrichment:
        feeds = fetch_enrichment_feeds(args.season, fetch_table, allow_partial=not args.strict_enrichment)
        raw_output = Path(args.enrichment_raw_output)
        raw_output.parent.mkdir(parents=True, exist_ok=True)
        raw_output.write_text(json.dumps(feeds, indent=2), encoding="utf-8")
        payload = calculate_historical_enrichment(payload, feeds)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {len(payload['teams'])} historical teams to {output}")


if __name__ == "__main__":
    main()
