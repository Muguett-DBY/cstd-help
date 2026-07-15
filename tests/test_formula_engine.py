import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _analysis_fixture():
    return {
        "duration_min": 40,
        "role_profile": {"id": "pos1", "label": "1号位"},
        "timeline": {
            "available": True,
            "ten_min_last_hits": 52,
            "last_hits_by_minute": [5] * 40,
            "gold_by_minute": [500] * 40,
            "experience_by_minute": [600] * 40,
            "low_efficiency_windows": [{"start_minute": 20, "end_minute": 23}],
            "death_resource_deltas": [{
                "death_time": 1440,
                "minute": 24.0,
                "lh_per_min_delta": -3.0,
                "avg_gpm_delta": -200.0,
            }],
        },
        "events": {
            "deaths": [{"minute": 24.0}, {"minute": 31.0}],
            "death_objective_windows": [{"death_minute": 24.0, "outcome": "lost"}],
            "post_item_windows": [{"classification": "low_conversion", "evaluable": True}],
        },
        "performance_context": {
            "lane_efficiency_pct": 68,
            "teamfight_participation_pct": 54,
            "dead_time_share_pct": 11.5,
        },
        "opendota_benchmarks": {
            "metrics": [
                {"id": "gold_per_min", "percentile": 72},
                {"id": "xp_per_min", "percentile": 65},
                {"id": "last_hits_per_min", "percentile": 74},
                {"id": "hero_damage_per_min", "percentile": 58},
                {"id": "tower_damage", "percentile": 61},
            ],
        },
        "extended_metrics": {
            "available": True,
            "combat": {"stuns_seconds": 8.4, "hero_damage_taken": 22000},
            "activity": {"actions_per_min": 278, "camps_stacked": 1},
            "objectives": {"tower_kills": 2, "roshan_kills": 0},
        },
        "data_quality": {"score": 100, "limitations": []},
        "review_findings": [
            {
                "priority": "medium",
                "category": "item_timing",
                "category_label": "装备后转化",
                "evidence": "关键装备后2分钟没有参战或推塔事件。",
                "why_it_matters": "强势期没有转成地图收益。",
                "action": "下一局关键装备完成后2分钟内推塔或参战。",
                "replay_check": "系统检查真实购买、参战和推塔事件。",
                "training_goal": "关键装备后立刻执行地图动作。",
                "success_metric": "关键装备后2分钟内至少1次参战或推塔。",
            },
            {
                "priority": "high",
                "category": "death_objective_window",
                "category_label": "死亡目标成本",
                "evidence": "24.0分死亡后90秒内丢失1个地图目标。",
                "why_it_matters": "死亡直接让出目标窗口。",
                "action": "下一局目标前90秒避免无收益死亡。",
                "replay_check": "系统检查真实死亡和目标事件。",
                "training_goal": "目标前死亡降为0次。",
                "success_metric": "目标前90秒死亡=0。",
            },
        ],
    }


