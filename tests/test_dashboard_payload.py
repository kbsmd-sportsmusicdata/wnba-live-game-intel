import importlib.util
import json
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

        class DummyConsole:
            def print(self, *_args, **_kwargs):
                return None

        console_mod.Console = DummyConsole
        rich_pkg.console = console_mod
        sys.modules["rich"] = rich_pkg
        sys.modules["rich.console"] = console_mod
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = load_module("build_dashboard_payload", ROOT / "02_process" / "build_dashboard_payload.py")


class DashboardPayloadHelpersTest(unittest.TestCase):
    def test_foul_status_thresholds(self):
        self.assertEqual(PAYLOAD.get_foul_status(2), "safe")
        self.assertEqual(PAYLOAD.get_foul_status(3), "watch")
        self.assertEqual(PAYLOAD.get_foul_status(4), "danger")
        self.assertEqual(PAYLOAD.get_foul_status(5), "foul_out")

    def test_ast_to_display_handles_zero_turnovers(self):
        ratio, display = PAYLOAD.compute_ast_to_fields(ast=5, tov=0)
        self.assertIsNone(ratio)
        self.assertEqual(display, "No TO")

        ratio, display = PAYLOAD.compute_ast_to_fields(ast=0, tov=0)
        self.assertEqual(ratio, 0)
        self.assertEqual(display, "0.0")

    def test_bench_impact_flag_and_tiers(self):
        self.assertTrue(PAYLOAD.get_bench_impact_flag(False, 8.0))
        self.assertFalse(PAYLOAD.get_bench_impact_flag(True, 12.0))
        self.assertEqual(PAYLOAD.get_impact_tier(19), "elite_impact")
        self.assertEqual(PAYLOAD.get_impact_tier(13), "strong_impact")
        self.assertEqual(PAYLOAD.get_efficiency_tier(0.66), "elite_efficiency")
        self.assertEqual(PAYLOAD.get_efficiency_tier(0.61), "strong_efficiency")
        self.assertEqual(PAYLOAD.get_efficiency_tier(0.53), "solid_efficiency")
        self.assertEqual(PAYLOAD.get_efficiency_tier(0.48), "low_efficiency")


class DashboardPayloadBuilderTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.output_dir = self.root / "03_outputs"
        self.docs_dir = self.root / "docs" / "dashboard_data"
        self.output_dir.mkdir(parents=True)
        self.docs_dir.mkdir(parents=True)

        player_derived = pd.DataFrame([
            {
                "game_id": "401856915",
                "fetched_at": "2026-06-13T00:00:00Z",
                "game_date": "2026-05-17T17:30Z",
                "game_status": "STATUS_FINAL",
                "period": 4,
                "clock": "0.0",
                "team_id": "17",
                "team_abbr": "LV",
                "home_away": "away",
                "player_id": "p1",
                "player_name": "Bench Spark",
                "position": "G",
                "starter": False,
                "active": True,
                "did_not_play": False,
                "minutes": 21,
                "pts": 16,
                "fgm": 6,
                "fga": 10,
                "tpm": 2,
                "tpa": 5,
                "ftm": 2,
                "fta": 2,
                "oreb": 1,
                "dreb": 4,
                "reb": 5,
                "ast": 5,
                "stl": 1,
                "blk": 0,
                "tov": 0,
                "pf": 3,
                "plus_minus": 7,
                "efg_pct": 0.7,
                "ts_pct": 0.68,
                "usg_pct": 0.31,
                "game_score": 18.5,
                "ast_pct": 0.35,
                "reb_pct": 0.12,
            },
            {
                "game_id": "401856915",
                "fetched_at": "2026-06-13T00:00:00Z",
                "game_date": "2026-05-17T17:30Z",
                "game_status": "STATUS_FINAL",
                "period": 4,
                "clock": "0.0",
                "team_id": "20",
                "team_abbr": "ATL",
                "home_away": "home",
                "player_id": "p2",
                "player_name": "Starter Anchor",
                "position": "F",
                "starter": True,
                "active": True,
                "did_not_play": False,
                "minutes": 33,
                "pts": 14,
                "fgm": 5,
                "fga": 14,
                "tpm": 1,
                "tpa": 4,
                "ftm": 3,
                "fta": 4,
                "oreb": 3,
                "dreb": 7,
                "reb": 10,
                "ast": 3,
                "stl": 2,
                "blk": 1,
                "tov": 4,
                "pf": 5,
                "plus_minus": -2,
                "efg_pct": 0.3929,
                "ts_pct": 0.5,
                "usg_pct": 0.29,
                "game_score": 9.2,
                "ast_pct": 0.17,
                "reb_pct": 0.21,
            },
        ])
        player_derived.to_csv(self.output_dir / "player_derived.csv", index=False)

        team_derived = pd.DataFrame([
            {
                "game_id": "401856915",
                "team_abbr": "LV",
                "team_name": "Las Vegas Aces",
                "home_away": "away",
                "pts": 85,
                "reb": 38,
                "pf": 23,
                "tov": 13,
                "efg_pct": 0.4932,
                "ts_pct": 0.571,
                "poss": 87.48,
                "pace": 89.38,
                "ortg": 97.17,
                "drtg": 95.96,
                "net_rtg": 1.21,
                "wpba_total_points": 6.0,
                "wpba_game_win_points": 3.0,
                "wpba_quarter_points": 3.0,
                "wpba_quarters_won": 3,
                "wpba_tied_quarters": 0,
                "wpba_scoreline_text": "LV 6.0, ATL 1.0",
                "four_factors_score": 0.2251,
            },
            {
                "game_id": "401856915",
                "team_abbr": "ATL",
                "team_name": "Atlanta Dream",
                "home_away": "home",
                "pts": 84,
                "reb": 45,
                "pf": 23,
                "tov": 13,
                "efg_pct": 0.4041,
                "ts_pct": 0.514,
                "poss": 91.28,
                "pace": 89.38,
                "ortg": 92.03,
                "drtg": 93.11,
                "net_rtg": -1.08,
                "wpba_total_points": 1.0,
                "wpba_game_win_points": 0.0,
                "wpba_quarter_points": 1.0,
                "wpba_quarters_won": 1,
                "wpba_tied_quarters": 0,
                "wpba_scoreline_text": "LV 6.0, ATL 1.0",
                "four_factors_score": 0.2532,
            },
        ])
        team_derived.to_csv(self.output_dir / "team_derived.csv", index=False)

        four_factors_long = pd.DataFrame([
            {"team_abbr": "LV", "efg_pct": 0.4932, "tov_rate": 0.1486, "oreb_pct": 0.15, "ftr": 0.2329},
            {"team_abbr": "ATL", "efg_pct": 0.4041, "tov_rate": 0.1424, "oreb_pct": 0.2558, "ftr": 0.5068},
        ])
        four_factors_long.to_csv(self.output_dir / "tier3_four_factors.csv", index=False)

        four_factors_wide = pd.DataFrame([
            {
                "factor": "efg_pct",
                "factor_label": "Effective FG%",
                "team_a_abbr": "LV",
                "team_b_abbr": "ATL",
                "team_a_value": 0.4932,
                "team_b_value": 0.4041,
                "differential": 0.0891,
                "winning_team": "LV",
            }
        ])
        four_factors_wide.to_csv(self.output_dir / "tier3_four_factors_wide.csv", index=False)

        game_context = {
            "game_id": "401856915",
            "game_date": "2026-05-17T17:30Z",
            "fetched_at": "2026-06-13T00:00:00Z",
            "game_status": "STATUS_FINAL",
            "is_final": True,
            "period": 4,
            "clock": "0.0",
            "minutes_elapsed": 40.0,
            "pace": 89.38,
            "home_team_abbr": "ATL",
            "away_team_abbr": "LV",
            "home_pts": 84,
            "away_pts": 85,
            "winner_team_abbr": "LV",
            "loser_team_abbr": "ATL",
            "final_margin": 1,
            "is_clutch_window": True,
            "is_close_final": True,
            "wpba": {
                "format_name": "WPBA 7-point system",
                "available_points": 7.0,
                "scoreline_text": "LV 6.0, ATL 1.0",
                "quarter_breakdown": [
                    {"quarter": 1, "winner_team_abbr": "LV"},
                    {"quarter": 2, "winner_team_abbr": "LV"},
                ],
            },
            "broadcast_storylines": [
                "WPBA scoreline: LV 6.0, ATL 1.0.",
                "LV banked 6.0 of 7 WPBA points and won 3 of 4 quarters plus the overall game.",
            ],
        }
        (self.output_dir / "game_context.json").write_text(json.dumps(game_context), encoding="utf-8")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_build_dashboard_payload_contains_required_top_level_sections(self):
        payload, summary = PAYLOAD.build_dashboard_payload(self.output_dir)

        self.assertIn("metadata", payload)
        self.assertIn("game", payload)
        self.assertIn("teams", payload)
        self.assertIn("players", payload)
        self.assertIn("leaders", payload)
        self.assertIn("four_factors", payload)
        self.assertIn("broadcast_storylines", payload)
        self.assertEqual(summary["winner_team_abbr"], "LV")
        self.assertEqual(summary["wpba_scoreline_text"], "LV 6.0, ATL 1.0")
        self.assertIn("last_updated", summary)

    def test_player_display_fields_and_leaders_are_enriched(self):
        payload, _summary = PAYLOAD.build_dashboard_payload(self.output_dir)
        bench_player = next(p for p in payload["players"] if p["player_name"] == "Bench Spark")
        starter_player = next(p for p in payload["players"] if p["player_name"] == "Starter Anchor")

        self.assertEqual(bench_player["ast_to_display"], "No TO")
        self.assertEqual(bench_player["foul_status"], "watch")
        self.assertEqual(bench_player["starter_label"], "Bench")
        self.assertTrue(bench_player["bench_impact_flag"])
        self.assertEqual(bench_player["impact_tier"], "elite_impact")
        self.assertEqual(bench_player["efficiency_tier"], "elite_efficiency")
        self.assertEqual(starter_player["foul_status"], "foul_out")

        self.assertIn("points", payload["leaders"])
        self.assertIn("bench_impact", payload["leaders"])
        self.assertEqual(payload["leaders"]["points"][0]["player_name"], "Bench Spark")
        self.assertEqual(payload["leaders"]["bench_impact"][0]["player_name"], "Bench Spark")

    def test_missing_optional_wide_four_factors_keeps_valid_payload_keys(self):
        (self.output_dir / "tier3_four_factors_wide.csv").unlink()
        payload, _summary = PAYLOAD.build_dashboard_payload(self.output_dir)
        self.assertIn("wide", payload["four_factors"])
        self.assertEqual(payload["four_factors"]["wide"], [])

    def test_fallback_player_sources_work_when_player_derived_missing(self):
        (self.output_dir / "player_derived.csv").unlink()
        pd.DataFrame([
            {
                "game_id": "401856915",
                "team_abbr": "LV",
                "player_id": "p1",
                "player_name": "Bench Spark",
                "starter": False,
                "minutes": 21,
                "pts": 16,
                "reb": 5,
                "ast": 5,
                "tov": 0,
                "pf": 3,
                "plus_minus": 7,
                "fga": 10,
                "fta": 2,
                "efg_pct": 0.7,
                "ts_pct": 0.68,
                "usg_pct": 0.31,
                "game_score": 18.5,
            }
        ]).to_csv(self.output_dir / "tier2_possession_player.csv", index=False)
        pd.DataFrame([
            {
                "game_id": "401856915",
                "team_abbr": "LV",
                "player_id": "p1",
                "player_name": "Bench Spark",
                "usg_pct": 0.31,
                "game_score": 18.5,
                "ast_pct": 0.35,
                "reb_pct": 0.12,
            }
        ]).to_csv(self.output_dir / "player_impact.csv", index=False)

        payload, _summary = PAYLOAD.build_dashboard_payload(self.output_dir)
        self.assertEqual(len(payload["players"]), 1)
        self.assertEqual(payload["players"][0]["player_name"], "Bench Spark")

    def test_missing_player_sources_fails_clearly(self):
        (self.output_dir / "player_derived.csv").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "player"):
            PAYLOAD.build_dashboard_payload(self.output_dir)

    def test_run_writes_outputs_to_pipeline_and_docs_locations(self):
        payload, summary = PAYLOAD.run(repo_root=self.root)

        self.assertTrue((self.output_dir / "dashboard_payload.json").exists())
        self.assertTrue((self.output_dir / "game_summary.json").exists())
        self.assertTrue((self.docs_dir / "dashboard_payload.json").exists())
        self.assertTrue((self.docs_dir / "game_summary.json").exists())
        self.assertEqual(payload["game"]["winner_team_abbr"], "LV")
        self.assertEqual(summary["game_status"], "STATUS_FINAL")


