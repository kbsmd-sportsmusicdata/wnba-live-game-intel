import importlib.util
import json
import sys
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
SCHEMAS = load_module("schemas", ROOT / "01_ingest" / "schemas.py")
PLAYER_IMPACT = load_module("player_impact", ROOT / "02_process" / "player_impact.py")
GAME_CONTEXT = load_module("game_context", ROOT / "02_process" / "game_context.py")
DERIVE_OUTPUTS = load_module("derive_outputs", ROOT / "02_process" / "derive_outputs.py")


class SchemaModuleTest(unittest.TestCase):
    def test_validate_schema_uses_extracted_required_columns(self):
        df = pd.DataFrame([{col: 1 for col in SCHEMAS.REQUIRED_TEAM_COLS}])
        self.assertTrue(SCHEMAS.validate_schema(df, SCHEMAS.REQUIRED_TEAM_COLS, "raw_team"))

    def test_validate_schema_returns_false_on_missing_column(self):
        df = pd.DataFrame([{"game_id": "1"}])
        self.assertFalse(SCHEMAS.validate_schema(df, SCHEMAS.REQUIRED_PLAYER_COLS, "raw_player"))


class PlayerImpactTest(unittest.TestCase):
    def test_compute_player_impact_adds_core_metrics(self):
        df_players = pd.DataFrame([
            {
                "game_id": "1",
                "player_id": "p1",
                "player_name": "A Player",
                "team_abbr": "LV",
                "minutes": 30,
                "pts": 20,
                "fgm": 8,
                "fga": 15,
                "ftm": 2,
                "fta": 3,
                "oreb": 2,
                "dreb": 5,
                "reb": 7,
                "ast": 6,
                "stl": 1,
                "blk": 1,
                "pf": 2,
                "tov": 3,
                "usg_pct": 0.25,
            }
        ])
        df_teams = pd.DataFrame([
            {"team_abbr": "LV", "fgm": 30, "reb": 40, "minutes_elapsed": 40},
            {"team_abbr": "ATL", "fgm": 28, "reb": 35, "minutes_elapsed": 40},
        ])

        result = PLAYER_IMPACT.compute_player_impact(df_players, df_teams)

        self.assertAlmostEqual(result.loc[0, "usg_pct"], 0.25, places=4)
        self.assertAlmostEqual(result.loc[0, "game_score"], 17.3, places=2)
        self.assertAlmostEqual(result.loc[0, "ast_pct"], 0.4138, places=4)
        self.assertAlmostEqual(result.loc[0, "reb_pct"], 0.1244, places=4)

    def test_compute_player_impact_handles_zero_denominators(self):
        df_players = pd.DataFrame([
            {
                "game_id": "1",
                "player_id": "p1",
                "player_name": "B Player",
                "team_abbr": "LV",
                "minutes": 0,
                "pts": 0,
                "fgm": 0,
                "fga": 0,
                "ftm": 0,
                "fta": 0,
                "oreb": 0,
                "dreb": 0,
                "reb": 0,
                "ast": 0,
                "stl": 0,
                "blk": 0,
                "pf": 0,
                "tov": 0,
                "usg_pct": 0.0,
            }
        ])
        df_teams = pd.DataFrame([
            {"team_abbr": "LV", "fgm": 0, "reb": 0, "minutes_elapsed": 40},
            {"team_abbr": "ATL", "fgm": 0, "reb": 0, "minutes_elapsed": 40},
        ])

        result = PLAYER_IMPACT.compute_player_impact(df_players, df_teams)

        self.assertEqual(result.loc[0, "ast_pct"], 0.0)
        self.assertEqual(result.loc[0, "reb_pct"], 0.0)


