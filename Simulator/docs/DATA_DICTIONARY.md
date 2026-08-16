---
title: NBA Simulator Data Dictionary
project: NBA Simulator
file_type: data_contract
status: active
purpose: Define canonical simulator inputs, provenance, derived fields, and audit outputs.
usage: Consult when creating, validating, mapping, or consuming historical and predicted datasets.
last_updated: 2026-08-14
---

# Data Dictionary

This document defines the simulator inputs. Placeholder values are currently used; real-data mappings should be documented here as they are implemented.

## Player profile fields

| Field | Meaning | Expected form |
| --- | --- | --- |
| `mpg` | Expected minutes per game | Minutes |
| `usage` | Offensive involvement when on court | Rate/proportion |
| `two_pct` | 2-point field-goal percentage | Proportion |
| `three_pct` | 3-point field-goal percentage | Proportion |
| `ft_pct` | Free-throw percentage | Proportion |
| `three_rate` | 3-point attempt tendency | Proportion/rate |
| `ftr` | Free-throw attempt tendency | Rate |
| `ast_rate` | Assist tendency | Rate |
| `tov_rate` | Turnover tendency | Rate |
| `orb_rate` / `drb_rate` | Offensive/defensive rebound tendency | Rate |
| `stl_rate` / `blk_rate` | Steal/block tendency | Rate |
| `foul_rate` | Personal-foul tendency | Rate |
| `defense` | General defensive quality | Standardized score |
| `stamina` | Fatigue resistance | Standardized score |
| `clutch` | Late-game performance modifier | Standardized score |
| `rim_pressure` | Rim-attacking tendency/effect | Standardized score |
| `off_ball_gravity` | Spacing effect away from ball | Standardized score |
| `switchability` | Ability to defend switches | Standardized score |
| `help_defense` | Help-defense effectiveness | Standardized score |

## Team and lineup inputs

Document these when real data is integrated:

- Team identity, season, and source.
- Starting lineup and rotation order.
- Player availability, injuries, and minutes limits.
- Team coaching profiles: pace, switching, help-defense aggression, bench depth, and timeout behavior.
- Game context: date, venue, rest days, travel, and back-to-back status.

## GameContext fields

| Field | Meaning |
| --- | --- |
| `game_id` | Stable scenario or scheduled-game identifier |
| `dataset_id` / `source_type` | Versioned baseline dataset and whether it is historical, predicted, or blended |
| `profile_mode` | `baseline`, `historical`, `predicted`, or `blended` game-profile behavior |
| `variability_path` | Optional historical-variability JSON used for game-form draws |
| `excluded_players` | Team-to-player mapping of game-specific inactive players |
| `player_overrides` | Per-player exclusion, starter, expected-minutes, minutes-limit, usage, and role overrides |
| `starters` | Explicit team starting-lineup lists |
| `rotation_size` | Maximum active rotation size by team; must be at least five |
| `home_rest_days` / `away_rest_days` | Pregame rest inputs |
| `home_travel_miles` / `away_travel_miles` | Pregame travel inputs |
| `home_court_points` | Bounded home-court efficiency adjustment expressed as approximate points |
| `enable_*` | Switches for profile sampling, shared environment, and matchup adjustments |

The historical dataset is the default input. The dataset supplies defaults, and `GameContext` only overrides the current simulated game. Excluded-player minutes and opportunities are redistributed among available players, respecting explicit minutes limits and preserving 240 expected team minutes. Future predicted datasets must use the same canonical profile fields and declare `source_type="predicted"`.

## SeasonState fields

`SeasonState` is updated only from the nested result selected for season standings. It tracks games played, unavailable players, cumulative minutes, and decayed player workload. Every nested simulation of the same fixture shares the same pregame state but receives a separate profile and event seed.

## Data standards to decide

- Source and season for every field.
- Whether rates are season totals, per-possession, per-minute, or percentile-normalized.
- Missing-data fallback and minimum-sample rules.
- How multi-team seasons and traded players are handled.
- Version/date stamp for every input extract.

## Data ownership boundary

The simulator must not depend on a specific retrieval process. It consumes a validated, versioned dataset in the canonical team/player profile schema. Separate upstream projects are responsible for regularly pulling historical data, generating predicted data, applying transformations, and publishing dataset manifests. Each consumed dataset must identify its source type (`historical`, `predicted`, or `blended`), version, coverage window, and field mappings.

## Initial data scope

- Teams: Knicks, Spurs, Celtics, and Lakers.
- Season: 2025–26 regular season only; do not blend playoff statistics into the initial profiles.
- Baseline: use season averages for the first real-player and real-team mappings.
- Upstream puller: `..\Data_Collection\scripts\pull_real_team_data.py` retrieves NBA Stats traditional, advanced, defense, hustle, tracking, speed/distance, drives, catch-and-shoot, and clutch aggregates; retains raw feeds upstream; and publishes mapped profiles in `..\Data_Collection\data\published\real_teams_2025-26_regular_season.json`.
- Temporary role mapping: roles are inferred from advanced assist, rebound, and block rates until real position/rotation inputs are added.
- Historically calculated fields: defense, stamina, clutch, rim pressure, off-ball gravity, switchability, and help defense use deterministic formula version `historical_enrichment_v2`. Each player record retains the raw components, reliability values, calculated outputs, and formula interpretation. Version 2 corrects joins for NBA defended-shooting feeds, whose identity columns differ from the other tracking feeds.

