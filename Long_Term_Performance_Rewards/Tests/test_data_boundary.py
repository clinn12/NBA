"""Verify the rewards project consumes governed Data Collection publications.

Front Matter
------------
Project: NBA Long-Term Performance Rewards
File type: Python test module
Status: Active
Last updated: 2026-08-16

Purpose
-------
Prevent shared NBA retrieval code or source datasets from drifting back into
this consumer project, and verify migrated publications match archived inputs.

Usage
-----
Run with ``python -m unittest discover -s Tests -v``. Tests are offline and do
not refresh or modify Data Collection publications.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from Scripts.generate_reports import create_run_directory, write_latest_pointer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NBA_ROOT = PROJECT_ROOT.parent
DATA_COLLECTION = NBA_ROOT / "Data_Collection"


def digest(path: Path) -> str:
    """Return a SHA-256 digest used for exact migration-equivalence checks."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


class DataBoundaryTests(unittest.TestCase):
    """Enforce one-way consumption of shared historical NBA publications."""

    def test_analysis_config_uses_published_data_collection_inputs(self) -> None:
        """Require every configured source input to resolve under Data Collection."""

        config = json.loads((PROJECT_ROOT / "Config/analysis_settings.json").read_text(encoding="utf-8"))
        for key in ("standings", "playoffs", "team_mapping"):
            resolved = (PROJECT_ROOT / config["paths"][key]).resolve()
            self.assertTrue(resolved.is_file(), f"Missing {key} publication: {resolved}")
            self.assertTrue(resolved.is_relative_to(DATA_COLLECTION.resolve()))
            self.assertIn("published", resolved.parts)

    def test_no_active_local_shared_data_or_pullers(self) -> None:
        """Keep source CSVs and retrieval scripts out of the active consumer surface."""

        self.assertFalse((PROJECT_ROOT / "Data").exists())
        self.assertFalse((PROJECT_ROOT / "Utils").exists())
        self.assertTrue((PROJECT_ROOT / "Scripts/generate_reports.py").is_file())
        self.assertTrue((PROJECT_ROOT / "Scripts/run_pipeline.py").is_file())
        self.assertTrue((PROJECT_ROOT / "__Archive__/Data").is_dir())
        self.assertFalse((PROJECT_ROOT / "Scripts/pull_nba_standings.py").exists())
        self.assertFalse((PROJECT_ROOT / "Scripts/pull_nba_playoffs.py").exists())

    def test_notebook_imports_current_scripts_package(self) -> None:
        """Prevent the interactive workflow from reverting to the retired Utils name."""

        notebook = json.loads(
            (PROJECT_ROOT / "Notebooks/NBA_Playoffs_and_Champions.ipynb").read_text(encoding="utf-8")
        )
        notebook_source = "\n".join("".join(cell["source"]) for cell in notebook["cells"])
        self.assertIn("from Scripts.common import configured_path, load_config", notebook_source)
        self.assertIn("from Scripts.generate_reports import generate_reports", notebook_source)
        self.assertNotIn("from Utils", notebook_source)

    def test_notebook_remains_a_thin_clean_pipeline_interface(self) -> None:
        """Keep the interactive entry point concise, reusable, and free of stale output."""

        notebook = json.loads(
            (PROJECT_ROOT / "Notebooks/NBA_Playoffs_and_Champions.ipynb").read_text(encoding="utf-8")
        )
        notebook_source = "\n".join("".join(cell["source"]) for cell in notebook["cells"])
        code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]

        self.assertLessEqual(len(notebook["cells"]), 10)
        self.assertEqual(1, notebook_source.count("reports = generate_reports("))
        self.assertNotIn("Logic now lives in Scripts/generate_reports.py", notebook_source)
        self.assertTrue(all(cell["execution_count"] is None for cell in code_cells))
        self.assertTrue(all(cell["outputs"] == [] for cell in code_cells))

    def test_report_run_directories_are_timestamped_and_collision_safe(self) -> None:
        """Require safe labels, deterministic naming, and non-overwriting collisions."""

        eastern = timezone(timedelta(hours=-4), name="EDT")
        run_time = datetime(2026, 8, 18, 14, 32, 5, tzinfo=eastern)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, _ = create_run_directory(root, run_name="Baseline Test", run_time=run_time)
            second, _ = create_run_directory(root, run_name="Baseline Test", run_time=run_time)
        self.assertEqual("run_2026_08_18_143205_Baseline_Test", first.name)
        self.assertEqual("run_2026_08_18_143205_Baseline_Test_02", second.name)

    def test_latest_pointer_identifies_completed_run(self) -> None:
        """Write an atomic root pointer to the newest completed run manifest."""

        completed = datetime(2026, 8, 18, 18, 32, 10, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_directory = root / "run_2026_08_18_143205"
            run_directory.mkdir()
            (run_directory / "Report_Manifest.json").write_text("{}", encoding="utf-8")
            pointer = write_latest_pointer(root, run_directory, completed)
            payload = json.loads(pointer.read_text(encoding="utf-8"))
        self.assertEqual("complete", payload["status"])
        self.assertEqual(run_directory.name, payload["run_id"])
        self.assertEqual(f"{run_directory.name}/Report_Manifest.json", payload["manifest"])

    def test_active_reports_use_run_folders_not_flat_outputs(self) -> None:
        """Require the report root to contain only navigation and governed run folders."""

        reports_root = PROJECT_ROOT / "Reports"
        self.assertEqual([], list(reports_root.glob("Output_*.csv")))
        latest = json.loads((reports_root / "latest_run.json").read_text(encoding="utf-8"))
        self.assertRegex(latest["run_id"], r"^run_\d{4}_\d{2}_\d{2}_\d{6}(?:_[A-Za-z0-9_-]+)?$")
        run_directory = reports_root / latest["run_directory"]
        self.assertTrue(run_directory.is_dir())
        self.assertTrue((reports_root / latest["manifest"]).is_file())

    def test_published_files_match_archived_migration_sources(self) -> None:
        """Prove the initial publications preserve the exact migrated source bytes."""

        archive = PROJECT_ROOT / "__Archive__/Data/__Archive__/migrated_to_data_collection_20260815"
        published = DATA_COLLECTION / "data/published/historical"
        pairs = {
            archive / "nba_standings.csv": published / "nba_standings.csv",
            archive / "nba_playoffs.csv": published / "nba_playoffs.csv",
            archive / "team_mapping.csv": published / "franchise_lineage.csv",
        }
        for archived, active in pairs.items():
            self.assertEqual(digest(archived), digest(active), f"Migration drift: {active.name}")


if __name__ == "__main__":
    unittest.main()
