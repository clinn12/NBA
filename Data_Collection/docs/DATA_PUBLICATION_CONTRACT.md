---
title: NBA Data Publication Contract
project: NBA Data Collection
file_type: data_contract
status: active
purpose: Define stable files and the ownership boundary exposed to NBA consumer projects.
usage: Follow when publishing data or changing any downstream consumer input path.
last_updated: 2026-08-15
---

# Data Publication Contract

The canonical publication root is `data/published/`. Consumer projects may read published files and related QA/manifests; they must not import `data_collection` or `scripts` implementation modules.

## Current files

- `real_teams_2025-26_regular_season.json`: enriched canonical team/player profiles.
- `historical_variability_2025-26_regular_season.json`: four-team descriptive game-form profiles.
- `historical_variability_2025-26_regular_season_all.json`: all-team descriptive game-form profiles.
- `pregame/pregame_profiles_2025-26_regular_season.json`: all-team dated pregame records.
- `pregame/pregame_profiles_2025-26_regular_season_pilot.json`: small structural/loader fixture.
- `pregame/pregame_profiles_2025-26_regular_season_qa.json`: published QA summary.
- `historical/nba_standings.csv`: validated regular-season standings history from Basketball Reference.
- `historical/nba_playoffs.csv`: validated playoff results with champion and conference-champion flags.
- `historical/franchise_lineage.csv`: explicit historical-to-current franchise normalization rules.
- `calibration/pilot_games_2025-26_regular_season.json`: 16-game structural reconstruction fixture; contains look-ahead inputs and is not predictive-backtest eligible.

`data/manifests/historical_league_results.json` records paths, schemas, row counts, season spans, and SHA-256 hashes for the three historical publications. `Long_Term_Performance_Rewards` consumes these files while retaining ownership of its policy thresholds and reports.

`data/manifests/pilot_calibration_games.json` governs the structural pilot publication consumed by Simulator's calibration harness.

## 2024-25 historical bundle

- `real_teams_2024-25_regular_season.json`: enriched all-team season-average profiles.
- `historical_variability_2024-25_regular_season_all.json`: descriptive player game-form profiles.
- `pregame/pregame_profiles_2024-25_regular_season.json`: strictly dated all-team pregame records.
- `pregame/pregame_profiles_2024-25_regular_season_qa.json`: leakage, chronology, roster, split, and provenance QA.

Raw player/team logs and enrichment responses remain under `data/raw/`. `data/manifests/historical_2024_25_regular_season_bundle.json` hashes every raw, published, and QA artifact. The enriched team profile is also frozen as content-addressed version `historical_enriched_2024_25_regular_season__sha256_068eedafc5e3`.

Published schemas must remain versioned and backward-compatible or be released under a new schema/version identifier. Actual outcomes in pregame records remain evaluation labels and must never enter pregame simulator features.
