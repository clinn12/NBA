---
title: Calibration and Validation
project: NBA Simulator
file_type: methodology
status: active
purpose: Define calibration targets, acceptance rules, evaluation modes, and formal results.
usage: Follow when tuning parameters or interpreting structural and predictive validation.
last_updated: 2026-08-15
---

# Calibration and Validation

## Objective

Align aggregate simulator behavior with real NBA distributions before relying on game projections.

## Primary metrics

- Pace
- Offensive rating
- Free-throw rate (FTr)
- Turnover percentage (TOV%)
- Offensive rebound percentage (ORB%)
- 3-point attempt rate
- Assist rate
- Block rate
- Steal rate

## Procedure

1. Define the league, season, data source, and exact formulas for target metrics.
2. Simulate representative matchups for an initial 500-game sample; increase to 5,000 for tuning decisions.
3. Compare Monte Carlo averages and distributions with target values, not just a single game.
4. Change one related parameter group at a time and record the rationale and effect.
5. Retain a holdout set of teams or games for post-tuning validation.

## Current state

The simulator emits per-game `calibration` output, Monte Carlo average calibration deltas, complete sampled-input audits, and historical-outcome percentile reports. `configs/calibration_plan.json` defines ordered parameter stages, three ablation variants, and explicit acceptance thresholds. `scripts/run_calibration.py` produces raw simulation CSVs, aggregate reports, interval coverage, winner Brier scores, metric biases, structural checks, and pass/fail decisions.

The default historical profiles now include formula-derived defense, switchability, help defense, stamina, clutch, rim pressure, and off-ball gravity. These are transparent historical indices rather than predictions. Their scales, weights, and reliability thresholds must be calibrated and sensitivity-tested before their simulation effects are considered forecast-ready.

The original pilot has 16 games in which both opponents are among NYK, SAS, BOS, and LAL. Because it uses completed-season averages and actual players who appeared, it remains restricted to structural reconstruction. The all-team dated dataset contains 1,069 predictive-eligible games with strictly prior-game rolling inputs and chronological calibration/validation/holdout splits. `calibration_defaults_v2` passed every configured validation gate and every pre-registered gate on the 176-game formal holdout. This validates its aggregate game and team-outcome behavior for the tested 2025-26 pregame-data scope. It does not validate player-minute distributions or grant unrestricted production-forecast status: expected availability is still inferred from prior appearances, exact starter coverage is incomplete, and official pregame injury reports are pending.

## Ordered calibration and ablation

Tune one layer at a time in this order: pace; scoring efficiency; shot mix; turnovers/fouls/free throws; rebounds; minutes/usage; player variability; shared environment; defense/matchups; home/rest/travel; late-game/blowout behavior. Retain the same games and common seeds while changing a single related parameter group.

Compare three variants on every run:

- `averages_only`: no game-form sampling, shared environment, or matchup adjustments.
- `game_form`: historical player-profile sampling only.
- `full_context`: profile sampling, shared environment, and matchup adjustments.

Acceptance requires zero runtime and structural failures plus the statistical thresholds in `configs/calibration_plan.json`. Passing a small structural pilot does not grant forecast-ready status; thresholds must also pass on a held-out pregame-valid sample.

## Historical-game distribution validation

Use `validate_historical_game_distribution` on a repeated matchup batch. For each historical game, record:

- Probability assigned to the actual winner.
- Actual home/away score percentiles.
- Actual margin and total-point percentiles.
- Coverage of the real result by the simulated p05–p95 and p25–p75 intervals.
- Optional player minutes, points, rebounds, assists, and other stat percentiles.

Aggregate these measures across many games. A healthy model should produce appropriately calibrated win probabilities and interval coverage; a single real result is not expected to equal the simulated mean.

Use only pregame-available inputs for predictive backtests. Full-season averages may be used for structural and descriptive tests but must be labeled as look-ahead inputs.

## Repeated-run outputs

