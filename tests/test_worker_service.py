import unittest
from datetime import datetime, timedelta, timezone

from analysis.coach_contract import (
    CoachValidationError,
    build_coach_payload,
    deterministic_coach,
    rank_coach_from_ai,
    select_coaching_findings,
    validate_coach_payload,
)
from analysis.evidence_contract import EVIDENCE_SCHEMA_VERSION
from api.normalization import (
    normalize_match_participants,
    normalize_player_match,
    normalize_recent_match,
)
from worker.contracts import ServiceError
from worker.service import ReviewService


ACCOUNT_ID = 173776719


class OpenDotaNormalizationTests(unittest.TestCase):
    def test_recent_match_normalizer_returns_personal_summary(self):
        raw_match = {
            "match_id": 8891116798,
            "player_slot": 3,
            "radiant_win": True,
            "duration": 2727,
            "start_time": 1783763197,
            "game_mode": 22,
            "lobby_type": 7,
            "hero_id": 48,
            "kills": 13,
            "deaths": 4,
            "assists": 11,
            "average_rank": 54,
            "lane": 1,
            "lane_role": 1,
        }

        summary = normalize_recent_match(raw_match, ACCOUNT_ID)

        self.assertEqual(summary["match_id"], 8891116798)
        self.assertEqual(summary["account_id"], ACCOUNT_ID)
        self.assertEqual(summary["hero"], {"id": 48, "name": "Luna", "slug": "luna"})
        self.assertEqual(summary["kda"], {"kills": 13, "deaths": 4, "assists": 11})
        self.assertTrue(summary["is_win"])
        self.assertEqual(summary["side"], "radiant")
        self.assertEqual(summary["duration_seconds"], 2727)
        self.assertEqual(summary["rank_tier"], 54)
        self.assertEqual(summary["lobby_type"], 7)
        self.assertTrue(summary["is_ranked"])
        self.assertEqual(summary["ended_at"], "2026-07-11T10:32:04Z")

    def test_recent_match_normalizer_calculates_dire_loss(self):
        raw_match = {
            "match_id": 8891064472,
            "player_slot": 130,
            "radiant_win": True,
            "duration": 1800,
            "start_time": 1783750000,
            "hero_id": 48,
            "kills": 1,
            "deaths": 2,
            "assists": 3,
            "lobby_type": 7,
        }

        summary = normalize_recent_match(raw_match, ACCOUNT_ID)

        self.assertEqual(summary["side"], "dire")
        self.assertFalse(summary["is_win"])

    def test_recent_match_normalizer_rejects_missing_identity(self):
        self.assertIsNone(normalize_recent_match({"hero_id": 48}, ACCOUNT_ID))
        self.assertIsNone(normalize_recent_match({"match_id": 1}, ACCOUNT_ID))

    def test_full_match_normalizer_returns_analyzer_player_shape(self):
        raw_match = {
            "match_id": 8891116798,
            "duration": 2727,
            "start_time": 1783763197,
            "radiant_win": True,
            "radiant_score": 34,
            "dire_score": 41,
            "game_mode": 22,
            "lobby_type": 7,
            "players": [{
                "account_id": ACCOUNT_ID,
                "hero_id": 48,
                "player_slot": 3,
                "kills": 13,
                "deaths": 4,
                "assists": 11,
                "gold_per_min": 940,
                "xp_per_min": 980,
                "hero_damage": 36000,
                "tower_damage": 4700,
                "hero_healing": 0,
                "last_hits": 643,
                "denies": 12,
                "level": 30,
                "gold": 2100,
                "net_worth": 42700,
                "item_0": 63,
                "item_1": 147,
                "item_2": 160,
                "item_3": 116,
                "item_4": 141,
                "item_5": 208,
                "ability_upgrades_arr": [5222, 5223],
                "lane": 1,
                "lane_role": 1,
                "is_roaming": False,
                "benchmarks": {"gold_per_min": {"pct": 0.91}},
            }],
        }

        normalized = normalize_player_match(raw_match, ACCOUNT_ID)

        self.assertEqual(normalized["account_id"], ACCOUNT_ID)
        self.assertEqual(normalized["hero_id"], 48)
        self.assertEqual(normalized["is_radiant"], 1)
        self.assertEqual(normalized["gold_per_min"], 940)
        self.assertEqual(normalized["item_5"], 208)
        self.assertEqual(normalized["ability_upgrades"], "[5222, 5223]")

    def test_full_match_normalizer_rejects_missing_personal_player(self):
        self.assertIsNone(normalize_player_match({"match_id": 1, "players": []}, ACCOUNT_ID))

    def test_match_participants_include_hero_and_final_item_identity(self):
        raw_match = {
            "players": [
                {
                    "account_id": ACCOUNT_ID,
                    "hero_id": 48,
                    "player_slot": 3,
                    "kills": 13,
                    "deaths": 4,
                    "assists": 11,
                    "item_0": 116,
                    "item_1": 147,
                    "level": 30,
                    "net_worth": 42700,
                },
                {
                    "account_id": 2,
                    "hero_id": 2,
                    "player_slot": 128,
                    "kills": 4,
                    "deaths": 9,
                    "assists": 18,
                },
            ],
        }

        participants = normalize_match_participants(raw_match, ACCOUNT_ID)

        self.assertEqual(participants[0]["hero"]["name"], "Luna")
        self.assertTrue(participants[0]["is_self"])
        self.assertEqual(participants[0]["side"], "radiant")
        self.assertEqual(participants[0]["items"][0]["name"], "Black King Bar")
        self.assertEqual(participants[0]["items"][0]["slug"], "black_king_bar")
        self.assertEqual(participants[1]["hero"]["name"], "Axe")
        self.assertFalse(participants[1]["is_self"])


