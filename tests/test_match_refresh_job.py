import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.fetch_match_cache import main, run_match_cache_job


ACCOUNT_ID = 173776719


class FakeOpenDotaClient:
    def __init__(self, recent=None, details=None):
        self.recent = list(recent or [])
        self.details = dict(details or {})
        self.detail_calls = []

    def get_recent_matches(self, account_id, limit=20, lobby_type=None):
        self.request = (account_id, limit, lobby_type)
        return list(self.recent)

    def get_match(self, match_id):
        self.detail_calls.append(match_id)
        return self.details.get(match_id)


def _recent(match_id, *, lobby_type=7):
    return {
        "match_id": match_id,
        "player_slot": 130,
        "radiant_win": True,
        "lobby_type": lobby_type,
        "duration": 1800,
        "start_time": 1783840000,
        "game_mode": 22,
        "hero_id": 48,
        "kills": 8,
        "deaths": 3,
        "assists": 11,
        "average_rank": 52,
    }


def _detail(match_id):
    return {
        "match_id": match_id,
        "duration": 1800,
        "start_time": 1783840000,
        "radiant_win": True,
        "players": [
            {
                "account_id": ACCOUNT_ID,
                "player_slot": 130,
                "hero_id": 48,
                "kills": 8,
                "deaths": 3,
                "assists": 11,
            }
        ],
    }


class MatchRefreshJobTests(unittest.TestCase):
    def test_job_builds_fixed_account_list_and_detail_bulk_payload(self):
        client = FakeOpenDotaClient(
            recent=[_recent(30), _recent(29, lobby_type=0), _recent(28)],
            details={30: _detail(30), 28: _detail(28)},
        )

        match_list, detail_bulk = run_match_cache_job(
            account_id=ACCOUNT_ID,
            opendota_client=client,
            now=datetime(2026, 7, 13, tzinfo=timezone.utc),
        )

        self.assertEqual(client.request, (ACCOUNT_ID, 20, 7))
        self.assertEqual([item["match_id"] for item in match_list["matches"]], [30, 28])
        self.assertEqual(client.detail_calls, [30, 28])
        self.assertEqual(match_list["source"], "github_actions_opendota")
        self.assertEqual(
            [item["key"] for item in detail_bulk],
            [
                "match:v2:30",
                "match:v2:28",
                "matches:v1:173776719",
                "match-refresh-status:v1:173776719",
            ],
        )
        cached_detail = json.loads(detail_bulk[0]["value"])
        self.assertEqual(cached_detail["summary"]["match_id"], 30)
        self.assertEqual(cached_detail["player"]["account_id"], ACCOUNT_ID)
        self.assertTrue(cached_detail["participants"][0]["is_self"])
        cached_list = json.loads(detail_bulk[-2]["value"])
        cached_status = json.loads(detail_bulk[-1]["value"])
        self.assertEqual(cached_list["matches"], match_list["matches"])
        self.assertEqual(cached_status["status"], "ready")

    def test_cli_removes_stale_outputs_and_writes_failure_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            list_path = root / "matches.json"
            details_path = root / "details.json"
            status_path = root / "status.json"
            publish_failure_path = root / "publish-failure.json"
            list_path.write_text("stale", encoding="utf-8")
            details_path.write_text("stale", encoding="utf-8")

            exit_code = main(
                [
                    "--list-output",
                    str(list_path),
                    "--details-output",
                    str(details_path),
                    "--status-output",
                    str(status_path),
                    "--publish-failure-output",
                    str(publish_failure_path),
                ],
                opendota_client=FakeOpenDotaClient(),
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(list_path.exists())
            self.assertFalse(details_path.exists())
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "failed")
            self.assertEqual(status["error_code"], "MATCH_LIST_UNAVAILABLE")
            publish_failure = json.loads(
                publish_failure_path.read_text(encoding="utf-8")
            )
            self.assertEqual(publish_failure["status"], "failed")
            self.assertEqual(publish_failure["error_code"], "KV_PUBLISH_FAILED")
