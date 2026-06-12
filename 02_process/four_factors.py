"""
02_process/four_factors.py
==========================
Tier 3: Dean Oliver's Four Factors

The Four Factors are the most analytically complete framework derivable
from box score data alone. They explain the overwhelming majority of
variance in game outcomes.

    Factor 1: Shooting      — eFG%
    Factor 2: Turnovers     — TOV% (turnovers per possession)
    Factor 3: Rebounding    — OREB%
    Factor 4: Free Throws   — FTR (FTA / FGA)

Oliver's original weights (offense):
    Shooting:    0.40
    Turnovers:   0.25
    Rebounding:  0.20
    Free Throws: 0.15

Inputs (reads from 03_outputs/):
    tier2_possession_team.csv  (has poss, poss_opp, oreb, dreb cols)

Derived metrics:
    efg_pct          eFG% (from Tier 1, already computed)
    tov_rate         TOV% = TOV / POSS
    oreb_pct         OREB% = OREB / (OREB + OPP_DREB)
    ftr              FT Rate = FTA / FGA (from Tier 1, already computed)

    All four computed for BOTH teams, plus net differentials.

    four_factors_score   Weighted composite (0.40*eFG - 0.25*tov_rate
                         + 0.20*oreb_pct + 0.15*ftr)
                         Higher = better offensive profile.

Outputs:
    tier3_four_factors.csv    — one row per team, all FF cols + differentials
    tier3_four_factors_wide.csv  — side-by-side pivot for dashboard rendering

Usage:
    python 02_process/four_factors.py
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

# Oliver's original factor weights
FACTOR_WEIGHTS = {
    "efg_pct":   0.40,
    "tov_rate":  0.25,  # sign-flipped in composite (turnovers are bad)
    "oreb_pct":  0.20,
    "ftr":       0.15,
}


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
            (pd.to_numeric(num, errors="coerce") /
             pd.to_numeric(denom, errors="coerce")).round(decimals),
            0.0,
        ).astype(float)
    denom = float(denom) if denom else 0.0
    return 0.0 if denom == 0 else round(float(num) / denom, decimals)


# ---------------------------------------------------------------------------
# Four Factors computation
# ---------------------------------------------------------------------------
def compute_four_factors(df_teams: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the Four Factors for each team row.

    Requires columns:
        efg_pct, ftr  (from Tier 1)
        poss, oreb, dreb  (from Tier 2 / raw)
        tov

    Also requires opponent rebounding to compute OREB%.
    Assumes exactly 2 rows (home + away) so opponent DREB is accessible.
    """
    df = df_teams.copy().reset_index(drop=True)

    # Factor 2: Turnover Rate = TOV / POSS
    df["tov_rate"] = safe_div(
        pd.to_numeric(df["tov"],  errors="coerce").fillna(0),
        pd.to_numeric(df["poss"], errors="coerce").fillna(1),
    )

    # Factor 3: OREB% = OREB / (OREB_team + DREB_opp)
    # For 2-team game: opp DREB is the other team's dreb
    if len(df) == 2:
        opp_dreb = df["dreb"].iloc[::-1].values
        df["opp_dreb"] = opp_dreb
    else:
        console.print("[yellow]Warning: expected 2 team rows for OREB% calculation.[/yellow]")
        df["opp_dreb"] = df["dreb"]  # fallback: own dreb as proxy

    df["oreb_pct"] = safe_div(
        pd.to_numeric(df["oreb"],     errors="coerce").fillna(0),
        pd.to_numeric(df["oreb"],     errors="coerce").fillna(0)
        + pd.to_numeric(df["opp_dreb"], errors="coerce").fillna(0),
    )

    # Confirm eFG% and FTR present (from Tier 1) — recompute if missing
    if "efg_pct" not in df.columns:
        df["efg_pct"] = safe_div(
            pd.to_numeric(df["fgm"], errors="coerce").fillna(0)
            + 0.5 * pd.to_numeric(df["tpm"], errors="coerce").fillna(0),
            pd.to_numeric(df["fga"], errors="coerce").fillna(1),
        )
    if "ftr" not in df.columns:
        df["ftr"] = safe_div(
            pd.to_numeric(df["fta"], errors="coerce").fillna(0),
            pd.to_numeric(df["fga"], errors="coerce").fillna(1),
        )

    # Four Factors composite score
    # Higher score = better overall offensive profile
    # TOV rate is subtracted (turnovers hurt)
    df["four_factors_score"] = (
        FACTOR_WEIGHTS["efg_pct"]  *  df["efg_pct"]
        - FACTOR_WEIGHTS["tov_rate"] * df["tov_rate"]
        + FACTOR_WEIGHTS["oreb_pct"] * df["oreb_pct"]
        + FACTOR_WEIGHTS["ftr"]      * df["ftr"]
    ).round(4)

    return df


