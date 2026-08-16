"""Build a governed manifest for one full historical-season data bundle.

Front Matter
------------
Project: NBA Data Collection
File type: Python script
Status: Active
Last updated: 2026-08-15

Purpose
-------
Tie raw league logs, enrichment responses, simulator profiles, variability,
dated pregame records, and QA evidence together with immutable SHA-256 hashes.

Usage
-----
Run ``python scripts/build_season_bundle_manifest.py --season 2024-25`` after
all named artifacts have been created and validated for that regular season.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def artifact_paths(season: str) -> dict[str, Path]:
    """Return the canonical raw, published, and QA paths for one season."""

    return {
        "player_game_logs": PROJECT_ROOT / f"data/raw/player_game_logs_{season}_regular_season_all.json",
        "team_game_logs": PROJECT_ROOT / f"data/raw/team_game_logs_{season}_regular_season_all.json",
        "historical_enrichment_raw": PROJECT_ROOT / f"data/raw/historical_enrichment_{season}_regular_season.json",
        "starter_cache": PROJECT_ROOT / f"data/raw/game_starters_{season}_regular_season_all.json",
        "starter_attempt_log": PROJECT_ROOT / f"data/raw/starter_attempts_{season}_regular_season.jsonl",
        "team_profiles": PROJECT_ROOT / f"data/published/real_teams_{season}_regular_season.json",
        "player_variability": PROJECT_ROOT / f"data/published/historical_variability_{season}_regular_season_all.json",
        "pregame_profiles": PROJECT_ROOT / f"data/published/pregame/pregame_profiles_{season}_regular_season.json",
        "pregame_qa": PROJECT_ROOT / f"data/published/pregame/pregame_profiles_{season}_regular_season_qa.json",
        "enrichment_qa_json": PROJECT_ROOT / f"reports/enrichment_qa_{season}_regular_season.json",
        "enrichment_qa_csv": PROJECT_ROOT / f"reports/enrichment_qa_players_{season}_regular_season.csv",
    }


def describe_artifact(path: Path) -> dict[str, Any]:
    """Validate one artifact and return its relative path, size, and digest."""

    if not path.is_file():
        raise FileNotFoundError(f"Season bundle artifact is missing: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": path.relative_to(PROJECT_ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest,
    }


def build_manifest(season: str) -> dict[str, Any]:
    """Build the complete manifest after checking QA and core record counts."""

    paths = artifact_paths(season)
    player_rows = json.loads(paths["player_game_logs"].read_text(encoding="utf-8"))
    team_rows = json.loads(paths["team_game_logs"].read_text(encoding="utf-8"))
    teams = json.loads(paths["team_profiles"].read_text(encoding="utf-8"))
    variability = json.loads(paths["player_variability"].read_text(encoding="utf-8"))
    pregame = json.loads(paths["pregame_profiles"].read_text(encoding="utf-8"))
    pregame_qa = json.loads(paths["pregame_qa"].read_text(encoding="utf-8"))
    enrichment_qa = json.loads(paths["enrichment_qa_json"].read_text(encoding="utf-8"))
    if pregame_qa.get("status") != "pass" or enrichment_qa.get("status") != "pass":
        raise ValueError("Season bundle cannot be governed until both QA reports pass")

    return {
        "manifest_version": "historical_season_bundle_v1",
        "season": season,
        "season_type": "Regular Season",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "player_game_rows": len(player_rows),
            "team_game_rows": len(team_rows),
            "teams": len(teams.get("teams", {})),
            "variability_teams": len(variability.get("teams", {})),
            "pregame_games": len(pregame.get("games", [])),
            "enrichment_qa_players": enrichment_qa.get("players"),
        },
        "quality": {
            "pregame_qa": pregame_qa.get("status"),
            "enrichment_qa": enrichment_qa.get("status"),
            "exact_starter_coverage": pregame_qa.get("exact_actual_starter_coverage"),
            "official_injury_report_games": pregame_qa.get("official_injury_report_games"),
        },
        "artifacts": {name: describe_artifact(path) for name, path in paths.items()},
    }


def write_manifest(season: str, output: Path | None = None) -> dict[str, Any]:
    """Atomically write and return a validated historical-season manifest."""

    manifest = build_manifest(season)
    slug = season.replace("-", "_")
    output = output or PROJECT_ROOT / f"data/manifests/historical_{slug}_regular_season_bundle.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    return manifest


def main() -> None:
    """Parse the season and optional output path, then write its manifest."""

    parser = argparse.ArgumentParser(description="Build a full historical-season publication manifest.")
    parser.add_argument("--season", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    manifest = write_manifest(args.season, Path(args.output) if args.output else None)
    print(json.dumps({"season": args.season, "counts": manifest["counts"], "quality": manifest["quality"]}, indent=2))


if __name__ == "__main__":
    main()
