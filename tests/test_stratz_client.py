import unittest

from api.stratz import StratzClient


ACCOUNT_ID = 173776719


class RecordingStratzClient(StratzClient):
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.last_warning = None

    def _execute(self, query, variables=None):
        self.calls.append((query, dict(variables or {})))
        return self.responses.pop(0)


class StratzClientTests(unittest.TestCase):
    def test_rich_evidence_query_merges_match_and_player_stats(self):
        core = {
            "match": {
                "id": 9001,
                "players": [{
                    "steamAccount": {"id": ACCOUNT_ID},
                    "hero": {"id": 48},
                    "isRadiant": True,
                    "stats": {"lastHitsPerMinute": [8, 9]},
                }],
            },
        }
        rich = {
            "match": {
                "id": 9001,
                "parsedDateTime": 1_700_000_000,
                "isStats": True,
                "towerDeaths": [{"time": 800, "npcId": 18, "isRadiant": True}],
                "playbackData": {
                    "towerDeathEvents": [{"time": 800, "radiant": 4, "dire": 0}],
                    "roshanEvents": [],
                    "wardEvents": [],
                },
                "players": [{
                    "steamAccount": {"id": ACCOUNT_ID},
                    "hero": {"id": 48},
                    "isRadiant": True,
                    "playbackData": {"deathEvents": [{"time": 900}]},
                    "stats": {
                        "deathEvents": [{
                            "time": 900,
                            "timeDead": 40,
                            "goldLost": 250,
                            "positionX": 120,
                            "positionY": 140,
                        }],
                        "itemPurchases": [{"time": 600, "itemId": 50}],
                        "actionsPerMinute": [300, 360],
                    },
                }],
            },
        }
        client = RecordingStratzClient([core, rich])

        match = client.get_match_detail(9001, include_playback=True, account_id=ACCOUNT_ID)

        self.assertEqual(match["parsedDateTime"], 1_700_000_000)
        self.assertTrue(match["isStats"])
        self.assertEqual(match["towerDeaths"][0]["npcId"], 18)
        self.assertIn("towerDeathEvents", match["playbackData"])
        player = match["players"][0]
        self.assertEqual(player["stats"]["lastHitsPerMinute"], [8, 9])
        self.assertEqual(player["stats"]["deathEvents"][0]["goldLost"], 250)
        self.assertEqual(player["stats"]["itemPurchases"][0]["itemId"], 50)
        rich_query, rich_variables = client.calls[1]
        self.assertIn("players(steamAccountId: $steamId)", rich_query)
        self.assertIn("wardDestruction", rich_query)
        self.assertEqual(rich_variables["steamId"], ACCOUNT_ID)

    def test_request_match_reparse_uses_stratz_retry_mutation(self):
        client = RecordingStratzClient([{"retryMatchDownload": True}])

        accepted = client.request_match_reparse(9001)

        self.assertTrue(accepted)
        query, variables = client.calls[0]
        self.assertIn("retryMatchDownload", query)
        self.assertEqual(variables, {"matchId": 9001})


if __name__ == "__main__":
    unittest.main()
