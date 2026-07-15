import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from analysis.analyzer import (
    _build_death_objective_drill,
    _build_post_item_windows,
    _build_review_findings,
    _item_detail,
    analyze_match,
    get_hero_name,
)
from analysis.formula_engine import build_formula_review, select_formula_findings
import db.schema as schema


def _generate_fallback_analysis(analysis, *_args):
    return build_formula_review(analysis)


class ReportQualityTests(unittest.TestCase):
    def _base_match(self):
        return {
            "match_id": 123,
            "account_id": 173776719,
            "hero_id": 1,
            "player_slot": 1,
            "is_radiant": 1,
            "radiant_win": 1,
            "duration": 2100,
            "kills": 8,
            "deaths": 6,
            "assists": 10,
            "gold_per_min": 540,
            "xp_per_min": 620,
            "hero_damage": 18000,
            "tower_damage": 2200,
            "hero_healing": 0,
            "last_hits": 180,
            "denies": 11,
            "level": 22,
            "gold": 900,
            "net_worth": 18800,
            "item_0": 160,
            "item_1": 116,
            "item_2": 145,
            "item_3": 0,
            "item_4": 0,
            "item_5": 0,
            "ability_upgrades": json.dumps([5003, 7314, 5004]),
        }

    def test_hero_names_follow_opendota_hero_ids(self):
        expected = {
            9: "Mirana",
            49: "Dragon Knight",
            55: "Dark Seer",
            69: "Doom",
            72: "Gyrocopter",
            82: "Meepo",
            135: "Dawnbreaker",
            155: "Largo",
        }

        self.assertEqual({hero_id: get_hero_name(hero_id) for hero_id in expected}, expected)

    def test_current_item_ids_resolve_to_real_names(self):
        expected = {
            235: "Octarine Core",
            598: "Mage Slayer",
            600: "Overwhelming Blink",
            1097: "Disperser",
            1852: "Essence Distiller",
            1856: "Crella's Crozier",
        }

        for item_id, item_name in expected.items():
            self.assertEqual(_item_detail(item_id)["name"], item_name)

    def test_high_gpm_long_loss_does_not_invent_missing_push_conversion(self):
        findings = _build_review_findings({
            "is_win": False,
            "duration_min": 52.8,
            "farm": {"gpm": 1030, "last_hits": 727},
            "derived": {"lh_per_min": 13.77, "deaths_per_10_min": 1.7},
            "role_profile": {"id": "pos1", "lane_farm_sensitive": True},
            "timeline": {
                "available": True,
                "ten_min_last_hits": 56,
                "low_efficiency_windows": [],
                "tower_windows": [{"label": "推塔窗口 45-50分钟", "total": 11607}],
            },
            "events": {
                "deaths": [],
                "purchases": [],
                "objectives": [],
                "has_objective_log": False,
            },
            "kda": {"deaths": 0},
        })

        self.assertNotIn("closing", [item["category"] for item in findings])

    def test_manta_uses_five_minute_farm_window_not_two_minute_fight_window(self):
        windows = _build_post_item_windows(
            {
                "key_purchases": [{
                    "item_name": "Manta Style",
                    "time": 600,
                    "minute": 10.0,
                }],
                "kills": [],
                "assists": [],
            },
            {
                "last_hits_by_minute": [5] * 30,
                "gold_by_minute": [650] * 30,
                "tower_damage_by_minute": [0] * 30,
            },
        )

        self.assertEqual(windows[0]["window_type"], "farm_acceleration")
        self.assertEqual(windows[0]["lh_gain"], 25)
        self.assertEqual(windows[0]["avg_gpm"], 650.0)

    def test_farm_item_window_is_not_scored_without_complete_lh_and_gold_minutes(self):
        windows = _build_post_item_windows(
            {
                "key_purchases": [{
                    "item_name": "Manta Style",
                    "time": 600,
                    "minute": 10.0,
                }],
            },
            {
                "last_hits_by_minute": [5] * 30,
                "gold_by_minute": [],
            },
        )

        self.assertFalse(windows[0]["evaluable"])
        self.assertEqual(windows[0]["classification"], "insufficient_data")
        self.assertIsNone(windows[0]["lh_gain"])
        self.assertIsNone(windows[0]["avg_gpm"])

    def test_farm_item_window_is_not_scored_when_match_ends_before_full_window(self):
        windows = _build_post_item_windows(
            {
                "key_purchases": [{
                    "item_name": "Manta Style",
                    "time": 28 * 60,
                    "minute": 28.0,
                }],
            },
            {
                "last_hits_by_minute": [5] * 30,
                "gold_by_minute": [650] * 30,
            },
        )

        self.assertFalse(windows[0]["evaluable"])
        self.assertEqual(windows[0]["classification"], "insufficient_data")

    def test_analysis_builds_real_match_metadata_from_opendota(self):
        match = self._base_match()
        match.update({
            "match_id": 8867002237,
            "hero_id": 9,
            "player_slot": 2,
            "start_time": 1782466505,
            "duration": 2894,
            "radiant_score": 43,
            "dire_score": 39,
            "radiant_win": 0,
        })
        opendota_data = {
            "players": [
                {"account_id": 173776719, "hero_id": 9, "player_slot": 2},
                {"account_id": 11, "hero_id": 8, "player_slot": 0},
                {"account_id": 12, "hero_id": 17, "player_slot": 1},
                {"account_id": 13, "hero_id": 100, "player_slot": 3},
                {"account_id": 14, "hero_id": 64, "player_slot": 4},
                {"account_id": 21, "hero_id": 75, "player_slot": 128},
                {"account_id": 22, "hero_id": 16, "player_slot": 129},
                {"account_id": 23, "hero_id": 2, "player_slot": 130},
                {"account_id": 24, "hero_id": 155, "player_slot": 131},
                {"account_id": 25, "hero_id": 6, "player_slot": 132},
            ]
        }

        result = analyze_match(match, opendota_data=opendota_data)
        metadata = result["match_metadata"]

        self.assertEqual(result["hero_name"], "Mirana")
        self.assertEqual(metadata["ended_at"], "2026-06-26T10:23:19Z")
        self.assertEqual(metadata["duration_seconds"], 2894)
        self.assertFalse(metadata["is_win"])
        self.assertEqual(metadata["kda"], {"kills": 8, "deaths": 6, "assists": 10})
        self.assertEqual(metadata["score"], {"team": 43, "enemy": 39})
        self.assertEqual(metadata["hero"]["slug"], "mirana")
        self.assertEqual([hero["name"] for hero in metadata["allies"]], [
            "Juggernaut", "Storm Spirit", "Mirana", "Tusk", "Jakiro",
        ])
        self.assertEqual([hero["name"] for hero in metadata["enemies"]], [
            "Silencer", "Sand King", "Axe", "Largo", "Drow Ranger",
        ])

    def test_missing_or_invalid_player_slots_do_not_pollute_lineups(self):
        match = self._base_match()
        opendota_data = {
            "players": [
                {"account_id": 173776719, "hero_id": 1, "player_slot": 1},
                {"account_id": 11, "hero_id": 2, "player_slot": 0},
                {"account_id": 12, "hero_id": 3},
                {"account_id": 13, "hero_id": 4, "player_slot": 99},
                {"account_id": 21, "hero_id": 5, "player_slot": 128},
            ],
        }

        result = analyze_match(match, opendota_data=opendota_data)

        self.assertEqual([hero["id"] for hero in result["context"]["ally_lineup"]], [2, 1])
        self.assertEqual([hero["id"] for hero in result["context"]["enemy_lineup"]], [5])

    def test_opendota_objectives_build_auditable_team_timeline(self):
        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
            }],
            "objectives": [
                {
                    "time": 600,
                    "type": "building_kill",
                    "key": "npc_dota_badguys_tower1_mid",
                    "player_slot": 1,
                },
                {
                    "time": 900,
                    "type": "building_kill",
                    "key": "npc_dota_goodguys_tower2_bot",
                    "player_slot": 1,
                },
                {"time": 1200, "type": "CHAT_MESSAGE_ROSHAN_KILL", "team": 2},
                {"time": 1201, "type": "CHAT_MESSAGE_AEGIS", "player_slot": 1},
            ],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        objectives = result["events"]["objectives"]

        self.assertEqual([item["label"] for item in objectives], [
            "中路一塔", "下路二塔", "肉山", "不朽盾",
        ])
        self.assertEqual([item["outcome"] for item in objectives], [
            "gained", "lost", "gained", "gained",
        ])
        self.assertTrue(objectives[0]["player_direct"])
        self.assertEqual(objectives[0]["direct_label"], "本人最后一击（敌方建筑）")
        self.assertTrue(objectives[1]["player_direct"])
        self.assertEqual(objectives[1]["direct_label"], "本人完成己方建筑反补")
        self.assertTrue(objectives[3]["player_direct"])
        self.assertEqual(result["events"]["objective_summary"], {
            "gained": 3,
            "lost": 1,
            "player_direct": 3,
            "total": 4,
        })
        self.assertEqual(result["events"]["objective_source"], "opendota_objectives")

    def test_deaths_are_cross_referenced_with_verified_objective_losses(self):
        match = self._base_match()
        match["deaths"] = 2
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "death_log": [{"time": 540}, {"time": 1170}],
                "purchase_log": [{"time": 1125, "key": "black_king_bar"}],
            }],
            "objectives": [
                {
                    "time": 600,
                    "type": "building_kill",
                    "key": "npc_dota_goodguys_tower1_mid",
                },
                {
                    "time": 610,
                    "type": "building_kill",
                    "key": "npc_dota_badguys_tower1_top",
                },
                {"time": 1200, "type": "CHAT_MESSAGE_ROSHAN_KILL", "team": 3},
            ],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        windows = result["events"]["death_objective_windows"]

        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0]["evidence_label"], "9.0分死亡 → 10.0分失去中路一塔（60秒）")
        self.assertEqual(windows[1]["evidence_label"], "19.5分死亡 → 20.0分失去肉山（30秒）")
        self.assertEqual(result["events"]["death_objective_summary"]["window_count"], 2)
        self.assertEqual(result["events"]["death_objective_summary"]["unique_death_count"], 2)
        drill = result["events"]["death_objective_drill"]
        self.assertEqual(drill["title"], "目标前90秒生存规则")
        self.assertIn("19.5分死亡 → 20.0分失去肉山（30秒）", drill["evidence"])
        self.assertIn("目标前90秒", drill["trigger"])
        self.assertNotIn("接失去", drill["trigger"])
        self.assertIn("肉山", drill["trigger"])
        self.assertEqual(
            [item["label"] for item in drill["checklist"]],
            ["局部人数数据"],
        )
        self.assertTrue(all("check" in item and item["check"] for item in drill["checklist"]))
        self.assertIn("全员位置采样未获取", drill["checklist"][0]["check"])
        self.assertIn("死亡后90秒内失去目标窗口为0", drill["success_metric"])
        objective_findings = [
            item for item in result["review_findings"]
            if item["category"] == "death_objective_window"
        ]
        self.assertEqual(len(objective_findings), 1)
        self.assertIn("60秒", objective_findings[0]["evidence"])
        self.assertIn("目标前90秒生存规则", objective_findings[0]["training_goal"])
        self.assertIn("死亡后90秒内失去目标窗口为0", objective_findings[0]["success_metric"])
        self.assertNotIn("单独深入次数", objective_findings[0]["success_metric"])
        self.assertIn("只自动验收死亡与目标事件的时间窗口", objective_findings[0]["replay_check"])
        self.assertIn("只标记事件先后", objective_findings[0]["replay_check"])
        self.assertIn("该死亡前45秒完成 Black King Bar", objective_findings[0]["evidence"])
        self.assertIn("刚完成 Black King Bar 后的首次目标接触", objective_findings[0]["action"])
        self.assertIn("系统自动对齐关键购买与焦点死亡", objective_findings[0]["replay_check"])

    def test_death_objective_drill_prioritizes_cumulative_loss_window(self):
        windows = [
            {
                "death_time": 1620,
                "death_minute": 27.0,
                "objective_time": 1637,
                "objective_kind": "barracks",
                "objective_display_label": "失去下路近战兵营",
                "elapsed_seconds": 17,
                "evidence_label": "27.0分死亡 → 27.3分失去下路近战兵营（17秒）",
            },
            {
                "death_time": 1620,
                "death_minute": 27.0,
                "objective_time": 1642,
                "objective_kind": "barracks",
                "objective_display_label": "失去下路远程兵营",
                "elapsed_seconds": 22,
                "evidence_label": "27.0分死亡 → 27.4分失去下路远程兵营（22秒）",
            },
            {
                "death_time": 1620,
                "death_minute": 27.0,
                "objective_time": 1662,
                "objective_kind": "tower",
                "objective_display_label": "失去中路高地塔",
                "elapsed_seconds": 42,
                "evidence_label": "27.0分死亡 → 27.7分失去中路高地塔（42秒）",
            },
            {
                "death_time": 1860,
                "death_minute": 31.0,
                "objective_time": 1868,
                "objective_kind": "ancient",
                "objective_display_label": "失去遗迹",
                "elapsed_seconds": 8,
                "evidence_label": "31.0分死亡 → 31.1分失去遗迹（8秒）",
            },
        ]

        drill = _build_death_objective_drill(windows, deaths=[{
            "time": 1620,
            "nearby_context": {
                "radius_units": 1600,
                "allies_within_radius_count": 1,
                "enemies_within_radius_count": 3,
                "nearest_ally": {"hero_name": "Crystal Maiden", "player_id": 1, "distance_units": 900},
                "nearest_enemy": {"hero_name": "Phantom Assassin", "player_id": 5, "distance_units": 400},
            },
        }])

        self.assertEqual(drill["focus_objective"], "高地防守")
        self.assertEqual(drill["focus_window_count"], 3)
        self.assertEqual(drill["focus_death_minute"], 27.0)
        self.assertIn("下路近战兵营", drill["evidence"])
        self.assertIn("中路高地塔", drill["evidence"])
        self.assertIn("准备参与高地防守", drill["trigger"])
        self.assertNotIn("基地防守", drill["trigger"])
        self.assertEqual(
            [item["label"] for item in drill["checklist"]],
            ["局部人数", "最近队友", "最近敌人"],
        )
        self.assertIn("队友1人、敌人3人", drill["checklist"][0]["check"])
        self.assertIn("Crystal Maiden", drill["checklist"][1]["check"])
        self.assertIn("Phantom Assassin", drill["checklist"][2]["check"])
        self.assertIn("全员位置与生命状态自动计算", drill["replay_check"])

        finding = next(
            item for item in _build_review_findings({
                "role_profile": {"id": "pos1"},
                "timeline": {},
                "events": {
                    "deaths": [],
                    "purchases": [],
                    "death_objective_windows": windows,
                    "death_objective_summary": {"unique_death_count": 2},
                    "death_objective_drill": drill,
                },
                "kda": {"deaths": 0},
            })
            if item["category"] == "death_objective_window"
        )
        self.assertIn("最高累计损失窗口", finding["evidence"])
        self.assertIn("共3个目标", finding["evidence"])
        self.assertIn("下路远程兵营", finding["evidence"])
        self.assertIn("其他相邻窗口", finding["evidence"])
        self.assertLess(
            finding["evidence"].index("下路近战兵营"),
            finding["evidence"].index("31.1分失去遗迹"),
        )

    def test_opendota_benchmarks_create_percentile_profile_and_findings(self):
        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "benchmarks": {
                    "gold_per_min": {"raw": 540, "pct": 0.52},
                    "xp_per_min": {"raw": 620, "pct": 0.61},
                    "last_hits_per_min": {"raw": 5.1, "pct": 0.22},
                    "hero_damage_per_min": {"raw": 360.5, "pct": 0.18},
                    "tower_damage": {"raw": 2200, "pct": 0.72},
                },
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        profile = result["opendota_benchmarks"]

        self.assertTrue(profile["available"])
        self.assertEqual(profile["source"], "OpenDota英雄样本百分位")
        self.assertEqual(profile["summary"]["weak_count"], 2)
        self.assertEqual(profile["summary"]["strong_count"], 1)
        self.assertEqual(profile["metrics"][0]["label"], "推塔伤害")
        self.assertEqual(profile["metrics"][0]["percentile_label"], "第72百分位")
        self.assertIn("hero_benchmarks", result["data_quality"]["available"])
        benchmark_findings = [
            item for item in result["review_findings"]
            if item["category"] == "hero_benchmark_gap"
        ]
        self.assertEqual(len(benchmark_findings), 1)
        self.assertEqual(benchmark_findings[0]["priority"], "medium")
        benchmark_index = result["review_findings"].index(benchmark_findings[0])
        death_index = next(
            index for index, item in enumerate(result["review_findings"])
            if item["category"] == "death_review"
        )
        self.assertLess(death_index, benchmark_index)
        self.assertIn("英雄伤害/分钟 第18百分位", benchmark_findings[0]["evidence"])
        self.assertIn("补刀/分钟 第22百分位", benchmark_findings[0]["evidence"])
        self.assertIn("OpenDota英雄样本百分位", benchmark_findings[0]["replay_check"])

    def test_zero_healing_percentile_is_not_presented_as_a_strength(self):
        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "benchmarks": {
                    "hero_healing_per_min": {"raw": 0, "pct": 0.96},
                    "kills_per_min": {"raw": 0.45, "pct": 0.95},
                },
            }],
        }

        profile = analyze_match(match, opendota_data=opendota_data)["opendota_benchmarks"]
        metric_ids = [item["id"] for item in profile["metrics"]]

        self.assertNotIn("hero_healing_per_min", metric_ids)
        self.assertIn("kills_per_min", metric_ids)

    def test_low_tower_damage_benchmark_produces_a_specific_and_measurable_rule(self):
        match = self._base_match()
        match["tower_damage"] = 116
        result = analyze_match(match, opendota_data={
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "benchmarks": {
                    "tower_damage": {"raw": 116, "pct": 0.18},
                },
            }],
        })

        finding = next(
            item for item in result["review_findings"]
            if item["category"] == "hero_benchmark_gap"
        )

        self.assertIn("兵线已到敌方建筑", finding["action"])
        self.assertIn("第18百分位", finding["success_metric"])
        self.assertIn("建筑转化不少于1次", finding["success_metric"])
        self.assertIn("至少第30百分位", finding["success_metric"])
        self.assertNotIn("建筑伤害>116", finding["success_metric"])
        self.assertNotIn("把路线和团战选择改到", finding["action"])

    def test_generated_report_shows_opendota_benchmark_percentiles(self):
        from report.generator import generate_report
        import report.generator as generator

        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "benchmarks": {
                    "gold_per_min": {"raw": 540, "pct": 0.52},
                    "last_hits_per_min": {"raw": 5.1, "pct": 0.22},
                    "hero_damage_per_min": {"raw": 360.5, "pct": 0.18},
                    "tower_damage": {"raw": 2200, "pct": 0.72},
                },
            }],
        }

        analysis = analyze_match(match, opendota_data=opendota_data)
        old_report_dir = generator.REPORT_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                generator.REPORT_DIR = tmpdir
                report_path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
                with open(report_path, encoding="utf-8") as report_file:
                    html = report_file.read()
        finally:
            generator.REPORT_DIR = old_report_dir

        self.assertIn("英雄样本百分位", html)
        self.assertIn("OpenDota英雄样本百分位", html)
        self.assertIn("英雄伤害/分钟", html)
        self.assertIn("第18百分位", html)
        self.assertIn("补刀/分钟", html)
        self.assertIn("第22百分位", html)

    def test_generated_report_embeds_generation_timestamp_in_structured_metadata(self):
        from report.generator import generate_report
        import report.generator as generator
        from scripts.build_pages_site import _read_embedded_metadata

        analysis = analyze_match(self._base_match())
        old_report_dir = generator.REPORT_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                generator.REPORT_DIR = tmpdir
                report_path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
                metadata = _read_embedded_metadata(Path(report_path))
        finally:
            generator.REPORT_DIR = old_report_dir

        self.assertRegex(
            metadata.get("report_generated_at") or "",
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
        )

    def test_config_prefers_environment_paths_and_stratz_secret(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = str(Path(tmpdir) / "reports")
            db_path = str(Path(tmpdir) / "refresh.db")
            env = os.environ.copy()
            env.update({
                "STRATZ_API_KEY": "environment-test-key",
                "DOTA_REVIEW_REPORT_DIR": report_dir,
                "DOTA_REVIEW_DB_PATH": db_path,
            })
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json, config; "
                        "print(json.dumps({"
                        "'key_matches': config.STRATZ_API_KEY == 'environment-test-key', "
                        "'report_dir': config.REPORT_DIR, "
                        "'db_path': config.DB_PATH}))"
                    ),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

        payload = json.loads(result.stdout)
        self.assertTrue(payload["key_matches"])
        self.assertEqual(payload["report_dir"], report_dir)
        self.assertEqual(payload["db_path"], db_path)

    def test_generated_report_honors_output_dir_and_embeds_source_fetches(self):
        from report.generator import generate_report
        from scripts.build_pages_site import _read_embedded_metadata

        analysis = analyze_match(self._base_match())
        source_fetches = {
            "stratz_fetched_at": "2026-07-11T09:52:00Z",
            "opendota_fetched_at": "2026-07-11T09:53:00Z",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = generate_report(
                analysis,
                _generate_fallback_analysis(analysis, "Anti-Mage", True),
                output_dir=tmpdir,
                source_fetches=source_fetches,
            )
            metadata = _read_embedded_metadata(Path(report_path))

        self.assertEqual(Path(report_path).parent, Path(tmpdir))
        self.assertEqual(metadata["source_fetches"], source_fetches)

    def test_opendota_performance_context_uses_real_match_fields_in_findings(self):
        match = self._base_match()
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
            }],
        }
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "lane_efficiency": 0.3969,
                "lane_efficiency_pct": 39,
                "teamfight_participation": 0.36,
                "life_state_dead": 420,
                "buyback_count": 1,
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data, opendota_data=opendota_data)
        profile = result["performance_context"]

        self.assertTrue(profile["available"])
        self.assertEqual(profile["source"], "OpenDota对局汇总字段")
        self.assertEqual(profile["lane_efficiency_pct"], 39)
        self.assertEqual(profile["teamfight_participation_pct"], 36)
        self.assertEqual(profile["dead_time_seconds"], 420)
        self.assertEqual(profile["dead_time_label"], "7分00秒")
        self.assertEqual(profile["dead_time_share_pct"], 20.0)
        self.assertEqual(profile["average_dead_time_per_death_seconds"], 70)
        self.assertEqual(profile["buyback_count"], 1)
        self.assertIn("opendota_performance_context", result["data_quality"]["available"])
        source = next(
            item for item in result["data_quality"]["evidence_sources"]
            if item["id"] == "performance_context"
        )
        self.assertEqual(source["status"], "available")
        self.assertIn("对线效率39%", source["coverage"])

        lane_finding = next(item for item in result["review_findings"] if item["category"] == "lane_farm")
        map_finding = next(item for item in result["review_findings"] if item["category"] == "map_impact")
        death_finding = next(item for item in result["review_findings"] if item["category"] == "death_review")
        self.assertIn("OpenDota对线效率 39%", lane_finding["evidence"])
        self.assertIn("提升到44%", lane_finding["action"])
        self.assertIn("OpenDota参战率 36%", map_finding["evidence"])
        self.assertIn("低于报告40%训练阈值", map_finding["why_it_matters"])
        self.assertNotIn("说明", map_finding["why_it_matters"])
        self.assertNotIn("空走", lane_finding["action"])
        self.assertIn("死亡占时 7分00秒（20.0%）", death_finding["evidence"])
        review = build_formula_review(result)
        conversion = next(card for card in review["scorecards"] if card["id"] == "conversion")
        self.assertTrue(any(item["id"] == "teamfight_participation_pct" for item in conversion["inputs"]))

    def test_generated_report_shows_opendota_performance_context(self):
        from report.generator import generate_report
        import report.generator as generator

        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "lane_efficiency_pct": 66,
                "teamfight_participation": 0.68,
                "life_state_dead": 420,
                "buyback_count": 1,
            }],
        }
        analysis = analyze_match(match, opendota_data=opendota_data)

        old_report_dir = generator.REPORT_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                generator.REPORT_DIR = tmpdir
                report_path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
                with open(report_path, encoding="utf-8") as report_file:
                    html = report_file.read()
        finally:
            generator.REPORT_DIR = old_report_dir

        self.assertIn("分路与参战画像", html)
        self.assertIn("performance-context-grid", html)
        self.assertIn("对线效率", html)
        self.assertIn("66%", html)
        self.assertIn("参战率", html)
        self.assertIn("68%", html)
        self.assertIn("死亡占时", html)
        self.assertIn("7分00秒", html)
        self.assertIn("买活次数", html)
        self.assertIn("OpenDota对局汇总字段", html)
        self.assertIn("不是职业均值", html)

    def test_generated_report_starts_with_primary_decision_snapshot(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 3
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "stats": {
                        "lastHitsPerMinute": [5] * 30,
                        "goldPerMinute": [400] * 30,
                        "deathEvents": [
                            {
                                "time": event_time,
                                "timeDead": 40,
                                "goldLost": 200,
                                "goldFed": 300,
                                "xpFed": 450,
                            }
                            for event_time in (420, 930, 1280)
                        ],
                    },
                    "playbackData": {
                        "deathEvents": [{"time": 420}, {"time": 930}, {"time": 1280}],
                    },
                }],
            }
            analysis = analyze_match(
                match,
                stratz_data=stratz_data,
                replay_data={
                    "source": "valve_replay_gem",
                    "validation": {
                        "status": "matched",
                        "checks": [{
                            "metric": "deaths",
                            "api_value": 3,
                            "replay_value": 3,
                            "delta": 0,
                            "status": "matched",
                        }],
                    },
                },
            )
            analysis["review_findings"].insert(0, {
                "priority": "low",
                "priority_label": "低优先级",
                "category": "review_focus",
                "category_label": "非首要占位问题",
                "evidence": "这条规则故意放在原始数组第一项。",
                "why_it_matters": "用于验证报告不会误用原始生成顺序。",
                "action": "不要把它显示为首要决策。",
                "replay_check": "系统检查公式排序。",
                "training_goal": "首屏遵守公式优先级。",
                "success_metric": "决策卡首项等于公式首项。",
            })
            top_finding = select_formula_findings(analysis)[0]
            self.assertNotEqual(
                analysis["review_findings"][0]["category"],
                top_finding["category"],
            )
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

        generator.REPORT_DIR = old_report_dir

        self.assertIn('id="decision-snapshot"', html)
        self.assertIn('id="formula-summary"', html)
        decision_index = html.index('id="decision-snapshot"')
        formula_index = html.index('id="formula-summary"')
        self.assertLess(decision_index, formula_index)
        self.assertIn("上分决策卡", html)
        self.assertIn("本局最该修", html)
        decision_html = html[decision_index:formula_index]
        self.assertIn(top_finding["category_label"], decision_html)
        self.assertIn(top_finding["evidence"], decision_html)
        self.assertIn(top_finding["action"], decision_html)
        self.assertIn(top_finding["success_metric"], decision_html)
        self.assertNotIn("非首要占位问题", decision_html)
        self.assertIn('href="#decision-snapshot"', html)
        self.assertIn('data-decision-tab="action"', html)
        self.assertIn('data-decision-tab="evidence"', html)
        self.assertIn('data-decision-tab="validation"', html)
        self.assertIn('data-decision-panel="validation"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('data-decision-tabs', html)

    def test_generated_report_shows_real_objective_timeline(self):
        from report.generator import generate_report
        import report.generator as generator

        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "death_log": [{"time": 1140}],
            }],
            "objectives": [
                {
                    "time": 600,
                    "type": "building_kill",
                    "key": "npc_dota_badguys_tower1_mid",
                    "player_slot": 1,
                },
                {"time": 1200, "type": "CHAT_MESSAGE_ROSHAN_KILL", "team": 3},
            ],
        }

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            analysis = analyze_match(match, opendota_data=opendota_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
        generator.REPORT_DIR = old_report_dir

        self.assertIn("目标事件时间线", html)
        self.assertIn("10.0分", html)
        self.assertIn("中路一塔", html)
        self.assertIn("本人直接参与", html)
        self.assertIn("20.0分", html)
        self.assertIn("失去肉山", html)
        self.assertIn("死亡后目标窗口", html)
        self.assertIn("19.0分死亡 → 20.0分失去肉山（60秒）", html)
        self.assertIn("只表示时间相邻", html)
        self.assertIn("目标前90秒生存规则", html)
        self.assertIn("证据窗口", html)
        self.assertIn("目标窗口自动证据", html)
        self.assertNotIn("优先回看", html)
        self.assertIn("局部人数数据", html)
        self.assertIn("全员位置采样未获取", html)
        self.assertNotIn("队友接应", html)
        self.assertNotIn("敌方控制", html)
        self.assertIn("objective-review-workbench", html)
        self.assertIn('data-objective-filter="all"', html)
        self.assertIn('data-objective-filter="gained"', html)
        self.assertIn('data-objective-filter="lost"', html)
        self.assertIn('data-objective-filter="direct"', html)
        self.assertIn('id="objective-event-list"', html)
        self.assertIn('data-objective-outcome="gained"', html)
        self.assertIn('data-objective-direct="true"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('data-objective-filtering', html)
        self.assertIn('href="#death-objective-windows"', html)

    def test_opendota_lane_is_labeled_without_guessing_numbered_position(self):
        match = self._base_match()
        match["hero_id"] = 9
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 9,
                "player_slot": 2,
                "lane_role": 3,
                "lane": 3,
            }] + [
                {"hero_id": hero_id, "player_slot": slot}
                for hero_id, slot in zip((8, 17, 100, 64, 75, 16, 2, 155, 6), (0, 1, 3, 4, 128, 129, 130, 131, 132))
            ]
        }

        result = analyze_match(match, opendota_data=opendota_data)

        self.assertEqual(result["context"]["lane"], "劣势路（OpenDota）")
        self.assertEqual(result["role_profile"]["label"], "劣势路（位置未细分）")
        limitations = " ".join(result["data_quality"]["limitations"])
        self.assertIn("阵容已由OpenDota补齐", limitations)
        self.assertNotIn("无法确认分路/位置/完整阵容上下文", limitations)

    def test_analyze_match_builds_evidence_from_stratz_player_detail(self):
        stratz_data = {
            "players": [
                {
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "lane": "SAFE_LANE",
                    "role": "CORE",
                    "abilityUpgrade": [
                        {"abilityId": 5003, "time": 88, "level": 1},
                        {"abilityId": 7314, "time": 154, "level": 2},
                    ],
                    "items": [{"id": 160}, {"id": 116}],
                },
                {
                    "steamAccount": {"id": 999},
                    "isRadiant": False,
                    "hero": {"id": 2, "displayName": "Axe"},
                },
            ]
        }

        result = analyze_match(self._base_match(), stratz_data=stratz_data)

        self.assertEqual(result["context"]["role"], "POSITION_1")
        self.assertEqual(result["context"]["lane"], "优势路（STRATZ）")
        self.assertEqual(result["context"]["raw_lane"], "SAFE_LANE")
        self.assertIn("Axe", result["context"]["enemy_heroes"])
        self.assertEqual(result["skills"]["upgrades"][0]["abilityId"], 5003)
        self.assertIn("stratz_player_detail", result["data_quality"]["available"])
        self.assertLess(result["data_quality"]["score"], 60)
        self.assertIn("死亡时间", " ".join(result["data_quality"]["limitations"]))

    def test_formula_review_names_missing_dimensions_without_estimating(self):
        analysis = analyze_match(self._base_match())
        review = build_formula_review(analysis)

        self.assertTrue(review["unscored_dimensions"])
        self.assertTrue(all("未计算也未估算" in item["reason"] for item in review["unscored_dimensions"]))
        self.assertIn("minute_lh", analysis["data_quality"]["blocking_gaps"])

    def test_static_favorable_matchup_table_does_not_create_an_evidence_finding(self):
        match = self._base_match()
        match["hero_id"] = 10
        opendota_data = {
            "players": [
                {
                    "account_id": 173776719,
                    "hero_id": 10,
                    "player_slot": 1,
                },
                {
                    "account_id": 999,
                    "hero_id": 2,
                    "player_slot": 128,
                },
            ],
        }

        result = analyze_match(match, opendota_data=opendota_data)

        self.assertEqual(result["hero_name"], "Morphling")
        self.assertIn("Axe", result["context"]["enemy_heroes"])
        self.assertFalse(any(issue.get("type") == "hero_matchup" for issue in result["issues"]))

    def test_data_quality_does_not_repeat_specific_gaps_as_generic_coverage_gaps(self):
        limitations = analyze_match(self._base_match())["data_quality"]["limitations"]

        self.assertTrue(any("缺少分钟补刀时间线" in item for item in limitations))
        self.assertTrue(any("缺少分钟经济时间线" in item for item in limitations))
        self.assertTrue(any("缺少购买时间线" in item for item in limitations))
        self.assertTrue(any("缺少团战/击杀日志" in item for item in limitations))
        self.assertTrue(any("缺少地图目标事件" in item for item in limitations))
        for duplicate in (
            "分钟时间线缺失",
            "购买时间缺失",
            "击杀/助攻事件缺失",
            "地图目标事件缺失",
        ):
            self.assertFalse(any(duplicate in item for item in limitations), duplicate)

    def test_match_identity_and_clock_are_required_evidence(self):
        match = self._base_match()
        match.pop("duration")

        result = analyze_match(match)
        ledger = next(
            item for item in result["data_quality"]["field_ledger"]
            if item["id"] == "match_identity"
        )

        self.assertEqual(ledger["status"], "partial")
        self.assertIn("duration", ledger["missing_fields"])
        self.assertIn("start_time", ledger["missing_fields"])
        self.assertIn("match_identity", result["data_quality"]["blocking_gaps"])

    def test_formula_review_keeps_limitations_out_of_priority_actions(self):
        analysis = analyze_match(self._base_match())
        review = build_formula_review(analysis)

        self.assertEqual(review["analysis_mode"], "deterministic_formula")
        self.assertEqual(review["next_actions"], [])
        self.assertEqual(review["data_limits"], analysis["data_quality"]["limitations"])

    def test_formula_review_prioritizes_high_death_cost(self):
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [5] * 35,
                    "goldPerMinute": [500] * 35,
                    "experiencePerMinute": [600] * 35,
                    "heroDamagePerMinute": [300] * 35,
                    "towerDamagePerMinute": [50] * 35,
                },
                "playbackData": {
                    "deathEvents": [
                        {"time": minute * 60}
                        for minute in (5, 10, 15, 20, 25, 30)
                    ],
                },
            }],
        }
        analysis = analyze_match(self._base_match(), stratz_data=stratz_data)
        review = build_formula_review(analysis)

        self.assertTrue(review["review_points"][0]["category"].startswith("death"))
        self.assertIn("死亡", review["conclusion"])

    def test_formula_review_names_top_finding_instead_of_generic_summary(self):
        match = self._base_match()
        match.update({
            "kills": 12,
            "deaths": 2,
            "assists": 7,
            "duration": 1620,
            "gold_per_min": 780,
            "tower_damage": 12720,
            "last_hits": 247,
        })
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Beastmaster"},
                "position": "POSITION_3",
                "lane": "OFF_LANE",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [9] * 30,
                    "goldPerMinute": [780] * 30,
                    "towerDamagePerMinute": [0] * 30,
                    "heroDamagePerMinute": [300] * 30,
                },
                "playbackData": {
                    "deathEvents": [{"time": 480}, {"time": 636}],
                },
            }],
        }
        analysis = analyze_match(match, stratz_data=stratz_data)
        review = build_formula_review(analysis)

        self.assertTrue(review["review_points"][0]["category"].startswith("death"))
        self.assertEqual(review["review_points"][0]["evidence"], next(
            item["evidence"] for item in analysis["review_findings"]
            if item["category"] == review["review_points"][0]["category"]
        ))

    def test_saved_stratz_detail_round_trips_as_json(self):
        old_db_path = schema.DB_PATH
        old_data_dir = schema.DATA_DIR
        with tempfile.TemporaryDirectory() as tmp:
            schema.DATA_DIR = tmp
            schema.DB_PATH = os.path.join(tmp, "dota2.db")
            schema.init_db()
            schema.save_stratz_detail(123, json.dumps({"players": [{"hero": {"displayName": "Axe"}}]}))

            saved = schema.get_stratz_detail(123)

            self.assertEqual(saved["players"][0]["hero"]["displayName"], "Axe")

        schema.DB_PATH = old_db_path
        schema.DATA_DIR = old_data_dir

    def test_timeline_uses_stratz_minute_arrays_for_lane_and_windows(self):
        match = self._base_match()
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "lane": "SAFE_LANE",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [3, 4, 4, 5, 3, 6, 5, 4, 4, 3, 8, 9, 10, 9, 8, 7, 7, 8, 9, 10],
                    "deniesPerMinute": [0, 1, 0, 1, 0, 0, 1, 0, 0, 0],
                    "goldPerMinute": [250, 280, 300, 310, 290, 330, 340, 320, 310, 300, 460, 520, 560, 590, 610],
                    "heroDamagePerMinute": [0, 80, 0, 110, 0, 0, 120, 0, 0, 60, 420, 50, 0, 700, 300],
                    "towerDamagePerMinute": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 350, 0, 0, 0, 800],
                },
            }]
        }

        result = analyze_match(match, stratz_data=stratz_data)

        self.assertEqual(result["timeline"]["ten_min_last_hits"], 41)
        self.assertEqual(result["timeline"]["phases"][0]["label"], "0-10")
        self.assertAlmostEqual(result["timeline"]["phases"][0]["lh_per_min"], 4.1)
        self.assertIn("低效率窗口", result["timeline"]["low_efficiency_windows"][0]["label"])
        self.assertIn("lane_timeline", result["data_quality"]["available"])

    def test_stratz_playback_cs_events_create_lane_timeline_when_minute_arrays_missing(self):
        match = self._base_match()
        match["duration"] = 1200
        cs_counts = [5, 5, 5, 5, 5, 1, 1, 1, 6, 6, 7, 7]
        cs_events = [
            {"time": minute * 60 + index + 1}
            for minute, count in enumerate(cs_counts)
            for index in range(count)
        ]
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "lane": "SAFE_LANE",
                "role": "CORE",
                "playbackData": {
                    "csEvents": cs_events,
                },
            }]
        }

        result = analyze_match(match, stratz_data=stratz_data)

        self.assertTrue(result["timeline"]["available"])
        self.assertEqual(result["timeline"]["source"], "stratz_playback_cs")
        self.assertEqual(result["timeline"]["ten_min_last_hits"], 40)
        self.assertEqual(result["timeline"]["phases"][0]["label"], "0-10")
        self.assertAlmostEqual(result["timeline"]["phases"][0]["lh_per_min"], 4.0)
        self.assertEqual(result["timeline"]["low_efficiency_windows"][0]["label"], "低效率窗口 5-8分钟")
        self.assertIn("lane_timeline", result["data_quality"]["available"])
        self.assertIn("stratz_playback_cs", result["data_quality"]["available"])

    def test_report_shows_timeline_source_for_stratz_playback_cs(self):
        from report import generator
        from report.generator import generate_report

        match = self._base_match()
        match["duration"] = 1200
        cs_events = [{"time": minute * 60 + index + 1} for minute in range(10) for index in range(5)]
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "playbackData": {"csEvents": cs_events},
            }]
        }
        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

        generator.REPORT_DIR = old_report_dir

        self.assertIn("时间线来源", html)
        self.assertIn("STRATZ补刀事件", html)

    def test_timeline_merges_opendota_farm_with_stratz_damage_arrays(self):
        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "lh_t": [0, 5, 10, 16, 22, 28, 34, 40, 46, 52, 58, 66, 74],
                "gold_t": [0, 300, 650, 980, 1320, 1660, 2020, 2380, 2740, 3100, 3500, 4100, 4700],
            }],
        }
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "stats": {
                    "heroDamagePerMinute": [0] * 10 + [120, 80],
                    "towerDamagePerMinute": [0] * 10 + [300, 400],
                    "deniesPerMinute": [1] * 12,
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data, opendota_data=opendota_data)

        self.assertEqual(result["timeline"]["source"], "opendota_parsed_logs+stratz_stats")
        self.assertEqual(result["timeline"]["phases"][1]["hero_damage"], 200)
        self.assertEqual(result["timeline"]["phases"][1]["tower_damage"], 700)
        self.assertEqual(result["timeline"]["ten_min_denies"], 10)
        self.assertTrue(result["timeline"]["damage_windows"])

    def test_timeline_rejects_cumulative_series_with_a_missing_minute(self):
        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "lh_t": [0, 5, None, 16],
                "gold_t": [0, 300, 650, 980],
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)

        self.assertFalse(result["timeline"]["available"])
        self.assertIsNone(result["timeline"]["ten_min_last_hits"])

    def test_timeline_rejects_non_monotonic_cumulative_series(self):
        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "lh_t": [0, 5, 4, 16],
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)

        self.assertFalse(result["timeline"]["available"])

    def test_timeline_does_not_invent_zero_for_unavailable_optional_series(self):
        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "lh_t": [0, 5, 10, 16, 22, 28, 34, 40, 46, 52, 58],
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        timeline = result["timeline"]

        self.assertIsNone(timeline["ten_min_denies"])
        self.assertIsNone(timeline["twenty_min_avg_gpm"])
        self.assertIsNone(timeline["phases"][0]["avg_gpm"])
        self.assertIsNone(timeline["phases"][0]["avg_xpm"])
        self.assertIsNone(timeline["phases"][0]["hero_damage"])
        self.assertIsNone(timeline["phases"][0]["tower_damage"])

        from report.generator import generate_report
        with tempfile.TemporaryDirectory() as output_dir:
            path = generate_report(
                result,
                _generate_fallback_analysis(result),
                output_dir=output_dir,
            )
            html = Path(path).read_text(encoding="utf-8")
        self.assertNotIn("None", html)
        self.assertIn("未获取", html)

    def test_report_translates_source_ids_and_preserves_unknown_header_values(self):
        result = analyze_match(self._base_match())
        result["is_win"] = None
        result["duration_min"] = None
        result["data_quality"]["available"] = [
            "opendota_core_stats",
            "valve_replay_gem",
        ]

        from report.generator import generate_report
        with tempfile.TemporaryDirectory() as output_dir:
            path = generate_report(
                result,
                _generate_fallback_analysis(result),
                output_dir=output_dir,
            )
            html = Path(path).read_text(encoding="utf-8")

        self.assertIn("比赛结果未获取", html)
        self.assertIn("时长 未获取", html)
        self.assertIn("OpenDota比赛核心数据", html)
        self.assertIn("Valve原始回放解析", html)
        self.assertNotIn("opendota_core_stats", html)
        self.assertNotIn("valve_replay_gem", html)

    def test_lane_farm_findings_ignore_only_late_low_efficiency_windows(self):
        match = self._base_match()
        match["duration"] = 4200
        diffs = [6] * 10 + [8] * 48 + [1, 1, 8, 8]
        lh_t = [0]
        for value in diffs:
            lh_t.append(lh_t[-1] + value)
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "lh_t": lh_t,
                "gold_t": [idx * 500 for idx in range(len(lh_t))],
                "purchase_log": [{"time": 800, "key": "bfury"}],
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)

        self.assertGreaterEqual(result["timeline"]["ten_min_last_hits"], 45)
        self.assertTrue(all(window["start_minute"] >= 10 for window in result["timeline"]["low_efficiency_windows"]))
        self.assertNotIn("lane_farm", {finding["category"] for finding in result["review_findings"]})

    def test_single_late_low_efficiency_window_requires_zero_target(self):
        match = self._base_match()
        match["duration"] = 1200
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "lane": "SAFE_LANE",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [6] * 10 + [2, 2] + [6] * 8,
                    "goldPerMinute": [500] * 20,
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        finding = next(
            item for item in result["review_findings"]
            if item["category"] == "resource_continuity"
        )

        self.assertIn("从1个降到不超过0个", finding["training_goal"])
        self.assertIn("低效率窗口不超过0个", finding["success_metric"])
        self.assertNotIn("从1个压到最多1个", finding["training_goal"])

    def test_unknown_lane_core_profile_keeps_late_resource_findings(self):
        findings = _build_review_findings({
            "duration_min": 52.8,
            "farm": {"last_hits": 727, "gpm": 1030},
            "derived": {"lh_per_min": 13.77, "deaths_per_10_min": 1.7},
            "role_profile": {
                "id": "unknown_lane",
                "label": "优势路（位置未细分）",
                "lane_farm_sensitive": True,
            },
            "timeline": {
                "available": True,
                "ten_min_last_hits": 56,
                "low_efficiency_windows": [{
                    "label": "低效率窗口 48-50分钟",
                    "start_minute": 48,
                    "end_minute": 50,
                    "avg_lh": 1.5,
                }],
                "death_overlap_windows": [{
                    "evidence_label": "低效率窗口 48-50分钟含 48.2分死亡",
                    "death_count": 1,
                }],
            },
            "events": {"deaths": [], "purchases": []},
            "kda": {"deaths": 0},
        })

        categories = {item["category"] for item in findings}
        self.assertIn("resource_continuity", categories)
        self.assertIn("death_resource_overlap", categories)

    def test_opendota_vision_profile_routes_supports_away_from_core_farm_goals(self):
        match = self._base_match()
        match["hero_id"] = 5
        match["last_hits"] = 110
        match["duration"] = 2400
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 5,
                "player_slot": 131,
                "lh_t": [0, 0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 14, 18],
                "gold_t": [0, 180, 340, 510, 690, 870, 1040, 1210, 1390, 1580, 1790, 2050, 2320],
                "purchase_log": [{"time": 420, "key": "ward_observer"}],
                "kills_log": [{"time": 600, "key": "npc_dota_hero_axe"}],
                "obs_log": [
                    {"time": -50, "key": "[128,129]"},
                    {"time": 70, "key": "[102,161]"},
                    {"time": 770, "key": "[120,150]"},
                    {"time": 1300, "key": "[98,142]"},
                ],
                "sen_log": [
                    {"time": -20, "key": "[89,156]"},
                    {"time": 120, "key": "[97,170]"},
                    {"time": 320, "key": "[87,158]"},
                    {"time": 900, "key": "[116,148]"},
                    {"time": 1500, "key": "[101,133]"},
                ],
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        categories = {finding["category"] for finding in result["review_findings"]}

        self.assertEqual(result["role_profile"]["id"], "support")
        self.assertNotIn("lane_farm", categories)
        self.assertIn("support_vision", categories)
        vision_finding = next(f for f in result["review_findings"] if f["category"] == "support_vision")
        self.assertIn("观察守卫 4", vision_finding["evidence"])
        self.assertIn("岗哨 5", vision_finding["evidence"])
        self.assertIn("vision_events", result["data_quality"]["available"])

    def test_report_context_displays_inferred_support_role(self):
        from report.generator import generate_report
        import report.generator as generator

        match = self._base_match()
        match["hero_id"] = 5
        match["last_hits"] = 110
        match["duration"] = 2400
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 5,
                "player_slot": 131,
                "lh_t": [0, 0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 14, 18],
                "gold_t": [0, 180, 340, 510, 690, 870, 1040, 1210, 1390, 1580, 1790, 2050, 2320],
                "purchase_log": [{"time": 420, "key": "ward_observer"}],
                "obs_log": [{"time": 70, "key": "[102,161]"} for _ in range(4)],
                "sen_log": [{"time": 120, "key": "[97,170]"} for _ in range(5)],
            }],
        }

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            analysis = analyze_match(match, opendota_data=opendota_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Crystal Maiden", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

            self.assertIn('<div class="stat-value small-text">辅助位</div>', html)
            self.assertNotIn("公共数据源缺口：缺少Stratz玩家详情", html)
            self.assertNotIn("低效率窗口 0-10分钟", html)
            self.assertNotIn("Ward Observer 7.0分钟 刷钱装", html)

        generator.REPORT_DIR = old_report_dir

    def test_playback_events_create_purchase_and_death_review_points(self):
        match = self._base_match()
        match["deaths"] = 3
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "lane": "SAFE_LANE",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [5] * 30,
                    "goldPerMinute": [350] * 10 + [600] * 20,
                    "heroDamagePerMinute": [0] * 10 + [200] * 20,
                    "towerDamagePerMinute": [0] * 30,
                },
                "playbackData": {
                    "purchaseEvents": [
                        {"time": 760, "itemId": 145},
                        {"time": 1420, "itemId": 116},
                    ],
                    "deathEvents": [
                        {"time": 930},
                        {"time": 1540},
                    ],
                    "killEvents": [{"time": 1240}],
                    "assistEvents": [{"time": 1260}],
                },
            }]
        }

        result = analyze_match(match, stratz_data=stratz_data)

        self.assertEqual(result["events"]["purchases"][0]["item_name"], "Battle Fury")
        self.assertEqual(result["events"]["deaths"][0]["minute"], 15.5)
        self.assertIn("purchase_timeline", result["data_quality"]["available"])
        self.assertIn("fight_log", result["data_quality"]["available"])
        categories = {finding["category"] for finding in result["review_findings"]}
        self.assertIn("death_review", categories)
        self.assertNotIn("item_timing", categories)
        self.assertTrue(all(
            window["classification"] == "insufficient_data"
            for window in result["events"]["post_item_windows"]
            if window["window_type"] == "map_conversion"
        ))

    def test_stratz_position_samples_are_attached_to_death_events(self):
        match = self._base_match()
        match["deaths"] = 2
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "lane": "SAFE_LANE",
                "role": "CORE",
                "playbackData": {
                    "deathEvents": [{"time": 420}, {"time": 930}],
                    "playerUpdatePositionEvents": [
                        {"time": 390, "x": 122, "y": 140},
                        {"time": 900, "x": 88, "y": 164},
                        {"time": 960, "x": 90, "y": 166},
                    ],
                },
            }]
        }

        result = analyze_match(match, stratz_data=stratz_data)

        first_death = result["events"]["deaths"][0]
        second_death = result["events"]["deaths"][1]
        self.assertEqual(first_death["position"], {"x": 122, "y": 140})
        self.assertEqual(first_death["position_sample_age_seconds"], 30)
        self.assertIn("x=122,y=140", first_death["position_label"])
        self.assertEqual(second_death["position"], {"x": 88, "y": 164})
        self.assertEqual(second_death["position_sample_age_seconds"], 30)
        self.assertIn("stratz_position_samples", result["data_quality"]["available"])
        death_finding = next(f for f in result["review_findings"] if f["category"] == "death_review")
        self.assertIn("死亡坐标覆盖 2/2 次", death_finding["evidence"])
        self.assertIn("坐标明细保留在死亡事件", death_finding["replay_check"])
        self.assertNotIn("x=122,y=140", death_finding["evidence"])
        self.assertNotIn("x=122,y=140", death_finding["replay_check"])

    def test_data_quality_lists_granular_evidence_sources_and_coverage(self):
        match = self._base_match()
        match["deaths"] = 2
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [5] * 30,
                    "goldPerMinute": [350] * 10 + [600] * 20,
                },
                "playbackData": {
                    "purchaseEvents": [{"time": 760, "itemId": 145}],
                    "deathEvents": [{"time": 420}, {"time": 930}],
                    "killEvents": [{"time": 840}],
                    "assistEvents": [{"time": 900}],
                    "playerUpdatePositionEvents": [
                        {"time": 390, "x": 122, "y": 140},
                        {"time": 900, "x": 88, "y": 164},
                    ],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        sources = {
            item["id"]: item
            for item in result["data_quality"]["evidence_sources"]
        }

        self.assertEqual(sources["timeline"]["source"], "STRATZ分钟数组")
        self.assertEqual(sources["purchases"]["source"], "STRATZ回放事件")
        self.assertIn("1条购买", sources["purchases"]["coverage"])
        self.assertEqual(sources["deaths"]["source"], "STRATZ回放事件")
        self.assertEqual(sources["deaths"]["coverage"], "已定位 2/2 次死亡")
        self.assertEqual(sources["death_positions"]["source"], "STRATZ位置采样")
        self.assertEqual(sources["death_positions"]["coverage"], "覆盖 2/2 次已定位死亡")
        self.assertEqual(sources["fight_events"]["source"], "STRATZ回放事件")

    def test_opendota_teamfight_death_positions_attach_to_valve_deaths(self):
        match = self._base_match()
        match["deaths"] = 2
        match["player_slot"] = 1
        opendota_data = {
            "replay_death_events": [
                {"time": 930, "targetname": "npc_dota_hero_antimage"},
                {"time": 1540, "targetname": "npc_dota_hero_antimage"},
            ],
            "players": [
                {"account_id": 1, "hero_id": 2, "player_slot": 0},
                {
                    "account_id": 173776719,
                    "hero_id": 1,
                    "player_slot": 1,
                    "purchase_log": [{"time": 760, "key": "bfury"}],
                    "lh_t": [0, 5, 10, 16, 22, 28, 34, 40, 46, 52, 58],
                    "gold_t": [0, 300, 650, 980, 1320, 1660, 2020, 2380, 2740, 3100, 3500],
                },
            ],
            "teamfights": [
                {
                    "start": 900,
                    "end": 960,
                    "last_death": 948,
                    "players": [
                        {"deaths": 0, "deaths_pos": {}},
                        {"deaths": 1, "deaths_pos": {"120": {"140": 1}}},
                    ],
                }
            ],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        sources = {
            item["id"]: item
            for item in result["data_quality"]["evidence_sources"]
        }

        self.assertEqual(result["events"]["death_count_observed"], 2)
        self.assertEqual(result["events"]["death_position_count"], 1)
        self.assertEqual(result["events"]["deaths"][0]["position"], {"x": 120, "y": 140})
        self.assertEqual(result["events"]["deaths"][0]["position_source"], "opendota_death_positions")
        self.assertEqual(sources["death_positions"]["source"], "OpenDota团战死亡坐标")
        self.assertEqual(sources["death_positions"]["coverage"], "覆盖 1/2 次已定位死亡")
        self.assertEqual(sources["death_positions"]["status"], "partial")
        self.assertLess(result["data_quality"]["score"], 100)
        self.assertIn(
            "死亡位置部分覆盖：覆盖 1/2 次已定位死亡",
            " ".join(result["data_quality"]["limitations"]),
        )
        death_finding = next(f for f in result["review_findings"] if f["category"] == "death_review")
        self.assertIn("死亡坐标覆盖 1/2 次", death_finding["evidence"])
        self.assertNotIn("x=120,y=140", death_finding["evidence"])

    def test_unlocated_deaths_keep_source_backed_context(self):
        match = self._base_match()
        match["deaths"] = 2
        match["duration"] = 1500
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [5] * 25,
                    "goldPerMinute": [420] * 10 + [160, 170, 180, 390, 400, 410, 420, 420, 420, 420, 420, 420, 420, 420, 420],
                },
                "playbackData": {
                    "deathEvents": [
                        {"time": 600, "timeDead": 30},
                        {"time": 960, "timeDead": 35},
                    ],
                    "purchaseEvents": [{"time": 540, "itemId": 145}, {"time": 1020, "itemId": 116}],
                },
            }],
        }
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
            }],
            "objectives": [{
                "time": 660,
                "type": "building_kill",
                "key": "npc_dota_goodguys_mid_tower1",
                "player_slot": 129,
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data, opendota_data=opendota_data)
        first_death = result["events"]["deaths"][0]
        joined_context = " ".join(line["text"] for line in first_death["context_lines"])

        self.assertFalse(first_death.get("position_label"))
        self.assertIn("目标上下文", {line["label"] for line in first_death["context_lines"]})
        self.assertIn("死亡后60秒失去中路一塔", joined_context)
        self.assertIn("恢复上下文", {line["label"] for line in first_death["context_lines"]})
        self.assertIn("装备上下文", {line["label"] for line in first_death["context_lines"]})
        self.assertIn("坐标缺口", {line["label"] for line in first_death["context_lines"]})

    def test_generated_report_explains_unlocated_death_cards_with_context(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 1
            match["duration"] = 1200
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "stats": {
                        "lastHitsPerMinute": [5] * 20,
                        "goldPerMinute": [420] * 20,
                    },
                    "playbackData": {
                        "deathEvents": [{"time": 600}],
                        "purchaseEvents": [{"time": 540, "itemId": 145}],
                    },
                }],
            }
            opendota_data = {
                "players": [{
                    "account_id": 173776719,
                    "hero_id": 1,
                    "player_slot": 1,
                }],
                "objectives": [{
                    "time": 660,
                    "type": "building_kill",
                    "key": "npc_dota_goodguys_mid_tower1",
                    "player_slot": 129,
                }],
            }

            analysis = analyze_match(match, stratz_data=stratz_data, opendota_data=opendota_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

        generator.REPORT_DIR = old_report_dir

        self.assertIn("死亡位置：无位置采样", html)
        self.assertIn("死亡证据上下文", html)
        self.assertIn("目标上下文", html)
        self.assertIn("死亡后60秒失去中路一塔", html)
        self.assertIn("坐标缺口", html)

    def test_ambiguous_opendota_teamfight_positions_are_not_assigned(self):
        match = self._base_match()
        match["deaths"] = 2
        opendota_data = {
            "replay_death_events": [{"time": 930}, {"time": 950}],
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "purchase_log": [{"time": 760, "key": "bfury"}],
                "lh_t": [0, 5, 10, 16, 22, 28, 34, 40, 46, 52, 58],
                "gold_t": [0, 300, 650, 980, 1320, 1660, 2020, 2380, 2740, 3100, 3500],
            }],
            "teamfights": [{
                "start": 900,
                "end": 960,
                "last_death": 950,
                "players": [{
                    "deaths": 2,
                    "deaths_pos": {"120": {"140": 1}, "130": {"150": 1}},
                }],
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)

        self.assertEqual(result["events"]["death_count_observed"], 2)
        self.assertEqual(result["events"]["death_position_count"], 0)
        self.assertTrue(all(not item.get("position") for item in result["events"]["deaths"]))

    def test_zero_opendota_vision_counts_are_available_evidence(self):
        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "purchase_log": [{"time": 760, "key": "bfury"}],
                "lh_t": [0, 5, 10, 16, 22, 28, 34, 40, 46, 52, 58],
                "gold_t": [0, 300, 650, 980, 1320, 1660, 2020, 2380, 2740, 3100, 3500],
                "obs_log": [],
                "sen_log": [],
                "obs_left_log": [],
                "sen_left_log": [],
                "obs_placed": 0,
                "sen_placed": 0,
                "observer_kills": 0,
                "sentry_kills": 0,
                "observer_uses": 0,
                "sentry_uses": 0,
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        sources = {
            item["id"]: item
            for item in result["data_quality"]["evidence_sources"]
        }

        self.assertTrue(result["events"]["has_vision_log"])
        self.assertEqual(sources["vision_events"]["source"], "OpenDota视野事件")
        self.assertEqual(sources["vision_events"]["status"], "available")
        self.assertIn("插眼0个", sources["vision_events"]["coverage"])
        self.assertIn("排眼0个", sources["vision_events"]["coverage"])

    def test_generated_report_shows_evidence_source_coverage(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 1
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "stats": {
                        "lastHitsPerMinute": [5] * 30,
                        "goldPerMinute": [350] * 10 + [600] * 20,
                    },
                    "playbackData": {
                        "purchaseEvents": [{"time": 760, "itemId": 145}],
                        "deathEvents": [{"time": 420}],
                        "playerUpdatePositionEvents": [{"time": 390, "x": 122, "y": 140}],
                    },
                }],
            }
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

            self.assertIn("证据来源与覆盖", html)
            self.assertIn("STRATZ分钟数组", html)
            self.assertIn("STRATZ位置采样", html)
            self.assertIn("覆盖 1/1 次已定位死亡", html)

        generator.REPORT_DIR = old_report_dir

    def test_evidence_sources_mark_zero_death_match_as_not_applicable(self):
        match = self._base_match()
        match["deaths"] = 0
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        sources = {
            item["id"]: item
            for item in result["data_quality"]["evidence_sources"]
        }

        self.assertEqual(sources["deaths"]["source"], "不适用")
        self.assertEqual(sources["deaths"]["status"], "available")
        self.assertEqual(sources["death_positions"]["source"], "不适用")
        self.assertEqual(sources["death_positions"]["status"], "available")

    def test_key_item_post_windows_use_item_specific_conversion_metrics(self):
        match = self._base_match()
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [5] * 10 + [9, 10, 9, 8, 9, 9, 8, 9],
                    "goldPerMinute": [420] * 10 + [650, 700, 680, 660, 690, 710, 700, 720],
                    "towerDamagePerMinute": [0] * 10 + [0, 0, 0, 100, 150, 0, 0, 0],
                    "heroDamagePerMinute": [0] * 18,
                },
                "playbackData": {
                    "purchaseEvents": [
                        {"time": 600, "itemId": 145},
                        {"time": 780, "itemId": 147},
                    ],
                    "killEvents": [{"time": 820}],
                    "assistEvents": [{"time": 850}],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)

        farm_window = result["events"]["post_item_windows"][0]
        self.assertEqual(farm_window["item_name"], "Battle Fury")
        self.assertEqual(farm_window["window_type"], "farm_acceleration")
        self.assertEqual(farm_window["lh_gain"], 45)
        self.assertEqual(farm_window["avg_gpm"], 676.0)

        manta_window = result["events"]["post_item_windows"][1]
        self.assertEqual(manta_window["item_name"], "Manta Style")
        self.assertEqual(manta_window["window_type"], "farm_acceleration")
        self.assertEqual(manta_window["lh_gain"], 43)
        self.assertEqual(manta_window["avg_gpm"], 696.0)

        self.assertNotIn("item_timing", {f["category"] for f in result["review_findings"]})

    def test_review_findings_include_training_goal_and_success_metric(self):
        analysis = analyze_match(self._base_match())

        for finding in analysis["review_findings"]:
            self.assertIn("training_goal", finding)
            self.assertIn("success_metric", finding)
            self.assertTrue(finding["training_goal"])
            self.assertTrue(finding["success_metric"])

    def test_buyback_log_is_linked_to_the_next_death_and_becomes_a_training_rule(self):
        match = self._base_match()
        match["deaths"] = 2
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "player_slot": 1,
                "buyback_count": 1,
                "buyback_log": [{"time": 1200, "slot": 1, "player_slot": 1}],
            }],
        }
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "playbackData": {
                    "deathEvents": [{"time": 600}, {"time": 1254}],
                },
            }],
        }

        result = analyze_match(
            match,
            stratz_data=stratz_data,
            opendota_data=opendota_data,
        )

        self.assertEqual(result["events"]["buyback_source"], "opendota_parsed_logs")
        self.assertEqual(result["events"]["buybacks"][0]["minute"], 20.0)
        self.assertEqual(result["events"]["buyback_death_windows"][0]["redeath_seconds"], 54)
        self.assertTrue(result["events"]["buyback_death_windows"][0]["short_redeath"])
        finding = next(
            item for item in result["review_findings"]
            if item["category"] == "buyback_redeath"
        )
        self.assertEqual(finding["priority"], "high")
        self.assertIn("20.0分买活", finding["evidence"])
        self.assertIn("54秒", finding["evidence"])
        self.assertIn("买活后120秒内再次死亡为0", finding["success_metric"])
        ledger = next(
            item for item in result["data_quality"]["field_ledger"]
            if item["id"] == "buyback_events"
        )
        self.assertEqual(ledger["status"], "available")
        from report.generator import generate_report
        with tempfile.TemporaryDirectory() as output_dir:
            path = generate_report(
                result,
                _generate_fallback_analysis(result),
                output_dir=output_dir,
            )
            html = Path(path).read_text(encoding="utf-8")
        self.assertIn("买活与再次死亡", html)
        self.assertIn("20.0分买活", html)
        self.assertIn("54秒", html)

    def test_missing_buyback_timeline_is_a_blocking_evidence_gap(self):
        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "player_slot": 1,
                "buyback_count": 1,
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)

        self.assertIn("buyback_events", result["data_quality"]["blocking_gaps"])
        ledger = next(
            item for item in result["data_quality"]["field_ledger"]
            if item["id"] == "buyback_events"
        )
        self.assertEqual(ledger["status"], "missing")

    def test_unknown_buyback_count_is_not_reported_as_zero_buybacks(self):
        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        source = next(
            item for item in result["data_quality"]["evidence_sources"]
            if item["id"] == "buyback_events"
        )

        self.assertEqual(source["status"], "missing")
        self.assertIn("未获取买活次数", source["coverage"])

    def test_partial_vision_fields_do_not_invent_a_complete_total(self):
        match = self._base_match()
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "obs_placed": 2,
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        summary = result["events"]["vision_summary"]

        self.assertTrue(summary["available"])
        self.assertIsNone(summary["placed_total"])
        self.assertIsNone(summary["kill_total"])
        self.assertIsNone(result["context"]["team_resource_ranks"]["vision_actions"])
        self.assertIn("观察眼2个", next(
            item["coverage"] for item in result["data_quality"]["evidence_sources"]
            if item["id"] == "vision_events"
        ))

    def test_stratz_destruction_only_vision_data_does_not_invent_zero_wards(self):
        match = self._base_match()
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "wardDestruction": [{"time": 700, "isWard": True}],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        summary = result["events"]["vision_summary"]

        self.assertIsNone(summary["observer_placed"])
        self.assertIsNone(summary["sentry_placed"])
        self.assertIsNone(summary["placed_total"])
        self.assertEqual(summary["kill_total"], 1)

    def test_low_item_conversion_window_becomes_measurable_next_game_goal(self):
        match = self._base_match()
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [6] * 20,
                    "goldPerMinute": [430] * 20,
                    "towerDamagePerMinute": [0] * 20,
                    "heroDamagePerMinute": [0] * 20,
                },
                "playbackData": {
                    "purchaseEvents": [
                        {"time": 600, "itemId": 145},
                        {"time": 780, "itemId": 147},
                    ],
                    "killEvents": [],
                    "assistEvents": [],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)

        item_finding = next(f for f in result["review_findings"] if f["category"] == "item_timing")
        self.assertIn("低刷钱窗口:", item_finding["replay_check"])
        self.assertIn("Manta Style后5分钟30补/430.0GPM", item_finding["replay_check"])
        self.assertIn("Manta Style", item_finding["training_goal"])
        self.assertIn("刷钱装后5分钟", item_finding["success_metric"])
        self.assertIn("补刀不少于40或平均GPM不低于600", item_finding["success_metric"])
        self.assertNotIn("强势装后2分钟", item_finding["success_metric"])

    def test_item_finding_evidence_only_names_windows_that_failed_thresholds(self):
        findings = _build_review_findings({
            "duration_min": 40,
            "role_profile": {"id": "pos1", "lane_farm_sensitive": False},
            "timeline": {},
            "events": {
                "purchases": [{"item_name": "Mage Slayer", "minute": 12.7}],
                "key_purchases": [
                    {"item_name": "Mage Slayer", "minute": 12.7},
                    {"item_name": "Diffusal Blade", "minute": 17.8},
                    {"item_name": "Black King Bar", "minute": 42.3},
                ],
                "post_item_windows": [
                    {
                        "item_name": "Mage Slayer",
                        "minute": 12.7,
                        "window_type": "context_only",
                        "evaluable": False,
                        "summary": "Mage Slayer于12.7分钟完成；该装备没有通用、可核验的固定转化窗口",
                    },
                    {
                        "item_name": "Diffusal Blade",
                        "minute": 17.8,
                        "window_type": "context_only",
                        "evaluable": False,
                        "summary": "Diffusal Blade于17.8分钟完成；该装备没有通用、可核验的固定转化窗口",
                    },
                    {
                        "item_name": "Black King Bar",
                        "minute": 42.3,
                        "window_type": "map_conversion",
                        "evaluable": True,
                        "kills_or_assists": 0,
                        "tower_damage": 0,
                        "summary": "Black King Bar后2分钟参战0次/推塔0",
                    },
                ],
            },
            "kda": {"deaths": 0},
        })

        item_finding = next(item for item in findings if item["category"] == "item_timing")
        self.assertIn("Black King Bar 42.3分钟", item_finding["evidence"])
        self.assertIn("Black King Bar后2分钟参战0次/推塔0", item_finding["evidence"])
        self.assertNotIn("Mage Slayer", item_finding["evidence"])
        self.assertNotIn("Diffusal Blade", item_finding["evidence"])

    def test_purchase_timeline_without_key_items_is_data_quality_not_main_issue(self):
        match = self._base_match()
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [6] * 20,
                    "goldPerMinute": [430] * 20,
                    "towerDamagePerMinute": [0] * 20,
                    "heroDamagePerMinute": [0] * 20,
                },
                "playbackData": {
                    "purchaseEvents": [
                        {"time": 120, "itemId": 2},
                        {"time": 240, "itemId": 3},
                    ],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)

        self.assertNotIn("item_timing", {f["category"] for f in result["review_findings"]})
        self.assertIn(
            "没有识别到关键装备完成点",
            " ".join(result["data_quality"]["limitations"]),
        )

    def test_opendota_metadata_recovers_final_major_item_timings_without_fallback_ids(self):
        match = self._base_match()
        match.update({
            "hero_id": 11,
            "item_0": 152,
            "item_1": 63,
            "item_2": 277,
            "item_3": 236,
            "item_4": 21,
            "item_5": 596,
        })
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 11,
                "player_slot": 1,
                "purchase_log": [
                    {"time": 186, "key": "falcon_blade"},
                    {"time": 365, "key": "power_treads"},
                    {"time": 1013, "key": "yasha_and_kaya"},
                    {"time": 1195, "key": "dragon_lance"},
                    {"time": 1513, "key": "invis_sword"},
                    {"time": 1514, "key": "invis_sword"},
                    {"time": 1688, "key": "ogre_axe"},
                ],
                "lh_t": list(range(36)),
                "gold_t": [minute * 500 for minute in range(36)],
                "kills_log": [],
                "assists_log": [],
                "obs_log": [],
                "sen_log": [],
                "obs_placed": 0,
                "sen_placed": 0,
                "observer_kills": 0,
                "sentry_kills": 0,
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        key_purchases = result["events"]["key_purchases"]

        self.assertEqual(
            [item["item_name"] for item in key_purchases],
            ["Yasha and Kaya", "Dragon Lance", "Shadow Blade"],
        )
        self.assertEqual([item["item_id"] for item in key_purchases], [277, 236, 152])
        self.assertEqual([item["item_cost"] for item in key_purchases], [4200, 1900, 3250])
        self.assertEqual([item["time"] for item in key_purchases], [1013, 1195, 1513])
        self.assertTrue(all(
            item["selection_reason"] == "final_inventory_major_item"
            for item in key_purchases
        ))
        self.assertEqual(
            [item["item_name"] for item in result["events"]["post_item_windows"]],
            ["Yasha and Kaya", "Dragon Lance", "Shadow Blade"],
        )
        self.assertNotIn(
            "没有识别到关键装备完成点",
            " ".join(result["data_quality"]["limitations"]),
        )

    def test_support_utility_items_are_key_purchases(self):
        match = self._base_match()
        match["hero_id"] = 86
        match["hero_name"] = "Rubick"
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 86,
                "player_slot": 128,
                "purchase_log": [
                    {"time": 1342, "key": "aether_lens"},
                    {"time": 1690, "key": "blink"},
                    {"time": 1842, "key": "aghanims_shard"},
                    {"time": 2283, "key": "ultimate_scepter"},
                ],
                "lh_t": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "gold_t": [0, 120, 240, 360, 480, 600, 720, 840, 960, 1080, 1200],
                "obs_log": [],
                "sen_log": [],
                "obs_placed": 0,
                "sen_placed": 0,
                "observer_kills": 0,
                "sentry_kills": 0,
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        names = [item["item_name"] for item in result["events"]["key_purchases"]]

        self.assertEqual(
            names,
            ["Aether Lens", "Blink Dagger", "Aghanim's Shard", "Aghanim's Scepter"],
        )
        self.assertNotIn(
            "没有识别到关键装备完成点",
            " ".join(result["data_quality"]["limitations"]),
        )

    def test_aura_and_teamfight_utility_items_are_key_purchases(self):
        match = self._base_match()
        match["hero_id"] = 55
        match["hero_name"] = "Dark Seer"
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 55,
                "player_slot": 128,
                "purchase_log": [
                    {"time": 945, "key": "mekansm"},
                    {"time": 1004, "key": "guardian_greaves"},
                    {"time": 1771, "key": "octarine_core"},
                ],
                "lh_t": [0, 3, 6, 10, 14, 18, 22, 26, 30, 35, 40],
                "gold_t": [0, 160, 330, 510, 700, 900, 1120, 1360, 1620, 1900, 2200],
                "obs_log": [],
                "sen_log": [],
                "obs_placed": 0,
                "sen_placed": 0,
                "observer_kills": 0,
                "sentry_kills": 0,
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)
        names = [item["item_name"] for item in result["events"]["key_purchases"]]

        self.assertEqual(names, ["Mekansm", "Guardian Greaves", "Octarine Core"])

    def test_death_review_highlights_clusters_and_next_game_death_metric(self):
        match = self._base_match()
        match["deaths"] = 5
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [5] * 40,
                    "goldPerMinute": [400] * 40,
                },
                "playbackData": {
                    "deathEvents": [
                        {"time": 420},
                        {"time": 570},
                        {"time": 930},
                        {"time": 1180},
                        {"time": 1280},
                    ],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)

        death_finding = next(f for f in result["review_findings"] if f["category"] == "death_review")
        self.assertIn("连续死亡簇: 7.0-9.5分钟、15.5-21.3分钟", death_finding["replay_check"])
        self.assertIn("复活后3分钟", death_finding["action"])
        self.assertIn("每10分钟死亡从1.43降到不超过1.1", death_finding["training_goal"])
        self.assertIn("每10分钟死亡不超过1.1", death_finding["success_metric"])
        self.assertIn("连续5分钟内死亡簇不超过1个", death_finding["success_metric"])

    def test_death_review_evidence_lists_all_death_minutes_when_complete(self):
        match = self._base_match()
        match["deaths"] = 8
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [5] * 40,
                    "goldPerMinute": [400] * 40,
                },
                "playbackData": {
                    "deathEvents": [
                        {"time": 420},
                        {"time": 570},
                        {"time": 930},
                        {"time": 1180},
                        {"time": 1280},
                        {"time": 1500},
                        {"time": 1900},
                        {"time": 2300},
                    ],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)

        death_finding = next(f for f in result["review_findings"] if f["category"] == "death_review")
        self.assertIn(
            "时间: 7.0, 9.5, 15.5, 19.7, 21.3, 25.0, 31.7, 38.3分钟",
            death_finding["evidence"],
        )

    def test_timeline_cross_references_deaths_inside_low_efficiency_windows(self):
        match = self._base_match()
        match["deaths"] = 2
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [6] * 10 + [1, 1, 6, 6, 6, 1, 1, 6, 6, 6],
                    "goldPerMinute": [400] * 20,
                },
                "playbackData": {
                    "deathEvents": [
                        {"time": 660},
                        {"time": 960},
                    ],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        overlap = result["timeline"]["death_overlap_windows"][0]

        self.assertEqual(overlap["label"], "低效率窗口 10-12分钟")
        self.assertEqual(overlap["death_minutes"], [11.0])
        overlap_finding = next(f for f in result["review_findings"] if f["category"] == "death_resource_overlap")
        self.assertIn("低效率窗口 10-12分钟含 11.0分死亡", overlap_finding["evidence"])
        self.assertIn("先补回一波安全线", overlap_finding["action"])
        self.assertIn("从2次降到不超过1次", overlap_finding["training_goal"])
        self.assertIn("重叠不超过1次", overlap_finding["success_metric"])

    def test_generated_report_shows_death_overlap_windows(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 1
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "stats": {
                        "lastHitsPerMinute": [6] * 10 + [1, 1, 6, 6, 6],
                        "goldPerMinute": [400] * 15,
                    },
                    "playbackData": {
                        "deathEvents": [{"time": 660}],
                    },
                }],
            }
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

        generator.REPORT_DIR = old_report_dir

        self.assertIn("死亡打断资源窗口", html)
        self.assertIn("低效率窗口 10-12分钟", html)
        self.assertIn("11.0分死亡", html)

    def test_death_recovery_windows_measure_post_death_resources(self):
        match = self._base_match()
        match["deaths"] = 1
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [6] * 10 + [99, 0, 1, 0, 6, 6],
                    "goldPerMinute": [420] * 10 + [999, 120, 150, 130, 420, 430],
                },
                "playbackData": {
                    "deathEvents": [{"time": 600, "timeDead": 1}],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        recovery = result["timeline"]["death_recovery_windows"][0]
        finding = next(f for f in result["review_findings"] if f["category"] == "death_recovery")

        self.assertEqual(recovery["minute"], 10.0)
        self.assertEqual(recovery["window_label"], "11-14分钟")
        self.assertEqual(recovery["window_basis"], "stratz_time_dead")
        self.assertEqual(recovery["lh_gain"], 1)
        self.assertAlmostEqual(recovery["avg_gpm"], 133.3)
        self.assertEqual(recovery["status_label"], "恢复不足")
        self.assertIn("10.0分复活后11-14分钟 1补/133.3平均GPM", finding["evidence"])
        self.assertIn("3分钟内先补到", finding["action"])

    def test_generated_report_shows_death_recovery_windows(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 1
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "stats": {
                        "lastHitsPerMinute": [6] * 10 + [99, 0, 1, 0, 6, 6],
                        "goldPerMinute": [420] * 10 + [999, 120, 150, 130, 420, 430],
                    },
                    "playbackData": {
                        "deathEvents": [{"time": 600, "timeDead": 1}],
                    },
                }],
            }
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

        generator.REPORT_DIR = old_report_dir

        self.assertIn("死亡后恢复窗口", html)
        self.assertIn("10.0分复活后11-14分钟", html)
        self.assertIn("1补", html)
        self.assertIn("平均GPM 133.3", html)
        self.assertIn("恢复不足", html)

    def test_death_recovery_window_stops_at_the_next_real_death(self):
        match = self._base_match()
        match["deaths"] = 2
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [6] * 20,
                    "goldPerMinute": [420] * 20,
                },
                "playbackData": {
                    "deathEvents": [
                        {"time": 600, "timeDead": 1},
                        {"time": 650, "timeDead": 10},
                    ],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        windows = result["timeline"]["death_recovery_windows"]

        self.assertEqual(windows[0]["status"], "interrupted")
        self.assertEqual(windows[0]["redeath_seconds"], 49)
        self.assertIn("复活后49秒再次死亡", windows[0]["evidence_label"])
        self.assertEqual(windows[1]["window_label"], "11-14分钟")
        finding = next(
            item for item in result["review_findings"]
            if item["category"] == "death_recovery"
        )
        self.assertIn("未形成完整资源分钟", finding["evidence"])

    def test_death_resource_deltas_compare_before_and_after_pace(self):
        match = self._base_match()
        match["deaths"] = 1
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [6] * 10 + [1, 1, 1, 6, 6],
                    "goldPerMinute": [500] * 10 + [200, 200, 200, 450, 450],
                },
                "playbackData": {
                    "deathEvents": [{"time": 600}],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        delta = result["timeline"]["death_resource_deltas"][0]

        self.assertEqual(delta["minute"], 10.0)
        self.assertEqual(delta["before_window_label"], "7-10分钟")
        self.assertEqual(delta["after_window_label"], "10-13分钟")
        self.assertEqual(delta["before_lh"], 18)
        self.assertEqual(delta["after_lh"], 3)
        self.assertEqual(delta["before_lh_per_min"], 6.0)
        self.assertEqual(delta["after_lh_per_min"], 1.0)
        self.assertEqual(delta["lh_per_min_delta"], -5.0)
        self.assertEqual(delta["before_avg_gpm"], 500.0)
        self.assertEqual(delta["after_avg_gpm"], 200.0)
        self.assertEqual(delta["avg_gpm_delta"], -300.0)
        self.assertEqual(delta["status"], "declined")
        self.assertEqual(delta["status_label"], "补刀与经济均下降")

    def test_death_resource_deltas_skip_fractional_death_minute(self):
        match = self._base_match()
        match["deaths"] = 1
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [6] * 20,
                    "goldPerMinute": [500] * 20,
                },
                "playbackData": {
                    "deathEvents": [{"time": 810}],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        delta = result["timeline"]["death_resource_deltas"][0]

        self.assertEqual(delta["minute"], 13.5)
        self.assertEqual(delta["before_window_label"], "10-13分钟")
        self.assertEqual(delta["after_window_label"], "14-17分钟")
        self.assertEqual(delta["excluded_partial_minute"], 13)

    def test_death_resource_delta_finding_flags_significant_post_death_drop(self):
        match = self._base_match()
        match["deaths"] = 1
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "stats": {
                    "lastHitsPerMinute": [8] * 10 + [5, 5, 5, 8, 8],
                    "goldPerMinute": [500] * 10 + [650, 650, 650, 700, 700],
                },
                "playbackData": {
                    "deathEvents": [{"time": 600}],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        finding = next(
            item for item in result["review_findings"]
            if item["category"] == "death_resource_delta"
        )

        self.assertEqual(finding["category_label"], "死亡前后资源变化")
        self.assertIn("死亡前后资源下降窗口", finding["evidence"])
        self.assertIn("10.0分死亡前后：补刀/分 8.0→5.0（-3.0）", finding["evidence"])
        self.assertIn("平均GPM 500.0→650.0（+150.0）", finding["evidence"])
        self.assertIn("复活后", finding["action"])
        self.assertIn("不判断死亡原因", finding["replay_check"])
        self.assertIn("从1个降到不超过0个", finding["training_goal"])
        self.assertIn("下降窗口不超过0个", finding["success_metric"])
        self.assertNotIn("从1个压到最多1个", finding["training_goal"])

    def test_generated_report_shows_death_resource_deltas(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 1
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "stats": {
                        "lastHitsPerMinute": [6] * 10 + [1, 1, 1, 6, 6],
                        "goldPerMinute": [500] * 10 + [200, 200, 200, 450, 450],
                    },
                    "playbackData": {
                        "deathEvents": [{"time": 600}],
                    },
                }],
            }
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

        generator.REPORT_DIR = old_report_dir

        self.assertIn("死亡前后资源变化", html)
        self.assertIn("10.0分死亡", html)
        self.assertIn("补刀/分钟 6.0→1.0（-5.0）", html)
        self.assertIn("平均GPM 500.0→200.0（-300.0）", html)
        self.assertIn("补刀与经济均下降", html)
        self.assertIn("变化只描述时间相邻数据，不代表死亡原因", html)

    def test_generated_report_has_mobile_timeline_and_death_review_workbench(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 2
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "stats": {
                        "lastHitsPerMinute": [6] * 10 + [1, 1, 1, 6, 6, 5, 5, 5, 4, 4],
                        "goldPerMinute": [420] * 10 + [120, 150, 130, 420, 430, 410, 410, 410, 390, 390],
                    },
                    "playbackData": {
                        "deathEvents": [{"time": 600}, {"time": 960}],
                        "playerUpdatePositionEvents": [
                            {"time": 600, "x": 122, "y": 140},
                            {"time": 960, "x": 88, "y": 164},
                        ],
                    },
                }],
            }
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

        generator.REPORT_DIR = old_report_dir

        self.assertIn("timeline-phase-cards", html)
        self.assertIn("timeline-phase-card", html)
        self.assertIn("death-review-workbench", html)
        self.assertIn("death-review-summary", html)
        self.assertIn("已定位死亡", html)
        self.assertIn("恢复窗口", html)
        self.assertIn("坐标点", html)

    def test_report_styles_include_mobile_timeline_cards(self):
        with open("report/static/style.css", "r", encoding="utf-8") as f:
            stylesheet = f.read()

        self.assertIn(".timeline-phase-cards", stylesheet)
        self.assertIn(".timeline-phase-card", stylesheet)
        self.assertIn(".death-review-workbench", stylesheet)
        self.assertIn(".death-review-summary", stylesheet)
        self.assertIn(".death-evidence-toolbar", stylesheet)
        self.assertIn(".death-event-card.repeat-position", stylesheet)
        self.assertIn(".death-context-list", stylesheet)
        self.assertIn(".death-context-line", stylesheet)
        self.assertIn("@media (max-width: 720px)", stylesheet)
        self.assertIn("#timeline-diagnosis .timeline-phase-table", stylesheet)
        self.assertIn(".timeline-phase-cards {", stylesheet)

    def test_report_styles_balance_long_hero_title_on_mobile(self):
        with open("report/static/style.css", "r", encoding="utf-8") as f:
            stylesheet = f.read()

        mobile_styles = stylesheet.split("@media (max-width: 720px)", 1)[1]
        self.assertIn(".header h1 {", mobile_styles)
        self.assertIn("font-size: 25px;", mobile_styles)
        self.assertIn("text-wrap: balance;", mobile_styles)
        self.assertIn(".evidence-completeness-chips {", mobile_styles)
        self.assertIn("flex-wrap: wrap;", mobile_styles)
        self.assertIn("overflow-x: visible;", mobile_styles)
        self.assertIn(".report-top-link {", mobile_styles)
        self.assertIn("position: static;", mobile_styles)

    def test_generated_report_versions_stylesheet_with_content_hash(self):
        import hashlib
        from report.generator import generate_report

        analysis = analyze_match(self._base_match())
        expected = hashlib.sha256(Path("report/static/style.css").read_bytes()).hexdigest()[:12]
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_report(
                analysis,
                _generate_fallback_analysis(analysis, "Anti-Mage", True),
                output_dir=tmp,
            )
            html = Path(path).read_text(encoding="utf-8")

        self.assertIn(f'href="static/style.css?v={expected}"', html)

    def test_review_findings_are_structured_and_formula_review_is_limited_to_them(self):
        analysis = analyze_match(self._base_match())

        self.assertTrue(analysis["review_findings"])
        for finding in analysis["review_findings"]:
            for key in ["priority", "category", "evidence", "why_it_matters", "action", "replay_check"]:
                self.assertIn(key, finding)
                self.assertTrue(finding[key])

        review = build_formula_review(analysis)
        source_categories = {item["category"] for item in analysis["review_findings"]}
        self.assertTrue(all(item["category"] in source_categories for item in review["review_points"]))
        for point in review["review_points"]:
            source = next(item for item in analysis["review_findings"] if item["category"] == point["category"])
            self.assertEqual(point["evidence"], source["evidence"])
            self.assertEqual(point["action"], source["action"])

    def test_report_template_contains_new_coaching_sections(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 3
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "stats": {
                        "lastHitsPerMinute": [5] * 30,
                        "goldPerMinute": [400] * 30,
                        "deathEvents": [
                            {
                                "time": event_time,
                                "timeDead": 40,
                                "goldLost": 200,
                                "goldFed": 300,
                                "xpFed": 450,
                            }
                            for event_time in (420, 930, 1280)
                        ],
                    },
                    "playbackData": {
                        "deathEvents": [{"time": 420}, {"time": 930}, {"time": 1280}],
                    },
                }],
            }
            analysis = analyze_match(
                match,
                stratz_data=stratz_data,
                replay_data={
                    "source": "valve_replay_gem",
                    "validation": {
                        "status": "matched",
                        "checks": [{
                            "metric": "deaths",
                            "api_value": 3,
                            "replay_value": 3,
                            "delta": 0,
                            "status": "matched",
                        }],
                    },
                },
            )
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

            for text in ["下一局行动清单", "时间线诊断", "死亡/装备事件", "本局主要问题证据", "数据缺口", "数据公式复盘"]:
                self.assertIn(text, html)
            for text in ["证据源对账", "死亡事件真实成本", "送出 900 金 / 1350 经验"]:
                self.assertIn(text, html)
            for text in ["下一局量化目标", "训练目标", "验收标准", "综合执行分", "分项权重"]:
                self.assertIn(text, html)
            self.assertIn('class="formula-overall-equation"', html)
            for text in [
                'class="skip-link"',
                'aria-label="报告章节"',
                'href="#next-actions"',
                'href="#timeline-diagnosis"',
                'id="next-actions"',
                'id="timeline-diagnosis"',
                'data-report-section-link',
                'IntersectionObserver',
                'track.scrollTo',
            ]:
                self.assertIn(text, html)
            for removed in ["数据对比（vs 基准线）", "改进建议", "AI教练分析", "## Anti-Mage", "### 本局最重要结论"]:
                self.assertNotIn(removed, html)

        generator.REPORT_DIR = old_report_dir

    def test_report_file_name_and_browser_title_start_with_hero_name(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 3
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "stats": {
                        "lastHitsPerMinute": [5] * 30,
                        "goldPerMinute": [400] * 30,
                    },
                    "playbackData": {
                        "deathEvents": [{"time": 420}, {"time": 930}, {"time": 1280}],
                    },
                }],
            }
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

            self.assertTrue(os.path.basename(path).startswith("Anti-Mage_"))
            self.assertIn("<title>Anti-Mage 复盘报告", html)

        generator.REPORT_DIR = old_report_dir

    def test_generated_report_shows_death_position_samples_in_event_section(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 2
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "playbackData": {
                        "deathEvents": [{"time": 420}, {"time": 930}],
                        "playerUpdatePositionEvents": [
                            {"time": 390, "x": 122, "y": 140},
                            {"time": 900, "x": 88, "y": 164},
                        ],
                    },
                }],
            }
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

            self.assertIn("死亡位置", html)
            self.assertIn("x=122,y=140", html)
            self.assertIn("死亡前30秒", html)
            self.assertIn("death-event-card", html)

        generator.REPORT_DIR = old_report_dir

    def test_generated_report_shows_every_death_and_real_replay_killer(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match.update({"deaths": 12, "duration": 3600})
            replay_data = {
                "deaths": [
                    {
                        "time": 120 + index * 240,
                        "killer": "npc_dota_hero_keeper_of_the_light",
                        "position": {"x": 100 + index, "y": 120 + index},
                    }
                    for index in range(12)
                ],
            }
            for death in replay_data["deaths"]:
                death["nearby_context"] = {
                    "source": "valve_replay_all_player_positions",
                    "radius_units": 1600,
                    "sample_resolution_seconds": 2,
                    "sampled_other_players": 9,
                    "allies_within_radius_count": 1,
                    "enemies_within_radius_count": 3,
                    "allies_within_radius": [{"player_id": 1, "hero_id": 5, "distance_units": 800}],
                    "enemies_within_radius": [{"player_id": 5, "hero_id": 44, "distance_units": 400}],
                    "nearest_ally": {"player_id": 1, "hero_id": 5, "distance_units": 800},
                    "nearest_enemy": {"player_id": 5, "hero_id": 44, "distance_units": 400},
                }
            analysis = analyze_match(match, replay_data=replay_data)
            death_finding = next(
                item for item in analysis["review_findings"]
                if item["category"] == "death_review"
            )
            self.assertIn("局部人数覆盖12/12次死亡", death_finding["evidence"])
            self.assertIn("12次敌方人数多于队友", death_finding["evidence"])
            self.assertIn("向最近队友方向撤退", death_finding["action"])
            path = generate_report(analysis, _generate_fallback_analysis(analysis))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

            self.assertEqual(html.count('<div class="death-event-card'), 12)
            self.assertIn("击杀者：Keeper of the Light", html)
            self.assertIn("1600范围内存活队友1人、敌人3人", html)
            self.assertIn("最近队友 Crystal Maiden 800单位", html)
            self.assertIn("最近敌人 Phantom Assassin 400单位", html)
            self.assertIn("46.0分", html)

        generator.REPORT_DIR = old_report_dir

    def test_death_position_samples_build_raw_coordinate_map_points(self):
        match = self._base_match()
        match["deaths"] = 2
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "playbackData": {
                    "deathEvents": [{"time": 420}, {"time": 930}],
                    "playerUpdatePositionEvents": [
                        {"time": 390, "x": 122, "y": 140},
                        {"time": 930, "x": 88, "y": 164},
                    ],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)

        self.assertEqual(result["events"]["death_map_points"][0]["minute"], 7.0)
        self.assertEqual(result["events"]["death_map_points"][0]["x"], 122)
        self.assertEqual(result["events"]["death_map_points"][0]["y"], 140)
        self.assertEqual(result["events"]["death_map_points"][0]["plot_y"], 115)
        self.assertIn("x=122,y=140", result["events"]["death_map_points"][0]["label"])

    def test_death_position_samples_build_repeated_coordinate_clusters(self):
        match = self._base_match()
        match["deaths"] = 3
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "playbackData": {
                    "deathEvents": [{"time": 420}, {"time": 540}, {"time": 930}],
                    "playerUpdatePositionEvents": [
                        {"time": 420, "x": 120, "y": 140},
                        {"time": 540, "x": 126, "y": 144},
                        {"time": 930, "x": 88, "y": 164},
                    ],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        cluster = result["events"]["death_position_clusters"][0]

        self.assertEqual(cluster["death_count"], 2)
        self.assertEqual(cluster["minutes"], [7.0, 9.0])
        self.assertEqual(cluster["center_x"], 123.0)
        self.assertEqual(cluster["center_y"], 142.0)
        self.assertIn("7.0、9.0分", cluster["evidence_label"])
        self.assertIn("中心x=123.0,y=142.0", cluster["evidence_label"])
        self.assertFalse(any(
            item["category"] == "death_position_pattern"
            for item in result["review_findings"]
        ))

    def test_repeated_coordinate_cluster_members_are_marked_for_report_scanning(self):
        match = self._base_match()
        match["deaths"] = 3
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "position": "POSITION_1",
                "role": "CORE",
                "playbackData": {
                    "deathEvents": [{"time": 420}, {"time": 540}, {"time": 930}],
                    "playerUpdatePositionEvents": [
                        {"time": 420, "x": 120, "y": 140},
                        {"time": 540, "x": 126, "y": 144},
                        {"time": 930, "x": 88, "y": 164},
                    ],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data)
        deaths = result["events"]["deaths"]

        self.assertEqual(deaths[0]["position_cluster_label"], "重复簇 #1 中心x=123.0,y=142.0")
        self.assertEqual(deaths[1]["position_cluster_label"], "重复簇 #1 中心x=123.0,y=142.0")
        self.assertNotIn("position_cluster_label", deaths[2])

    def test_generated_report_shows_raw_death_coordinate_map(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 1
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "playbackData": {
                        "deathEvents": [{"time": 420}],
                        "playerUpdatePositionEvents": [{"time": 390, "x": 122, "y": 140}],
                    },
                }],
            }
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

        generator.REPORT_DIR = old_report_dir

        self.assertIn("死亡坐标图", html)
        self.assertIn("death-coordinate-map", html)
        self.assertIn('data-minute="7.0"', html)
        self.assertIn("x=122,y=140", html)
        self.assertIn("原始x/y坐标", html)

    def test_generated_report_shows_repeated_death_coordinate_clusters(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 3
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "playbackData": {
                        "deathEvents": [{"time": 420}, {"time": 540}, {"time": 930}],
                        "playerUpdatePositionEvents": [
                            {"time": 420, "x": 120, "y": 140},
                            {"time": 540, "x": 126, "y": 144},
                            {"time": 930, "x": 88, "y": 164},
                        ],
                    },
                }],
            }
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

        generator.REPORT_DIR = old_report_dir

        self.assertIn("重复死亡坐标簇", html)
        self.assertIn("death-coordinate-clusters", html)
        self.assertIn("中心x=123.0,y=142.0", html)
        self.assertIn("7.0、9.0分", html)
        self.assertIn("不生成地图区域名", html)
        for banned in ["优先回看", "需要回放确认", "可回放复查", "回放确认后的", "回放场景"]:
            self.assertNotIn(banned, html)

    def test_replay_coordinate_clusters_name_the_actual_position_source(self):
        from report.generator import generate_report

        match = self._base_match()
        match["deaths"] = 2
        replay_data = {
            "deaths": [
                {"time": 420, "position": {"x": 120, "y": 140}},
                {"time": 540, "position": {"x": 126, "y": 144}},
            ],
        }
        analysis = analyze_match(match, replay_data=replay_data)

        with tempfile.TemporaryDirectory() as tmp:
            path = generate_report(analysis, build_formula_review(analysis), output_dir=tmp)
            html = Path(path).read_text(encoding="utf-8")

        self.assertIn("Valve回放实体位置采样的原始x/y距离聚类", html)
        self.assertNotIn("只按 STRATZ 原始x/y距离聚类", html)

    def test_generated_report_highlights_repeated_coordinate_death_cards(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 3
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "playbackData": {
                        "deathEvents": [{"time": 420}, {"time": 540}, {"time": 930}],
                        "playerUpdatePositionEvents": [
                            {"time": 420, "x": 120, "y": 140},
                            {"time": 540, "x": 126, "y": 144},
                            {"time": 930, "x": 88, "y": 164},
                        ],
                    },
                }],
            }
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

        generator.REPORT_DIR = old_report_dir

        self.assertIn("death-evidence-toolbar", html)
        self.assertIn('href="#death-event-list"', html)
        self.assertIn('href="#death-coordinate-map"', html)
        self.assertIn('href="#death-coordinate-clusters"', html)
        self.assertIn('death-event-card repeat-position', html)
        self.assertIn("重复坐标", html)
        self.assertIn("重复簇 #1 中心x=123.0,y=142.0", html)

    def test_generated_report_avoids_raw_less_than_signs_in_metric_text(self):
        from report.generator import generate_report
        import report.generator as generator

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            match = self._base_match()
            match["deaths"] = 3
            stratz_data = {
                "players": [{
                    "steamAccount": {"id": 173776719},
                    "isRadiant": True,
                    "hero": {"id": 1, "displayName": "Anti-Mage"},
                    "position": "POSITION_1",
                    "role": "CORE",
                    "stats": {
                        "lastHitsPerMinute": [5] * 30,
                        "goldPerMinute": [400] * 30,
                    },
                    "playbackData": {
                        "deathEvents": [{"time": 420}, {"time": 930}, {"time": 1280}],
                    },
                }],
            }
            analysis = analyze_match(match, stratz_data=stratz_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

            self.assertNotIn("<=1", html)
            self.assertNotIn("<=2", html)
            self.assertIn("不超过", html)

        generator.REPORT_DIR = old_report_dir

    def test_generated_report_uses_system_evidence_not_manual_review_language(self):
        from report.generator import generate_report
        import report.generator as generator

        match = self._base_match()
        match["deaths"] = 3
        match["player_slot"] = 1
        opendota_data = {
            "players": [
                {"account_id": 1, "hero_id": 2, "player_slot": 0},
                {
                    "account_id": 173776719,
                    "hero_id": 1,
                    "player_slot": 1,
                    "purchase_log": [{"time": 760, "key": "bfury"}],
                    "kills_log": [{"time": 1240, "key": "npc_dota_hero_sniper"}],
                    "lh_t": [0, 5, 10, 16, 22, 28, 34, 40, 46, 52, 58],
                    "gold_t": [0, 300, 650, 980, 1320, 1660, 2020, 2380, 2740, 3100, 3500],
                },
            ],
            "teamfights": [{
                "start": 920,
                "end": 960,
                "last_death": 948,
                "players": [
                    {"deaths": 0, "deaths_pos": {}},
                    {"deaths": 1, "deaths_pos": {"120": {"140": 1}}},
                ],
            }],
        }

        old_report_dir = generator.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generator.REPORT_DIR = tmp
            analysis = analyze_match(match, opendota_data=opendota_data)
            path = generate_report(analysis, _generate_fallback_analysis(analysis, "Anti-Mage", True))
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

            self.assertIn("已定位 1/3 次死亡", html)
            for banned in ["人工", "手动", "回看", "回顾", "需要回放确认", "等待 OpenDota", "等待自动解析", "推断", "推测", "可能"]:
                self.assertNotIn(banned, html)
            self.assertIn("Valve回放全员位置与生命状态采样", html)

        generator.REPORT_DIR = old_report_dir

    def test_opendota_parsed_logs_create_events_without_manual_review(self):
        match = self._base_match()
        opendota_data = {
            "match_id": 123,
            "version": 1,
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "purchase_log": [
                    {"time": 745, "key": "bfury"},
                    {"time": 1385, "key": "black_king_bar"},
                ],
                "death_log": [
                    {"time": 930},
                    {"time": 1540},
                ],
                "kills_log": [{"time": 1240, "key": "npc_dota_hero_sniper"}],
                "lh_t": [0, 3, 8, 13, 18, 24, 30, 35, 41, 47, 54, 65, 78],
                "gold_t": [0, 250, 530, 850, 1160, 1450, 1780, 2130, 2460, 2800, 3200, 3820, 4470],
                "xp_t": [0, 160, 380, 620, 910],
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)

        self.assertEqual(result["timeline"]["ten_min_last_hits"], 54)
        self.assertEqual(result["events"]["purchases"][0]["item_name"], "Battle Fury")
        self.assertEqual(result["events"]["deaths"][0]["minute"], 15.5)
        self.assertIn("opendota_parsed_logs", result["data_quality"]["available"])
        joined_actions = " ".join(f["action"] + f["replay_check"] for f in result["review_findings"])
        self.assertNotIn("人工", joined_actions)
        self.assertNotIn("需要回放确认", joined_actions)

    def test_opendota_teamfights_provide_death_events_when_death_log_missing(self):
        match = self._base_match()
        match["player_slot"] = 1
        match["deaths"] = 1
        opendota_data = {
            "players": [
                {"account_id": 1, "hero_id": 2, "player_slot": 0},
                {
                    "account_id": 173776719,
                    "hero_id": 1,
                    "player_slot": 1,
                    "purchase_log": [{"time": 700, "key": "bfury"}],
                    "lh_t": [0, 5, 10, 16, 22, 28, 34, 40, 46, 52, 58],
                    "gold_t": [0, 300, 650, 980, 1320, 1660, 2020, 2380, 2740, 3100, 3500],
                },
            ],
            "teamfights": [{
                "start": 920,
                "end": 960,
                "last_death": 948,
                "players": [
                    {"deaths": 0, "deaths_pos": {}},
                    {"deaths": 1, "deaths_pos": {"120": {"140": 1}}},
                ],
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)

        self.assertEqual(result["events"]["deaths"][0]["minute"], 15.8)
        self.assertEqual(result["events"]["deaths"][0]["source"], "opendota_teamfights")
        self.assertIn("fight_log", result["data_quality"]["available"])

    def test_opponent_kill_logs_reconstruct_complete_personal_death_timeline(self):
        match = self._base_match()
        match["deaths"] = 2
        match["player_slot"] = 1
        opendota_data = {
            "players": [
                {
                    "account_id": 173776719,
                    "hero_id": 1,
                    "player_slot": 1,
                },
                {
                    "account_id": 2,
                    "hero_id": 2,
                    "player_slot": 128,
                    "kills_log": [
                        {"time": 420, "key": "npc_dota_hero_antimage"},
                    ],
                },
                {
                    "account_id": 3,
                    "hero_id": 3,
                    "player_slot": 129,
                    "kills_log": [
                        {"time": 930, "key": "npc_dota_hero_antimage"},
                    ],
                },
            ],
        }

        result = analyze_match(match, opendota_data=opendota_data)

        deaths = result["events"]["deaths"]
        self.assertEqual([item["minute"] for item in deaths], [7.0, 15.5])
        self.assertEqual([item["killer_hero_id"] for item in deaths], [2, 3])
        self.assertTrue(all(item["source"] == "opendota_opponent_kill_logs" for item in deaths))
        self.assertEqual(result["events"]["death_coverage_label"], "已定位 2/2 次死亡")
        self.assertTrue(result["events"]["death_timeline_complete"])
        self.assertFalse(any(
            "死亡时间线不完整" in item
            for item in result["data_quality"]["limitations"]
        ))

    def test_stratz_death_events_fill_opendota_death_log_gap(self):
        match = self._base_match()
        match["deaths"] = 2
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "purchase_log": [{"time": 760, "key": "bfury"}],
                "lh_t": [0, 5, 10, 16, 22, 28, 34, 40, 46, 52, 58],
                "gold_t": [0, 300, 650, 980, 1320, 1660, 2020, 2380, 2740, 3100, 3500],
            }],
        }
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "playbackData": {
                    "deathEvents": [{"time": 420}, {"time": 930}],
                    "killEvents": [{"time": 1240}],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data, opendota_data=opendota_data)

        self.assertEqual([item["minute"] for item in result["events"]["deaths"]], [7.0, 15.5])
        self.assertEqual(result["events"]["death_coverage_label"], "已定位 2/2 次死亡")
        self.assertIn("stratz_playback", result["events"]["source"])

    def test_complete_stratz_death_timeline_beats_partial_opendota_log(self):
        match = self._base_match()
        match["deaths"] = 2
        opendota_data = {
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
                "death_log": [{"time": 420}],
            }],
        }
        stratz_data = {
            "players": [{
                "steamAccount": {"id": 173776719},
                "isRadiant": True,
                "hero": {"id": 1, "displayName": "Anti-Mage"},
                "playbackData": {
                    "deathEvents": [{"time": 420}, {"time": 930}],
                },
            }],
        }

        result = analyze_match(match, stratz_data=stratz_data, opendota_data=opendota_data)

        self.assertEqual([item["minute"] for item in result["events"]["deaths"]], [7.0, 15.5])
        self.assertEqual(result["events"]["death_coverage_label"], "已定位 2/2 次死亡")
        self.assertIn("stratz_playback", result["events"]["source"])

    def test_valve_replay_deaths_fill_public_api_gap(self):
        match = self._base_match()
        match["deaths"] = 2
        opendota_data = {
            "replay_death_events": [
                {"time": 477, "targetname": "npc_dota_hero_antimage"},
                {"time": 930, "targetname": "npc_dota_hero_antimage"},
            ],
            "players": [{
                "account_id": 173776719,
                "hero_id": 1,
                "player_slot": 1,
            }],
        }

        result = analyze_match(match, opendota_data=opendota_data)

        self.assertEqual([item["minute"] for item in result["events"]["deaths"]], [8.0, 15.5])
        self.assertEqual(result["events"]["death_coverage_label"], "已定位 2/2 次死亡")
        self.assertIn("valve_replay", result["events"]["source"])

    def test_replay_life_state_fills_each_death_duration_without_fake_zero_costs(self):
        match = self._base_match()
        match["deaths"] = 1
        replay_data = {
            "deaths": [{
                "time": 420,
                "time_dead": 37,
                "respawn_observed_at": 457,
                "time_dead_source": "valve_replay_life_state",
                "time_dead_resolution_seconds": 1,
            }],
            "performance": {"life_state_dead": 37},
        }

        result = analyze_match(match, replay_data=replay_data)

        death = result["events"]["deaths"][0]
        summary = result["events"]["death_cost_summary"]
        finding = next(
            item for item in result["review_findings"]
            if item["category"] == "death_review"
        )
        self.assertEqual(death["time_dead"], 37)
        self.assertEqual(death["respawn_observed_at"], 457)
        self.assertEqual(summary["total_dead_seconds"], 37)
        self.assertEqual(summary["time_covered_deaths"], 1)
        self.assertIsNone(summary["total_gold_lost"])
        self.assertFalse(summary["gold_lost_available"])
        self.assertEqual(summary["source"], "Valve回放逐秒生命状态")
        self.assertIn("死亡时长0分37秒", finding["evidence"])
        self.assertNotIn("丢失0金", finding["evidence"])
        self.assertNotIn("给出0金/0经验", finding["evidence"])
        self.assertNotIn("可量化金钱/经验", finding["why_it_matters"])
        self.assertIn("可行动时间", finding["why_it_matters"])
        self.assertIn("系统已自动对齐", finding["replay_check"])
        self.assertIn("逐次死亡时长", finding["replay_check"])
        self.assertNotIn("优先检查装备冷却", finding["replay_check"])
        self.assertNotIn("队友距离", finding["replay_check"])

        from report.generator import generate_report

        with tempfile.TemporaryDirectory() as tmp:
            path = generate_report(
                result,
                build_formula_review(result),
                output_dir=tmp,
            )
            html = Path(path).read_text(encoding="utf-8")
        self.assertIn("死亡 37 秒", html)
        self.assertNotIn("丢失 0 金", html)
        self.assertNotIn("送出 0 金 / 0 经验", html)
        self.assertNotIn("None", html)

        primary_training_goal = select_formula_findings(result)[0]["training_goal"]
        self.assertEqual(html.count(primary_training_goal), 1)

    def test_replay_position_without_sample_delta_is_not_labeled_death_time(self):
        match = self._base_match()
        match["deaths"] = 1
        replay_data = {
            "deaths": [{
                "time": 420,
                "position": {"x": 100.0, "y": 120.0},
            }],
        }

        result = analyze_match(match, replay_data=replay_data)
        death = result["events"]["deaths"][0]

        self.assertNotIn("position_sample_age_seconds", death)
        self.assertIn("采样时间差未返回", death["position_label"])
        self.assertNotIn("死亡时", death["position_label"])

    def test_report_marks_unfinished_final_death_duration_as_a_lower_bound(self):
        match = self._base_match()
        match["deaths"] = 1
        replay_data = {
            "deaths": [{
                "time": 2040,
                "time_dead": 60,
                "time_dead_source": "valve_replay_life_state",
            }],
            "performance": {"life_state_dead": 60},
        }
        analysis = analyze_match(match, replay_data=replay_data)

        from report.generator import generate_report

        with tempfile.TemporaryDirectory() as tmp:
            path = generate_report(analysis, build_formula_review(analysis), output_dir=tmp)
            html = Path(path).read_text(encoding="utf-8")

        self.assertIn("回放终局前至少死亡 60 秒", html)

    def test_missing_event_data_names_public_data_gap_not_user_manual_review(self):
        analysis = analyze_match(self._base_match())
        text = str(build_formula_review(analysis))

        self.assertNotIn("人工回看", text)
        self.assertNotIn("人工查看", text)

    def test_formula_review_contains_no_inference_or_manual_review_language(self):
        analysis = analyze_match(self._base_match())
        text = str(build_formula_review(analysis))

        for marker in ("推测", "猜测", "人工回看", "手动检查"):
            self.assertNotIn(marker, text)

    def test_formula_review_is_always_deterministic(self):
        analysis = analyze_match(self._base_match())
        first = build_formula_review(analysis)
        second = build_formula_review(analysis)

        self.assertEqual(first, second)
        self.assertEqual(first["analysis_mode"], "deterministic_formula")

    def test_saved_opendota_detail_round_trips_as_json(self):
        old_db_path = schema.DB_PATH
        old_data_dir = schema.DATA_DIR
        with tempfile.TemporaryDirectory() as tmp:
            schema.DATA_DIR = tmp
            schema.DB_PATH = os.path.join(tmp, "dota2.db")
            schema.init_db()
            schema.save_opendota_detail(123, {"players": [{"purchase_log": [{"time": 10, "key": "bfury"}]}]})

            saved = schema.get_opendota_detail(123)

            self.assertEqual(saved["players"][0]["purchase_log"][0]["key"], "bfury")

        schema.DB_PATH = old_db_path
        schema.DATA_DIR = old_data_dir

    def test_player_match_save_is_unique_per_account_and_match(self):
        old_db_path = schema.DB_PATH
        old_data_dir = schema.DATA_DIR
        with tempfile.TemporaryDirectory() as tmp:
            schema.DATA_DIR = tmp
            schema.DB_PATH = os.path.join(tmp, "dota2.db")
            schema.init_db()
            match = self._base_match()
            schema.save_match(match)
            schema.save_player_match(match)
            updated = dict(match)
            updated["kills"] = 9
            schema.save_player_match(updated)

            rows = schema.get_recent_matches_from_db(173776719, limit=10)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["match_id"], match["match_id"])
            self.assertEqual(rows[0]["kills"], 9)

        schema.DB_PATH = old_db_path
        schema.DATA_DIR = old_data_dir

    def test_saved_stratz_detail_accepts_dict_and_round_trips_as_json(self):
        old_db_path = schema.DB_PATH
        old_data_dir = schema.DATA_DIR
        with tempfile.TemporaryDirectory() as tmp:
            schema.DATA_DIR = tmp
            schema.DB_PATH = os.path.join(tmp, "dota2.db")
            schema.init_db()
            schema.save_stratz_detail(456, {"players": [{"playbackData": {"deathEvents": [{"time": 60}]}}]})

            saved = schema.get_stratz_detail(456)

            self.assertEqual(saved["players"][0]["playbackData"]["deathEvents"][0]["time"], 60)

        schema.DB_PATH = old_db_path
        schema.DATA_DIR = old_data_dir

    def test_stratz_cache_survives_live_fetch_failure(self):
        old_db_path = schema.DB_PATH
        old_data_dir = schema.DATA_DIR
        with tempfile.TemporaryDirectory() as tmp:
            schema.DATA_DIR = tmp
            schema.DB_PATH = os.path.join(tmp, "dota2.db")
            schema.init_db()
            schema.save_stratz_detail(789, {"players": [{"hero": {"displayName": "Anti-Mage"}}]})

            saved = schema.get_stratz_detail(789)

            self.assertEqual(saved["players"][0]["hero"]["displayName"], "Anti-Mage")

        schema.DB_PATH = old_db_path
        schema.DATA_DIR = old_data_dir


if __name__ == "__main__":
    unittest.main()
