import unittest
from datetime import datetime, timedelta, timezone

from analysis.evidence_contract import EVIDENCE_SCHEMA_VERSION
from analysis.formula_engine import FORMULA_VERSION, REVIEW_SCHEMA_VERSION
from worker.contracts import ServiceError
from worker.service import ReviewService


ACCOUNT_ID = 173776719
MATCH_ID = 8891116798


def _recent_match(match_id=MATCH_ID):
    return {
        "match_id": match_id,
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
    }


def _detail(match_id=MATCH_ID):
    players = [{
        "account_id": ACCOUNT_ID,
        "hero_id": 48,
        "player_slot": 3,
        "kills": 13,
        "deaths": 4,
        "assists": 11,
        "gold_per_min": 940,
        "xp_per_min": 980,
        "last_hits": 643,
        "denies": 8,
        "hero_damage": 52000,
        "tower_damage": 9000,
        "hero_healing": 0,
        "level": 30,
        "net_worth": 41000,
        "item_0": 50,
    }]
    for index in range(1, 10):
        players.append({
            "account_id": 1000 + index,
            "hero_id": 48 + index,
            "player_slot": index if index < 5 else 128 + index - 5,
            "kills": 0,
            "deaths": 0,
            "assists": 0,
        })
    return {
        "match_id": match_id,
        "duration": 2727,
        "start_time": 1783763197,
        "radiant_win": True,
        "lobby_type": 7,
        "players": players,
    }


def _finding(category="resource_continuity", priority="medium"):
    return {
        "priority": priority,
        "category": category,
        "category_label": "资源连续性",
        "evidence": "32-34分钟连续低效率窗口，平均2.0 LH/min。",
        "why_it_matters": "资源断档会延后装备和目标窗口。",
        "action": "下一局提前规划32分钟后的安全线野路线。",
        "replay_check": "系统检查真实分钟补刀数组。",
        "training_goal": "下一局把低效率窗口从1个压到0个。",
        "success_metric": "30分钟后连续低效率窗口=0。",
    }


def _analysis_fixture(complete=True):
    if not complete:
        return {
            "duration_min": 45.5,
            "timeline": {"available": False},
            "events": {
                "deaths": [],
                "death_count_expected": 4,
                "purchases": [],
                "has_purchase_timeline": False,
            },
            "review_findings": [_finding()],
            "data_quality": {
                "score": 40,
                "limitations": ["必需字段不完整"],
                "blocking_gaps": ["minute_lh", "deaths", "purchases"],
            },
        }
    return {
        "hero_name": "Luna",
        "is_win": True,
        "duration_min": 45.5,
        "kda": {"kills": 13, "deaths": 4, "assists": 11},
        "role_profile": {"id": "pos1", "label": "1号位"},
        "timeline": {
            "available": True,
            "ten_min_last_hits": 53,
            "last_hits_by_minute": [6] * 45,
            "gold_by_minute": [700] * 45,
            "experience_by_minute": [800] * 45,
            "low_efficiency_windows": [{"start_minute": 32, "end_minute": 34}],
            "death_resource_deltas": [],
        },
        "events": {
            "deaths": [{"minute": 12.0}, {"minute": 24.0}, {"minute": 36.0}, {"minute": 40.0}],
            "death_count_expected": 4,
            "purchases": [{"minute": 10.0, "item_id": 50}],
            "has_purchase_timeline": True,
            "post_item_windows": [],
            "death_objective_windows": [],
        },
        "performance_context": {
            "lane_efficiency_pct": 78,
            "teamfight_participation_pct": 62,
            "dead_time_share_pct": 10,
        },
        "opendota_benchmarks": {
            "metrics": [
                {"id": "gold_per_min", "percentile": 80},
                {"id": "xp_per_min", "percentile": 76},
                {"id": "last_hits_per_min", "percentile": 82},
                {"id": "hero_damage_per_min", "percentile": 72},
                {"id": "tower_damage", "percentile": 69},
            ],
        },
        "review_findings": [_finding()],
        "data_quality": {
            "score": 100,
            "limitations": [],
            "blocking_gaps": [],
        },
    }