class GameContextTest(unittest.TestCase):
    def test_build_game_context_handles_completed_game(self):
        df_raw = pd.DataFrame([
            {
                "game_id": "1",
                "game_date": "2026-06-12",
                "fetched_at": "2026-06-13T00:00:00Z",
                "game_status": "STATUS_FINAL",
                "period": 4,
                "clock": "0.0",
                "team_abbr": "ATL",
                "home_away": "home",
                "pts": 84,
                "pts_in_paint": 42,
                "pts_off_tov": 10,
                "second_chance_pts": 14,
                "tpm": 5,
                "ftm": 25,
                "ast": 15,
                "reb": 45,
                "largest_lead": 2,
            },
            {
                "game_id": "1",
                "game_date": "2026-06-12",
                "fetched_at": "2026-06-13T00:00:00Z",
                "game_status": "STATUS_FINAL",
                "period": 4,
                "clock": "0.0",
                "team_abbr": "LV",
                "home_away": "away",
                "pts": 85,
                "pts_in_paint": 38,
                "pts_off_tov": 16,
                "second_chance_pts": 9,
                "tpm": 10,
                "ftm": 13,
                "ast": 21,
                "reb": 38,
                "largest_lead": 19,
            },
        ])
        df_tier2 = pd.DataFrame([
            {"team_abbr": "ATL", "pace": 89.38, "minutes_elapsed": 40.0},
            {"team_abbr": "LV", "pace": 89.38, "minutes_elapsed": 40.0},
        ])

        summary_data = {
            "header": {
                "competitions": [
                    {
                        "competitors": [
                            {
                                "homeAway": "home",
                                "abbreviation": "ATL",
                                "score": "84",
                                "linescores": [
                                    {"displayValue": "23"},
                                    {"displayValue": "21"},
                                    {"displayValue": "19"},
                                    {"displayValue": "21"},
                                ],
                            },
                            {
                                "homeAway": "away",
                                "abbreviation": "LV",
                                "score": "85",
                                "linescores": [
                                    {"displayValue": "24"},
                                    {"displayValue": "27"},
                                    {"displayValue": "24"},
                                    {"displayValue": "10"},
                                ],
                            },
                        ]
                    }
                ]
            }
        }

        context = GAME_CONTEXT.build_game_context(df_raw, df_tier2, summary_data=summary_data)

        self.assertTrue(context["is_final"])
        self.assertEqual(context["winner_team_abbr"], "LV")
        self.assertEqual(context["final_margin"], 1)
        self.assertTrue(context["is_clutch_window"])
        self.assertTrue(context["is_close_final"])
        self.assertAlmostEqual(context["pace"], 89.38, places=2)
        self.assertEqual(context["wpba"]["home_total_points"], 1.0)
        self.assertEqual(context["wpba"]["away_total_points"], 6.0)
        self.assertEqual(context["wpba"]["points_leader_team_abbr"], "LV")
        self.assertEqual(context["wpba"]["home_quarters_won"], 1)
        self.assertEqual(context["wpba"]["away_quarters_won"], 3)
        self.assertEqual(len(context["wpba"]["quarter_breakdown"]), 4)
        self.assertIn("6.0 of 7 WPBA points", " ".join(context["broadcast_storylines"]))
        self.assertIn("won 3 of 4 quarters", " ".join(context["broadcast_storylines"]))
        self.assertIn("led assists 21-15", " ".join(context["broadcast_storylines"]))
        self.assertIn("nearly gave away a 19-point lead", " ".join(context["broadcast_storylines"]))
        self.assertIn("paint 42-38", " ".join(context["broadcast_storylines"]))
        self.assertIn("points off turnovers 16-10", " ".join(context["broadcast_storylines"]))
        self.assertIn("second-chance scoring 14-9", " ".join(context["broadcast_storylines"]))
        self.assertIn("3-point scoring share", " ".join(context["broadcast_storylines"]))
        self.assertIn("free-throw scoring share", " ".join(context["broadcast_storylines"]))

    def test_build_game_context_handles_in_progress_game(self):
        df_raw = pd.DataFrame([
            {
                "game_id": "1",
                "game_date": "2026-06-12",
                "fetched_at": "2026-06-13T00:00:00Z",
                "game_status": "STATUS_IN_PROGRESS",
                "period": 4,
                "clock": "4:30",
                "team_abbr": "ATL",
                "home_away": "home",
                "pts": 70,
            },
            {
                "game_id": "1",
                "game_date": "2026-06-12",
                "fetched_at": "2026-06-13T00:00:00Z",
                "game_status": "STATUS_IN_PROGRESS",
                "period": 4,
                "clock": "4:30",
                "team_abbr": "LV",
                "home_away": "away",
                "pts": 68,
            },
        ])

        context = GAME_CONTEXT.build_game_context(df_raw, None)

        self.assertFalse(context["is_final"])
        self.assertEqual(context["winner_team_abbr"], "ATL")
        self.assertTrue(context["is_clutch_window"])
        self.assertFalse(context["is_close_final"])

    def test_build_game_context_handles_wpba_tied_quarters(self):
        df_raw = pd.DataFrame([
            {
                "game_id": "2",
                "game_date": "2026-06-13",
                "fetched_at": "2026-06-13T00:00:00Z",
                "game_status": "STATUS_FINAL",
                "period": 4,
                "clock": "0.0",
                "team_abbr": "HOME",
                "home_away": "home",
                "pts": 64,
            },
            {
                "game_id": "2",
                "game_date": "2026-06-13",
                "fetched_at": "2026-06-13T00:00:00Z",
                "game_status": "STATUS_FINAL",
                "period": 4,
                "clock": "0.0",
                "team_abbr": "AWAY",
                "home_away": "away",
                "pts": 57,
            },
        ])
        summary_data = {
            "header": {
                "competitions": [
                    {
                        "competitors": [
                            {
                                "homeAway": "home",
                                "abbreviation": "HOME",
                                "score": "64",
                                "linescores": [
                                    {"displayValue": "20"},
                                    {"displayValue": "18"},
                                    {"displayValue": "10"},
                                    {"displayValue": "16"},
                                ],
                            },
                            {
                                "homeAway": "away",
                                "abbreviation": "AWAY",
                                "score": "57",
                                "linescores": [
                                    {"displayValue": "20"},
                                    {"displayValue": "15"},
                                    {"displayValue": "22"},
                                    {"displayValue": "16"},
                                ],
                            },
                        ]
                    }
                ]
            }
        }

        context = GAME_CONTEXT.build_game_context(df_raw, None, summary_data=summary_data)

        self.assertEqual(context["wpba"]["home_total_points"], 5.0)
        self.assertEqual(context["wpba"]["away_total_points"], 2.0)
        self.assertEqual(context["wpba"]["tied_quarters"], 2)
        self.assertIn("Two quarters ended tied", " ".join(context["broadcast_storylines"]))


