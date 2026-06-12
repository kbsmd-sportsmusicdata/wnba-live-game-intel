"""
01_ingest/box_ingest.py
=======================
Fetches live WNBA box score data from the ESPN hidden summary API.

Data source:
    ESPN Summary API:
    https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event={game_id}

Outputs (written to 03_outputs/):
    raw_player.csv  — one row per player per team, all available box score fields
    raw_team.csv    — one row per team, aggregate box score totals

Usage:
    python 01_ingest/box_ingest.py
    python 01_ingest/box_ingest.py --game_id 401663644
    python 01_ingest/box_ingest.py --live   # polls on interval from config
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yaml
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "game_config.yaml"

console = Console()


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def load_config(config_path: Path = CONFIG_PATH) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# ESPN API fetch
# ---------------------------------------------------------------------------
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Raw field names returned by ESPN for player stats
# Order matches ESPN's boxscore athlete stats array
ESPN_PLAYER_STAT_KEYS = [
    "minutes",
    "field_goals",       # "3-5" string — parsed to FGM/FGA
    "three_pointers",    # "1-2" string
    "free_throws",       # "2-2" string
    "oreb",
    "dreb",
    "reb",
    "ast",
    "stl",
    "blk",
    "tov",
    "pf",
    "plus_minus",
    "pts",
]


def fetch_espn_summary(game_id: str) -> dict:
    """Hit ESPN summary endpoint and return parsed JSON."""
    params = {"event": game_id}
    try:
        resp = requests.get(ESPN_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        console.print(f"[bold red]HTTP error fetching game {game_id}: {e}[/bold red]")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        console.print("[bold red]Connection error — check network.[/bold red]")
        sys.exit(1)
    except requests.exceptions.Timeout:
        console.print("[bold red]Request timed out after 10s.[/bold red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def _parse_made_att(s: str) -> tuple[int, int]:
    """Parse ESPN '3-5' style string to (made, attempted)."""
    if not s or s in ("-", ""):
        return 0, 0
    parts = s.split("-")
    if len(parts) != 2:
        return 0, 0
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return 0, 0


def _safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _safe_float(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _safe_minutes(val) -> float:
    """Convert '32:15' or '32' to float minutes."""
    if not val or val in ("-", ""):
        return 0.0
    val = str(val)
    if ":" in val:
        parts = val.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except (ValueError, IndexError):
            return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# ESPN JSON → DataFrames
# ---------------------------------------------------------------------------
def parse_boxscore(data: dict, game_id: str, fetched_at: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parse ESPN summary JSON into player and team DataFrames.

    Returns:
        (df_players, df_teams)
    """
    player_rows = []
    team_rows = []

    boxscore = data.get("boxscore", {})
    teams_data = boxscore.get("teams", [])
    players_data = boxscore.get("players", [])

    # ---- Game-level metadata ----
    competitions = data.get("header", {}).get("competitions", [])
    game_info = competitions[0] if competitions else {}
    status_type = game_info.get("status", {}).get("type", {}).get("name", "unknown")
    period = game_info.get("status", {}).get("period", 0)
    display_clock = game_info.get("status", {}).get("displayClock", "")
    game_date = game_info.get("date", "")

    # Map ESPN team id → home/away
    team_homeaway = {}
    for comp_team in game_info.get("competitors", []):
        espn_id = comp_team.get("id", "")
        team_homeaway[espn_id] = comp_team.get("homeAway", "unknown")

    # ---- Team totals ----
    for t in teams_data:
        team_info = t.get("team", {})
        team_id = team_info.get("id", "")
        stats_list = t.get("statistics", [])

        # ESPN returns stats as [{name: ..., displayValue: ...}, ...]
        stats_map = {s["name"]: s.get("displayValue", "") for s in stats_list}

        fg_made, fg_att = _parse_made_att(stats_map.get("fieldGoalsMade-fieldGoalsAttempted", ""))
        tp_made, tp_att = _parse_made_att(stats_map.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted", ""))
        ft_made, ft_att = _parse_made_att(stats_map.get("freeThrowsMade-freeThrowsAttempted", ""))

        team_rows.append({
            "game_id": game_id,
            "fetched_at": fetched_at,
            "game_date": game_date,
            "game_status": status_type,
            "period": _safe_int(period),
            "clock": display_clock,
            "team_id": team_id,
            "team_name": team_info.get("displayName", ""),
            "team_abbr": team_info.get("abbreviation", ""),
            "home_away": team_homeaway.get(team_id, "unknown"),
            "pts": _safe_int(stats_map.get("points", 0)),
            "fgm": fg_made,
            "fga": fg_att,
            "fg_pct": _safe_float(stats_map.get("fieldGoalPct", 0)),
            "tpm": tp_made,
            "tpa": tp_att,
            "tp_pct": _safe_float(stats_map.get("threePointFieldGoalPct", 0)),
            "ftm": ft_made,
            "fta": ft_att,
            "ft_pct": _safe_float(stats_map.get("freeThrowPct", 0)),
            "oreb": _safe_int(stats_map.get("offensiveRebounds", 0)),
            "dreb": _safe_int(stats_map.get("defensiveRebounds", 0)),
            "reb": _safe_int(stats_map.get("rebounds", 0)),
            "ast": _safe_int(stats_map.get("assists", 0)),
            "stl": _safe_int(stats_map.get("steals", 0)),
            "blk": _safe_int(stats_map.get("blocks", 0)),
            "tov": _safe_int(stats_map.get("turnovers", 0)),
            "pf": _safe_int(stats_map.get("fouls", 0)),
            "pts_in_paint": _safe_int(stats_map.get("pointsInPaint", 0)),
            "fast_break_pts": _safe_int(stats_map.get("fastBreakPoints", 0)),
            "second_chance_pts": _safe_int(stats_map.get("secondChancePoints", 0)),
            "pts_off_tov": _safe_int(stats_map.get("pointsOffTurnovers", 0)),
            "bench_pts": _safe_int(stats_map.get("benchPoints", 0)),
            "largest_lead": _safe_int(stats_map.get("largestLead", 0)),
        })

    # ---- Player rows ----
    for team_entry in players_data:
        team_info = team_entry.get("team", {})
        team_id = team_info.get("id", "")
        team_abbr = team_info.get("abbreviation", "")
        home_away = team_homeaway.get(team_id, "unknown")

        for athlete_entry in team_entry.get("statistics", []):
            # Each entry has a list of athletes with their stat arrays
            stat_names = [
                s.get("name", "") if isinstance(s, dict) else str(s)
                for s in athlete_entry.get("keys", [])
            ]

            for athlete in athlete_entry.get("athletes", []):
                athlete_info = athlete.get("athlete", {})
                stats_values = athlete.get("stats", [])

                # Map stat name → value
                stat_map = dict(zip(stat_names, stats_values))

                did_not_play = athlete.get("didNotPlay", False)
                active = athlete.get("active", True)

                minutes_raw = stat_map.get("minutes", stat_map.get("MIN", "0"))
                minutes = _safe_minutes(minutes_raw)

                fg_made, fg_att = _parse_made_att(
                    stat_map.get("fieldGoalsMade-fieldGoalsAttempted",
                    stat_map.get("FG", ""))
                )
                tp_made, tp_att = _parse_made_att(
                    stat_map.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted",
                    stat_map.get("3PT", ""))
                )
                ft_made, ft_att = _parse_made_att(
                    stat_map.get("freeThrowsMade-freeThrowsAttempted",
                    stat_map.get("FT", ""))
                )

                player_rows.append({
                    "game_id": game_id,
                    "fetched_at": fetched_at,
                    "game_date": game_date,
                    "game_status": status_type,
                    "period": _safe_int(period),
                    "clock": display_clock,
                    "team_id": team_id,
                    "team_abbr": team_abbr,
                    "home_away": home_away,
                    "player_id": athlete_info.get("id", ""),
                    "player_name": athlete_info.get("displayName", ""),
                    "position": athlete_info.get("position", {}).get("abbreviation", ""),
                    "starter": athlete.get("starter", False),
                    "active": active,
                    "did_not_play": did_not_play,
                    "minutes": round(minutes, 2),
                    "pts": _safe_int(stat_map.get("points", stat_map.get("PTS", 0))),
                    "fgm": fg_made,
                    "fga": fg_att,
                    "tpm": tp_made,
                    "tpa": tp_att,
                    "ftm": ft_made,
                    "fta": ft_att,
                    "oreb": _safe_int(stat_map.get("offensiveRebounds", stat_map.get("OREB", 0))),
                    "dreb": _safe_int(stat_map.get("defensiveRebounds", stat_map.get("DREB", 0))),
                    "reb": _safe_int(stat_map.get("rebounds", stat_map.get("REB", 0))),
                    "ast": _safe_int(stat_map.get("assists", stat_map.get("AST", 0))),
                    "stl": _safe_int(stat_map.get("steals", stat_map.get("STL", 0))),
                    "blk": _safe_int(stat_map.get("blocks", stat_map.get("BLK", 0))),
                    "tov": _safe_int(stat_map.get("turnovers", stat_map.get("TO", 0))),
                    "pf": _safe_int(stat_map.get("fouls", stat_map.get("PF", 0))),
                    "plus_minus": _safe_int(stat_map.get("plusMinus", stat_map.get("+/-", 0))),
                })

    df_players = pd.DataFrame(player_rows)
    df_teams = pd.DataFrame(team_rows)

    return df_players, df_teams


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
REQUIRED_PLAYER_COLS = [
    "game_id", "player_id", "player_name", "team_abbr",
    "minutes", "pts", "fgm", "fga", "tpm", "tpa",
    "ftm", "fta", "oreb", "dreb", "reb",
    "ast", "stl", "blk", "tov", "pf", "plus_minus",
]

