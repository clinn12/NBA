"""Run the NBA long-term performance rewards analysis pipeline.

Front Matter
------------
Project: NBA Long-Term Performance Rewards
File type: Python script
Status: Active
Last updated: 2026-08-16

Purpose
-------
Provide a single analysis-only entry point that reads governed shared inputs and
generates all project-owned policy reports.

Usage
-----
Run ``python Scripts/run_pipeline.py`` with optional analysis config and run label.

This is the project-local orchestration layer. It reads governed publications
from the sibling Data Collection project and generates reward-policy reports.

Why it matters:
    Data retrieval and publication are deliberately owned by Data Collection.
    Keeping this command analysis-only prevents a consumer project from silently
    mutating shared source data while producing policy reports.
"""

from __future__ import annotations

import argparse

try:
    from .common import DEFAULT_ANALYSIS_CONFIG_PATH, load_config
    from .generate_reports import generate_reports
except ImportError:
    from common import DEFAULT_ANALYSIS_CONFIG_PATH, load_config
    from generate_reports import generate_reports


def main() -> None:
    """Command-line entry point for the full pipeline."""
    parser = argparse.ArgumentParser(description="Generate NBA long-term performance reward reports.")
    parser.add_argument("--config", default=None, help="Path to the analysis JSON config file.")
    parser.add_argument("--run-name", default=None, help="Optional label appended to the timestamped run folder.")
    args = parser.parse_args()
    analysis_config = load_config(args.config or DEFAULT_ANALYSIS_CONFIG_PATH)
    generate_reports(analysis_config, run_name=args.run_name)


if __name__ == "__main__":
    main()
