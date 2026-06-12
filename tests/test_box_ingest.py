import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

import pandas as pd


def load_module(name: str, path: Path):
    if "yaml" not in sys.modules:
        yaml_stub = types.SimpleNamespace(safe_load=lambda *_args, **_kwargs: {})
        sys.modules["yaml"] = yaml_stub
    if "rich" not in sys.modules:
        rich_pkg = types.ModuleType("rich")
        console_mod = types.ModuleType("rich.console")
        table_mod = types.ModuleType("rich.table")

        class DummyConsole:
            def print(self, *_args, **_kwargs):
                return None

            def rule(self, *_args, **_kwargs):
                return None

        class DummyTable:
            def __init__(self, *args, **kwargs):
                self.rows = []

            def add_column(self, *_args, **_kwargs):
                return None

            def add_row(self, *args, **_kwargs):
                self.rows.append(args)

        console_mod.Console = DummyConsole
        table_mod.Table = DummyTable
        rich_pkg.console = console_mod
        rich_pkg.table = table_mod
        sys.modules["rich"] = rich_pkg
        sys.modules["rich.console"] = console_mod
        sys.modules["rich.table"] = table_mod
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parents[1]
BOX_INGEST = load_module("box_ingest", ROOT / "01_ingest" / "box_ingest.py")


