import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import tomllib

from scripts.build_worker_bundle import build_worker_bundle
from worker.contracts import ServiceError
from worker.router import route_request


ROOT = Path(__file__).resolve().parents[1]


class FakeService:
    account_id = 173776719

    def __init__(self):
        self.calls = []
        self.error = None
        self.results = {}

    async def _result(self, name, match_id=None):
        self.calls.append((name, match_id))
        if self.error:
            raise self.error
        return self.results.get(name, {"operation": name, "match_id": match_id})

    async def get_matches(self):
        return await self._result("get_matches")

    async def refresh_matches(self):
        return await self._result("refresh_matches")

    async def get_match_detail(self, match_id):
        return await self._result("get_match_detail", match_id)

    async def review_status(self, match_id):
        return await self._result("review_status", match_id)

    async def generate_review(self, match_id):
        return await self._result("generate_review", match_id)


class WorkerRouterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = FakeService()

    async def test_health_exposes_fixed_account_without_secrets(self):
        response = await route_request("GET", "/api/health", self.service)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload, {"status": "ok", "account_id": 173776719})
        self.assertEqual(self.service.calls, [])

    async def test_get_matches_routes_to_cache_only_service(self):
        response = await route_request("GET", "/api/matches", self.service)

        self.assertEqual(response.status, 200)
        self.assertEqual(self.service.calls, [("get_matches", None)])

    async def test_refresh_requires_post(self):
        response = await route_request("GET", "/api/matches/refresh", self.service)

        self.assertEqual(response.status, 405)
        self.assertEqual(response.payload["error"]["code"], "METHOD_NOT_ALLOWED")

    async def test_refresh_post_routes_to_refresh_service(self):
        response = await route_request("POST", "/api/matches/refresh", self.service)

        self.assertEqual(response.status, 200)
        self.assertEqual(self.service.calls, [("refresh_matches", None)])

    async def test_match_detail_route_parses_numeric_id(self):
        response = await route_request("GET", "/api/matches/8891116798", self.service)

        self.assertEqual(response.status, 200)
        self.assertEqual(self.service.calls, [("get_match_detail", 8891116798)])

    async def test_review_status_is_get_only(self):
        response = await route_request("GET", "/api/reviews/8891116798/status", self.service)

        self.assertEqual(response.status, 200)
        self.assertEqual(self.service.calls, [("review_status", 8891116798)])

    async def test_review_generation_requires_post(self):
        get_response = await route_request("GET", "/api/reviews/8891116798", self.service)
        post_response = await route_request("POST", "/api/reviews/8891116798", self.service)

        self.assertEqual(get_response.status, 405)
        self.assertEqual(post_response.status, 200)
        self.assertEqual(self.service.calls, [("generate_review", 8891116798)])

    async def test_review_processing_uses_accepted_status(self):
        self.service.results["generate_review"] = {
            "status": "processing",
            "retry_after_seconds": 5,
        }

        response = await route_request("POST", "/api/reviews/8891116798", self.service)

        self.assertEqual(response.status, 202)
        self.assertEqual(response.payload["status"], "processing")

    async def test_invalid_match_id_returns_stable_error(self):
        response = await route_request("GET", "/api/matches/not-a-number", self.service)

        self.assertEqual(response.status, 400)
        self.assertEqual(response.payload["error"]["code"], "INVALID_MATCH_ID")

    async def test_service_error_is_converted_to_api_response(self):
        self.service.error = ServiceError("UPSTREAM_UNAVAILABLE", "上游不可用", 502)

        response = await route_request("POST", "/api/matches/refresh", self.service)

        self.assertEqual(response.status, 502)
        self.assertEqual(response.payload["error"]["code"], "UPSTREAM_UNAVAILABLE")
        self.assertEqual(response.payload["error"]["message"], "上游不可用")

    async def test_unknown_route_returns_not_found(self):
        response = await route_request("GET", "/api/unknown", self.service)

        self.assertEqual(response.status, 404)
        self.assertEqual(response.payload["error"]["code"], "NOT_FOUND")


