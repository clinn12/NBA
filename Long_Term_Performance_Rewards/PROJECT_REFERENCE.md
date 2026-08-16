---
title: NBA Long-Term Performance Rewards Project Reference
project: NBA Long-Term Performance Rewards
file_type: project_reference
status: active
purpose: Preserve policy decisions, shared-data boundaries, methodology, validation, and open work.
usage: Review before changing data inputs, franchise lineage, thresholds, or report logic.
last_updated: 2026-08-16
---

# Project Reference

## Project Purpose

This project explores whether NBA teams should receive long-term rewards or penalties based on sustained performance patterns.

The central idea is that the NBA currently has limited long-term punishment for repeated losing and limited long-term reward for repeated winning. The project identifies teams that meet configurable eligibility rules for:

- Reward signals: playoff appearances, NBA championships, conference championships
- Penalty signals: missed playoffs, repeated lowest-win non-playoff seasons

## Current Folder Structure

- `Config/` - Analysis input paths and policy thresholds
- `__Archive__/Data/` - Former local source data retained only for provenance
- `Notebooks/` - Reward-analysis workbench; data-pull notebooks moved upstream
- `Reports/` - Generated output reports and AI-readable metadata
- `Scripts/generate_reports.py` - Repeatable script for generating reward and penalty reports
- `Scripts/run_pipeline.py` - Analysis-only report orchestration
- `Tests/` - Offline enforcement of the Data Collection consumer boundary

## Core Data Files

- `..\Data_Collection\data\published\historical\nba_standings.csv` - Regular-season standings
- `..\Data_Collection\data\published\historical\nba_playoffs.csv` - Playoff performance
- `..\Data_Collection\data\published\historical\franchise_lineage.csv` - Franchise normalization rules

The data currently covers NBA seasons from `1960` through `2025`.

## Important Project Decisions

1. Users may run the analysis through either `Scripts/run_pipeline.py` or
   `Notebooks/NBA_Playoffs_and_Champions.ipynb`; both call the same shared report
   generator.
2. Repeatable policy-analysis logic lives in `Scripts/`; shared retrieval and dataset creation live exclusively in `Data_Collection`.
3. `Config/analysis_settings.json` contains consumer paths and report thresholds. Collection configuration is upstream.
4. Franchise mapping is a governed shared publication named `franchise_lineage.csv`.
5. Reports are written to `Reports/`.
6. Every report execution writes to an immutable `run_YYYY_MM_DD_HHMMSS[_label]` folder using local time. `latest_run.json` is updated only after successful completion.
7. Report outputs should be understandable by both humans and AI agents.
8. The project uses non-overlapping streak/window logic so a qualifying period is not repeatedly counted.
9. Team names are normalized before identifying playoff, non-playoff, low-win, championship, and conference championship cohorts.
10. Documentation should explain what is happening, why it matters, and why the approach was chosen.

## Script Entry Points

Use the Anaconda Python found on this machine:

```powershell
C:\Users\clinn\anaconda3\python.exe
```

Generate reports from the current governed publications:

```powershell
C:\Users\clinn\anaconda3\python.exe Scripts\generate_reports.py
```

Run the analysis-only pipeline:

```powershell
C:\Users\clinn\anaconda3\python.exe Scripts\run_pipeline.py
```

Alternatively, open `Notebooks/NBA_Playoffs_and_Champions.ipynb` and run it from
top to bottom. Its editable controls are `config_path`, `run_name`, and the
optional `report_name` used for preview. The notebook displays effective inputs
and thresholds before execution, then shows the completed run directory and row
counts. It must remain a thin interface over `Scripts/generate_reports.py`.

Optionally label a run:

```powershell
C:\Users\clinn\anaconda3\python.exe Scripts\run_pipeline.py --run-name baseline
```

Refresh shared source publications from the sibling project:

```powershell
cd C:\Users\clinn\Documents\NBA\Data_Collection
python scripts\pull_historical_results.py
```

## Config Reference

Primary analysis config file:

```text
Config/analysis_settings.json
```

Analysis settings:

- `paths.standings`: standings CSV path
- `paths.playoffs`: playoffs CSV path
- `paths.team_mapping`: franchise mapping CSV path
- `paths.reports_dir`: output reports folder
- `thresholds`: reward and penalty eligibility settings