- Matchup batches retain all raw games and provide average score, win rates, possessions, and calibration deltas.
- Season runs retain every season iteration and its final standings.
- Nested season mode retains every game within every fixture batch, plus the selected result used to form each discrete season standing. Use the batch summaries for matchup uncertainty and `standing_distribution` for season-level uncertainty.

## Scale trigger

Current simulations should remain local and use the Python simulator core. If calibration or matchup analysis routinely requires 1,000 or more simulations per game, evaluate PySpark for distributed input preparation, workload dispatch, and aggregate analysis. Keep the possession-resolution logic as a deterministic Python unit so it remains testable and reproducible.

## Calibration log

### 2026-08-15 - frozen 176-game formal holdout

- Evaluated manifest `formal_holdout_v2_20260814` with frozen `calibration_defaults_v2` on exactly the 176 holdout games not previously exposed under v1. The 50 exposed game IDs were explicitly excluded and the manifest verified the dataset, plan, configuration, engine, and backtest hashes before execution.
- Used 500 deterministic draws per game: 88,000 total simulations. All 176 game checkpoints, raw simulation files, and raw player-stat files were retained; there were zero missing games, runtime errors, structural failures, or temporary files.
- Every pre-registered acceptance check passed. Team-score MAE was `11.378`, margin MAE `14.088`, total-points MAE `17.737`, winner Brier score `0.217`, score p05-p95 coverage `0.881`, and score p25-p75 coverage `0.497`.
- Aggregate player-stat coverage passed at `0.798` for p05-p95 and `0.563` for p25-p75. Player-minute coverage remained poor (`0.281` and `0.136`, respectively), confirming that the aggregate player-stat result must not be interpreted as validated rotation realism.
- Aggregate biases passed: pace `-0.580`, offensive rating `-2.452`, eFG `-0.0242`, 3PA rate `+0.0294`, FTr `+0.0024`, TOV% `+0.238`, ORB% `-1.694`, assist rate `-0.0494`, block rate `-0.0108`, and steal rate `-0.0159`.
- Governance decision: promote v2 as formally holdout-validated for aggregate game and team-outcome simulation within this dataset and season scope. Do not tune v2 from these results. Availability/starter enrichment and player-minute calibration constitute a future model version and require a newly reserved holdout.
- The first parallel execution was interrupted after a machine sleep and exposed an uncapped-overtime runtime tail in a small number of worker processes. The runner was changed to isolate each game in a fresh process with a timeout and resumable checkpoints; no frozen engine, input, parameter, manifest partition, or completed result was altered.

### 2026-08-14 — full-league calibration and v2 validation

- Ran the original defaults on all 623 calibration games at 10 draws each: 6,230 simulations, zero runtime errors, and zero structural failures. Team-score MAE was 13.79, total-points MAE 24.02, pace bias -6.56, 3PA-rate bias +0.0636, and ORB% bias -4.73.
- Added governed `--sim-config-file` overrides to the pregame backtest and retained every candidate report under `outputs/calibration_sweeps/`.
- Ordered common-seed sweeps selected average possession time `13.5` from `13.4/13.5/13.6/13.8`, 3-point attempt weight `0.75` from `0.75/0.78/0.81`, and offensive-rebound multiplier `1.40` from `1.40/1.50`. Scoring efficiency, turnover, foul, free-throw, assist, and steal controls already passed and were not changed.
- The combined 10-draw calibration confirmation improved team-score MAE to 11.13, total-points MAE to 17.68, pace bias to -1.14, 3PA-rate bias to +0.0268, and ORB% bias to -1.62, with zero errors or structural failures.
- Froze the candidate and evaluated all 220 validation games at 20 draws each: 4,400 simulations, zero runtime/structural failures, and `pass` on every configured gate. Team-score MAE was 10.19, margin MAE 12.38, total-points MAE 16.32, winner Brier 0.228, score p05-p95 coverage 0.820, and overall player-stat p05-p95 coverage 0.755.
- Validation biases all passed: pace -0.68, offensive rating -1.44, eFG -0.0178, 3PA rate +0.0218, FTr -0.0080, TOV% +0.05, ORB% -1.70, assist rate -0.0483, block rate -0.0167, and steal rate -0.0179.
- Promoted `configs/calibration_defaults_v2.json` and activated its settings in `SimConfig`. Full evidence is retained in `reports/calibration_tuning_20260814.json`.
- Player-minute p05-p95 coverage remains only 0.258. Rotation/minutes tuning is deferred because incomplete starter and injury/availability data confound inferred-roster error with simulator error.
- Governance correction: the first 50 holdout games were inspected under v1 and are no longer strictly untouched. The remaining 176 games are reserved for one formal v2 run at 500 or more draws per game; no tuning may follow from that result.

