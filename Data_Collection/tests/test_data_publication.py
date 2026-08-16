"""Contract tests for governed NBA data-collection publications.

Front Matter
------------
Project: NBA Data Collection
File type: Python test module
Status: Active
Last updated: 2026-08-15

Purpose: verify that published simulator inputs, QA reports, and immutable
dataset snapshots remain present, internally consistent, and independently
usable without importing the NBA Simulator project.
Usage: included in ``python -m unittest discover -s tests -v``; all checks are
local and perform no network calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.enrichment_qa import build_enrichment_qa
from scripts.pull_historical_league_data import (
    StarterRequestError,
    hydrate_starters,
    plan_starter_hydration,
)
from scripts.validate_pregame_dataset import validate
from data_collection.historical_results import build_publication_manifest


PROJECT_DIR = Path(__file__).resolve().parents[1]
PUBLISHED_DIR = PROJECT_DIR / "data/published"


class DataPublicationTests(unittest.TestCase):
    """Verify published inputs, QA gates, and governed snapshot integrity."""

    def test_required_simulator_inputs_are_published(self) -> None:
        """Require the current team, variability, and pregame publications."""

        expected = (
            "real_teams_2025-26_regular_season.json",
            "historical_variability_2025-26_regular_season.json",
            "historical_variability_2025-26_regular_season_all.json",
            "pregame/pregame_profiles_2025-26_regular_season.json",
            "pregame/pregame_profiles_2025-26_regular_season_pilot.json",
            "calibration/pilot_games_2025-26_regular_season.json",
        )
        self.assertEqual([], [name for name in expected if not (PUBLISHED_DIR / name).is_file()])

    def test_pilot_calibration_manifest_matches_publication(self) -> None:
        """Require the structural-only pilot fixture to match its governed hash."""

        manifest = json.loads((PROJECT_DIR / "data/manifests/pilot_calibration_games.json").read_text(encoding="utf-8"))
        publication = PROJECT_DIR / manifest["publication_path"]
        self.assertEqual(16, manifest["games"])
        self.assertFalse(manifest["predictive_backtest_eligible"])
        self.assertEqual(manifest["sha256"], hashlib.sha256(publication.read_bytes()).hexdigest())

    def test_2024_25_season_bundle_is_complete_and_hash_valid(self) -> None:
        """Verify the expanded historical season and every retained artifact digest."""

        manifest_path = PROJECT_DIR / "data/manifests/historical_2024_25_regular_season_bundle.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(26306, manifest["counts"]["player_game_rows"])
        self.assertEqual(2460, manifest["counts"]["team_game_rows"])
        self.assertEqual(30, manifest["counts"]["teams"])
        self.assertEqual(1069, manifest["counts"]["pregame_games"])
        self.assertEqual("pass", manifest["quality"]["pregame_qa"])
        self.assertEqual("pass", manifest["quality"]["enrichment_qa"])
        for artifact in manifest["artifacts"].values():
            path = PROJECT_DIR / artifact["path"]
            self.assertEqual(artifact["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_historical_results_publications_are_governed(self) -> None:
        """Require reusable standings, playoff, and franchise-lineage publications."""

        manifest = build_publication_manifest()
        artifacts = manifest["artifacts"]
        self.assertEqual({"standings", "playoffs", "franchise_lineage"}, set(artifacts))
        self.assertGreaterEqual(artifacts["standings"]["rows"], 1500)
        self.assertGreaterEqual(artifacts["playoffs"]["rows"], 800)
        self.assertEqual(1960, artifacts["standings"]["first_year"])
        self.assertEqual(1960, artifacts["playoffs"]["first_year"])
        for artifact in artifacts.values():
            self.assertEqual(64, len(artifact["sha256"]))

    def test_historical_enrichment_passes_qa(self) -> None:
        """Recalculate QA for the default historical team publication."""

        payload = json.loads((PUBLISHED_DIR / "real_teams_2025-26_regular_season.json").read_text(encoding="utf-8"))
        report = build_enrichment_qa(payload)
        self.assertEqual("historical_enrichment_v2", payload["metadata"]["formula_version"])
        self.assertEqual("pass", report["status"])
        self.assertEqual(72, report["players"])
        self.assertEqual(72, report["source_component_coverage"]["dfga"]["nonzero"])

    def test_full_pregame_publication_passes_quality_gates(self) -> None:
        """Revalidate chronology, leakage, roster shape, and split integrity."""

        payload = json.loads((PUBLISHED_DIR / "pregame/pregame_profiles_2025-26_regular_season.json").read_text(encoding="utf-8"))
        report = validate(payload)
        self.assertEqual("pass", report["status"], report["errors"])
        self.assertEqual(1069, report["games"])
        self.assertEqual(30, report["teams"])

    def test_registry_snapshot_hash(self) -> None:
        """Ensure the registry's default immutable snapshot matches its hash."""

        manifests = PROJECT_DIR / "data/manifests"
        registry = json.loads((manifests / "DATASET_REGISTRY.json").read_text(encoding="utf-8"))
        version_id = registry["default_historical_version"]
        manifest = json.loads((manifests / f"{version_id}.json").read_text(encoding="utf-8"))
        snapshot = Path(manifest["snapshot_path"])
        self.assertTrue(snapshot.is_file())
        self.assertEqual(manifest["sha256"], hashlib.sha256(snapshot.read_bytes()).hexdigest())

    def test_failed_resume_preserves_successful_source_provenance(self) -> None:
        """Keep a failed fallback attempt from relabeling cached successes."""

        cache = {
            "metadata": {"starter_source": "nba_stats_v3"},
            "games": {"existing": {"game_id": "existing", "teams": {}}},
            "failures": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "starters.json"
            path.write_text(json.dumps(cache), encoding="utf-8")
            with patch(
                "scripts.pull_historical_league_data.fetch_starters_stats",
                side_effect=RuntimeError("blocked"),
            ):
                result = hydrate_starters(
                    ["existing", "missing"], path, delay_seconds=0,
                    source="nba_stats_v2", workers=1,
                    attempt_log=Path(directory) / "attempts.jsonl",
                    snapshot_before_run=False,
                )
        self.assertEqual("nba_stats_v3", result["metadata"]["starter_source"])
        self.assertEqual(["nba_stats_v2", "nba_stats_v3"], result["metadata"]["starter_sources_attempted"])
        self.assertIn("missing", result["failures"])

    def test_hydration_plan_selects_only_unresolved_games(self) -> None:
        """Apply diagnostic and batch selection after excluding cached games."""

        cache = {"games": {"g1": {}, "g3": {}}}
        batch = plan_starter_hydration(["g1", "g2", "g3", "g4"], cache, batch_size=1)
        diagnostic = plan_starter_hydration(
            ["g1", "g2", "g3", "g4"], cache,
            batch_size=25, diagnostic_game_id="g4",
        )
        self.assertEqual(["g2"], batch["selected_games"])
        self.assertEqual(["g4"], diagnostic["selected_games"])

    def test_access_denial_circuit_breaker_stops_batch(self) -> None:
        """Stop a batch after consecutive 403 responses without retrying them."""

        denied = StarterRequestError("HTTP 403", status_code=403, retryable=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "starters.json"
            attempt_log = Path(directory) / "attempts.jsonl"
            with patch(
                "scripts.pull_historical_league_data.fetch_starters_stats_v3",
                side_effect=denied,
            ) as fetch:
                result = hydrate_starters(
                    ["g1", "g2", "g3"], path, delay_seconds=0,
                    batch_size=3, access_denial_limit=2,
                    attempt_log=attempt_log, snapshot_before_run=False,
                )
        self.assertEqual(2, fetch.call_count)
        self.assertEqual(2, result["metadata"]["last_run"]["attempted_games"])
        self.assertEqual("circuit_breaker_after_2_access_denials", result["metadata"]["last_run"]["stopped_reason"])
        self.assertNotIn("g3", result["failures"])

    def test_transient_failure_retries_and_logs_success(self) -> None:
        """Retry a temporary rate limit and record both auditable attempts."""

        rate_limited = StarterRequestError(
            "HTTP 429", status_code=429, retryable=True, retry_after_seconds=0,
        )
        success = {"game_id": "g1", "teams": {"AAA": {}, "BBB": {}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "starters.json"
            attempt_log = Path(directory) / "attempts.jsonl"
            with patch(
                "scripts.pull_historical_league_data.fetch_starters_stats_v3",
                side_effect=[rate_limited, success],
            ) as fetch:
                result = hydrate_starters(
                    ["g1"], path, delay_seconds=0, batch_size=1,
                    attempt_log=attempt_log, snapshot_before_run=False,
                )
            attempts = [json.loads(line) for line in attempt_log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(2, fetch.call_count)
        self.assertEqual(["failure", "success"], [row["outcome"] for row in attempts])
        self.assertEqual("nba_stats_v3", result["games"]["g1"]["source"])

    def test_resume_snapshots_existing_checkpoint(self) -> None:
        """Archive the exact pre-run checkpoint before a pending request."""

        cache = {
            "metadata": {"starter_source": "nba_stats_v3"},
            "games": {"existing": {"game_id": "existing", "teams": {}}},
            "failures": {},
        }
        success = {"game_id": "missing", "teams": {"AAA": {}, "BBB": {}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "starters.json"
            path.write_text(json.dumps(cache), encoding="utf-8")
            with patch(
                "scripts.pull_historical_league_data.fetch_starters_stats_v3",
                return_value=success,
            ):
                result = hydrate_starters(
                    ["existing", "missing"], path, delay_seconds=0,
                    attempt_log=Path(directory) / "attempts.jsonl",
                )
            snapshot = Path(result["metadata"]["last_run"]["checkpoint_snapshot"])
            self.assertTrue(snapshot.is_file())
            self.assertEqual(cache, json.loads(snapshot.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
