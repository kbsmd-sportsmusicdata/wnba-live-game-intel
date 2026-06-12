"""
02_process/shooting_metrics.py
==============================
Tier 1: Shooting Efficiency Metrics

Inputs (reads from 03_outputs/):
    raw_player.csv
    raw_team.csv

Derived metrics (player + team level):
    fgm_2        2-point field goals made  (fgm - tpm)
    fga_2        2-point field goals attempted  (fga - tpa)
    fg2_pct      2P% = fgm_2 / fga_2
    fg3_pct      3P% = tpm / tpa
    ft_pct       FT% = ftm / fta
    efg_pct      eFG% = (fgm + 0.5 * tpm) / fga
    ts_pct       TS%  = (0.5 * pts) / (fga + 0.44 * fta)
    ftr          FT Rate = fta / fga
    three_rate   3-point attempt rate = tpa / fga
    two_rate     2-point attempt rate = fga_2 / fga

Outputs (written to 03_outputs/):
    tier1_shooting_player.csv
    tier1_shooting_team.csv

Usage:
    python 02_process/shooting_metrics.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "game_config.yaml"

console = Console()


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Safe division helper
# ---------------------------------------------------------------------------
def safe_div(numerator: pd.Series, denominator: pd.Series, decimals: int = 4) -> pd.Series:
    """Element-wise division; returns 0.0 where denominator is 0 or NaN."""
    return np.where(
        denominator.fillna(0) > 0,
        (numerator / denominator).round(decimals),
         0.0,
    ).astype(float)


# ---------------------------------------------------------------------------
# Core derivation functions
# ---------------------------------------------------------------------------
def compute_shooting_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add all Tier 1 shooting columns to a player or team DataFrame.
    Expects columns: pts, fgm, fga, tpm, tpa, ftm, fta.
    Returns a copy with new columns appended.
    """
    df = df.copy()

    # --- 2-point splits (inferred from totals and 3P counts) ---
    df["fgm_2"] = df["fgm"] - df["tpm"]
    df["fga_2"] = df["fga"] - df["tpa"]

    # --- Basic percentages ---
    df["fg_pct"]  = safe_div(df["fgm"], df["fga"])
    df["fg2_pct"] = safe_div(df["fgm_2"], df["fga_2"])
    df["fg3_pct"] = safe_div(df["tpm"], df["tpa"])
    df["ft_pct"]  = safe_div(df["ftm"], df["fta"])

    # --- Advanced shooting efficiency ---
    # eFG% = (FGM + 0.5 * 3PM) / FGA
    df["efg_pct"] = safe_div(df["fgm"] + 0.5 * df["tpm"], df["fga"])

    # TS% = (0.5 * PTS) / (FGA + 0.44 * FTA)
    ts_denom = df["fga"] + 0.44 * df["fta"]
    df["ts_pct"] = safe_div(0.5 * df["pts"], ts_denom)

    # --- Shot selection rates ---
    # FT Rate = FTA / FGA (how often player draws fouls relative to shot volume)
    df["ftr"] = safe_div(df["fta"], df["fga"])

    # 3-point attempt rate = 3PA / FGA
    df["three_rate"] = safe_div(df["tpa"], df["fga"])

    # 2-point attempt rate = (FGA - 3PA) / FGA
    df["two_rate"] = safe_div(df["fga_2"], df["fga"])

    return df


# ---------------------------------------------------------------------------
# Threshold flag columns (for dashboard color coding)
# ---------------------------------------------------------------------------
def apply_threshold_flags(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    """
    Add boolean flag columns used by the dashboard to color-code efficiency.
    flag_ts_good     True if TS% >= threshold
    flag_efg_good    True if eFG% >= threshold
    flag_ftr_good    True if FTR >= threshold
    """
    df = df.copy()
    df["flag_ts_good"]  = df["ts_pct"]   >= thresholds.get("ts_pct_good",  0.560)
    df["flag_efg_good"] = df["efg_pct"]  >= thresholds.get("efg_pct_good", 0.520)
    df["flag_ftr_good"] = df["ftr"]      >= thresholds.get("ftr_good",     0.300)
    return df


# ---------------------------------------------------------------------------
# Rich console preview
# ---------------------------------------------------------------------------
def print_shooting_preview(df_players: pd.DataFrame, df_teams: pd.DataFrame) -> None:
    console.rule("[bold]Tier 1 — Team Shooting Efficiency[/bold]")
    t = Table(show_header=True, header_style="bold magenta")
    team_cols = ["team_abbr", "pts", "fg_pct", "efg_pct", "ts_pct",
                 "fg2_pct", "fg3_pct", "ft_pct", "ftr", "three_rate"]
    for c in team_cols:
        if c in df_teams.columns:
            t.add_column(c)
    for _, row in df_teams.iterrows():
        t.add_row(*[str(row.get(c, "")) for c in team_cols if c in df_teams.columns])
    console.print(t)

    console.rule("[bold]Tier 1 — Player Shooting (active, sorted by TS%)[/bold]")
    p = Table(show_header=True, header_style="bold cyan")
    player_cols = ["player_name", "team_abbr", "minutes", "pts",
                   "fgm", "fga", "efg_pct", "ts_pct", "ftr",
                   "three_rate", "flag_ts_good"]
    for c in player_cols:
        if c in df_players.columns:
            p.add_column(c)
    active = df_players[df_players["did_not_play"] == False].sort_values(
        "ts_pct", ascending=False
    ) if "did_not_play" in df_players.columns else df_players.sort_values("ts_pct", ascending=False)
    for _, row in active.head(12).iterrows():
        p.add_row(*[str(row.get(c, "")) for c in player_cols if c in df_players.columns])
    console.print(p)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    config = load_config()
    output_dir = REPO_ROOT / config.get("output_dir", "03_outputs")
    thresholds = config.get("thresholds", {})

    # Load raw inputs
    player_path = output_dir / "raw_player.csv"
    team_path   = output_dir / "raw_team.csv"

    if not player_path.exists() or not team_path.exists():
        console.print("[bold red]Raw CSVs not found. Run 01_ingest/box_ingest.py first.[/bold red]")
        raise FileNotFoundError("Missing raw_player.csv or raw_team.csv in 03_outputs/")

    df_players = pd.read_csv(player_path)
    df_teams   = pd.read_csv(team_path)

    console.print(f"[green]Loaded raw_player.csv ({len(df_players)} rows)[/green]")
    console.print(f"[green]Loaded raw_team.csv ({len(df_teams)} rows)[/green]")

    # Compute
    df_players = compute_shooting_metrics(df_players)
    df_teams   = compute_shooting_metrics(df_teams)

    # Apply flags
    df_players = apply_threshold_flags(df_players, thresholds)
    df_teams   = apply_threshold_flags(df_teams, thresholds)

    # Write outputs
    out_player = output_dir / "tier1_shooting_player.csv"
    out_team   = output_dir / "tier1_shooting_team.csv"
    df_players.to_csv(out_player, index=False)
    df_teams.to_csv(out_team, index=False)
    console.print(f"[cyan]Wrote {out_player}[/cyan]")
    console.print(f"[cyan]Wrote {out_team}[/cyan]")

    print_shooting_preview(df_players, df_teams)

    return df_players, df_teams


if __name__ == "__main__":
    run()
