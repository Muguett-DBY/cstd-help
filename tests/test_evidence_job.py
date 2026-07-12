import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from scripts import fetch_review_evidence
from scripts.fetch_review_evidence import EvidenceJobError, run_evidence_job


ACCOUNT_ID = 173776719
MATCH_ID = 8892808420


class FakeOpenDota:
    def __init__(self):
        self.recent = [{"match_id": MATCH_ID, "lobby_type": 7}]
        self.detail = {
            "match_id": MATCH_ID,
            "players": [{"account_id": ACCOUNT_ID, "hero_id": 48, "deaths": 4}],
        }

    def get_recent_matches(self, account_id, limit=20, lobby_type=None):
        return list(self.recent)

    def get_match(self, match_id):
        return self.detail

    def parse_match_for_player(self, detail, account_id=None):
        return detail["players"][0]


class FakeStratz:
    def get_match_detail(self, match_id, include_playback=True):
        return {"id": match_id, "players": [{"playbackData": {}}]}


def complete_analysis(*_args, **_kwargs):
    return {
        "hero_name": "Luna",
        "timeline": {"available": True},
        "events": {
            "death_count_expected": 1,
            "deaths": [{"minute": 12.0}],
            "purchases": [{"minute": 10.0}],
            "has_purchase_timeline": True,
        },
        "review_findings": [{
            "category": "death_review",
            "action": "下一局目标前先确认撤退路线。",
            "success_metric": "目标前死亡=0。",
        }],
        "data_quality": {"limitations": []},
    }


class EvidenceJobTests(unittest.TestCase):
    def test_job_returns_versioned_complete_analysis_for_recent_match(self):
        result = run_evidence_job(
            MATCH_ID,
            account_id=ACCOUNT_ID,
            opendota_client=FakeOpenDota(),
            stratz_client=FakeStratz(),
            analyze_fn=complete_analysis,
            now=datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["match_id"], MATCH_ID)
        self.assertEqual(result["source"], "github_actions_stratz")
        self.assertEqual(result["analysis"]["hero_name"], "Luna")

    def test_job_rejects_match_outside_fixed_recent_ten(self):
        with self.assertRaises(EvidenceJobError) as raised:
            run_evidence_job(
                123,
                account_id=ACCOUNT_ID,
                opendota_client=FakeOpenDota(),
                stratz_client=FakeStratz(),
                analyze_fn=complete_analysis,
            )

        self.assertEqual(raised.exception.code, "MATCH_NOT_RECENT")

    def test_job_refuses_to_publish_incomplete_evidence(self):
        def incomplete(*_args, **_kwargs):
            analysis = complete_analysis()
            analysis["timeline"] = {"available": False}
            analysis["events"] = {
                "death_count_expected": 4,
                "deaths": [],
                "purchases": [],
                "has_purchase_timeline": False,
            }
            return analysis

        with self.assertRaises(EvidenceJobError) as raised:
            run_evidence_job(
                MATCH_ID,
                account_id=ACCOUNT_ID,
                opendota_client=FakeOpenDota(),
                stratz_client=FakeStratz(),
                analyze_fn=incomplete,
            )

        self.assertEqual(raised.exception.code, "INCOMPLETE_EVIDENCE")

    def test_failed_cli_removes_stale_evidence_file_and_replaces_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = Path(temp_dir) / "evidence.json"
            status_path = Path(temp_dir) / "status.json"
            evidence_path.write_text('{"stale":true}', encoding="utf-8")
            with mock.patch.object(fetch_review_evidence, "STRATZ_API_KEY", ""):
                code = fetch_review_evidence.main([
                    "--match-id", str(MATCH_ID),
                    "--evidence-output", str(evidence_path),
                    "--status-output", str(status_path),
                ])

            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 1)
            self.assertFalse(evidence_path.exists())
            self.assertEqual(status["status"], "failed")
            self.assertEqual(status["error_code"], "STRATZ_SECRET_MISSING")


if __name__ == "__main__":
    unittest.main()
