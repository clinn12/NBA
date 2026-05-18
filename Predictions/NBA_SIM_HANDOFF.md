# NBA Possession Simulator Handoff

Date: 2026-05-01

## Working Files

- Main working notebook: `C:\Users\clinn\Documents\Codex\2026-05-01\i-am-trying-to-build-the\Simulation_robust_copy.ipynb`
- Original source notebook was copied from: `C:\Users\clinn\Documents\NBA\Predictions\Simulation.ipynb`
- ESPN play-by-play snapshot used for event review: `C:\Users\clinn\Documents\Codex\2026-05-01\i-am-trying-to-build-the\espn_401869393_summary.json`

The original notebook was not edited. All current work is in `Simulation_robust_copy.ipynb`.

## Current Simulator Direction

The simulator is intended to be a robust NBA game simulator that runs possession by possession and produces completed-game outputs similar to NBA.com box score views.

The active core is near the top of `Simulation_robust_copy.ipynb`, before the older draft cells. Older code cells remain below for reference.

## Event Model Decisions

The event model was intentionally simplified after reviewing ESPN game `401869393`.

Kept event categories:

- `2PT Field Goal`
- `3PT Field Goal`
- `Free Throw`
- `Turnover`
- `Block`
- `Offensive Rebound`
- `Defensive Rebound`
- `Personal Foul`
- `Shooting Foul`
- `Substitution`
- `Full Timeout`
- `period_start`
- `period_end`

Excluded by design:

- Kicked ball
- 3-second turnover
- Defensive goaltending
- Delay of game
- Double technical foul
- Coach challenge
- Personal take foul
- Shot clock turnover
- Out-of-bounds turnover variants
- Ejection
- Offensive foul turnover as a distinct label
- Technical foul
- Jumpball
- Detailed shot subtypes

Turnovers are generic, but can credit a defender with a steal. Shots are generic 2PT or 3PT field goals, plus free throws.

## Implemented Mechanics

Possession simulation currently includes:

- Player usage-weighted shooter selection.
- 2PT / 3PT shot selection from play type, player tendency, spacing, rim pressure, and defense.
- Probabilistic assists on made field goals. Not every made field goal is assisted.
- Offensive and defensive rebounds after missed field goals.
- Blocks on missed field goals, credited to defenders.
- Turnovers, including live-ball steals credited to defenders.
- Shooting fouls and non-shooting personal fouls.
- Team foul bonus logic:
  - Standard bonus after configured team foul limit.
  - Final-two-minute bonus threshold.
- Free throw possession correctness:
  - And-1 rebound only if the one free throw is missed.
  - Two-shot trip rebound only if the second free throw is missed.
  - Three-shot trip rebound only if the third free throw is missed.
  - Made final free throw ends the possession and switches teams.
  - Missed final free throw can create offensive or defensive rebound.
- Substitutions based on fatigue, foul trouble, minutes target, and overuse.
- Timeouts that reduce active stint fatigue.
- Period breaks that reduce fatigue and reset team fouls.
- Overtime if regulation ends tied.

## Recently Added Realism Layers

Implemented from recommendation items #2, #3, #4, #6, #7, and #8:

- Defender assignment:
  - Primary defender selected for each shot.
  - Switch probability, especially for PNR/handoff.
  - Help defender probability, especially at the rim.
  - Matchup defensive stats are tracked for the NBA-style defense view.
- Lineup chemistry:
  - Spacing.
  - Rim pressure.
  - Lineup defense.
  - Per-player on-court chemistry exposure fields.
- Game-state strategy:
  - Play type weights adjust for clock, score margin, spacing, rim pressure, defense strength, and late-game state.
  - Trailing teams lean more into threes/transition.
  - Leading teams slow down and use safer actions.
- Foul context:
  - Team fouls per period.
  - Bonus free throws.
  - Foul trouble substitutions.
- Calibration loop:
  - Each game returns `game["calibration"]`.
  - Monte Carlo returns `avg_calibration_deltas`.
  - Current targets: pace, offensive rating, turnover percentage, free throw rate, offensive rebound percentage.
- Fatigue/rest:
  - Consecutive active seconds tracked by player.
  - Long stints degrade performance.
  - Substitutions reset stints.
  - Timeouts and period breaks restore fatigue.
  - Config includes `fatigue_back_to_back_load` for schedule fatigue simulation.

## Placeholder Inputs

Until real player averages are wired in, use:

```python
home = create_placeholder_team("Home Team", seed=1)
away = create_placeholder_team("Away Team", seed=2)
game = simulate_game_robust(home, away, SimConfig(seed=3))
```

Placeholder player inputs include:

- `mpg`
- `usage`
- `two_pct`
- `three_pct`
- `ft_pct`
- `three_rate`
- `ftr`
- `ast_rate`
- `tov_rate`
- `orb_rate`
- `drb_rate`
- `stl_rate`
- `blk_rate`
- `foul_rate`
- `defense`
- `stamina`
- `clutch`
- `rim_pressure`
- `off_ball_gravity`
- `switchability`
- `help_defense`

These inputs currently inform possession probabilities.

## Completed Game Outputs

Every completed game returns:

```python
game["team_table"]
game["player_table"]
game["play_by_play"]
game["box_score_views"]
game["calibration"]
```

NBA.com-style views:

```python
game["box_score_views"]["traditional"]
game["box_score_views"]["advanced"]
game["box_score_views"]["scoring"]
game["box_score_views"]["defense"]
```

Each view contains:

```python
{
    "players": [...],
    "teams": [...]
}
```

## Validation Performed

Recent validation included:

- Notebook robust core and demo cells execute.
- Placeholder teams simulate end to end.
- All four NBA-style box score views are generated.
- Excluded event labels do not leak back into play-by-play.
- Assists are possible but not automatic.
- Defensive rebounds are explicit after missed shots without offensive rebounds.
- Steals, blocks, bonus free throws, switches, and help defense occur in validation runs.
- Monte Carlo returns average calibration deltas.

## Good Next Steps

1. Import real player stats and map them to placeholder profile fields.
2. Add real lineup/rotation data and starting lineups.
3. Calibrate league averages over 500 to 5,000 simulations:
   - Pace
   - Offensive rating
   - FTr
   - TOV%
   - ORB%
   - 3PA rate
   - Assist rate
   - Block/steal rates
4. Add shot location granularity later if desired:
   - Rim
   - Paint non-rim
   - Midrange
   - Corner 3
   - Above-break 3
5. Add team-level coaching profiles:
   - Pace preference
   - Switch frequency
   - Help defense aggressiveness
   - Bench depth
   - Timeout behavior
6. Add schedule context:
   - Rest days
   - Back-to-back
   - Travel
   - Injury limitations
7. Split notebook core into a `.py` module once the model stabilizes.

## Important Caution

The current simulator is structurally richer than the first draft, but it is not yet calibrated to real NBA distributions. Treat single-game outputs as plausible simulations, not predictions. The calibration loop should be the next serious engineering step before trusting projected outcomes.
