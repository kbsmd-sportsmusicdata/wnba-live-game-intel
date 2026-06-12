import importlib.util
import tempfile
import unittest
from pathlib import Path

import pandas as pd


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parents[1]
GAME_IDS = load_module("game_id_reference", ROOT / "04_refresh" / "game_id_reference.py")


class GameIdReferenceTest(unittest.TestCase):
    def test_normalize_schedule_keeps_completed_and_future_games_with_ids(self):
        schedule = pd.DataFrame(
            [
                {
                    "game_id": 101,
                    "game_date": "2026-06-10",
                    "home_team_abbrev": "MIN",
                    "away_team_abbrev": "ATL",
                    "status_type_completed": True,
                },
                {
                    "game_id": 202,
                    "game_date": "2026-06-15",
                    "home_team_abbrev": "NY",
                    "away_team_abbrev": "SEA",
                    "status_type_completed": False,
                },
                {
                    "game_id": None,
                    "game_date": "2026-06-20",
                    "home_team_abbrev": "DAL",
                    "away_team_abbrev": "LV",
                    "status_type_completed": False,
                },
            ]
        )

        normalized = GAME_IDS.normalize_schedule_for_reference(schedule)

        self.assertEqual(
            list(normalized.columns),
            ["Date", "Team", "Opponent", "Game ID", "Status"],
        )
        self.assertEqual(len(normalized), 4)
        self.assertEqual(set(normalized["Game ID"]), {"101", "202"})
        self.assertEqual(
            normalized.to_dict(orient="records"),
            [
                {"Date": "2026-06-10", "Team": "ATL", "Opponent": "MIN", "Game ID": "101", "Status": "completed"},
                {"Date": "2026-06-10", "Team": "MIN", "Opponent": "ATL", "Game ID": "101", "Status": "completed"},
                {"Date": "2026-06-15", "Team": "NY", "Opponent": "SEA", "Game ID": "202", "Status": "upcoming"},
                {"Date": "2026-06-15", "Team": "SEA", "Opponent": "NY", "Game ID": "202", "Status": "upcoming"},
            ],
        )

    def test_build_markdown_table_is_human_readable(self):
        normalized = pd.DataFrame(
            [
                {"Date": "2026-06-10", "Team": "ATL", "Opponent": "MIN", "Game ID": "101", "Status": "completed"},
                {"Date": "2026-06-15", "Team": "SEA", "Opponent": "NY", "Game ID": "202", "Status": "upcoming"},
            ]
        )

        markdown = GAME_IDS.build_reference_markdown(normalized)

        self.assertIn("## Game ID Reference", markdown)
        self.assertIn("| Date | Team | Opponent | Game ID | Status |", markdown)
        self.assertIn("| 2026-06-10 | ATL | MIN | 101 | completed |", markdown)
        self.assertIn("| 2026-06-15 | SEA | NY | 202 | upcoming |", markdown)

    def test_build_markdown_note_when_schedule_file_is_missing(self):
        missing_path = ROOT / "data" / "raw" / "sportsdataverse" / "wnba_2026" / "schedule_2026.parquet"

        markdown = GAME_IDS.build_missing_schedule_markdown(missing_path)

        self.assertIn("## Game ID Reference", markdown)
        self.assertIn("generated from `schedule_2026.parquet`", markdown)
        self.assertIn("04_refresh/fetch_wnba_sportsdataverse_2026.py", markdown)
        self.assertIn(str(missing_path), markdown)

    def test_update_readme_section_replaces_marker_block(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            readme = Path(tmpdir) / "README.md"
            readme.write_text(
                "# Demo\n\n"
                "<!-- GAME_ID_REFERENCE_START -->\nold\n<!-- GAME_ID_REFERENCE_END -->\n",
                encoding="utf-8",
            )

            GAME_IDS.update_readme_section(readme, "new section")

            text = readme.read_text(encoding="utf-8")
            self.assertIn("new section", text)
            self.assertNotIn("\nold\n", text)


if __name__ == "__main__":
    unittest.main()