class DashboardDocsSmokeTest(unittest.TestCase):
    def test_dashboard_files_exist_and_fetch_local_json_contract(self):
        docs_root = ROOT / "docs"
        index_path = docs_root / "index.html"
        app_path = docs_root / "assets" / "js" / "app.js"
        charts_path = docs_root / "assets" / "js" / "charts.js"
        styles_path = docs_root / "assets" / "css" / "styles.css"
        contract_path = docs_root / "raw_data_contract.md"

        self.assertTrue(index_path.exists())
        self.assertTrue(app_path.exists())
        self.assertTrue(charts_path.exists())
        self.assertTrue(styles_path.exists())
        self.assertTrue(contract_path.exists())

        index_text = index_path.read_text(encoding="utf-8")
        app_text = app_path.read_text(encoding="utf-8")
        contract_text = contract_path.read_text(encoding="utf-8")

        self.assertIn("Live Game Intelligence Dashboard", index_text)
        self.assertIn("./dashboard_data/dashboard_payload.json", app_text)
        self.assertIn("./dashboard_data/game_summary.json", app_text)
        self.assertNotIn("site.api.espn.com", app_text)
        self.assertNotIn("docs.google.com", app_text)
        self.assertIn("03_outputs/raw_player.csv", contract_text)
        self.assertIn("03_outputs/raw_team.csv", contract_text)


if __name__ == "__main__":
    unittest.main()
