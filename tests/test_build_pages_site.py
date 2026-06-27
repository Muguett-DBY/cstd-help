import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_pages_site import _parse_report, _render_index


class BuildPagesSiteTests(unittest.TestCase):
    def _write_report(self, directory, metadata):
        path = Path(directory) / "Mirana_8867002237_20260626_224839.html"
        payload = json.dumps(metadata, ensure_ascii=False).replace("</", "<\\/")
        path.write_text(
            "<!doctype html><html><head><title>Mirana 复盘报告</title></head>"
            "<body>"
            '<div class="finding-card high">'
            '<div class="finding-title">前10分钟资源</div>'
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

            parsed = _parse_report(report)

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

            parsed = _parse_report(path)

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

            _render_index(reports, output_path=output)
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
        self.assertIn("Mirana_8867002237_20260626_224839.html", text)
        self.assertNotIn("报告生成时间", text)


if __name__ == "__main__":
    unittest.main()