def compute_four_factors_differentials(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add net differential columns for each factor (team - opponent).
    Positive = team is winning that factor.
    Assumes 2 rows. Differentials added as new columns.
    """
    df = df.copy().reset_index(drop=True)
    if len(df) != 2:
        console.print("[yellow]Differential computation requires exactly 2 team rows.[/yellow]")
        return df

    factors = ["efg_pct", "tov_rate", "oreb_pct", "ftr", "four_factors_score"]
    for factor in factors:
        if factor not in df.columns:
            continue
        vals = pd.to_numeric(df[factor], errors="coerce").fillna(0).values
        diff = vals - vals[::-1]
        col = f"{factor}_diff"
        df[col] = diff.round(4)
        # Flag: who is winning this factor?
        # For tov_rate: LOWER is better, so flip sign
        if factor == "tov_rate":
            df[f"{factor}_winning"] = diff < 0  # negative diff = fewer TOVs = winning
        else:
            df[f"{factor}_winning"] = diff > 0  # positive diff = higher value = winning

    return df


def build_wide_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot to a wide format for side-by-side dashboard display.

    Returns a DataFrame with one row per factor and columns:
        factor, factor_label, weight, team_a_value, team_b_value,
        team_a_abbr, team_b_abbr, differential, winning_team
    """
    if len(df) != 2:
        return pd.DataFrame()

    team_a = df.iloc[0]
    team_b = df.iloc[1]

    factor_meta = [
        ("efg_pct",  "Effective FG%",    FACTOR_WEIGHTS["efg_pct"],  False),
        ("tov_rate", "Turnover Rate",     FACTOR_WEIGHTS["tov_rate"], True),   # lower=better
        ("oreb_pct", "Off. Reb. %",       FACTOR_WEIGHTS["oreb_pct"], False),
        ("ftr",      "Free Throw Rate",   FACTOR_WEIGHTS["ftr"],      False),
    ]

    rows = []
    for factor, label, weight, lower_is_better in factor_meta:
        val_a = float(team_a.get(factor, 0))
        val_b = float(team_b.get(factor, 0))
        diff  = round(val_a - val_b, 4)

        if lower_is_better:
            winning_team = team_a["team_abbr"] if val_a < val_b else team_b["team_abbr"]
        else:
            winning_team = team_a["team_abbr"] if val_a > val_b else team_b["team_abbr"]

        rows.append({
            "factor":          factor,
            "factor_label":    label,
            "weight":          weight,
            "lower_is_better": lower_is_better,
            "team_a_abbr":     team_a["team_abbr"],
            "team_b_abbr":     team_b["team_abbr"],
            "team_a_value":    round(val_a, 4),
            "team_b_value":    round(val_b, 4),
            "differential":    diff,
            "winning_team":    winning_team,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Threshold flags
# ---------------------------------------------------------------------------
def apply_four_factors_flags(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    df = df.copy()
    df["flag_efg_good"]  = df["efg_pct"]  >= thresholds.get("efg_pct_good",  0.520)
    df["flag_tov_bad"]   = df["tov_rate"] >= thresholds.get("tov_rate_bad",  0.180)
    df["flag_oreb_good"] = df["oreb_pct"] >= thresholds.get("oreb_pct_good", 0.300)
    df["flag_ftr_good"]  = df["ftr"]      >= thresholds.get("ftr_good",      0.300)
    return df


# ---------------------------------------------------------------------------
# Rich preview
# ---------------------------------------------------------------------------
def print_four_factors_preview(df: pd.DataFrame, df_wide: pd.DataFrame) -> None:
    console.rule("[bold]Tier 3 — Four Factors (per team)[/bold]")
    t = Table(show_header=True, header_style="bold magenta")
    cols = ["team_abbr", "efg_pct", "tov_rate", "oreb_pct", "ftr",
            "four_factors_score", "efg_pct_diff", "tov_rate_diff",
            "oreb_pct_diff", "ftr_diff"]
    for c in cols:
        if c in df.columns:
            t.add_column(c)
    for _, row in df.iterrows():
        t.add_row(*[str(row.get(c, "")) for c in cols if c in df.columns])
    console.print(t)

    if not df_wide.empty:
        console.rule("[bold]Tier 3 — Four Factors Side-by-Side[/bold]")
        w = Table(show_header=True, header_style="bold green")
        wide_cols = ["factor_label", "weight", "team_a_abbr",
                     "team_a_value", "team_b_value", "team_b_abbr",
                     "differential", "winning_team"]
        for c in wide_cols:
            if c in df_wide.columns:
                w.add_column(c)
        for _, row in df_wide.iterrows():
            w.add_row(*[str(row.get(c, "")) for c in wide_cols if c in df_wide.columns])
        console.print(w)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    config = load_config()
    output_dir = REPO_ROOT / config.get("output_dir", "03_outputs")
    thresholds  = config.get("thresholds", {})

    team_path = output_dir / "tier2_possession_team.csv"
    if not team_path.exists():
        console.print("[bold red]Tier 2 team CSV not found. Run 02_process/possession_engine.py first.[/bold red]")
        raise FileNotFoundError("Missing tier2_possession_team.csv in 03_outputs/")

    df_teams = pd.read_csv(team_path)
    console.print(f"[green]Loaded tier2_possession_team.csv ({len(df_teams)} rows)[/green]")

    df_teams = compute_four_factors(df_teams)
    df_teams = compute_four_factors_differentials(df_teams)
    df_teams = apply_four_factors_flags(df_teams, thresholds)
    df_wide  = build_wide_table(df_teams)

    out_long = output_dir / "tier3_four_factors.csv"
    out_wide = output_dir / "tier3_four_factors_wide.csv"
    df_teams.to_csv(out_long, index=False)
    df_wide.to_csv(out_wide, index=False)
    console.print(f"[cyan]Wrote {out_long}[/cyan]")
    console.print(f"[cyan]Wrote {out_wide}[/cyan]")

    print_four_factors_preview(df_teams, df_wide)

    return df_teams, df_wide


if __name__ == "__main__":
    run()
