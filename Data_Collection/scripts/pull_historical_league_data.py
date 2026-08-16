"""Pull full-league regular-season logs and optionally hydrate exact starters.

Front Matter
------------
Project: NBA Data Collection
File type: Python script
Status: Active
Last updated: 2026-08-14

Purpose: retain authoritative player/team game totals and resumable official
box-score starter/active-player records for dated feature construction.
Usage: run ``python scripts/pull_historical_league_data.py``. Player logs may be
reused, and starter hydration is optional, checkpointed, conservatively paced,
status-aware, and single-worker because the NBA endpoints restrict automation.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import shutil
import time
from typing import Any, Dict, Iterable, List, Mapping
from urllib.parse import urlencode

import requests

try:
    from ._project_paths import PROJECT_ROOT
except ImportError:  # Direct execution
    from _project_paths import PROJECT_ROOT

from scripts.build_historical_variability import fetch_game_logs, numeric
from scripts.pull_real_team_data import NBA_STATS_BASE, REQUEST_HEADERS


DEFAULT_PLAYER_LOGS = PROJECT_ROOT / "data/raw/player_game_logs_2025-26_regular_season_all.json"
DEFAULT_TEAM_LOGS = PROJECT_ROOT / "data/raw/team_game_logs_2025-26_regular_season_all.json"
DEFAULT_STARTERS = PROJECT_ROOT / "data/raw/game_starters_2025-26_regular_season_all.json"
DEFAULT_ATTEMPT_LOG = PROJECT_ROOT / "data/raw/starter_hydration_attempts.jsonl"
TEAM_FIELDS = ("FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "PTS")
LIVE_BOXSCORE = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
SESSION_HEADERS = {
    **REQUEST_HEADERS,
    "Connection": "keep-alive",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
ACCESS_DENIED_STATUS_CODES = {403}


class StarterRequestError(RuntimeError):
    """Describe a starter-source failure with retry and HTTP diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
        response_excerpt: str | None = None,
    ) -> None:
        """Store status-aware diagnostics without retaining full response bodies."""

        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.response_excerpt = response_excerpt


def build_http_session() -> requests.Session:
    """Return one persistent, consistently headed session for a hydration run."""

    session = requests.Session()
    session.headers.update(SESSION_HEADERS)
    return session


