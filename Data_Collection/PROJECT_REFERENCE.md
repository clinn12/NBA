---
title: NBA Data Collection Project Reference
project: NBA Data Collection
file_type: project_reference
status: active
purpose: Preserve project boundaries, decisions, status, limitations, and open data work.
usage: Review before changing a source, schema, calculation, or publication contract.
last_updated: 2026-08-15
---

# Project Reference — NBA Data Collection

## Purpose

Create reproducible historical NBA inputs outside the simulation engine and publish them through a stable, auditable contract.

## Boundary decisions

- `Data_Collection` owns retrieval, raw data, transformations, QA, pregame feature construction, manifests, immutable versions, and published inputs.
- `Simulator` owns event resolution, game/season simulations, calibration evaluation, backtests, and simulator-only calibration fixtures.
- `Long_Term_Performance_Rewards` owns reward-policy thresholds, streak/window calculations, and reports.
- Downstream projects may read `data/published/` and QA/manifests but must not import upstream implementation code.
- Historical calculations are transparent formulas, not fitted predictive models.
- Predictive datasets may later be published through the same consumer contract by a different upstream project.
- Every maintained source/document follows front-matter, documentation, and `__Archive__` standards.
- Exact-starter retrieval uses conservative one-worker batches, persistent sessions, 3â€“6 second jitter, status-aware retries, a two-denial circuit breaker, per-attempt JSON-lines logging, and automatic pre-run checkpoint snapshots.

## Current published scope

- Four-team enriched 2025–26 regular-season historical profiles.
- Four-team and all-team descriptive variability profiles.
- All-team dated pregame dataset with chronological splits and QA report.
- Content-addressed historical profile snapshots and registry.
- Basketball Reference standings for 1960-2026, playoff results for 1960-2025, and 25 explicit franchise-lineage rules, governed by `historical_league_results_v1`.
- Full 2024-25 all-team Simulator bundle: player/team game logs, enriched team profiles, player variability, dated pregame records, QA evidence, hashes, and an immutable profile snapshot.

## Known limitations

- Exact starter hydration remains incomplete: 72 of 1,230 games are cached. On 2026-08-14, NBA Stats v3 and the live-data CDN returned HTTP 403, while the legacy v2 endpoint returned an unexpected blocked response shape. The checkpoint remains resumable when official access is restored.
- Official pregame injury-report coverage has not yet been added.
- Possession-level lineup combination inputs are not yet published.

## Open work

1. Resume exact starter/active-player hydration.
2. Add a versioned official injury/availability source.
3. Add lineup-combination and richer schedule/travel inputs.
4. Expand enriched published profiles to all 30 teams and additional seasons.
5. Add an explicit publication manifest for every remaining file in `data/published/`; historical league results now have one.

## 2026-08-15 workspace consolidation

- Migrated regular-season standings, playoff results, franchise lineage, retrieval scripts, configuration, and notebook wrappers from `Long_Term_Performance_Rewards`.
- Established `data/published/historical/` as the shared consumer contract and `data/raw/basketball_reference/` as the retained source-response layer.
- Added manifest hashing, schema/row/season validation, offline publication tests, and a combined refresh command.
- Verified the rewards project regenerated all ten analytical CSVs byte-for-byte from the migrated publications before its local source assets were archived.

## 2026-08-15 historical expansion

- Pulled the complete 2024-25 regular season: 26,306 player-game rows, 2,460 team-game rows, 30 teams, and 1,230 games.
- Published 30 enriched team profiles covering 569 players; every official enrichment feed completed and QA passed with zero flags.
- Published 654 descriptive variability profiles and 1,069 time-valid pregame games. Pregame QA passed with 619 calibration, 224 validation, and 226 holdout games.
- Froze immutable profile version `historical_enriched_2024_25_regular_season__sha256_068eedafc5e3` and created a bundle manifest hashing eleven raw, published, QA, and starter-diagnostic artifacts.
- Exact starters and official pregame injuries remain unavailable for 2024-25; pregame availability and starter provenance are explicit proxies.
- A one-game official v3 starter diagnostic for game `0022400001` failed after two request timeouts and a connection failure. No bulk hydration was attempted; the empty checkpoint and attempt log are retained and hashed in the season bundle.

## Maintenance convention

Update this file and `CHANGELOG.md` after source, formula, schema, QA, or publication changes.

## 2026-08-16 Git ignore policy

- Reproducible `data/raw`, `data/published`, `data/versions`, and `reports`
  artifacts remain local and are excluded from Git to avoid committing large
  generated files.
- Lightweight dataset manifests remain eligible for version control because
  they record governed contracts, hashes, and provenance.
- Source code, configs, schemas, documentation, notebooks, and tests remain
  eligible for version control.
- Python/Jupyter caches, local environments, editor state, logs, secrets, model
  binaries, and all `__Archive__` contents are ignored.
