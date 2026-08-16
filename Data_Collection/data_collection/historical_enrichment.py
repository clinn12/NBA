"""Transparent historical calculations for simulator-only player attributes.

Front Matter
------------
Project: NBA Data Collection
File type: Python module
Status: Active
Last updated: 2026-08-14

Purpose: derive bounded defense, stamina, clutch, movement, and role attributes
from historical NBA aggregates without fitting a predictive model.
Usage: data-pull workflows call ``fetch_enrichment_feeds`` and
``calculate_historical_enrichment`` before publishing canonical player inputs.
Every formula uses sample-size shrinkage toward a neutral league value.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import math
import statistics
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FORMULA_VERSION = "historical_enrichment_v2"
ENRICHED_FIELDS = (
    "defense", "switchability", "help_defense", "stamina", "clutch",
    "rim_pressure", "off_ball_gravity",
)


def _number(row: Optional[Mapping[str, Any]], *keys: str, default: float = 0.0) -> float:
    if not row:
        return default
    for key in keys:
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                continue
    return default


def _bounded(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _reliability(sample: float, prior_weight: float) -> float:
    return _bounded(sample / (sample + prior_weight), 0.0, 1.0)


def _mean_sd(values: Iterable[float]) -> Tuple[float, float]:
    observed = [float(value) for value in values if math.isfinite(float(value))]
    if not observed:
        return 0.0, 1.0
    mean = statistics.fmean(observed)
    sd = statistics.pstdev(observed)
    return mean, sd if sd > 1e-9 else 1.0


def _z(value: float, distribution: Tuple[float, float]) -> float:
    return _bounded((value - distribution[0]) / distribution[1], -3.0, 3.0)


def _row_key(row: Mapping[str, Any]) -> Tuple[int, int]:
    # Player-defense dashboards use CLOSE_DEF_PERSON_ID and PLAYER_LAST_TEAM_ID,
    # while the other tracking dashboards use PLAYER_ID and TEAM_ID.
    return (
        int(_number(row, "PLAYER_ID", "CLOSE_DEF_PERSON_ID")),
        int(_number(row, "TEAM_ID", "PLAYER_LAST_TEAM_ID")),
    )


def _index(rows: Sequence[Mapping[str, Any]]) -> Dict[Tuple[int, int], Mapping[str, Any]]:
    return {_row_key(row): row for row in rows if _number(row, "PLAYER_ID", "CLOSE_DEF_PERSON_ID")}


def _tracking_params(season: str, measure: str) -> Dict[str, Any]:
    return {
        "College": "", "Conference": "", "Country": "", "DateFrom": "", "DateTo": "",
        "Division": "", "DraftPick": "", "DraftYear": "", "GameScope": "", "Height": "",
        "LastNGames": 0, "LeagueID": "00", "Location": "", "Month": 0, "OpponentTeamID": 0,
        "Outcome": "", "PORound": 0, "PerMode": "PerGame", "PlayerExperience": "",
        "PlayerOrTeam": "Player", "PlayerPosition": "", "PtMeasureType": measure, "Season": season,
        "SeasonSegment": "", "SeasonType": "Regular Season", "StarterBench": "", "TeamID": 0,
        "VsConference": "", "VsDivision": "", "Weight": "",
    }


def _defense_params(season: str, category: str = "Overall") -> Dict[str, Any]:
    return {
        "College": "", "Conference": "", "Country": "", "DateFrom": "", "DateTo": "",
        "DefenseCategory": category, "Division": "", "DraftPick": "", "DraftYear": "",
        "GameSegment": "", "Height": "", "LastNGames": 0, "LeagueID": "00", "Location": "",
        "Month": 0, "OpponentTeamID": 0, "Outcome": "", "PORound": 0, "PerMode": "PerGame",
        "Period": 0, "PlayerExperience": "", "PlayerPosition": "", "Season": season,
        "SeasonSegment": "", "SeasonType": "Regular Season", "StarterBench": "", "TeamID": 0,
        "VsConference": "", "VsDivision": "", "Weight": "",
    }


def _clutch_params(season: str) -> Dict[str, Any]:
    return {
        "AheadBehind": "Ahead or Behind", "ClutchTime": "Last 5 Minutes", "College": "",
        "Conference": "", "Country": "", "DateFrom": "", "DateTo": "", "Division": "",
        "DraftPick": "", "DraftYear": "", "GameScope": "", "GameSegment": "", "Height": "",
        "LastNGames": 0, "LeagueID": "00", "Location": "", "MeasureType": "Base", "Month": 0,
        "OpponentTeamID": 0, "Outcome": "", "PORound": 0, "PaceAdjust": "N", "PerMode": "Totals",
        "Period": 0, "PlayerExperience": "", "PlayerPosition": "", "PlusMinus": "N", "PointDiff": 5,
        "Rank": "N", "Season": season, "SeasonSegment": "", "SeasonType": "Regular Season",
        "ShotClockRange": "", "StarterBench": "", "TeamID": 0, "VsConference": "",
        "VsDivision": "", "Weight": "",
    }


def _hustle_params(season: str) -> Dict[str, Any]:
    return {"LeagueID": "00", "PerMode": "PerGame", "Season": season, "SeasonType": "Regular Season"}


def fetch_enrichment_feeds(season: str, fetch_table: Callable[[str, Dict[str, Any]], List[Dict[str, Any]]], allow_partial: bool = True) -> Dict[str, Any]:
    """Fetch official NBA aggregate feeds while retaining per-feed failures."""
    requests = {
        "defense_overall": ("leaguedashptdefend", _defense_params(season, "Overall")),
        "defense_2pt": ("leaguedashptdefend", _defense_params(season, "2 Pointers")),
        "defense_3pt": ("leaguedashptdefend", _defense_params(season, "3 Pointers")),
        "hustle": ("leaguehustlestatsplayer", _hustle_params(season)),
        "speed_distance": ("leaguedashptstats", _tracking_params(season, "SpeedDistance")),
        "tracking_defense": ("leaguedashptstats", _tracking_params(season, "Defense")),
        "drives": ("leaguedashptstats", _tracking_params(season, "Drives")),
        "catch_shoot": ("leaguedashptstats", _tracking_params(season, "CatchShoot")),
        "clutch": ("leaguedashplayerclutch", _clutch_params(season)),
    }
    feeds: Dict[str, Any] = {"metadata": {"season": season, "pulled_at_utc": datetime.now(timezone.utc).isoformat(), "failures": {}}}
    for name, (endpoint, params) in requests.items():
        try:
            feeds[name] = fetch_table(endpoint, params)
        except Exception as error:
            if not allow_partial:
                raise
            feeds[name] = []
            feeds["metadata"]["failures"][name] = str(error)
    return feeds


def _metric_rows(base_players: Sequence[Mapping[str, Any]], feeds: Mapping[str, Any]) -> List[Dict[str, float]]:
    indexed = {name: _index(feeds.get(name, [])) for name in feeds if isinstance(feeds.get(name), list)}
    metrics = []
    for player in base_players:
        base = player["source_stats"]["traditional_per_game"]
        advanced = player["source_stats"]["advanced_per_game"]
        key = (int(base["PLAYER_ID"]), int(base["TEAM_ID"]))
        defense = indexed.get("defense_overall", {}).get(key, {})
        defense_2 = indexed.get("defense_2pt", {}).get(key, {})
        defense_3 = indexed.get("defense_3pt", {}).get(key, {})
        hustle = indexed.get("hustle", {}).get(key, {})
        speed = indexed.get("speed_distance", {}).get(key, {})
        tracking_defense = indexed.get("tracking_defense", {}).get(key, {})
        drives = indexed.get("drives", {}).get(key, {})
        catch = indexed.get("catch_shoot", {}).get(key, {})
        clutch = indexed.get("clutch", {}).get(key, {})
        minutes = max(1.0, _number(base, "MIN"))
        contested_2 = _number(hustle, "CONTESTED_SHOTS_2PT", "CONTESTED_2PT_SHOTS")
        contested_3 = _number(hustle, "CONTESTED_SHOTS_3PT", "CONTESTED_3PT_SHOTS")
        clutch_attempts = _number(clutch, "FGA") + 0.44 * _number(clutch, "FTA")
        clutch_ts = _number(clutch, "TS_PCT") or _ratio(_number(clutch, "PTS"), 2 * clutch_attempts)
        metrics.append({
            "player_id": _number(base, "PLAYER_ID"), "team_id": _number(base, "TEAM_ID"),
            "gp": _number(base, "GP"), "minutes": minutes,
            "def_rating": _number(advanced, "DEF_RATING", "E_DEF_RATING", default=115.0),
            "dfg_diff": _number(defense, "PCT_PLUSMINUS", "PLUSMINUS", default=0.0),
            "dfga": _number(defense, "D_FGA", "DFGA"),
            "dfg2_diff": _number(defense_2, "PCT_PLUSMINUS", "PLUSMINUS", default=0.0),
            "dfg3_diff": _number(defense_3, "PCT_PLUSMINUS", "PLUSMINUS", default=0.0),
            "deflections": _number(hustle, "DEFLECTIONS"),
            "contested_2": contested_2, "contested_3": contested_3,
            "charges": _number(hustle, "CHARGES_DRAWN"), "loose_balls": _number(hustle, "LOOSE_BALLS_RECOVERED"),
            "rim_dfg": _number(tracking_defense, "DEF_RIM_FG_PCT", default=0.0),
            "rim_dfga": _number(tracking_defense, "DEF_RIM_FGA"),
            "distance": _number(speed, "DIST_MILES"), "avg_speed": _number(speed, "AVG_SPEED"),
            "drives": _number(drives, "DRIVES"), "drive_fta": _number(drives, "DRIVE_FTA"),
            "drive_pts": _number(drives, "DRIVE_PTS"),
            "catch_fga": _number(catch, "CATCH_SHOOT_FGA"), "catch_3pm": _number(catch, "CATCH_SHOOT_FG3M"),
            "catch_3pa": _number(catch, "CATCH_SHOOT_FG3A"),
            "clutch_min": _number(clutch, "MIN"), "clutch_ts": clutch_ts,
            "base_ts": _number(advanced, "TS_PCT"), "ftr": _ratio(_number(base, "FTA"), max(1.0, _number(base, "FGA"))),
            "stl": _number(base, "STL"), "blk": _number(base, "BLK"),
        })
    return metrics


def calculate_historical_enrichment(payload: Mapping[str, Any], feeds: Mapping[str, Any]) -> Dict[str, Any]:
    """Return an enriched copy of a canonical historical team-profile payload."""
    result = copy.deepcopy(payload)
    players = [player for team in result["teams"] for player in team["roster"]]
    metrics = _metric_rows(players, feeds)
    distributions = {
        name: _mean_sd(row[name] for row in metrics)
        for name in (
            "def_rating", "dfg_diff", "deflections", "contested_2", "contested_3", "charges",
            "rim_dfg", "distance", "avg_speed", "drives", "drive_fta", "catch_fga", "catch_3pa",
            "minutes", "gp", "stl", "blk", "ftr",
        )
    }
    metric_by_key = {(int(row["player_id"]), int(row["team_id"])): row for row in metrics}
    for team in result["teams"]:
        for player in team["roster"]:
            base = player["source_stats"]["traditional_per_game"]
            key = (int(base["PLAYER_ID"]), int(base["TEAM_ID"]))
            row = metric_by_key[key]
            general_rel = _reliability(row["gp"], 20.0)
            defense_rel = _reliability(row["dfga"], 200.0) if row["dfga"] else general_rel * 0.55
            tracking_rel = general_rel if row["distance"] or row["drives"] else general_rel * 0.45
            clutch_rel = _reliability(row["clutch_min"], 100.0)
            defense_components = {
                "def_rating": -_z(row["def_rating"], distributions["def_rating"]),
                "dfg_diff": -_z(row["dfg_diff"], distributions["dfg_diff"]),
                "deflections": _z(row["deflections"], distributions["deflections"]),
                "contests": 0.5 * _z(row["contested_2"], distributions["contested_2"]) + 0.5 * _z(row["contested_3"], distributions["contested_3"]),
                "stocks": 0.5 * _z(row["stl"], distributions["stl"]) + 0.5 * _z(row["blk"], distributions["blk"]),
            }
            defense_index = defense_rel * (
                0.30 * defense_components["def_rating"] + 0.25 * defense_components["dfg_diff"] +
                0.20 * defense_components["deflections"] + 0.15 * defense_components["contests"] +
                0.10 * defense_components["stocks"]
            )
            contest_total = row["contested_2"] + row["contested_3"]
            contest_balance = 2 * min(row["contested_2"], row["contested_3"]) / contest_total if contest_total else 0.0
            switch_index = general_rel * (
                0.45 * _z(contest_balance, _mean_sd(
                    2 * min(item["contested_2"], item["contested_3"]) / (item["contested_2"] + item["contested_3"])
                    if item["contested_2"] + item["contested_3"] else 0.0 for item in metrics
                )) + 0.30 * defense_components["deflections"] + 0.25 * defense_components["def_rating"]
            )
            help_index = general_rel * (
                0.30 * defense_components["deflections"] + 0.25 * _z(row["contested_2"], distributions["contested_2"]) +
                0.20 * _z(row["blk"], distributions["blk"]) + 0.15 * _z(row["charges"], distributions["charges"]) +
                0.10 * defense_components["dfg_diff"]
            )
            stamina_index = general_rel * (
                0.55 * _z(row["minutes"], distributions["minutes"]) + 0.20 * _z(row["gp"], distributions["gp"]) +
                0.15 * _z(row["distance"], distributions["distance"]) + 0.10 * _z(row["avg_speed"], distributions["avg_speed"])
            )
            clutch_delta = row["clutch_ts"] - row["base_ts"] if row["clutch_ts"] and row["base_ts"] else 0.0
            rim_index = tracking_rel * (
                0.45 * _z(row["drives"], distributions["drives"]) + 0.25 * _z(row["drive_fta"], distributions["drive_fta"]) +
                0.30 * _z(row["ftr"], distributions["ftr"])
            )
            catch_accuracy = _ratio(row["catch_3pm"], row["catch_3pa"])
            gravity_index = tracking_rel * (
                0.55 * _z(row["catch_3pa"], distributions["catch_3pa"]) + 0.25 * _z(row["catch_fga"], distributions["catch_fga"]) +
                0.20 * _bounded((catch_accuracy - 0.36) / 0.08, -3.0, 3.0)
            )
            calculated = {
                "defense": round(_bounded(defense_index * 0.70, -2.0, 2.0), 4),
                "switchability": round(_bounded(switch_index * 0.60, -1.0, 2.0), 4),
                "help_defense": round(_bounded(help_index * 0.65, -1.0, 2.0), 4),
                "stamina": round(_bounded(0.86 + stamina_index * 0.035, 0.70, 0.98), 4),
                "clutch": round(_bounded(clutch_delta * 5.0 * clutch_rel, -1.0, 1.0), 4),
                "rim_pressure": round(_bounded(rim_index * 0.70, -1.0, 2.0), 4),
                "off_ball_gravity": round(_bounded(gravity_index * 0.70, -1.0, 2.0), 4),
            }
            player["overrides"].update(calculated)
            player["source_stats"]["historical_enrichment"] = {
                "formula_version": FORMULA_VERSION,
                "calculated_fields": calculated,
                "reliability": {
                    "general": round(general_rel, 4), "defense": round(defense_rel, 4),
                    "tracking": round(tracking_rel, 4), "clutch": round(clutch_rel, 4),
                },
                "components": {name: round(value, 6) for name, value in row.items() if name not in {"player_id", "team_id"}},
                "interpretation": "Transparent historical calculation with shrinkage to neutral; not a fitted predictive model.",
            }
    metadata = result.setdefault("metadata", {})
    metadata.update({
        "dataset_id": f"historical_enriched_{metadata.get('season', 'unknown').replace('-', '_')}_regular_season",
        "source_type": "historical",
        "default_simulator_input": True,
        "formula_version": FORMULA_VERSION,
        "enriched_at_utc": datetime.now(timezone.utc).isoformat(),
        "enriched_fields": list(ENRICHED_FIELDS),
        "enrichment_method": "Deterministic league-normalized formulas with sample-size shrinkage; no field-specific predictive models.",
        "feed_failures": dict(feeds.get("metadata", {}).get("failures", {})),
    })
    return result
