import json
import unittest
from types import SimpleNamespace

from worker.cloudflare_adapters import (
    CloudflareDotaGateway,
    GitHubEvidenceGateway,
    GitHubMatchRefreshGateway,
    WorkersAIGateway,
    parse_ai_output,
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


class FakeAI:
    def __init__(self, output, field="response"):
        self.output = output
        self.field = field
        self.calls = []

    async def run(self, model, payload):
        self.calls.append((model, payload))
        return SimpleNamespace(**{self.field: self.output})


class FakeJsValue:
    def __init__(self, value):
        self.value = value

    def to_py(self):
        return self.value


class FakeDirectAI:
    def __init__(self, response):
        self.response = response

    async def run(self, model, payload):
        return self.response


class CloudflareAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_ai_output_accepts_fenced_json(self):
        payload = {"conclusion": "结论", "review_points": [], "next_actions": [], "data_limits": []}

        parsed = parse_ai_output(f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```")

        self.assertEqual(parsed, payload)

    def test_parse_ai_output_rejects_non_object(self):
        with self.assertRaises(ValueError):
            parse_ai_output("[]")

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

    async def test_workers_ai_receives_structured_findings(self):
        output = {"finding_order": [0]}
        ai = FakeAI(json.dumps(output, ensure_ascii=False))
        gateway = WorkersAIGateway(ai, "@cf/openai/gpt-oss-120b")
        evidence = {"review_findings": [{"category": "resource_continuity"}]}

        result = await gateway.generate(evidence)

        self.assertEqual(result, output)
        model, request = ai.calls[0]
        self.assertEqual(model, "@cf/openai/gpt-oss-120b")
        response_format = request["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertEqual(response_format["json_schema"]["required"], ["finding_order"])
        self.assertEqual(request["temperature"], 0.2)
        self.assertGreaterEqual(request["max_tokens"], 1024)
        self.assertEqual(request["messages"][0]["role"], "system")
        self.assertIn("只负责", request["messages"][0]["content"])
        self.assertEqual(request["messages"][1]["role"], "user")
        self.assertIn("resource_continuity", request["messages"][1]["content"])

    async def test_workers_ai_converts_nested_request_before_crossing_ffi(self):
        output = {"finding_order": [0]}
        ai = FakeAI(json.dumps(output))
        marker = object()
        converted = []

        def converter(payload):
            converted.append(payload)
            return marker

        result = await WorkersAIGateway(
            ai,
            "model",
            js_converter=converter,
        ).generate({"review_findings": [{"category": "death_review"}]})

        self.assertEqual(result, output)
        self.assertEqual(len(converted), 1)
        self.assertIn("messages", converted[0])
        self.assertIs(ai.calls[0][1], marker)

    async def test_workers_ai_remains_compatible_with_legacy_output_field(self):
        output = {"finding_order": []}
        ai = FakeAI(json.dumps(output, ensure_ascii=False), field="output")

        result = await WorkersAIGateway(ai, "model").generate({"review_findings": []})

        self.assertEqual(result, output)

    async def test_workers_ai_converts_nested_pyodide_response_value(self):
        output = {"finding_order": [2, 0, 1]}
        ai = FakeAI(FakeJsValue(output), field="response")

        result = await WorkersAIGateway(ai, "model").generate({"review_findings": []})

        self.assertEqual(result, output)

    async def test_workers_ai_extracts_chat_completions_content(self):
        output = {"finding_order": [1, 0, 2]}
        response = {
            "choices": [{
                "message": {
                    "content": json.dumps(output),
                    "reasoning": "internal reasoning must not reach the coach payload",
                },
            }],
        }

        result = await WorkersAIGateway(FakeDirectAI(response), "model").generate({})

        self.assertEqual(result, output)


if __name__ == "__main__":
    unittest.main()
