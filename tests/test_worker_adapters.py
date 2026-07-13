import json
import unittest

from worker.cloudflare_adapters import (
    CloudflareDotaGateway,
    GitHubEvidenceGateway,
    GitHubMatchRefreshGateway,
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.ok = 200 <= status < 300

    async def json(self):
        return self.payload


class FakeFetcher:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, url, **options):
        self.calls.append((url, options))
        return self.responses.pop(0)


class CloudflareAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_matches_requests_fixed_ranked_filter(self):
        fetcher = FakeFetcher([FakeResponse([{"match_id": 1}])])
        gateway = CloudflareDotaGateway(fetcher=fetcher)

        result = await gateway.recent_ranked_matches(173776719, 20)

        self.assertEqual(result, [{"match_id": 1}])
        url, options = fetcher.calls[0]
        self.assertIn("/players/173776719/matches", url)
        self.assertIn("limit=20", url)
        self.assertIn("lobby_type=7", url)
        self.assertEqual(options["headers"]["Accept"], "application/json")

    async def test_stratz_without_secret_is_optional(self):
        gateway = CloudflareDotaGateway(fetcher=FakeFetcher([]), stratz_api_key="")

        self.assertIsNone(await gateway.stratz_detail(8891116798))

    async def test_github_evidence_dispatch_is_fixed_to_configured_workflow(self):
        fetcher = FakeFetcher([FakeResponse({}, status=204)])
        gateway = GitHubEvidenceGateway(
            fetcher=fetcher,
            token="test-token",
            repository="Muguett-DBY/cstd-help",
            workflow="on-demand-review.yml",
            ref="main",
        )

        result = await gateway.dispatch(8892808420)

        self.assertTrue(result["accepted"])
        url, options = fetcher.calls[0]
        self.assertEqual(
            url,
            "https://api.github.com/repos/Muguett-DBY/cstd-help/actions/workflows/on-demand-review.yml/dispatches",
        )
        self.assertEqual(options["method"], "POST")
        self.assertEqual(options["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(
            json.loads(options["body"]),
            {"ref": "main", "inputs": {"match_id": "8892808420"}},
        )

    async def test_github_match_refresh_dispatch_has_no_user_control_inputs(self):
        fetcher = FakeFetcher([FakeResponse({}, status=204)])
        gateway = GitHubMatchRefreshGateway(
            fetcher=fetcher,
            token="test-token",
            repository="Muguett-DBY/cstd-help",
            workflow="on-demand-match-refresh.yml",
            ref="main",
        )

        result = await gateway.dispatch()

        self.assertTrue(result["accepted"])
        url, options = fetcher.calls[0]
        self.assertEqual(
            url,
            "https://api.github.com/repos/Muguett-DBY/cstd-help/actions/workflows/on-demand-match-refresh.yml/dispatches",
        )
        self.assertEqual(json.loads(options["body"]), {"ref": "main"})

if __name__ == "__main__":
    unittest.main()
