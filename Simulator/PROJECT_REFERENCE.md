---
title: Project Reference — NBA Possession Simulator
project: NBA Simulator
file_type: project_reference
status: active
purpose: Preserve project decisions, implementation status, limitations, and open work.
usage: Review before making design changes and update after every meaningful development step.
last_updated: 2026-08-15
---

# Project Reference — NBA Possession Simulator

Last updated: 2026-08-15

## Purpose

Develop a possession-by-possession NBA game simulator that produces credible completed-game results and NBA.com-style box-score views. Until calibrated against real distributions, outputs are plausible simulations—not predictions.

## Current Working Context

- Project name: NBA Simulator.
- Project folder: `C:\Users\clinn\Documents\NBA\Simulator`.
- Upstream data project: `C:\Users\clinn\Documents\NBA\Data_Collection`; canonical consumer root: `..\Data_Collection\data\published`.
- Original source notebook: `notebooks/__Archive__/Simulation_original_20260524.ipynb` (preserved; do not edit unless explicitly intended).
- Active working notebook: `notebooks/Simulation_robust_copy.ipynb`.
- Historical handoff: `docs/__Archive__/NBA_SIM_HANDOFF_20260501.md`.
- Reusable engine package: `nba_simulator/`; runnable workflows: `scripts/`; structural documentation: `docs/`.

## Real-Team Scope

- Initial enriched pilot: New York Knicks, San Antonio Spurs, Boston Celtics, and Los Angeles Lakers.
- Dated rolling/backtest foundation: all 30 NBA teams.
- Data window: 2025–26 regular season only; exclude playoffs for the initial player and team profiles.
- Initial profile method: season averages mapped to simulator input fields.

## Decisions Made

- Model games at the possession level.
- Keep events to generic 2PT/3PT attempts, free throws, turnovers, rebounds, blocks, fouls, substitutions, timeouts, and period boundaries.
- Do not model technicals, jump balls, detailed turnover variants, or detailed shot subtypes at this stage.
- Track defender assignment, switching/help defense, lineup chemistry, game-state strategy, fatigue/rest, team-foul context, and overtime.
- Treat calibration as a prerequisite to relying on projected outcomes.
- Use two independent Monte Carlo layers: standalone matchups default to 10 game runs; seasons default to 10 season runs with one simulation per scheduled game.
- Support nested season mode with configurable `season_game_runs`; each nested batch is retained and one randomly selected run determines that season iteration's standings.
- Export raw player/team simulation outcomes to CSV alongside player/team statistical summaries and season-standings summaries. Raw files preserve distributions; summary files provide means, ranges, standard deviations, and percentiles.
- Organize every CSV export batch in a date-stamped `YYYYMMDD` subfolder beneath the chosen output directory.
- Support the same robust simulation workflow from `notebooks/Simulation_robust_copy.ipynb` or the dependency-free `scripts/run_simulation.py` command-line entry point.
- Keep the simulator core in plain Python for current workloads. If recurring analysis requires 1,000+ runs of the same matchup or other cluster-scale workloads, evaluate PySpark for distributed data preparation, simulation dispatch, and aggregation—not for individual possession resolution.
- Use season averages as the first real-data baseline. Later add a player game-form layer based on historical game-to-game distributions, varying related latent inputs together rather than independently randomizing final box-score statistics.
- Separate data creation from simulation. The sibling `Data_Collection` project owns retrieval, raw data, historical transformations, QA, manifests, immutable versions, and publication. Simulator owns event resolution, simulation, calibration evaluation, and backtesting. Simulator may read published artifacts and reports but must not import upstream implementation modules.
- Treat documentation as part of implementation: every active Python file requires a purpose/usage module header, every public API requires a docstring, non-obvious logic requires intent-focused comments, and every active notebook requires opening usage documentation. New and updated files must pass `scripts/check_documentation.py`.
- Standardize file front matter under the `NBA Simulator` identity: YAML for Markdown, structured module-docstring metadata for Python, and matching visible/notebook metadata for Jupyter. Strict-schema JSON and generated data/output artifacts remain schema-safe and carry provenance through their existing metadata or manifests.

## Implemented

