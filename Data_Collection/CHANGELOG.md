---
title: NBA Data Collection Changelog
project: NBA Data Collection
file_type: changelog
status: active
purpose: Record source, transformation, QA, versioning, and publication changes.
usage: Add an entry whenever collection behavior or a published data contract changes.
last_updated: 2026-08-15
---

# Changelog

## 2026-08-15

- Expanded Data Collection from Simulator-only support into the authoritative shared data layer for the NBA workspace.
- Published historical regular-season standings, playoff results, and franchise-lineage rules under `data/published/historical/`.
- Migrated the Basketball Reference pullers, notebook wrappers, and source settings from `Long_Term_Performance_Rewards`; future retrieval preserves season-level raw HTML.
- Added `historical_league_results_v1` manifest generation with schema, row-count, season-span, and SHA-256 evidence plus offline contract tests.
- Switched the rewards project to one-way publication consumption and verified all ten analytical report CSVs remained byte-for-byte identical.
- Migrated Simulator's structural pilot dataset and its builder into `data/published/calibration/` and `scripts/`, added a hash manifest, and switched Simulator's calibration default to the upstream publication.
- Added the complete 2024-25 regular-season historical bundle: full-league game logs, strict all-team enrichment, player variability, dated pregame records, QA reports, an immutable profile version, and an eleven-artifact SHA-256 bundle manifest including starter diagnostic evidence.
- Attempted one conservative 2024-25 exact-starter diagnostic. The official v3 endpoint timed out/failed, so bulk hydration was not started; checkpoint and attempt evidence were retained in the season manifest.

## 2026-08-14

- Created the sibling Data_Collection project outside NBA Simulator.
- Moved retrieval, historical enrichment, variability, pregame construction, QA, manifests, raw data, immutable versions, and published datasets without deleting artifacts.
- Established a one-way publication boundary: Data_Collection publishes; Simulator consumes.
- Added project documentation, front matter, archive conventions, and automated documentation/data-contract tests.
- Retried checkpointed starter hydration. No new games were retrieved because all three supported official access paths remain blocked; preserved the existing 72 successful games and 1,158 failures.
- Improved starter-cache provenance so successful providers and failed retry providers are recorded separately instead of overwriting the source label when a retry yields no data.
- Hardened exact-starter retrieval with persistent sessions, complete consistent headers, safe 25-game batches, 3â€“6 second jitter, transient-only retries, `Retry-After` support, a two-403 circuit breaker, one-game diagnostics, dry-run planning, per-attempt logs, and automatic checkpoint snapshots.
- Added `docs/STARTER_HYDRATION_RUNBOOK.md`, a minimal `requests` dependency declaration, and offline regression tests for selection, retries, logging, provenance, and circuit breaking.
