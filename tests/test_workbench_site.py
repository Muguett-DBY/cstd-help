import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.build_workbench_site import _seed_match, build_workbench_site


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

    def test_seed_match_preserves_unknown_duration_and_kda(self):
        match = _seed_match({
            "match_id": 123,
            "hero": "Anti-Mage",
            "file": "Anti-Mage_123.html",
            "kda": {},
        })

        self.assertIsNone(match["duration_seconds"])
        self.assertEqual(match["kda"], {
            "kills": None,
            "deaths": None,
            "assists": None,
        })

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

    def test_history_never_coerces_missing_kda_to_zero(self):
        self.assertNotIn("Number(kda.kills) || 0", self.history_js)
        self.assertNotIn("Number(kda.deaths) || 0", self.history_js)
        self.assertNotIn("Number(kda.assists) || 0", self.history_js)
        self.assertIn("numberLabel(kda.kills)", self.history_js)

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

    def test_match_page_never_coerces_missing_facts_to_zero(self):
        for unsafe in (
            "Number(kda.kills) || 0",
            "Number(kda.deaths) || 0",
            "Number(kda.assists) || 0",
            "Number(detail.radiant_score) || 0",
            "Number(detail.dire_score) || 0",
            "Number(player.kills) || 0",
            "Number(player.deaths) || 0",
            "Number(player.assists) || 0",
            "Number(player.stuns || 0)",
        ):
            self.assertNotIn(unsafe, self.match_js)
        self.assertIn("numberLabel(kda.kills)", self.match_js)
        self.assertIn("numberLabel(detail.radiant_score)", self.match_js)
        self.assertIn("hasFiniteNumber(player.stuns)", self.match_js)

    def test_match_page_renders_facts_actions_timeline_events_and_limits(self):
        for token in (
            "renderParticipants",
            "renderFinalItems",
            "renderActions",
            "renderFormulaScores",
            "renderPerformanceContext",
            "renderExtendedMetrics",
            "renderTimeline",
            "renderEvents",
            "renderDeathCoordinateMap",
            "renderFindings",
            "renderSourceReconciliation",
            "renderDataLimits",
        ):
            self.assertIn(token, self.match_js)
        self.assertIn("只展示原始坐标，不生成地图区域名", self.match_js)
        self.assertIn(".death-coordinate-plot", self.css)
        self.assertIn(".death-cost-strip", self.css)
        self.assertIn(
            "renderFindings(guidance.review_points || analysis.review_findings || [])",
            self.match_js,
        )
        self.assertIn(
            "finding.title || finding.category_label || finding.category",
            self.match_js,
        )
        self.assertIn("analysis.performance_context", self.match_js)
        self.assertIn("analysis.opendota_benchmarks", self.match_js)
        self.assertIn("benchmarkRawLabel", self.match_js)
        self.assertIn("maximumFractionDigits: 2", self.match_js)
        self.assertIn("timeline.damage_windows", self.match_js)
        self.assertIn("timeline.tower_windows", self.match_js)
        self.assertIn("timeline.death_overlap_windows", self.match_js)
        self.assertIn("timeline.death_recovery_windows", self.match_js)
        self.assertIn("timeline.death_resource_deltas", self.match_js)
        self.assertIn("输出高峰", self.match_js)
        self.assertIn("推塔高峰", self.match_js)
        self.assertIn("复活后恢复与再死", self.match_js)
        self.assertIn("events?.objectives || []", self.match_js)
        self.assertIn("events?.death_objective_windows || []", self.match_js)
        self.assertIn("events?.kills || []", self.match_js)
        self.assertIn("events?.assists || []", self.match_js)
        self.assertIn("events?.vision_summary || {}", self.match_js)
        self.assertIn("回放终局前至少死亡", self.match_js)
        self.assertIn("death_cost_summary", self.match_js)
        self.assertIn("死亡总时长", self.match_js)
        self.assertIn("给出金钱 / 经验", self.match_js)
        self.assertIn("死亡事件真实成本", self.match_js)
        self.assertIn("extended.source", self.match_js)
        self.assertIn("data_quality?.field_ledger", self.match_js)
        self.assertIn("data_quality?.source_reconciliation", self.match_js)
        self.assertIn("证据源对账", self.match_js)
        self.assertIn("字段覆盖账本", self.match_js)
        self.assertIn("guidance?.overall_equation", self.match_js)
        self.assertIn("分项权重", self.match_js)
        self.assertIn("limitsPanel.open = list.length > 0", self.match_js)
        self.assertIn("表现上下文", self.match_html)
        self.assertIn("公式评分", self.match_html)
        self.assertIn("扩展比赛数据", self.match_html)
        self.assertNotIn("AI", self.match_html + self.match_js)
        self.assertIn("const MAX_REVIEW_POLL_ATTEMPTS = 210", self.match_js)
        self.assertIn(".timeline-diagnostic-grid", self.css)
        self.assertIn(".event-group-wide", self.css)

    def test_event_timeline_expands_when_key_purchases_are_empty(self):
        self.assertIn(
            'target.classList.toggle("single-column", purchases.length === 0)',
            self.match_js,
        )
        self.assertRegex(
            self.css,
            r"\.event-columns\.single-column\s*\{[^}]*grid-template-columns:\s*1fr",
        )

    def test_key_purchase_cards_show_cost_and_post_item_evidence(self):
        self.assertIn("events?.post_item_windows || []", self.match_js)
        self.assertIn("purchase.item_cost", self.match_js)
        self.assertIn("postWindow?.summary", self.match_js)
        self.assertRegex(
            self.css,
            r"\.event-columns\s*\{[^}]*align-items:\s*start",
        )

    def test_event_timeline_renders_buyback_redeath_windows(self):
        self.assertIn("events?.buyback_death_windows || []", self.match_js)
        self.assertIn("买活后再次死亡", self.match_js)
        self.assertIn("redeath_seconds", self.match_js)
        self.assertRegex(self.css, r"\.buyback-event-strip\s*\{")

    def test_responsive_accessible_styles_cover_mobile_and_focus(self):
        self.assertIn("@media (max-width: 720px)", self.css)
        self.assertIn(":focus-visible", self.css)
        self.assertRegex(self.css, r"min-height:\s*44px")
        self.assertIn("overflow-x: hidden", self.css)
        self.assertNotIn("letter-spacing: -", self.css)
        self.assertNotRegex(self.css, r"font-size:[^;]*vw")

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
        self.assertIn("img-src 'self' data: https://cdn.cloudflare.steamstatic.com https://cdn.steamstatic.com", self.headers)
        self.assertIn(
            "script-src 'self' https://unpkg.com https://static.cloudflareinsights.com;",
            self.headers,
        )
        self.assertIn("frame-ancestors 'none'", self.headers)
        self.assertIn("X-Content-Type-Options: nosniff", self.headers)
        self.assertNotIn("/*.html", self.headers)

    def test_entry_assets_bypass_stale_browser_cache(self):
        rendered_assets = "\n".join((
            self.index_html,
            self.match_html,
            self.history_js,
            self.match_js,
        ))
        versions = re.findall(r"/static/[^\"']+\?v=([0-9a-f]{12})", rendered_assets)

        self.assertEqual(len(versions), 6)
        self.assertEqual(len(set(versions)), 1)
        self.assertNotIn("__ASSET_VERSION__", rendered_assets)

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
