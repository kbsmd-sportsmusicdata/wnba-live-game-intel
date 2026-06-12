"""
fetch_wnba_sportsdataverse_2026.py

Non-interactive 2026 WNBA parquet downloader for SportsDataverse GitHub releases.
This script is intended for local runs and GitHub Actions.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


SEASON = "2026"
BASE_RELEASE_URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DATA_ROOT = REPO_ROOT / "data" / "raw" / "sportsdataverse" / "wnba_2026"
DATA_ROOT = Path(os.getenv("SPORTSDATAVERSE_WNBA_2026_DATA_ROOT", str(DEFAULT_DATA_ROOT)))
RUN_LOG_PATH = DATA_ROOT / "run_logs" / "download_manifest_2026.json"

GAME_LEVEL_DATASET_NAMES = [
    "schedule_2026.parquet",
    "player_box_2026.parquet",
    "team_box_2026.parquet",
    "player_game_logs_2026.parquet",
    "shots_2026.parquet",
    "game_rosters_2026.parquet",
    "wnba_pbp_2026.parquet",
    "espn_pbp_2026.parquet",
]

TEAM_TOTAL_DATASET_NAMES = [
    "team_season_stats_2026.parquet",
    "standings_2026.parquet",
]


def espn(tag: str, filename: str) -> str:
    return f"{BASE_RELEASE_URL}/{tag}/{filename}"


def wnba(tag: str, filename: str) -> str:
    return f"{BASE_RELEASE_URL}/{tag}/{filename}"


def build_2026_file_list() -> Dict[str, Dict[str, str]]:
    year = SEASON
    return {
        f"player_box_{year}.parquet": {
            "url": espn("espn_wnba_player_boxscores", f"player_box_{year}.parquet"),
            "size_note": "~50-170 KB",
            "source": "ESPN",
        },
        f"team_box_{year}.parquet": {
            "url": espn("espn_wnba_team_boxscores", f"team_box_{year}.parquet"),
            "size_note": "~32-54 KB",
            "source": "ESPN",
        },
        f"player_game_logs_{year}.parquet": {
            "url": wnba("wnba_stats_player_game_logs", f"player_game_logs_{year}.parquet"),
            "size_note": "~22-126 KB",
            "source": "WNBA.com",
        },
        f"player_season_stats_{year}.parquet": {
            "url": espn("espn_wnba_player_season_stats", f"player_season_stats_{year}.parquet"),
            "size_note": "~57-61 KB",
            "source": "ESPN",
        },
        f"team_season_stats_{year}.parquet": {
            "url": espn("espn_wnba_team_season_stats", f"team_season_stats_{year}.parquet"),
            "size_note": "~16-18 KB",
            "source": "ESPN",
        },
        f"standings_{year}.parquet": {
            "url": espn("espn_wnba_standings", f"standings_{year}.parquet"),
            "size_note": "~15-16 KB",
            "source": "ESPN",
        },
        f"shots_{year}.parquet": {
            "url": espn("espn_wnba_shots", f"shots_{year}.parquet"),
            "size_note": "~58-463 KB",
            "source": "ESPN",
        },
        f"game_rosters_{year}.parquet": {
            "url": espn("espn_wnba_game_rosters", f"game_rosters_{year}.parquet"),
            "size_note": "~32-70 KB",
            "source": "ESPN",
        },
        f"lineups_{year}.parquet": {
            "url": wnba("wnba_stats_lineups", f"lineups_{year}.parquet"),
            "size_note": "~282 KB",
            "source": "WNBA.com",
        },
        f"wnba_pbp_{year}.parquet": {
            "url": wnba("wnba_stats_pbp", f"play_by_play_{year}.parquet"),
            "size_note": "~367 KB",
            "source": "WNBA.com",
        },
        f"espn_pbp_{year}.parquet": {
            "url": espn("espn_wnba_pbp", f"play_by_play_{year}.parquet"),
            "size_note": "~633 KB",
            "source": "ESPN",
        },
        f"schedule_{year}.parquet": {
            "url": espn("espn_wnba_schedules", f"wnba_schedule_{year}.parquet"),
            "size_note": "~91-97 KB",
            "source": "ESPN",
        },
    }


def ensure_dirs(data_root: Path, manifest_path: Path) -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json_dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(stable_json_dumps(payload), encoding="utf-8")
    tmp_path.replace(path)


def format_date_value(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def build_completed_schedule_lookup(schedule_df: pd.DataFrame) -> Dict[Any, str]:
    if schedule_df.empty or "status_type_completed" not in schedule_df.columns or "game_id" not in schedule_df.columns:
        return {}
    completed = schedule_df[schedule_df["status_type_completed"] == True].copy()  # noqa: E712
    if completed.empty:
        return {}
    completed["game_date_iso"] = pd.to_datetime(completed["game_date"], errors="coerce").dt.date.astype(str)
    completed = completed.dropna(subset=["game_date_iso"])
    return dict(zip(completed["game_id"].astype(str), completed["game_date_iso"]))


def latest_completed_game_date(dataset_name: str, df: pd.DataFrame, schedule_lookup: Dict[Any, str]) -> Optional[str]:
    if df.empty:
        return None
    if dataset_name == "schedule_2026.parquet":
        if "status_type_completed" not in df.columns or "game_date" not in df.columns:
            return None
        completed = df[df["status_type_completed"] == True].copy()  # noqa: E712
        if completed.empty:
            return None
        dates = pd.to_datetime(completed["game_date"], errors="coerce").dropna()
        return format_date_value(dates.max()) if not dates.empty else None

    if "game_date" in df.columns:
        dates = pd.to_datetime(df["game_date"], errors="coerce").dropna()
        if not dates.empty:
            return format_date_value(dates.max())

    if "game_id" in df.columns and schedule_lookup:
        mapped = [schedule_lookup.get(str(game_id)) for game_id in df["game_id"].dropna().unique()]
        mapped = [value for value in mapped if value]
        return max(mapped) if mapped else None

    return None


def summarize_game_level_datasets(dataset_frames: Dict[str, pd.DataFrame]) -> List[Dict[str, Optional[str]]]:
    schedule_df = dataset_frames.get("schedule_2026.parquet", pd.DataFrame())
    schedule_lookup = build_completed_schedule_lookup(schedule_df)
    summaries = []
    for dataset_name in GAME_LEVEL_DATASET_NAMES:
        df = dataset_frames.get(dataset_name)
        if df is None:
            continue
        summaries.append(
            {
                "dataset": dataset_name,
                "latest_completed_game_date": latest_completed_game_date(dataset_name, df, schedule_lookup),
            }
        )
    return summaries


def summarize_team_total_games(dataset_frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []

    team_season_stats = dataset_frames.get("team_season_stats_2026.parquet")
    if (
        team_season_stats is not None
        and not team_season_stats.empty
        and {"stat_label", "value"}.issubset(team_season_stats.columns)
    ):
        key_col = "team_id" if "team_id" in team_season_stats.columns else "team_abbreviation"
        label_col = "team_abbreviation" if "team_abbreviation" in team_season_stats.columns else key_col
        selected_cols = list(dict.fromkeys([key_col, label_col, "value"]))
        gp = team_season_stats[team_season_stats["stat_label"].astype(str) == "GP"][selected_cols].copy()
        gp["_team_key"] = gp[key_col].astype(str)
        gp["team"] = gp[label_col].astype(str)
        gp["team_season_stats_gp"] = pd.to_numeric(gp["value"], errors="coerce").astype("Int64")
        frames.append(gp[["_team_key", "team", "team_season_stats_gp"]])

    standings = dataset_frames.get("standings_2026.parquet")
    if (
        standings is not None
        and not standings.empty
        and {"stat_abbreviation", "value"}.issubset(standings.columns)
    ):
        key_col = "team_id" if "team_id" in standings.columns else "team_abbreviation"
        label_col = "team_abbreviation" if "team_abbreviation" in standings.columns else key_col
        selected_cols = list(dict.fromkeys([key_col, label_col, "stat_abbreviation", "value"]))
        wl = standings[standings["stat_abbreviation"].astype(str).isin(["W", "L"])][selected_cols].copy()
        if not wl.empty:
            wl["_team_key"] = wl[key_col].astype(str)
            wl["team"] = wl[label_col].astype(str)
            pivot = wl.pivot_table(
                index=["_team_key", "team"],
                columns="stat_abbreviation",
                values="value",
                aggfunc="first",
            ).reset_index()
            pivot["standings_gp"] = (
                pd.to_numeric(pivot.get("W"), errors="coerce").fillna(0)
                + pd.to_numeric(pivot.get("L"), errors="coerce").fillna(0)
            ).astype("Int64")
            frames.append(pivot[["_team_key", "team", "standings_gp"]])

    if not frames:
        return pd.DataFrame(columns=["team"])

    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="_team_key", how="outer", suffixes=("", "_other"))
        if "team_other" in merged.columns:
            merged["team"] = merged["team_other"].fillna(merged["team"])
            merged = merged.drop(columns=["team_other"])

    return merged.sort_values("team").reset_index(drop=True)


def build_workflow_summary_markdown(
    *,
    dataset_frames: Dict[str, pd.DataFrame],
    run_label: str,
) -> str:
    lines = [
        "## SportsDataverse WNBA 2026 Summary",
        "",
        f"- Run label: `{run_label}`",
        f"- Output root: `{DATA_ROOT}`",
        "",
        "### Latest Completed Game Date By Game-Level Dataset",
        "",
        "| Dataset | Latest Completed Game Date |",
        "| --- | --- |",
    ]

    for item in summarize_game_level_datasets(dataset_frames):
        lines.append(
            f"| {item['dataset']} | {item['latest_completed_game_date'] or 'not available'} |"
        )

    lines.extend(["", "### Team Games By Totals Dataset", ""])
    games_df = summarize_team_total_games(dataset_frames)
    if games_df.empty:
        lines.append("No team totals datasets were available for summary.")
        return "\n".join(lines)

    lines.extend(
        [
            "| Team | Team Season Stats GP | Standings GP |",
            "| --- | ---: | ---: |",
        ]
    )
    for _, row in games_df.iterrows():
        lines.append(
            f"| {row['team']} | {row.get('team_season_stats_gp', pd.NA)} | {row.get('standings_gp', pd.NA)} |"
        )
    return "\n".join(lines)


def write_github_step_summary(markdown: str) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write(markdown)
        fh.write("\n\n")


def download_one(filename: str, file_info: Dict[str, str], data_root: Path) -> tuple[Dict[str, Any], pd.DataFrame]:
    output_path = data_root / filename
    df = pd.read_parquet(file_info["url"])
    df.to_parquet(output_path, index=False)
    return (
        {
            "filename": filename,
            "source": file_info["source"],
            "url": file_info["url"],
            "size_note": file_info["size_note"],
            "success": True,
            "row_count": int(len(df)),
            "column_count": int(df.shape[1]),
            "sha256": sha256_file(output_path),
        },
        df,
    )


def download_all(
    *,
    file_map: Dict[str, Dict[str, str]] | None = None,
    data_root: Path = DATA_ROOT,
    manifest_path: Path = RUN_LOG_PATH,
) -> Dict[str, Any]:
    ensure_dirs(data_root, manifest_path)
    resolved_files = file_map or build_2026_file_list()
    results = []
    dataset_frames: Dict[str, pd.DataFrame] = {}

    for filename in sorted(resolved_files):
        file_info = resolved_files[filename]
        file_result, df = download_one(filename, file_info, data_root)
        results.append(file_result)
        dataset_frames[filename] = df

    game_level_summary = summarize_game_level_datasets(dataset_frames)
    team_games_summary = summarize_team_total_games(dataset_frames)

    manifest = {
        "season": SEASON,
        "output_dir": str(data_root),
        "file_count": len(results),
        "files": results,
        "workflow_summary": {
            "game_level_datasets": game_level_summary,
            "team_games_by_dataset": team_games_summary.to_dict(orient="records"),
        },
    }
    save_json(manifest_path, manifest)
    write_github_step_summary(
        build_workflow_summary_markdown(
            dataset_frames=dataset_frames,
            run_label=f"{SEASON} manifest",
        )
    )
    return manifest


def main() -> None:
    manifest = download_all()
    print(f"Downloaded {manifest['file_count']} SportsDataverse WNBA {SEASON} parquet files to {DATA_ROOT}")


if __name__ == "__main__":
    main()