class FakeCache:
    def __init__(self):
        self.values = {}
        self.puts = []

    async def get_json(self, key):
        return self.values.get(key)

    async def put_json(self, key, value, expiration_ttl=None):
        self.values[key] = value
        self.puts.append((key, expiration_ttl))


class FakeDotaGateway:
    def __init__(self):
        self.recent = [_recent_match()]
        self.details = {MATCH_ID: _detail()}
        self.recent_calls = 0
        self.detail_calls = []
        self.parse_calls = []

    async def recent_ranked_matches(self, account_id, limit):
        self.recent_calls += 1
        return self.recent[:limit]

    async def match_detail(self, match_id):
        self.detail_calls.append(match_id)
        return self.details[match_id]

    async def request_parse(self, match_id):
        self.parse_calls.append(match_id)
        return {"jobId": 77}


class FakeAnalyzer:
    def __init__(self, result=None):
        self.result = result or _analysis_fixture()
        self.calls = 0

    def analyze(self, match, *, stratz_data=None, opendota_data=None):
        self.calls += 1
        return self.result


class FakeEvidenceGateway:
    def __init__(self):
        self.calls = []

    async def dispatch(self, match_id):
        self.calls.append(match_id)
        return {"accepted": True}


class ReviewServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 13, 3, 0, tzinfo=timezone.utc)
        self.cache = FakeCache()
        self.dota = FakeDotaGateway()
        self.analyzer = FakeAnalyzer()
        self.evidence = FakeEvidenceGateway()
        self.service = ReviewService(
            ACCOUNT_ID,
            self.cache,
            self.dota,
            analyzer=self.analyzer,
            evidence_gateway=self.evidence,
            prefer_remote_evidence=False,
        )

    async def asyncSetUp(self):
        await self.service.refresh_matches(self.now)

    async def test_match_list_is_cached_and_fixed_to_ranked_recent_ten(self):
        result = await self.service.get_matches()

        self.assertEqual(result["account_id"], ACCOUNT_ID)
        self.assertEqual(len(result["matches"]), 1)
        self.assertTrue(result["matches"][0]["is_ranked"])
        self.assertEqual(self.dota.recent_calls, 1)

    async def test_match_detail_normalizes_self_and_all_participants(self):
        result = await self.service.get_match_detail(MATCH_ID)

        self.assertEqual(result["player"]["hero_id"], 48)
        self.assertEqual(len(result["participants"]), 10)
        self.assertEqual(sum(item["is_self"] for item in result["participants"]), 1)

    async def test_match_outside_recent_ten_is_rejected(self):
        with self.assertRaises(ServiceError) as raised:
            await self.service.get_match_detail(123)

        self.assertEqual(raised.exception.code, "MATCH_NOT_IN_RECENT_LIST")

    async def test_review_status_reads_cache_without_running_analysis(self):
        status = await self.service.review_status(MATCH_ID)

        self.assertFalse(status["exists"])
        self.assertEqual(status["analysis_mode"], "deterministic_formula")
        self.assertEqual(status["formula_version"], FORMULA_VERSION)
        self.assertEqual(self.analyzer.calls, 0)
        self.assertEqual(self.dota.detail_calls, [])

    async def test_explicit_review_builds_formula_guidance_and_reuses_cache(self):
        first = await self.service.generate_review(MATCH_ID, self.now)
        second = await self.service.generate_review(MATCH_ID, self.now + timedelta(minutes=1))

        self.assertEqual(first["analysis_mode"], "deterministic_formula")
        self.assertEqual(first["schema_version"], REVIEW_SCHEMA_VERSION)
        self.assertEqual(first["formula_version"], FORMULA_VERSION)
        self.assertEqual(first["guidance"]["analysis_mode"], "deterministic_formula")
        self.assertTrue(first["guidance"]["overall_equation"])
        self.assertEqual(
            first["analysis"]["formula_diagnostics"]["overall_equation"],
            first["guidance"]["overall_equation"],
        )
        self.assertEqual(
            len(first["guidance"]["overall_inputs"]),
            len(first["guidance"]["scorecards"]),
        )
        self.assertEqual(first["guidance"]["next_actions"][0]["category"], "resource_continuity")
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(self.analyzer.calls, 1)
        self.assertEqual(self.dota.detail_calls, [MATCH_ID])

    async def test_ready_remote_evidence_avoids_detail_refetch(self):
        analysis = _analysis_fixture()
        analysis["suggestions"] = [{
            "category": "stale_legacy",
            "message": "旧证据缓存中的未筛选建议",
        }]
        await self.cache.put_json(
            self.service.evidence_key(MATCH_ID),
            {
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "match_id": MATCH_ID,
                "source": "github_actions_stratz",
                "analysis": analysis,
            },
        )

        result = await self.service.generate_review(MATCH_ID, self.now)

        self.assertEqual(result["evidence_source"], "github_actions_stratz")
        self.assertEqual(
            [item["category"] for item in result["analysis"]["suggestions"]],
            [item["category"] for item in result["guidance"]["next_actions"]],
        )
        self.assertNotIn(
            "stale_legacy",
            [item["category"] for item in result["analysis"]["suggestions"]],
        )
        self.assertEqual(self.analyzer.calls, 0)
        self.assertEqual(self.dota.detail_calls, [])

    async def test_preferred_remote_evidence_dispatches_once_and_returns_processing(self):
        service = ReviewService(
            ACCOUNT_ID,
            self.cache,
            self.dota,
            analyzer=self.analyzer,
            evidence_gateway=self.evidence,
            prefer_remote_evidence=True,
        )

        first = await service.generate_review(MATCH_ID, self.now)
        second = await service.generate_review(MATCH_ID, self.now + timedelta(seconds=5))

        self.assertEqual(first["status"], "processing")
        self.assertEqual(second["status"], "processing")
        self.assertEqual(self.evidence.calls, [MATCH_ID])
        self.assertEqual(self.analyzer.calls, 0)

    async def test_incomplete_local_evidence_requests_parse_and_is_not_cached(self):
        self.analyzer.result = _analysis_fixture(complete=False)

        result = await self.service.generate_review(MATCH_ID, self.now)

        self.assertEqual(result["status"], "processing")
        self.assertEqual(
            set(result["evidence_gaps"]),
            {"minute_lh", "deaths", "purchases"},
        )
        self.assertEqual(self.dota.parse_calls, [MATCH_ID])
        self.assertNotIn(self.service.review_key(MATCH_ID), self.cache.values)

    async def test_incomplete_evidence_is_never_published_after_wait_timeout(self):
        self.analyzer.result = _analysis_fixture(complete=False)
        service = ReviewService(
            ACCOUNT_ID,
            self.cache,
            self.dota,
            analyzer=self.analyzer,
            evidence_gateway=self.evidence,
            prefer_remote_evidence=True,
        )
        await self.cache.put_json(service.parse_state_key(MATCH_ID), {
            "match_id": MATCH_ID,
            "evidence_requested_at": (self.now - timedelta(seconds=120)).isoformat(),
            "requested_at": (self.now - timedelta(seconds=45)).isoformat(),
        })
        await self.cache.put_json(service.evidence_status_key(MATCH_ID), {
            "match_id": MATCH_ID,
            "status": "failed",
            "completed_at": (self.now - timedelta(seconds=100)).isoformat(),
        })

        result = await service.generate_review(MATCH_ID, self.now)

        self.assertEqual(result["status"], "processing")
        self.assertEqual(
            set(result["evidence_gaps"]),
            {"minute_lh", "deaths", "purchases"},
        )
        self.assertNotIn(self.service.review_key(MATCH_ID), self.cache.values)

    async def test_review_cache_key_isolated_from_prior_schema(self):
        self.assertEqual(self.service.review_key(MATCH_ID), f"review:v{REVIEW_SCHEMA_VERSION}:{MATCH_ID}")
        self.assertNotEqual(self.service.review_key(MATCH_ID), f"review:v{REVIEW_SCHEMA_VERSION - 1}:{MATCH_ID}")


if __name__ == "__main__":
    unittest.main()
