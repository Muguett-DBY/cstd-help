import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from build_pages_site import _parse_report
except ModuleNotFoundError:
    from scripts.build_pages_site import _parse_report


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "public"
REQUIRED_REPORT_TEXT = [
    "下一局行动清单",
    "时间线诊断",
    "10分钟补刀",
    "低效率窗口",
    "数据缺口",
]
REQUIRED_REPORT_EVIDENCE_SOURCE_TEXT = [
    "证据来源与覆盖",
    "evidence-source-list",
    "evidence-source-row",
    "比赛核心数据",
    "分钟时间线",
    "购买时间",
    "死亡时间",
    "死亡位置",
]
SUPPORT_HTML_PAGES = frozenset({
    "index.html",
    "practice-plan.html",
    "match-brief.html",
})
SUPPORT_TEXT_EXPORTS = frozenset({
    "practice-plan.txt",
    "match-brief.txt",
})
REQUIRED_SUPPORT_FILES = frozenset({
    *SUPPORT_HTML_PAGES,
    *SUPPORT_TEXT_EXPORTS,
    "review-trends.json",
    "site-manifest.json",
    "static/style.css",
})


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


class LocalLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.append(element_id)
        if tag.lower() not in {"a", "link", "script", "img"}:
            return
        for name in ("href", "src"):
            value = attributes.get(name)
            if value:
                self.links.append(value)


def _title_for(path):
    parser = TitleParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.title


def _is_local_asset_reference(value):
    normalized = value.strip()
    if not normalized or normalized.startswith("#"):
        return False
    if normalized.startswith(("http://", "https://", "mailto:", "tel:", "data:")):
        return False
    return True


def _strip_link_suffix(value):
    return value.split("#", 1)[0].split("?", 1)[0]


def _parse_page(public_dir, page):
    parser = LocalLinkParser()
    parser.feed(page.read_text(encoding="utf-8"))
    return parser


def _is_topic_page(path):
    return Path(path).suffix == ".html" and Path(path).name.startswith("trend-")


def _is_report_page(path):
    path = Path(path)
    return path.suffix == ".html" and path.name not in SUPPORT_HTML_PAGES and not _is_topic_page(path)


def _report_pages(public_dir=PUBLIC_DIR):
    public_dir = Path(public_dir)
    return sorted(path for path in public_dir.glob("*.html") if _is_report_page(path))


def _find_local_link_issues(public_dir=PUBLIC_DIR):
    public_dir = Path(public_dir)
    issues = []
    for page in sorted(public_dir.glob("*.html")):
        parser = _parse_page(public_dir, page)
        for raw_link in parser.links:
            if not _is_local_asset_reference(raw_link):
                continue
            target = _strip_link_suffix(raw_link)
            if not target:
                continue
            target_path = (page.parent / target).resolve()
            try:
                target_path.relative_to(public_dir.resolve())
            except ValueError:
                issues.append(f"{page.name} -> {raw_link}")
                continue
            if not target_path.exists():
                issues.append(f"{page.name} -> {raw_link}")
    return issues


def _find_duplicate_id_issues(public_dir=PUBLIC_DIR):
    public_dir = Path(public_dir)
    issues = []
    for page in sorted(public_dir.glob("*.html")):
        parser = _parse_page(public_dir, page)
        seen = set()
        duplicates = []
        for element_id in parser.ids:
            if element_id in seen and element_id not in duplicates:
                duplicates.append(element_id)
            seen.add(element_id)
        for element_id in sorted(duplicates):
            issues.append(f"{page.name} -> duplicate id '{element_id}'")
    return issues