class WorkerDeploymentContractTests(unittest.TestCase):
    def test_worker_config_declares_python_ai_kv_and_api_route(self):
        config = (ROOT / "wrangler.toml").read_text(encoding="utf-8")

        self.assertIn('name = "cstd-help-api"', config)
        self.assertIn('main = ".worker-build/worker_entry.py"', config)
        self.assertIn('base_dir = ".worker-build"', config)
        self.assertIn("workers_dev = false", config)
        self.assertIn(
            'compatibility_flags = ["python_workers", "disable_python_external_sdk"]',
            config,
        )
        self.assertIn('ACCOUNT_ID = "173776719"', config)
        self.assertIn('AI_MODEL = "@cf/openai/gpt-oss-120b"', config)
        self.assertIn('binding = "AI"', config)
        self.assertIn('binding = "REVIEW_CACHE"', config)
        self.assertIn('pattern = "dota.custard.top/api/*"', config)
        self.assertIn("[observability]", config)
        self.assertIn("enabled = true", config)
        self.assertIn("head_sampling_rate = 1", config)

    def test_pages_deploy_does_not_use_unsupported_custom_config_path(self):
        workflow = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")
        deploy_line = next(line for line in workflow.splitlines() if "wrangler@4.110.0 pages deploy" in line)

        self.assertNotIn("--config", deploy_line)
        self.assertIn('pages deploy "$GITHUB_WORKSPACE/public"', deploy_line)
        self.assertIn('--cwd "$RUNNER_TEMP"', deploy_line)

    def test_main_deploy_publishes_worker_before_pages(self):
        workflow = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")

        self.assertIn("astral-sh/setup-uv@", workflow)
        self.assertIn("uv sync --locked", workflow)
        self.assertIn("pywrangler deploy", workflow)
        self.assertIn("pages deploy", workflow)
        self.assertLess(workflow.index("pywrangler deploy"), workflow.index("pages deploy"))

    def test_worker_entry_wires_runtime_adapters_without_secret_values(self):
        entry = (ROOT / "worker_entry.py").read_text(encoding="utf-8")

        self.assertIn("CloudflareCache", entry)
        self.assertIn("CloudflareDotaGateway", entry)
        self.assertIn("WorkersAIGateway", entry)
        self.assertIn("route_request", entry)
        self.assertNotIn("Bearer ey", entry)

    def test_worker_packaging_uses_one_locked_cli_dependency_group(self):
        self.assertFalse((ROOT / "requirements.txt").exists())
        self.assertFalse((ROOT / "requirements-cli.txt").exists())
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        cli = project["dependency-groups"]["cli"]
        for dependency in ("requests", "gql", "jinja2", "beautifulsoup4", "lxml"):
            self.assertTrue(any(item.startswith(dependency) for item in cli), dependency)
        self.assertTrue((ROOT / "uv.lock").exists())
        self.assertTrue((ROOT / "pylock.toml").exists())
        for workflow_name in (
            "deploy-pages.yml",
            "refresh-reports.yml",
            "on-demand-review.yml",
        ):
            workflow = (ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
            self.assertIn("astral-sh/setup-uv@", workflow)
            self.assertIn("uv sync --locked --python 3.13 --group cli", workflow)
            self.assertNotIn("pip install", workflow)

    def test_worker_bundle_allowlists_runtime_and_analysis_evidence(self):
        config = tomllib.loads((ROOT / "wrangler.toml").read_text(encoding="utf-8"))
        rules = config.get("rules", [])
        text_rule = next(rule for rule in rules if rule.get("type") == "Text")

        self.assertEqual(config["base_dir"], ".worker-build")
        self.assertEqual(text_rule["globs"], ["analysis/rules/*.json"])
        self.assertFalse(text_rule.get("fallthrough", True))

        with TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "worker-build"
            build_worker_bundle(ROOT, destination)
            bundled = {
                path.relative_to(destination).as_posix()
                for path in destination.rglob("*")
                if path.is_file()
            }

        self.assertIn("worker_entry.py", bundled)
        self.assertIn("worker/service.py", bundled)
        self.assertIn("analysis/analyzer.py", bundled)
        self.assertIn("analysis/coach_contract.py", bundled)
        self.assertIn("analysis/evidence_contract.py", bundled)
        self.assertIn("analysis/rules/heroes.json", bundled)
        self.assertIn("api/normalization.py", bundled)
        self.assertNotIn("tests/test_worker_router.py", bundled)
        self.assertNotIn("public/index.html", bundled)
        self.assertNotIn("requirements-cli.txt", bundled)

    def test_windows_worker_launcher_keeps_uv_and_pyodide_on_workspace_drive(self):
        launcher = (ROOT / "scripts" / "run_worker_dev.ps1").read_text(encoding="utf-8")
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("UV_CACHE_DIR", launcher)
        self.assertIn("UV_PYTHON_INSTALL_DIR", launcher)
        self.assertIn("pywrangler", launcher)
        self.assertIn("build_worker_bundle.py", launcher)
        self.assertIn("python -m uv tool run --from uv uv run pywrangler", launcher)
        self.assertNotIn("Get-Command uvx", launcher)
        self.assertIn(".uv-cache/", ignore)
        self.assertIn(".uv-python/", ignore)
        self.assertIn(".venv-workers/", ignore)
        self.assertIn(".worker-build/", ignore)

    def test_on_demand_evidence_workflow_is_manual_and_kv_only(self):
        workflow_path = ROOT / ".github" / "workflows" / "on-demand-review.yml"
        self.assertTrue(workflow_path.is_file())
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("STRATZ_API_KEY", workflow)
        self.assertIn("wrangler@4.110.0 kv key put", workflow)
        self.assertIn("37577b67ad5f47b2a0e03b4d5a5ee929", workflow)


if __name__ == "__main__":
    unittest.main()
