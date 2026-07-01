import json
import re
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

    def test_practice_plan_custom_topic_check_ids_are_unique(self):
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
            self._write_report(
                source,
                metadata,
                filename="Mirana_8867002237_20260626_224839.html",
                focus="死亡前后资源变化",
            )
            second = dict(metadata)
            second["match_id"] = 8867002240
            second["hero"] = {"id": 69, "name": "Doom", "slug": "doom_bringer"}
            self._write_report(
                source,
                second,
                filename="Doom_8867002240_20260626_224840.html",
                focus="死亡打断资源",
            )

            pages_site.build_pages_site(source, public_dir=public)
            public_path = Path(public)
            plan_html = (public_path / "practice-plan.html").read_text(encoding="utf-8")
            duplicate_issues = check_public_site._find_duplicate_id_issues(public_path)

        custom_ids = re.findall(r'id="(practice-custom-[^"]+)"', plan_html)
        self.assertEqual(duplicate_issues, [])
        self.assertEqual(len(custom_ids), 6)
        self.assertEqual(len(custom_ids), len(set(custom_ids)))

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

    def test_static_site_checker_detects_report_without_evidence_source_coverage(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Legion_Commander_8870219537.html").write_text(
                "<html><head><title>Legion Commander 复盘报告</title></head>"
                "<body>"
                "下一局行动清单 时间线诊断 10分钟补刀 低效率窗口 数据缺口"
                "</body></html>",
                encoding="utf-8",
            )
            (public_path / "index.html").write_text("<html></html>", encoding="utf-8")

            issues = check_public_site._find_report_evidence_source_issues(public_path)

        self.assertEqual(
            issues,
            [
                "Legion_Commander_8870219537.html -> missing evidence source coverage: "
                "证据来源与覆盖, evidence-source-list, evidence-source-row, 比赛核心数据, 分钟时间线, 购买时间, 死亡时间, 死亡位置"
            ],
        )

    def test_static_site_checker_detects_missing_death_review_coverage(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Legion_Commander_8870219537.html").write_text(
                "<html><head><title>Legion Commander 复盘报告</title></head>"
                "<body>"
                "下一局行动清单 时间线诊断 10分钟补刀 低效率窗口 数据缺口 死亡/装备事件"
                "</body></html>",
                encoding="utf-8",
            )
            (public_path / "index.html").write_text("<html><body>复盘数据覆盖</body></html>", encoding="utf-8")
            (public_path / "site-manifest.json").write_text(
                json.dumps({"schema_version": 1, "report_count": 1}, ensure_ascii=False),
                encoding="utf-8",
            )

            issues = check_public_site._find_death_review_coverage_issues(public_path)

        self.assertEqual(
            issues,
            [
                "Legion_Commander_8870219537.html -> missing death review coverage: "
                "death-review-workbench, death-review-summary, 死亡后恢复窗口, timeline-phase-cards",
                "index.html -> missing death review coverage panel",
                "site-manifest.json -> missing death review coverage fields: "
                "death_review_workbench_report_count, death_recovery_window_report_count, "
                "death_coordinate_map_report_count, complete_death_review_report_count",
            ],
        )

    def test_static_site_checker_detects_missing_quality_gate_summary(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Legion_Commander_8870219537.html").write_text(
                "<html><head><title>Legion Commander 复盘报告</title></head>"
                "<body>"
                '<section id="decision-snapshot" class="decision-snapshot">上分决策卡</section>'
                '<section class="report-trend-context">近期同类问题'
                '<div class="trend-context-examples">完整趋势证据</div></section>'
                '<div class="evidence-source-list"><div class="evidence-source-row">证据来源与覆盖</div></div>'
                "</body></html>",
                encoding="utf-8",
            )
            (public_path / "index.html").write_text("<html><body>复盘数据覆盖</body></html>", encoding="utf-8")
            (public_path / "site-manifest.json").write_text(
                json.dumps({"schema_version": 1, "report_count": 1}, ensure_ascii=False),
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_quality_gate_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "index.html -> missing quality gate panel",
                "site-manifest.json -> missing quality gate summary",
            ],
        )

    def test_static_site_checker_detects_missing_source_freshness_summary(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Legion_Commander_8870219537_20260630_212154.html").write_text(
                "<html><head><title>Legion Commander 复盘报告</title></head>"
                "<body>下一局行动清单</body></html>",
                encoding="utf-8",
            )
            (public_path / "index.html").write_text("<html><body>复盘数据覆盖</body></html>", encoding="utf-8")
            (public_path / "site-manifest.json").write_text(
                json.dumps({"schema_version": 1, "report_count": 1}, ensure_ascii=False),
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_source_freshness_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "index.html -> missing source freshness panel",
                "site-manifest.json -> missing source freshness summary",
            ],
        )

    def test_static_site_checker_detects_missing_evidence_field_audit(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "index.html").write_text("<html><body>复盘数据覆盖</body></html>", encoding="utf-8")
            (public_path / "practice-plan.html").write_text("<html><body>训练计划</body></html>", encoding="utf-8")
            (public_path / "site-manifest.json").write_text(
                json.dumps({"schema_version": 1, "report_count": 1}, ensure_ascii=False),
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_evidence_field_audit_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "index.html -> missing evidence field audit panel",
                "practice-plan.html -> missing evidence field audit panel",
                "site-manifest.json -> missing evidence field audit summary",
            ],
        )

    def test_static_site_checker_rejects_partial_evidence_field_without_report_counts(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            panel = '<html><body><section data-evidence-field-audit-panel>实证字段覆盖</section></body></html>'
            (public_path / "index.html").write_text(panel, encoding="utf-8")
            (public_path / "practice-plan.html").write_text(panel, encoding="utf-8")
            audit = {
                "status": "tracked",
                "basis": "fixture",
                "report_count": 2,
                "payload_match_count": 2,
                "field_count": 1,
                "complete_field_count": 0,
                "partial_field_count": 1,
                "missing_field_count": 0,
                "fields": [{
                    "key": "position_samples",
                    "label": "位置采样",
                    "source": "fixture",
                    "supports": "死亡位置",
                    "coverage_count": 1,
                    "coverage_ratio": 0.5,
                    "status": "partial",
                }],
                "limitation": "fixture",
            }
            (public_path / "site-manifest.json").write_text(
                json.dumps({"report_count": 2, "evidence_field_audit": audit}, ensure_ascii=False),
                encoding="utf-8",
            )

            issues = check_public_site._find_evidence_field_audit_issues(public_path)

        self.assertEqual(
            issues,
            ["site-manifest.json -> partial evidence fields need explicit report counts: position_samples"],
        )

    def test_static_site_checker_accepts_source_bounded_partial_evidence_field(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            panel = '<html><body><section data-evidence-field-audit-panel>实证字段覆盖</section></body></html>'
            (public_path / "index.html").write_text(panel, encoding="utf-8")
            (public_path / "practice-plan.html").write_text(panel, encoding="utf-8")
            audit = {
                "status": "partial",
                "basis": "fixture",
                "report_count": 2,
                "payload_match_count": 2,
                "field_count": 1,
                "complete_field_count": 0,
                "partial_field_count": 1,
                "missing_field_count": 0,
                "fields": [{
                    "key": "position_samples",
                    "label": "位置采样",
                    "source": "fixture",
                    "supports": "死亡位置",
                    "coverage_count": 2,
                    "coverage_ratio": 1.0,
                    "complete_report_count": 1,
                    "partial_report_count": 1,
                    "missing_report_count": 0,
                    "status": "partial",
                }],
                "limitation": "字段覆盖来自报告证据明细；部分字段按已覆盖范围使用。",
            }
            (public_path / "site-manifest.json").write_text(
                json.dumps({"report_count": 2, "evidence_field_audit": audit}, ensure_ascii=False),
                encoding="utf-8",
            )

            issues = check_public_site._find_evidence_field_audit_issues(public_path)

        self.assertEqual(issues, [])

    def test_evidence_field_audit_counts_opendota_teamfight_death_positions(self):
        reports = [{
            "match_id": "8867002237",
            "hero_id": 9,
            "hero": "Mirana",
            "file": "Mirana_8867002237.html",
        }]
        evidence_payloads = {
            "8867002237": {
                "stratz": {
                    "players": [{
                        "steamAccount": {"id": 173776719},
                        "hero": {"id": 9},
                        "playbackData": {"deathEvents": [{"time": 948}]},
                    }]
                },
                "opendota": {
                    "players": [
                        {"account_id": 173776719, "hero_id": 9, "player_slot": 0},
                    ],
                    "teamfights": [{
                        "start": 920,
                        "end": 960,
                        "last_death": 948,
                        "players": [
                            {"deaths": 1, "deaths_pos": {"120": {"140": 1}}},
                        ],
                    }],
                },
            }
        }

        audit = pages_site._build_evidence_field_audit(reports, evidence_payloads)
        fields = {item["key"]: item for item in audit["fields"]}

        self.assertEqual(fields["position_samples"]["coverage_count"], 1)
        self.assertEqual(fields["position_samples"]["status"], "complete")

    def test_evidence_field_audit_marks_partial_death_position_reports(self):
        reports = [{
            "match_id": "8867002237",
            "hero_id": 9,
            "hero": "Mirana",
            "file": "Mirana_8867002237.html",
            "evidence_sources": [{
                "label": "死亡位置",
                "status": "partial",
                "coverage": "覆盖 1/2 次已定位死亡",
            }],
        }]
        evidence_payloads = {
            "8867002237": {
                "stratz": {"players": [{"hero": {"id": 9}}]},
                "opendota": {"players": [{"account_id": 173776719, "hero_id": 9}]},
            }
        }

        audit = pages_site._build_evidence_field_audit(reports, evidence_payloads)
        fields = {item["key"]: item for item in audit["fields"]}

        self.assertEqual(fields["position_samples"]["status"], "partial")
        self.assertEqual(fields["position_samples"]["partial_report_count"], 1)
        self.assertEqual(audit["partial_field_count"], 1)

    def test_static_site_checker_detects_missing_evidence_command_bar(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "index.html").write_text("<html><body>实证字段覆盖</body></html>", encoding="utf-8")
            (public_path / "practice-plan.html").write_text("<html><body>实证字段覆盖</body></html>", encoding="utf-8")

            finder = getattr(check_public_site, "_find_evidence_command_bar_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "index.html -> missing evidence command bar",
                "practice-plan.html -> missing evidence command bar",
            ],
        )

    def test_static_site_checker_detects_missing_or_mismatched_report_source_provenance(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Mirana_8867002237_20260626_224839.html").write_text(
                '<html><body><div class="report-context-deck" data-report-context-deck>'
                '<details class="report-source-provenance" '
                'data-report-source-provenance data-match-id="8867009999" '
                'data-report-generated-at="2026-06-26T22:48:39" '
                'data-stratz-fetched-at="2026-06-26T22:20:00Z" '
                'data-opendota-fetched-at="2026-06-26T22:10:00Z">'
                '<summary class="source-provenance-summary">证据时间 来源完整</summary>'
                'STRATZ 抓取 OpenDota 抓取 报告生成 已缓存证据'
                '</details></div></body></html>',
                encoding="utf-8",
            )
            (public_path / "Doom_8867002240_20260627_090000.html").write_text(
                "<html><body>下一局行动清单</body></html>",
                encoding="utf-8",
            )
            (public_path / "site-manifest.json").write_text(
                json.dumps(
                    {
                        "report_sources": [
                            {
                                "file": "Mirana_8867002237_20260626_224839.html",
                                "match_id": "8867002237",
                                "report_generated_at": "2026-06-26T22:48:39",
                                "stratz_fetched_at": "2026-06-26T22:20:00Z",
                                "opendota_fetched_at": "2026-06-26T22:10:00Z",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_report_source_provenance_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "Doom_8867002240_20260627_090000.html -> missing report source provenance",
                "Mirana_8867002237_20260626_224839.html -> source provenance match id 8867009999 does not match filename 8867002237",
            ],
        )

    def test_static_site_checker_detects_missing_or_mismatched_report_evidence_completeness(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Mirana_8867002237.html").write_text(
                '<html><head><title>Mirana 复盘报告</title></head><body>'
                '<div class="evidence-source-list">'
                '<div class="evidence-source-row available"><div class="evidence-source-name">比赛核心数据</div></div>'
                '<div class="evidence-source-row partial"><div class="evidence-source-name">死亡时间</div></div>'
                '<div class="evidence-source-row missing"><div class="evidence-source-name">视野事件</div></div>'
                '</div>'
                '</body></html>',
                encoding="utf-8",
            )
            (public_path / "Doom_8867002240.html").write_text(
                '<html><head><title>Doom 复盘报告</title></head><body>'
                '<div class="evidence-source-list">'
                '<div class="evidence-source-row available"><div class="evidence-source-name">比赛核心数据</div></div>'
                '</div>'
                '<section class="report-evidence-completeness" data-report-evidence-completeness '
                'data-evidence-total="2" data-evidence-complete="1" data-evidence-usable="1" '
                'data-evidence-partial="0" data-evidence-missing="1">'
                '<div class="evidence-completeness-summary">本局证据完整度</div>'
                '<div class="evidence-completeness-guidance"><strong>执行信号</strong>'
                '<span>本局建议由完整证据支撑，可直接按行动清单执行并复核。</span></div>'
                '<span class="evidence-completeness-chip available">比赛核心数据</span>'
                '</section>'
                '</body></html>',
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_report_evidence_completeness_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "Doom_8867002240.html -> evidence completeness mismatch: total expected 1 got 2; missing expected 0 got 1",
                "Mirana_8867002237.html -> missing report evidence completeness summary",
            ],
        )

    def test_static_site_checker_detects_unstable_report_header_context(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Mirana_8867002237.html").write_text(
                '<html><head><title>Mirana 复盘报告</title></head><body>'
                '<div class="report-context-deck" data-report-context-deck>'
                '<section class="report-evidence-completeness" data-report-evidence-completeness '
                'data-evidence-total="1" data-evidence-complete="1" data-evidence-usable="1" '
                'data-evidence-partial="0" data-evidence-missing="0">'
                '<div class="evidence-completeness-summary">本局证据完整度</div>'
                '<span class="evidence-completeness-chip available">比赛核心数据</span>'
                '<details class="evidence-completeness-details" open><summary>查看证据类明细</summary></details>'
                '</section>'
                '<nav class="report-neighbors" aria-label="相邻比赛"></nav>'
                '<details class="report-source-provenance" open><summary class="source-provenance-summary">证据时间</summary></details>'
                '</div>'
                '<h1>Mirana 复盘报告</h1>'
                '<section id="decision-snapshot" class="decision-snapshot">上分决策卡</section>'
                '</body></html>',
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_report_header_context_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "Mirana_8867002237.html -> report context deck order must be neighbors, source provenance, evidence completeness",
                "Mirana_8867002237.html -> source provenance must be collapsed by default",
                "Mirana_8867002237.html -> evidence completeness details must be collapsed by default",
            ],
        )

    def test_static_site_checker_rejects_report_missing_evidence_classes(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Doom_8867002240.html").write_text(
                '<html><head><title>Doom 复盘报告</title></head><body>'
                '<div class="evidence-source-list">'
                '<div class="evidence-source-row missing"><div class="evidence-source-name">视野事件</div></div>'
                '</div>'
                '<section class="report-evidence-completeness" data-report-evidence-completeness '
                'data-evidence-total="1" data-evidence-complete="0" data-evidence-usable="0" '
                'data-evidence-partial="0" data-evidence-missing="1">'
                '<div class="evidence-completeness-summary">本局证据完整度</div>'
                '<div class="evidence-completeness-guidance"><strong>执行信号</strong>'
                '<span>存在缺失证据类。</span></div>'
                '<span class="evidence-completeness-chip missing">视野事件</span>'
                '</section>'
                '</body></html>',
                encoding="utf-8",
            )

            issues = check_public_site._find_report_evidence_completeness_issues(public_path)

        self.assertEqual(
            issues,
            ["Doom_8867002240.html -> report evidence still has 1 missing classes"],
        )

    def test_static_site_checker_rejects_partial_evidence_scored_as_perfect(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Rubick_8867351572.html").write_text(
                '<html><head><title>Rubick 复盘报告</title></head><body>'
                '<div class="evidence-source-list">'
                '<div class="evidence-source-row available"><div class="evidence-source-name">比赛核心数据</div></div>'
                '<div class="evidence-source-row partial"><div class="evidence-source-name">死亡位置</div></div>'
                '</div>'
                '<section class="report-evidence-completeness" data-report-evidence-completeness '
                'data-evidence-total="2" data-evidence-complete="1" data-evidence-usable="2" '
                'data-evidence-partial="1" data-evidence-missing="0">'
                '<div class="evidence-completeness-summary">本局证据完整度</div>'
                '<div class="evidence-completeness-guidance"><strong>执行信号</strong>'
                '<span>部分证据只按已覆盖范围复核。</span></div>'
                '<span class="evidence-completeness-chip available">比赛核心数据</span>'
                '<span class="evidence-completeness-chip partial">死亡位置</span>'
                '</section>'
                '<div class="decision-rail-item"><span>证据覆盖</span><strong>100/100</strong></div>'
                '<div class="quality-score">100/100</div>'
                '<div class="coach-analysis">数据完整度：100/100。</div>'
                '</body></html>',
                encoding="utf-8",
            )

            issues = check_public_site._find_report_evidence_completeness_issues(public_path)

        self.assertEqual(
            issues,
            ["Rubick_8867351572.html -> partial or missing evidence must not be presented as 100/100"],
        )

    def test_static_site_checker_detects_missing_evidence_execution_guidance(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Mirana_8867002237.html").write_text(
                '<html><head><title>Mirana 复盘报告</title></head><body>'
                '<div class="report-context-deck" data-report-context-deck>'
                '<nav class="report-neighbors" aria-label="相邻比赛"></nav>'
                '<details class="report-source-provenance"><summary class="source-provenance-summary">证据时间</summary></details>'
                '<section class="report-evidence-completeness" data-report-evidence-completeness '
                'data-evidence-total="1" data-evidence-complete="1" data-evidence-usable="1" '
                'data-evidence-partial="0" data-evidence-missing="0">'
                '<div class="evidence-completeness-summary">本局证据完整度</div>'
                '<span class="evidence-completeness-chip available">比赛核心数据</span>'
                '<details class="evidence-completeness-details"><summary>查看证据类明细</summary></details>'
                '</section>'
                '</div>'
                '<h1>Mirana 复盘报告</h1>'
                '<section id="decision-snapshot" class="decision-snapshot">上分决策卡</section>'
                '<div class="evidence-source-list">'
                '<div class="evidence-source-row available"><div class="evidence-source-name">比赛核心数据</div></div>'
                '</div>'
                '</body></html>',
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_report_evidence_completeness_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            ["Mirana_8867002237.html -> missing evidence execution guidance"],
        )

    def test_static_site_checker_detects_report_text_quality_issues(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Legion_Commander_8870219537.html").write_text(
                "<html><head><title>Legion Commander Report</title></head>"
                "<body>死亡后目标窗口 下一局每次准备接失去肉山前90秒</body></html>",
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_report_text_quality_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "Legion_Commander_8870219537.html -> title must include 复盘报告",
                "Legion_Commander_8870219537.html -> awkward coaching phrase: 接失去",
                "Legion_Commander_8870219537.html -> death/objective windows require 目标前90秒生存规则",
            ],
        )

    def test_static_site_checker_detects_missing_hero_benchmark_section(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Legion_Commander_8870219537.html").write_text(
                "<html><head><title>Legion Commander 复盘报告</title></head>"
                "<body>证据来源与覆盖 hero_benchmarks OpenDota英雄样本百分位</body></html>",
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_hero_benchmark_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "Legion_Commander_8870219537.html -> hero benchmark evidence requires rendered 英雄样本百分位 section",
            ],
        )

    def test_static_site_checker_detects_missing_performance_context_section(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Anti_Mage_123.html").write_text(
                "<html><head><title>Anti-Mage 复盘报告</title></head>"
                "<body>证据来源与覆盖 opendota_performance_context</body></html>",
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_performance_context_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "Anti_Mage_123.html -> performance context evidence requires rendered 分路与参战画像 section",
            ],
        )

    def test_static_site_checker_detects_missing_decision_snapshot(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Anti_Mage_123.html").write_text(
                "<html><head><title>Anti-Mage 复盘报告</title></head>"
                "<body>下一局行动清单 finding-card high</body></html>",
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_decision_snapshot_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "Anti_Mage_123.html -> report with findings requires rendered 上分决策卡 decision snapshot",
            ],
        )

    def test_static_site_checker_detects_missing_report_trend_context(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Anti_Mage_123.html").write_text(
                "<html><head><title>Anti-Mage 复盘报告</title></head>"
                "<body>"
                '<section id="decision-snapshot" class="decision-snapshot">上分决策卡</section>'
                '<div class="finding-card high">下一局行动清单</div>'
                "</body></html>",
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_report_trend_context_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "Anti_Mage_123.html -> report with findings requires rendered 近期同类问题 trend context",
            ],
        )

    def test_static_site_checker_detects_manual_review_language(self):
        with tempfile.TemporaryDirectory() as public:
            public_path = Path(public)
            (public_path / "Legion_Commander_123.html").write_text(
                "<html><head><title>Legion Commander 复盘报告</title></head>"
                "<body>"
                '<section id="decision-snapshot" class="decision-snapshot">上分决策卡</section>'
                '<section class="report-trend-context">近期同类问题'
                '<div class="trend-context-examples">完整趋势证据</div></section>'
                '<div class="finding-card high">下一局行动清单</div>'
                "<p>系统检查: 需要回放确认这些点对应的入口。</p>"
                "<p>行动: 下一局每次进入这些重复坐标对应的回放场景前先确认条件。</p>"
                "</body></html>",
                encoding="utf-8",
            )

            finder = getattr(check_public_site, "_find_manual_review_language_issues", lambda *_: [])
            issues = finder(public_path)

        self.assertEqual(
            issues,
            [
                "Legion_Commander_123.html -> manual review language is not allowed: 需要回放确认",
                "Legion_Commander_123.html -> manual review language is not allowed: 回放场景",
            ],
        )

    def test_static_site_checker_classifies_support_pages_and_exports(self):
        support_pages = {
            "index.html",
            "practice-plan.html",
            "match-brief.html",
            "trend-death-cost.html",
        }
        for name in support_pages:
            self.assertFalse(check_public_site._is_report_page(Path(name)), name)

        self.assertTrue(check_public_site._is_report_page(Path("Legion_Commander_8870219537.html")))
        self.assertIn("practice-plan.txt", check_public_site.REQUIRED_SUPPORT_FILES)
        self.assertIn("match-brief.txt", check_public_site.REQUIRED_SUPPORT_FILES)

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
        self.assertEqual(parsed["report_generated_at"], "2026-06-26T22:48:39")
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
            first_report = self._write_report(source, metadata, filename="Mirana_8867002237_20260626_224839.html")
            quality_snippet = (
                '<section id="decision-snapshot" class="decision-snapshot">上分决策卡</section>'
                '<div class="evidence-source-list"><div class="evidence-source-row">证据来源与覆盖</div></div>'
            )
            first_text = first_report.read_text(encoding="utf-8")
            first_report.write_text(
                first_text.replace(
                    "</body>",
                    quality_snippet +
                    '<div class="death-review-workbench"></div>'
                    '<div class="death-coordinate-map"></div>'
                    '<div>死亡后恢复窗口</div>'
                    "</body>",
                ),
                encoding="utf-8",
            )
            second = dict(metadata)
            second["match_id"] = 8867002240
            second["hero"] = {"id": 69, "name": "Doom", "slug": "doom_bringer"}
            second["is_win"] = True
            second["ended_at"] = "2026-06-27T01:00:00Z"
            second_report = self._write_report(source, second, filename="Doom_8867002240_20260627_090000.html")
            second_text = second_report.read_text(encoding="utf-8")
            second_report.write_text(
                second_text.replace(
                    "</body>",
                    quality_snippet +
                    '<div class="death-review-workbench"></div>'
                    '<div>死亡后恢复窗口</div>'
                    "</body>",
                ),
                encoding="utf-8",
            )
            source_fetch_times = {
                "8867002237": {
                    "stratz_fetched_at": "2026-06-26T22:20:00Z",
                    "opendota_fetched_at": "2026-06-26T22:10:00Z",
                    "latest_external_fetch_at": "2026-06-26T22:20:00Z",
                },
                "8867002240": {
                    "stratz_fetched_at": "2026-06-27T08:55:00Z",
                    "opendota_fetched_at": "2026-06-27T08:40:00Z",
                    "latest_external_fetch_at": "2026-06-27T08:55:00Z",
                },
            }
            evidence_payloads = {
                "8867002237": {
                    "stratz": {
                        "players": [
                            {
                                "steamAccount": {"id": 173776719},
                                "hero": {"id": 9},
                                "stats": {"lastHitsPerMinute": [4, 6], "goldPerMinute": [320, 410]},
                                "playbackData": {
                                    "deathEvents": [{"time": 840}],
                                    "purchaseEvents": [{"time": 620, "itemId": 50}],
                                    "playerUpdatePositionEvents": [{"time": 830, "x": 91, "y": 112}],
                                    "killEvents": [{"time": 900}],
                                },
                            }
                        ]
                    },
                    "opendota": {
                        "objectives": [{"time": 950, "type": "CHAT_MESSAGE_TOWER_KILL"}],
                        "teamfights": [{"start": 840, "deaths": [{"player_slot": 0}]}],
                        "players": [
                            {
                                "account_id": 173776719,
                                "hero_id": 9,
                                "lh_t": [0, 7, 15],
                                "gold_t": [600, 1200],
                                "purchase_log": [{"time": 620, "key": "phase_boots"}],
                                "kills_log": [{"time": 900, "key": "axe"}],
                                "obs_log": [{"time": 500, "x": 100, "y": 120}],
                                "benchmarks": {"gold_per_min": {"pct": 0.55}},
                            }
                        ],
                    },
                },
                "8867002240": {
                    "stratz": {
                        "players": [
                            {
                                "steamAccount": {"id": 173776719},
                                "hero": {"id": 69},
                                "playbackData": {
                                    "deathEvents": [{"time": 740}],
                                    "purchaseEvents": [{"time": 520, "itemId": 1}],
                                },
                            }
                        ]
                    },
                    "opendota": {
                        "objectives": [{"time": 1020, "type": "CHAT_MESSAGE_ROSHAN_KILL"}],
                        "players": [
                            {
                                "account_id": 173776719,
                                "hero_id": 69,
                                "lh_t": [0, 5, 11],
                                "purchase_log": [{"time": 520, "key": "blink"}],
                            }
                        ],
                    },
                },
            }

            pages_site.build_pages_site(
                source,
                public_dir=public,
                source_fetch_times=source_fetch_times,
                evidence_payloads=evidence_payloads,
            )
            manifest = json.loads((Path(public) / "site-manifest.json").read_text(encoding="utf-8"))
            index_html = (Path(public) / "index.html").read_text(encoding="utf-8")
            plan_html = (Path(public) / "practice-plan.html").read_text(encoding="utf-8")
            mirana_html = (Path(public) / "Mirana_8867002237_20260626_224839.html").read_text(encoding="utf-8")
            doom_html = (Path(public) / "Doom_8867002240_20260627_090000.html").read_text(encoding="utf-8")

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["report_count"], 2)
        self.assertEqual(manifest["finding_count"], 2)
        self.assertEqual(manifest["topic_count"], 1)
        self.assertEqual(manifest["high_priority_report_count"], 2)
        self.assertEqual(manifest["death_review_workbench_report_count"], 2)
        self.assertEqual(manifest["death_recovery_window_report_count"], 2)
        self.assertEqual(manifest["death_coordinate_map_report_count"], 1)
        self.assertEqual(manifest["complete_death_review_report_count"], 1)
        self.assertEqual(manifest["quality_gate"]["status"], "pass")
        self.assertEqual(manifest["quality_gate"]["decision_snapshot_report_count"], 2)
        self.assertEqual(manifest["quality_gate"]["trend_context_report_count"], 2)
        self.assertEqual(manifest["quality_gate"]["evidence_source_report_count"], 2)
        self.assertEqual(manifest["quality_gate"]["manual_review_language_hit_count"], 0)
        self.assertEqual(manifest["quality_gate"]["complete_quality_report_count"], 2)
        self.assertEqual(manifest["latest_match"]["hero"], "Doom")
        self.assertEqual(manifest["latest_match"]["match_id"], "8867002240")
        self.assertEqual(manifest["latest_match"]["report_generated_at"], "2026-06-27T09:00:00")
        self.assertEqual(manifest["latest_match"]["source_fetches"]["stratz_fetched_at"], "2026-06-27T08:55:00Z")
        self.assertEqual(manifest["source_freshness"]["status"], "tracked")
        self.assertEqual(manifest["source_freshness"]["basis"], "report_filename_timestamp+sqlite_fetched_at")
        self.assertEqual(manifest["source_freshness"]["report_timestamp_count"], 2)
        self.assertEqual(manifest["source_freshness"]["stratz_fetch_timestamp_report_count"], 2)
        self.assertEqual(manifest["source_freshness"]["opendota_fetch_timestamp_report_count"], 2)
        self.assertEqual(manifest["source_freshness"]["complete_source_timestamp_report_count"], 2)
        self.assertEqual(manifest["source_freshness"]["latest_report_generated_at"], "2026-06-27T09:00:00")
        self.assertEqual(manifest["source_freshness"]["latest_external_fetch_at"], "2026-06-27T08:55:00Z")
        self.assertEqual(manifest["evidence_field_audit"]["status"], "partial")
        self.assertEqual(manifest["evidence_field_audit"]["basis"], "sqlite_cached_stratz_opendota_json")
        self.assertEqual(manifest["evidence_field_audit"]["report_count"], 2)
        self.assertEqual(manifest["evidence_field_audit"]["field_count"], 8)
        self.assertGreaterEqual(manifest["evidence_field_audit"]["complete_field_count"], 4)
        field_status = {
            item["key"]: item["status"]
            for item in manifest["evidence_field_audit"]["fields"]
        }
        self.assertEqual(field_status["death_events"], "complete")
        self.assertEqual(field_status["position_samples"], "partial")
        self.assertEqual(field_status["vision_events"], "partial")
        self.assertEqual(len(manifest["report_sources"]), 2)
        self.assertEqual(manifest["report_sources"][0]["match_id"], "8867002240")
        self.assertEqual(manifest["report_sources"][1]["stratz_fetched_at"], "2026-06-26T22:20:00Z")
        self.assertIn("复盘数据覆盖", index_html)
        self.assertIn("evidence-command-bar", index_html)
        self.assertIn("证据指挥台", index_html)
        self.assertIn("字段 4/8", index_html)
        self.assertIn('href="#evidence-field-audit"', index_html)
        self.assertIn('href="match-brief.html"', index_html)
        self.assertIn("死亡复盘覆盖", index_html)
        self.assertIn("复盘质量门禁", index_html)
        self.assertIn("数据新鲜度", index_html)
        self.assertIn("data-source-freshness-panel", index_html)
        self.assertIn("最新报告生成", index_html)
        self.assertIn("STRATZ 抓取", index_html)
        self.assertIn("OpenDota 抓取", index_html)
        self.assertIn("公开页展示的是已缓存证据", index_html)
        self.assertIn("实证字段覆盖", index_html)
        self.assertIn("data-evidence-field-audit-panel", index_html)
        self.assertIn("死亡事件时间线", index_html)
        self.assertIn("位置采样", index_html)
        self.assertIn("质量门禁：通过", index_html)
        self.assertIn("决策卡覆盖", index_html)
        self.assertIn("趋势上下文覆盖", index_html)
        self.assertIn("手工复盘旧词", index_html)
        self.assertIn("2 局", index_html)
        self.assertIn("恢复窗口", index_html)
        self.assertIn("1 局", index_html)
        self.assertIn("完整死亡复盘", index_html)
        self.assertIn("site-manifest.json", index_html)
        self.assertIn("Doom #8867002240", index_html)
        self.assertIn("2 场", index_html)
        self.assertIn("2 条 finding", index_html)
        self.assertIn("1 个训练主题", index_html)
        self.assertIn("data-coverage-panel", index_html)
        self.assertIn("data-quality-gate-panel", index_html)
        self.assertIn("复盘数据覆盖", plan_html)
        self.assertIn("evidence-command-bar", plan_html)
        self.assertIn("证据指挥台", plan_html)
        self.assertIn("字段 4/8", plan_html)
        self.assertIn('href="#evidence-field-audit"', plan_html)
        self.assertIn("复盘质量门禁", plan_html)
        self.assertIn("数据新鲜度", plan_html)
        self.assertIn("实证字段覆盖", plan_html)
        self.assertIn('data-report-source-provenance', mirana_html)
        self.assertIn('data-report-context-deck', mirana_html)
        self.assertIn('<details class="report-source-provenance"', mirana_html)
        self.assertIn('<summary class="source-provenance-summary">', mirana_html)
        self.assertIn('data-match-id="8867002237"', mirana_html)
        self.assertIn("证据时间", mirana_html)
        self.assertIn("报告生成", mirana_html)
        self.assertIn("2026-06-26T22:48:39", mirana_html)
        self.assertIn("STRATZ 抓取", mirana_html)
        self.assertIn("2026-06-26T22:20:00Z", mirana_html)
        self.assertIn("OpenDota 抓取", mirana_html)
        self.assertIn("2026-06-26T22:10:00Z", mirana_html)
        self.assertIn("已缓存证据", mirana_html)
        self.assertNotIn("2026-06-27T08:55:00Z", mirana_html)
        self.assertIn('data-match-id="8867002240"', doom_html)
        self.assertIn("2026-06-27T08:55:00Z", doom_html)
        self.assertNotIn("2026-06-26T22:20:00Z", doom_html)

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
            plan_text = (Path(public) / "practice-plan.txt").read_text(encoding="utf-8")
            brief_html = (Path(public) / "match-brief.html").read_text(encoding="utf-8")
            brief_text = (Path(public) / "match-brief.txt").read_text(encoding="utf-8")

        self.assertIn("practice-plan.html", index_html)
        self.assertIn("match-brief.html", index_html)
        self.assertIn("match-brief.html", plan_html)
        self.assertIn("practice-plan.txt", plan_html)
        self.assertIn("导出训练清单", plan_html)
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
        self.assertIn("Dota 2 下一局训练清单", plan_text)
        self.assertIn("玩家 173776719", plan_text)
        self.assertIn("第 1 优先级：前10分钟资源", plan_text)
        self.assertIn("下一局前10分钟低效率窗口=0。", plan_text)
        self.assertIn("10分钟补刀>=35。", plan_text)
        self.assertIn("失败证据：trend-early-resource.html?result=lose", plan_text)
        self.assertIn("赛前执行卡", brief_html)
        self.assertIn("三条核心承诺", brief_html)
        self.assertIn("match-brief.txt", brief_html)
        self.assertIn("导出执行卡", brief_html)
        self.assertIn("对局中只盯", brief_html)
        self.assertIn("赛后复核", brief_html)
        self.assertIn("失败证据", brief_html)
        self.assertIn("胜利样本", brief_html)
        self.assertIn("Doom #8867002240", brief_html)
        self.assertIn('href="practice-plan.html"', brief_html)
        self.assertIn('href="trend-early-resource.html?result=lose"', brief_html)
        self.assertIn('href="trend-early-resource.html?result=win"', brief_html)
        self.assertIn('class="brief-freshness"', brief_html)
        self.assertIn("证据覆盖", brief_html)
        self.assertIn('data-brief-report-count', brief_html)
        self.assertIn("2 场复盘", brief_html)
        self.assertIn("2 条教练证据", brief_html)
        self.assertIn("1 个训练主题", brief_html)
        self.assertIn('class="brief-card"', brief_html)
        self.assertIn('class="brief-proof-grid"', brief_html)
        self.assertIn('aria-label="赛前承诺导航"', brief_html)
        self.assertIn('class="brief-command-bar"', brief_html)
        self.assertIn('class="brief-command-link"', brief_html)
        self.assertIn("赛前只盯", brief_html)
        self.assertIn('href="#brief-commitment-1"', brief_html)
        self.assertIn('id="brief-commitment-1"', brief_html)
        self.assertIn("Dota 2 赛前执行卡", brief_text)
        self.assertIn("玩家 173776719", brief_text)
        self.assertIn("最新复盘：Doom #8867002240", brief_text)
        self.assertIn("承诺 1：前10分钟资源", brief_text)
        self.assertIn("对局中只盯：下一局前10分钟低效率窗口=0。", brief_text)
        self.assertIn("赛后复核：10分钟补刀>=35。", brief_text)
        self.assertIn("失败证据：trend-early-resource.html?result=lose", brief_text)
        self.assertIn("胜利样本：trend-early-resource.html?result=win", brief_text)

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
        self.assertIn(".evidence-command-bar", stylesheet)
        self.assertIn(".evidence-command-track", stylesheet)
        self.assertIn(".evidence-command-link", stylesheet)
        self.assertIn(".evidence-command-chip", stylesheet)
        self.assertIn(".coverage-subtitle", stylesheet)
        self.assertIn(".quality-gate-panel", stylesheet)
        self.assertIn(".quality-gate-status", stylesheet)
        self.assertIn(".quality-gate-pass", stylesheet)
        self.assertIn(".source-freshness-panel", stylesheet)
        self.assertIn(".source-freshness-status", stylesheet)
        self.assertIn(".evidence-field-audit-panel", stylesheet)
        self.assertIn(".field-audit-list", stylesheet)
        self.assertIn(".field-audit-row", stylesheet)
        self.assertIn(".report-source-provenance", stylesheet)
        self.assertIn(".source-provenance-grid", stylesheet)
        self.assertIn(".report-context-deck", stylesheet)
        self.assertIn(".source-provenance-summary", stylesheet)
        self.assertIn(".report-source-provenance[open]", stylesheet)
        self.assertIn(".report-evidence-completeness", stylesheet)
        self.assertIn(".evidence-completeness-summary", stylesheet)
        self.assertIn(".evidence-completeness-chips", stylesheet)
        self.assertIn(".evidence-completeness-chip", stylesheet)
        self.assertIn(".evidence-completeness-details", stylesheet)
        self.assertIn(".evidence-completeness-guidance", stylesheet)
        self.assertIn(".practice-workbench", stylesheet)
        self.assertIn(".practice-evidence-links", stylesheet)
        self.assertIn(".practice-checklist", stylesheet)
        self.assertIn(".practice-card[hidden]", stylesheet)
        self.assertIn(".brief-command-bar", stylesheet)
        self.assertIn(".brief-command-link", stylesheet)
        self.assertIn(".brief-freshness", stylesheet)
        self.assertIn(".report-section-nav", stylesheet)
        self.assertIn(".skip-link", stylesheet)
        self.assertIn(".report-top-link", stylesheet)
        self.assertIn(".decision-snapshot", stylesheet)
        self.assertIn(".decision-snapshot-grid", stylesheet)
        self.assertIn(".decision-tab", stylesheet)
        self.assertIn(".decision-panel", stylesheet)
        self.assertIn("[data-decision-panel][hidden]", stylesheet)
        self.assertIn(".decision-jump-row", stylesheet)
        self.assertIn(".report-trend-context", stylesheet)
        self.assertIn(".trend-context-examples", stylesheet)
        self.assertRegex(stylesheet, r"\.report-top-link\s*\{[^}]*position:\s*sticky")
        self.assertIn("#timeline-diagnosis table", stylesheet)
        self.assertRegex(
            stylesheet,
            r"@media \(max-width: 720px\)[\s\S]*\.decision-snapshot-grid\s*\{[^}]*grid-template-columns:\s*1fr",
        )
        self.assertRegex(
            stylesheet,
            r"@media \(max-width: 720px\)[\s\S]*\.report-context-deck\s*\{[^}]*grid-template-columns:\s*1fr",
        )

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

    def test_build_pages_site_upgrades_legacy_item_slots_to_names(self):
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
            text = report_path.read_text(encoding="utf-8")
            legacy_items = (
                '<div class="item-slot item-name" title="Item #1856">1856</div>'
                '<div class="item-slot item-name" title="Item #214">214</div>'
                '<div class="item-slot item-name" title="Item #254">254</div>'
            )
            report_path.write_text(text.replace("</body>", legacy_items + "</body>"), encoding="utf-8")

            pages_site.build_pages_site(source, public_dir=public)
            report_html = (Path(public) / report_path.name).read_text(encoding="utf-8")

        self.assertNotIn("Item #1856", report_html)
        self.assertNotIn("Item #214", report_html)
        self.assertNotIn("Item #254", report_html)
        self.assertIn("Crella&#x27;s Crozier", report_html)
        self.assertIn("Tranquil Boots", report_html)
        self.assertIn("Glimmer Cape", report_html)

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
        self.assertIn('class="report-context-deck"', latest_html)
        self.assertIn("下一局（更早）", latest_html)
        self.assertIn("Anti-Mage", latest_html)
        self.assertIn("Anti-Mage_8866000193_20260625_160037.html", latest_html)
        self.assertIn("终结比赛", latest_html)

    def test_build_pages_site_injects_report_evidence_completeness_summary(self):
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
            text = report_path.read_text(encoding="utf-8")
            evidence_sources = (
                '<section class="section" id="data-quality">'
                '<div class="evidence-source-list">'
                '<div class="evidence-source-row available">'
                '<div class="evidence-source-name">比赛核心数据</div>'
                '<div class="evidence-source-detail"><span class="evidence-source-origin">OpenDota比赛核心数据</span>'
                '<span class="evidence-source-coverage">KDA、GPM、XPM</span></div>'
                '</div>'
                '<div class="evidence-source-row partial">'
                '<div class="evidence-source-name">死亡时间</div>'
                '<div class="evidence-source-detail"><span class="evidence-source-origin">STRATZ回放事件</span>'
                '<span class="evidence-source-coverage">已定位 5/7 次死亡</span></div>'
                '</div>'
                '<div class="evidence-source-row missing">'
                '<div class="evidence-source-name">视野事件</div>'
                '<div class="evidence-source-detail"><span class="evidence-source-origin">OpenDota视野事件</span>'
                '<span class="evidence-source-coverage">公共数据未提供</span></div>'
                '</div>'
                '</div></section>'
            )
            report_path.write_text(text.replace("</body>", evidence_sources + "</body>"), encoding="utf-8")

            pages_site.build_pages_site(source, public_dir=public)
            report_html = (Path(public) / report_path.name).read_text(encoding="utf-8")

        self.assertIn('data-report-evidence-completeness', report_html)
        self.assertIn('data-evidence-total="3"', report_html)
        self.assertIn('data-evidence-complete="1"', report_html)
        self.assertIn('data-evidence-usable="2"', report_html)
        self.assertIn('data-evidence-partial="1"', report_html)
        self.assertIn('data-evidence-missing="1"', report_html)
        self.assertIn("本局证据完整度", report_html)
        self.assertIn('class="evidence-completeness-guidance"', report_html)
        self.assertIn("执行信号", report_html)
        self.assertIn("缺失证据项不作为本局归因", report_html)
        self.assertIn("1/3 类完整", report_html)
        self.assertIn("可用/部分 2/3 · 缺失 1", report_html)
        self.assertIn("比赛核心数据", report_html)
        self.assertIn("死亡时间", report_html)
        self.assertIn("视野事件", report_html)
        self.assertLess(report_html.index('class="report-source-provenance"'), report_html.index('data-report-evidence-completeness'))

    def test_build_pages_site_injects_report_trend_context_after_decision_snapshot(self):
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
            first = self._write_report(source, metadata, filename="Mirana_8867002237_20260626_224839.html")
            older = dict(metadata)
            older["match_id"] = 8866000193
            older["hero"] = {"id": 1, "name": "Anti-Mage", "slug": "antimage"}
            older["ended_at"] = "2026-06-25T16:00:37Z"
            second = self._write_report(source, older, filename="Anti-Mage_8866000193_20260625_160037.html")
            for path in (first, second):
                text = path.read_text(encoding="utf-8")
                path.write_text(
                    text.replace(
                        '<div class="finding-card high">',
                        '<section class="section priority-section decision-snapshot" id="decision-snapshot">'
                        '<div>上分决策卡</div></section>'
                        '<div class="finding-card high">',
                    ),
                    encoding="utf-8",
                )

            pages_site.build_pages_site(source, public_dir=public)
            report_html = (Path(public) / first.name).read_text(encoding="utf-8")

        self.assertIn("近期同类问题", report_html)
        self.assertIn("最近 2 场中 2 场出现", report_html)
        self.assertIn("2 条证据", report_html)
        self.assertIn('href="trend-early-resource.html"', report_html)
        self.assertIn("完整趋势证据", report_html)
        self.assertLess(report_html.index('id="decision-snapshot"'), report_html.index('class="report-trend-context"'))
        self.assertIn("Anti-Mage #8866000193", report_html)

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
