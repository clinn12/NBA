---
title: NBA Long-Term Performance Rewards
project: NBA Long-Term Performance Rewards
file_type: project_readme
status: active
purpose: Explain the policy-analysis workflow, shared data boundary, configuration, and outputs.
usage: Start here before generating or interpreting reward and penalty reports.
last_updated: 2026-08-16
---

# NBA Long-Term Performance Rewards

This project evaluates configurable long-term rewards and penalties for sustained NBA team performance. It identifies playoff, championship, conference-championship, missed-playoff, and low-win patterns across seasons.

## Project boundary

This project is a consumer of governed NBA data. The sibling project at `C:\Users\clinn\Documents\NBA\Data_Collection` owns retrieval, raw source preservation, cleaning, validation, franchise lineage, manifests, and publication.

The active analysis reads:

- `..\Data_Collection\data\published\historical\nba_standings.csv`
- `..\Data_Collection\data\published\historical\nba_playoffs.csv`
- `..\Data_Collection\data\published\historical\franchise_lineage.csv`

No active file in this project retrieves or creates shared source datasets. Superseded local data-pull assets are preserved beneath dated `__Archive__` folders.

## Active folders

- `Config/` - Policy-analysis input paths and thresholds.
- `Notebooks/` - Interactive reward-analysis workbench.
- `Scripts/` - Reusable report logic and the analysis-only pipeline.
- `Reports/` - Generated policy outputs and agent-readable metadata.
- `Tests/` - Offline checks for the Data Collection consumer boundary.
- `__Archive__/Data/` - Former local source datasets retained only for provenance.

## Run the analysis

Users can run the same analysis through either the pipeline script or the
interactive notebook. Both entry points load `Config/analysis_settings.json`
and call the shared production logic in `Scripts/generate_reports.py`, so report
methodology and output structure remain identical.

### Option 1: Pipeline script

```powershell
C:\Users\clinn\anaconda3\python.exe Scripts\run_pipeline.py
```

Every execution creates an immutable local-time folder such as `Reports/run_2026_08_18_143205/`. Add an optional descriptive suffix with:

```powershell
C:\Users\clinn\anaconda3\python.exe Scripts\run_pipeline.py --run-name baseline
```

Use `--config` to run a different governed analysis configuration:

```powershell
C:\Users\clinn\anaconda3\python.exe Scripts\run_pipeline.py --config Config\analysis_settings.json
```

### Option 2: Jupyter notebook

Open `Notebooks/NBA_Playoffs_and_Champions.ipynb` and run its cells from top to
bottom. Before generating reports, the notebook displays the resolved source
paths and effective thresholds. Set `run_name` to an optional label, then run
the generation cell. The final cells identify the exact output directory,
summarize report row counts, and allow interactive inspection of a selected
report.

The notebook is intentionally a thin interface. Do not copy report calculations
into it; add reusable behavior to `Scripts/generate_reports.py` so script and
notebook executions cannot drift.

Refresh shared historical inputs separately from the Data Collection project:

```powershell
cd C:\Users\clinn\Documents\NBA\Data_Collection
python scripts\pull_historical_results.py
```

## Configuration and reports

`Config/analysis_settings.json` contains the three published input paths, the `Reports` output path, and configurable streak/window thresholds. The analytical CSVs remain project-owned because they encode reward-policy decisions rather than reusable source data.

Each run folder contains all ten analytical CSVs, `Report_Manifest.json`, `Report_Parameters.csv`, `Report_Data_Dictionary.csv`, and `README_For_AI_Agents.md`. The manifest records local and UTC timestamps, timezone information, source hashes, configuration hash, generator hash, thresholds, methodology, and output inventory.

`Reports/latest_run.json` points to the newest successfully completed run. Existing run folders are never overwritten; a same-second collision receives `_02`, `_03`, and so on.

Generated files beneath `Reports/`, including `latest_run.json`, are excluded
from Git because every run is reproducible and machine-specific. The tracked
`Reports/README.md` documents the folder contract; report runs remain available
locally unless a user deliberately removes or archives them.

## Validation

```powershell
C:\Users\clinn\anaconda3\python.exe -m unittest discover -s Tests -v
```

The 2026-08-15 migration regenerated all ten analytical output CSVs from Data Collection publications and confirmed they were byte-for-byte identical to the preserved pre-migration baseline.
