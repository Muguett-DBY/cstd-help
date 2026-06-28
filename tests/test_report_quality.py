import json
import os
import tempfile
import unittest

import analysis.ai_analyst as ai_analyst
from analysis.ai_analyst import _build_analysis_prompt, _generate_fallback_analysis, _is_ai_response_safe
from analysis.analyzer import _item_detail, analyze_match, get_hero_name
import db.schema as schema


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
        self.assertEqual(result["context"]["lane"], "SAFE_LANE")
        self.assertIn("Axe", result["context"]["enemy_heroes"])
        self.assertEqual(result["skills"]["upgrades"][0]["abilityId"], 5003)
        self.assertIn("stratz_player_detail", result["data_quality"]["available"])
        self.assertGreaterEqual(result["data_quality"]["score"], 60)

    def test_prompt_is_evidence_driven_and_names_data_gaps(self):
        analysis = analyze_match(self._base_match())
        prompt = _build_analysis_prompt(analysis, "Anti-Mage", True)

        self.assertIn("数据完整性", prompt)
        self.assertIn("LH/min", prompt)
        self.assertIn("伤害/分钟", prompt)
        self.assertIn("最终装备", prompt)
        self.assertIn("不要编造", prompt)
        self.assertIn("缺少10分钟补刀/经济时间线", prompt)

    def test_fallback_analysis_uses_limitations_and_priority_actions(self):
        analysis = analyze_match(self._base_match())
        text = _generate_fallback_analysis(analysis, "Anti-Mage", True)

        self.assertIn("数据完整度", text)
        self.assertIn("下一局只盯这几件事", text)
        self.assertIn("LH/min", text)
        self.assertNotIn("整体表现不错，继续保持", text)

    def test_fallback_analysis_does_not_call_high_death_game_survivable(self):
        analysis = analyze_match(self._base_match())
        text = _generate_fallback_analysis(analysis, "Anti-Mage", True)

        self.assertIn("当前最影响胜负的是死亡成本", text)
        self.assertNotIn("核心指标没有暴露单点崩盘", text)
        self.assertNotIn("生存能力强", text)

    def test_fallback_analysis_names_top_finding_instead_of_generic_summary(self):
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
        text = _generate_fallback_analysis(analysis, "Beastmaster", True)

        self.assertIn("本局优先复盘死亡成本", text)
        self.assertNotIn("核心指标没有暴露单点崩盘", text)
        self.assertNotIn("生存能力强", text)

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
        self.assertIn("item_timing", categories)

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
                    "lastHitsPerMinute": [5] * 10 + [9, 10, 9, 8, 9, 9, 8],
                    "goldPerMinute": [420] * 10 + [650, 700, 680, 660, 690, 710, 700],
                    "towerDamagePerMinute": [0] * 10 + [0, 0, 0, 100, 150, 0, 0],
                    "heroDamagePerMinute": [0] * 17,
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

        power_window = result["events"]["post_item_windows"][1]
        self.assertEqual(power_window["item_name"], "Manta Style")
        self.assertEqual(power_window["window_type"], "map_conversion")
        self.assertEqual(power_window["kills_or_assists"], 2)
        self.assertEqual(power_window["tower_damage"], 250)

        self.assertNotIn("item_timing", {f["category"] for f in result["review_findings"]})

    def test_review_findings_include_training_goal_and_success_metric(self):
        analysis = analyze_match(self._base_match())

        for finding in analysis["review_findings"]:
            self.assertIn("training_goal", finding)
            self.assertIn("success_metric", finding)
            self.assertTrue(finding["training_goal"])
            self.assertTrue(finding["success_metric"])

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
        self.assertIn("低转化窗口: Manta Style后2分钟参战0次/推塔0", item_finding["replay_check"])
        self.assertIn("Manta Style", item_finding["training_goal"])
        self.assertIn("强势装后2分钟", item_finding["success_metric"])
        self.assertIn("参战>=1或推塔伤害>=300", item_finding["success_metric"])

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
        self.assertIn("死亡压到", death_finding["training_goal"])
        self.assertIn("连续5分钟内死亡簇=0", death_finding["success_metric"])

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

    def test_review_findings_are_structured_and_prompt_is_limited_to_them(self):
        analysis = analyze_match(self._base_match())

        self.assertTrue(analysis["review_findings"])
        for finding in analysis["review_findings"]:
            for key in ["priority", "category", "evidence", "why_it_matters", "action", "replay_check"]:
                self.assertIn(key, finding)
                self.assertTrue(finding[key])

        prompt = _build_analysis_prompt(analysis, "Anti-Mage", True)
        self.assertIn("review_findings", prompt)
        self.assertIn("不得新增未在 review_findings 出现的问题", prompt)
        self.assertNotIn("职业选手平均", prompt)

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

            for text in ["下一局行动清单", "时间线诊断", "死亡/装备事件", "本局主要问题证据", "数据缺口", "教练总结"]:
                self.assertIn(text, html)
            for text in ["下一局量化目标", "训练目标", "验收标准"]:
                self.assertIn(text, html)
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
            for banned in ["人工", "手动", "回放", "回顾", "需要回放确认", "等待 OpenDota", "等待自动解析", "推断", "推测", "可能"]:
                self.assertNotIn(banned, html)

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

    def test_missing_event_data_names_public_data_gap_not_user_manual_review(self):
        analysis = analyze_match(self._base_match())
        text = _generate_fallback_analysis(analysis, "Anti-Mage", True)

        self.assertIn("公共数据源", text)
        self.assertNotIn("人工回看", text)
        self.assertNotIn("人工查看", text)

    def test_ai_response_with_inference_or_manual_replay_language_is_rejected(self):
        analysis = analyze_match(self._base_match())
        unsafe = "基于860 GPM推测你方经济领先，你需要优先回放这些时间点并回顾站位。"
        safe = "本局最重要结论：证据来自 review_findings。系统检查已定位 2/2 次死亡。"

        self.assertFalse(_is_ai_response_safe(unsafe, analysis))
        self.assertTrue(_is_ai_response_safe(safe, analysis))

    def test_ai_analysis_defaults_to_deterministic_fallback(self):
        analysis = analyze_match(self._base_match())
        old_value = ai_analyst.ENABLE_FREEFORM_AI
        try:
            ai_analyst.ENABLE_FREEFORM_AI = False
            text = ai_analyst.analyze_with_ai(analysis, "Anti-Mage", True)
        finally:
            ai_analyst.ENABLE_FREEFORM_AI = old_value

        self.assertIn("下一局只盯这几件事", text)
        self.assertNotIn("推测", text)
        self.assertNotIn("回放", text)

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