## Current Thresholds

- Playoff streak: `8`
- Playoff window: `8` appearances in `10` years
- Championship streak: `3`
- Championship window: `3` championships in `5` years
- Conference championship streak: `4`
- Conference championship window: `4` conference championships in `6` years
- Non-playoff streak: `5`
- Non-playoff window: `5` missed playoffs in `7` years
- Lowest-win teams per year: `3`
- Lowest-win streak: `2`
- Lowest-win window: `2` low-win seasons in `3` years

## Report Files

Primary output reports:

- `Output_Playoff_Streaks.csv`
- `Output_Playoff_Windows.csv`
- `Output_Championship_Streaks.csv`
- `Output_Championship_Windows.csv`
- `Output_Conference_Championship_Streaks.csv`
- `Output_Conference_Championship_Windows.csv`
- `Output_Non_Playoff_Streaks.csv`
- `Output_Non_Playoff_Windows.csv`
- `Output_Lowest_Win_Streaks.csv`
- `Output_Lowest_Win_Windows.csv`

AI-readable report metadata:

- `Reports/<run_id>/Report_Manifest.json` - Machine-readable report inventory, methodology, criteria, source files, thresholds, timestamps, and hashes
- `Reports/<run_id>/Report_Data_Dictionary.csv` - Column definitions
- `Reports/<run_id>/README_For_AI_Agents.md` - Plain-language guide to interpreting reports
- `Reports/<run_id>/Report_Parameters.csv` - Threshold values used for the report run

These files now live together inside each timestamped run folder. `Reports/latest_run.json` provides the current run ID and relative manifest path without duplicating the report files.

## Report Run Governance

- Folder pattern: `run_YYYY_MM_DD_HHMMSS` with an optional sanitized label.
- Time basis: the machine's local Eastern time; manifests also store UTC, timezone name, and offset.
- Collision behavior: append `_02`, `_03`, and so on rather than overwrite.
- Completion behavior: update `latest_run.json` only after all report and metadata files have been written.
- Reproducibility: retain source-data, analysis-config, and generator SHA-256 hashes in every run manifest.
- Historical flat files from before this convention are preserved beneath `Reports/__Archive__/`.

## Report Logic

Season alignment:

- Reports only use seasons that exist in both published standings and playoff datasets.
- This prevents newly pulled standings seasons from being incorrectly treated as non-playoff seasons before playoff data is complete.

Streak reports:

- Require consecutive qualifying seasons.
- Split long runs into non-overlapping streak chunks.
- Example: an 8-year playoff streak qualifies once for an 8-year threshold; a 16-year streak can qualify twice.

Window reports:

- Require a configured count of qualifying seasons inside a configured inclusive year span.
- Results are non-overlapping.
- Example: `5` missed playoffs in `7` years qualifies if the selected 5 missed-playoff seasons fit within a 7-year inclusive window.

Lowest-win reports:

- First identify non-playoff teams.
- For each season, rank those non-playoff teams by `WL_pct`.
- Keep the configured number of lowest-win teams per year.
- Apply streak/window logic to that derived cohort.

## Franchise Mapping Notes

Franchise mapping is intentionally explicit and governed upstream in:

```text
..\Data_Collection\data\published\historical\franchise_lineage.csv
```

Important current choices:

- Historical Nets names map to `Brooklyn Nets`.
- Historical Bullets/Packers/Zephyrs names map to `Washington Wizards`.
- Historical Warriors names map to `Golden State Warriors`.
- Historical Lakers names map to `Los Angeles Lakers`.
- `Charlotte Hornets` through `2002` maps to `New Orleans Pelicans`.
- `Seattle SuperSonics` through `2008` maps to `Oklahoma City Thunder`.

These are business-rule choices, not universal truths. Revisit them if the project needs a different franchise-lineage philosophy.

## Known Caveats