- Usage-weighted shooter selection and 2PT/3PT choice.
- Assists, rebounds, blocks, steals, shooting/non-shooting fouls, bonus rules, substitutions, fatigue, timeouts, period breaks, and overtime.
- Completed-game outputs: team/player tables, play-by-play, traditional/advanced/scoring/defense box-score views, and calibration diagnostics.
- Placeholder player profiles and Monte Carlo average calibration deltas.
- Rotation engine now evaluates every dead-ball substitution from frozen lineup/bench snapshots, caps normal changes at five per stoppage, and requires a two-minute bench rest before re-entry. The rest requirement resets at period breaks and is relaxed in the final five minutes of a half or overtime.
- Rotation selection still values players behind their expected minutes, but tempers that priority with a bounded in-game performance signal so persistently poor bench play is not rewarded and a strongly outperforming bench player can earn time over a starter.
- A player who reaches the disqualification limit is replaced immediately before play resumes, including before any resulting free throws. A team is capped at five disqualified players; reaching four or five emits a calibration-warning event, while a sixth raises a calibration error and stops the simulation.
- Every free-throw sequence now has an explicit preceding foul record: shooting foul, personal foul, intentional foul, or and-one personal foul.
- Player minutes are recorded from the final game-clock decrement, preserving exact team-minute totals.
- `GameContext` and `SeasonState` separate baseline datasets from game overrides and evolving season workload. Exclusions, starters, rotation sizes, minutes limits, rest, travel, and dataset metadata are supported.
- Every repeated game samples a separate reproducible player profile. Opportunity and efficiency are varied separately using correlated team/player factors and the historical-variability dataset when selected.
- Shared game environments, active-roster matchup effects, home court, closing lineups, blowout rotations, two-for-one behavior, clock management, and fourth-quarter/overtime intentional-foul logic are implemented.
- Each game preserves context, seeds, sampled profiles, and matchup/environment inputs in memory and in dedicated audit CSVs.
- Historical-game validation reports outcome percentiles and the probability assigned to the real winner rather than requiring exact-score reproduction.
- Historical data is the default simulator input. Official NBA defense, hustle, tracking, speed/distance, drives, catch-and-shoot, and clutch feeds are preserved and converted into transparent, reliability-shrunk simulator ratings by `historical_enrichment_v2`; no field-specific predictive models are trained.
- Future predictive datasets remain interchangeable because they must publish the same canonical player fields and identify `source_type="predicted"`.
- Historical enrichment has automated missingness, source-component, reliability, distribution, extreme-value, correlation, and missing-defender sensitivity QA.
- Historical inputs are frozen upstream as immutable content-addressed snapshots with SHA-256 manifests. `..\Data_Collection\data\manifests\DATASET_REGISTRY.json` identifies current and superseded versions.
- A 16-game four-team structural pilot and automated Monte Carlo harness are implemented. Structural reconstruction and predictive backtesting are separate modes; look-ahead pilot records are rejected in predictive mode.
- Calibration is governed by ordered parameter stages, three ablations, common seeds, explicit thresholds, raw CSV retention, and acceptance reports.
- `calibration_defaults_v2` is active: average possession time `13.5`, shot accuracy `-0.020`, 3-point attempt weight `0.75`, offensive-rebound probability multiplier `1.40`, assisted-make probability `0.62`, and steal share `0.53`.
- Formal full-context validation completed at 500 draws for each of 16 games (8,000 games total) with zero runtime or structural failures. Every bias and coverage gate passed; total-points MAE was the only failed threshold.
- `nba_simulator/simulator_core.py` is the single canonical Python engine. The active notebook and CLI both import it directly; the obsolete notebook-code extraction fallback has been removed.
- Full-league official regular-season logs contain 26,651 player-game rows, 2,460 team-game rows, 30 teams, and 1,230 games. The all-team variability layer contains 661 player profiles.
- The dated pregame builder produced 1,069 strictly time-valid games with rolling 5/10/20-game, season-to-date, home/away, rest, expected-roster, starter, rotation, pace, offense, defense, and expected-total context. Chronological splits are 623 calibration, 220 validation, and 226 holdout games.
- Full-dataset QA passes with zero leakage/schema errors. Exact actual-starter coverage is currently 43 eligible games (4.0%) because the official endpoint rate-limited the resumable hydration; all fallback provenance is explicit. Official injury-report coverage remains zero.
- The 50-game by 50-draw untouched holdout evaluation completed 2,500 simulations with zero runtime or structural failures. It passed most probability, interval, and rate gates but failed team-score MAE, total-points MAE, pace, 3PA rate, ORB%, and steal-rate gates. No holdout retuning was performed.
- Calibration-only common-seed sweeps and a 6,230-simulation confirmation selected v2. On all 220 validation games at 20 draws each, every configured gate passed with zero errors or structural failures; team-score MAE was 10.19 and total-points MAE was 16.32.
- Because the first 50 holdout games were inspected under v1, they were excluded from the formal v2 evaluation. The remaining 176 games completed 500 draws each under the frozen manifest; every pre-registered gate passed with zero errors or structural failures.
- `calibration_defaults_v2` is formally holdout-validated for aggregate game and team-outcome simulation within the tested 2025-26 pregame-data scope. This status does not cover player-minute realism or unrestricted production forecasts because exact starter and official injury/availability inputs remain incomplete.

