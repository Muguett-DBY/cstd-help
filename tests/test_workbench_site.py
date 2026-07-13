import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.build_workbench_site import build_workbench_site


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
REPORT_DIR = ROOT / "public"


class WorkbenchSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.public_dir = Path(cls.temp_dir.name) / "public"
        build_workbench_site(
            public_dir=cls.public_dir,
            web_dir=WEB_DIR,
            report_dir=REPORT_DIR,
        )
        cls.index_html = (cls.public_dir / "index.html").read_text(encoding="utf-8")
        cls.match_html = (cls.public_dir / "match.html").read_text(encoding="utf-8")
        cls.shared_js = (cls.public_dir / "static" / "shared.js").read_text(encoding="utf-8")
        cls.history_js = (cls.public_dir / "static" / "history.js").read_text(encoding="utf-8")
        cls.match_js = (cls.public_dir / "static" / "match.js").read_text(encoding="utf-8")
        cls.css = (cls.public_dir / "static" / "workbench.css").read_text(encoding="utf-8")
        cls.headers = (cls.public_dir / "_headers").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_build_outputs_exactly_ten_sorted_seed_matches(self):
        payload = json.loads((self.public_dir / "matches.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["account_id"], 173776719)
        self.assertEqual(len(payload["matches"]), 10)
        ended_at = [match["ended_at"] for match in payload["matches"]]
        self.assertEqual(ended_at, sorted(ended_at, reverse=True))
        self.assertTrue(all(match["hero"]["name"] for match in payload["matches"]))
        self.assertTrue(all(match["legacy_report"].endswith(".html") for match in payload["matches"]))

    def test_home_contains_manual_refresh_and_no_automatic_refresh(self):
        self.assertIn("data-refresh-matches", self.index_html)
        self.assertIn('aria-live="polite"', self.index_html)
        self.assertNotIn("setInterval(", self.index_html + self.history_js)
        self.assertEqual(self.history_js.count("/api/matches/refresh"), 1)
        self.assertIn("payload?.refreshing", self.history_js)
        self.assertIn('apiFetch("/api/matches", { method: "GET"', self.history_js)
        self.assertIn("REFRESH_POLL_INTERVAL_MS", self.history_js)
        self.assertIn(
            "if (hasMatches && !payload?.refreshing && hasNewTimestamp)",
            self.history_js,
        )
        self.assertRegex(
            self.history_js,
            r"addEventListener\(\s*[\"']click[\"']\s*,\s*refreshMatches",
        )

    def test_initial_history_loader_reads_cache_and_seed_only(self):
        self.assertIn('apiFetch("/api/matches"', self.history_js)
        self.assertIn('fetch("/matches.json"', self.history_js)
        self.assertIn("loadCachedMatches();", self.history_js)
        self.assertIn("slice(0, 10)", self.history_js)
        self.assertIn("/match.html?id=", self.history_js)

    def test_match_shell_contains_click_only_analysis_control(self):
        self.assertIn("data-generate-review", self.match_html)
        self.assertIn("data-review-output", self.match_html)
        self.assertIn("data-factual-detail", self.match_html)
        self.assertIn('aria-live="polite"', self.match_html)

        generate_match = re.search(
            r"async function generateReview\(\)[\s\S]*?\n}\n",
            self.match_js,
        )
        init_match = re.search(
            r"async function initMatchPage\(\)[\s\S]*?\n}\n",
            self.match_js,
        )
        self.assertIsNotNone(generate_match)
        self.assertIsNotNone(init_match)
        self.assertIn('method: "POST"', generate_match.group(0))
        self.assertNotIn("generateReview()", init_match.group(0))
        self.assertRegex(
            self.match_js,
            r"addEventListener\(\s*[\"']click[\"']\s*,\s*generateReview",
        )

    def test_review_generation_polls_processing_state_after_user_click(self):
        self.assertIn('payload.status === "processing"', self.match_js)
        self.assertIn("MAX_REVIEW_POLL_ATTEMPTS", self.match_js)
        self.assertIn("retry_after_seconds", self.match_js)

    def test_match_page_sets_hero_first_document_title_and_heading(self):
        self.assertIn("document.title = `${heroName}", self.match_js)
        self.assertIn("heroHeading.textContent = `${heroName}", self.match_js)
        self.assertIn("loadMatchDetail", self.match_js)
        self.assertIn("loadReviewStatus", self.match_js)

    def test_match_page_renders_facts_actions_timeline_events_and_limits(self):
        for token in (
            "renderParticipants",
            "renderFinalItems",
            "renderActions",
            "renderTimeline",
            "renderEvents",
            "renderDeathCoordinateMap",
            "renderFindings",
            "renderDataLimits",
        ):
            self.assertIn(token, self.match_js)
        self.assertIn("只展示原始坐标，不生成地图区域名", self.match_js)
        self.assertIn(".death-coordinate-plot", self.css)
        self.assertIn(
            "renderFindings(coach.review_points || analysis.review_findings || [])",
            self.match_js,
        )
        self.assertIn(
            "finding.title || finding.category_label || finding.category",
            self.match_js,
        )

    def test_responsive_accessible_styles_cover_mobile_and_focus(self):
        self.assertIn("@media (max-width: 720px)", self.css)
        self.assertIn(":focus-visible", self.css)
        self.assertRegex(self.css, r"min-height:\s*44px")
        self.assertIn("overflow-x: hidden", self.css)
        self.assertNotIn("letter-spacing: -", self.css)

    def test_primary_pages_do_not_restore_legacy_coverage_dashboard(self):
        primary = self.index_html + self.match_html
        for old_marker in ("43 份复盘", "189 条问题", "证据覆盖总览", "CI 质量门禁"):
            self.assertNotIn(old_marker, primary)

    def test_all_source_controlled_assets_are_copied(self):
        expected = {
            "favicon.svg",
            "index.html",
            "match.html",
            "matches.json",
            "static/workbench.css",
            "static/shared.js",
            "static/history.js",
            "static/match.js",
        }
        actual = {
            path.relative_to(self.public_dir).as_posix()
            for path in self.public_dir.rglob("*")
            if path.is_file()
        }
        self.assertTrue(expected.issubset(actual))

    def test_primary_pages_reference_the_bundled_favicon(self):
        self.assertIn('href="/favicon.svg"', self.index_html)
        self.assertIn('href="/favicon.svg"', self.match_html)

    def test_primary_pages_pin_external_script_and_ship_scoped_security_headers(self):
        for page in (self.index_html, self.match_html):
            self.assertIn('integrity="sha384-', page)
            self.assertIn('crossorigin="anonymous"', page)
        self.assertIn("Content-Security-Policy:", self.headers)
        self.assertIn(
            "script-src 'self' https://unpkg.com https://static.cloudflareinsights.com;",
            self.headers,
        )
        self.assertIn("frame-ancestors 'none'", self.headers)
        self.assertIn("X-Content-Type-Options: nosniff", self.headers)
        self.assertNotIn("/*.html", self.headers)

    def test_builder_runs_as_direct_cli(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_workbench_site.py"),
                    "--public-dir",
                    str(Path(temp_dir) / "public"),
                    "--web-dir",
                    str(WEB_DIR),
                    "--report-dir",
                    str(REPORT_DIR),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
