"""Structural, possession, pregame, and shared-core regression gates.

Front Matter
------------
Project: NBA Simulator
File type: Python test module
Status: Active
Last updated: 2026-08-14

Purpose: catch NBA rule, lineup, reproducibility, data-leakage, notebook parity,
and simulation accounting defects before outputs are trusted.
Usage: included in ``python -m unittest discover -s tests -v`` and uses fixed
seeds plus retained local datasets for deterministic validation.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from nba_simulator.pregame_profile_loader import build_pregame_context, build_pregame_team
from scripts.run_calibration import _structural_failures
from scripts.run_simulation import load_simulator


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_COLLECTION_DIR = PROJECT_DIR.parent / "Data_Collection"


class SimulatorRegressionTests(unittest.TestCase):
    """Exercise deterministic simulator rules and full pregame data invariants."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.simulator = load_simulator()

    def _game(self, seed: int = 11):
        s = self.simulator
        return s["simulate_game_robust"](s["create_placeholder_team"]("Home", 1), s["create_placeholder_team"]("Away", 2), s["SimConfig"](seed=seed))

    def test_structural_invariants_across_repeated_games(self) -> None:
        for seed in range(20, 30):
            self.assertEqual([], _structural_failures(self._game(seed)), f"seed={seed}")

    def test_possession_changes_after_turnover_or_defensive_rebound(self) -> None:
        game = self._game(31)
        rows = game["possession_log"]
        checked = 0
        for current, following in zip(rows, rows[1:]):
            events = current["events"]
            requires_change = any(event.get("event") in {"turnover", "defensive_rebound"} for event in events)
            if requires_change and current["period"] == following["period"]:
                self.assertEqual(current["defense_team"], following["offense_team"])
                checked += 1
        self.assertGreater(checked, 10)

    def test_period_opening_rule_and_boundary_logs(self) -> None:
        game = self._game(32)
        starts = [row for row in game["play_by_play"] if row.get("event") == "period_start"]
        ends = [row for row in game["play_by_play"] if row.get("event") == "period_end"]
        by_period = {row["period"]: row for row in starts}
        opener = by_period[1]["opening_possession_team"]
        other = "Away" if opener == "Home" else "Home"
        self.assertEqual(other, by_period[2]["opening_possession_team"])
        self.assertEqual(other, by_period[3]["opening_possession_team"])
        self.assertEqual(opener, by_period[4]["opening_possession_team"])
        self.assertEqual(game["periods"], len(starts)); self.assertEqual(game["periods"], len(ends))

    def test_free_throw_sequences_have_preceding_foul_context(self) -> None:
        log = self._game(33)["play_by_play"]
        allowed = {"shooting_foul", "personal_foul"}
        for index, event in enumerate(log):
            if event.get("event") != "free_throw" or (index and log[index - 1].get("event") == "free_throw"):
                continue
            self.assertGreater(index, 0)
            self.assertIn(log[index - 1].get("event"), allowed)

    def test_normal_substitution_cap(self) -> None:
        log = self._game(34)["play_by_play"]
        counts = {}
        for event in log:
            if event.get("event") == "substitution" and not event.get("disqualification_replacement"):
                key = (event.get("period"), event.get("clock"), event.get("team"))
                counts[key] = counts.get(key, 0) + 1
        self.assertTrue(all(value <= 5 for value in counts.values()))

    def test_fixed_seed_is_reproducible(self) -> None:
        first, second = self._game(35), self._game(35)
        self.assertEqual(first["final_score"], second["final_score"])
        self.assertEqual(first["possession_log"], second["possession_log"])

    def test_notebook_imports_canonical_module(self) -> None:
        notebook = json.loads((PROJECT_DIR / "notebooks/Simulation_robust_copy.ipynb").read_text(encoding="utf-8"))
        sources = ["".join(cell.get("source", [])) for cell in notebook["cells"] if cell.get("cell_type") == "code"]
        self.assertTrue(any("from nba_simulator.simulator_core import *" in source for source in sources))
        self.assertFalse(any("class SimConfig" in source and "def simulate_game_robust" in source for source in sources))

    def test_pregame_features_have_no_date_leakage(self) -> None:
        path = DATA_COLLECTION_DIR / "data/published/pregame/pregame_profiles_2025-26_regular_season_pilot.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for game in payload["games"]:
            self.assertTrue(game["evaluation_labels"]["predictive_backtest_eligible"])
            for team in game["pregame"]["teams"].values():
                self.assertGreaterEqual(len(team["players"]), 5)
                for player in team["players"]:
                    self.assertLess(player["last_appearance_date"], game["game_date"])

    def test_full_pregame_dataset_passes_quality_gates(self) -> None:
        path = DATA_COLLECTION_DIR / "data/published/pregame/pregame_profiles_2025-26_regular_season_qa.json"
        if not path.exists():
            self.skipTest("Full pregame dataset QA report has not been published")
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "pass", report["errors"])
        self.assertEqual(report["teams"], 30)

    def test_pregame_context_is_applied_and_audited(self) -> None:
        s = self.simulator
        payload = json.loads((DATA_COLLECTION_DIR / "data/published/pregame/pregame_profiles_2025-26_regular_season_pilot.json").read_text(encoding="utf-8"))
        game = payload["games"][-1]
        home = build_pregame_team(game, game["home_team"], s["create_team"]); away = build_pregame_team(game, game["away_team"], s["create_team"])
        result = s["simulate_game_robust"](home, away, s["SimConfig"](seed=88), game_context=build_pregame_context(game))
        audit = result["simulation_audit"]["pregame_team_context"]
        self.assertTrue(audit["enabled"])
        self.assertGreater(audit["pace_multiplier"], 0.91); self.assertLess(audit["pace_multiplier"], 1.09)
        self.assertIn("home_efficiency_adjustment", audit)


if __name__ == "__main__":
    unittest.main()
