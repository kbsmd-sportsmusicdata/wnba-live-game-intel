# Raw Data Contract

All current and future live-game input adapters must normalize into the same
two raw pipeline outputs before any Tier 1 calculations run:

- `03_outputs/raw_player.csv`
- `03_outputs/raw_team.csv`

This keeps the downstream analytics and GitHub Pages dashboard source-agnostic.
The dashboard should never read ESPN, Google Sheets, raw spreadsheet tabs, or
database tables directly. It reads generated JSON payloads only.

## Required `raw_player.csv` Columns

```text
game_id
fetched_at
game_date
game_status
period
clock
team_id
team_abbr
home_away
player_id
player_name
position
starter
active
did_not_play
minutes
pts
fgm
fga
tpm
tpa
ftm
fta
oreb
dreb
reb
ast
stl
blk
tov
pf
plus_minus
```

## Required `raw_team.csv` Columns

```text
game_id
fetched_at
game_date
game_status
period
clock
team_id
team_name
team_abbr
home_away
pts
fgm
fga
fg_pct
tpm
tpa
tp_pct
ftm
fta
ft_pct
oreb
dreb
reb
ast
stl
blk
tov
pf
pts_in_paint
fast_break_pts
second_chance_pts
pts_off_tov
bench_pts
largest_lead
```

## Contract Notes

- `tpm` and `tpa` mean three-point makes and attempts.
- `starter`, `active`, and `did_not_play` should be boolean-like fields.
- `minutes` should be stored as decimal minutes.
- `period` should be numeric.
- `clock` should stay display-friendly for downstream UI use.
- Future spreadsheet, CSV, or database adapters must normalize into this raw
  contract before Tier 1.
- Spreadsheet-computed fields should not be treated as the source of truth.
- Python remains the advanced-metrics layer for the live pipeline.
- The GitHub Pages dashboard reads generated JSON only, not raw external
  sources.
