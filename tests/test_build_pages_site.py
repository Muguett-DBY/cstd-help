import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_pages_site as pages_site
from scripts import check_public_site


class BuildPagesSiteTests(unittest.TestCase):
    def _write_report(self, directory, metadata, filename="Mirana_8867002237_20260626_224839.html", focus="前10分钟资源"):
        path = Path(directory) / filename
        payload = json.dumps(metadata, ensure_ascii=False).replace("</", "<\\/")
        path.write_text(
            "<!doctype html><html><head><title>Mirana 复盘报告</title></head>"
            "<body>"
            '<a class="back-link" href="index.html">← 比赛历史</a>'
            '<div class="finding-card high">'
            f'<div class="finding-title">{focus}</div>'
            '<div class="finding-line"><strong>训练目标:</strong> 下一局前10分钟低效率窗口=0。</div>'
            '<div class="finding-line"><strong>验收标准:</strong> 10分钟补刀>=35。</div>'
            "</div>"
            f'<script id="report-metadata" type="application/json">{payload}</script>'
            "</body></html>",
            encoding="utf-8",
        )
        return path

    def test_static_site_checker_detects_missing_local_links(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "index.html").write_text(
                '<html><body><a href="missing-report.html">broken</a><a href="https://example.com">external</a></body></html>',
                encoding="utf-8",
            )
            (public_path / "present.html").write_text("<html></html>", encoding="utf-8")

            issues = check_public_site._find_local_link_issues(public_path)

        self.assertEqual(issues, ["index.html -> missing-report.html"])

    def test_static_site_checker_detects_broken_anchor_links(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "index.html").write_text(
                '<html><body><a href="#missing-local">bad local</a>'
                '<a href="present.html#ok">ok</a>'
                '<a href="present.html#missing">bad target</a>'
                '<section id="present"></section></body></html>',
                encoding="utf-8",
            )
            (public_path / "present.html").write_text('<html><body><div id="ok"></div></body></html>', encoding="utf-8")

            issues = check_public_site._find_anchor_issues(public_path)

        self.assertEqual(
            issues,
            [
                "index.html -> #missing-local",
                "index.html -> present.html#missing",
            ],
        )

    def test_static_site_checker_detects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "index.html").write_text(
                '<html><body><section id="dup"></section><div id="dup"></div></body></html>',
                encoding="utf-8",
            )

            issues = check_public_site._find_duplicate_id_issues(public_path)

        self.assertEqual(issues, ["index.html -> duplicate id 'dup'"])

    def test_static_site_checker_detects_unresolved_item_names(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Dragon_Knight_1.html").write_text(
                '<html><body><div title="Item #600">Item #600</div></body></html>',
                encoding="utf-8",
            )
            finder = getattr(check_public_site, "_find_unresolved_item_references", lambda *_: [])

            issues = finder(public_path)

        self.assertEqual(issues, ["Dragon_Knight_1.html -> Item #600"])

    def test_parse_report_uses_embedded_match_metadata(self):
        metadata = {
            "match_id": 8867002237,
            "hero": {"id": 9, "name": "Mirana", "slug": "mirana"},
            "is_win": False,
            "ended_at": "2026-06-26T10:23:19Z",
            "duration_seconds": 2894,
            "kda": {"kills": 13, "deaths": 5, "assists": 21},
            "score": {"team": 43, "enemy": 39},
            "allies": [{"name": "Mirana", "slug": "mirana"}],
            "enemies": [{"name": "Axe", "slug": "axe"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = self._write_report(tmp, metadata)

            parsed = pages_site._parse_report(report)

        self.assertEqual(parsed["hero"], "Mirana")
        self.assertEqual(parsed["ended_at"], "2026-06-26T10:23:19Z")
        self.assertEqual(parsed["duration_seconds"], 2894)
        self.assertEqual(parsed["kda"]["assists"], 21)
        self.assertEqual(parsed["enemies"][0]["name"], "Axe")
        self.assertEqual(parsed["review_focus"], "前10分钟资源")
        self.assertEqual(parsed["next_action"], "下一局前10分钟低效率窗口=0。")
        self.assertEqual(parsed["success_metric"], "10分钟补刀>=35。")
        self.assertEqual(parsed["review_priority"], "high")

    def test_parse_report_keeps_all_structured_findings_for_trends(self):
        metadata = {
            "match_id": 8867002237,
            "hero": {"id": 9, "name": "Mirana", "slug": "mirana"},
            "is_win": False,
            "ended_at": "2026-06-26T10:23:19Z",
            "duration_seconds": 2894,
            "kda": {"kills": 13, "deaths": 5, "assists": 21},
            "score": {"team": 43, "enemy": 39},
            "allies": [{"name": "Mirana", "slug": "mirana"}],
            "enemies": [{"name": "Axe", "slug": "axe"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_report(tmp, metadata)
            text = path.read_text(encoding="utf-8")
            second_finding = (
                '<div class="finding-card medium">'
                '<div class="finding-title">中优先级 · 装备后转化</div>'
                '<div class="finding-line"><strong>证据:</strong> 20分钟后已有关键装备。</div>'
                '<div class="finding-line"><strong>训练目标:</strong> 强势装后2分钟内参战。</div>'
                '<div class="finding-line"><strong>验收标准:</strong> 装备后参战次数&gt;=1。</div>'
                '</div>'
            )
            path.write_text(text.replace("</body>", second_finding + "</body>"), encoding="utf-8")

            parsed = pages_site._parse_report(path)

        self.assertEqual(parsed["review_focus"], "前10分钟资源")
        self.assertEqual(len(parsed["review_findings"]), 2)
        self.assertEqual(parsed["review_findings"][1]["review_focus"], "中优先级 · 装备后转化")
        self.assertEqual(parsed["review_findings"][1]["review_evidence"], "20分钟后已有关键装备。")

    def test_parse_legacy_report_does_not_call_generation_time_match_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Mirana_8867002237_20260626_224839.html"
            path.write_text("<html><title>Mirana 复盘报告</title></html>", encoding="utf-8")

            parsed = pages_site._parse_report(path)

        self.assertIsNone(parsed["ended_at"])

    def test_render_index_contains_clickable_match_table_with_real_fields(self):
        reports = [{
            "file": "Mirana_8867002237_20260626_224839.html",
            "hero": "Mirana",
            "hero_slug": "mirana",
            "match_id": "8867002237",
            "is_win": False,
            "ended_at": "2026-06-26T10:23:19Z",
            "duration_seconds": 2894,
            "kda": {"kills": 13, "deaths": 5, "assists": 21},
            "score": {"team": 43, "enemy": 39},
            "allies": [{"name": "Mirana", "slug": "mirana"}],
            "enemies": [{"name": "Axe", "slug": "axe"}],
            "review_focus": "前10分钟资源",
            "next_action": "下一局前10分钟低效率窗口=0。",
            "success_metric": "10分钟补刀>=35。",
            "review_priority": "high",
        }]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "index.html"

            pages_site._render_index(reports, output_path=output)
            text = output.read_text(encoding="utf-8")

        self.assertIn("比赛历史", text)
        self.assertIn("data-ended-at=\"2026-06-26T10:23:19Z\"", text)
        self.assertIn("13 / 5 / 21", text)
        self.assertIn("43 - 39", text)
        self.assertIn("我方阵容", text)
        self.assertIn("敌方阵容", text)
        self.assertIn("优先复盘", text)
        self.assertIn("本局训练重点", text)
        self.assertIn("下一局前10分钟低效率窗口=0。", text)
        self.assertIn("10分钟补刀&gt;=35。", text)
        self.assertIn("筛选比赛", text)
        self.assertIn("id=\"match-search\"", text)
        self.assertIn("data-filter-result=\"lose\"", text)
        self.assertIn("data-filter-priority=\"high\"", text)
        self.assertIn("data-clear-filters", text)
        self.assertIn("URLSearchParams", text)
        self.assertIn("history.replaceState", text)
        self.assertIn("data-result=\"lose\"", text)
        self.assertIn("data-priority=\"high\"", text)
        self.assertIn("data-match-count", text)
        self.assertIn("data-empty-state", text)
        self.assertIn("没有匹配的比赛", text)
        self.assertIn("Mirana_8867002237_20260626_224839.html", text)
        self.assertNotIn("报告生成时间", text)

    def test_build_focus_trends_groups_repeated_findings_with_examples(self):
        reports = [
            {
                "file": "Mirana_1.html",
                "hero": "Mirana",
                "match_id": "1",
                "review_focus": "前10分钟资源",
                "next_action": "下一局前10分钟低效率窗口=0。",
                "success_metric": "10分钟补刀>=35。",
                "review_priority": "high",
            },
            {
                "file": "Doom_2.html",
                "hero": "Doom",
                "match_id": "2",
                "review_focus": "前10分钟资源",
                "next_action": "下一局前10分钟低效率窗口=0。",
                "success_metric": "10分钟补刀>=48。",
                "review_priority": "high",
            },
            {
                "file": "Anti-Mage_3.html",
                "hero": "Anti-Mage",
                "match_id": "3",
                "review_focus": "终结比赛",
                "next_action": "主动呼叫控盾/逼塔。",
                "success_metric": "强势装后2分钟参战>=1。",
                "review_priority": "medium",
            },
        ]

        self.assertTrue(hasattr(pages_site, "_build_focus_trends"))

        trends = pages_site._build_focus_trends(reports)

        self.assertEqual(trends[0]["focus"], "前10分钟资源")
        self.assertEqual(trends[0]["count"], 2)
        self.assertEqual(trends[0]["priority"], "high")
        self.assertEqual(trends[0]["heroes"], ["Doom", "Mirana"])
        self.assertEqual(trends[0]["examples"][0]["match_id"], "1")
        self.assertIn("低效率窗口=0", trends[0]["next_action"])

    def test_build_focus_trends_groups_semantic_aliases_per_match(self):
        reports = [
            {
                "file": "Mirana_1.html",
                "hero": "Mirana",
                "match_id": "1",
                "is_win": False,
                "review_findings": [
                    {
                        "review_focus": "高优先级 · 前10分钟资源",
                        "next_action": "前10分钟低效率窗口清零。",
                        "success_metric": "10分钟补刀>=35。",
                        "review_priority": "high",
                    },
                    {
                        "review_focus": "对线补刀",
                        "next_action": "前10分钟低效率窗口清零。",
                        "success_metric": "10分钟补刀>=35。",
                        "review_priority": "medium",
                    },
                ],
            },
            {
                "file": "Doom_2.html",
                "hero": "Doom",
                "match_id": "2",
                "is_win": True,
                "review_findings": [
                    {
                        "review_focus": "前10分钟发育",
                        "next_action": "先稳定对线资源。",
                        "success_metric": "10分钟补刀>=45。",
                        "review_priority": "high",
                    }
                ],
            },
        ]

        trends = pages_site._build_focus_trends(reports)

        self.assertEqual(len(trends), 1)
        self.assertEqual(trends[0]["topic_id"], "early_resource")
        self.assertEqual(trends[0]["focus"], "前10分钟资源")
        self.assertEqual(trends[0]["count"], 2)
        self.assertEqual(trends[0]["finding_count"], 3)
        self.assertEqual(len(trends[0]["findings"]), 3)
        self.assertEqual(trends[0]["findings"][0]["source_focus"], "前10分钟资源")
        self.assertIn("review_evidence", trends[0]["findings"][0])
        self.assertEqual(
            trends[0]["source_focuses"],
            ["前10分钟发育", "前10分钟资源", "对线补刀"],
        )

    def test_build_pages_site_writes_review_trends_json(self):
        metadata = {
            "match_id": 8867002237,
            "hero": {"id": 9, "name": "Mirana", "slug": "mirana"},
            "is_win": False,
            "ended_at": "2026-06-26T10:23:19Z",
            "duration_seconds": 2894,
            "kda": {"kills": 13, "deaths": 5, "assists": 21},
            "score": {"team": 43, "enemy": 39},
            "allies": [{"name": "Mirana", "slug": "mirana"}],
            "enemies": [{"name": "Axe", "slug": "axe"}],
        }
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as public:
            self._write_report(source, metadata, filename="Mirana_8867002237_20260626_224839.html")
            second = dict(metadata)
            second["match_id"] = 8867002240
            second["hero"] = {"id": 69, "name": "Doom", "slug": "doom_bringer"}
            second["is_win"] = True
            self._write_report(source, second, filename="Doom_8867002240_20260626_224840.html")

            pages_site.build_pages_site(source, public_dir=public)
            trend_path = Path(public) / "review-trends.json"

            self.assertTrue(trend_path.exists())
            payload = json.loads(trend_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["taxonomy_version"], 1)
        self.assertEqual(payload["trends"][0]["focus"], "前10分钟资源")
        self.assertEqual(payload["trends"][0]["count"], 2)

    def test_build_pages_site_writes_site_manifest_and_coverage_panel(self):
        metadata = {
            "match_id": 8867002237,
            "hero": {"id": 9, "name": "Mirana", "slug": "mirana"},
            "is_win": False,
            "ended_at": "2026-06-26T10:23:19Z",
            "duration_seconds": 2894,
            "kda": {"kills": 13, "deaths": 5, "assists": 21},
            "score": {"team": 43, "enemy": 39},
            "allies": [{"name": "Mirana", "slug": "mirana"}],
            "enemies": [{"name": "Axe", "slug": "axe"}],
        }
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as public:
            self._write_report(source, metadata, filename="Mirana_8867002237_20260626_224839.html")
            second = dict(metadata)
            second["match_id"] = 8867002240
            second["hero"] = {"id": 69, "name": "Doom", "slug": "doom_bringer"}
            second["is_win"] = True
            second["ended_at"] = "2026-06-27T01:00:00Z"
            self._write_report(source, second, filename="Doom_8867002240_20260627_090000.html")

            pages_site.build_pages_site(source, public_dir=public)
            manifest = json.loads((Path(public) / "site-manifest.json").read_text(encoding="utf-8"))
            index_html = (Path(public) / "index.html").read_text(encoding="utf-8")
            plan_html = (Path(public) / "practice-plan.html").read_text(encoding="utf-8")

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["report_count"], 2)
        self.assertEqual(manifest["finding_count"], 2)
        self.assertEqual(manifest["topic_count"], 1)
        self.assertEqual(manifest["high_priority_report_count"], 2)
        self.assertEqual(manifest["latest_match"]["hero"], "Doom")
        self.assertEqual(manifest["latest_match"]["match_id"], "8867002240")
        self.assertIn("复盘数据覆盖", index_html)
        self.assertIn("site-manifest.json", index_html)
        self.assertIn("Doom #8867002240", index_html)
        self.assertIn("2 场", index_html)
        self.assertIn("2 条 finding", index_html)
        self.assertIn("1 个训练主题", index_html)
        self.assertIn("data-coverage-panel", index_html)
        self.assertIn("复盘数据覆盖", plan_html)

    def test_build_pages_site_writes_practice_plan_page(self):
        metadata = {
            "match_id": 8867002237,
            "hero": {"id": 9, "name": "Mirana", "slug": "mirana"},
            "is_win": False,
            "ended_at": "2026-06-26T10:23:19Z",
            "duration_seconds": 2894,
            "kda": {"kills": 13, "deaths": 5, "assists": 21},
            "score": {"team": 43, "enemy": 39},
            "allies": [{"name": "Mirana", "slug": "mirana"}],
            "enemies": [{"name": "Axe", "slug": "axe"}],
        }
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as public:
            self._write_report(source, metadata, filename="Mirana_8867002237_20260626_224839.html")
            second = dict(metadata)
            second["match_id"] = 8867002240
            second["hero"] = {"id": 69, "name": "Doom", "slug": "doom_bringer"}
            second["is_win"] = True
            self._write_report(source, second, filename="Doom_8867002240_20260626_224840.html")

            pages_site.build_pages_site(source, public_dir=public)
            index_html = (Path(public) / "index.html").read_text(encoding="utf-8")
            plan_html = (Path(public) / "practice-plan.html").read_text(encoding="utf-8")

        self.assertIn("practice-plan.html", index_html)
        self.assertIn("下一次训练计划", plan_html)
        self.assertIn("第 1 优先级", plan_html)
        self.assertIn("前10分钟资源", plan_html)
        self.assertIn("下一局前10分钟低效率窗口=0。", plan_html)
        self.assertIn("10分钟补刀&gt;=35。", plan_html)
        self.assertIn('class="practice-workbench"', plan_html)
        self.assertIn('data-practice-filter="todo"', plan_html)
        self.assertIn('data-practice-visible-count', plan_html)
        self.assertIn('data-practice-card', plan_html)
        self.assertIn("下一局检查点", plan_html)
        self.assertIn('data-practice-check', plan_html)
        self.assertIn('data-practice-empty', plan_html)
        self.assertIn("localStorage", plan_html)
        self.assertIn('href="trend-early-resource.html?result=lose"', plan_html)
        self.assertIn('href="trend-early-resource.html?result=win"', plan_html)
        self.assertIn('href="trend-early-resource.html?hero=', plan_html)

    def test_build_pages_site_writes_topic_evidence_pages_and_links(self):
        metadata = {
            "match_id": 8867002237,
            "hero": {"id": 9, "name": "Mirana", "slug": "mirana"},
            "is_win": False,
            "ended_at": "2026-06-26T10:23:19Z",
            "duration_seconds": 2894,
            "kda": {"kills": 13, "deaths": 5, "assists": 21},
            "score": {"team": 43, "enemy": 39},
            "allies": [{"name": "Mirana", "slug": "mirana"}],
            "enemies": [{"name": "Axe", "slug": "axe"}],
        }
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as public:
            self._write_report(source, metadata, filename="Mirana_8867002237_20260626_224839.html")
            second = dict(metadata)
            second["match_id"] = 8867002240
            second["hero"] = {"id": 69, "name": "Doom", "slug": "doom_bringer"}
            second["is_win"] = True
            self._write_report(source, second, filename="Doom_8867002240_20260626_224840.html")

            pages_site.build_pages_site(source, public_dir=public)
            topic_path = Path(public) / "trend-early-resource.html"
            topic_exists = topic_path.exists()
            index_html = (Path(public) / "index.html").read_text(encoding="utf-8")
            plan_html = (Path(public) / "practice-plan.html").read_text(encoding="utf-8")
            topic_html = topic_path.read_text(encoding="utf-8")

        self.assertTrue(topic_exists)
        self.assertIn('href="trend-early-resource.html"', index_html)
        self.assertIn('href="trend-early-resource.html"', plan_html)
        self.assertIn("前10分钟资源 · 完整证据", topic_html)
        self.assertIn("Mirana #8867002237", topic_html)
        self.assertIn("Doom #8867002240", topic_html)
        self.assertIn("训练动作", topic_html)
        self.assertIn("打开本局完整复盘", topic_html)
        self.assertIn("topic-workbench", topic_html)
        self.assertIn("topic-switcher", topic_html)
        self.assertIn('data-topic-filter="all"', topic_html)
        self.assertIn('data-topic-filter="win"', topic_html)
        self.assertIn('data-topic-filter="lose"', topic_html)
        self.assertIn('data-topic-card-count', topic_html)
        self.assertIn('data-topic-empty', topic_html)
        self.assertIn('data-topic-clear-filter', topic_html)
        self.assertIn('data-topic-hero-filter', topic_html)
        self.assertIn('data-hero="Mirana"', topic_html)
        self.assertIn('data-hero="Doom"', topic_html)
        self.assertIn('<option value="Mirana">Mirana</option>', topic_html)
        self.assertIn('<option value="Doom">Doom</option>', topic_html)
        self.assertIn("URLSearchParams", topic_html)
        self.assertIn("history.replaceState", topic_html)
        self.assertIn("selectedHero", topic_html)
        self.assertIn('data-result="lose"', topic_html)
        self.assertIn('data-result="win"', topic_html)
        self.assertIn("没有符合当前筛选的证据", topic_html)
        self.assertIn("setupTopicWorkbench", topic_html)

    def test_semantic_trend_provenance_has_visible_styles(self):
        stylesheet = (pages_site.STATIC_SOURCE / "style.css").read_text(encoding="utf-8")

        self.assertIn(".trend-sources", stylesheet)
        self.assertIn(".taxonomy-note", stylesheet)
        self.assertIn(".topic-evidence-card", stylesheet)
        self.assertIn(".topic-evidence-line", stylesheet)
        self.assertIn(".topic-workbench", stylesheet)
        self.assertIn(".topic-switcher", stylesheet)
        self.assertIn(".topic-hero-filter", stylesheet)
        self.assertIn(".topic-page { overflow-x: hidden; }", stylesheet)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", stylesheet)
        self.assertIn(".topic-filter-button", stylesheet)
        self.assertIn(".topic-empty-state", stylesheet)
        self.assertIn(".data-coverage", stylesheet)
        self.assertIn(".practice-workbench", stylesheet)
        self.assertIn(".practice-evidence-links", stylesheet)
        self.assertIn(".practice-checklist", stylesheet)
        self.assertIn(".practice-card[hidden]", stylesheet)
        self.assertIn(".report-section-nav", stylesheet)
        self.assertIn(".skip-link", stylesheet)
        self.assertIn(".report-top-link", stylesheet)
        self.assertRegex(stylesheet, r"\.report-top-link\s*\{[^}]*position:\s*sticky")
        self.assertIn("#timeline-diagnosis table", stylesheet)

    def test_generated_coaching_pages_have_no_trailing_whitespace(self):
        metadata = {
            "match_id": 8867002237,
            "hero": {"id": 9, "name": "Mirana", "slug": "mirana"},
            "is_win": False,
            "ended_at": "2026-06-26T10:23:19Z",
            "duration_seconds": 2894,
            "kda": {"kills": 13, "deaths": 5, "assists": 21},
            "score": {"team": 43, "enemy": 39},
            "allies": [{"name": "Mirana", "slug": "mirana"}],
            "enemies": [{"name": "Axe", "slug": "axe"}],
        }
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as public:
            report_path = self._write_report(source, metadata)
            pages_site.build_pages_site(source, public_dir=public)

            for filename in ("index.html", "practice-plan.html"):
                data = (Path(public) / filename).read_bytes()
                self.assertNotIn(b"\r\n", data, f"{filename} should be written with LF newlines")
                lines = data.decode("utf-8").splitlines()
                self.assertFalse(
                    any(line != line.rstrip() for line in lines),
                    f"{filename} contains trailing whitespace",
                )
            report_data = (Path(public) / report_path.name).read_bytes()
            self.assertNotIn(b"\r\n", report_data, f"{report_path.name} should be written with LF newlines")

    def test_build_pages_site_injects_adjacent_report_navigation(self):
        metadata = {
            "match_id": 8867002237,
            "hero": {"id": 9, "name": "Mirana", "slug": "mirana"},
            "is_win": False,
            "ended_at": "2026-06-26T10:23:19Z",
            "duration_seconds": 2894,
            "kda": {"kills": 13, "deaths": 5, "assists": 21},
            "score": {"team": 43, "enemy": 39},
            "allies": [{"name": "Mirana", "slug": "mirana"}],
            "enemies": [{"name": "Axe", "slug": "axe"}],
        }
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as public:
            self._write_report(source, metadata, filename="Mirana_8867002237_20260626_224839.html")
            older = dict(metadata)
            older["match_id"] = 8866000193
            older["hero"] = {"id": 1, "name": "Anti-Mage", "slug": "antimage"}
            older["ended_at"] = "2026-06-25T16:00:37Z"
            self._write_report(source, older, filename="Anti-Mage_8866000193_20260625_160037.html", focus="终结比赛")

            pages_site.build_pages_site(source, public_dir=public)
            latest = Path(public) / "Mirana_8867002237_20260626_224839.html"
            latest_html = latest.read_text(encoding="utf-8")

        self.assertIn("相邻比赛", latest_html)
        self.assertIn("下一局（更早）", latest_html)
        self.assertIn("Anti-Mage", latest_html)
        self.assertIn("Anti-Mage_8866000193_20260625_160037.html", latest_html)
        self.assertIn("终结比赛", latest_html)

    def test_build_pages_site_upgrades_legacy_reports_with_section_navigation(self):
        metadata = {
            "match_id": 8867002237,
            "hero": {"id": 9, "name": "Mirana", "slug": "mirana"},
            "is_win": False,
            "ended_at": "2026-06-26T10:23:19Z",
            "duration_seconds": 2894,
            "kda": {"kills": 13, "deaths": 5, "assists": 21},
            "score": {"team": 43, "enemy": 39},
            "allies": [{"name": "Mirana", "slug": "mirana"}],
            "enemies": [{"name": "Axe", "slug": "axe"}],
        }
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as public:
            path = self._write_report(source, metadata)
            text = path.read_text(encoding="utf-8")
            sections = (
                '<div class="section priority-section"><div class="section-header">教练总结</div></div>'
                '<div class="section priority-section"><div class="section-header">下一局行动清单</div></div>'
                '<div class="section"><div class="section-header">比赛概览</div></div>'
                '<div class="section"><div class="section-header">时间线诊断</div></div>'
                '<div class="section"><div class="section-header">死亡/装备事件</div></div>'
                '<div class="section"><div class="section-header">本局主要问题证据</div></div>'
                '<div class="section"><div class="section-header">出装分析</div></div>'
            )
            path.write_text(text.replace('<div class="finding-card high">', sections + '<div class="finding-card high">'), encoding="utf-8")

            pages_site.build_pages_site(source, public_dir=public)
            report_html = (Path(public) / path.name).read_text(encoding="utf-8")

        self.assertIn('class="skip-link"', report_html)
        self.assertIn('aria-label="报告章节"', report_html)
        self.assertIn('href="#next-actions"', report_html)
        self.assertIn('id="next-actions"', report_html)
        self.assertIn('id="timeline-diagnosis"', report_html)
        self.assertIn('data-report-section-link', report_html)
        self.assertIn('track.scrollTo', report_html)
        self.assertEqual(report_html.count('class="report-section-nav"'), 1)


if __name__ == "__main__":
    unittest.main()
