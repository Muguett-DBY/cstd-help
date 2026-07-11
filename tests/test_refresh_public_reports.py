import json
import tempfile
import unittest
from pathlib import Path

from api.opendota import OpenDotaClient


ACCOUNT_ID = 173776719


class FakeOpenDotaClient:
    def __init__(self, recent_matches, detail_versions):
        self.recent_matches = recent_matches
        self.detail_versions = {
            int(match_id): list(versions)
            for match_id, versions in detail_versions.items()
        }
        self.detail_calls = []
        self.parse_requests = []

    def get_recent_matches(self, account_id=None, limit=20, lobby_type=None):
        self.recent_args = (account_id, limit, lobby_type)
        return list(self.recent_matches)

    def get_match(self, match_id):
        match_id = int(match_id)
        self.detail_calls.append(match_id)
        versions = self.detail_versions[match_id]
        return versions.pop(0) if len(versions) > 1 else versions[0]

    def request_parse(self, match_id):
        self.parse_requests.append(int(match_id))
        return f"job-{match_id}"

    def has_minute_player_logs(self, match_data, account_id=None):
        player = self.find_player(match_data, account_id)
        return bool(player and player.get("lh_t"))

    def find_player(self, match_data, account_id=None):
        target = account_id or ACCOUNT_ID
        return next(
            (player for player in (match_data or {}).get("players", []) if player.get("account_id") == target),
            None,
        )

    def parse_match_for_player(self, raw_match, account_id=None):
        player = self.find_player(raw_match, account_id)
        if not player:
            return None
        return {
            "match_id": raw_match["match_id"],
            "account_id": player["account_id"],
            "hero_id": player.get("hero_id", 9),
            "player_slot": player.get("player_slot", 0),
            "radiant_win": int(bool(raw_match.get("radiant_win"))),
            "duration": raw_match.get("duration", 2400),
            "kills": player.get("kills", 1),
            "deaths": player.get("deaths", 1),
            "assists": player.get("assists", 1),
            "last_hits": player.get("last_hits", 100),
            "gold_per_min": player.get("gold_per_min", 400),
            "xp_per_min": player.get("xp_per_min", 500),
        }


def _recent(match_id, lobby_type=7):
    return {"match_id": match_id, "lobby_type": lobby_type, "game_mode": 22}


def _detail(match_id, parsed=True):
    player = {
        "account_id": ACCOUNT_ID,
        "hero_id": 9,
        "player_slot": 0,
        "kills": 8,
        "deaths": 4,
        "assists": 12,
        "last_hits": 210,
        "gold_per_min": 550,
        "xp_per_min": 620,
    }
    if parsed:
        player.update({
            "lh_t": [0, 5, 11, 17],
            "gold_t": [600, 900, 1300, 1800],
            "xp_t": [0, 300, 750, 1200],
            "purchase_log": [{"time": 90, "key": "boots"}],
        })
    return {
        "match_id": match_id,
        "lobby_type": 7,
        "game_mode": 22,
        "duration": 2400,
        "radiant_win": True,
        "players": [player],
    }


def _analysis(match_data, timeline_status="available", valid_findings=True, missing_evidence=False):
    findings = [{
        "priority": "high",
        "category": "early_resource",
        "evidence": "10分钟补刀54",
        "why_it_matters": "资源决定关键装备窗口",
        "action": "下一局10分钟补刀达到55",
        "replay_check": "系统已核对分钟补刀数组",
    }]
    if not valid_findings:
        findings[0].pop("evidence")
    return {
        "match_id": match_data["match_id"],
        "hero_name": "Mirana",
        "is_win": True,
        "data_quality": {
            "evidence_sources": [
                {
                    "id": "timeline",
                    "status": timeline_status,
                    "source": "OpenDota解析日志",
                },
                {
                    "id": "objectives",
                    "status": "missing" if missing_evidence else "available",
                    "source": "OpenDota目标事件" if not missing_evidence else "未获取",
                },
            ],
        },
        "review_findings": findings,
    }


