---
title: NBA Possession Simulation Methodology
project: NBA Simulator
file_type: methodology
status: active
purpose: Explain game construction, event flow, NBA rules, outputs, and interpretation boundaries.
usage: Review before changing simulator mechanics or interpreting simulation behavior.
last_updated: 2026-08-14
---

# Methodology

## Scope

The simulator models an NBA game as a sequence of possessions. It aims to generate internally consistent completed games and box-score statistics, not a detailed reproduction of every official play-by-play event.

## Event model

Included categories are 2PT field goals, 3PT field goals, free throws, turnovers, blocks, offensive and defensive rebounds, personal and shooting fouls, substitutions, full timeouts, and period boundaries.

Excluded categories include technicals, jump balls, detailed turnover subtypes, coach challenges, ejections, and detailed shot locations.

## Possession flow

1. Select an offensive action using player tendencies, lineup context, defense, game state, and clock.
2. Select shooter and primary defender; allow switching and help defense where relevant.
3. Resolve turnover, foul, or shot outcome.
4. On missed field goals or final missed free throws, resolve a block where applicable and then an offensive or defensive rebound.
5. Update score, clock, player/team statistics, fatigue, lineups, and possession.

## Pregame construction

1. Load the historical dataset by default, or an explicitly selected predicted or blended dataset, as the baseline profile.
2. Combine it with the current `SeasonState`, then apply `GameContext` exclusions, starters, rotation size, minutes limits, rest, and travel.
3. Redistribute expected opportunity across available players while preserving 240 expected team minutes.
4. Sample one game-specific profile per player. Opportunity and role variables are sampled before efficiency variables; correlated team and player factors prevent independent, incoherent box-score draws.
5. Sample a shared game environment for pace, shooting, fouls, turnovers, and rebounding.
6. Recalculate active-roster and lineup matchup strength. Availability adjustments represent the change from the expected roster; possession-level defense continues to use the five players currently on the floor.

Every repeated matchup run performs this process independently with hierarchical deterministic seeds. The sampled profile remains fixed within that game while possession randomness resolves individual events.

For historical predictive evaluation, `..\Data_Collection\scripts\pregame_dataset.py` processes games chronologically and publishes validated records to the upstream publication root. It calculates season-to-date, venue-split, and last-5/10/20 team/player features before adding the current game to history. Expected active players come from prior appearances; expected starters prefer exact prior starter frequency when official box scores are cached and otherwise fall back to prior minutes. These are pregame estimates, never reconstructed from the current game's participants. Current-game box scores and starters are isolated under `actual` for scoring the forecast.

The transparent team-context layer uses rolling pace and the average of the offense's recent offensive rating and opponent's recent defensive rating. It applies bounded pace and efficiency adjustments and retains every input and multiplier in `simulation_audit`. This is deterministic historical feature calculation, not a fitted predictive model. Chronological calibration, validation, and holdout dates never overlap.

## Rules represented

- Team-foul bonus and final-two-minute thresholds.
- Correct free-throw possession resolution: rebounds only follow a missed final free throw.
- Made final free throws switch possession.
- Overtime occurs after a tied regulation score.
- Fatigue is affected by active stint length, timeouts, and period breaks.
- Period-opening possession follows NBA Rule 6: randomly resolve the opening jump ball for period 1; the team that gains first possession begins period 4, while the other team begins periods 2 and 3. Each overtime begins with a newly resolved jump ball. This scheduled regulation-period opening possession is independent of which team had the ball when the preceding period ended.
- Period-start and period-end log records explicitly identify their possession context. Shooting-foul records precede the resulting free-throw attempts.
- Normal substitutions are capped at five per stoppage. A player who exits must rest two game-clock minutes before returning, except that period breaks reset this requirement and the final five minutes of a half or overtime may use immediate tactical re-entry. Minutes-target priority is adjusted by a bounded in-game performance signal after a player has logged a meaningful sample of minutes.
- A disqualified active player is immediately replaced from the eligible bench before play resumes. Four or five team disqualifications emit a calibration warning; a sixth stops the simulation as a calibration error rather than allowing an implausible roster-wide foul-out.
- Intentional and and-one fouls are recorded explicitly, so every free-throw sequence has a preceding foul context in the play-by-play.
- Closing games prioritize the expected closing group; late blowouts shift minutes toward bench players. End-game pace, three-point preference, clock use, and intentional fouling respond to period, score margin, and time remaining.
- Two-for-one windows modestly increase faster actions near the end of periods. Clutch and intentional-foul logic applies only in the fourth quarter or overtime.

## Outputs

Each game returns team and player tables, play-by-play, NBA.com-style traditional/advanced/scoring/defense views, and calibration diagnostics.

It also returns `simulation_audit`. CSV exports preserve context/environment, sampled player profiles, team matchup inputs, and the seeds needed to reconstruct unusual outcomes.

## Interpretation

Single outcomes are stochastic. Evaluate the model primarily through aggregate behavior across many simulated games, using the calibration process defined in `CALIBRATION.md`.

Historical validation uses score, margin, total, and player-stat percentiles; winner probability; interval coverage; and aggregate calibration across many games. Exact reproduction of one historical result is not the objective.

Structural reconstruction and predictive backtesting are separate evaluation modes. Structural reconstruction may condition on completed-game availability and use completed-season averages, but every such result must be labeled as containing look-ahead inputs. Predictive backtesting requires a dated pregame profile snapshot and information known before tipoff; the calibration harness rejects ineligible records rather than silently reporting them as forecasts.

Global mechanics use versioned `calibration_defaults_v2` controls selected through ordered, calibration-only common-seed sweeps and confirmed on the separate validation split. The active changes center pace, reduce excess 3-point attempts, and raise offensive-rebound probability while retaining the v1 shot-accuracy, assist, and steal controls. A later version may replace these settings only when it improves its target metric without breaking structural invariants or previously healthy guardrails.

## Future counterfactual player-impact analysis

Player impact will be estimated through paired season simulations: run the same schedule and seeded simulation draws for a baseline roster and a counterfactual roster, then calculate within-run differences in wins, losses, point differential, and relevant player/team statistics. This paired design reduces Monte Carlo noise.

Excluding a player requires an explicit replacement and minutes-redistribution rule; otherwise the result mixes player value with an undefined roster construction choice. Adding a player universally must also identify whether the player is cloned onto each target roster or transferred away from the source roster.