class FormulaEngineTests(unittest.TestCase):
    def _engine(self):
        try:
            from analysis.formula_engine import build_formula_review
        except ImportError as exc:
            self.fail(f"deterministic formula engine is missing: {exc}")
        return build_formula_review

    def test_formula_review_is_repeatable_and_exposes_equations(self):
        build_formula_review = self._engine()
        analysis = _analysis_fixture()

        first = build_formula_review(analysis)
        second = build_formula_review(analysis)

        self.assertEqual(first, second)
        self.assertEqual(first["analysis_mode"], "deterministic_formula")
        self.assertIn("overall_equation", first)
        self.assertEqual(len(first["overall_inputs"]), len(first["scorecards"]))
        self.assertGreaterEqual(len(first["scorecards"]), 4)
        for card in first["scorecards"]:
            self.assertIn("formula_id", card)
            self.assertIn("equation", card)
            self.assertTrue(card["inputs"])
            self.assertGreaterEqual(card["score"], 0)
            self.assertLessEqual(card["score"], 100)

    def test_formula_ranking_prioritizes_measured_death_objective_cost(self):
        review = self._engine()(_analysis_fixture())

        self.assertEqual(review["review_points"][0]["category"], "death_objective_window")
        self.assertGreater(review["review_points"][0]["formula_score"], review["review_points"][1]["formula_score"])
        input_ids = {
            item["id"]
            for item in review["review_points"][0]["formula_inputs"]
        }
        self.assertIn("linked_objective_deaths", input_ids)
        self.assertIn("objective_severity_weight", input_ids)
        self.assertIn("impact_points", input_ids)
        self.assertEqual(
            review["next_actions"][0]["action"],
            "下一局目标前90秒避免无收益死亡。",
        )

    def test_death_objective_priority_uses_cumulative_focus_window_weight(self):
        analysis = _analysis_fixture()
        analysis["events"]["death_objective_windows"] = [
            {"death_time": 1620, "objective_kind": "barracks"},
            {"death_time": 1620, "objective_kind": "barracks"},
            {"death_time": 1620, "objective_kind": "tower"},
            {"death_time": 1860, "objective_kind": "ancient"},
        ]
        analysis["events"]["death_objective_drill"] = {
            "focus_severity_points": 13,
        }

        review = self._engine()(analysis)
        point = next(
            item for item in review["review_points"]
            if item["category"] == "death_objective_window"
        )
        severity = next(
            item for item in point["formula_inputs"]
            if item["id"] == "objective_severity_weight"
        )

        self.assertEqual(severity["value"], 13)
        self.assertIn("同一死亡窗口累计目标权重", severity["label"])
        self.assertIn("累计目标权重", point["formula"])

    def test_missing_inputs_are_omitted_instead_of_estimated(self):
        analysis = _analysis_fixture()
        analysis["performance_context"] = {}
        analysis["opendota_benchmarks"] = {"metrics": []}

        review = self._engine()(analysis)

        self.assertTrue(review["unscored_dimensions"])
        serialized = str(review)
        self.assertNotIn("estimated", serialized.lower())
        self.assertNotIn("推断", serialized)

    def test_support_vision_rate_is_not_scored_without_real_duration(self):
        analysis = _analysis_fixture()
        analysis["duration_min"] = None
        analysis["role_profile"] = {"id": "support", "label": "辅助"}
        analysis["events"].update({
            "has_vision_log": True,
            "vision_source": "Valve回放",
            "observer_wards": [{"time": 120}],
            "sentry_wards": [{"time": 240}],
        })

        review = self._engine()(analysis)
        role_card = next(card for card in review["scorecards"] if card["id"] == "role_execution")
        input_ids = {item["id"] for item in role_card["inputs"]}

        self.assertNotIn("vision_events_per_10", input_ids)
        self.assertNotIn("vision_training_target", input_ids)
        self.assertNotIn("每10分钟视野动作达成率", role_card["equation"])

    def test_finding_scores_do_not_replace_missing_inputs_with_zero(self):
        cases = (
            ("death_review", "dead_time_share_pct"),
            ("lane_farm", "lane_efficiency_gap"),
            ("map_impact", "teamfight_participation_gap"),
        )
        for category, forbidden_input in cases:
            analysis = _analysis_fixture()
            analysis["performance_context"] = {}
            analysis["data_quality"] = {}
            analysis["review_findings"] = [{
                "priority": "medium",
                "category": category,
                "category_label": category,
                "evidence": "仅使用已返回事件。",
                "why_it_matters": "用于回归测试。",
                "action": "执行可记录动作。",
                "replay_check": "系统检查真实事件。",
                "training_goal": "减少问题窗口。",
                "success_metric": "问题窗口下降。",
            }]

            with self.subTest(category=category):
                review = self._engine()(analysis)
                inputs = {
                    item["id"]
                    for item in review["review_points"][0]["formula_inputs"]
                }
                self.assertNotIn(forbidden_input, inputs)
                self.assertNotIn("evidence_completeness", inputs)

    def test_survival_score_counts_unique_objective_deaths_and_real_resource_drops(self):
        analysis = _analysis_fixture()
        analysis["events"]["death_objective_windows"] = [
            {"death_time": 1440, "objective_kind": "tower"},
            {"death_time": 1440, "objective_kind": "barracks"},
        ]

        review = self._engine()(analysis)
        survival = next(card for card in review["scorecards"] if card["id"] == "survival")
        inputs = {item["id"]: item["value"] for item in survival["inputs"]}

        self.assertEqual(inputs["death_objective_losses"], 1)
        self.assertEqual(inputs["death_resource_drops"], 1)
        self.assertIn("1x12", survival["equation"])
        self.assertIn("1x8", survival["equation"])

    def test_death_resource_overlap_priority_uses_overlap_deaths_not_delta_windows(self):
        analysis = _analysis_fixture()
        analysis["timeline"]["death_overlap_windows"] = [
            {"death_minutes": [24.0, 25.0]},
            {"death_minutes": [31.0]},
        ]
        analysis["timeline"]["death_resource_deltas"] = [{
            "minute": 24.0,
            "lh_per_min_delta": -3.0,
            "avg_gpm_delta": -200.0,
        }]
        analysis["events"]["death_objective_windows"] = []
        analysis["review_findings"] = [{
            "priority": "high",
            "category": "death_resource_overlap",
            "category_label": "死亡打断资源",
            "evidence": "3次死亡与低效率窗口重叠。",
            "why_it_matters": "死亡打断资源连续性。",
            "action": "复活后先恢复资源。",
            "replay_check": "系统对齐真实死亡和分钟数组。",
            "training_goal": "减少重叠死亡。",
            "success_metric": "死亡与低效率窗口重叠=0。",
        }]

        review = self._engine()(analysis)
        point = review["review_points"][0]
        inputs = {item["id"]: item["value"] for item in point["formula_inputs"]}

        self.assertEqual(inputs["death_resource_overlap_deaths"], 3)
        self.assertIn("重叠死亡数", point["formula"])

    def test_conversion_score_excludes_context_and_missing_data_windows(self):
        analysis = _analysis_fixture()
        analysis["events"]["post_item_windows"] = [
            {"classification": "converted", "evaluable": True},
            {"classification": "low_conversion", "evaluable": True},
            {"classification": "context_only", "evaluable": False},
            {"classification": "insufficient_data", "evaluable": False},
        ]

        review = self._engine()(analysis)
        conversion = next(card for card in review["scorecards"] if card["id"] == "conversion")
        window_input = next(
            item for item in conversion["inputs"]
            if item["id"] == "post_item_conversion_rate"
        )

        self.assertEqual(window_input["value"], 50.0)

    def test_buyback_redeath_priority_uses_exact_event_interval(self):
        analysis = _analysis_fixture()
        analysis["events"]["buyback_death_windows"] = [{
            "buyback_time": 2051,
            "death_time": 2105,
            "redeath_seconds": 54,
            "short_redeath": True,
        }]
        analysis["review_findings"] = [{
            "priority": "high",
            "category": "buyback_redeath",
            "category_label": "买活后再次阵亡",
            "evidence": "34.2分买活，35.1分再次死亡，间隔54秒。",
            "why_it_matters": "买活后的可行动窗口被快速终止。",
            "action": "买活后120秒内不要作为第一进场点。",
            "replay_check": "系统对齐买活和死亡事件。",
            "training_goal": "保住买活后的防守窗口。",
            "success_metric": "买活后120秒内再次死亡=0。",
        }]

        review = self._engine()(analysis)
        point = review["review_points"][0]
        inputs = {item["id"]: item["value"] for item in point["formula_inputs"]}

        self.assertEqual(point["category"], "buyback_redeath")
        self.assertEqual(inputs["short_buyback_redeaths"], 1)
        self.assertEqual(inputs["shortest_buyback_redeath_seconds"], 54)
        self.assertIn("120-最短间隔秒", point["formula"])

    def test_action_selection_suppresses_death_overlapped_farm_and_raw_coordinate_drills(self):
        analysis = _analysis_fixture()
        analysis["events"]["deaths"] = [{"minute": 21.0}]
        analysis["review_findings"].extend([
            {
                "priority": "medium",
                "category": "resource_continuity",
                "category_label": "资源连续性",
                "evidence": "20-23分钟低效率窗口。",
                "why_it_matters": "资源下降。",
                "action": "下一局保持资源路线。",
                "replay_check": "系统检查分钟数组。",
                "training_goal": "减少低效率窗口。",
                "success_metric": "低效率窗口=0。",
            },
            {
                "priority": "high",
                "category": "death_position_pattern",
                "category_label": "重复死亡坐标",
                "evidence": "两个raw坐标簇。",
                "why_it_matters": "重复死亡。",
                "action": "下一局避开这些raw坐标。",
                "replay_check": "系统检查坐标。",
                "training_goal": "减少坐标簇。",
                "success_metric": "坐标簇<=1。",
            },
        ])

        review = self._engine()(analysis)
        categories = [item["category"] for item in review["review_points"]]

        self.assertNotIn("resource_continuity", categories)
        self.assertNotIn("death_position_pattern", categories)

    def test_action_selection_suppresses_resource_recovery_when_same_death_already_cost_objectives(self):
        analysis = _analysis_fixture()
        analysis["events"]["death_objective_windows"] = [{
            "death_time": 1440,
            "death_minute": 24.0,
            "objective_kind": "barracks",
        }]
        analysis["timeline"]["death_overlap_windows"] = [{
            "death_minutes": [24.0],
        }]
        analysis["timeline"]["death_recovery_windows"] = [{
            "minute": 24.0,
            "status": "low",
        }]
        analysis["review_findings"].extend([
            {
                "priority": "high",
                "category": "death_resource_overlap",
                "category_label": "死亡打断资源",
                "evidence": "24.0分死亡与低效率窗口重叠。",
                "why_it_matters": "死亡打断资源。",
                "action": "复活后先补资源。",
                "replay_check": "系统检查时间重叠。",
                "training_goal": "减少资源中断。",
                "success_metric": "死亡资源重叠=0。",
            },
            {
                "priority": "high",
                "category": "death_recovery",
                "category_label": "死亡后恢复",
                "evidence": "24.0分死亡后恢复不足。",
                "why_it_matters": "资源恢复慢。",
                "action": "复活后先补资源。",
                "replay_check": "系统检查恢复窗口。",
                "training_goal": "改善恢复。",
                "success_metric": "恢复不足=0。",
            },
        ])

        review = self._engine()(analysis)
        categories = {item["category"] for item in review["review_points"]}

        self.assertNotIn("death_resource_overlap", categories)
        self.assertNotIn("death_recovery", categories)

    def test_action_selection_does_not_fill_quota_with_duplicate_dimensions(self):
        analysis = _analysis_fixture()
        analysis["review_findings"] = []
        for category in ("death_resource_overlap", "death_resource_delta"):
            analysis["review_findings"].append({
                "priority": "high",
                "category": category,
                "category_label": "死亡资源下降",
                "evidence": "死亡后资源下降。",
                "why_it_matters": "复活后恢复变慢。",
                "action": "复活后先收安全资源。",
                "replay_check": "系统检查真实资源数组。",
                "training_goal": "减少死亡后资源下降。",
                "success_metric": "死亡后资源下降窗口<=1。",
            })

        review = self._engine()(analysis)
        categories = [item["category"] for item in review["review_points"]]

        self.assertFalse(
            {"death_resource_overlap", "death_resource_delta"}.issubset(categories)
        )

    def test_map_impact_priority_uses_same_40_percent_training_threshold(self):
        analysis = _analysis_fixture()
        analysis["performance_context"]["teamfight_participation_pct"] = 36
        analysis["review_findings"] = [{
            "priority": "medium",
            "category": "map_impact",
            "category_label": "地图影响力",
            "evidence": "OpenDota参战率 36%。",
            "why_it_matters": "低于40%训练阈值。",
            "action": "下一局把路线接到地图目标。",
            "replay_check": "系统检查OpenDota参战率。",
            "training_goal": "提高可记录参战率。",
            "success_metric": "参战率>=40%。",
        }]

        review = self._engine()(analysis)
        point = review["review_points"][0]
        gap = next(
            item for item in point["formula_inputs"]
            if item["id"] == "teamfight_participation_gap"
        )

        self.assertEqual(gap["value"], 4)
        self.assertIn("max(0,40-参战率)", point["formula"])
        self.assertEqual(point["formula_score"], 44.0)

    def test_runtime_sources_have_no_model_configuration_or_gateway(self):
        paths = [
            ROOT / "config.py",
            ROOT / "wrangler.toml",
            ROOT / "worker_entry.py",
            ROOT / "worker" / "service.py",
            ROOT / "worker" / "cloudflare_adapters.py",
            ROOT / "main.py",
            ROOT / "web" / "match.html",
            ROOT / "web" / "static" / "match.js",
        ]
        forbidden = ("AI_MODEL", "WorkersAIGateway", "ai_gateway", "OPENCODE_AI", "生成 AI", "AI 教练")

        for path in paths:
            content = path.read_text(encoding="utf-8")
            for marker in forbidden:
                self.assertNotIn(marker, content, f"{path.name} still contains {marker}")


if __name__ == "__main__":
    unittest.main()