def _find_anchor_issues(public_dir=PUBLIC_DIR):
    public_dir = Path(public_dir)
    public_root = public_dir.resolve()
    id_cache = {}
    issues = []

    def ids_for(target_path):
        resolved = target_path.resolve()
        if resolved not in id_cache:
            parser = _parse_page(public_dir, target_path)
            id_cache[resolved] = set(parser.ids)
        return id_cache[resolved]

    for page in sorted(public_dir.glob("*.html")):
        parser = _parse_page(public_dir, page)
        for raw_link in parser.links:
            normalized = raw_link.strip()
            if not normalized or normalized.startswith(("http://", "https://", "mailto:", "tel:", "data:")):
                continue
            parsed = urlsplit(normalized)
            fragment = unquote(parsed.fragment)
            if not fragment:
                continue
            target_name = _strip_link_suffix(normalized)
            target_path = page if not target_name else (page.parent / target_name)
            resolved = target_path.resolve()
            try:
                resolved.relative_to(public_root)
            except ValueError:
                continue
            if not resolved.exists():
                continue
            if fragment not in ids_for(resolved):
                issues.append(f"{page.name} -> {raw_link}")
    return issues


def _find_unresolved_item_references(public_dir=PUBLIC_DIR):
    public_dir = Path(public_dir)
    issues = []
    for page in sorted(public_dir.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        for reference in sorted(set(re.findall(r"\bItem #\d+\b", text))):
            issues.append(f"{page.name} -> {reference}")
    return issues


def _find_report_evidence_source_issues(public_dir=PUBLIC_DIR):
    issues = []
    for report in _report_pages(public_dir):
        text = report.read_text(encoding="utf-8")
        missing = [item for item in REQUIRED_REPORT_EVIDENCE_SOURCE_TEXT if item not in text]
        if missing:
            issues.append(f"{report.name} -> missing evidence source coverage: {', '.join(missing)}")
    return issues


def main():
    required_paths = {name: PUBLIC_DIR / name for name in REQUIRED_SUPPORT_FILES}
    for name, path in sorted(required_paths.items()):
        if not path.exists():
            raise SystemExit(f"public/{name} is missing")

    index_path = required_paths["index.html"]
    practice_path = required_paths["practice-plan.html"]
    brief_path = required_paths["match-brief.html"]
    practice_text_path = required_paths["practice-plan.txt"]
    brief_text_path = required_paths["match-brief.txt"]
    trends_path = required_paths["review-trends.json"]
    manifest_path = required_paths["site-manifest.json"]

    topic_pages = sorted(PUBLIC_DIR.glob("trend-*.html"))
    reports = _report_pages(PUBLIC_DIR)
    if not reports:
        raise SystemExit("public contains no report HTML files")

    local_link_issues = _find_local_link_issues(PUBLIC_DIR)
    if local_link_issues:
        preview = "; ".join(local_link_issues[:10])
        raise SystemExit(f"public contains broken local links: {preview}")

    duplicate_ids = _find_duplicate_id_issues(PUBLIC_DIR)
    if duplicate_ids:
        preview = "; ".join(duplicate_ids[:10])
        raise SystemExit(f"public contains duplicate element ids: {preview}")

    anchor_issues = _find_anchor_issues(PUBLIC_DIR)
    if anchor_issues:
        preview = "; ".join(anchor_issues[:10])
        raise SystemExit(f"public contains broken anchor links: {preview}")

    unresolved_items = _find_unresolved_item_references(PUBLIC_DIR)
    if unresolved_items:
        preview = "; ".join(unresolved_items[:10])
        raise SystemExit(f"public contains unresolved item names: {preview}")

    evidence_source_issues = _find_report_evidence_source_issues(PUBLIC_DIR)
    if evidence_source_issues:
        preview = "; ".join(evidence_source_issues[:10])
        raise SystemExit(f"public reports are missing evidence source coverage: {preview}")

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
        "data-clear-filters",
        "URLSearchParams",
        "data-empty-state",
        "没有匹配的比赛",
        "practice-plan.html",
        "match-brief.html",
        "优先复盘",
        "最近反复问题",
        "我方阵容",
        "敌方阵容",
        "data-ended-at",
        "复盘数据覆盖",
        "data-coverage-panel",
        "site-manifest.json",
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
            "page",
            "findings",
        ):
            if key not in trend:
                raise SystemExit(f"review trend is missing required field: {key}")
        if trend["count"] < 1 or trend["finding_count"] < trend["count"] or not trend["source_focuses"]:
            raise SystemExit(f"review trend has inconsistent aggregation counts: {trend.get('topic_id')}")
        if len(trend["findings"]) != trend["finding_count"]:
            raise SystemExit(f"review trend finding payload is incomplete: {trend.get('topic_id')}")
        for finding in trend["findings"]:
            for key in ("hero", "match_id", "file", "source_focus", "review_evidence", "next_action", "success_metric"):
                if key not in finding:
                    raise SystemExit(f"review trend finding is missing required field: {key}")

    try:
        site_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"public/site-manifest.json is invalid JSON: {exc}") from exc
    for key in (
        "schema_version",
        "player_id",
        "report_count",
        "finding_count",
        "topic_count",
        "high_priority_report_count",
        "latest_match",
        "topics",
    ):
        if key not in site_manifest:
            raise SystemExit(f"site manifest is missing required field: {key}")
    if site_manifest["schema_version"] != 1:
        raise SystemExit("site manifest must use schema_version=1")

    expected_topic_pages = {trend["page"] for trend in trends}
    actual_topic_pages = {path.name for path in topic_pages}
    if actual_topic_pages != expected_topic_pages:
        raise SystemExit(
            f"topic evidence pages do not match trend payload: expected {len(expected_topic_pages)}, got {len(actual_topic_pages)}"
        )

    practice_html = practice_path.read_text(encoding="utf-8")
    for required in (
        "下一次训练计划",
        "第 1 优先级",
        "下一局动作",
        "验收标准",
        "复盘数据覆盖",
        "practice-workbench",
        "data-practice-filter",
        "data-practice-check",
        "data-practice-empty",
        "result=lose",
        "result=win",
    ):
        if required not in practice_html:
            raise SystemExit(f"practice plan page is missing required content: {required}")
    practice_text = practice_text_path.read_text(encoding="utf-8")
    for required in ("Dota 2 下一局训练清单", "玩家 173776719", "失败证据：", "胜利样本：", "检查点："):
        if required not in practice_text:
            raise SystemExit(f"practice plan text export is missing required content: {required}")
    brief_html = brief_path.read_text(encoding="utf-8")
    for required in (
        "赛前执行卡",
        "三条核心承诺",
        "对局中只盯",
        "赛后复核",
        "失败证据",
        "胜利样本",
        "result=win",
        "practice-plan.html",
        "match-brief.txt",
        "导出执行卡",
        "证据覆盖",
        "data-brief-report-count",
        "brief-card",
        "brief-command-bar",
        "brief-proof-grid",
    ):
        if required not in brief_html:
            raise SystemExit(f"match brief page is missing required content: {required}")
    brief_text = brief_text_path.read_text(encoding="utf-8")
    for required in ("Dota 2 赛前执行卡", "玩家 173776719", "承诺 1：", "对局中只盯：", "失败证据：", "胜利样本："):
        if required not in brief_text:
            raise SystemExit(f"match brief text export is missing required content: {required}")

    if site_manifest["report_count"] != len(reports):
        raise SystemExit("site manifest report_count does not match generated reports")
    if site_manifest["topic_count"] != len(trends):
        raise SystemExit("site manifest topic_count does not match review trends")
    if len(site_manifest["topics"]) != len(trends):
        raise SystemExit("site manifest topic list does not match review trends")

    for trend in trends:
        page_name = trend["page"]
        if f'href="{page_name}"' not in index_html or f'href="{page_name}"' not in practice_html:
            raise SystemExit(f"topic evidence page is not linked from dashboard and practice plan: {page_name}")
        topic_html = (PUBLIC_DIR / page_name).read_text(encoding="utf-8")
        for required in (
            "完整证据",
            "主题证据工作台",
            "topic-switcher",
            "data-topic-filter",
            "data-topic-card-count",
            "data-topic-empty",
            "归并标签",
            "训练动作",
            "验收标准",
            "打开本局完整复盘",
        ):
            if required not in topic_html:
                raise SystemExit(f"{page_name} is missing required topic content: {required}")

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