class FakeCache:
    def __init__(self, initial=None):
        self.values = dict(initial or {})
        self.puts = []

    async def get_json(self, key):
        return self.values.get(key)

    async def put_json(self, key, value, expiration_ttl=None):
        self.values[key] = value
        self.puts.append((key, value, expiration_ttl))


class FakeDotaGateway:
    def __init__(self, recent=None, details=None, stratz=None):
        self.recent = list(recent or [])
        self.details = dict(details or {})
        self.stratz = dict(stratz or {})
        self.recent_calls = 0
        self.detail_calls = []
        self.stratz_calls = []
        self.parse_calls = []

    async def recent_ranked_matches(self, account_id, limit):
        self.recent_calls += 1
        return list(self.recent)

    async def match_detail(self, match_id):
        self.detail_calls.append(match_id)
        return self.details.get(match_id)

    async def stratz_detail(self, match_id):
        self.stratz_calls.append(match_id)
        return self.stratz.get(match_id)

    async def request_parse(self, match_id):
        self.parse_calls.append(match_id)
        return {"job": {"jobId": 987654321}}


class FakeMatchRefreshGateway:
    def __init__(self):
        self.calls = 0

    async def dispatch(self):
        self.calls += 1
        return {"accepted": True}


def _recent_match(match_id, *, lobby_type=7, hero_id=48):
    return {
        "match_id": match_id,
        "player_slot": 3,
        "radiant_win": match_id % 2 == 0,
        "duration": 1800,
        "start_time": 1783760000 + match_id % 1000,
        "game_mode": 22,
        "lobby_type": lobby_type,
        "hero_id": hero_id,
        "kills": 8,
        "deaths": 3,
        "assists": 12,
    }


class ReviewServiceMatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
        recent = [_recent_match(8891116800 - index) for index in range(12)]
        recent.insert(2, _recent_match(8891116700, lobby_type=0))
        detail = {
            "match_id": 8891116800,
            "duration": 1800,
            "start_time": 1783760000,
            "radiant_win": True,
            "players": [{
                "account_id": ACCOUNT_ID,
                "hero_id": 48,
                "player_slot": 3,
                "kills": 8,
                "deaths": 3,
                "assists": 12,
            }],
        }
        self.cache = FakeCache()
        self.dota = FakeDotaGateway(recent, {8891116800: detail})
        self.service = ReviewService(ACCOUNT_ID, self.cache, self.dota)

    async def test_get_matches_reads_cache_without_external_fetch(self):
        result = await self.service.get_matches()

        self.assertEqual(self.dota.recent_calls, 0)
        self.assertEqual(result["source"], "cache")
        self.assertEqual(result["matches"], [])
        self.assertTrue(result["stale"])

    async def test_refresh_keeps_only_ten_ranked_personal_matches(self):
        result = await self.service.refresh_matches(self.now)

        self.assertEqual(len(result["matches"]), 10)
        self.assertTrue(all(match["is_ranked"] for match in result["matches"]))
        self.assertTrue(all(match["account_id"] == ACCOUNT_ID for match in result["matches"]))
        self.assertEqual(self.dota.recent_calls, 1)
        self.assertFalse(result["rate_limited"])
        self.assertFalse(result["stale"])

    async def test_refresh_inside_cooldown_returns_cache(self):
        first = await self.service.refresh_matches(self.now)
        second = await self.service.refresh_matches(self.now + timedelta(seconds=30))

        self.assertEqual(second["matches"], first["matches"])
        self.assertTrue(second["rate_limited"])
        self.assertEqual(self.dota.recent_calls, 1)

    async def test_refresh_after_cooldown_fetches_again(self):
        await self.service.refresh_matches(self.now)
        await self.service.refresh_matches(self.now + timedelta(seconds=61))

        self.assertEqual(self.dota.recent_calls, 2)

    async def test_refresh_dispatches_cache_job_without_edge_opendota_fetch(self):
        gateway = FakeMatchRefreshGateway()
        service = ReviewService(
            ACCOUNT_ID,
            self.cache,
            self.dota,
            match_refresh_gateway=gateway,
        )

        result = await service.refresh_matches(self.now)

        self.assertTrue(result["refreshing"])
        self.assertEqual(result["source"], "cache")
        self.assertEqual(result["matches"], [])
        self.assertEqual(gateway.calls, 1)
        self.assertEqual(self.dota.recent_calls, 0)
        self.assertEqual(
            self.cache.values[service.match_refresh_status_key]["status"],
            "processing",
        )

    async def test_refresh_does_not_dispatch_duplicate_processing_job(self):
        gateway = FakeMatchRefreshGateway()
        service = ReviewService(
            ACCOUNT_ID,
            self.cache,
            self.dota,
            match_refresh_gateway=gateway,
        )

        first = await service.refresh_matches(self.now)
        second = await service.refresh_matches(self.now + timedelta(seconds=30))

        self.assertTrue(first["refreshing"])
        self.assertTrue(second["refreshing"])
        self.assertTrue(second["rate_limited"])
        self.assertEqual(gateway.calls, 1)
        self.assertEqual(self.dota.recent_calls, 0)

    async def test_refresh_logs_sanitized_upstream_failure_before_returning_service_error(self):
        class FailingDotaGateway(FakeDotaGateway):
            async def recent_ranked_matches(self, account_id, limit):
                raise RuntimeError("upstream returned HTTP 403")

        self.service.dota = FailingDotaGateway()

        with self.assertLogs("worker.service", level="WARNING") as captured:
            with self.assertRaises(ServiceError) as raised:
                await self.service.refresh_matches(self.now)

        self.assertEqual(raised.exception.code, "UPSTREAM_UNAVAILABLE")
        self.assertIn("RuntimeError: upstream returned HTTP 403", captured.output[0])

    async def test_match_detail_rejects_id_outside_cached_personal_list(self):
        await self.service.refresh_matches(self.now)

        with self.assertRaises(ServiceError) as raised:
            await self.service.get_match_detail(1234567890)

        self.assertEqual(raised.exception.code, "MATCH_NOT_IN_RECENT_LIST")
        self.assertEqual(self.dota.detail_calls, [])

    async def test_match_detail_fetches_once_then_uses_cache(self):
        await self.service.refresh_matches(self.now)

        first = await self.service.get_match_detail(8891116800)
        second = await self.service.get_match_detail(8891116800)

        self.assertEqual(first["match_id"], 8891116800)
        self.assertEqual(first["source"], "upstream")
        self.assertEqual(second["source"], "cache")
        self.assertEqual(self.dota.detail_calls, [8891116800])

    async def test_match_detail_rejects_upstream_match_without_personal_player(self):
        await self.service.refresh_matches(self.now)
        self.dota.details[8891116800] = {"match_id": 8891116800, "players": []}

        with self.assertRaises(ServiceError) as raised:
            await self.service.get_match_detail(8891116800)

        self.assertEqual(raised.exception.code, "MATCH_NOT_FOUND")


