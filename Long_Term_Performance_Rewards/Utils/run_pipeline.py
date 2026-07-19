"""Run the NBA rewards pipeline.

This is the orchestration layer for the project. It can pull regular-season
standings, pull playoff data, and generate reports in one command while still
allowing each stage to be skipped.

Why it matters:
    A single pipeline entry point makes the project easier to run consistently
    for humans, schedulers, and AI agents. The skip flags allow safe report-only
    runs when the user does not want to scrape Basketball Reference.
"""

from __future__ import annotations

import argparse

try:
    from .common import DEFAULT_CONFIG_PATH, load_config, load_pipeline_configs
    from .generate_reports import generate_reports
    from .pull_nba_playoffs import update_playoffs
    from .pull_nba_standings import update_standings
except ImportError:
    from common import DEFAULT_CONFIG_PATH, load_config, load_pipeline_configs
    from generate_reports import generate_reports
    from pull_nba_playoffs import update_playoffs
    from pull_nba_standings import update_standings


def main() -> None:
    """Command-line entry point for the full pipeline."""
    parser = argparse.ArgumentParser(description="Run the NBA data pull and report pipeline.")
    parser.add_argument("--config", default=None, help="Path to the pipeline JSON config file.")
    parser.add_argument("--skip-standings", action="store_true", help="Do not pull regular season standings.")
    parser.add_argument("--skip-playoffs", action="store_true", help="Do not pull playoff data.")
    parser.add_argument("--skip-reports", action="store_true", help="Do not generate report outputs.")
    args = parser.parse_args()

    data_pull_config, analysis_config = load_pipeline_configs(args.config or DEFAULT_CONFIG_PATH)

    if not args.skip_standings:
        update_standings(data_pull_config)

    if not args.skip_playoffs:
        update_playoffs(data_pull_config)

    if not args.skip_reports:
        generate_reports(analysis_config)


if __name__ == "__main__":
    main()