## Historical enrichment formulas

These are transparent indices, not fitted predictive models:

- `defense`: defended shooting differential, on-court defensive rating, deflections, contests, steals, and blocks.
- `switchability`: balance between 2PT and 3PT contests, deflections, and defensive-rating contribution.
- `help_defense`: deflections, interior contests, blocks, charges, and defended shooting.
- `stamina`: minutes, games played, distance, and average speed, mapped to the simulator's bounded workload-tolerance scale.
- `clutch`: clutch true-shooting difference from the player's overall true shooting, heavily shrunk by clutch minutes.
- `rim_pressure`: drives, drive free throws, and overall free-throw rate.
- `off_ball_gravity`: catch-and-shoot attempt volume and catch-and-shoot 3PT accuracy.

League standardization is calculated from the complete returned player population, not only the four pilot teams. General, defensive-attempt, tracking, and clutch sample sizes determine shrinkage toward neutral values. Missing feeds therefore reduce reliability instead of silently creating extreme ratings.

## Performance-distribution layer

Season averages define a player's baseline, while possession-level randomness resolves each game. The historical game-form layer uses historical game-to-game distributions to vary related underlying inputs—such as shot-making, usage, turnover tendency, and fatigue—together. It does not independently randomize final box-score totals and applies regression toward neutral values when samples are small.

## Dated pregame profile dataset

`pregame_profiles_v1` is produced upstream by `..\Data_Collection\scripts\pregame_dataset.py` from full-league player/team game logs. Every feature is calculated before the current game is added to history. Completed-game data appears only under `actual` and must never be passed into the simulation input loader.

Each game record includes:

- Stable game/date, home/away team, and chronological calibration/validation/holdout split.
- League pace/offensive-rating context and transparent expected pace, team offensive ratings, and game total.
- Per-team season-to-date, home/away, and last-5/10/20 rolling summaries.
- Pregame rest days, travel placeholder, expected active roster, expected starters, rotation size, and canonical player overrides.
- Player appearance counts, last appearance date, recent rolling totals, and starter-frequency provenance.
- Actual team/player box scores and actual starters only as evaluation labels.

`availability_source` and `starter_source` are required provenance fields. Current availability is inferred from prior appearances. Exact actual starters are retained only where the official `boxscoretraditionalv3` cache is populated; all other expected starters use explicitly labeled prior-frequency or minutes fallbacks. `..\Data_Collection\scripts\validate_pregame_dataset.py` enforces chronology, player-date leakage, roster/starter shape, split order, game uniqueness, and expected-context validity.

The full 2025–26 files are:

- `..\Data_Collection\data\raw\player_game_logs_2025-26_regular_season_all.json`: 26,651 player-game rows.
- `..\Data_Collection\data\raw\team_game_logs_2025-26_regular_season_all.json`: 2,460 team-game rows and 1,230 games.
- `..\Data_Collection\data\published\pregame\pregame_profiles_2025-26_regular_season.json`: 1,069 eligible dated games across 30 teams.
- `..\Data_Collection\data\published\historical_variability_2025-26_regular_season_all.json`: 661 descriptive player profiles.

## Calibrated mechanics controls

`configs/calibration_defaults_v1.json` mirrors the active `SimConfig` defaults:

| Field | Default | Meaning |
|---|---:|---|
| `shot_accuracy_adjustment` | -0.020 | Additive field-goal make-probability adjustment after player baseline selection and before bounding |
| `three_point_attempt_weight_multiplier` | 0.90 | Multiplier on the 3-point option during shot-zone selection; it changes shot mix, not player 3P accuracy |
| `offensive_rebound_probability_multiplier` | 1.20 | Multiplier on the lineup-derived offensive-rebound probability before bounding |
| `assist_probability_on_made_fg` | 0.62 | Probability that a made non-putback field goal receives an assist |

These are simulator-mechanics calibration constants, not player predictions. Alternate settings can be supplied to `scripts/run_calibration.py --sim-config-file` and must be logged with the input version, games, seeds, and acceptance results.

## Historical variability profiles

`..\Data_Collection\scripts\build_historical_variability.py` creates the published historical-variability input from NBA regular-season player game logs. It separately measures raw game totals, per-36 opportunity-adjusted rates, shooting/attempt rates, availability proxies, and home/away splits. Each distribution includes sample size, mean, sample standard deviation, minimum, maximum, and p05/p25/p50/p75/p95.

The matching filtered game logs are retained under `..\Data_Collection\data\raw\` for auditability. The Simulator reads descriptive distributions from `..\Data_Collection\data\published\`; this is an interim stochastic layer, not a trained player-performance prediction model.

## Simulation audit outputs

Each game retains the context, environment seed and factors, sampled opportunity/efficiency profiles, active roster, starters, exclusions, minute-target totals, and matchup adjustments in `simulation_audit`. Batch and season CSV exports write these records to separate context, player-profile, and team-matchup files.
