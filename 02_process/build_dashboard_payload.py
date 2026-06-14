"""
02_process/build_dashboard_payload.py
=====================================
Builds the GitHub Pages dashboard JSON contract from the current live-game
derived outputs.

Preferred inputs (reads from 03_outputs/):
    player_derived.csv
    team_derived.csv
    game_context.json
    tier3_four_factors.csv
    tier3_four_factors_wide.csv

Fallback inputs:
    tier2_possession_player.csv
    tier2_possession_team.csv
    player_impact.csv
    raw_team.csv

Outputs:
    03_outputs/dashboard_payload.json
    03_outputs/game_summary.json
    docs/dashboard_data/dashboard_payload.json
    docs/dashboard_data/game_summary.json
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from rich.console import Console
except ImportError:  # pragma: no cover - exercised in local bare-python runs
    class Console:  # type: ignore
        def print(self, *_args, **_kwargs):
            return None

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised in local bare-python runs
    yaml = None


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "game_config.yaml"
PIPELINE_VERSION = "phase1_pages_mvp_v2"

console = Console()


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    if not Path(config_path).exists():
        return {}
    if yaml is None:
        text = Path(config_path).read_text(encoding="utf-8")
        match = re.search(r'^\s*output_dir:\s*"?(.*?)"?\s*$', text, flags=re.MULTILINE)
        return {"output_dir": match.group(1)} if match else {}
    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _round_or_none(value: Any, digits: int = 4):
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def get_foul_status(pf: Any) -> str:
    fouls = _safe_int(pf)
    if fouls >= 5:
        return "foul_out"
    if fouls >= 4:
        return "danger"
    if fouls >= 3:
        return "watch"
    return "safe"


def compute_ast_to_fields(ast: Any, tov: Any) -> tuple[float | None | int, str]:
    assists = _safe_float(ast)
    turnovers = _safe_float(tov)
    if turnovers > 0:
        ratio = round(assists / turnovers, 2)
        return ratio, f"{ratio:.2f}"
    if assists > 0:
        return None, "No TO"
    return 0, "0.0"


def get_impact_tier(game_score: Any) -> str:
    score = _safe_float(game_score)
    if score >= 18:
        return "elite_impact"
    if score >= 12:
        return "strong_impact"
    if score >= 6:
        return "positive_impact"
    return "low_impact"


def get_efficiency_tier(ts_pct: Any) -> str:
    ts_value = _safe_float(ts_pct)
    if ts_value >= 0.650:
        return "elite_efficiency"
    if ts_value >= 0.600:
        return "strong_efficiency"
    if ts_value >= 0.520:
        return "solid_efficiency"
    return "low_efficiency"


def get_bench_impact_flag(starter: Any, game_score: Any) -> bool:
    return (not _as_bool(starter)) and _safe_float(game_score) >= 8.0


def _normalize_player_frame(df_players: pd.DataFrame) -> pd.DataFrame:
    df = df_players.copy()
    for col in ["minutes", "pts", "reb", "ast", "tov", "pf", "plus_minus", "fga", "fta", "efg_pct", "ts_pct", "usg_pct", "game_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["starter", "active", "did_not_play"]:
        if col in df.columns:
            df[col] = df[col].apply(_as_bool)
        else:
            df[col] = False
    if "home_away" not in df.columns:
        df["home_away"] = ""
    if "team_abbr" not in df.columns:
        df["team_abbr"] = ""
    if "player_name" not in df.columns:
        df["player_name"] = ""
    if "position" not in df.columns:
        df["position"] = ""

    ast_to_values = df.apply(lambda row: compute_ast_to_fields(row.get("ast"), row.get("tov")), axis=1)
    df["ast_to"] = [item[0] for item in ast_to_values]
    df["ast_to_display"] = [item[1] for item in ast_to_values]
    df["foul_status"] = df["pf"].apply(get_foul_status)
    df["starter_label"] = df["starter"].apply(lambda is_starter: "Starter" if is_starter else "Bench")
    df["impact_tier"] = df["game_score"].apply(get_impact_tier)
    df["efficiency_tier"] = df["ts_pct"].apply(get_efficiency_tier)
    df["bench_impact_flag"] = df.apply(lambda row: get_bench_impact_flag(row.get("starter"), row.get("game_score")), axis=1)
    return df


def _load_players(output_dir: Path) -> pd.DataFrame:
    derived_path = output_dir / "player_derived.csv"
    if derived_path.exists():
        return _normalize_player_frame(pd.read_csv(derived_path))

    tier2_path = output_dir / "tier2_possession_player.csv"
    impact_path = output_dir / "player_impact.csv"
    if tier2_path.exists():
        df_players = pd.read_csv(tier2_path)
        if impact_path.exists():
            df_impact = pd.read_csv(impact_path)
            impact_cols = ["game_id", "player_id", "usg_pct", "game_score", "ast_pct", "reb_pct"]
            df_players = df_players.drop(columns=["usg_pct", "game_score", "ast_pct", "reb_pct"], errors="ignore")
            df_players = df_players.merge(df_impact[impact_cols], on=["game_id", "player_id"], how="left")
        return _normalize_player_frame(df_players)

    raise FileNotFoundError("Missing player dashboard source files: player_derived.csv and fallback player inputs.")


def _load_teams(output_dir: Path, game_context: dict) -> pd.DataFrame:
    derived_path = output_dir / "team_derived.csv"
    if derived_path.exists():
        return pd.read_csv(derived_path)

    if tier2_team_path.exists() and raw_team_path.exists():
        df_raw = pd.read_csv(raw_team_path)
        df_tier2 = pd.read_csv(tier2_team_path)
        join_cols = ["game_id", "team_abbr"]
        merged = df_raw.merge(df_tier2, on=join_cols, how="left", suffixes=("", "_tier2"))
        merged["is_final"] = game_context.get("is_final")
        merged["final_margin"] = game_context.get("final_margin")
        merged["winner_team_abbr"] = game_context.get("winner_team_abbr")
        return merged

    if four_factors_path.exists():
        return pd.read_csv(four_factors_path)

    raise FileNotFoundError("Missing team dashboard source files: team_derived.csv and fallback team inputs.")


def _load_game_context(output_dir: Path) -> dict:
    context_path = output_dir / "game_context.json"
    if not context_path.exists():
        raise FileNotFoundError("Missing required game context input: game_context.json")
    return json.loads(context_path.read_text(encoding="utf-8"))


def _read_optional_csv(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def _serialize_record(record: dict) -> dict:
    clean = {}
    for key, value in record.items():
        if isinstance(value, (pd.Timestamp, datetime)):
            clean[key] = value.isoformat()
        elif pd.isna(value):
            clean[key] = None
        elif isinstance(value, bool):
            clean[key] = value
        elif isinstance(value, (int, float, str)) or value is None:
            clean[key] = value
        else:
            clean[key] = value
    return clean


def _build_team_cards(df_teams: pd.DataFrame) -> list[dict]:
    cards = []
    for _, row in df_teams.iterrows():
        cards.append(_serialize_record({
            "team_abbr": row.get("team_abbr"),
            "team_name": row.get("team_name"),
            "home_away": row.get("home_away"),
            "points": _safe_int(row.get("pts")),
            "rebounds": _safe_int(row.get("reb")),
            "fouls": _safe_int(row.get("pf")),
            "turnovers": _safe_int(row.get("tov")),
            "efg_pct": _round_or_none(row.get("efg_pct")),
            "ts_pct": _round_or_none(row.get("ts_pct")),
            "possessions": _round_or_none(row.get("poss"), 2),
            "pace": _round_or_none(row.get("pace"), 2),
            "ortg": _round_or_none(row.get("ortg"), 2),
            "drtg": _round_or_none(row.get("drtg"), 2),
            "net_rtg": _round_or_none(row.get("net_rtg"), 2),
            "wpba_total_points": _round_or_none(row.get("wpba_total_points"), 1),
            "wpba_game_win_points": _round_or_none(row.get("wpba_game_win_points"), 1),
            "wpba_quarter_points": _round_or_none(row.get("wpba_quarter_points"), 1),
            "wpba_quarters_won": _safe_int(row.get("wpba_quarters_won")),
            "wpba_tied_quarters": _safe_int(row.get("wpba_tied_quarters")),
            "four_factors_score": _round_or_none(row.get("four_factors_score")),
            "is_winner": bool(row.get("is_winner")) if "is_winner" in row else False,
        }))
    return cards


def _build_players(df_players: pd.DataFrame) -> list[dict]:
    players = []
    for _, row in df_players.iterrows():
        players.append(_serialize_record({
            "game_id": row.get("game_id"),
            "team_abbr": row.get("team_abbr"),
            "home_away": row.get("home_away"),
            "player_id": row.get("player_id"),
            "player_name": row.get("player_name"),
            "position": row.get("position"),
            "starter": _as_bool(row.get("starter")),
            "starter_label": row.get("starter_label"),
            "active": _as_bool(row.get("active")),
            "did_not_play": _as_bool(row.get("did_not_play")),
            "minutes": _round_or_none(row.get("minutes"), 1),
            "pts": _safe_int(row.get("pts")),
            "reb": _safe_int(row.get("reb")),
            "ast": _safe_int(row.get("ast")),
            "tov": _safe_int(row.get("tov")),
            "pf": _safe_int(row.get("pf")),
            "plus_minus": _safe_int(row.get("plus_minus")),
            "efg_pct": _round_or_none(row.get("efg_pct")),
            "ts_pct": _round_or_none(row.get("ts_pct")),
            "usg_pct": _round_or_none(row.get("usg_pct")),
            "game_score": _round_or_none(row.get("game_score"), 2),
            "ast_to": row.get("ast_to"),
            "ast_to_display": row.get("ast_to_display"),
            "foul_status": row.get("foul_status"),
            "impact_tier": row.get("impact_tier"),
            "efficiency_tier": row.get("efficiency_tier"),
            "bench_impact_flag": bool(row.get("bench_impact_flag")),
        }))
    return players


def _top_records(df: pd.DataFrame, sort_cols: list[str], ascending: list[bool], size: int = 5) -> list[dict]:
    if df.empty:
        return []
    subset = df.sort_values(sort_cols, ascending=ascending).head(size)
    return _build_players(subset)


def _build_leaders(df_players: pd.DataFrame) -> dict:
    efficiency_pool = df_players[(df_players.get("fga", 0).fillna(0) + df_players.get("fta", 0).fillna(0)) >= 3].copy()
    usage_pool = df_players[df_players.get("minutes", 0).fillna(0) >= 5].copy()
    bench_pool = df_players[df_players["bench_impact_flag"]].copy()
    foul_pool = df_players[df_players.get("pf", 0).fillna(0) >= 3].copy()

    return {
        "points": _top_records(df_players, ["pts", "game_score"], [False, False]),
        "rebounds": _top_records(df_players, ["reb", "game_score"], [False, False]),
        "assists": _top_records(df_players, ["ast", "game_score"], [False, False]),
        "game_score": _top_records(df_players, ["game_score", "pts"], [False, False]),
        "usage": _top_records(usage_pool, ["usg_pct", "game_score"], [False, False]),
        "efficiency": _top_records(efficiency_pool, ["ts_pct", "pts"], [False, False]),
        "bench_impact": _top_records(bench_pool, ["game_score", "pts"], [False, False]),
        "foul_trouble": _top_records(foul_pool, ["pf", "minutes"], [False, False]),
    }


def _build_insight_flags(df_players: pd.DataFrame, game_context: dict) -> list[dict]:
    flags = []
    if game_context.get("is_close_final") or game_context.get("is_clutch_window"):
        flags.append({
            "flag_type": "close_game",
            "message": "This game stayed inside a high-leverage window late, so possession-level swings mattered to both the scoreboard and the WPBA race.",
        })

    wpba = game_context.get("wpba") or {}
    if wpba.get("points_leader_team_abbr"):
        flags.append({
            "flag_type": "wpba_quarter_swing",
            "message": f"{wpba.get('points_leader_team_abbr')} is winning the WPBA points race through quarter control.",
        })

    for _, row in df_players.iterrows():
        player_name = row.get("player_name")
        team_abbr = row.get("team_abbr")
        if _safe_int(row.get("pf")) >= 5:
            flags.append({"flag_type": "foul_out", "message": f"{player_name} ({team_abbr}) reached foul-out territory."})
        elif _safe_int(row.get("pf")) >= 3:
            flags.append({"flag_type": "foul_trouble", "message": f"{player_name} ({team_abbr}) is in foul watch territory."})
        if _safe_float(row.get("game_score")) >= 15 or _safe_int(row.get("pts")) >= 15:
            flags.append({"flag_type": "hot_scorer", "message": f"{player_name} ({team_abbr}) is carrying a major scoring load."})
        if _safe_float(row.get("usg_pct")) >= 0.30 and _safe_float(row.get("minutes")) >= 5:
            flags.append({"flag_type": "high_usage", "message": f"{player_name} ({team_abbr}) is operating with high usage."})
        if _safe_float(row.get("ts_pct")) >= 0.60 and _safe_int(row.get("pts")) >= 8:
            flags.append({"flag_type": "efficient_scorer", "message": f"{player_name} ({team_abbr}) is scoring efficiently."})
        if _safe_int(row.get("tov")) >= 4:
            flags.append({"flag_type": "turnover_issue", "message": f"{player_name} ({team_abbr}) has a turnover-pressure flag."})
        if bool(row.get("bench_impact_flag")):
            flags.append({"flag_type": "bench_impact", "message": f"{player_name} ({team_abbr}) is driving meaningful bench impact."})

    deduped = []
    seen = set()
    for flag in flags:
        key = (flag["flag_type"], flag["message"])
        if key not in seen:
            seen.add(key)
            deduped.append(flag)
    return deduped


def _build_game_summary(game_context: dict) -> dict:
    return {
        "game_id": game_context.get("game_id"),
        "game_date": game_context.get("game_date"),
        "game_status": game_context.get("game_status"),
        "home_team_abbr": game_context.get("home_team_abbr"),
        "away_team_abbr": game_context.get("away_team_abbr"),
        "home_pts": game_context.get("home_pts"),
        "away_pts": game_context.get("away_pts"),
        "winner_team_abbr": game_context.get("winner_team_abbr"),
        "final_margin": game_context.get("final_margin"),
        "period": game_context.get("period"),
        "clock": game_context.get("clock"),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "wpba_scoreline_text": (game_context.get("wpba") or {}).get("scoreline_text"),
    }


def build_dashboard_payload(output_dir: Path) -> tuple[dict, dict]:
    output_dir = Path(output_dir)
    game_context = _load_game_context(output_dir)
    df_players = _load_players(output_dir)
    df_teams = _load_teams(output_dir, game_context)
    df_four_factors_long = _read_optional_csv(output_dir / "tier3_four_factors.csv")
    df_four_factors_wide = _read_optional_csv(output_dir / "tier3_four_factors_wide.csv")

    payload = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": PIPELINE_VERSION,
            "source": "espn_simulation",
        },
        "game": {
            "game_id": game_context.get("game_id"),
            "game_date": game_context.get("game_date"),
            "game_status": game_context.get("game_status"),
            "is_final": game_context.get("is_final"),
            "period": game_context.get("period"),
            "clock": game_context.get("clock"),
            "home_team_abbr": game_context.get("home_team_abbr"),
            "away_team_abbr": game_context.get("away_team_abbr"),
            "home_pts": game_context.get("home_pts"),
            "away_pts": game_context.get("away_pts"),
            "winner_team_abbr": game_context.get("winner_team_abbr"),
            "final_margin": game_context.get("final_margin"),
            "is_clutch_window": game_context.get("is_clutch_window"),
            "is_close_final": game_context.get("is_close_final"),
        },
        "wpba": game_context.get("wpba") or {},
        "teams": _build_team_cards(df_teams),
        "players": _build_players(df_players),
        "four_factors": {
            "long": [_serialize_record(item) for item in df_four_factors_long.to_dict(orient="records")] if not df_four_factors_long.empty else [],
            "wide": [_serialize_record(item) for item in df_four_factors_wide.to_dict(orient="records")] if not df_four_factors_wide.empty else [],
        },
        "leaders": _build_leaders(df_players),
        "insight_flags": _build_insight_flags(df_players, game_context),
        "broadcast_storylines": list(game_context.get("broadcast_storylines") or []),
    }
    summary = _build_game_summary(game_context)
    return payload, summary


def run(repo_root: Path | None = None) -> tuple[dict, dict]:
    active_root = Path(repo_root) if repo_root else REPO_ROOT
    config_path = active_root / "config" / "game_config.yaml"
    config = load_config(config_path)
    output_dir = active_root / config.get("output_dir", "03_outputs")
    docs_data_dir = active_root / "docs" / "dashboard_data"
    docs_data_dir.mkdir(parents=True, exist_ok=True)

    payload, summary = build_dashboard_payload(output_dir)

    output_payload_path = output_dir / "dashboard_payload.json"
    output_summary_path = output_dir / "game_summary.json"
    docs_payload_path = docs_data_dir / "dashboard_payload.json"
    docs_summary_path = docs_data_dir / "game_summary.json"

    for path, data in (
        (output_payload_path, payload),
        (output_summary_path, summary),
        (docs_payload_path, payload),
        (docs_summary_path, summary),
    ):
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        console.print(f"[cyan]Wrote {path}[/cyan]")

    return payload, summary


if __name__ == "__main__":
    run()
