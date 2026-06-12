from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = REPO_ROOT / "data" / "raw" / "sportsdataverse" / "wnba_2026"
DEFAULT_SCHEDULE_PATH = Path(
    os.getenv("SPORTSDATAVERSE_WNBA_2026_DATA_ROOT", str(DEFAULT_DATA_ROOT))
) / "schedule_2026.parquet"

README_PATH = REPO_ROOT / "README.md"
README_START_MARKER = "<!-- GAME_ID_REFERENCE_START -->"
README_END_MARKER = "<!-- GAME_ID_REFERENCE_END -->"


def _find_first_column(columns: Iterable[str], candidates: List[str]) -> str | None:
    normalized = {str(col).lower(): col for col in columns}
    for candidate in candidates:
        match = normalized.get(candidate.lower())
        if match:
            return match
    return None


def _status_label(value) -> str:
    if pd.isna(value):
        return "scheduled"
    return "completed" if bool(value) else "upcoming"


def _format_game_id(value) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(numeric)) if numeric.is_integer() else str(value)


def normalize_schedule_for_reference(schedule_df: pd.DataFrame) -> pd.DataFrame:
    if schedule_df.empty:
        return pd.DataFrame(columns=["Date", "Team", "Opponent", "Game ID"])

    game_id_col = _find_first_column(schedule_df.columns, ["game_id", "GameId"])
    date_col = _find_first_column(schedule_df.columns, ["game_date", "GameDate", "date"])
    home_col = _find_first_column(
        schedule_df.columns,
        ["home_team_abbrev", "home_team_abbreviation", "home_team", "home"],
    )
    away_col = _find_first_column(
        schedule_df.columns,
        ["away_team_abbrev", "away_team_abbreviation", "away_team", "away"],
    )
    status_col = _find_first_column(
        schedule_df.columns,
        ["status_type_completed", "completed", "is_completed"],
    )

    required = [game_id_col, date_col, home_col, away_col]
    if any(col is None for col in required):
        return pd.DataFrame(columns=["Date", "Team", "Opponent", "Game ID"])

    df = schedule_df.copy()
    df = df[df[game_id_col].notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=["Date", "Team", "Opponent", "Game ID"])

    df["Date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    df = df[df["Date"].notna()].copy()
    df["Date"] = df["Date"].astype(str)
    df["Game ID"] = df[game_id_col].apply(_format_game_id)
    df["Home Team"] = df[home_col].astype(str)
    df["Away Team"] = df[away_col].astype(str)

    rows = []
    for _, row in df.iterrows():
        status_value = _status_label(row[status_col]) if status_col else None
        rows.append(
            {
                "Date": row["Date"],
                "Team": row["Away Team"],
                "Opponent": row["Home Team"],
                "Game ID": row["Game ID"],
                "Status": status_value,
            }
        )
        rows.append(
            {
                "Date": row["Date"],
                "Team": row["Home Team"],
                "Opponent": row["Away Team"],
                "Game ID": row["Game ID"],
                "Status": status_value,
            }
        )

    normalized = pd.DataFrame(rows).sort_values(["Date", "Team", "Opponent"]).reset_index(drop=True)
    if status_col is None:
        normalized = normalized.drop(columns=["Status"])
    return normalized


def build_reference_markdown(reference_df: pd.DataFrame, schedule_path: Path = DEFAULT_SCHEDULE_PATH) -> str:
    if reference_df.empty:
        return build_missing_schedule_markdown(schedule_path)

    columns = list(reference_df.columns)
    lines = [
        "## Game ID Reference",
        "",
        "Generated from `schedule_2026.parquet` when available. Includes completed games and future games that already have assigned `game_id` values.",
        "",
        f"| {' | '.join(columns)} |",
        f"| {' | '.join(['---'] * len(columns))} |",
    ]
    for _, row in reference_df.iterrows():
        lines.append("| " + " | ".join(str(row[col]) for col in columns) + " |")
    return "\n".join(lines)


def build_missing_schedule_markdown(schedule_path: Path) -> str:
    return "\n".join(
        [
            "## Game ID Reference",
            "",
            "This section is generated from `schedule_2026.parquet` when that file is available locally.",
            "",
            f"- Expected schedule path: `{schedule_path}`",
            "- Refresh source: `04_refresh/fetch_wnba_sportsdataverse_2026.py`",
            "- When the schedule parquet is present, regenerate this section to list completed and future games that already have assigned `game_id` values.",
        ]
    )


def build_markdown_from_schedule_path(schedule_path: Path = DEFAULT_SCHEDULE_PATH) -> str:
    if not schedule_path.exists():
        return build_missing_schedule_markdown(schedule_path)
    schedule_df = pd.read_parquet(schedule_path)
    return build_reference_markdown(normalize_schedule_for_reference(schedule_df), schedule_path)


def update_readme_section(readme_path: Path, section_markdown: str) -> None:
    text = readme_path.read_text(encoding="utf-8")
    if README_START_MARKER not in text or README_END_MARKER not in text:
        raise ValueError(
            f"Required markers '{README_START_MARKER}' and/or '{README_END_MARKER}' "
            f"not found in {readme_path}"
        )
    start = text.index(README_START_MARKER)
    end = text.index(README_END_MARKER) + len(README_END_MARKER)
    replacement = f"{README_START_MARKER}\n{section_markdown}\n{README_END_MARKER}"
    updated = text[:start] + replacement + text[end:]
    readme_path.write_text(updated, encoding="utf-8")


def main() -> None:
    markdown = build_markdown_from_schedule_path()
    update_readme_section(README_PATH, markdown)
    print(markdown)


if __name__ == "__main__":
    main()