def _analysis_fixture():
    finding = {
        "priority": "medium",
        "category": "resource_continuity",
        "category_label": "中后期资源连续性",
        "evidence": "中后期低效率窗口: 32-34分钟 2.0补/分钟。",
        "why_it_matters": "该窗口打断了核心位资源连续性。",
        "action": "下一局集合前先推出一条安全线。",
        "replay_check": "系统已交叉核对分钟补刀与事件时间。",
        "training_goal": "下一局10分钟后把低效率窗口从1个压到0个。",
        "success_metric": "10分钟后低效率窗口=0。",
    }
    return {
        "hero_name": "Luna",
        "duration_min": 45.5,
        "match_metadata": {"is_win": True},
        "kda": {"kills": 13, "deaths": 4, "assists": 11},
        "farm": {"gpm": 940, "xpm": 980, "last_hits": 643},
        "derived": {"lh_per_min": 14.13, "deaths_per_10_min": 0.88},
        "role_profile": {"id": "pos1", "label": "1号位"},
        "timeline": {
            "available": True,
            "ten_min_last_hits": 53,
            "twenty_min_last_hits": 205,
            "low_efficiency_windows": [{"start_minute": 32, "end_minute": 34, "avg_lh": 2.0}],
        },
        "events": {
            "deaths": [{"minute": 12.0}],
            "death_count_expected": 1,
            "purchases": [{"minute": 10.0, "item_id": 1}],
            "has_purchase_timeline": True,
        },
        "review_findings": [finding],
        "data_quality": {"score": 100, "limitations": []},
    }


