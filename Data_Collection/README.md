---
title: NBA Data Collection
project: NBA Data Collection
file_type: project_readme
status: active
purpose: Explain historical NBA retrieval, transformation, QA, versioning, and publication workflows.
usage: Start here before refreshing or publishing datasets consumed by any NBA project.
last_updated: 2026-08-15
---

# NBA Data Collection

This project owns the upstream creation of validated, versioned NBA datasets shared across the `NBA` workspace. It is intentionally separate from consumer projects such as `Simulator` and `Long_Term_Performance_Rewards`, which read publications but do not retrieve or construct shared inputs.

Project folder: `C:\Users\clinn\Documents\NBA\Data_Collection`

## Responsibilities

- Retrieve official NBA player, team, starter, tracking, hustle, defense, and clutch data.
- Preserve raw source responses and resumable caches.
- Calculate transparent historical enrichment and variability fields.
- Build strictly time-valid rolling pregame datasets.
- Run data-quality and leakage checks.
- Freeze immutable versions and publish canonical consumer files.
- Retrieve Basketball Reference standings and playoff history, preserve season-level raw HTML, and publish shared franchise-lineage rules.

## Typical workflow

```powershell
python scripts/pull_historical_league_data.py --reuse-player-logs --hydrate-starters
python scripts/pull_real_team_data.py --all-teams
python scripts/build_historical_variability.py --all-teams --reuse-raw
python scripts/pregame_dataset.py
python scripts/validate_pregame_dataset.py
python scripts/enrichment_qa.py
python scripts/freeze_historical_dataset.py
python scripts/pull_historical_results.py
```

Published inputs live in `data/published/`. Downstream projects read those files through sibling-project paths and must not import collection implementation modules.

Raw responses, generated publications, immutable version copies, and QA reports
are intentionally excluded by `.gitignore` because they are reproducible and
can be large. Dataset manifests remain eligible for version control as the
lightweight record of governed contracts and hashes. A new checkout must run the
documented collection/publication workflow or receive the governed datasets
through a future artifact store before downstream projects can execute.

Historical league-results publications live in `data/published/historical/`. Use `scripts/pull_historical_results.py` to refresh both standings and playoffs, or the individual scripts/notebooks for a single source family. The initial migrated publications contain 1,595 standings rows (1960-2026), 886 playoff rows (1960-2025), and 25 franchise-lineage rules.

The structural-only 16-game calibration fixture lives in `data/published/calibration/` and is rebuilt with `scripts/build_pilot_calibration_dataset.py`. Its manifest explicitly prohibits predictive-backtest use.

## Additional historical season

The 2024-25 regular season is now published as a full 30-team historical bundle:

- 26,306 player-game rows and 2,460 team-game rows covering all 1,230 games.
- Enriched season-average profiles for 30 teams and 569 players; QA passes with zero flags.
- 654 player variability profiles across 30 teams.
- 1,069 strictly dated pregame records with calibration/validation/holdout splits; leakage and schema QA pass.

The governed bundle is recorded in `data/manifests/historical_2024_25_regular_season_bundle.json`. Exact starter and official injury coverage are both currently zero for this season, so the pregame publication explicitly uses prior-minutes and prior-appearance proxies.

A single official v3 starter diagnostic was attempted for game `0022400001`; it failed by timeout/connection error. No bulk starter requests were launched, and the checkpoint plus attempt log are retained as bundle evidence.

## Safe starter hydration

Install the minimal HTTP dependency with `python -m pip install -r requirements.txt`.
Starter hydration is checkpointed and defaults to one worker, 25 unresolved games,
3â€“6 second jitter, status-aware transient retries, and a circuit breaker after two
HTTP 403 responses. Always preview the selection first:

```powershell
python scripts/pull_historical_league_data.py --reuse-player-logs --hydrate-starters --dry-run --diagnostic-game-id 0022500071
```

Follow `docs/STARTER_HYDRATION_RUNBOOK.md` before making a network request. The
official sources were still blocked on 2026-08-14, so the next probe must wait for
the documented cooldown and begin with one game.

## Validation

```powershell
python scripts/check_documentation.py
python -m unittest discover -s tests -v
```
