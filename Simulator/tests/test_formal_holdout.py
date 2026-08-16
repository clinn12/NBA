"""Regression tests for frozen formal-holdout governance and aggregation.

Front Matter
------------
Project: NBA Simulator
File type: Python test module
Status: Active
Last updated: 2026-08-14

Purpose: ensure exposed games cannot enter final evaluation, batch seeds remain
monolithic-run equivalent, completed games resume safely, and compact per-game
summaries aggregate with the governed weighting rules.
Usage: included in ``python -m unittest discover -s tests -v`` and performs no
holdout simulations or network requests.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_formal_holdout import (
    _aggregate_results,
    _completed_results,
    _game_seed,
    _select_games,
)


class FormalHoldoutTests(unittest.TestCase):
    """Protect the frozen split, deterministic resume, and weighted report."""

    def test_frozen_ids_partition_holdout_and_exclude_exposed(self) -> None:
        """Select only explicit evaluation IDs when both sets partition holdout."""

        payload = {"games": [
            {"game_id": "exposed", "split": "holdout"},
            {"game_id": "final_1", "split": "holdout"},
            {"game_id": "final_2", "split": "holdout"},
        ]}
        manifest = {
            "exposed_game_ids": ["exposed"],
            "evaluation_game_ids": ["final_1", "final_2"],
            "expected_exposed_games": 1,
            "expected_evaluation_games": 2,
        }
        selected = _select_games(payload, manifest)
        self.assertEqual(["final_1", "final_2"], [game["game_id"] for game in selected])

    def test_overlap_is_rejected(self) -> None:
        """Reject any manifest that exposes a game and evaluates it again."""

        payload = {"games": [{"game_id": "g1", "split": "holdout"}]}
        manifest = {
            "exposed_game_ids": ["g1"], "evaluation_game_ids": ["g1"],
            "expected_exposed_games": 1, "expected_evaluation_games": 1,
        }
        with self.assertRaisesRegex(ValueError, "overlap"):
            _select_games(payload, manifest)

    def test_seed_matches_original_holdout_position(self) -> None:
        """Keep resumed and parallel games equivalent to one ordered run."""

        self.assertEqual(20_260_814, _game_seed(20_260_814, 0))
        self.assertEqual(25_260_814, _game_seed(20_260_814, 50))

    def test_completed_results_resume_only_matching_manifest(self) -> None:
        """Load a compact result only when it belongs to the frozen manifest."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = root / "games/g1/result.json"
            result.parent.mkdir(parents=True)
            result.write_text(json.dumps({"manifest_id": "frozen", "summary": {}}), encoding="utf-8")
            self.assertIn("g1", _completed_results(root, ["g1", "g2"], "frozen"))
            with self.assertRaisesRegex(ValueError, "another manifest"):
                _completed_results(root, ["g1"], "different")

    def test_compact_summaries_use_game_and_player_group_weights(self) -> None:
        """Combine per-game summaries without retaining all raw player rows."""

        thresholds = {
            "structural_failure_count_max": 0, "simulation_error_count_max": 0,
            "team_score_mae_max": 20, "margin_mae_max": 20,
            "total_points_mae_max": 30, "winner_brier_score_max": 0.5,
            "score_p05_p95_coverage_min": 0, "score_p05_p95_coverage_max": 1,
            "score_p25_p75_coverage_min": 0, "score_p25_p75_coverage_max": 1,
            "player_stat_p05_p95_coverage_min": 0, "player_stat_p05_p95_coverage_max": 1,
            "player_stat_p25_p75_coverage_min": 0, "player_stat_p25_p75_coverage_max": 1,
            "metric_absolute_bias_max": {"pace": 10},
        }
        def summary(score_mae: float, player_groups: int, player_coverage: float) -> dict:
            return {
                "games": 1, "simulation_rows": 2, "simulation_error_count": 0,
                "structural_failure_count": 0, "team_score_mae": score_mae,
                "margin_mae": 5, "total_points_mae": 10, "winner_brier_score": 0.2,
                "score_p05_p95_coverage": 1, "score_p25_p75_coverage": 0.5,
                "player_stat_groups": player_groups,
                "player_stat_p05_p95_coverage": player_coverage,
                "player_stat_p25_p75_coverage": player_coverage,
                "player_stat_coverage_by_stat": {
                    "PTS": {"groups": player_groups, "p05_p95_coverage": player_coverage, "p25_p75_coverage": player_coverage}
                },
                "metrics": {"pace": {"actual_mean": 100, "simulated_mean": 101, "bias": 1}},
            }
        result = _aggregate_results([
            {"summary": summary(10, 1, 1.0)},
            {"summary": summary(14, 3, 0.0)},
        ], thresholds)
        self.assertEqual(12.0, result["team_score_mae"])
        self.assertEqual(0.25, result["player_stat_p05_p95_coverage"])
        self.assertEqual("pass", result["acceptance_status"])


if __name__ == "__main__":
    unittest.main()
