---
title: NBA Analytics Workspace
project: NBA Workspace
file_type: workspace_readme
status: active
purpose: Define project ownership and the shared NBA data boundary.
usage: Start here before adding datasets, retrieval code, simulations, or policy analyses.
last_updated: 2026-08-15
---

# NBA Analytics Workspace

This workspace separates reusable NBA data creation from downstream analytical products.

## Project ownership

| Project | Owns |
| --- | --- |
| `Data_Collection` | Retrieval, raw source retention, transformations, QA, schemas, manifests, versions, and shared publications |
| `Simulator` | Possession simulation, calibration execution, backtesting, simulation outputs, and calibration evidence |
| `Long_Term_Performance_Rewards` | Reward/penalty methodology, thresholds, analysis, and project reports |

## Mandatory data boundary

Reusable source data and dataset-building code belong in `Data_Collection`. Consumer projects read stable files beneath `Data_Collection/data/published` and must not import collection implementation modules or maintain competing active copies.

Project-owned outputs remain with their producer. Simulator output distributions and calibration reports stay in `Simulator`; reward-policy reports stay in `Long_Term_Performance_Rewards`.

## Shared historical results

The long-run regular-season standings, playoff results, franchise-lineage rules, and structural calibration fixture are published at:

- `Data_Collection/data/published/historical/`
- `Data_Collection/data/published/calibration/`

Refresh historical standings and playoffs with:

```powershell
cd C:\Users\clinn\Documents\NBA\Data_Collection
python scripts\pull_historical_results.py
```

Each project maintains its own README and project reference. Superseded files are preserved in dated `__Archive__` folders rather than deleted.

## Version-control hygiene

The workspace and each project maintain layered `.gitignore` files. Git should
retain source code, tests, notebooks without saved runtime state, configuration,
documentation, schemas, and Data Collection manifests. Reproducible or
machine-local artifacts remain on disk but are not added to version control:

- Data Collection raw responses, publications, immutable dataset copies, and QA reports
- Simulator datasets, simulation outputs, and calibration reports
- Long-Term Performance Rewards generated report runs and `latest_run.json`
- Python/Jupyter caches, local environments, coverage/build products, editor state, logs, temporary files, local databases, serialized models, and secrets
- All `__Archive__` contents

Small fixtures needed for automated tests should live beneath a test fixture
folder rather than a generated output directory. `.gitignore` does not remove a
file that Git already tracks; use an explicit Git index cleanup when Git becomes
available if generated artifacts had previously been committed.
