import unittest

from scripts.audit_recent_evidence import audit_recent_matches


class FakeOpenDota:
    def get_recent_matches(self, account_id, limit, lobby_type=None):
        return [
            {"match_id": 20, "lobby_type": 7},
            {"match_id": 10, "lobby_type": 7},
        ]

    def get_match(self, match_id):
        return {"match_id": match_id, "players": [{"account_id": 173776719}]}

    def parse_match_for_player(self, detail, account_id=None):
        return {"match_id": detail["match_id"], "account_id": account_id}


class FakeStratz:
    last_warning = None

    def get_match_detail(self, match_id, include_playback=True):
        return {"id": match_id, "_fetch_warnings": []}


def fake_analyze(player, *, stratz_data=None, opendota_data=None):
    match_id = player["match_id"]
    gaps = [] if match_id == 20 else ["death_positions"]
    return {
        "match_id": match_id,
        "hero_name": "Luna",
        "role_profile": {"label": "1号位"},
        "data_quality": {
            "score": 100 if not gaps else 94,
            "blocking_gaps": gaps,
            "field_ledger": [
                {"id": "core_stats", "status": "available"},
                {"id": "death_positions", "status": "available" if not gaps else "partial"},
            ],
        },
    }


class RecentEvidenceAuditTests(unittest.TestCase):
    def test_audit_reports_every_match_and_blocks_on_required_gap(self):
        result = audit_recent_matches(
            account_id=173776719,
            limit=2,
            opendota_client=FakeOpenDota(),
            stratz_client=FakeStratz(),
            analyze_fn=fake_analyze,
        )

        self.assertEqual(result["match_count"], 2)
        self.assertEqual(result["complete_count"], 1)
        self.assertFalse(result["all_complete"])
        self.assertTrue(result["matches"][0]["complete"])
        self.assertEqual(result["matches"][1]["blocking_gaps"], ["death_positions"])
        self.assertEqual(result["matches"][1]["field_status_counts"]["partial"], 1)


if __name__ == "__main__":
    unittest.main()
