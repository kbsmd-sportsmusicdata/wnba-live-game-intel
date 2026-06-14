# WNBA Live Game Intelligence Pipeline

A modular Python pipeline that ingests live WNBA box score data and derives broadcast-ready analytics in real time — from raw inputs through shooting efficiency, possession estimates, and the Dean Oliver Four Factors framework.

## Pipeline Architecture

```
01_ingest/        Raw player + team box score fetch and validation
02_process/       Tiered derivation modules (Tiers 1–3 + beyond)
03_outputs/       CSV, JSON, and dashboard payload artifacts
04_refresh/       Season-wide refresh scripts for SportsDataverse + PBPStats
config/           Game metadata, team colors, thresholds
tests/            Relocated unit tests for refresh workflows
```

## Tiers

| Tier | Module | What It Computes |
|------|--------|------------------|
| Layer 0 | `box_ingest.py` | Raw box score fetch, schema validation, normalization |
| Tier 1 | `shooting_metrics.py` | eFG%, TS%, FTR, 2P/3P splits |
| Tier 2 | `possession_engine.py` | Possession estimates, ORtg, DRtg, Net Rating, Pace |
| Tier 3 | `four_factors.py` | Dean Oliver Four Factors (team + opponent differentials) |

## Data Sources

Live box scores are fetched from the **ESPN hidden API** (`site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary`) using a `game_id`. This is the only reliable free source of in-progress WNBA box score data.

## Quickstart

```bash
pip install -r requirements.txt

# Set your game_id in config/game_config.yaml
python 01_ingest/box_ingest.py
python 02_process/shooting_metrics.py
python 02_process/possession_engine.py
python 02_process/four_factors.py
```

## GitHub Actions

The repo includes a manual workflow at
[`.github/workflows/wnba-live-game-pipeline.yml`](.github/workflows/wnba-live-game-pipeline.yml)
for one-shot live game runs in GitHub Actions. It accepts an ESPN `game_id`,
updates [`config/game_config.yaml`](config/game_config.yaml) at runtime inside
the workflow, runs ingest, optionally runs the downstream tiers, commits the
selected generated datasets back into `03_outputs/` on the branch that ran the
workflow, and uploads the captured stage logs as artifacts from
`03_outputs/logs/`.

## Dashboard Demo

The Phase 1 MVP dashboard is served from GitHub Pages and reads from:

- `docs/dashboard_data/dashboard_payload.json`
- `docs/dashboard_data/game_summary.json`

The dashboard is intentionally source-agnostic. It does not read directly from
ESPN or Google Sheets. Any future input source only needs to produce the
standard raw outputs defined in `docs/raw_data_contract.md`.

For the first completed-game smoke test, use `game_id` `401856915` as the
fixed 2026 validation fixture for both local ingest checks and the first manual
workflow dispatch.

<!-- GAME_ID_REFERENCE_START -->
## Game ID Reference

This section is generated from `schedule_2026.parquet` when that file is available locally.

- Expected schedule path: `/Users/krystalbeasley/projects/wnba-live-game-intel/data/raw/sportsdataverse/wnba_2026/schedule_2026.parquet`
- Refresh source: `04_refresh/fetch_wnba_sportsdataverse_2026.py`
- When the schedule parquet is present, regenerate this section to list completed and future games that already have assigned `game_id` values.
<!-- GAME_ID_REFERENCE_END -->

## Season Refresh Workflow

Use `04_refresh/` for offline season-wide data refreshes that should stay separate
from the live single-game pipeline.

```bash
python 04_refresh/fetch_wnba_sportsdataverse_2026.py
python 04_refresh/pbpstats_2026_pull_clean.py
python 04_refresh/pbpstats_2026_features.py
```

These scripts keep their own env-configured data roots under `data/` and do not
write into `03_outputs/`, which remains reserved for live-game artifacts.

## Current Derived Outputs

After Tier 3, the pipeline now adds:

- `player_impact.csv` from `02_process/player_impact.py`
- `game_context.json` from `02_process/game_context.py`
- `player_derived.csv` and `team_derived.csv` from `02_process/derive_outputs.py`

The dashboard payload is built from these derived outputs instead of duplicating
calculation logic in the front end.

## Output Files

All outputs land in `03_outputs/`:

- `raw_player.csv` — cleaned player box score rows
- `raw_team.csv` — cleaned team box score rows
- `tier1_shooting_player.csv` and `tier1_shooting_team.csv` — per-player and team shooting efficiency
- `tier2_possession_player.csv` and `tier2_possession_team.csv` — possession counts, pace, ORtg/DRtg
- `tier3_four_factors.csv` — Four Factors side-by-side with differentials
- `player_impact.csv` — player-level usage, Game Score, AST%, and REB%
- `game_context.json` — game state, WPBA scoring context, and broadcast notes
- `player_derived.csv` and `team_derived.csv` — preferred downstream derived tables
- `dashboard_payload.json` — all derived stats formatted for dashboard ingestion
- `game_summary.json` — compact summary for the GitHub Pages command center

Manual GitHub Actions runs persist the selected output datasets above back into
the branch’s `03_outputs/` folder. Stage logs are written under
`03_outputs/logs/` during the run and remain artifact-only so repo history does
not fill up with run-by-run log files.

## Raw Data Contract

All input adapters must produce:

- `03_outputs/raw_player.csv`
- `03_outputs/raw_team.csv`

See `docs/raw_data_contract.md`.

## Configuration

Edit `config/game_config.yaml` to set the active `game_id`, team metadata, and display thresholds before running.

## Requirements

See `requirements.txt`. Python 3.9+ recommended.