class DerivedOutputMergeTest(unittest.TestCase):
    def test_merge_player_derived_prefers_player_impact_usg_pct(self):
        df_tier2_player = pd.DataFrame([
            {
                "game_id": "1",
                "player_id": "p1",
                "player_name": "A Player",
                "team_abbr": "LV",
                "minutes": 30,
                "pts": 20,
                "usg_pct": 0.20,
            }
        ])
        df_player_impact = pd.DataFrame([
            {
                "game_id": "1",
                "player_id": "p1",
                "player_name": "A Player",
                "team_abbr": "LV",
                "usg_pct": 0.25,
                "game_score": 17.3,
                "ast_pct": 0.41,
                "reb_pct": 0.12,
            }
        ])

        result = DERIVE_OUTPUTS.merge_player_derived(df_tier2_player, df_player_impact)

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result.loc[0, "usg_pct"], 0.25, places=4)
        self.assertIn("game_score", result.columns)

    def test_merge_team_derived_adds_flattened_context_fields(self):
        df_tier3_team = pd.DataFrame([
            {"team_abbr": "LV", "four_factors_score": 0.52},
            {"team_abbr": "ATL", "four_factors_score": 0.47},
        ])
        context = {
            "game_status": "STATUS_FINAL",
            "is_final": True,
            "final_margin": 1,
            "is_clutch_window": True,
            "is_close_final": True,
            "winner_team_abbr": "LV",
            "home_team_abbr": "ATL",
            "away_team_abbr": "LV",
            "wpba": {
                "home_total_points": 1.0,
                "away_total_points": 6.0,
                "home_quarters_won": 1,
                "away_quarters_won": 3,
                "tied_quarters": 0,
                "home_game_win_points": 0.0,
                "away_game_win_points": 3.0,
                "home_quarter_points": 1.0,
                "away_quarter_points": 3.0,
                "points_leader_team_abbr": "LV",
                "scoreline_text": "LV 6.0, ATL 1.0",
            },
        }

        result = DERIVE_OUTPUTS.merge_team_derived(df_tier3_team, context)

        self.assertEqual(len(result), 2)
        self.assertTrue(result.loc[result["team_abbr"] == "LV", "is_winner"].iloc[0])
        self.assertTrue(result.loc[result["team_abbr"] == "ATL", "is_home_team"].iloc[0])
        self.assertEqual(result["final_margin"].nunique(), 1)
        self.assertEqual(result.loc[result["team_abbr"] == "LV", "wpba_total_points"].iloc[0], 6.0)
        self.assertEqual(result.loc[result["team_abbr"] == "ATL", "wpba_quarters_won"].iloc[0], 1)
        self.assertEqual(result.loc[result["team_abbr"] == "LV", "wpba_scoreline_text"].iloc[0], "LV 6.0, ATL 1.0")


if __name__ == "__main__":
    unittest.main()
