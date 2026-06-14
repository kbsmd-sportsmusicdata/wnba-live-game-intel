from __future__ import annotations

import pandas as pd


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


def validate_schema(df: pd.DataFrame, required_cols: list[str], label: str, console=None) -> bool:
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        if console is not None:
            console.print(f"[bold red]Schema error in {label}: missing columns {missing}[/bold red]")
        return False
    if console is not None:
        console.print(f"[green]✓ {label} schema OK — {len(df)} rows, {len(df.columns)} cols[/green]")
    return True
