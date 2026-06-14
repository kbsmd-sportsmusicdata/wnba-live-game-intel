"""
02_process/derive_outputs.py
============================
Consolidates the tiered live-game outputs into final player and team derived tables.

Outputs:
    player_derived.csv
    team_derived.csv
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml
from rich.console import Console


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "game_config.yaml"

console = Console()


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f) or {}


def merge_player_derived(df_tier2_player: pd.DataFrame, df_player_impact: pd.DataFrame) -> pd.DataFrame:
    base = df_tier2_player.copy()
    impact = df_player_impact.copy()
    impact_cols = ["game_id", "player_id", "usg_pct", "game_score", "ast_pct", "reb_pct"]
    impact = impact[impact_cols]
    base = base.drop(columns=["usg_pct"], errors="ignore")
    merged = base.merge(impact, on=["game_id", "player_id"], how="left", validate="one_to_one")
    return merged


def merge_team_derived(df_tier3_team: pd.DataFrame, game_context: dict) -> pd.DataFrame:
    base = df_tier3_team.copy()
    team_abbr = base["team_abbr"].astype(str)
    home_abbr = str(game_context.get("home_team_abbr", ""))
    away_abbr = str(game_context.get("away_team_abbr", ""))
    winner_abbr = str(game_context.get("winner_team_abbr", ""))

    base["game_status"] = game_context.get("game_status")
    base["is_final"] = game_context.get("is_final")
    base["final_margin"] = game_context.get("final_margin")
    base["is_clutch_window"] = game_context.get("is_clutch_window")
    base["is_close_final"] = game_context.get("is_close_final")
    base["winner_team_abbr"] = winner_abbr
    base["is_winner"] = team_abbr == winner_abbr
    base["is_home_team"] = team_abbr == home_abbr
    base["is_away_team"] = team_abbr == away_abbr

    wpba = game_context.get("wpba", {})
    if wpba:
        is_home_mask = base["is_home_team"]
        base["wpba_total_points"] = 0.0
        base.loc[is_home_mask, "wpba_total_points"] = wpba.get("home_total_points")
        base.loc[~is_home_mask, "wpba_total_points"] = wpba.get("away_total_points")

        base["wpba_game_win_points"] = 0.0
        base.loc[is_home_mask, "wpba_game_win_points"] = wpba.get("home_game_win_points")
        base.loc[~is_home_mask, "wpba_game_win_points"] = wpba.get("away_game_win_points")

        base["wpba_quarter_points"] = 0.0
        base.loc[is_home_mask, "wpba_quarter_points"] = wpba.get("home_quarter_points")
        base.loc[~is_home_mask, "wpba_quarter_points"] = wpba.get("away_quarter_points")

        base["wpba_quarters_won"] = 0
        base.loc[is_home_mask, "wpba_quarters_won"] = wpba.get("home_quarters_won")
        base.loc[~is_home_mask, "wpba_quarters_won"] = wpba.get("away_quarters_won")

        base["wpba_tied_quarters"] = wpba.get("tied_quarters")
        base["wpba_points_leader_team_abbr"] = wpba.get("points_leader_team_abbr")
        base["wpba_scoreline_text"] = wpba.get("scoreline_text")
    return base


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    config = load_config()
    output_dir = REPO_ROOT / config.get("output_dir", "03_outputs")

    tier2_player_path = output_dir / "tier2_possession_player.csv"
    tier3_team_path = output_dir / "tier3_four_factors.csv"
    player_impact_path = output_dir / "player_impact.csv"
    game_context_path = output_dir / "game_context.json"

    required = [tier2_player_path, tier3_team_path, player_impact_path, game_context_path]
    missing = [str(path.name) for path in required if not path.exists()]
    if missing:
        console.print(f"[bold red]Missing required derived inputs: {missing}[/bold red]")
        raise FileNotFoundError(", ".join(missing))

    df_tier2_player = pd.read_csv(tier2_player_path)
    df_tier3_team = pd.read_csv(tier3_team_path)
    df_player_impact = pd.read_csv(player_impact_path)
    game_context = json.loads(game_context_path.read_text(encoding="utf-8"))

    df_player_derived = merge_player_derived(df_tier2_player, df_player_impact)
    df_team_derived = merge_team_derived(df_tier3_team, game_context)

    player_out = output_dir / "player_derived.csv"
    team_out = output_dir / "team_derived.csv"
    df_player_derived.to_csv(player_out, index=False)
    df_team_derived.to_csv(team_out, index=False)
    console.print(f"[cyan]Wrote {player_out}[/cyan]")
    console.print(f"[cyan]Wrote {team_out}[/cyan]")
    return df_player_derived, df_team_derived


if __name__ == "__main__":
    run()