- Basketball Reference page structure can change, so upstream Data Collection parser validation is important.
- `nba_playoffs.csv` still contains some historical mojibake column names from earlier pulls, such as encoded less-than/greater-than symbols. The core report logic does not rely on those columns; cleanup must occur as a versioned upstream publication change.
- Offline boundary tests now verify source paths, prohibit active local shared datasets/pullers, and compare published bytes with the archived migration sources.
- Git was not available in the original shell session.
- Python was found at `C:\Users\clinn\anaconda3\python.exe`, but plain `python` was not on PATH in the shell used by Codex.

## Documentation Standard

Documentation in this project should be strong enough for a future human or AI agent to regain context without reconstructing intent from code alone.

Use this standard for scripts, notebooks, reports, and future files:

- Explain the purpose of the file near the top.
- Explain what the code does and why that behavior matters to the project.
- Document business rules explicitly, especially franchise mapping, thresholds, season eligibility, and non-overlapping logic.
- Prefer module and function docstrings for reusable code.
- Use comments sparingly inside functions, focused on reasoning or non-obvious choices.
- Keep notebooks readable as guided workflows: purpose, inputs, processing steps, outputs, and caveats.
- Keep generated report metadata agent-readable: criteria, interpretation, source files, thresholds, and column definitions.
- When a choice is debatable, document it as a project decision rather than hiding it as code.
- Avoid comments that merely restate a line of code.

Recommended docstring shape:

```python
def example(...):
    """
    Explain what this function does.

    Why it matters:
        Explain the project-level reason this function exists.

    Important behavior:
        Explain business rules, edge cases, or assumptions.
    """
```

## Good Next Steps

- Run `Scripts/generate_reports.py` with Anaconda Python and confirm report regeneration.
- Run `Scripts/run_pipeline.py` as the analysis-only pipeline test.
- Consider adding lightweight tests for streak/window edge cases.
- Keep the reward-analysis notebook as a thin wrapper around `Scripts/generate_reports.py` so notebook and script logic cannot drift.

## 2026-08-16 Folder Alignment

- Renamed the active Python package and command folder from `Utils` to `Scripts`.
- Moved the former `Data` folder beneath the root `__Archive__` because all active shared inputs are published by `Data_Collection`.
- Updated active documentation, notebook imports, tests, and commands to reflect the current folder names without changing report methodology.

## 2026-08-16 Timestamped Report Runs

- Replaced flat, overwriting report output with immutable `Reports/run_YYYY_MM_DD_HHMMSS[_label]/` folders.
- Added collision-safe suffixes, optional `--run-name`, source/config/generator hashes, local and UTC timestamps, and an atomic `Reports/latest_run.json` pointer.
- Preserved the former flat report files in a dated archive and verified the first structured run reproduced all ten analytical CSVs byte-for-byte.
- Keep `requirements.txt` updated if new Python packages are added.

## 2026-08-16 Notebook Entry-Point Cleanup

- Reduced the active rewards notebook from 25 historical/placeholder cells to a
  concise interactive workflow.
- Removed obsolete loading, cleaning, function-definition, and CSV-saving
  sections whose logic already lives in `Scripts/generate_reports.py`.
- Added robust project-root discovery, visible configuration review, optional
  run labeling, completed-run details, report row counts, and an optional report
  preview.
- Kept notebook outputs and execution counts empty in source control so the file
  opens cleanly and does not present stale results as current.

## 2026-08-16 Git Ignore Policy

- Generated `Reports/` contents and `latest_run.json` remain local and are not
  added to Git; `Reports/README.md` remains eligible for version control.
- Python/Jupyter caches, local environments, coverage/build files, editor and
  agent state, logs, temporary files, local databases, serialized models, and
  secrets are ignored.
- `__Archive__` contents remain retained locally but are excluded from Git.
- Source code, active notebooks, configuration, documentation, and tests remain
  eligible for version control.

## 2026-08-15 Data Migration

- Published the exact standings, playoff, and franchise-lineage inputs under the sibling Data Collection contract with SHA-256 manifest coverage.
- Moved the two retrieval scripts, their notebook wrappers, and collection settings upstream.
- Changed this project to consume only `Data_Collection/data/published/historical` inputs.
- Archived superseded local data, pullers, notebooks, and configurations without deleting them.
- Regenerated all ten analytical CSV reports and verified they were byte-for-byte identical to the preserved pre-migration baseline.