class CoachContractTests(unittest.TestCase):
    def test_build_coach_payload_contains_only_evidence_package(self):
        analysis = _analysis_fixture()
        analysis["untrusted_note"] = "must not leave the server"

        payload = build_coach_payload(analysis, "Luna", True)

        self.assertEqual(payload["hero_name"], "Luna")
        self.assertEqual(payload["review_findings"], analysis["review_findings"])
        self.assertEqual(payload["timeline"]["ten_min_last_hits"], 53)
        self.assertNotIn("untrusted_note", payload)

    def test_coach_payload_rejects_categories_absent_from_findings(self):
        with self.assertRaises(CoachValidationError):
            validate_coach_payload(
                {
                    "conclusion": "结论",
                    "review_points": [{
                        "category": "invented_positioning",
                        "evidence": "站位错误",
                        "action": "靠后站",
                    }],
                    "next_actions": [],
                    "data_limits": [],
                },
                _analysis_fixture()["review_findings"],
            )

    def test_coach_payload_rejects_rewritten_evidence(self):
        finding = _analysis_fixture()["review_findings"][0]
        with self.assertRaises(CoachValidationError):
            validate_coach_payload(
                {
                    "conclusion": "结论",
                    "review_points": [{
                        "category": finding["category"],
                        "evidence": "10分钟只有20补。",
                        "action": finding["action"],
                    }],
                    "next_actions": [],
                    "data_limits": [],
                },
                [finding],
            )

    def test_deterministic_coach_preserves_measurable_actions(self):
        analysis = _analysis_fixture()

        coach = deterministic_coach(analysis)

        self.assertIn("32-34分钟", coach["conclusion"])
        self.assertEqual(coach["review_points"][0]["category"], "resource_continuity")
        self.assertIn("从1个压到0个", coach["next_actions"][0]["training_goal"])
        self.assertIn("=0", coach["next_actions"][0]["success_metric"])

    def test_data_acquisition_gaps_never_become_next_match_actions(self):
        analysis = _analysis_fixture()
        gap = dict(analysis["review_findings"][0])
        gap.update({
            "category": "death_data_gap",
            "category_label": "死亡数据缺口",
            "action": "系统会继续请求事件日志。",
            "training_goal": "下一局先保证系统拿到死亡时间线。",
            "success_metric": "数据验收：下一份报告死亡覆盖率=100%。",
        })
        analysis["review_findings"].insert(0, gap)

        coach = deterministic_coach(analysis)

        self.assertEqual(
            [item["category"] for item in coach["next_actions"]],
            ["resource_continuity"],
        )

    def test_coaching_selection_prefers_distinct_training_dimensions(self):
        analysis = _analysis_fixture()
        template = analysis["review_findings"][0]
        analysis["review_findings"] = []
        for category, priority in (
            ("death_review", "high"),
            ("death_resource_overlap", "high"),
            ("death_position_pattern", "high"),
            ("item_timing", "medium"),
            ("resource_continuity", "medium"),
        ):
            finding = dict(template)
            finding.update({"category": category, "priority": priority})
            analysis["review_findings"].append(finding)

        selected = select_coaching_findings(analysis)

        categories = [item["category"] for item in selected]
        self.assertEqual(categories[:3], [
            "death_review",
            "item_timing",
            "resource_continuity",
        ])
        self.assertEqual(len(categories), 4)

    def test_coaching_selection_caps_repeated_death_dimension(self):
        analysis = _analysis_fixture()
        template = analysis["review_findings"][0]
        analysis["review_findings"] = []
        for category in (
            "death_review",
            "death_resource_overlap",
            "death_position_pattern",
            "death_resource_delta",
            "resource_continuity",
        ):
            finding = dict(template)
            finding.update({"category": category, "priority": "high"})
            analysis["review_findings"].append(finding)

        selected = select_coaching_findings(analysis)

        categories = [item["category"] for item in selected]
        self.assertEqual(len(categories), 3)
        self.assertIn("resource_continuity", categories)

    def test_ai_ranking_hydrates_only_deterministic_findings(self):
        analysis = _analysis_fixture()
        second = dict(analysis["review_findings"][0])
        second.update({
            "category": "death_cost",
            "category_label": "死亡成本",
            "evidence": "20.0分钟死亡后30秒丢失一塔。",
            "action": "下一局死亡前先确认撤退路线。",
            "training_goal": "下一局死亡后30秒失塔从1次降到0次。",
            "success_metric": "死亡后30秒失塔=0次。",
        })
        analysis["review_findings"].append(second)

        coach = rank_coach_from_ai({"finding_order": [1, 0]}, analysis)

        self.assertTrue(coach["ai_ranked"])
        self.assertEqual(coach["review_points"][0]["category"], "death_cost")
        self.assertEqual(coach["review_points"][0]["evidence"], second["evidence"])
        self.assertEqual(coach["next_actions"][0]["action"], second["action"])

    def test_ai_ranking_requires_every_finding_index_exactly_once(self):
        with self.assertRaises(CoachValidationError):
            rank_coach_from_ai({"finding_order": [0, 0]}, _analysis_fixture())


class FakeAnalyzer:
    def __init__(self, result=None):
        self.result = result or _analysis_fixture()
        self.calls = 0

    def analyze(self, match, *, stratz_data=None, opendota_data=None):
        self.calls += 1
        return self.result


class FakeAI:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = 0

    async def generate(self, evidence_package):
        self.calls += 1
        if self.error:
            raise self.error
        return self.payload