class BoxIngestParsingTest(unittest.TestCase):
    def test_parse_boxscore_maps_team_and_player_rows(self):
        sample = {
            "header": {
                "competitions": [
                    {
                        "date": "2026-05-17T17:30Z",
                        "status": {
                            "type": {"name": "STATUS_FINAL"},
                            "period": 4,
                            "displayClock": "0:00",
                        },
                        "competitors": [
                            {"id": "17", "homeAway": "away"},
                            {"id": "20", "homeAway": "home"},
                        ],
                    }
                ]
            },
            "boxscore": {
                "teams": [
                    {
                        "team": {"id": "17", "displayName": "Las Vegas Aces", "abbreviation": "LV"},
                        "statistics": [
                            {"name": "points", "displayValue": "85"},
                            {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "31-73"},
                            {"name": "fieldGoalPct", "displayValue": "42.5"},
                            {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "10-27"},
                            {"name": "threePointFieldGoalPct", "displayValue": "37.0"},
                            {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "13-17"},
                            {"name": "freeThrowPct", "displayValue": "76.5"},
                            {"name": "offensiveRebounds", "displayValue": "6"},
                            {"name": "defensiveRebounds", "displayValue": "32"},
                            {"name": "rebounds", "displayValue": "38"},
                            {"name": "assists", "displayValue": "21"},
                            {"name": "steals", "displayValue": "5"},
                            {"name": "blocks", "displayValue": "8"},
                            {"name": "turnovers", "displayValue": "13"},
                            {"name": "fouls", "displayValue": "23"},
                        ],
                    },
                    {
                        "team": {"id": "20", "displayName": "Atlanta Dream", "abbreviation": "ATL"},
                        "statistics": [
                            {"name": "points", "displayValue": "84"},
                            {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "27-73"},
                            {"name": "fieldGoalPct", "displayValue": "37.0"},
                            {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "5-23"},
                            {"name": "threePointFieldGoalPct", "displayValue": "21.7"},
                            {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "25-37"},
                            {"name": "freeThrowPct", "displayValue": "67.6"},
                            {"name": "offensiveRebounds", "displayValue": "11"},
                            {"name": "defensiveRebounds", "displayValue": "34"},
                            {"name": "rebounds", "displayValue": "45"},
                            {"name": "assists", "displayValue": "15"},
                            {"name": "steals", "displayValue": "9"},
                            {"name": "blocks", "displayValue": "5"},
                            {"name": "turnovers", "displayValue": "13"},
                            {"name": "fouls", "displayValue": "23"},
                        ],
                    },
                ],
                "players": [
                    {
                        "team": {"id": "17", "abbreviation": "LV"},
                        "statistics": [
                            {
                                "keys": [
                                    {"name": "minutes"},
                                    {"name": "fieldGoalsMade-fieldGoalsAttempted"},
                                    {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted"},
                                    {"name": "freeThrowsMade-freeThrowsAttempted"},
                                    {"name": "offensiveRebounds"},
                                    {"name": "defensiveRebounds"},
                                    {"name": "rebounds"},
                                    {"name": "assists"},
                                    {"name": "steals"},
                                    {"name": "blocks"},
                                    {"name": "turnovers"},
                                    {"name": "fouls"},
                                    {"name": "plusMinus"},
                                    {"name": "points"},
                                ],
                                "athletes": [
                                    {
                                        "athlete": {
                                            "id": "3149391",
                                            "displayName": "A'ja Wilson",
                                            "position": {"abbreviation": "C"},
                                        },
                                        "starter": True,
                                        "active": True,
                                        "didNotPlay": False,
                                        "stats": [
                                            "31:00",
                                            "6-12",
                                            "2-2",
                                            "6-7",
                                            "0",
                                            "6",
                                            "6",
                                            "1",
                                            "0",
                                            "2",
                                            "4",
                                            "5",
                                            "-3",
                                            "20",
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        }

        players, teams = BOX_INGEST.parse_boxscore(
            sample,
            game_id="401856915",
            fetched_at="2026-06-12T00:00:00+00:00",
        )

        self.assertEqual(len(teams), 2)
        self.assertEqual(len(players), 1)
        self.assertEqual(set(teams["team_abbr"]), {"LV", "ATL"})
        self.assertEqual(teams.loc[teams["team_abbr"] == "LV", "home_away"].iloc[0], "away")
        self.assertEqual(players.loc[0, "player_name"], "A'ja Wilson")
        self.assertEqual(players.loc[0, "minutes"], 31.0)
        self.assertEqual(players.loc[0, "pts"], 20)
        self.assertTrue(BOX_INGEST.validate_schema(players, BOX_INGEST.REQUIRED_PLAYER_COLS, "raw_player"))
        self.assertTrue(BOX_INGEST.validate_schema(teams, BOX_INGEST.REQUIRED_TEAM_COLS, "raw_team"))

    def test_parse_boxscore_accepts_string_stat_keys_from_live_payloads(self):
        sample = {
            "header": {
                "competitions": [
                    {
                        "date": "2026-05-17T17:30Z",
                        "status": {
                            "type": {"name": "STATUS_FINAL"},
                            "period": 4,
                            "displayClock": "0:00",
                        },
                        "competitors": [
                            {"id": "17", "homeAway": "away"},
                            {"id": "20", "homeAway": "home"},
                        ],
                    }
                ]
            },
            "boxscore": {
                "teams": [
                    {
                        "team": {"id": "17", "displayName": "Las Vegas Aces", "abbreviation": "LV"},
                        "statistics": [
                            {"name": "points", "displayValue": "85"},
                            {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "31-73"},
                            {"name": "fieldGoalPct", "displayValue": "42.5"},
                            {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "10-27"},
                            {"name": "threePointFieldGoalPct", "displayValue": "37.0"},
                            {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "13-17"},
                            {"name": "freeThrowPct", "displayValue": "76.5"},
                            {"name": "offensiveRebounds", "displayValue": "6"},
                            {"name": "defensiveRebounds", "displayValue": "32"},
                            {"name": "rebounds", "displayValue": "38"},
                            {"name": "assists", "displayValue": "21"},
                            {"name": "steals", "displayValue": "5"},
                            {"name": "blocks", "displayValue": "8"},
                            {"name": "turnovers", "displayValue": "13"},
                            {"name": "fouls", "displayValue": "23"},
                        ],
                    }
                ],
                "players": [
                    {
                        "team": {"id": "17", "abbreviation": "LV"},
                        "statistics": [
                            {
                                "keys": [
                                    "minutes",
                                    "points",
                                    "fieldGoalsMade-fieldGoalsAttempted",
                                    "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
                                    "freeThrowsMade-freeThrowsAttempted",
                                    "offensiveRebounds",
                                    "defensiveRebounds",
                                    "rebounds",
                                    "assists",
                                    "steals",
                                    "blocks",
                                    "turnovers",
                                    "fouls",
                                    "plusMinus",
                                ],
                                "athletes": [
                                    {
                                        "athlete": {
                                            "id": "3149391",
                                            "displayName": "A'ja Wilson",
                                            "position": {"abbreviation": "C"},
                                        },
                                        "starter": True,
                                        "active": True,
                                        "didNotPlay": False,
                                        "stats": [
                                            "31:00",
                                            "20",
                                            "6-12",
                                            "2-2",
                                            "6-7",
                                            "0",
                                            "6",
                                            "6",
                                            "1",
                                            "0",
                                            "2",
                                            "4",
                                            "5",
                                            "-3",
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        }

        players, teams = BOX_INGEST.parse_boxscore(
            sample,
            game_id="401856915",
            fetched_at="2026-06-12T00:00:00+00:00",
        )

        self.assertEqual(len(players), 1)
        self.assertEqual(players.loc[0, "player_name"], "A'ja Wilson")
        self.assertEqual(players.loc[0, "pts"], 20)
        self.assertEqual(players.loc[0, "fgm"], 6)
        self.assertEqual(players.loc[0, "tpm"], 2)
        self.assertEqual(players.loc[0, "team_abbr"], "LV")
        self.assertEqual(len(teams), 1)

    def test_write_outputs_writes_expected_raw_files(self):
        players = pd.DataFrame([{"player_name": "Example", "pts": 12}])
        teams = pd.DataFrame([{"team_abbr": "LV", "pts": 85}])

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            BOX_INGEST.write_outputs(players, teams, output_dir)

            player_path = output_dir / "raw_player.csv"
            team_path = output_dir / "raw_team.csv"

            self.assertTrue(player_path.exists())
            self.assertTrue(team_path.exists())
            self.assertEqual(pd.read_csv(player_path).loc[0, "player_name"], "Example")
            self.assertEqual(pd.read_csv(team_path).loc[0, "team_abbr"], "LV")


if __name__ == "__main__":
    unittest.main()
