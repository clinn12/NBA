---
title: NBA Data Collection Folder Structure
project: NBA Data Collection
file_type: project_standard
status: active
purpose: Define ownership and archive rules for collection code and data layers.
usage: Follow when adding, moving, publishing, or superseding files.
last_updated: 2026-08-15
---

# Folder Structure

| Folder | Ownership |
| --- | --- |
| `data_collection/` | Reusable source-independent calculations |
| `scripts/` | Retrieval, transformation, QA, versioning, and publication commands |
| `configs/` | Source-family paths and governed collection behavior |
| `notebooks/` | Thin interactive wrappers around canonical collection scripts |
| `tests/` | Documentation, dataset, manifest, and contract validation |
| `data/raw/` | Retained source responses, logs, and resumable caches |
| `data/published/` | Stable files exposed to consumer projects |
| `data/manifests/` | Dataset registry and content-addressed manifests |
| `data/versions/` | Immutable snapshots |
| `reports/` | Data QA reports |
| `docs/` | Standards and publication contracts |

Within the data layers, `data/raw/basketball_reference/` retains season-level source HTML and `data/published/historical/` exposes standings, playoffs, and franchise-lineage files to consumer projects.

Every maintained category has an `__Archive__` folder. Move superseded material there instead of deleting it. Generated version directories do not each require a nested archive.
