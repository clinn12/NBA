"""Refresh all long-run NBA standings and playoff publications.

Front Matter
------------
Project: NBA Data Collection
File type: Python script
Status: Active
Last updated: 2026-08-15

Purpose
-------
Provide one entry point for refreshing Basketball Reference regular-season and
playoff history, validating the publications, and updating their manifest.

Usage
-----
Run ``python scripts/pull_historical_results.py`` from any directory. Use
``--config`` only when intentionally testing an alternate governed config.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_collection.historical_results import DEFAULT_CONFIG_PATH, load_config, write_publication_manifest
from scripts.pull_historical_playoffs import update_playoffs
from scripts.pull_historical_standings import update_standings


def refresh_historical_results(config: dict | None = None) -> dict:
    """Refresh both source families and return the validated publication manifest."""

    config = config or load_config(DEFAULT_CONFIG_PATH)
    update_standings(config, write_manifest=False)
    update_playoffs(config, write_manifest=False)
    return write_publication_manifest(config)


def main() -> None:
    """Run the combined historical-results refresh from the command line."""

    parser = argparse.ArgumentParser(description="Refresh historical NBA standings and playoff results.")
    parser.add_argument("--config", default=None, help="Path to a historical-results JSON config file.")
    args = parser.parse_args()
    config = load_config(args.config or DEFAULT_CONFIG_PATH)
    manifest = refresh_historical_results(config)
    print(f"Published {len(manifest['artifacts'])} governed historical artifacts.")


if __name__ == "__main__":
    main()
