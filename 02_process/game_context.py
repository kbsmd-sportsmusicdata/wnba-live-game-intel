"""
02_process/game_context.py
==========================
Game-level context derived from raw team box and team possession outputs.

Inputs (reads from 03_outputs/):
    raw_team.csv
    tier2_possession_team.csv

Outputs:
    game_context.json
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests
import yaml
from rich.console import Console


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "game_config.yaml"
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

console = Console()


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f) or {}


def _clock_to_minutes(clock_value) -> float:
    if clock_value in (None, "", float("nan")):
        return 0.0
    clock_str = str(clock_value)
    try:
        if ":" in clock_str:
            mins, secs = clock_str.split(":")
            return float(mins) + float(secs) / 60
        return float(clock_str) / 60
    except (ValueError, TypeError):
        return 0.0


def fetch_espn_summary(game_id: str) -> dict:
    try:
        response = requests.get(
            ESPN_URL,
            params={"event": game_id},
            headers=HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        console.print(f"[yellow]Warning: unable to fetch summary payload for game context ({exc}).[/yellow]")
        return {}


def _extract_linescores(summary_data: dict) -> tuple[dict, dict]:
    competitors = (summary_data.get("header", {}).get("competitions", [{}])[0]).get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    return home, away


def _normalize_linescore_values(competitor: dict) -> list[int]:
    values = []
    for entry in competitor.get("linescores", []) or []:
        try:
            values.append(int(entry.get("displayValue", 0)))
        except (TypeError, ValueError):
            values.append(0)
    return values


def _build_wpba_context(
    home_abbr: str,
    away_abbr: str,
    home_pts: int,
    away_pts: int,
    is_final: bool,
    summary_data: dict,
    pace: float | None,
) -> dict:
    home_competitor, away_competitor = _extract_linescores(summary_data)
    home_linescores = _normalize_linescore_values(home_competitor)
    away_linescores = _normalize_linescore_values(away_competitor)
    quarter_count = min(len(home_linescores), len(away_linescores))
    home_quarter_points = 0.0
    away_quarter_points = 0.0
    home_quarters_won = 0
    away_quarters_won = 0
    tied_quarters = 0
    quarter_breakdown = []

    for idx in range(quarter_count):
        home_q = home_linescores[idx]
        away_q = away_linescores[idx]
        if home_q > away_q:
            winner_abbr = home_abbr
            home_points = 1.0
            away_points = 0.0
            home_quarters_won += 1
        elif away_q > home_q:
            winner_abbr = away_abbr
            home_points = 0.0
            away_points = 1.0
            away_quarters_won += 1
        else:
            winner_abbr = "TIE"
            home_points = 0.5
            away_points = 0.5
            tied_quarters += 1

        home_quarter_points += home_points
        away_quarter_points += away_points
        quarter_breakdown.append({
            "quarter": idx + 1,
            "home_points_scored": home_q,
            "away_points_scored": away_q,
            "winner_team_abbr": winner_abbr,
            "home_wpba_points": home_points,
            "away_wpba_points": away_points,
        })

    home_game_win_points = 3.0 if is_final and home_pts > away_pts else 0.0
    away_game_win_points = 3.0 if is_final and away_pts > home_pts else 0.0
    home_total_points = home_game_win_points + home_quarter_points
    away_total_points = away_game_win_points + away_quarter_points

    if home_total_points > away_total_points:
        points_leader_team_abbr = home_abbr
    elif away_total_points > home_total_points:
        points_leader_team_abbr = away_abbr
    else:
        points_leader_team_abbr = "TIE"

    if points_leader_team_abbr == away_abbr:
        scoreline_text = f"{away_abbr} {away_total_points:.1f}, {home_abbr} {home_total_points:.1f}"
    else:
        scoreline_text = f"{home_abbr} {home_total_points:.1f}, {away_abbr} {away_total_points:.1f}"

    storylines = [f"WPBA scoreline: {scoreline_text}."]
    if is_final and points_leader_team_abbr in {home_abbr, away_abbr}:
        leader_points = away_total_points if points_leader_team_abbr == away_abbr else home_total_points
        leader_quarters = away_quarters_won if points_leader_team_abbr == away_abbr else home_quarters_won
        storylines.append(
            f"{points_leader_team_abbr} banked {leader_points:.1f} of 7 WPBA points and won {leader_quarters} of {quarter_count} quarters plus the overall game."
        )
    if tied_quarters:
        if tied_quarters == 1:
            storylines.append("One quarter ended tied, so both teams split 0.5 WPBA points in that period.")
        else:
            storylines.append(f"Two quarters ended tied, so both teams split 0.5 points in each of those periods." if tied_quarters == 2 else f"{tied_quarters} quarters ended tied, creating shared WPBA quarter points.")
    if quarter_breakdown:
        final_quarter = quarter_breakdown[-1]
        final_winner = final_quarter["winner_team_abbr"]
        game_winner = home_abbr if home_pts > away_pts else away_abbr
        if is_final and final_winner not in ("TIE", game_winner):
            storylines.append(
                f"{final_winner} won the final quarter to bank a late WPBA point despite dropping the overall result."
            )
    if pace:
        storylines.append(
            f"The game played at a {pace:.1f} pace, increasing the value of every quarter-possession swing in the WPBA points race."
        )

    return {
        "format_name": "WPBA 7-point system",
        "available_points": 7.0,
        "home_game_win_points": home_game_win_points,
        "away_game_win_points": away_game_win_points,
        "home_quarter_points": round(home_quarter_points, 1),
        "away_quarter_points": round(away_quarter_points, 1),
        "home_total_points": round(home_total_points, 1),
        "away_total_points": round(away_total_points, 1),
        "home_quarters_won": home_quarters_won,
        "away_quarters_won": away_quarters_won,
        "tied_quarters": tied_quarters,
        "points_leader_team_abbr": points_leader_team_abbr,
        "scoreline_text": scoreline_text,
        "quarter_breakdown": quarter_breakdown,
    }, storylines


def _build_team_storylines(home: pd.Series, away: pd.Series, winner_abbr: str) -> list[str]:
    storylines = []
    home_abbr = str(home.get("team_abbr", ""))
    away_abbr = str(away.get("team_abbr", ""))

    home_assists = _safe_int(home.get("ast", 0))
    away_assists = _safe_int(away.get("ast", 0))
    if abs(home_assists - away_assists) >= 5:
        leader_abbr = home_abbr if home_assists > away_assists else away_abbr
        leader_assists = max(home_assists, away_assists)
        trailing_assists = min(home_assists, away_assists)
        storylines.append(
            f"{leader_abbr} led assists {leader_assists}-{trailing_assists}, a strong ball-movement and coaching-control signal for the broadcast."
        )

    home_paint = _safe_int(home.get("pts_in_paint", 0))
    away_paint = _safe_int(away.get("pts_in_paint", 0))
    if abs(home_paint - away_paint) >= 4:
        leader_abbr = home_abbr if home_paint > away_paint else away_abbr
        leader_paint = max(home_paint, away_paint)
        trailing_paint = min(home_paint, away_paint)
        storylines.append(
            f"{leader_abbr} controlled the paint {leader_paint}-{trailing_paint}, a useful frontcourt and game-plan angle to emphasize."
        )

    home_reb = _safe_int(home.get("reb", 0))
    away_reb = _safe_int(away.get("reb", 0))
    if abs(home_reb - away_reb) >= 5:
        leader_abbr = home_abbr if home_reb > away_reb else away_abbr
        leader_reb = max(home_reb, away_reb)
        trailing_reb = min(home_reb, away_reb)
        storylines.append(
            f"{leader_abbr} won the glass {leader_reb}-{trailing_reb}, which helps explain quarter-by-quarter WPBA point pressure."
        )

    home_pts_off_tov = _safe_int(home.get("pts_off_tov", 0))
    away_pts_off_tov = _safe_int(away.get("pts_off_tov", 0))
    if abs(home_pts_off_tov - away_pts_off_tov) >= 4:
        leader_abbr = home_abbr if home_pts_off_tov > away_pts_off_tov else away_abbr
        leader_pts_off_tov = max(home_pts_off_tov, away_pts_off_tov)
        trailing_pts_off_tov = min(home_pts_off_tov, away_pts_off_tov)
        storylines.append(
            f"{leader_abbr} created a live-ball edge with points off turnovers {leader_pts_off_tov}-{trailing_pts_off_tov}."
        )

    home_second_chance = _safe_int(home.get("second_chance_pts", 0))
    away_second_chance = _safe_int(away.get("second_chance_pts", 0))
    if abs(home_second_chance - away_second_chance) >= 4:
        leader_abbr = home_abbr if home_second_chance > away_second_chance else away_abbr
        leader_second_chance = max(home_second_chance, away_second_chance)
        trailing_second_chance = min(home_second_chance, away_second_chance)
        storylines.append(
            f"{leader_abbr} won the extra-possession battle with second-chance scoring {leader_second_chance}-{trailing_second_chance}."
        )

    for team, team_abbr in ((home, home_abbr), (away, away_abbr)):
        total_points = _safe_float(team.get("pts", 0))
        if total_points <= 0:
            continue
        three_point_points = _safe_float(team.get("tpm", 0)) * 3.0
        free_throw_points = _safe_float(team.get("ftm", 0))
        two_point_points = max(
            total_points - three_point_points - free_throw_points,
            0.0,
        )
        two_share = round((two_point_points / total_points) * 100)
        three_share = round((three_point_points / total_points) * 100)
        free_throw_share = round((free_throw_points / total_points) * 100)
        storylines.append(
            f"{team_abbr} scoring distribution: {two_share}% from 2P, {three_share}% from 3P, and {free_throw_share}% from the line."
        )
        if three_share >= 30:
            storylines.append(
                f"{team_abbr} carried a heavy 3-point scoring share at {three_share}%, which is a clear shot-diet talking point."
            )
        if free_throw_share >= 20:
            storylines.append(
                f"{team_abbr} posted a notable free-throw scoring share at {free_throw_share}%, showing how often they converted pressure into points."
            )

    home_largest_lead = _safe_int(home.get("largest_lead", 0))
    away_largest_lead = _safe_int(away.get("largest_lead", 0))
    max_lead = max(home_largest_lead, away_largest_lead)
    if max_lead >= 10:
        leader_abbr = home_abbr if home_largest_lead >= away_largest_lead else away_abbr
        if leader_abbr == winner_abbr:
            storylines.append(
                f"{leader_abbr} nearly gave away a {max_lead}-point lead before still securing the top-value WPBA game-win points."
            )
        else:
            storylines.append(
                f"{leader_abbr} built a {max_lead}-point cushion but could not convert it into the 3-point overall WPBA reward."
            )

    return storylines


def build_game_context(
    df_raw_teams: pd.DataFrame,
    df_team_possession: pd.DataFrame | None = None,
    summary_data: dict | None = None,
) -> dict:
    if df_raw_teams.empty:
        return {}

    raw = df_raw_teams.copy().reset_index(drop=True)
    pace = None
    minutes_elapsed = None
    if df_team_possession is not None and not df_team_possession.empty:
        pace = float(pd.to_numeric(df_team_possession["pace"], errors="coerce").fillna(0).mean())
        minutes_elapsed = float(pd.to_numeric(df_team_possession["minutes_elapsed"], errors="coerce").fillna(0).max())

    home_rows = raw[raw["home_away"] == "home"]
    away_rows = raw[raw["home_away"] == "away"]
    home = home_rows.iloc[0] if not home_rows.empty else raw.iloc[0]
    away = away_rows.iloc[0] if not away_rows.empty else raw.iloc[-1]

    home_pts = _safe_int(home.get("pts", 0))
    away_pts = _safe_int(away.get("pts", 0))
    final_margin = abs(home_pts - away_pts)
    game_status = str(home.get("game_status", "unknown"))
    period = _safe_int(home.get("period", 0))
    clock = home.get("clock", "")
    clock_minutes = _clock_to_minutes(clock)
    is_final = "FINAL" in game_status.upper()
    is_clutch_window = period >= 4 and clock_minutes <= 5.0

    winner = home if home_pts >= away_pts else away
    loser = away if home_pts >= away_pts else home

    wpba_context = None
    broadcast_storylines = []
    if summary_data:
        wpba_context, broadcast_storylines = _build_wpba_context(
            home_abbr=str(home.get("team_abbr", "")),
            away_abbr=str(away.get("team_abbr", "")),
            home_pts=home_pts,
            away_pts=away_pts,
            is_final=is_final,
            summary_data=summary_data,
            pace=pace,
        )
    broadcast_storylines.extend(
        _build_team_storylines(
            home=home,
            away=away,
            winner_abbr=str(winner.get("team_abbr", "")),
        )
    )

    context = {
        "game_id": str(home.get("game_id", "")),
        "game_date": str(home.get("game_date", "")),
        "fetched_at": str(home.get("fetched_at", "")),
        "game_status": game_status,
        "is_final": is_final,
        "period": period,
        "clock": str(clock),
        "minutes_elapsed": minutes_elapsed,
        "pace": pace,
        "home_team_abbr": str(home.get("team_abbr", "")),
        "away_team_abbr": str(away.get("team_abbr", "")),
        "home_pts": home_pts,
        "away_pts": away_pts,
        "winner_team_abbr": str(winner.get("team_abbr", "")),
        "loser_team_abbr": str(loser.get("team_abbr", "")),
        "final_margin": final_margin,
        "is_clutch_window": is_clutch_window,
        "is_close_final": is_final and final_margin <= 5,
    }
    if wpba_context is not None:
        context["wpba"] = wpba_context
        context["broadcast_storylines"] = broadcast_storylines
    return context


def run() -> dict:
    config = load_config()
    output_dir = REPO_ROOT / config.get("output_dir", "03_outputs")
    raw_team_path = output_dir / "raw_team.csv"
    team_possession_path = output_dir / "tier2_possession_team.csv"

    if not raw_team_path.exists():
        console.print("[bold red]raw_team.csv not found. Run 01_ingest/box_ingest.py first.[/bold red]")
        raise FileNotFoundError("Missing raw_team.csv in 03_outputs/")

    df_raw_teams = pd.read_csv(raw_team_path)
    df_team_possession = pd.read_csv(team_possession_path) if team_possession_path.exists() else None
    game_id = str(df_raw_teams.iloc[0]["game_id"]) if not df_raw_teams.empty else ""
    summary_data = fetch_espn_summary(game_id) if game_id else {}
    context = build_game_context(df_raw_teams, df_team_possession, summary_data=summary_data)

    out_path = output_dir / "game_context.json"
    out_path.write_text(json.dumps(context, indent=2), encoding="utf-8")
    console.print(f"[cyan]Wrote {out_path}[/cyan]")
    return context


if __name__ == "__main__":
    run()
