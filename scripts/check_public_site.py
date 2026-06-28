import json
from html.parser import HTMLParser
from pathlib import Path

from build_pages_site import _parse_report


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "public"
REQUIRED_REPORT_TEXT = [
    "下一局行动清单",
    "时间线诊断",
    "10分钟补刀",
    "低效率窗口",
    "数据缺口",
]


class TitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title_parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self):
        return "".join(self.title_parts).strip()


def _title_for(path):
    parser = TitleParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.title


def main():
    index_path = PUBLIC_DIR / "index.html"
    practice_path = PUBLIC_DIR / "practice-plan.html"
    trends_path = PUBLIC_DIR / "review-trends.json"
    style_path = PUBLIC_DIR / "static" / "style.css"
    if not index_path.exists():
        raise SystemExit("public/index.html is missing")
    if not practice_path.exists():
        raise SystemExit("public/practice-plan.html is missing")
    if not trends_path.exists():
        raise SystemExit("public/review-trends.json is missing")
    if not style_path.exists():
        raise SystemExit("public/static/style.css is missing")

    reports = sorted(path for path in PUBLIC_DIR.glob("*.html") if path.name not in {"index.html", "practice-plan.html"})
    if not reports:
        raise SystemExit("public contains no report HTML files")

    index_html = index_path.read_text(encoding="utf-8")
    if "Dota 2 天梯复盘报告" not in index_html:
        if "Dota 2 天梯复盘历史" not in index_html:
            raise SystemExit("index page has the wrong title")
    for required in (
        "比赛历史",
        "筛选比赛",
        "match-search",
        "data-filter-result",
        "data-filter-priority",
        "data-empty-state",
        "没有匹配的比赛",
        "practice-plan.html",
        "优先复盘",
        "最近反复问题",
        "我方阵容",
        "敌方阵容",
        "data-ended-at",
    ):
        if required not in index_html:
            raise SystemExit(f"index page is missing required match-history content: {required}")

    try:
        trend_payload = json.loads(trends_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"public/review-trends.json is invalid JSON: {exc}") from exc
    trends = trend_payload.get("trends") if isinstance(trend_payload, dict) else None
    if (
        trend_payload.get("schema_version") != 2
        or trend_payload.get("taxonomy_version") != 1
        or not isinstance(trends, list)
        or not trends
    ):
        raise SystemExit(
            "public/review-trends.json must include schema_version=2, taxonomy_version=1, and non-empty trends"
        )
    for trend in trends:
        for key in (
            "topic_id",
            "focus",
            "count",
            "finding_count",
            "priority",
            "heroes",
            "source_focuses",
            "next_action",
            "success_metric",
            "examples",
        ):
            if key not in trend:
                raise SystemExit(f"review trend is missing required field: {key}")
        if trend["count"] < 1 or trend["finding_count"] < trend["count"] or not trend["source_focuses"]:
            raise SystemExit(f"review trend has inconsistent aggregation counts: {trend.get('topic_id')}")

    practice_html = practice_path.read_text(encoding="utf-8")
    for required in ("下一次训练计划", "第 1 优先级", "下一局动作", "验收标准"):
        if required not in practice_html:
            raise SystemExit(f"practice plan page is missing required content: {required}")

    for report in reports:
        text = report.read_text(encoding="utf-8")
        missing = [item for item in REQUIRED_REPORT_TEXT if item not in text]
        if missing:
            raise SystemExit(f"{report.name} is missing required report sections: {', '.join(missing)}")
        if "相邻比赛" not in text or "report-neighbors" not in text:
            raise SystemExit(f"{report.name} is missing adjacent report navigation")
        title = _title_for(report)
        if not title or title.startswith("复盘报告"):
            raise SystemExit(f"{report.name} title must start with the hero name")
        metadata = _parse_report(report)
        required_metadata = ("match_id", "hero", "ended_at", "duration_seconds", "kda", "score")
        missing_metadata = [key for key in required_metadata if metadata.get(key) in (None, "", {})]
        if missing_metadata:
            raise SystemExit(f"{report.name} is missing match metadata: {', '.join(missing_metadata)}")
        if len(metadata.get("allies") or []) != 5 or len(metadata.get("enemies") or []) != 5:
            raise SystemExit(f"{report.name} must include both five-hero lineups")
        if not title.startswith(metadata["hero"]):
            raise SystemExit(f"{report.name} title and metadata hero do not match")

    print(f"Validated {len(reports)} report pages in {PUBLIC_DIR}")


if __name__ == "__main__":
    main()