def _retry_after_seconds(value: str | None) -> float | None:
    """Parse a numeric Retry-After header while safely ignoring date formats."""

    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def request_json(
    session: requests.Session,
    url: str,
    *,
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Request JSON once and raise a status-aware error for policy decisions."""

    try:
        response = session.get(url, timeout=timeout_seconds)
    except requests.Timeout as error:
        raise StarterRequestError("Request timed out", retryable=True) from error
    except requests.ConnectionError as error:
        raise StarterRequestError("Connection failed", retryable=True) from error
    excerpt = response.text[:300].replace("\n", " ").strip() or None
    if response.status_code != 200:
        raise StarterRequestError(
            f"HTTP {response.status_code}",
            status_code=response.status_code,
            retryable=response.status_code in TRANSIENT_STATUS_CODES,
            retry_after_seconds=_retry_after_seconds(response.headers.get("Retry-After")),
            response_excerpt=excerpt,
        )
    try:
        payload = response.json()
    except requests.JSONDecodeError as error:
        raise StarterRequestError(
            "Response was not valid JSON", response_excerpt=excerpt,
        ) from error
    if not isinstance(payload, dict):
        raise StarterRequestError("Expected a JSON object response")
    return payload


def append_attempt_log(path: Path | None, record: Mapping[str, Any]) -> None:
    """Append one compact JSON request-attempt record when logging is enabled."""

    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True) + "\n")


def snapshot_checkpoint(output: Path, run_id: str) -> Path | None:
    """Copy the pre-run checkpoint into its raw-data archive when it exists."""

    if not output.exists():
        return None
    archive = output.parent / "__Archive__"
    archive.mkdir(parents=True, exist_ok=True)
    destination = archive / f"{output.stem}__pre_resume_{run_id}{output.suffix}"
    shutil.copy2(output, destination)
    return destination


def build_team_logs(player_logs: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate player game logs into one auditable team row per game and side."""

    grouped: Dict[tuple[str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for row in player_logs:
        grouped[(str(row["GAME_ID"]), str(row["TEAM_ABBREVIATION"]))].append(row)
    result = []
    for (game_id, abbreviation), rows in grouped.items():
        first = rows[0]
        totals = {field: round(sum(numeric(row.get(field)) for row in rows), 4) for field in TEAM_FIELDS}
        totals["POSS_EST"] = round(totals["FGA"] + 0.44 * totals["FTA"] - totals["OREB"] + totals["TOV"], 4)
        result.append({
            "GAME_ID": game_id, "GAME_DATE": first["GAME_DATE"], "TEAM_ID": first["TEAM_ID"],
            "TEAM_ABBREVIATION": abbreviation, "TEAM_NAME": first["TEAM_NAME"], "MATCHUP": first["MATCHUP"],
            "HOME": " vs. " in str(first["MATCHUP"]), "WL": first.get("WL"), **totals,
        })
    return sorted(result, key=lambda row: (row["GAME_DATE"], row["GAME_ID"], row["TEAM_ABBREVIATION"]))


def fetch_starters_live(
    game_id: str,
    *,
    session: requests.Session,
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Fetch starters from the NBA live-data CDN compatibility endpoint."""

    payload = request_json(
        session, LIVE_BOXSCORE.format(game_id=game_id),
        timeout_seconds=timeout_seconds,
    )
    game = payload.get("game")
    if not isinstance(game, dict):
        raise StarterRequestError("Live CDN response did not contain a game object")
    teams: Dict[str, Any] = {}
    for side in ("homeTeam", "awayTeam"):
        team = game[side]
        players = team.get("players", [])
        teams[str(team["teamTricode"])] = {
            "team_id": team.get("teamId"),
            "starters": [player["name"] for player in players if player.get("starter") == "1"],
            "active_players": [player["name"] for player in players if player.get("played") == "1"],
            "players": [{"player_id": player.get("personId"), "player": player.get("name"), "starter": player.get("starter") == "1", "played": player.get("played") == "1"} for player in players],
        }
    return {"game_id": game_id, "game_time_utc": game.get("gameTimeUTC"), "teams": teams}


def fetch_starters_stats(
    game_id: str,
    *,
    session: requests.Session,
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Fetch starters through the legacy NBA Stats v2 box-score endpoint."""

    params = {
        "EndPeriod": 10, "EndRange": 28800, "GameID": game_id,
        "RangeType": 0, "StartPeriod": 1, "StartRange": 0,
    }
    payload = request_json(
        session, f"{NBA_STATS_BASE}boxscoretraditionalv2?{urlencode(params)}",
        timeout_seconds=timeout_seconds,
    )
    result_sets = payload.get("resultSets") or payload.get("resultSet")
    if isinstance(result_sets, dict):
        result_sets = [result_sets]
    if not result_sets:
        raise StarterRequestError("NBA Stats v2 returned no result set")
    result_set = result_sets[0]
    headers = result_set.get("headers") or result_set.get("Headers")
    values = result_set.get("rowSet") or result_set.get("RowSet")
    if not headers or values is None:
        raise StarterRequestError("Unexpected NBA Stats v2 response shape")
    rows = [dict(zip(headers, row)) for row in values]
    teams: Dict[str, Any] = {}
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["TEAM_ABBREVIATION"])].append(row)
    for abbreviation, players in grouped.items():
        teams[abbreviation] = {
            "team_id": players[0].get("TEAM_ID"),
            "starters": [row["PLAYER_NAME"] for row in players if str(row.get("START_POSITION") or "").strip()],
            "active_players": [row["PLAYER_NAME"] for row in players if row.get("MIN") not in (None, "") and not row.get("COMMENT")],
            "players": [{"player_id": row.get("PLAYER_ID"), "player": row.get("PLAYER_NAME"), "starter": bool(str(row.get("START_POSITION") or "").strip()), "played": row.get("MIN") not in (None, "") and not row.get("COMMENT"), "start_position": row.get("START_POSITION")} for row in players],
        }
    if len(teams) != 2:
        raise RuntimeError(f"Expected two teams in boxscoretraditionalv2 for {game_id}, received {len(teams)}")
    return {"game_id": game_id, "game_time_utc": None, "teams": teams}


def fetch_starters_stats_v3(
    game_id: str,
    *,
    session: requests.Session,
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Fetch exact starters and active players from the current NBA Stats box score."""

    query = urlencode({"GameID": game_id, "LeagueID": "00"})
    payload = request_json(
        session, f"{NBA_STATS_BASE}boxscoretraditionalv3?{query}",
        timeout_seconds=timeout_seconds,
    )
    boxscore = payload.get("boxScoreTraditional")
    if not isinstance(boxscore, dict):
        raise StarterRequestError("NBA Stats v3 response omitted boxScoreTraditional")
    teams: Dict[str, Any] = {}
    for side in ("homeTeam", "awayTeam"):
        team = boxscore[side]
        normalized_players = []
        for player in team.get("players", []):
            position = str(player.get("position") or "").strip()
            minutes = player.get("statistics", {}).get("minutes") or ""
            name = f"{player.get('firstName') or ''} {player.get('familyName') or ''}".strip()
            normalized_players.append({
                "player_id": player.get("personId"),
                "player": name,
                "starter": bool(position),
                "played": bool(minutes),
                "start_position": position,
                "comment": player.get("comment"),
            })
        abbreviation = str(team["teamTricode"])
        teams[abbreviation] = {
            "team_id": team.get("teamId"),
            "starters": [player["player"] for player in normalized_players if player["starter"]],
            "active_players": [player["player"] for player in normalized_players if player["played"]],
            "players": normalized_players,
        }
    if len(teams) != 2:
        raise RuntimeError(f"Expected two teams in boxscoretraditionalv3 for {game_id}, received {len(teams)}")
    return {"game_id": game_id, "game_time_utc": None, "teams": teams}


def plan_starter_hydration(
    game_ids: List[str],
    cache: Mapping[str, Any],
    *,
    limit: int | None = None,
    batch_size: int | None = 25,
    diagnostic_game_id: str | None = None,
) -> Dict[str, Any]:
    """Return the unresolved games that a safe hydration run would request."""

    unique_game_ids = list(dict.fromkeys(str(game_id) for game_id in game_ids))
    if diagnostic_game_id and diagnostic_game_id not in unique_game_ids:
        raise ValueError(f"Diagnostic game {diagnostic_game_id} is not in the retained logs")
    scoped = unique_game_ids[:limit] if limit is not None else unique_game_ids
    hydrated = cache.get("games", {})
    unresolved = [game_id for game_id in scoped if game_id not in hydrated]
    if diagnostic_game_id:
        selected = [diagnostic_game_id] if diagnostic_game_id not in hydrated else []
    else:
        selected = unresolved[:batch_size] if batch_size is not None else unresolved
    return {
        "total_games_available": len(unique_game_ids),
        "scoped_games": len(scoped),
        "already_hydrated": len(hydrated),
        "unresolved_in_scope": len(unresolved),
        "selected_games": selected,
        "diagnostic_game_id": diagnostic_game_id,
    }


def hydrate_starters(
    game_ids: List[str],
    output: Path,
    delay_seconds: float | None = None,
    limit: int | None = None,
    source: str = "nba_stats_v3",
    workers: int = 1,
    *,
    min_delay_seconds: float = 3.0,
    max_delay_seconds: float = 6.0,
    batch_size: int | None = 25,
    max_retries: int = 2,
    access_denial_limit: int = 2,
    timeout_seconds: float = 45.0,
    attempt_log: Path | None = DEFAULT_ATTEMPT_LOG,
    diagnostic_game_id: str | None = None,
    snapshot_before_run: bool = True,
    jitter_seed: int | None = None,
) -> Dict[str, Any]:
    """Safely resume exact-starter hydration from an auditable checkpoint.

    The routine requests only unresolved games, snapshots the checkpoint, uses
    one persistent session, retries only transient failures, stops after repeated
    access denials, and saves after every attempted game. ``delay_seconds`` is a
    backward-compatible fixed-delay override for deterministic tests.
    """

    if workers != 1:
        raise ValueError("Starter hydration requires --workers 1 to protect the source")
    if min_delay_seconds < 0 or max_delay_seconds < min_delay_seconds:
        raise ValueError("Delay bounds must satisfy 0 <= min <= max")
    if batch_size is not None and batch_size < 1:
        raise ValueError("batch_size must be positive or None")
    if max_retries < 0 or access_denial_limit < 1:
        raise ValueError("Retry count must be nonnegative and denial limit positive")
    if delay_seconds is not None:
        min_delay_seconds = max_delay_seconds = max(0.0, delay_seconds)

    if output.exists():
        cache = json.loads(output.read_text(encoding="utf-8"))
    else:
        cache = {
            "metadata": {
                "source": "Official NBA box-score endpoints",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            "games": {}, "failures": {}, "failure_details": {},
        }
    cache.setdefault("games", {})
    cache.setdefault("failures", {})
    cache.setdefault("failure_details", {})
    plan = plan_starter_hydration(
        game_ids, cache, limit=limit, batch_size=batch_size,
        diagnostic_game_id=diagnostic_game_id,
    )
    pending = list(plan["selected_games"])
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot = snapshot_checkpoint(output, run_id) if pending and snapshot_before_run else None
    rng = random.Random(jitter_seed)
    fetchers = {
        "nba_stats_v3": fetch_starters_stats_v3,
        "nba_stats_v2": fetch_starters_stats,
        "live_cdn": fetch_starters_live,
    }
    fetcher = fetchers[source]
    attempted_games = 0
    successful_this_run = 0
    consecutive_access_denials = 0
    stopped_reason: str | None = None

    with build_http_session() as session:
        for game_index, game_id in enumerate(pending):
            attempted_games += 1
            final_error: Exception | None = None
            final_status: int | None = None
            for attempt in range(1, max_retries + 2):
                started = time.perf_counter()
                try:
                    game_record = fetcher(
                        game_id, session=session, timeout_seconds=timeout_seconds,
                    )
                    game_record["source"] = source
                    game_record["retrieved_at_utc"] = datetime.now(timezone.utc).isoformat()
                    cache["games"][game_id] = game_record
                    cache["failures"].pop(game_id, None)
                    cache["failure_details"].pop(game_id, None)
                    successful_this_run += 1
                    consecutive_access_denials = 0
                    append_attempt_log(attempt_log, {
                        "attempt": attempt, "elapsed_seconds": round(time.perf_counter() - started, 4),
                        "game_id": game_id, "outcome": "success", "run_id": run_id,
                        "source": source, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    })
                    final_error = None
                    break
                except Exception as error:
                    final_error = error
                    final_status = getattr(error, "status_code", None)
                    retryable = bool(getattr(error, "retryable", False))
                    retry_after = getattr(error, "retry_after_seconds", None)
                    append_attempt_log(attempt_log, {
                        "attempt": attempt, "elapsed_seconds": round(time.perf_counter() - started, 4),
                        "error": str(error), "error_type": type(error).__name__,
                        "game_id": game_id, "outcome": "failure", "retryable": retryable,
                        "retry_after_seconds": retry_after, "run_id": run_id, "source": source,
                        "response_excerpt": getattr(error, "response_excerpt", None),
                        "status_code": final_status,
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    })
                    if not retryable or attempt > max_retries:
                        break
                    backoff = retry_after
                    if backoff is None:
                        backoff = min(max_delay_seconds, min_delay_seconds * (2 ** (attempt - 1)))
                    if backoff:
                        time.sleep(backoff)

            if final_error is not None:
                cache["failures"][game_id] = f"{type(final_error).__name__}: {final_error}"
                cache["failure_details"][game_id] = {
                    "attempted_at_utc": datetime.now(timezone.utc).isoformat(),
                    "error": str(final_error), "error_type": type(final_error).__name__,
                    "source": source, "status_code": final_status,
                }
                if final_status in ACCESS_DENIED_STATUS_CODES:
                    consecutive_access_denials += 1
                else:
                    consecutive_access_denials = 0

            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(cache, indent=2), encoding="utf-8")
            if consecutive_access_denials >= access_denial_limit:
                stopped_reason = f"circuit_breaker_after_{consecutive_access_denials}_access_denials"
                break
            if game_index < len(pending) - 1:
                delay = rng.uniform(min_delay_seconds, max_delay_seconds)
                if delay:
                    time.sleep(delay)

    metadata = cache["metadata"]
    previous_source = metadata.get("starter_source")
    attempted_sources = set(metadata.get("starter_sources_attempted", []))
    if pending:
        attempted_sources.add(source)
    if previous_source and previous_source != "mixed":
        attempted_sources.add(str(previous_source))
    successful_sources = set(metadata.get("successful_sources", []))
    if previous_source and previous_source != "mixed":
        successful_sources.add(str(previous_source))
    if successful_this_run:
        successful_sources.add(source)
    metadata.update({
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "games_requested": attempted_games,
        "total_games_available": len(game_ids),
        "games_hydrated": len(cache["games"]),
        "last_attempted_source": source if pending else metadata.get("last_attempted_source"),
        "starter_sources_attempted": sorted(attempted_sources),
        "successful_sources": sorted(successful_sources),
        "starter_source": (
            next(iter(successful_sources))
            if len(successful_sources) == 1
            else "mixed" if successful_sources else None
        ),
        "last_run": {
            "attempted_games": attempted_games,
            "batch_size": batch_size,
            "checkpoint_snapshot": str(snapshot) if snapshot else None,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "diagnostic_game_id": diagnostic_game_id,
            "planned_games": len(pending),
            "run_id": run_id,
            "source": source,
            "stopped_reason": stopped_reason,
            "successful_games": successful_this_run,
        },
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return cache


def main() -> None:
    """Pull or reuse full-league logs and optionally hydrate starter records."""

    parser = argparse.ArgumentParser(description="Pull full-league player/team logs and optional exact starters.")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--player-output", default=str(DEFAULT_PLAYER_LOGS))
    parser.add_argument("--team-output", default=str(DEFAULT_TEAM_LOGS))
    parser.add_argument("--starter-output", default=str(DEFAULT_STARTERS))
    parser.add_argument("--reuse-player-logs", action="store_true")
    parser.add_argument("--hydrate-starters", action="store_true")
    parser.add_argument("--starter-limit", type=int, help="Backward-compatible cap on the ordered game-ID scope.")
    parser.add_argument("--batch-size", type=int, default=25, help="Maximum unresolved games to request in this run.")
    parser.add_argument("--delay-seconds", type=float, help="Use one fixed delay instead of the jitter range; mainly for tests.")
    parser.add_argument("--min-delay-seconds", type=float, default=3.0)
    parser.add_argument("--max-delay-seconds", type=float, default=6.0)
    parser.add_argument("--max-retries", type=int, default=2, help="Retries for transient failures only; HTTP 403 is never retried.")
    parser.add_argument("--access-denial-limit", type=int, default=2, help="Stop after this many consecutive HTTP 403 responses.")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--workers", type=int, choices=[1], default=1, help="Starter hydration is intentionally single-worker.")
    parser.add_argument("--starter-source", choices=["nba_stats_v3", "nba_stats_v2", "live_cdn"], default="nba_stats_v3")
    parser.add_argument("--diagnostic-game-id", help="Request exactly one unresolved retained game.")
    parser.add_argument("--attempt-log", default=str(DEFAULT_ATTEMPT_LOG))
    parser.add_argument("--jitter-seed", type=int)
    parser.add_argument("--no-checkpoint-snapshot", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print the hydration plan without making network requests.")
    args = parser.parse_args()
    if args.dry_run and not args.hydrate_starters:
        parser.error("--dry-run requires --hydrate-starters")
    player_output, team_output = Path(args.player_output), Path(args.team_output)
    if args.reuse_player_logs:
        player_logs = json.loads(player_output.read_text(encoding="utf-8"))
    else:
        player_logs = fetch_game_logs(args.season)
        player_output.parent.mkdir(parents=True, exist_ok=True)
        player_output.write_text(json.dumps(player_logs, indent=2), encoding="utf-8")
    team_logs = build_team_logs(player_logs)
    team_output.parent.mkdir(parents=True, exist_ok=True)
    team_output.write_text(json.dumps(team_logs, indent=2), encoding="utf-8")
    summary = {"player_rows": len(player_logs), "team_rows": len(team_logs), "teams": len({row['TEAM_ABBREVIATION'] for row in team_logs}), "games": len({row['GAME_ID'] for row in team_logs})}
    if args.hydrate_starters:
        game_ids = sorted({row["GAME_ID"] for row in team_logs})
        starter_output = Path(args.starter_output)
        existing_cache = (
            json.loads(starter_output.read_text(encoding="utf-8"))
            if starter_output.exists() else {"games": {}}
        )
        plan = plan_starter_hydration(
            game_ids, existing_cache, limit=args.starter_limit,
            batch_size=args.batch_size,
            diagnostic_game_id=args.diagnostic_game_id,
        )
        if args.dry_run:
            summary["hydration_plan"] = plan
        else:
            starters = hydrate_starters(
                game_ids, starter_output, args.delay_seconds, args.starter_limit,
                args.starter_source, args.workers,
                min_delay_seconds=args.min_delay_seconds,
                max_delay_seconds=args.max_delay_seconds,
                batch_size=args.batch_size,
                max_retries=args.max_retries,
                access_denial_limit=args.access_denial_limit,
                timeout_seconds=args.timeout_seconds,
                attempt_log=Path(args.attempt_log) if args.attempt_log else None,
                diagnostic_game_id=args.diagnostic_game_id,
                snapshot_before_run=not args.no_checkpoint_snapshot,
                jitter_seed=args.jitter_seed,
            )
            summary.update({
                "starters_hydrated": len(starters["games"]),
                "starter_failures": len(starters["failures"]),
                "starter_hydration_last_run": starters["metadata"]["last_run"],
            })
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
