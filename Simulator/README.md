---
title: NBA Possession Simulator
project: NBA Simulator
file_type: project_readme
status: active
purpose: Orient users to project capabilities, structure, commands, and current readiness.
usage: Start here before running simulations or contributing simulator code.
last_updated: 2026-08-15
---

# NBA Possession Simulator

A possession-by-possession NBA game simulator designed to produce completed-game results, play-by-play, and NBA.com-style box-score views.

Project folder: `C:\Users\clinn\Documents\NBA\Simulator`

Historical data collection is a separate sibling project at `C:\Users\clinn\Documents\NBA\Data_Collection`. The Simulator reads validated publications from `..\Data_Collection\data\published` and does not import collection implementation code.

Generated files beneath `outputs/`, `reports/`, and the Simulator-local `data/`
folder are excluded from Git. Shared datasets belong in Data Collection, while
simulation and calibration outputs are reproducible run artifacts. Source code,
configuration, documentation, examples, notebooks, and test fixtures remain
eligible for version control.

## Project status

The simulator's core mechanics, real-team profile loading, game-context overrides, game-specific profile sampling, and distribution validation are implemented. The active `calibration_defaults_v2` passed its frozen 176-game formal holdout at 500 draws per game, supporting aggregate game and team-outcome simulation for the tested 2025-26 pregame-data scope. Outputs are still simulation estimates rather than production predictions because exact starter and official pregame availability coverage remain incomplete, and player-minute distributions are not yet calibrated.

## Key capabilities

- Possession-level field goals, free throws, turnovers, rebounds, blocks, fouls, substitutions, timeouts, period breaks, and overtime.
- Player tendencies, defender assignment, switching/help defense, lineup chemistry, game-state strategy, and fatigue.
- Traditional, advanced, scoring, and defense box-score views.
- Per-game calibration diagnostics and Monte Carlo calibration summaries.
- Dataset-neutral game contexts for exclusions, starters, minutes limits, rest, travel, and source metadata.
- Independently sampled opportunity and efficiency profiles for every repeated game run.
- Shared game environments, active-roster matchup adjustments, closing lineups, blowout rotations, and late-game strategy.
- Evolving season workload state and complete sampled-input audit exports.

## Working files

- `notebooks/__Archive__/Simulation_original_20260524.ipynb` — preserved original source notebook.
- `notebooks/Simulation_robust_copy.ipynb` — active robust simulator notebook.
- `docs/__Archive__/NBA_SIM_HANDOFF_20260501.md` — archived original handoff.
- `PROJECT_REFERENCE.md` — living decisions, status, and remaining work.
- `docs/DATA_DICTIONARY.md` — input-field definitions and source requirements.
- `docs/METHODOLOGY.md` — modeling assumptions and event flow.
- `docs/CALIBRATION.md` — calibration targets and validation procedure.
- `docs/FOLDER_STRUCTURE.md` — folder ownership and archive policy.
- `docs/DOCUMENTATION_STANDARDS.md` — mandatory comments, docstrings, notebook headers, and review checks.

Additional calibration files:

- `configs/calibration_plan.json` — ordered parameter stages, ablation variants, and acceptance thresholds.
- `..\Data_Collection\scripts\build_pilot_calibration_dataset.py` — upstream labeled historical-game pilot construction.
- `scripts/run_calibration.py` — Monte Carlo validation, ablations, CSV reports, and acceptance checks.

Retrieval, historical enrichment, variability generation, pregame construction, data QA, and immutable dataset versioning live in the sibling Data Collection project. See `..\Data_Collection\README.md` and `..\Data_Collection\docs\DATA_PUBLICATION_CONTRACT.md`.

## Quick start

In the active notebook, create placeholder teams and simulate a game:

```python
home = create_placeholder_team("Home Team", seed=1)
away = create_placeholder_team("Away Team", seed=2)
game = simulate_game_robust(home, away, SimConfig(seed=3))
```

Useful outputs include:

```python
game["team_table"]
game["player_table"]
game["play_by_play"]
game["box_score_views"]
game["calibration"]
```

## Development documentation standard

Every active Python file must explain its purpose and usage at the top, and every public class/function must have a useful docstring. Non-obvious NBA rules, statistical formulas, time-valid data boundaries, state mutations, caching, and fallbacks require intent-focused inline comments. Every active notebook must open with Purpose, How to use, inputs/outputs, and active-versus-historical guidance.

Run both checks after adding or materially changing code:

```powershell
python scripts/check_documentation.py
python -m unittest discover -s tests -v
```

The documentation audit is also part of the automated regression suite. Full requirements are in `docs/DOCUMENTATION_STANDARDS.md`.

## Running without Jupyter