REQUIRED_TEAM_COLS = [
    "game_id", "team_id", "team_abbr", "home_away",
    "pts", "fgm", "fga", "tpm", "tpa",
    "ftm", "fta", "oreb", "dreb", "reb",
    "ast", "stl", "blk", "tov", "pf",
]


def validate_schema(df: pd.DataFrame, required_cols: list[str], label: str) -> bool:
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        console.print(f"[bold red]Schema error in {label}: missing columns {missing}[/bold red]")
        return False
    console.print(f"[green]✓ {label} schema OK — {len(df)} rows, {len(df.columns)} cols[/green]")
    return True


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def write_outputs(df_players: pd.DataFrame, df_teams: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    player_path = output_dir / "raw_player.csv"
    team_path = output_dir / "raw_team.csv"
    df_players.to_csv(player_path, index=False)
    df_teams.to_csv(team_path, index=False)
    console.print(f"[cyan]Wrote {player_path}[/cyan]")
    console.print(f"[cyan]Wrote {team_path}[/cyan]")


def print_preview(df_players: pd.DataFrame, df_teams: pd.DataFrame) -> None:
    """Print a Rich summary table to console for quick QA."""
    console.rule("[bold]Team Box Score[/bold]")
    t = Table(show_header=True, header_style="bold magenta")
    preview_cols = ["team_abbr", "home_away", "pts", "fgm", "fga",
                    "tpm", "tpa", "ftm", "fta", "reb", "ast", "tov"]
    for col in preview_cols:
        if col in df_teams.columns:
            t.add_column(col)
    for _, row in df_teams.iterrows():
        t.add_row(*[str(row.get(c, "")) for c in preview_cols if c in df_teams.columns])
    console.print(t)

    console.rule("[bold]Player Box Score (starters)[/bold]")
    p = Table(show_header=True, header_style="bold cyan")
    player_preview_cols = ["player_name", "team_abbr", "minutes", "pts",
                            "fgm", "fga", "tpm", "tpa", "reb", "ast", "tov", "plus_minus"]
    for col in player_preview_cols:
        if col in df_players.columns:
            p.add_column(col)
    starters = df_players[df_players.get("starter", pd.Series(dtype=bool)) == True] if "starter" in df_players.columns else df_players.head(10)
    for _, row in starters.iterrows():
        p.add_row(*[str(row.get(c, "")) for c in player_preview_cols if c in df_players.columns])
    console.print(p)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def run(game_id: str | None = None, live_mode: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    config = load_config()
    _game_id = game_id or str(config["game"]["game_id"])
    output_dir = REPO_ROOT / config.get("output_dir", "03_outputs")
    interval = config.get("polling_interval_seconds", 45)

    def _fetch_and_parse() -> tuple[pd.DataFrame, pd.DataFrame]:
        fetched_at = datetime.now(timezone.utc).isoformat()
        console.print(f"[bold]Fetching game_id={_game_id} at {fetched_at}[/bold]")
        data = fetch_espn_summary(_game_id)
        df_players, df_teams = parse_boxscore(data, _game_id, fetched_at)
        validate_schema(df_players, REQUIRED_PLAYER_COLS, "raw_player")
        validate_schema(df_teams, REQUIRED_TEAM_COLS, "raw_team")
        write_outputs(df_players, df_teams, output_dir)
        print_preview(df_players, df_teams)
        return df_players, df_teams

    if live_mode:
        console.print(f"[bold yellow]Live mode: polling every {interval}s. Ctrl+C to stop.[/bold yellow]")
        while True:
            try:
                _fetch_and_parse()
                time.sleep(interval)
            except KeyboardInterrupt:
                console.print("[yellow]Polling stopped.[/yellow]")
                break
        return pd.DataFrame(), pd.DataFrame()
    else:
        return _fetch_and_parse()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch WNBA live box score from ESPN API")
    parser.add_argument("--game_id", type=str, default=None, help="ESPN game_id to fetch")
    parser.add_argument("--live", action="store_true", help="Poll continuously on interval from config")
    args = parser.parse_args()
    run(game_id=args.game_id, live_mode=args.live)
