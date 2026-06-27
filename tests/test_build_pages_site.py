import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_pages_site as pages_site


class BuildPagesSiteTests(unittest.TestCase):
    def _write_report(self, directory, metadata, filename="Mirana_8867002237_20260626_224839.html", focus="前10分钟资源"):
        path = Path(directory) / filename
        payload = json.dumps(metadata, ensure_ascii=False).replace("</", "<\\/")
        path.write_text(
            "<!doctype html><html><head><title>Mirana 复盘报告</title></head>"
            "<body>"
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
        self.assertIn("data-result=\"lose\"", text)
        self.assertIn("data-priority=\"high\"", text)
        self.assertIn("data-match-count", text)
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
            self._write_report(source, second, filename="Doom_8867002240_20260626_224840.html")

            pages_site.build_pages_site(source, public_dir=public)
            trend_path = Path(public) / "review-trends.json"

            self.assertTrue(trend_path.exists())
            payload = json.loads(trend_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["trends"][0]["focus"], "前10分钟资源")
        self.assertEqual(payload["trends"][0]["count"], 2)


if __name__ == "__main__":
    unittest.main()