### 2026-08-01 — full-league time-valid foundation and first holdout

- Built official full-league regular-season inputs: 26,651 player-game rows, 2,460 team-game rows, 1,230 games, and 30 teams; generated 661 all-team descriptive variability profiles.
- Built 1,069 dated pregame records with 623 calibration, 220 validation, and 226 holdout games. Full-dataset QA passed with no chronology, leakage, roster, starter-shape, split, or expected-context errors.
- Exact actual starters are currently available for 43 eligible games (4.0%). The official v3 cache is resumable; all remaining expected-starter and availability fallbacks are explicitly labeled. Official injury-report coverage is zero.
- Ran an untouched 50-game holdout at 50 draws per game: 2,500 possession simulations, zero runtime errors, and zero structural failures.
- Results: team-score MAE 12.55, margin MAE 11.88, total-points MAE 22.41, winner Brier 0.205, score p05–p95 coverage 0.810, score p25–p75 coverage 0.430, player-stat p05–p95 coverage 0.772, and player-stat p25–p75 coverage 0.546.
- Failed gates: team-score MAE, total-points MAE, pace bias (-5.97 possessions), 3PA-rate bias (+0.0687), ORB% bias (-6.17 points), and steal-rate bias (-0.0208). The holdout was not used for parameter selection. Tune only on calibration/validation before rerunning the full untouched holdout.

### 2026-07-31 — enrichment QA, dataset freeze, and 16-game diagnostic baseline

- Added enrichment QA for missing fields, source-component coverage, reliability, distributions, extremes, correlations, and missing-defender sensitivity.
- QA exposed an identity-field mismatch in NBA defended-shooting feeds. Corrected the join and incremented the deterministic formula to `historical_enrichment_v2`; all 72 pilot players now have populated defended-attempt components and QA passes with no flags.
- Froze corrected input version `historical_enriched_2025_26_regular_season__sha256_e81d3c579c0b`. The earlier snapshot is preserved but marked superseded in the registry.
- Built 16 pilot games from retained official player logs. They are labeled structural reconstruction with look-ahead inputs, not predictive backtests.
- Ran 25 draws per game for three ablations: 1,200 possession simulations total. All completed with zero runtime errors and zero structural failures.
- No variant passed the full statistical gate. Full context had team-score MAE 11.27, margin MAE 12.24, total-points MAE 19.69, winner Brier score 0.219, p05–p95 score coverage 0.781, and p25–p75 coverage 0.438.
- The final report also retained 3,480 game/player/stat distributions per variant. Full-context player p05–p95 coverage was 0.842 and p25–p75 coverage was 0.651.
- First tuning targets were total-points error, 3-point attempt share (about +0.047 bias), offensive rebound percentage (about -4.27 points; under-produced), and assist rate (about -0.051 in full context).

### 2026-07-31 — staged tuning and formal 500-draw validation