## Open Work

1. Resume official v3 box-score hydration to raise exact starter/active-player coverage from 4.0%; the cache is checkpointed and safe to rerun.
2. Add a versioned upstream official pregame injury/availability feed and possession-level lineup-combination source. Do not infer these as observed facts.
3. Calibrate player minutes and rotations only after availability/starter coverage improves; treat that as a new model version and reserve a new holdout rather than tuning v2 from its formal result.
4. Add a bounded-overtime safety invariant in the canonical engine and a regression test for pathological overtime tails; the formal runner already isolates and times out individual games.
5. Expand deterministic historical enrichment to all 30 teams and later seasons; keep predictive profiles interchangeable through the canonical contract.
6. Add sourced team coaching profiles and richer travel schedule context; basic rest, home court, workload, closing, and blowout behavior are implemented.
7. Optionally add shot-location granularity.
8. Add counterfactual player-impact analysis:
   - Single-player exclusion for one team's season, compared with a paired baseline season.
   - Exhaustive player exclusions for a team's roster, producing per-player wins-added/lost results.
   - Universal player-addition analysis across target teams, clearly labeled as either a cloned addition or a true transfer from the source team.
   - Define roster replacement, minutes redistribution, and availability rules before interpreting exclusion results.
   - Use common random seeds and the same schedule for baseline and counterfactual seasons so impact is measured as paired win deltas rather than simulation noise.

## Change Log

### 2026-08-15

- Added a governed 2024-25 full-league historical input option upstream: enriched profiles, variability, and 1,069 time-valid pregame games. Simulator defaults remain on 2025-26 until a separate cross-season evaluation is designed.
- Completed the NBA-wide data-boundary consolidation by moving the structural pilot calibration fixture and its builder to Data Collection. Simulator retains calibration execution and evidence but no longer creates or stores active shared input datasets.
- Completed the frozen `formal_holdout_v2_20260814` evaluation on the 176 games never inspected under v1, using 500 draws per game and retaining all raw evidence.
- All pre-registered gates passed across 88,000 simulations with zero missing games, runtime errors, or structural failures. Team-score MAE was `11.38`, margin MAE `14.09`, total-points MAE `17.74`, and winner Brier score `0.217`.
- Promoted v2 to formally holdout-validated status for aggregate game and team outcomes in the tested scope. No parameters were changed after inspection.
- Retained player-minute calibration as open work: MIN p05-p95 coverage was only `0.281`, consistent with incomplete exact-starter and official availability inputs.
- Hardened formal evaluation orchestration with resumable per-game checkpoints, isolated processes, and timeouts after a machine-sleep interruption revealed a pathological overtime runtime tail. Frozen simulation behavior and completed artifacts were unchanged.

### 2026-08-14

- Created the sibling `NBA\Data_Collection` project and moved retrieval, enrichment, variability, pregame construction, data QA, raw inputs, publications, manifests, immutable versions, and data reports into it without deleting files.
- Established `Data_Collection\data\published` as the stable consumer boundary. Simulator defaults and tests now read published artifacts without importing upstream implementation code.
- Kept simulator calibration fixtures, calibration/backtest execution, engine code, outputs, and tuning reports inside Simulator.

### 2026-08-01

