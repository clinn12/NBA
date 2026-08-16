---
title: NBA Simulator Folder Structure
project: NBA Simulator
file_type: project_standard
status: active
purpose: Define folder ownership, active-file placement, and non-destructive archive conventions.
usage: Follow whenever adding, moving, superseding, or archiving project files.
last_updated: 2026-08-14
---

# Project Folder Structure

The project root contains only the primary orientation and governance files: `README.md`, `PROJECT_REFERENCE.md`, and `CHANGELOG.md`.

| Folder | Purpose |
| --- | --- |
| `nba_simulator/` | Reusable possession engine, game context, season logic, historical validation, and data adapters |
| `scripts/` | Directly runnable simulation, calibration, and backtest workflows |
| `tests/` | Automated structural, reproducibility, calibration, and consumer-contract tests |
| `notebooks/` | Active Jupyter notebooks |
| `configs/` | Versioned calibration defaults and plans |
| `examples/` | Sample schedules and game-context inputs |
| `docs/` | Methodology, data dictionary, calibration history, and structural documentation |
| `data/` | Simulator-owned calibration fixtures and archived pre-separation structure |
| `outputs/` | Dated simulation and backtest outputs |
| `reports/` | Simulator calibration and tuning reports |

The sibling `C:\Users\clinn\Documents\NBA\Data_Collection` project owns retrieval, raw and derived data, pregame construction, data QA, manifests, immutable versions, and the canonical `data/published/` consumer files. Simulator code may read those publications but must not import Data Collection implementation modules.

## Archive policy

Every maintained category has an `__Archive__` folder. Move superseded or historical material there instead of deleting it. Archived code and notebooks are retained for reference but are not imported, tested, or used by active commands. Generated dated directories beneath `outputs/` do not each require another archive layer.

When archiving a file, prefer a descriptive name containing its status or archival date. Update `PROJECT_REFERENCE.md` when the archived item affected a documented workflow.