class FakeEvidenceGateway:
    def __init__(self):
        self.calls = []

    async def dispatch(self, match_id):
        self.calls.append(match_id)
        return {"accepted": True}


def _valid_ai_payload():
    return {"finding_order": [0]}


class ReviewServiceGenerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
        recent = [_recent_match(8891116798)]
        detail = {
            "match_id": 8891116798,
            "duration": 2727,
            "start_time": 1783763197,
            "radiant_win": True,
            "players": [{
                "account_id": ACCOUNT_ID,
                "hero_id": 48,
                "player_slot": 3,
                "kills": 13,
                "deaths": 4,
                "assists": 11,
            }],
        }
        self.cache = FakeCache()
        self.dota = FakeDotaGateway(recent, {8891116798: detail}, {8891116798: {"players": []}})
        self.analyzer = FakeAnalyzer()
        self.ai = FakeAI(_valid_ai_payload())
        self.evidence = FakeEvidenceGateway()
        self.service = ReviewService(
            ACCOUNT_ID,
            self.cache,
            self.dota,
            analyzer=self.analyzer,
            ai_gateway=self.ai,
            evidence_gateway=self.evidence,
            prefer_remote_evidence=False,
        )

    async def asyncSetUp(self):
        await self.service.refresh_matches(self.now)

    async def test_review_status_does_not_run_analysis_or_ai(self):
        status = await self.service.review_status(8891116798)

        self.assertFalse(status["exists"])
        self.assertEqual(self.ai.calls, 0)
        self.assertEqual(self.analyzer.calls, 0)
        self.assertEqual(self.dota.detail_calls, [])

    async def test_review_runs_only_after_explicit_generation(self):
        result = await self.service.generate_review(8891116798, self.now)

        self.assertEqual(self.analyzer.calls, 1)
        self.assertEqual(self.ai.calls, 1)
        self.assertEqual(self.dota.stratz_calls, [])
        self.assertFalse(result["cached"])
        self.assertEqual(result["ai_status"], "generated")

    async def test_click_prefers_remote_stratz_evidence_even_when_opendota_is_complete(self):
        service = ReviewService(
            ACCOUNT_ID,
            self.cache,
            self.dota,
            analyzer=self.analyzer,
            ai_gateway=self.ai,
            evidence_gateway=self.evidence,
            prefer_remote_evidence=True,
        )

        first = await service.generate_review(8891116798, self.now)

        self.assertEqual(first["status"], "processing")
        self.assertEqual(first["evidence_gaps"], ["stratz_enrichment"])
        self.assertEqual(self.evidence.calls, [8891116798])
        self.assertEqual(self.analyzer.calls, 0)
        self.assertEqual(self.ai.calls, 0)

        await self.cache.put_json(
            service.evidence_key(8891116798),
            {
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "match_id": 8891116798,
                "source": "github_actions_stratz",
                "analysis": _analysis_fixture(),
            },
        )
        second = await service.generate_review(
            8891116798,
            self.now + timedelta(seconds=5),
        )

        self.assertEqual(second["ai_status"], "generated")
        self.assertEqual(second["evidence_source"], "github_actions_stratz")
        self.assertEqual(self.analyzer.calls, 0)
        self.assertEqual(self.ai.calls, 1)

    async def test_failed_remote_enrichment_automatically_falls_back_to_opendota(self):
        service = ReviewService(
            ACCOUNT_ID,
            self.cache,
            self.dota,
            analyzer=self.analyzer,
            ai_gateway=self.ai,
            evidence_gateway=self.evidence,
            prefer_remote_evidence=True,
        )
        first = await service.generate_review(8891116798, self.now)
        self.assertEqual(first["status"], "processing")
        await self.cache.put_json(
            service.evidence_status_key(8891116798),
            {
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "match_id": 8891116798,
                "status": "failed",
                "completed_at": "2026-07-12T03:00:05Z",
                "error_code": "STRATZ_UNAVAILABLE",
            },
        )

        second = await service.generate_review(
            8891116798,
            self.now + timedelta(seconds=5),
        )

        self.assertEqual(second["ai_status"], "generated")
        self.assertEqual(second["evidence_source"], "opendota_parsed")
        self.assertEqual(self.analyzer.calls, 1)
        self.assertEqual(self.ai.calls, 1)

    async def test_remote_enrichment_timeout_falls_back_without_redispatch(self):
        service = ReviewService(
            ACCOUNT_ID,
            self.cache,
            self.dota,
            analyzer=self.analyzer,
            ai_gateway=self.ai,
            evidence_gateway=self.evidence,
            prefer_remote_evidence=True,
        )
        first = await service.generate_review(8891116798, self.now)
        self.assertEqual(first["status"], "processing")

        second = await service.generate_review(
            8891116798,
            self.now + timedelta(seconds=91),
        )

        self.assertEqual(second["ai_status"], "generated")
        self.assertEqual(second["evidence_source"], "opendota_parsed")
        self.assertEqual(self.evidence.calls, [8891116798])

    async def test_incomplete_fallback_stops_polling_after_parse_wait(self):
        incomplete = _analysis_fixture()
        incomplete["timeline"] = {"available": False}
        incomplete["events"] = {
            "deaths": [],
            "death_count_expected": 4,
            "purchases": [],
            "has_purchase_timeline": False,
        }
        self.analyzer.result = incomplete
        service = ReviewService(
            ACCOUNT_ID,
            self.cache,
            self.dota,
            analyzer=self.analyzer,
            ai_gateway=self.ai,
            evidence_gateway=self.evidence,
            prefer_remote_evidence=True,
        )
        first = await service.generate_review(8891116798, self.now)
        self.assertEqual(first["status"], "processing")
        await self.cache.put_json(
            service.evidence_status_key(8891116798),
            {
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "match_id": 8891116798,
                "status": "failed",
                "completed_at": "2026-07-12T03:00:05Z",
                "error_code": "STRATZ_UNAVAILABLE",
            },
        )
        second = await service.generate_review(
            8891116798,
            self.now + timedelta(seconds=5),
        )
        self.assertEqual(second["status"], "processing")

        third = await service.generate_review(
            8891116798,
            self.now + timedelta(seconds=36),
        )

        self.assertNotEqual(third.get("status"), "processing")
        self.assertEqual(third["evidence_source"], "opendota_partial")
        self.assertEqual(self.evidence.calls, [8891116798])
        self.assertEqual(self.dota.parse_calls, [8891116798])

    async def test_incomplete_evidence_requests_parse_and_skips_ai(self):
        incomplete = _analysis_fixture()
        incomplete["timeline"] = {"available": False}
        incomplete["events"] = {
            "deaths": [],
            "death_count_expected": 4,
            "purchases": [],
            "has_purchase_timeline": False,
        }
        self.analyzer.result = incomplete

        result = await self.service.generate_review(8891116798, self.now)

        self.assertEqual(result["status"], "processing")
        self.assertGreaterEqual(result["retry_after_seconds"], 1)
        self.assertEqual(
            set(result["evidence_gaps"]),
            {"minute_timeline", "death_timeline", "purchase_timeline"},
        )
        self.assertEqual(self.dota.parse_calls, [8891116798])
        self.assertEqual(self.evidence.calls, [8891116798])
        self.assertEqual(self.ai.calls, 0)
        self.assertNotIn(self.service.review_key(8891116798), self.cache.values)

    async def test_processing_poll_does_not_submit_duplicate_parse_job(self):
        incomplete = _analysis_fixture()
        incomplete["timeline"] = {"available": False}
        incomplete["events"] = {
            "deaths": [],
            "death_count_expected": 4,
            "purchases": [],
            "has_purchase_timeline": False,
        }
        self.analyzer.result = incomplete

        await self.service.generate_review(8891116798, self.now)
        await self.service.generate_review(
            8891116798,
            self.now + timedelta(seconds=5),
        )

        self.assertEqual(self.dota.parse_calls, [8891116798])
        self.assertEqual(self.evidence.calls, [8891116798])
        self.assertEqual(self.ai.calls, 0)

    async def test_ready_github_evidence_runs_ai_without_refetching_match(self):
        await self.cache.put_json(
            self.service.evidence_key(8891116798),
            {
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "match_id": 8891116798,
                "source": "github_actions_stratz",
                "analysis": _analysis_fixture(),
            },
        )

        result = await self.service.generate_review(8891116798, self.now)

        self.assertEqual(result["ai_status"], "generated")
        self.assertEqual(result["evidence_source"], "github_actions_stratz")
        self.assertEqual(self.analyzer.calls, 0)
        self.assertEqual(self.dota.detail_calls, [])
        self.assertEqual(self.evidence.calls, [])

    async def test_cached_review_does_not_repeat_ai(self):
        await self.service.generate_review(8891116798, self.now)
        result = await self.service.generate_review(8891116798, self.now + timedelta(minutes=1))

        self.assertTrue(result["cached"])
        self.assertEqual(self.analyzer.calls, 1)
        self.assertEqual(self.ai.calls, 1)

    async def test_cached_opendota_review_upgrades_when_remote_evidence_arrives(self):
        first = await self.service.generate_review(8891116798, self.now)
        self.assertEqual(first["evidence_source"], "opendota_parsed")
        await self.cache.put_json(
            self.service.evidence_key(8891116798),
            {
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "match_id": 8891116798,
                "source": "github_actions_stratz",
                "analysis": _analysis_fixture(),
            },
        )

        upgraded = await self.service.generate_review(
            8891116798,
            self.now + timedelta(minutes=2),
        )

        self.assertFalse(upgraded["cached"])
        self.assertEqual(upgraded["evidence_source"], "github_actions_stratz")
        self.assertEqual(self.analyzer.calls, 1)
        self.assertEqual(self.ai.calls, 2)

    async def test_fallback_review_upgrades_when_remote_evidence_arrives(self):
        self.ai.payload = {"finding_order": [1]}
        first = await self.service.generate_review(8891116798, self.now)
        self.assertEqual(first["ai_status"], "fallback")
        await self.cache.put_json(
            self.service.evidence_key(8891116798),
            {
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "match_id": 8891116798,
                "source": "github_actions_stratz",
                "analysis": _analysis_fixture(),
            },
        )
        self.ai.payload = _valid_ai_payload()

        upgraded = await self.service.generate_review(
            8891116798,
            self.now + timedelta(minutes=2),
        )

        self.assertEqual(upgraded["ai_status"], "generated")
        self.assertEqual(upgraded["evidence_source"], "github_actions_stratz")
        self.assertEqual(self.analyzer.calls, 1)
        self.assertEqual(self.ai.calls, 2)

    async def test_invalid_ai_output_uses_deterministic_fallback(self):
        self.ai.payload = {
            "finding_order": [1],
        }

        result = await self.service.generate_review(8891116798, self.now)

        self.assertEqual(result["ai_status"], "fallback")
        self.assertEqual(result["ai_error_code"], "AI_OUTPUT_REJECTED")
        self.assertEqual(result["coach"], deterministic_coach(_analysis_fixture()))

    async def test_fallback_review_retries_ai_without_recomputing_analysis(self):
        self.ai.error = RuntimeError("temporary AI failure")
        first = await self.service.generate_review(8891116798, self.now)
        self.ai.error = None
        self.ai.payload = _valid_ai_payload()

        second = await self.service.generate_review(
            8891116798,
            self.now + timedelta(minutes=1),
        )

        self.assertEqual(first["ai_status"], "fallback")
        self.assertEqual(second["ai_status"], "generated")
        self.assertFalse(second["cached"])
        self.assertEqual(self.analyzer.calls, 1)
        self.assertEqual(self.ai.calls, 2)
        self.assertEqual(self.dota.detail_calls, [8891116798])


if __name__ == "__main__":
    unittest.main()
