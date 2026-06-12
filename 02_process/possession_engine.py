"""
02_process/possession_engine.py
================================
Tier 2: Possession Estimation, Pace, and Per-100 Efficiency Ratings

Inputs (reads from 03_outputs/):
    tier1_shooting_team.csv    (team-level, includes raw box + Tier 1 cols)
    tier1_shooting_player.csv  (player-level, for player ORtg approximation)

Key computation: Possession estimation
    POSS = FGA - OREB + TOV + (0.475 * FTA)
    This is the college/WNBA standard (0.475 FT multiplier vs. 0.44 NBA).
    Note: WNBA uses the same 0.44 multiplier as NBA. We expose both as
    config-switchable; default = 0.44 for WNBA.

Derived metrics (team level):
    poss             estimated possessions used
    poss_opp         opponent estimated possessions
    pace             (poss + poss_opp) / 2 * (40 / minutes_played)
    ortg             offensive rating = (pts / poss) * 100
    drtg             defensive rating = (pts_opp / poss_opp) * 100
    net_rtg          ortg - drtg
    ppp              points per possession
    ppp_opp          opponent points per possession

Derived metrics (player level):
    poss_share       player's estimated possession share of team total
    usg_pct          usage rate = (FGA + 0.44*FTA + TOV) / (team_poss * min_share)
    approx_ortg      simplified individual offensive rating

Outputs (written to 03_outputs/):
    tier2_possession_team.csv
    tier2_possession_player.csv

Usage:
    python 02_process/possession_engine.py
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
# Safe division
# ---------------------------------------------------------------------------
def safe_div(num, denom, decimals: int = 4):
    if isinstance(num, pd.Series):
        return np.where(
            pd.to_numeric(denom, errors="coerce").fillna(0) > 0,
            (pd.to_numeric(num, errors="coerce") / pd.to_numeric(denom, errors="coerce")).round(decimals),
            0.0,
        ).astype(float)
    denom = float(denom) if denom else 0.0
    if denom == 0:
        return 0.0
    return round(float(num) / denom, decimals)


# ---------------------------------------------------------------------------
# Possession estimation
# ---------------------------------------------------------------------------
def estimate_possessions(
    fga: pd.Series,
    oreb: pd.Series,
    tov: pd.Series,
    fta: pd.Series,
    ft_multiplier: float = 0.44,
) -> pd.Series:
    """
    WNBA/NBA standard possession estimate:
        POSS = FGA - OREB + TOV + (ft_multiplier * FTA)

    ft_multiplier:
        0.44  — WNBA / NBA standard (default)
        0.475 — NCAA college standard
    """
    poss = fga - oreb + tov + (ft_multiplier * fta)
    return poss.clip(lower=0).round(2)


# ---------------------------------------------------------------------------
# Pace calculation
# ---------------------------------------------------------------------------
def compute_pace(
    poss_team: pd.Series,
    poss_opp: pd.Series,
    minutes_played: float,
    regulation_minutes: float = 40.0,
) -> pd.Series:
    """
    Pace = average possessions per regulation (40 min for WNBA).
        pace = ((poss_team + poss_opp) / 2) * (regulation_minutes / minutes_played)

    minutes_played: actual elapsed game minutes at point of calculation.
    regulation_minutes: 40 for WNBA (4 x 10-min quarters).
    """
    if minutes_played <= 0:
        return pd.Series([0.0] * len(poss_team))
    return (((poss_team + poss_opp) / 2) * (regulation_minutes / minutes_played)).round(2)


# ---------------------------------------------------------------------------
# Team-level Tier 2 derivation
# ---------------------------------------------------------------------------
def compute_team_possession_metrics(
    df_teams: pd.DataFrame,
    ft_multiplier: float = 0.44,
    regulation_minutes: float = 40.0,
) -> pd.DataFrame:
    """
    Compute all Tier 2 team metrics.
    Requires both teams in df_teams (home + away) so opponent stats are accessible.
    """
    df = df_teams.copy().reset_index(drop=True)

    # Estimate possessions per team
    df["poss"] = estimate_possessions(
        df["fga"], df["oreb"], df["tov"], df["fta"], ft_multiplier
    )

    # Pair each team with its opponent
    # Assumes exactly 2 rows (home + away); generalize if OT squads appear
    if len(df) == 2:
        opp_pts  = df["pts"].iloc[::-1].values
        opp_poss = df["poss"].iloc[::-1].values
        df["pts_opp"]  = opp_pts
        df["poss_opp"] = opp_poss
    else:
        # Fallback: join on game_id, match by home_away inverse
        console.print("[yellow]Warning: expected 2 team rows, got {len(df)}. Opponent stats may be missing.[/yellow]")
        df["pts_opp"]  = np.nan
        df["poss_opp"] = np.nan

    # Elapsed minutes — use period + clock to estimate
    # period 1–4 each = 10 min; clock counts down within period
    # If game_status is final, minutes_played = 40 (or 45/50 for OT)
    if "period" in df.columns and "clock" in df.columns:
        def _elapsed_minutes(row) -> float:
            period = int(row.get("period", 1))
            clock_str = str(row.get("clock", "10:00"))
            try:
                if ":" in clock_str:
                    mins, secs = clock_str.split(":")
                    remaining_in_period = float(mins) + float(secs) / 60
                else:
                    remaining_in_period = float(clock_str) / 60
            except (ValueError, AttributeError):
                remaining_in_period = 0.0
            completed_periods = max(period - 1, 0)
            elapsed = completed_periods * 10.0 + (10.0 - remaining_in_period)
            # Cap to regulation; OT handling can be extended later
            return min(max(elapsed, 1.0), regulation_minutes)

        df["minutes_elapsed"] = df.apply(_elapsed_minutes, axis=1)
    else:
        df["minutes_elapsed"] = regulation_minutes  # assume full game if no clock

    # Pace
    df["pace"] = compute_pace(
        df["poss"], df["poss_opp"].fillna(df["poss"]),
        df["minutes_elapsed"].iloc[0],  # same clock for both teams
        regulation_minutes,
    )

    # Points per possession
    df["ppp"]     = safe_div(df["pts"],     df["poss"])
    df["ppp_opp"] = safe_div(df["pts_opp"], df["poss_opp"].fillna(1))

    # Offensive and Defensive ratings (per 100 possessions)
    df["ortg"] = (df["ppp"]     * 100).round(2)
    df["drtg"] = (df["ppp_opp"] * 100).round(2)
    df["net_rtg"] = (df["ortg"] - df["drtg"]).round(2)

    # Pace vs WNBA average flag (from config thresholds)
    # Set by caller after load_config

    return df


# ---------------------------------------------------------------------------
# Player-level Tier 2 derivation
# ---------------------------------------------------------------------------
def compute_player_possession_metrics(
    df_players: pd.DataFrame,
    df_teams_tier2: pd.DataFrame,
    ft_multiplier: float = 0.44,
) -> pd.DataFrame:
    """
    Compute player-level Tier 2 metrics:
        usg_pct          Usage rate
        poss_share       % of team possessions used while on floor
        approx_ortg      Simplified individual offensive rating

    Merges team-level poss onto player rows by team_abbr.
    """
    df = df_players.copy()

    # Pull team-level poss + minutes_elapsed for the merge
    team_ref = df_teams_tier2[["team_abbr", "poss", "minutes_elapsed", "ortg"]].copy()
    team_ref = team_ref.rename(columns={
        "poss": "team_poss",
        "minutes_elapsed": "team_minutes_elapsed",
        "ortg": "team_ortg",
    })
    df = df.merge(team_ref, on="team_abbr", how="left")

    # Minutes share = player minutes / team minutes elapsed
    df["min_share"] = safe_div(
        pd.to_numeric(df["minutes"], errors="coerce").fillna(0),
        pd.to_numeric(df["team_minutes_elapsed"], errors="coerce").fillna(1),
    )

    # Denominator for USG%: team_poss * min_share
    usg_denom = df["team_poss"] * df["min_share"]

    # USG% = (FGA + 0.44*FTA + TOV) / (team_poss * min_share)
    usg_num = (
        pd.to_numeric(df["fga"], errors="coerce").fillna(0)
        + 0.44 * pd.to_numeric(df["fta"], errors="coerce").fillna(0)
        + pd.to_numeric(df["tov"], errors="coerce").fillna(0)
    )
    df["usg_pct"] = safe_div(usg_num, usg_denom)
    df["usg_pct"] = df["usg_pct"].clip(upper=1.0)  # cap at 100%

    # Poss share (simpler version): player estimated possessions / team total
    player_poss = estimate_possessions(
        pd.to_numeric(df["fga"],  errors="coerce").fillna(0),
        pd.to_numeric(df["oreb"], errors="coerce").fillna(0),
        pd.to_numeric(df["tov"],  errors="coerce").fillna(0),
        pd.to_numeric(df["fta"],  errors="coerce").fillna(0),
        ft_multiplier,
    )
    df["player_poss"] = player_poss
    df["poss_share"]  = safe_div(player_poss, df["team_poss"].fillna(1))

    # Approximate individual offensive rating
    # approx_ortg = (pts / player_poss) * 100 (simplified; not Hollinger full formula)
    df["approx_ortg"] = safe_div(
        pd.to_numeric(df["pts"], errors="coerce").fillna(0) * 100,
        player_poss.replace(0, np.nan),
    )
    df["approx_ortg"] = df["approx_ortg"].fillna(0).clip(upper=200).round(2)

    return df


# ---------------------------------------------------------------------------
# Threshold flags
# ---------------------------------------------------------------------------
def apply_possession_flags(df_teams: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    df = df_teams.copy()
    wnba_avg_pace = thresholds.get("pace_wnba_avg", 88.5)
    wnba_avg_ortg = thresholds.get("ortg_wnba_avg", 103.0)
    df["flag_pace_above_avg"] = df["pace"] >= wnba_avg_pace
    df["flag_ortg_above_avg"] = df["ortg"] >= wnba_avg_ortg
    df["flag_net_rtg_pos"]    = df["net_rtg"] > 0
    return df


# ---------------------------------------------------------------------------
# Rich preview
# ---------------------------------------------------------------------------
def print_possession_preview(df_teams: pd.DataFrame, df_players: pd.DataFrame) -> None:
    console.rule("[bold]Tier 2 — Team Possession & Efficiency Ratings[/bold]")
    t = Table(show_header=True, header_style="bold magenta")
    cols = ["team_abbr", "home_away", "poss", "poss_opp", "pace",
            "ppp", "ortg", "drtg", "net_rtg", "minutes_elapsed"]
    for c in cols:
        if c in df_teams.columns:
            t.add_column(c)
    for _, row in df_teams.iterrows():
        t.add_row(*[str(row.get(c, "")) for c in cols if c in df_teams.columns])
    console.print(t)

    console.rule("[bold]Tier 2 — Player Usage & Possession Share (top 10 by USG%)[/bold]")
    p = Table(show_header=True, header_style="bold cyan")
    pcols = ["player_name", "team_abbr", "minutes", "usg_pct",
             "poss_share", "player_poss", "approx_ortg"]
    for c in pcols:
        if c in df_players.columns:
            p.add_column(c)
    active = df_players[df_players["did_not_play"] == False] if "did_not_play" in df_players.columns else df_players
    for _, row in active.sort_values("usg_pct", ascending=False).head(10).iterrows():
        p.add_row(*[str(row.get(c, "")) for c in pcols if c in df_players.columns])
    console.print(p)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    config = load_config()
    output_dir = REPO_ROOT / config.get("output_dir", "03_outputs")
    thresholds  = config.get("thresholds", {})

    player_path = output_dir / "tier1_shooting_player.csv"
    team_path   = output_dir / "tier1_shooting_team.csv"

    if not player_path.exists() or not team_path.exists():
        console.print("[bold red]Tier 1 CSVs not found. Run 02_process/shooting_metrics.py first.[/bold red]")
        raise FileNotFoundError("Missing tier1_shooting_*.csv in 03_outputs/")

    df_players = pd.read_csv(player_path)
    df_teams   = pd.read_csv(team_path)

    console.print(f"[green]Loaded tier1_shooting_player.csv ({len(df_players)} rows)[/green]")
    console.print(f"[green]Loaded tier1_shooting_team.csv ({len(df_teams)} rows)[/green]")

    df_teams   = compute_team_possession_metrics(df_teams)
    df_players = compute_player_possession_metrics(df_players, df_teams)
    df_teams   = apply_possession_flags(df_teams, thresholds)

    out_team   = output_dir / "tier2_possession_team.csv"
    out_player = output_dir / "tier2_possession_player.csv"
    df_teams.to_csv(out_team, index=False)
    df_players.to_csv(out_player, index=False)
    console.print(f"[cyan]Wrote {out_team}[/cyan]")
    console.print(f"[cyan]Wrote {out_player}[/cyan]")

    print_possession_preview(df_teams, df_players)

    return df_players, df_teams


if __name__ == "__main__":
    run()
