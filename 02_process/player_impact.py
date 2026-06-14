"""
02_process/player_impact.py
===========================
Focused player impact metrics built from Tier 2 player and team outputs.

Inputs (reads from 03_outputs/):
    tier2_possession_player.csv
    tier2_possession_team.csv

Outputs:
    player_impact.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from rich.console import Console
from rich.table import Table


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "game_config.yaml"

console = Console()


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f) or {}


def safe_div(num, denom, decimals: int = 4):
    if isinstance(num, pd.Series):
        denom_series = pd.to_numeric(denom, errors="coerce").fillna(0)
        num_series = pd.to_numeric(num, errors="coerce").fillna(0)
        return np.where(
            denom_series > 0,
            (num_series / denom_series).round(decimals),
            0.0,
        ).astype(float)
    denom_value = float(denom) if denom else 0.0
    if denom_value == 0:
        return 0.0
    return round(float(num) / denom_value, decimals)


def compute_game_score(df: pd.DataFrame) -> pd.Series:
    pts = pd.to_numeric(df["pts"], errors="coerce").fillna(0)
    fgm = pd.to_numeric(df["fgm"], errors="coerce").fillna(0)
    fga = pd.to_numeric(df["fga"], errors="coerce").fillna(0)
    ftm = pd.to_numeric(df["ftm"], errors="coerce").fillna(0)
    fta = pd.to_numeric(df["fta"], errors="coerce").fillna(0)
    oreb = pd.to_numeric(df["oreb"], errors="coerce").fillna(0)
    dreb = pd.to_numeric(df["dreb"], errors="coerce").fillna(0)
    ast = pd.to_numeric(df["ast"], errors="coerce").fillna(0)
    stl = pd.to_numeric(df["stl"], errors="coerce").fillna(0)
    blk = pd.to_numeric(df["blk"], errors="coerce").fillna(0)
    pf = pd.to_numeric(df["pf"], errors="coerce").fillna(0)
    tov = pd.to_numeric(df["tov"], errors="coerce").fillna(0)
    game_score = (
        pts
        + 0.4 * fgm
        - 0.7 * fga
        - 0.4 * (fta - ftm)
        + 0.7 * oreb
        + 0.3 * dreb
        + stl
        + 0.7 * ast
        + 0.7 * blk
        - 0.4 * pf
        - tov
    )
    return game_score.round(2)


def compute_player_impact(df_players: pd.DataFrame, df_teams: pd.DataFrame) -> pd.DataFrame:
    df = df_players.copy()

    team_ref = df_teams[["team_abbr", "fgm", "minutes_elapsed"]].copy()
    team_ref = team_ref.rename(columns={
        "fgm": "team_fgm",
        "minutes_elapsed": "team_minutes_elapsed_ref",
    })
    total_game_rebounds = pd.to_numeric(df_teams["reb"], errors="coerce").fillna(0).sum()

    df = df.merge(team_ref, on="team_abbr", how="left")

    minutes = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
    if "team_minutes_elapsed" in df.columns:
        team_minutes = pd.to_numeric(df["team_minutes_elapsed"], errors="coerce").fillna(0)
    else:
        team_minutes = pd.to_numeric(
            df.get("team_minutes_elapsed_ref", pd.Series([0] * len(df), index=df.index)),
            errors="coerce",
        ).fillna(0)
    team_fgm = pd.to_numeric(df["team_fgm"], errors="coerce").fillna(0)
    player_fgm = pd.to_numeric(df["fgm"], errors="coerce").fillna(0)
    player_ast = pd.to_numeric(df["ast"], errors="coerce").fillna(0)
    player_reb = pd.to_numeric(df["reb"], errors="coerce").fillna(0)

    ast_denom = ((minutes / team_minutes.replace(0, np.nan)) * team_fgm) - player_fgm
    reb_denom = (minutes / team_minutes.replace(0, np.nan)) * total_game_rebounds

    if "usg_pct" in df.columns:
        usg_pct = pd.to_numeric(df["usg_pct"], errors="coerce").fillna(0).round(4)
    else:
        team_poss = pd.to_numeric(df["team_poss"], errors="coerce").fillna(0)
        fga = pd.to_numeric(df["fga"], errors="coerce").fillna(0)
        fta = pd.to_numeric(df["fta"], errors="coerce").fillna(0)
        tov = pd.to_numeric(df["tov"], errors="coerce").fillna(0)
        min_share = safe_div(minutes, team_minutes.replace(0, 1))
        usg_pct = safe_div(fga + (0.44 * fta) + tov, team_poss * min_share).clip(0, 1.0)

    df["usg_pct"] = usg_pct
    df["game_score"] = compute_game_score(df)
    df["ast_pct"] = safe_div(player_ast, ast_denom).clip(0, 1.0)
    df["reb_pct"] = safe_div(player_reb, reb_denom).clip(0, 1.0)

    keep_cols = [
        "game_id", "team_abbr", "player_id", "player_name",
        "usg_pct", "game_score", "ast_pct", "reb_pct",
    ]
    return df[keep_cols].copy()


def print_player_impact_preview(df: pd.DataFrame) -> None:
    console.rule("[bold]Player Impact[/bold]")
    table = Table(show_header=True, header_style="bold magenta")
    cols = ["player_name", "team_abbr", "usg_pct", "game_score", "ast_pct", "reb_pct"]
    for col in cols:
        table.add_column(col)
    active = df.sort_values("game_score", ascending=False).head(10)
    for _, row in active.iterrows():
        table.add_row(*[str(row.get(c, "")) for c in cols])
    console.print(table)


def run() -> pd.DataFrame:
    config = load_config()
    output_dir = REPO_ROOT / config.get("output_dir", "03_outputs")
    player_path = output_dir / "tier2_possession_player.csv"
    team_path = output_dir / "tier2_possession_team.csv"

    if not player_path.exists() or not team_path.exists():
        console.print("[bold red]Tier 2 CSVs not found. Run 02_process/possession_engine.py first.[/bold red]")
        raise FileNotFoundError("Missing tier2_possession_*.csv in 03_outputs/")

    df_players = pd.read_csv(player_path)
    df_teams = pd.read_csv(team_path)
    console.print(f"[green]Loaded tier2_possession_player.csv ({len(df_players)} rows)[/green]")
    console.print(f"[green]Loaded tier2_possession_team.csv ({len(df_teams)} rows)[/green]")

    df_player_impact = compute_player_impact(df_players, df_teams)
    out_path = output_dir / "player_impact.csv"
    df_player_impact.to_csv(out_path, index=False)
    console.print(f"[cyan]Wrote {out_path}[/cyan]")
    print_player_impact_preview(df_player_impact)
    return df_player_impact


if __name__ == "__main__":
    run()
