---
title: NBA Simulator Changelog
project: NBA Simulator
file_type: changelog
status: active
purpose: Record notable user-visible, structural, data, and validation changes over time.
usage: Add an entry whenever implementation, data contracts, defaults, or workflows change.
last_updated: 2026-08-15
---

# Changelog

All notable project changes are recorded here. For current decisions and open work, see `PROJECT_REFERENCE.md`.

## Unreleased

- Moved the structural pilot calibration dataset and its builder to Data Collection. Simulator now reads the governed `data/published/calibration/pilot_games_2025-26_regular_season.json` publication; superseded local copies were archived.

- Added a frozen, deterministic, resumable formal-holdout runner and manifest with artifact-hash verification, exact exclusion of the 50 holdout games exposed under v1, per-game process isolation/timeouts, raw gzip evidence retention, and compact aggregation checkpoints.
- Completed the untouched 176-game v2 evaluation at 500 draws per game (88,000 simulations). All pre-registered gates passed with zero missing games, runtime errors, or structural failures; team-score MAE was `11.38`, margin MAE `14.09`, total-points MAE `17.74`, and winner Brier score `0.217`.
- Classified `calibration_defaults_v2` as formally validated for aggregate game and team-outcome simulation within the tested 2025-26 pregame-data scope. No post-holdout tuning was performed. Production use and player-minute realism remain limited by incomplete starter/injury inputs and poor minute interval coverage.

- Added governed `--sim-config-file` support to the full-league pregame backtest so calibration candidates can be evaluated without editing engine defaults.
- Ran a 6,230-simulation calibration baseline, ordered common-seed pace/shot-mix/rebound sweeps, and a 6,230-simulation combined confirmation using only the 623-game calibration split.
- Promoted `calibration_defaults_v2`: possession time `13.5`, 3-point attempt weight `0.75`, and offensive-rebound multiplier `1.40`; retained v1 shot-accuracy, assist, and steal controls.
- Evaluated v2 on all 220 validation games at 20 draws each. All configured gates passed with zero runtime/structural failures, team-score MAE `10.19`, total-points MAE `16.32`, and winner Brier `0.228`.
- Deferred player-minute/rotation tuning because minute interval coverage remains poor and starter/injury availability inputs are incomplete. Reserved the 176 not-previously-inspected holdout games for final evaluation.

- Separated data collection into the sibling `C:\Users\clinn\Documents\NBA\Data_Collection` project. Retrieval, raw data, historical enrichment, variability, pregame construction, data QA, publications, manifests, versions, and data reports now live upstream.
- Established `Data_Collection\data\published` as the Simulator's read-only consumer boundary and updated defaults, examples, tests, and documentation to avoid importing upstream implementation code.
- Preserved Simulator ownership of the possession engine, run modes, calibration fixtures, calibration/backtest harnesses, outputs, and tuning reports.

- Standardized `NBA Simulator` front matter across Python module docstrings, Markdown YAML headers, and visible plus machine-readable Jupyter metadata.
- Updated documentation and archived path references for the project-folder rename from `Predictions` to `Simulator`.
- Extended documentation validation to enforce required front-matter fields, active/archive status, canonical project identity, and rejection of obsolete project-name references.
- Established mandatory code/notebook documentation standards covering purpose, usage, public API docstrings, intent-focused comments, inputs/outputs, and historical-cell warnings.
- Added `scripts/check_documentation.py` and a regression test so new active Python files and notebooks fail validation when required documentation is missing.
- Updated all active Python module headers and missing public API docstrings, and expanded the active notebook's opening documentation to identify its supported workflow and preserved legacy cells.

- Reorganized active code and artifacts into `nba_simulator/`, `scripts/`, `tests/`, `notebooks/`, `configs/`, `examples/`, and `docs/`, retaining `data/`, `outputs/`, and `reports/` as dedicated stores.
- Added documented `__Archive__` folders across maintained categories. Historical files were moved rather than deleted, including the original notebook, old handoff, completed extraction utility, notebook checkpoints, Python cache, and unused ESPN snapshot.
- Updated all active imports, notebook bootstrap code, configuration locations, project-root defaults, examples, and command documentation for the new layout.
- Validated the reorganized project with all 15 current tests, a direct no-export game simulation, and pregame-dataset QA launched from outside the project directory.

- Extracted the canonical possession engine to `simulator_core.py`; both the active notebook and Python CLI now use the same importable module.
- Added official full-league player/team log retrieval plus resumable NBA Stats v3 starter and active-player hydration.
- Added strictly dated rolling pregame profiles for all 30 teams, a canonical pregame loader, bounded/audited game-total context, chronological splits, and explicit availability/starter provenance.
- Added `scripts/validate_pregame_dataset.py` with chronology, leakage, roster, starter, split, uniqueness, and expected-context gates. The 1,069-game dataset passes with zero errors; exact starter coverage is currently 4.0% and official injury-report coverage remains pending.
- Added `scripts/run_pregame_backtest.py` with raw simulation/player CSVs, game forecasts, segmented diagnostics, and acceptance reports.
- Completed a 50-game, 2,500-simulation untouched holdout with zero runtime or structural failures. Six statistical gates remain failed, so forecast-ready status was not granted.
- Expanded historical variability generation to all 30 teams, producing 661 player profiles.