`scripts/run_simulation.py` provides the same robust simulator from a standard Python command line; it has no third-party runtime dependency. `nba_simulator/simulator_core.py` is the single canonical engine, and `notebooks/Simulation_robust_copy.ipynb` imports that module, so notebook and script runs use the same logic.

```powershell
# Repeated matchup; defaults to 10 game runs and writes dated CSVs.
python scripts/run_simulation.py matchup --home-name Knicks --away-name Celtics

# One detailed game; writes a possession-by-possession CSV.
python scripts/run_simulation.py game --home-name Knicks --away-name Celtics

# Repeated seasons using a JSON schedule.
python scripts/run_simulation.py season --schedule examples/sample_schedule.json --season-runs 10

# Nested season mode.
python scripts/run_simulation.py season --schedule examples/sample_schedule.json --season-runs 10 --season-game-runs 10

# Real-profile game with historical variability and context overrides.
python scripts/run_simulation.py game --team-data ..\Data_Collection\data\published\real_teams_2025-26_regular_season.json --home-abbr NYK --away-abbr BOS --context examples/sample_game_context.json
```

Use `--no-export` for an in-memory-only run, or `--output-dir my_outputs` to choose an output parent folder.

## Published historical inputs

Data Collection now publishes full-league historical inputs for both 2024-25 and 2025-26. The 2024-25 bundle includes enriched season averages, player variability, and a strictly dated pregame dataset suitable for additional backtesting. Select the desired season explicitly through the existing `--team-data`, variability, or backtest input arguments; the active default remains the governed 2025-26 dataset.

The initial real-data target is 2025–26 regular-season averages for NYK, SAS, BOS, and LAL. Pull the official NBA Stats dashboard data with:

```powershell
python ..\Data_Collection\scripts\pull_real_team_data.py
```

This publishes the default historical input at `Data_Collection\data\published\real_teams_2025-26_regular_season.json`. Raw feeds and transformation logic remain upstream; the Simulator consumes only the validated publication contract.

In the notebook, load a pulled team through the existing `create_team` function:

```python
from nba_simulator.real_team_loader import build_real_team, load_real_team_payload

payload = load_real_team_payload("../Data_Collection/data/published/real_teams_2025-26_regular_season.json")
knicks = build_real_team(payload, "NYK", create_team)
celtics = build_real_team(payload, "BOS", create_team)
```

## Building historical variability profiles

Create the descriptive game-to-game variability dataset for the initial teams with:

```powershell
python ..\Data_Collection\scripts\build_historical_variability.py
```

It publishes a versioned profile beneath `Data_Collection\data\published` and retains filtered source logs upstream. The Simulator uses these descriptive distributions for bounded game-specific historical profile draws. They are calculations, not a trained performance model.

## Single-game possession log

Use `simulate_single_game_robust` for a detailed single-game output. It returns the completed game plus `possession_log` and, by default, saves `single_game_possession_log.csv` beneath `outputs/YYYYMMDD/`. Each row represents one actual possession; offensive-rebound continuations remain in the same row. It includes the offense/defense, period and clock range, score before/after, points scored, event flags, and an `event_details` JSON field containing the possession event sequence.

## Individual-game context and sampling

`GameContext` keeps the input dataset separate from game-specific assumptions. The selected dataset supplies the default roster and expectations; context overrides can exclude players, set starters, change the rotation size, impose minutes limits, and describe rest or travel.

```python
context = GameContext(
    game_id="nyk_bos_example",
    dataset_id="real_teams_2025_26_regular_season",
    source_type="historical",
    profile_mode="historical",
    variability_path="../Data_Collection/data/published/historical_variability_2025-26_regular_season.json",
    excluded_players={"Boston Celtics": ["Example Player"]},
    player_overrides={
        "New York Knicks": {
            "Example Player": {"expected_minutes": 28, "minutes_limit": 30}
        }
    },
)

batch = simulate_game_batch_robust(
    knicks,
    celtics,
    SimConfig(seed=100, game_runs=1000),
    game_context=context,
)
```

Every repeated run receives a different reproducible profile. Opportunity variables such as minutes and usage are sampled separately from efficiency variables. Team-level pace, shooting, foul, turnover, and rebounding conditions create correlated outcomes within a game.

Every result retains `simulation_audit`. CSV exports also create `*_simulation_context.csv`, `*_sampled_player_profiles.csv`, and `*_team_matchup_inputs.csv`.

## Historical distribution validation

Compare a real result with a simulation batch rather than expecting one run to reproduce the exact score:

```python
validation = validate_historical_game_distribution(
    batch,
    actual_score={"New York Knicks": 118, "Boston Celtics": 112},
)
```

The result reports score, margin, and total-point percentiles, the probability assigned to the real winner, and optional player-stat percentiles.

