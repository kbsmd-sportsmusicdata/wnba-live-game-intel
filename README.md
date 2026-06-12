# WNBA Live Game Intelligence Pipeline

A modular Python pipeline that ingests live WNBA box score data and derives broadcast-ready analytics in real time — from raw inputs through shooting efficiency, possession estimates, and the Dean Oliver Four Factors framework.

## Pipeline Architecture

```
01_ingest/        Raw player + team box score fetch and validation
02_process/       Tiered derivation modules (Tiers 1–3 + beyond)
03_outputs/       CSV, JSON, and dashboard payload artifacts
config/           Game metadata, team colors, thresholds
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

## Output Files

All outputs land in `03_outputs/`:

- `raw_player.csv` — cleaned player box score rows
- `raw_team.csv` — cleaned team box score rows
- `tier1_shooting_player.csv` and `tier1_shooting_team.csv` — per-player and team shooting efficiency
- `tier2_possession_player.csv` and `tier2_possession_team.csv` — possession counts, pace, ORtg/DRtg
- `tier3_four_factors.csv` — Four Factors side-by-side with differentials
- `dashboard_payload.json` — all derived stats formatted for dashboard ingestion

## Configuration

Edit `config/game_config.yaml` to set the active `game_id`, team metadata, and display thresholds before running.

## Requirements

See `requirements.txt`. Python 3.9+ recommended.