- Extracted the canonical simulator engine to `nba_simulator/simulator_core.py`; the active notebook now imports it.
- Added the full-league log/starter puller, dated pregame profile builder/loader, transparent pregame team context, time-valid backtest harness, segmented reports, and full-dataset QA.
- Built 1,069 all-team pregame games and 661 all-team variability profiles. QA passed with no chronology, leakage, roster, or schema errors.
- Completed a 50-game, 2,500-simulation untouched holdout evaluation with zero runtime/structural failures. Acceptance remains failed on six statistical gates; the holdout was not used for tuning.
- Reorganized the project into `nba_simulator/`, `scripts/`, `tests/`, `notebooks/`, `configs/`, `examples/`, and `docs/`. Existing data/output/report locations were retained.
- Added an `__Archive__` convention to every maintained category and data layer. Archived the original notebook, old handoff, completed extraction utility, notebook checkpoints, Python cache, and unused ESPN snapshot without deleting them.
- Updated imports, root-stable defaults, notebook bootstrap logic, CLI commands, and tests. All 15 current regression tests, a direct CLI game, and an out-of-project data-QA invocation pass after the move.
- Added `docs/DOCUMENTATION_STANDARDS.md`, upgraded all active Python/notebook headers and public API docstrings, and added documentation enforcement to the regression suite.
- Renamed the project folder from `Predictions` to `Simulator`; updated current and archived documentation paths and added automated rejection of the obsolete project name.
- Added standardized `NBA Simulator` front matter to all active Python files, all maintained Markdown documents, and both visible and machine-readable active-notebook metadata.

### 2026-07-31

- Implemented enrichment QA, content-addressed dataset freezing, manifest/registry governance, the 16-game pilot builder, automated calibration/ablation reports, ordered tuning stages, and explicit acceptance thresholds.
- QA identified and corrected NBA defended-shooting feed identity mapping; the corrected deterministic input is `historical_enrichment_v2` with immutable snapshot SHA prefix `e81d3c579c0b`.
- Ran 1,200 diagnostic possession simulations across 16 games and three variants. All structural checks passed with no runtime errors, while all variants appropriately failed the not-yet-calibrated statistical gate.
- First tuning targets are total scoring, 3PA share, offensive rebounding, and assist rate. Predictive claims remain prohibited until pregame-only snapshots and availability inputs exist.
- Completed ordered common-seed tuning and promoted `calibration_defaults_v1`. The formal 8,000-game run passed all checks except total-points MAE (19.37 versus 18.0); the threshold remains unchanged.

### 2026-07-19

- Created this living reference from the existing project handoff.
- Added the project documentation set: README, data dictionary, methodology, calibration plan, and changelog.
- Added configurable game, season, and nested-season simulation-run support to the active simulator workstream.
- Added default CSV exports for matchup and season simulations, including player, team, and standings outputs.
- Documented the 1,000+ repeated-matchup scale trigger for evaluating PySpark.
- Defined the initial real-team scope: Knicks, Spurs, Celtics, and Lakers using 2025–26 regular-season averages only.
- Added an NBA Stats data puller and real-team loader for the initial 2025–26 regular-season pilot.
- Defined the long-term data boundary: future real and predicted datasets will be created upstream and supplied to this simulator through a common normalized profile contract.
- Added an initial descriptive historical-variability dataset for the four pilot teams. It is deliberately separate from the simulator and will inform a future player game-form model.
- Added a single-game possession-log output. It records true possessions (including offensive-rebound continuations) and exports a detailed dated CSV.
- Completed a single-game Knicks–Celtics smoke test using real season-average profiles. The winner matched but scoring was materially high; formal calibration and time-valid backtesting remain required.

## Maintenance Convention

After each meaningful development step, update this file with the decision made, implementation status, validation performed, and remaining follow-up work.

## 2026-08-16 Git Ignore Policy

- Reproducible Simulator `outputs`, `reports`, and local `data` artifacts remain
  on disk but are excluded from Git. Shared governed datasets continue to belong
  in Data Collection.
- Source code, configs, documentation, examples, active notebooks, tests, and
  intentionally small test fixtures remain eligible for version control.
- Python/Jupyter caches, local environments, editor state, logs, temporary
  files, secrets, local databases, serialized models, and all `__Archive__`
  contents are ignored.