## Calibration pipeline

```powershell
python ..\Data_Collection\scripts\enrichment_qa.py
python ..\Data_Collection\scripts\freeze_historical_dataset.py
python ..\Data_Collection\scripts\build_pilot_calibration_dataset.py
python scripts/run_calibration.py --simulations-per-game 500
```

The current pilot contains 16 games where both opponents are in the four-team dataset. It uses completed-season profiles and actual players who appeared, so it is explicitly structural reconstruction—not a predictive backtest. Predictive mode rejects these look-ahead records. Reports are written beneath `outputs/calibration/YYYYMMDD/` and compare averages only, historical game-form sampling, and the full context/matchup system.

The current governed historical snapshot is identified in `..\Data_Collection\data\manifests\DATASET_REGISTRY.json`. Content-addressed versions are never overwritten.

The active calibrated mechanics are recorded in `configs/calibration_defaults_v2.json`: average possession time `13.5`, shot accuracy adjustment `-0.020`, 3-point attempt weight `0.75`, offensive-rebound probability multiplier `1.40`, assisted-make probability `0.62`, and steal share `0.53`. These are the default `SimConfig` settings. Use `--sim-config-file` to test a governed alternate without editing code.

## Full-league dated pregame workflow

The strictly time-valid workflow covers all 30 teams. Features for a game are calculated before that game's rows enter history; completed-game values are retained only beneath `actual` for evaluation.

```powershell
python ..\Data_Collection\scripts\pull_historical_league_data.py --reuse-player-logs --hydrate-starters
python ..\Data_Collection\scripts\pregame_dataset.py
python ..\Data_Collection\scripts\validate_pregame_dataset.py
python ..\Data_Collection\scripts\build_historical_variability.py --all-teams --reuse-raw
python scripts/run_pregame_backtest.py --split validation --simulations-per-game 20 --sim-config-file configs/calibration_defaults_v2.json
```

Expected availability is currently inferred from prior appearances. Exact starters are used where the resumable official box-score cache is populated; otherwise the builder explicitly labels its prior-starter-frequency or prior-minutes fallback. Official pregame injury reports and possession-level lineup combinations still require an upstream source.

`calibration_defaults_v2` passed every configured gate on all 220 validation games at 20 draws per game and then passed every pre-registered gate on the 176-game formal holdout at 500 draws per game. The formal run completed 88,000 simulations with zero runtime or structural failures; team-score MAE was `11.38`, margin MAE `14.09`, total-points MAE `17.74`, and winner Brier score `0.217`. The first 50 holdout games previously exposed under v1 were excluded exactly, and no tuning followed from the formal result.

## Next milestone

Complete official starter coverage and add sourced pregame injury/availability plus lineup-combination inputs. Then calibrate player minutes and rotations on calibration/validation data and evaluate that distinct future version on a newly reserved holdout. Do not tune v2 from its formal holdout result.

## Simulation run modes

The robust simulator uses three configurable run counts:

- `game_runs=10`: repeated runs for one matchup or a selected set of matchups.
- `season_runs=10`: independent full-season iterations.
- `season_game_runs=1`: simulations per scheduled game inside each season iteration. Set this above `1` to enable nested season mode.

Nested mode retains every simulation of every scheduled game. One run is randomly selected from each nested batch to produce an unbiased discrete season standing; the selected index and the full batch summary are included in the result for traceability.

```python
config = SimConfig(game_runs=10, season_runs=10, season_game_runs=1)

# One matchup, repeated 10 times by default.
matchup = simulate_game_batch_robust(home, away, config)

# A schedule contains (home, away) or (game_id, home, away) entries.
season = simulate_season_robust(schedule, config)

# Nested season mode: repeat each scheduled fixture 10 times per season iteration.
nested = simulate_season_robust(schedule, SimConfig(season_game_runs=10))
```

## CSV exports

Batch and season simulations save CSV outputs to `outputs/YYYYMMDD/` by default (for example, `outputs/20260719/`). Set `output_dir` to choose another parent location, or `output_dir=None` to keep results in memory only.

Matchup exports:

- `matchup_player_game_results.csv` and `matchup_team_game_results.csv` contain every raw simulation and therefore the full distributions.
- `matchup_player_summary.csv` and `matchup_team_summary.csv` contain mean, min, max, standard deviation, and p05/p25/p50/p75/p95 for every numeric stat.

Season exports provide the same four files with a `season_` prefix, plus `season_standings.csv` and `season_standings_summary.csv`. Game-level rows include `game_id`, `season_run`, `game_run`, `nested_game_run`, and `standings_selected`; player rows also include `player` and `team`. Team totals are supplied in their own files.