- Broad time-valid model calibration is pending; the calibration framework and four-team structural pilot are implemented.
- Added configurable repeated matchup runs (`game_runs`), repeated season runs (`season_runs`), and nested fixture runs within a season (`season_game_runs`).
- Added game-batch and season APIs that preserve raw results, summaries, selected standings outcomes, and standing distributions.
- Added default CSV exports for raw player/team results, player/team distribution summaries, season standings, and standings summaries.
- CSV exports are organized beneath a date-stamped `YYYYMMDD` folder.
- Added a Python command-line runner and example schedule; it loads the same robust notebook core used by Jupyter.
- Documented the future PySpark evaluation trigger for 1,000+ repeated simulations of a matchup.
- Set the first real-data target to 2025–26 regular-season averages for the Knicks, Spurs, Celtics, and Lakers; documented the future game-form distribution layer.
- Added the official NBA Stats puller and loader for the initial real-team profiles.
- Added a historical player game-log variability builder, retaining raw logs and descriptive distribution profiles for the pilot teams.
- Added a detailed single-game possession-log CSV export and matching CLI command.
- Documented future paired counterfactual player-impact analyses for exclusions and universal player additions.
- Logged the first real-profile single-game smoke test and its calibration limitations.
- Audited a single-game possession log and documented period-boundary possession-continuity and shooting-foul event-ordering issues for repair.
- Logged a confirmed rotation-engine defect found during simulated-versus-actual structural review.
- Repaired the rotation and minute-accounting defects; validated repeated real-profile games for lineup, substitution, participation, and minute-total invariants.
- Corrected the documented period-opening design to the NBA scheduled Q2–Q4 possession rule and jump-ball overtime openings.

- Implemented the period-opening rule, explicit period-end/next-period possession context, and shooting-foul-before-free-throw event ordering.
- Updated rotation policy: up to five normal changes per stoppage; two-minute bench-rest requirement with period-break and late-half/overtime exceptions; bounded in-game performance adjustments to bench priority and starter/bench swaps.
- Ran five real-profile Knicks–Celtics regression games: period-opening, shooting-foul ordering, substitution-cap, re-entry-rest, five-player-lineup, and exact-minute-total checks passed.

- Replaced disqualified players immediately before play resumes and added explicit intentional-foul and and-one foul records before their free throws.
- Validated the repair with standard real-profile games and a forced-disqualification scenario while an eligible bench player was available.

- Added a five-player team foul-out cap: four or five disqualifications are logged as calibration warnings, and a sixth raises a calibration error.
- Validated the cap across 10 standard real-profile games and a forced foul-out stress test.

- Added dataset-neutral `GameContext`, per-player overrides, and evolving `SeasonState` workload tracking.
- Added exclusions, starter and rotation overrides, minutes limits, and automatic 240-minute opportunity redistribution.
- Added independent reproducible player-profile draws for every repeated game, separating opportunity and efficiency with correlated team/player factors.
- Added shared game environments, active-roster matchup adjustments, home court, rest, and travel inputs.
- Added closing-lineup, blowout, two-for-one, late-clock, and fourth-quarter/overtime intentional-foul behavior.
- Added simulation-context, sampled-player-profile, and team-matchup audit CSVs plus historical-outcome distribution validation.
- Added CLI support for context JSON and dataset-backed teams by abbreviation, with `examples/sample_game_context.json` as an example.
- Passed a 100-game real-profile regression with 100 unique sampled-profile signatures and all structural/accounting/audit invariants intact.
- Made historical profiles the default input while preserving the same canonical contract for future predicted profiles.
- Added official NBA defense, hustle, tracking, speed/distance, drives, catch-and-shoot, and clutch feed retrieval with raw-feed retention.
- Added transparent historical enrichment calculations and reliability shrinkage for defense, switchability, help defense, stamina, clutch, rim pressure, and off-ball gravity; no predictive models are fitted.
- Refreshed the four-team 2025–26 regular-season dataset successfully with all enrichment feeds available and no recorded feed failures.
- Added enrichment QA covering missingness, source-component coverage, reliability, distributions, extremes, correlations, and missing-defender sensitivity.
- Corrected the alternate identity-field mapping used by NBA defended-shooting feeds and versioned the formula as `historical_enrichment_v2`.
- Added content-addressed immutable dataset snapshots, manifests, and a registry that identifies current and superseded versions.
- Built a 16-game four-team structural calibration pilot from retained official player game logs with explicit look-ahead and predictive-ineligibility labels.
- Added ordered calibration stages, three ablation modes, acceptance thresholds, historical Monte Carlo reports, and predictive-backtest eligibility enforcement.
- Completed a 1,200-simulation diagnostic baseline with zero runtime or structural failures; all three variants correctly remain below the statistical acceptance gate.
- Added scoped `SimConfig` controls for global shot accuracy, 3-point attempt weighting, and offensive-rebound probability, plus file-based calibration overrides for PowerShell-friendly reproducibility.
- Completed ordered common-seed parameter sweeps and promoted `calibration_defaults_v1`: `-0.020` shot accuracy, `0.90` 3-point weight, `1.20` offensive-rebound multiplier, and `0.62` assisted-make probability.
- Completed a 2,400-game three-way validation and a formal 8,000-game full-context validation. All structural, runtime, aggregate-bias, and coverage checks passed; only total-points MAE remains above threshold.

## 2026-07-19

- Added project documentation: README, data dictionary, methodology, calibration plan, project reference, and changelog.

## 2026-05-01

- Documented the original possession-simulator handoff and robust-core implementation status; it is now preserved at `docs/__Archive__/NBA_SIM_HANDOFF_20260501.md`.