class OpenDotaRefreshSupportTests(unittest.TestCase):
    def test_recent_matches_can_be_filtered_by_ranked_lobby_type(self):
        client = OpenDotaClient()
        captured = {}

        def fake_get(endpoint, params=None, **_kwargs):
            captured["endpoint"] = endpoint
            captured["params"] = params
            return []

        client._get = fake_get
        client.get_recent_matches(ACCOUNT_ID, limit=50, lobby_type=7)

        self.assertEqual(captured["endpoint"], f"/players/{ACCOUNT_ID}/matches")
        self.assertEqual(captured["params"], {"limit": 50, "lobby_type": 7})

    def test_minute_player_logs_require_target_player_last_hit_timeline(self):
        client = OpenDotaClient()
        parsed = _detail(8891116798, parsed=True)
        unparsed = _detail(8891116798, parsed=False)

        self.assertTrue(client.has_minute_player_logs(parsed, account_id=ACCOUNT_ID))
        self.assertFalse(client.has_minute_player_logs(unparsed, account_id=ACCOUNT_ID))
        self.assertFalse(client.has_minute_player_logs({"players": []}, account_id=ACCOUNT_ID))


class RefreshPublicReportsTests(unittest.TestCase):
    def _module(self):
        from scripts import refresh_public_reports
        return refresh_public_reports

    def _write_existing_report(self, public_dir, match_id=8867002237):
        metadata = {
            "match_id": match_id,
            "hero": {"id": 9, "name": "Mirana", "slug": "mirana"},
            "ended_at": "2026-06-26T10:23:19Z",
        }
        path = Path(public_dir) / f"Mirana_{match_id}.html"
        path.write_text(
            '<html><body><a class="back-link" href="index.html">比赛历史</a>'
            f'<script id="report-metadata" type="application/json">{json.dumps(metadata)}</script>'
            "</body></html>",
            encoding="utf-8",
        )
        return path

    def test_refresh_filters_ranked_unseen_matches_and_preserves_existing_reports(self):
        module = self._module()
        existing_id = 8867002237
        new_id = 8891116798
        unranked_id = 8891116797
        client = FakeOpenDotaClient(
            [_recent(existing_id), _recent(new_id), _recent(unranked_id, lobby_type=0)],
            {new_id: [_detail(new_id, parsed=True)]},
        )
        generated_sources = []
        build_sources = []

        def fake_analyze(match_data, **_kwargs):
            return _analysis(match_data)

        def fake_report(analysis, _coach, output_dir=None, source_fetches=None, **_kwargs):
            path = Path(output_dir) / f"Mirana_{analysis['match_id']}_20260711_100000.html"
            path.write_text("<html></html>", encoding="utf-8")
            generated_sources.append(source_fetches)
            return str(path)

        def fake_build(source, public_dir=None, **_kwargs):
            build_sources.extend(path.name for path in Path(source).glob("*.html"))

        with tempfile.TemporaryDirectory() as public:
            self._write_existing_report(public, existing_id)
            result = module.refresh_public_reports(
                public_dir=public,
                recent_limit=20,
                max_new=10,
                parse_wait=0,
                opendota_client=client,
                use_stratz=False,
                use_d2pt=False,
                analyze_fn=fake_analyze,
                ai_fn=lambda *_args: "coach",
                report_fn=fake_report,
                build_fn=fake_build,
            )

        self.assertEqual(client.recent_args, (ACCOUNT_ID, 20, 7))
        self.assertEqual(client.detail_calls, [new_id])
        self.assertEqual(result.discovered, 2)
        self.assertEqual(result.missing, 1)
        self.assertEqual(result.ready, 1)
        self.assertEqual(result.generated, 1)
        self.assertTrue(result.changed)
        self.assertIn(f"Mirana_{existing_id}.html", build_sources)
        self.assertIn(f"Mirana_{new_id}_20260711_100000.html", build_sources)
        self.assertEqual(generated_sources[0]["opendota_fetched_at"][-1], "Z")

    def test_refresh_batches_parse_requests_waits_once_and_refetches(self):
        module = self._module()
        first_id = 8891116798
        second_id = 8891064472
        client = FakeOpenDotaClient(
            [_recent(first_id), _recent(second_id)],
            {
                first_id: [_detail(first_id, parsed=False), _detail(first_id, parsed=True)],
                second_id: [_detail(second_id, parsed=False), _detail(second_id, parsed=True)],
            },
        )
        waits = []

        with tempfile.TemporaryDirectory() as public:
            result = module.refresh_public_reports(
                public_dir=public,
                parse_wait=45,
                opendota_client=client,
                use_stratz=False,
                use_d2pt=False,
                analyze_fn=lambda match_data, **_kwargs: _analysis(match_data),
                ai_fn=lambda *_args: "coach",
                report_fn=lambda analysis, _coach, output_dir=None, **_kwargs: str(
                    Path(output_dir, f"Mirana_{analysis['match_id']}_20260711_100000.html")
                ),
                build_fn=lambda *_args, **_kwargs: None,
                sleep_fn=waits.append,
            )

        self.assertEqual(client.parse_requests, [first_id, second_id])
        self.assertEqual(waits, [45])
        self.assertEqual(client.detail_calls, [first_id, second_id, first_id, second_id])
        self.assertEqual(result.requested_parse, 2)
        self.assertEqual(result.generated, 2)

    def test_refresh_defers_missing_timeline_or_invalid_findings_without_building(self):
        module = self._module()
        missing_timeline_id = 8891116798
        invalid_findings_id = 8891064472
        client = FakeOpenDotaClient(
            [_recent(missing_timeline_id), _recent(invalid_findings_id)],
            {
                missing_timeline_id: [_detail(missing_timeline_id, parsed=False)],
                invalid_findings_id: [_detail(invalid_findings_id, parsed=True)],
            },
        )
        built = []

        def fake_analyze(match_data, **_kwargs):
            if match_data["match_id"] == missing_timeline_id:
                return _analysis(match_data, timeline_status="missing")
            return _analysis(match_data, valid_findings=False)

        with tempfile.TemporaryDirectory() as public:
            result = module.refresh_public_reports(
                public_dir=public,
                parse_wait=0,
                opendota_client=client,
                use_stratz=False,
                use_d2pt=False,
                analyze_fn=fake_analyze,
                ai_fn=lambda *_args: "coach",
                report_fn=lambda *_args, **_kwargs: self.fail("deferred report must not render"),
                build_fn=lambda *_args, **_kwargs: built.append(True),
            )

        self.assertEqual(result.deferred, 2)
        self.assertEqual(result.generated, 0)
        self.assertFalse(result.changed)
        self.assertEqual(built, [])

    def test_refresh_with_no_unseen_ranked_match_is_deterministic_no_change(self):
        module = self._module()
        existing_id = 8867002237
        client = FakeOpenDotaClient([_recent(existing_id)], {})

        with tempfile.TemporaryDirectory() as public:
            self._write_existing_report(public, existing_id)
            result = module.refresh_public_reports(
                public_dir=public,
                opendota_client=client,
                use_stratz=False,
                use_d2pt=False,
                analyze_fn=lambda *_args, **_kwargs: self.fail("existing match must not be analyzed"),
                build_fn=lambda *_args, **_kwargs: self.fail("no-change refresh must not build"),
            )

        self.assertEqual(result.missing, 0)
        self.assertEqual(result.generated, 0)
        self.assertFalse(result.changed)

    def test_timeline_readiness_accepts_available_or_partial_only(self):
        module = self._module()
        self.assertTrue(module.analysis_is_publishable(_analysis({"match_id": 1}, "available")))
        self.assertTrue(module.analysis_is_publishable(_analysis({"match_id": 1}, "partial")))
        self.assertFalse(module.analysis_is_publishable(_analysis({"match_id": 1}, "missing")))
        self.assertFalse(module.analysis_is_publishable(_analysis({"match_id": 1}, "available", False)))

    def test_publishability_defers_reports_with_missing_evidence_classes(self):
        module = self._module()

        analysis = _analysis({"match_id": 1}, missing_evidence=True)

        self.assertFalse(module.analysis_is_publishable(analysis))


if __name__ == "__main__":
    unittest.main()
