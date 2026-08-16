---
title: Exact Starter Hydration Runbook
project: NBA Data Collection
file_type: operational_runbook
status: active
purpose: Define safe diagnosis, pacing, checkpointing, and staged resumption of official NBA starter retrieval.
usage: Follow before every exact-starter network run and stop when the circuit breaker reports access denial.
last_updated: 2026-08-14
---

# Exact Starter Hydration Runbook

The retained checkpoint currently contains 72 of 1,230 games. Do not delete or
re-request successful games. NBA Stats v3, NBA Stats v2, and the live-data CDN
were still blocked on 2026-08-14, so allow at least a 24â€“48 hour cooldown before
the next network probe.

## Safety defaults

- One persistent HTTP session and one worker.
- At most 25 unresolved games per invocation.
- Random 3â€“6 second spacing between games.
- Retries only for timeouts, connection errors, HTTP 429, and temporary 5xx errors.
- No retry for HTTP 403; stop after two consecutive access denials.
- Save after every attempted game and snapshot the pre-run checkpoint under
  `data/raw/__Archive__/`.
- Append compact request outcomes to `data/raw/starter_hydration_attempts.jsonl`.

## Before making a request

Preview the exact work without network access:

```powershell
python scripts/pull_historical_league_data.py --reuse-player-logs --hydrate-starters --dry-run --diagnostic-game-id 0022500071
```

After the cooldown, open that failed game's official endpoint in a normal browser
on the same connection. If the browser receives HTTP 403, do not run Python.

## One-game diagnostic

Only after the browser succeeds, request exactly one unresolved game:

```powershell
python scripts/pull_historical_league_data.py --reuse-player-logs --hydrate-starters --diagnostic-game-id 0022500071 --starter-source nba_stats_v3
```

Inspect the printed `starter_hydration_last_run`, the checkpoint metadata, and
the JSON-lines attempt log. Stop if the circuit breaker or another 403 appears.

## Staged resume

If the diagnostic succeeds, increase conservatively and review after each run:

```powershell
python scripts/pull_historical_league_data.py --reuse-player-logs --hydrate-starters --batch-size 10
python scripts/pull_historical_league_data.py --reuse-player-logs --hydrate-starters --batch-size 25
```

Use repeated 25-game runs with substantial pauses. Do not remove pacing, enable
concurrency, rotate proxies, or otherwise attempt to circumvent access controls.

## Source fallback order

Prefer `nba_stats_v3`, then test `live_cdn`, then `nba_stats_v2`, always with a
single diagnostic game first. Each newly successful record stores its provider;
cache metadata separately records successful and attempted sources.

