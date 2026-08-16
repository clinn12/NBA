"""Regression tests for historical QA, versioning, and calibration labels.

Front Matter
------------
Project: NBA Simulator
File type: Python test module
Status: Active
Last updated: 2026-08-14

Purpose: ensure calibrated defaults, enriched source coverage, immutable hashes,
and structural-versus-predictive eligibility remain governed correctly.
Usage: included in ``python -m unittest discover -s tests -v``; it reads retained
project datasets and performs no network calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from scripts.run_calibration import _context
from scripts.run_simulation import load_simulator


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_COLLECTION_DIR = PROJECT_DIR.parent / "Data_Collection"


class CalibrationToolTests(unittest.TestCase):
    """Verify governed defaults, source QA, dataset labels, and snapshot hashes."""

    def test_calibrated_defaults_are_active(self) -> None:
        config = load_simulator()["SimConfig"]()
        self.assertEqual(13.50, config.average_possession_seconds)
        self.assertEqual(-0.020, config.shot_accuracy_adjustment)
        self.assertEqual(0.75, config.three_point_attempt_weight_multiplier)
        self.assertEqual(1.40, config.offensive_rebound_probability_multiplier)
        self.assertEqual(0.62, config.assist_probability_on_made_fg)

    def test_current_enrichment_passes_qa(self) -> None:
        payload = json.loads((DATA_COLLECTION_DIR / "data/published/real_teams_2025-26_regular_season.json").read_text(encoding="utf-8"))
        report = json.loads((DATA_COLLECTION_DIR / "reports/enrichment_qa_2025-26_regular_season.json").read_text(encoding="utf-8"))
        self.assertEqual("historical_enrichment_v2", payload["metadata"]["formula_version"])
        self.assertEqual("pass", report["status"])
        self.assertEqual(72, report["players"])
        self.assertEqual(72, report["source_component_coverage"]["dfga"]["nonzero"])

    def test_pilot_is_structural_not_predictive(self) -> None:
        pilot = json.loads((DATA_COLLECTION_DIR / "data/published/calibration/pilot_games_2025-26_regular_season.json").read_text(encoding="utf-8"))
        self.assertEqual(16, len(pilot["games"]))
        self.assertTrue(all(game["evaluation_labels"]["structural_reconstruction_eligible"] for game in pilot["games"]))
        self.assertTrue(all(not game["evaluation_labels"]["predictive_backtest_eligible"] for game in pilot["games"]))
        with self.assertRaisesRegex(ValueError, "not predictive-backtest eligible"):
            _context(pilot["games"][0], {}, {"metadata": {}}, {}, "predictive_backtest", "unused.json")

    def test_registry_snapshot_hash(self) -> None:
        registry = json.loads((DATA_COLLECTION_DIR / "data/manifests/DATASET_REGISTRY.json").read_text(encoding="utf-8"))
        version_id = registry["default_historical_version"]
        manifest = json.loads((DATA_COLLECTION_DIR / "data/manifests" / f"{version_id}.json").read_text(encoding="utf-8"))
        snapshot = Path(manifest["snapshot_path"])
        self.assertEqual(manifest["sha256"], hashlib.sha256(snapshot.read_bytes()).hexdigest())
        current = next(version for version in registry["versions"] if version["version_id"] == version_id)
        self.assertEqual("current", current["status"])


if __name__ == "__main__":
    unittest.main()