- Added neutral, auditable controls at the causal points for shot accuracy, 3-point shot selection, and offensive-rebound probability; retained the existing assisted-make control.
- Common-seed sweeps selected `shot_accuracy_adjustment=-0.020`, `three_point_attempt_weight_multiplier=0.90`, `offensive_rebound_probability_multiplier=1.20`, and `assist_probability_on_made_fg=0.62`. They are now the defaults and are versioned in `configs/calibration_defaults_v1.json`.
- A 50-draw-per-game three-way ablation produced zero structural/runtime failures. All aggregate bias and coverage checks passed; total-points MAE remained the only failed check for every variant.
- Formal full-context validation used 500 draws for each of 16 games: 8,000 possession simulations. It completed with zero runtime errors and zero structural failures.
- Formal results: team-score MAE 10.82, margin MAE 12.23, total-points MAE 19.37, winner Brier score 0.230, score p05–p95 coverage 0.938, score p25–p75 coverage 0.500, player-stat p05–p95 coverage 0.898, and player-stat p25–p75 coverage 0.677.
- Metric biases were all within threshold: pace -1.66, offensive rating -0.07, eFG -0.0032, 3PA rate +0.0246, FTr +0.0043, TOV% +0.82, ORB% -2.16, assist rate -0.0120, block rate +0.0094, and steal rate -0.0095.
- Acceptance remains `fail` only because total-points MAE is 19.37 against the retained 18.0 threshold. The threshold was not weakened. Mean efficiency is centered, so remaining total error is treated as a missing game-specific context problem rather than another global scoring-bias problem.

Add a dated entry for each formal run containing: code/input version, sample size, matchups, targets, observed results, parameter changes, and follow-up actions.

### 2026-07-31 — single-game smoke test

- Actual game: `0022500018`, Knicks vs. Celtics, 2025-10-24. Actual result: Knicks 105, Celtics 95.
- Inputs: 2025–26 full regular-season averages for both teams; no game-date roster, injury, or lineup reconstruction.
- One simulated game, seed 7: Knicks 131, Celtics 125.
- Result: winner matched, but the simulated total was 56 points too high. This is a functional smoke test, not a predictive backtest, because it uses full-season look-ahead inputs and only one stochastic draw.
- Follow-up: calibrate scoring/pace over large samples and evaluate using rolling historical snapshots that contain only information available before each game.

### 2026-07-31 — rotation structural audit

- Simulated real-profile Knicks–Celtics regulation game: 409 substitution events, with only six players per team receiving minutes. Team minutes still reconciled to 240.
- Actual game `0022500018`: 10 Knicks and 12 Celtics played, with 240 minutes per team.
- Finding: confirmed rotation-engine bug, not a calibration issue. Sequential substitution decisions reuse players moved to the bench earlier in the same stoppage, creating substitution chains.
- Follow-up: repair the rotation engine and add structural regression tests before using simulation outputs for further realism assessment.

### 2026-07-31 — rotation repair validation

- Replaced sequential mutable-lineup substitutions with frozen lineup/bench snapshot decisions and capped normal substitutions at two per stoppage.
- Moved player-minute recording to the final period-clock decrement, resolving duration mismatches from shortened possession branches.
- Five real-profile regulation validation games: 13–19 substitutions per team, 12–13 active players per team, zero same-stoppage re-entries, five-player lineups throughout, and exactly 240 raw team minutes per game.
- Remaining limitation: rotation distributions and minutes targets require future tuning against real rotations; this is no longer a structural integrity failure.

### 2026-07-31 — individual-game framework regression

- Ran 100 real-profile Knicks–Celtics games with historical game-form sampling enabled.
- All 100 runs produced unique sampled-profile seed signatures.
- Passed score and player/team aggregation, exact team-minute totals, five-player lineups, foul/free-throw ordering, period-opening ownership, normal substitution-cap, disqualification, and audit-completeness invariants.
- This validates implementation integrity, not predictive calibration. The historical variability draw widths, matchup effects, home court, game environment, rotations, and late-game behavior still require time-valid calibration across many historical games.
