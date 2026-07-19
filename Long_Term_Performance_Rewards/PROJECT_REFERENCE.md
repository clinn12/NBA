# Project Reference

## Project Purpose

This project explores whether NBA teams should receive long-term rewards or penalties based on sustained performance patterns.

The central idea is that the NBA currently has limited long-term punishment for repeated losing and limited long-term reward for repeated winning. The project identifies teams that meet configurable eligibility rules for:

- Reward signals: playoff appearances, NBA championships, conference championships
- Penalty signals: missed playoffs, repeated lowest-win non-playoff seasons

## Current Folder Structure

- `Config/` - Separate pipeline, data-pull, and analysis settings
- `Data/` - Source CSV files and franchise mapping rules
- `Notebooks/` - Notebook workbench for scraping and analysis
- `Reports/` - Generated output reports and AI-readable metadata
- `Utils/pull_nba_standings.py` and `Utils/pull_nba_playoffs.py` - Repeatable scripts for refreshing Basketball Reference source data
- `Utils/generate_reports.py` - Repeatable script for generating reward and penalty reports
- `Utils/run_pipeline.py` - Orchestrates data-pull and analysis stages

## Core Data Files

- `Data/nba_standings.csv` - Regular season standings data
- `Data/nba_playoffs.csv` - Playoff performance data
- `Data/team_mapping.csv` - Franchise name normalization rules

The data currently covers NBA seasons from `1960` through `2025`.

## Important Project Decisions

1. Notebooks remain as the exploratory workbench.
2. Repeatable pipeline logic lives in `Utils/` scripts, with pull scripts and analysis scripts kept separate by file responsibility.
3. Configuration is separated by responsibility: `Config/data_pull_settings.json` for scraping and `Config/analysis_settings.json` for report generation.
4. Franchise mapping was externalized to `Data/team_mapping.csv`.
5. Reports are written to `Reports/`.
6. Report outputs should be understandable by both humans and AI agents.
7. The project uses non-overlapping streak/window logic so a qualifying period is not repeatedly counted.
8. Team names are normalized before identifying playoff, non-playoff, low-win, championship, and conference championship cohorts.
9. Documentation should explain what is happening, why it matters, and why the approach was chosen.

## Script Entry Points

Use the Anaconda Python found on this machine:

```powershell
C:\Users\clinn\anaconda3\python.exe
```

Generate reports without scraping:

```powershell
C:\Users\clinn\anaconda3\python.exe Utils\generate_reports.py
```

Run the full pipeline:

```powershell
C:\Users\clinn\anaconda3\python.exe Utils\run_pipeline.py
```

Optional pipeline flags:

```powershell
C:\Users\clinn\anaconda3\python.exe Utils\run_pipeline.py --skip-standings
C:\Users\clinn\anaconda3\python.exe Utils\run_pipeline.py --skip-playoffs
C:\Users\clinn\anaconda3\python.exe Utils\run_pipeline.py --skip-reports
```

## Config Reference

Primary config file:

```text
Config/settings.json
```

`Config/settings.json` is now an orchestration file. It points to:

```text
Config/data_pull_settings.json
Config/analysis_settings.json
```

Data-pull settings:

- `start_year`: first season to process
- `paths.standings`: standings CSV path
- `paths.playoffs`: playoffs CSV path
- `processing.standings_completed_only`: whether standings pulls should avoid active incomplete seasons
- `processing.playoffs_completed_only`: whether playoff pulls should avoid incomplete playoff seasons
- `processing.request_timeout_seconds`: web request timeout

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

- `Reports/Report_Manifest.json` - Machine-readable report inventory, methodology, criteria, source files, thresholds
- `Reports/Report_Data_Dictionary.csv` - Column definitions
- `Reports/README_For_AI_Agents.md` - Plain-language guide to interpreting reports
- `Reports/Report_Parameters.csv` - Threshold values used for the report run

## Report Logic

Season alignment:

- Reports only use seasons that exist in both `Data/nba_standings.csv` and `Data/nba_playoffs.csv`.
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

Franchise mapping is intentionally explicit and editable in:

```text
Data/team_mapping.csv
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

- Basketball Reference page structure can change, so scraper validation is important.
- `nba_playoffs.csv` still contains some historical mojibake column names from earlier pulls, such as encoded less-than/greater-than symbols. The core report logic does not rely on those columns.
- The project has scripts but no formal test suite yet.
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

- Run `Utils/generate_reports.py` with Anaconda Python and confirm report regeneration.
- Run `Utils/run_pipeline.py --skip-standings --skip-playoffs` as a safe report-only pipeline test.
- Consider adding lightweight tests for streak/window edge cases.
- Keep notebooks as thin wrappers around `Utils/` scripts so notebook and script logic cannot drift.
- Keep `requirements.txt` updated if new Python packages are added.
