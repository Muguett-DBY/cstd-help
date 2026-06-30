import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from build_pages_site import _parse_report, _read_evidence_sources_from_text
except ModuleNotFoundError:
    from scripts.build_pages_site import _parse_report, _read_evidence_sources_from_text


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
REQUIRED_DEATH_REVIEW_REPORT_TEXT = [
    "death-review-workbench",
    "death-review-summary",
    "死亡后恢复窗口",
    "timeline-phase-cards",
]
REQUIRED_DEATH_REVIEW_MANIFEST_FIELDS = [
    "death_review_workbench_report_count",
    "death_recovery_window_report_count",
    "death_coordinate_map_report_count",
    "complete_death_review_report_count",
]
REQUIRED_QUALITY_GATE_FIELDS = [
    "status",
    "decision_snapshot_report_count",
    "trend_context_report_count",
    "evidence_source_report_count",
    "manual_review_language_hit_count",
    "complete_quality_report_count",
]
REQUIRED_SOURCE_FRESHNESS_FIELDS = [
    "status",
    "basis",
    "report_timestamp_count",
    "stratz_fetch_timestamp_report_count",
    "opendota_fetch_timestamp_report_count",
    "complete_source_timestamp_report_count",
    "latest_report_generated_at",
    "latest_external_fetch_at",
    "limitation",
]
REQUIRED_REPORT_SOURCE_PROVENANCE_TEXT = [
    "证据时间",
    "report-context-deck",
    "data-report-context-deck",
    "report-source-provenance",
    "data-report-source-provenance",
    "source-provenance-summary",
    "data-report-generated-at",
    "data-stratz-fetched-at",
    "data-opendota-fetched-at",
    "报告生成",
    "STRATZ 抓取",
    "OpenDota 抓取",
    "已缓存证据",
]
REQUIRED_REPORT_EVIDENCE_COMPLETENESS_TEXT = [
    "本局证据完整度",
    "data-report-evidence-completeness",
    "data-evidence-total",
    "data-evidence-complete",
    "data-evidence-usable",
    "data-evidence-partial",
    "data-evidence-missing",
    "evidence-completeness-summary",
    "evidence-completeness-chip",
]
FORBIDDEN_REPORT_TEXT = [
    "接失去",
    "接获取",
    "릿턍",
    "괩멩",
]
FORBIDDEN_MANUAL_REVIEW_LANGUAGE = [
    "需要回放确认",
    "优先回看",
    "可回放复查",
    "回放确认后的",
    "回放场景",
    "逐一回放",
    "回放时只核对",
    "回放检查点",
    "人工回看",
    "人工查看",
    "手动复盘",
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


def _find_death_review_coverage_issues(public_dir=PUBLIC_DIR):
    public_dir = Path(public_dir)
    issues = []
    for report in _report_pages(public_dir):
        text = report.read_text(encoding="utf-8")
        missing = [item for item in REQUIRED_DEATH_REVIEW_REPORT_TEXT if item not in text]
        if missing:
            issues.append(f"{report.name} -> missing death review coverage: {', '.join(missing)}")

    index_path = public_dir / "index.html"
    if index_path.exists() and "死亡复盘覆盖" not in index_path.read_text(encoding="utf-8"):
        issues.append("index.html -> missing death review coverage panel")

    manifest_path = public_dir / "site-manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
        missing_fields = [
            field for field in REQUIRED_DEATH_REVIEW_MANIFEST_FIELDS
            if field not in manifest
        ]
        if missing_fields:
            issues.append(
                "site-manifest.json -> missing death review coverage fields: "
                + ", ".join(missing_fields)
            )
        else:
            expected = {
                "death_review_workbench_report_count": 0,
                "death_recovery_window_report_count": 0,
                "death_coordinate_map_report_count": 0,
                "complete_death_review_report_count": 0,
            }
            for report in _report_pages(public_dir):
                evidence = (_parse_report(report).get("death_evidence") or {})
                if evidence.get("has_death_review_workbench"):
                    expected["death_review_workbench_report_count"] += 1
                if evidence.get("has_death_recovery_windows"):
                    expected["death_recovery_window_report_count"] += 1
                if evidence.get("has_death_coordinate_map"):
                    expected["death_coordinate_map_report_count"] += 1
                if evidence.get("has_complete_death_review"):
                    expected["complete_death_review_report_count"] += 1
            mismatches = [
                f"{field} expected {expected[field]} got {manifest.get(field)}"
                for field in REQUIRED_DEATH_REVIEW_MANIFEST_FIELDS
                if manifest.get(field) != expected[field]
            ]
            if mismatches:
                issues.append(
                    "site-manifest.json -> inconsistent death review coverage fields: "
                    + ", ".join(mismatches)
                )
    return issues


def _report_quality_evidence(report):
    text = report.read_text(encoding="utf-8")
    manual_hits = [
        phrase for phrase in FORBIDDEN_MANUAL_REVIEW_LANGUAGE
        if phrase in text
    ]
    return {
        "has_decision_snapshot": 'id="decision-snapshot"' in text and "上分决策卡" in text,
        "has_trend_context": 'class="report-trend-context"' in text and "近期同类问题" in text,
        "has_evidence_source_coverage": "证据来源与覆盖" in text and "evidence-source-list" in text,
        "manual_review_language_hits": manual_hits,
    }


def _find_quality_gate_issues(public_dir=PUBLIC_DIR):
    public_dir = Path(public_dir)
    issues = []
    index_path = public_dir / "index.html"
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8")
        if "复盘质量门禁" not in index_text or "data-quality-gate-panel" not in index_text:
            issues.append("index.html -> missing quality gate panel")

    manifest_path = public_dir / "site-manifest.json"
    if not manifest_path.exists():
        return issues
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        manifest = {}
    quality_gate = manifest.get("quality_gate") if isinstance(manifest, dict) else None
    if not isinstance(quality_gate, dict):
        issues.append("site-manifest.json -> missing quality gate summary")
        return issues

    missing_fields = [
        field for field in REQUIRED_QUALITY_GATE_FIELDS
        if field not in quality_gate
    ]
    if missing_fields:
        issues.append("site-manifest.json -> missing quality gate fields: " + ", ".join(missing_fields))
        return issues

    expected = {
        "decision_snapshot_report_count": 0,
        "trend_context_report_count": 0,
        "evidence_source_report_count": 0,
        "manual_review_language_hit_count": 0,
        "complete_quality_report_count": 0,
    }
    reports = _report_pages(public_dir)
    for report in reports:
        evidence = _report_quality_evidence(report)
        if evidence["has_decision_snapshot"]:
            expected["decision_snapshot_report_count"] += 1
        if evidence["has_trend_context"]:
            expected["trend_context_report_count"] += 1
        if evidence["has_evidence_source_coverage"]:
            expected["evidence_source_report_count"] += 1
        expected["manual_review_language_hit_count"] += len(evidence["manual_review_language_hits"])
        if (
            evidence["has_decision_snapshot"]
            and evidence["has_trend_context"]
            and evidence["has_evidence_source_coverage"]
            and not evidence["manual_review_language_hits"]
        ):
            expected["complete_quality_report_count"] += 1
    expected_status = (
        "pass"
        if reports
        and expected["complete_quality_report_count"] == len(reports)
        and expected["manual_review_language_hit_count"] == 0
        else "needs_attention"
    )
    mismatches = [
        f"{field} expected {expected[field]} got {quality_gate.get(field)}"
        for field in expected
        if quality_gate.get(field) != expected[field]
    ]
    if quality_gate.get("status") != expected_status:
        mismatches.append(f"status expected {expected_status} got {quality_gate.get('status')}")
    if mismatches:
        issues.append("site-manifest.json -> inconsistent quality gate summary: " + ", ".join(mismatches))
    return issues


def _find_source_freshness_issues(public_dir=PUBLIC_DIR):
    public_dir = Path(public_dir)
    issues = []
    for page_name in ("index.html", "practice-plan.html"):
        page_path = public_dir / page_name
        if not page_path.exists():
            continue
        page_text = page_path.read_text(encoding="utf-8")
        if "数据新鲜度" not in page_text or "data-source-freshness-panel" not in page_text:
            issues.append(f"{page_name} -> missing source freshness panel")

    manifest_path = public_dir / "site-manifest.json"
    if not manifest_path.exists():
        return issues
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        manifest = {}
    source_freshness = manifest.get("source_freshness") if isinstance(manifest, dict) else None
    if not isinstance(source_freshness, dict):
        issues.append("site-manifest.json -> missing source freshness summary")
        return issues

    missing_fields = [
        field for field in REQUIRED_SOURCE_FRESHNESS_FIELDS
        if field not in source_freshness
    ]
    if missing_fields:
        issues.append("site-manifest.json -> missing source freshness fields: " + ", ".join(missing_fields))
        return issues

    reports = _report_pages(public_dir)
    report_count = len(reports)
    expected_report_timestamp_count = sum(
        1 for report in reports
        if _parse_report(report).get("report_generated_at")
    )
    mismatches = []
    if source_freshness.get("status") not in {"tracked", "partial", "source_timestamps_missing"}:
        mismatches.append(f"status invalid {source_freshness.get('status')}")
    if source_freshness.get("report_timestamp_count") != expected_report_timestamp_count:
        mismatches.append(
            "report_timestamp_count expected "
            f"{expected_report_timestamp_count} got {source_freshness.get('report_timestamp_count')}"
        )
    for field in (
        "stratz_fetch_timestamp_report_count",
        "opendota_fetch_timestamp_report_count",
        "complete_source_timestamp_report_count",
    ):
        value = source_freshness.get(field)
        if not isinstance(value, int) or value < 0 or value > report_count:
            mismatches.append(f"{field} out of range: {value}")
    if (
        isinstance(source_freshness.get("complete_source_timestamp_report_count"), int)
        and isinstance(source_freshness.get("stratz_fetch_timestamp_report_count"), int)
        and isinstance(source_freshness.get("opendota_fetch_timestamp_report_count"), int)
        and source_freshness["complete_source_timestamp_report_count"] > min(
            source_freshness["stratz_fetch_timestamp_report_count"],
            source_freshness["opendota_fetch_timestamp_report_count"],
        )
    ):
        mismatches.append("complete_source_timestamp_report_count exceeds source-specific coverage")
    if mismatches:
        issues.append("site-manifest.json -> inconsistent source freshness summary: " + ", ".join(mismatches))
    return issues


def _find_report_source_provenance_issues(public_dir=PUBLIC_DIR):
    public_dir = Path(public_dir)
    issues = []
    manifest_sources = {}
    manifest_path = public_dir / "site-manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
        for source in manifest.get("report_sources") or []:
            if isinstance(source, dict) and source.get("file"):
                manifest_sources[str(source["file"])] = source

    for report in _report_pages(public_dir):
        text = report.read_text(encoding="utf-8")
        if any(required not in text for required in REQUIRED_REPORT_SOURCE_PROVENANCE_TEXT):
            issues.append(f"{report.name} -> missing report source provenance")
            continue
        filename_match = re.search(r"_(\d{8,})_(\d{8}_\d{6})\.html$", report.name)
        markup_match = re.search(
            r'data-match-id="([^"]*)"[\s\S]*?'
            r'data-report-generated-at="([^"]*)"[\s\S]*?'
            r'data-stratz-fetched-at="([^"]*)"[\s\S]*?'
            r'data-opendota-fetched-at="([^"]*)"',
            text,
        )
        if not filename_match or not markup_match:
            issues.append(f"{report.name} -> malformed report source provenance")
            continue
        filename_match_id = filename_match.group(1)
        markup_match_id = markup_match.group(1)
        if markup_match_id != filename_match_id:
            issues.append(
                f"{report.name} -> source provenance match id {markup_match_id} "
                f"does not match filename {filename_match_id}"
            )
            continue
        expected = manifest_sources.get(report.name)
        if not expected:
            continue
        actual_values = {
            "match_id": markup_match.group(1),
            "report_generated_at": markup_match.group(2),
            "stratz_fetched_at": markup_match.group(3),
            "opendota_fetched_at": markup_match.group(4),
        }
        mismatches = [
            f"{field} expected {expected.get(field) or ''} got {actual_values[field]}"
            for field in actual_values
            if str(expected.get(field) or "") != actual_values[field]
        ]
        if mismatches:
            issues.append(f"{report.name} -> inconsistent report source provenance: " + ", ".join(mismatches))
    return issues


def _evidence_source_counts(evidence_sources):
    total = len(evidence_sources)
    complete = sum(1 for item in evidence_sources if item.get("status") == "available")
    partial = sum(1 for item in evidence_sources if item.get("status") == "partial")
    missing = sum(1 for item in evidence_sources if item.get("status") == "missing")
    return {
        "total": total,
        "complete": complete,
        "usable": complete + partial,
        "partial": partial,
        "missing": missing,
    }


def _report_evidence_completeness_attrs(text):
    tag_match = re.search(
        r'<section[^>]*class="[^"]*report-evidence-completeness[^"]*"[^>]*data-report-evidence-completeness[^>]*>',
        text,
    )
    if not tag_match:
        return None
    attrs = {}
    for key in ("total", "complete", "usable", "partial", "missing"):
        attr_match = re.search(rf'data-evidence-{key}="(\d+)"', tag_match.group(0))
        if attr_match:
            attrs[key] = int(attr_match.group(1))
    return attrs


def _find_report_evidence_completeness_issues(public_dir=PUBLIC_DIR):
    issues = []
    for report in _report_pages(public_dir):
        text = report.read_text(encoding="utf-8")
        if "evidence-source-list" not in text:
            continue
        if any(required not in text for required in REQUIRED_REPORT_EVIDENCE_COMPLETENESS_TEXT):
            issues.append(f"{report.name} -> missing report evidence completeness summary")
            continue
        attrs = _report_evidence_completeness_attrs(text)
        if attrs is None:
            issues.append(f"{report.name} -> malformed report evidence completeness summary")
            continue
        expected = _evidence_source_counts(_read_evidence_sources_from_text(text))
        mismatches = [
            f"{key} expected {expected[key]} got {attrs.get(key)}"
            for key in ("total", "complete", "usable", "partial", "missing")
            if attrs.get(key) != expected[key]
        ]
        if mismatches:
            issues.append(f"{report.name} -> evidence completeness mismatch: " + "; ".join(mismatches))
    return issues


def _find_hero_benchmark_issues(public_dir=PUBLIC_DIR):
    issues = []
    for report in _report_pages(public_dir):
        text = report.read_text(encoding="utf-8")
        if "hero_benchmarks" not in text and "OpenDota英雄样本百分位" not in text:
            continue
        if "英雄样本百分位" not in text or "benchmark-grid" not in text:
            issues.append(
                f"{report.name} -> hero benchmark evidence requires rendered 英雄样本百分位 section"
            )
    return issues


def _find_performance_context_issues(public_dir=PUBLIC_DIR):
    issues = []
    for report in _report_pages(public_dir):
        text = report.read_text(encoding="utf-8")
        if "opendota_performance_context" not in text:
            continue
        if "分路与参战画像" not in text or "performance-context-grid" not in text:
            issues.append(
                f"{report.name} -> performance context evidence requires rendered 分路与参战画像 section"
            )
    return issues


def _find_decision_snapshot_issues(public_dir=PUBLIC_DIR):
    issues = []
    required = (
        "上分决策卡",
        'id="decision-snapshot"',
        "decision-snapshot-grid",
        'data-decision-tab="action"',
        'data-decision-panel="validation"',
        "decision-jump-row",
    )
    for report in _report_pages(public_dir):
        text = report.read_text(encoding="utf-8")
        if "finding-card" not in text and "下一局行动清单" not in text:
            continue
        if any(item not in text for item in required):
            issues.append(
                f"{report.name} -> report with findings requires rendered 上分决策卡 decision snapshot"
            )
    return issues


def _find_report_trend_context_issues(public_dir=PUBLIC_DIR):
    issues = []
    required = (
        "近期同类问题",
        'class="report-trend-context"',
        "trend-context-examples",
        "完整趋势证据",
    )
    for report in _report_pages(public_dir):
        text = report.read_text(encoding="utf-8")
        if "finding-card" not in text and "下一局行动清单" not in text:
            continue
        if any(item not in text for item in required):
            issues.append(
                f"{report.name} -> report with findings requires rendered 近期同类问题 trend context"
            )
    return issues


def _public_review_language_paths(public_dir):
    paths = []
    for path in sorted(public_dir.glob("*")):
        if path.suffix not in {".html", ".txt", ".json"}:
            continue
        if (
            _is_report_page(path)
            or _is_topic_page(path)
            or path.name in SUPPORT_HTML_PAGES
            or path.name in SUPPORT_TEXT_EXPORTS
            or path.name == "review-trends.json"
        ):
            paths.append(path)
    return paths


def _find_manual_review_language_issues(public_dir=PUBLIC_DIR):
    issues = []
    for path in _public_review_language_paths(public_dir):
        text = path.read_text(encoding="utf-8")
        for phrase in FORBIDDEN_MANUAL_REVIEW_LANGUAGE:
            if phrase in text:
                issues.append(f"{path.name} -> manual review language is not allowed: {phrase}")
    return issues


def _find_report_text_quality_issues(public_dir=PUBLIC_DIR):
    issues = []
    for report in _report_pages(public_dir):
        text = report.read_text(encoding="utf-8")
        parser = TitleParser()
        parser.feed(text)
        if "复盘报告" not in parser.title:
            issues.append(f"{report.name} -> title must include 复盘报告")
        for phrase in FORBIDDEN_REPORT_TEXT:
            if phrase in text:
                issues.append(f"{report.name} -> awkward coaching phrase: {phrase}")
        if "死亡后目标窗口" in text and "目标前90秒生存规则" not in text:
            issues.append(f"{report.name} -> death/objective windows require 目标前90秒生存规则")
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

    death_review_issues = _find_death_review_coverage_issues(PUBLIC_DIR)
    if death_review_issues:
        preview = "; ".join(death_review_issues[:10])
        raise SystemExit(f"public death review coverage is incomplete: {preview}")

    quality_gate_issues = _find_quality_gate_issues(PUBLIC_DIR)
    if quality_gate_issues:
        preview = "; ".join(quality_gate_issues[:10])
        raise SystemExit(f"public quality gate summary is incomplete: {preview}")

    source_freshness_issues = _find_source_freshness_issues(PUBLIC_DIR)
    if source_freshness_issues:
        preview = "; ".join(source_freshness_issues[:10])
        raise SystemExit(f"public source freshness summary is incomplete: {preview}")

    report_source_issues = _find_report_source_provenance_issues(PUBLIC_DIR)
    if report_source_issues:
        preview = "; ".join(report_source_issues[:10])
        raise SystemExit(f"public report source provenance is incomplete: {preview}")

    report_evidence_completeness_issues = _find_report_evidence_completeness_issues(PUBLIC_DIR)
    if report_evidence_completeness_issues:
        preview = "; ".join(report_evidence_completeness_issues[:10])
        raise SystemExit(f"public report evidence completeness summaries are incomplete: {preview}")

    hero_benchmark_issues = _find_hero_benchmark_issues(PUBLIC_DIR)
    if hero_benchmark_issues:
        preview = "; ".join(hero_benchmark_issues[:10])
        raise SystemExit(f"public hero benchmark sections are incomplete: {preview}")

    performance_context_issues = _find_performance_context_issues(PUBLIC_DIR)
    if performance_context_issues:
        preview = "; ".join(performance_context_issues[:10])
        raise SystemExit(f"public performance context sections are incomplete: {preview}")

    decision_snapshot_issues = _find_decision_snapshot_issues(PUBLIC_DIR)
    if decision_snapshot_issues:
        preview = "; ".join(decision_snapshot_issues[:10])
        raise SystemExit(f"public decision snapshot sections are incomplete: {preview}")

    trend_context_issues = _find_report_trend_context_issues(PUBLIC_DIR)
    if trend_context_issues:
        preview = "; ".join(trend_context_issues[:10])
        raise SystemExit(f"public report trend contexts are incomplete: {preview}")

    manual_language_issues = _find_manual_review_language_issues(PUBLIC_DIR)
    if manual_language_issues:
        preview = "; ".join(manual_language_issues[:10])
        raise SystemExit(f"public manual review language issues: {preview}")

    text_quality_issues = _find_report_text_quality_issues(PUBLIC_DIR)
    if text_quality_issues:
        preview = "; ".join(text_quality_issues[:10])
        raise SystemExit(f"public report text quality issues: {preview}")

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
