import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.analyzer import _item_detail

DEFAULT_SOURCE = Path(r"C:\Users\12031\Desktop\REVIEW_REPORT")
PUBLIC_DIR = ROOT / "public"
STATIC_SOURCE = ROOT / "report" / "static"
SOURCE_DB_PATH = ROOT / "data" / "dota2.db"
REPORT_NAME_RE = re.compile(r"^(?P<hero>.+)_(?P<match_id>\d{8,})_(?P<stamp>\d{8}_\d{6})\.html$")
LEGACY_ITEM_SLOT_RE = re.compile(
    r'(<div class="item-slot item-name" title=")(?:Item #|ID )(?P<item_id>\d+)(">\s*)(?:Item #)?\d+(\s*</div>)',
    re.MULTILINE,
)
HERO_IMAGE_BASE = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes"
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
PRIORITY_PREFIX_RE = re.compile(r"^(?:高|中|低)优先级\s*[·:：\-]\s*")
FOCUS_TAXONOMY = (
    {
        "topic_id": "early_resource",
        "focus": "前10分钟资源",
        "aliases": ("前10分钟资源", "前10分钟发育", "前期资源效率", "前期发育效率", "对线补刀", "对线发育"),
    },
    {
        "topic_id": "death_cost",
        "focus": "死亡成本",
        "aliases": ("死亡成本", "无效死亡", "生存与死亡", "生存能力"),
    },
    {
        "topic_id": "item_conversion",
        "focus": "装备后转化",
        "aliases": ("装备后转化", "装备转化", "关键装备转化", "强势期转化"),
    },
    {
        "topic_id": "close_game",
        "focus": "终结比赛",
        "aliases": ("终结比赛", "结束比赛", "终结能力", "优势终结"),
    },
    {
        "topic_id": "resource_continuity",
        "focus": "中后期资源连续性",
        "aliases": ("中后期资源连续性", "中期资源连续性", "后期资源连续性", "资源连续性"),
    },
    {
        "topic_id": "vision_control",
        "focus": "视野/控图",
        "aliases": ("视野/控图", "视野与控图", "视野控图", "地图视野"),
    },
)


def _write_utf8(path, text):
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    Path(path).write_bytes(normalized.encode("utf-8"))


class ReportMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_metadata = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag.lower() == "script" and attributes.get("id") == "report-metadata":
            self.in_metadata = True

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.in_metadata:
            self.in_metadata = False

    def handle_data(self, data):
        if self.in_metadata:
            self.parts.append(data)

    @property
    def metadata(self):
        if not self.parts:
            return {}
        try:
            value = json.loads("".join(self.parts))
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}


class CoachFindingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_card = False
        self.card_depth = 0
        self.current_field = None
        self.current_parts = []
        self.finding = None
        self.findings = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag.lower() == "div" and "finding-card" in classes and not self.in_card:
            self.in_card = True
            self.card_depth = 1
            self.finding = {"review_priority": _priority_from_classes(classes)}
            return
        if self.in_card:
            if tag.lower() == "div":
                self.card_depth += 1
            if "finding-title" in classes:
                self.current_field = "review_focus"
                self.current_parts = []
            elif "finding-line" in classes:
                self.current_field = "finding_line"
                self.current_parts = []

    def handle_endtag(self, tag):
        if not self.in_card:
            return
        if self.current_field and tag.lower() == "div":
            text = _normalize_text("".join(self.current_parts))
            if self.current_field == "review_focus" and text:
                self.finding["review_focus"] = text
            elif self.current_field == "finding_line" and text:
                self._store_line(text)
            self.current_field = None
            self.current_parts = []
        if tag.lower() == "div":
            self.card_depth -= 1
            if self.card_depth <= 0:
                self.in_card = False
                if self.finding:
                    self.findings.append(self.finding)
                self.finding = None

    def handle_data(self, data):
        if self.in_card and self.current_field:
            self.current_parts.append(data)

    def _store_line(self, text):
        if self.finding is None:
            return
        if text.startswith("证据:"):
            self.finding.setdefault("review_evidence", text.removeprefix("证据:").strip())
        elif text.startswith("训练目标:"):
            self.finding.setdefault("next_action", text.removeprefix("训练目标:").strip())
        elif text.startswith("验收标准:"):
            self.finding.setdefault("success_metric", text.removeprefix("验收标准:").strip())


class EvidenceSourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_row = False
        self.row_depth = 0
        self.current_field = None
        self.current_parts = []
        self.current_row = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag.lower() == "div" and "evidence-source-row" in classes and not self.in_row:
            self.in_row = True
            self.row_depth = 1
            self.current_row = {"status": _evidence_source_status(classes)}
            return
        if not self.in_row:
            return
        if tag.lower() == "div":
            self.row_depth += 1
        if "evidence-source-name" in classes:
            self.current_field = "label"
            self.current_parts = []
        elif "evidence-source-origin" in classes:
            self.current_field = "source"
            self.current_parts = []
        elif "evidence-source-coverage" in classes:
            self.current_field = "coverage"
            self.current_parts = []

    def handle_endtag(self, tag):
        if not self.in_row:
            return
        if self.current_field and tag.lower() in {"div", "span"}:
            text = _normalize_text("".join(self.current_parts))
            if text and self.current_row is not None:
                self.current_row[self.current_field] = text
            self.current_field = None
            self.current_parts = []
        if tag.lower() == "div":
            self.row_depth -= 1
            if self.row_depth <= 0:
                if self.current_row and self.current_row.get("label"):
                    self.rows.append(self.current_row)
                self.in_row = False
                self.current_row = None

    def handle_data(self, data):
        if self.in_row and self.current_field:
            self.current_parts.append(data)


def _evidence_source_status(classes):
    for status in ("available", "partial", "missing"):
        if status in classes:
            return status
    return "unknown"


def _read_evidence_sources_from_text(text):
    parser = EvidenceSourceParser()
    parser.feed(text or "")
    return parser.rows


def _priority_from_classes(classes):
    for priority in ("high", "medium", "low"):
        if priority in classes:
            return priority
    return "unknown"


def _normalize_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def _display_hero(raw_name):
    return raw_name.replace("_", " ")


def _coerce_iso_timestamp(value, *, assume_utc=False):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        if assume_utc:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            return parsed.strftime("%Y-%m-%dT%H:%M:%S")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp_sort_key(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_timestamp(values):
    clean_values = [value for value in values if value]
    if not clean_values:
        return None
    return max(clean_values, key=_timestamp_sort_key)


def _oldest_timestamp(values):
    clean_values = [value for value in values if value]
    if not clean_values:
        return None
    return min(clean_values, key=_timestamp_sort_key)


def _report_generated_at_from_name(filename):
    match = REPORT_NAME_RE.match(str(filename))
    if not match:
        return None
    try:
        generated = datetime.strptime(match.group("stamp"), "%Y%m%d_%H%M%S")
    except ValueError:
        return None
    return generated.strftime("%Y-%m-%dT%H:%M:%S")


def _normalize_source_fetch_times(source_fetch_times):
    normalized = {}
    for match_id, raw in (source_fetch_times or {}).items():
        if not isinstance(raw, dict):
            continue
        entry = {
            "stratz_fetched_at": _coerce_iso_timestamp(raw.get("stratz_fetched_at"), assume_utc=True),
            "opendota_fetched_at": _coerce_iso_timestamp(raw.get("opendota_fetched_at"), assume_utc=True),
        }
        entry["latest_external_fetch_at"] = _latest_timestamp(
            [
                raw.get("latest_external_fetch_at"),
                entry["stratz_fetched_at"],
                entry["opendota_fetched_at"],
            ]
        )
        entry["oldest_external_fetch_at"] = _oldest_timestamp(
            [
                entry["stratz_fetched_at"],
                entry["opendota_fetched_at"],
            ]
        )
        normalized[str(match_id)] = {key: value for key, value in entry.items() if value}
    return normalized


def _load_source_fetch_times(match_ids, db_path=None):
    db_path = Path(db_path) if db_path else None
    if not db_path or not db_path.exists():
        return {}
    clean_ids = sorted({str(match_id) for match_id in match_ids if match_id})
    if not clean_ids:
        return {}
    placeholders = ",".join("?" for _ in clean_ids)
    sources = {
        "stratz_fetched_at": "stratz_details",
        "opendota_fetched_at": "opendota_details",
    }
    fetched = {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            for field, table in sources.items():
                rows = conn.execute(
                    f"SELECT match_id, fetched_at FROM {table} WHERE CAST(match_id AS TEXT) IN ({placeholders})",
                    clean_ids,
                ).fetchall()
                for row in rows:
                    entry = fetched.setdefault(str(row["match_id"]), {})
                    entry[field] = _coerce_iso_timestamp(row["fetched_at"], assume_utc=True)
        finally:
            conn.close()
    except sqlite3.Error:
        return _normalize_source_fetch_times(fetched)
    return _normalize_source_fetch_times(fetched)


def _read_embedded_metadata(path):
    parser = ReportMetadataParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.metadata


def _read_coach_finding(path):
    findings = _read_coach_findings(path)
    if findings:
        return findings[0]
    return {
        "review_focus": "需要查看报告",
        "review_evidence": "",
        "next_action": "打开报告查看下一局行动清单。",
        "success_metric": "以报告内验收标准为准。",
        "review_priority": "unknown",
    }


def _read_coach_findings(path):
    parser = CoachFindingParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return [
        {
            "review_focus": finding.get("review_focus") or "需要查看报告",
            "review_evidence": finding.get("review_evidence") or "",
            "next_action": finding.get("next_action") or "打开报告查看下一局行动清单。",
            "success_metric": finding.get("success_metric") or "以报告内验收标准为准。",
            "review_priority": finding.get("review_priority") or "unknown",
        }
        for finding in parser.findings
    ]


def _normalize_lineup(value):
    return [hero for hero in (value or []) if isinstance(hero, dict) and hero.get("name")]


def _parse_report(path):
    match = REPORT_NAME_RE.match(path.name)
    fallback_hero = _display_hero(match.group("hero")) if match else path.stem
    fallback_match_id = match.group("match_id") if match else ""
    report_text = path.read_text(encoding="utf-8")
    evidence_sources = _read_evidence_sources_from_text(report_text)
    metadata = _read_embedded_metadata(path)
    coach_findings = _read_coach_findings(path)
    coach_finding = coach_findings[0] if coach_findings else _read_coach_finding(path)
    hero = metadata.get("hero") if isinstance(metadata.get("hero"), dict) else {}
    kda = metadata.get("kda") if isinstance(metadata.get("kda"), dict) else {}
    score = metadata.get("score") if isinstance(metadata.get("score"), dict) else {}
    death_evidence = {
        "has_death_review_workbench": 'class="death-review-workbench"' in report_text,
        "has_death_recovery_windows": "死亡后恢复窗口" in report_text,
        "has_death_coordinate_map": 'class="death-coordinate-map"' in report_text,
    }
    death_evidence["has_complete_death_review"] = all(death_evidence.values())
    quality_evidence = {
        "has_decision_snapshot": 'id="decision-snapshot"' in report_text and "上分决策卡" in report_text,
        "has_trend_context": 'class="report-trend-context"' in report_text and "近期同类问题" in report_text,
        "has_evidence_source_coverage": "证据来源与覆盖" in report_text and "evidence-source-list" in report_text,
        "manual_review_language_hits": [
            phrase for phrase in FORBIDDEN_MANUAL_REVIEW_LANGUAGE
            if phrase in report_text
        ],
    }
    quality_evidence["has_complete_quality_gate"] = (
        quality_evidence["has_decision_snapshot"]
        and quality_evidence["has_trend_context"]
        and quality_evidence["has_evidence_source_coverage"]
        and not quality_evidence["manual_review_language_hits"]
    )

    return {
        "file": path.name,
        "hero": hero.get("name") or fallback_hero,
        "hero_slug": hero.get("slug") or "",
        "match_id": str(metadata.get("match_id") or fallback_match_id),
        "report_generated_at": _report_generated_at_from_name(path.name),
        "is_win": metadata.get("is_win") if isinstance(metadata.get("is_win"), bool) else None,
        "ended_at": metadata.get("ended_at"),
        "duration_seconds": metadata.get("duration_seconds"),
        "kda": kda,
        "score": score,
        "allies": _normalize_lineup(metadata.get("allies")),
        "enemies": _normalize_lineup(metadata.get("enemies")),
        "size": path.stat().st_size,
        "review_findings": coach_findings,
        "evidence_sources": evidence_sources,
        "death_evidence": death_evidence,
        "quality_evidence": quality_evidence,
        **coach_finding,
    }


def _copy_static_assets(public_dir):
    if STATIC_SOURCE.exists():
        shutil.copytree(STATIC_SOURCE, public_dir / "static", dirs_exist_ok=True)


def _upgrade_legacy_item_slots(text):
    def replace(match):
        item_id = int(match.group("item_id"))
        item_name = _item_detail(item_id).get("name") or f"Item #{item_id}"
        if item_name.startswith("Item #"):
            return match.group(0)
        return (
            f'{match.group(1)}ID {item_id}{match.group(3)}'
            f'{html.escape(item_name)}'
            f'{match.group(4)}'
        )

    return LEGACY_ITEM_SLOT_RE.sub(replace, text)


def _copy_reports(source, public_dir):
    reports = sorted(source.glob("*.html"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not reports:
        raise SystemExit(f"No HTML reports found in {source}")

    copied = []
    seen_matches = set()
    for report in reports:
        parsed = _parse_report(report)
        dedupe_key = parsed.get("match_id") or report.name
        if dedupe_key in seen_matches:
            continue
        seen_matches.add(dedupe_key)
        target = public_dir / report.name
        shutil.copy2(report, target)
        upgraded_text = _upgrade_legacy_item_slots(target.read_text(encoding="utf-8"))
        _write_utf8(target, upgraded_text)
        copied.append(_parse_report(target))
    return copied


def _format_duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "未知"
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def _priority_label(priority):
    return {
        "high": "高",
        "medium": "中",
        "low": "低",
    }.get(priority, "待确认")


def _result_key(report):
    if report.get("is_win") is True:
        return "win"
    if report.get("is_win") is False:
        return "lose"
    return "unknown"


def _priority_rank(report):
    priority_score = {"high": 0, "medium": 1, "low": 2, "unknown": 3}.get(report.get("review_priority"), 3)
    loss_score = 0 if report.get("is_win") is False else 1
    deaths = (report.get("kda") or {}).get("deaths")
    death_score = -int(deaths) if isinstance(deaths, (int, float)) else 0
    sort_time = _report_sort_key(report)
    time_score = sort_time.timestamp() if sort_time.year > 1971 else 0
    return (priority_score, loss_score, death_score, -time_score)


def _focus_token(value):
    without_priority = PRIORITY_PREFIX_RE.sub("", _normalize_text(value))
    return re.sub(r"[\s·:：/\\_\-]+", "", without_priority).lower()


def _classify_focus(value):
    source_focus = PRIORITY_PREFIX_RE.sub("", _normalize_text(value)) or "需要查看报告"
    token = _focus_token(source_focus)
    for topic in FOCUS_TAXONOMY:
        alias_tokens = {_focus_token(alias) for alias in topic["aliases"]}
        if token in alias_tokens:
            return topic["topic_id"], topic["focus"], source_focus
    return f"custom::{token or 'unknown'}", source_focus, source_focus


def _iter_trend_findings(reports):
    for report in reports:
        findings = report.get("review_findings")
        if not isinstance(findings, list) or not findings:
            findings = [report]
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            item = {key: value for key, value in report.items() if key != "review_findings"}
            item.update(finding)
            yield item


def _build_focus_trends(reports):
    grouped = defaultdict(list)
    topic_labels = {}
    for finding in _iter_trend_findings(reports):
        topic_id, focus, source_focus = _classify_focus(finding.get("review_focus"))
        finding["source_focus"] = source_focus
        grouped[topic_id].append(finding)
        topic_labels[topic_id] = focus

    trends = []
    for topic_id, items in grouped.items():
        sorted_items = sorted(items, key=_priority_rank)
        unique_matches = {}
        for item_index, item in enumerate(sorted_items):
            match_key = str(item.get("match_id") or item.get("file") or f"finding-{item_index}")
            unique_matches.setdefault(match_key, item)
        representative_items = list(unique_matches.values())
        priority = representative_items[0].get("review_priority") or "unknown"
        heroes = sorted({str(item.get("hero") or "未知英雄") for item in representative_items})
        actions = [item.get("next_action") for item in sorted_items if item.get("next_action")]
        metrics = [item.get("success_metric") for item in sorted_items if item.get("success_metric")]
        examples = [
            {
                "hero": item.get("hero") or "未知英雄",
                "match_id": str(item.get("match_id") or ""),
                "file": item.get("file") or "",
                "result": "win" if item.get("is_win") is True else "lose" if item.get("is_win") is False else "unknown",
            }
            for item in representative_items[:3]
        ]
        detailed_findings = [
            {
                "hero": item.get("hero") or "未知英雄",
                "hero_slug": item.get("hero_slug") or "",
                "match_id": str(item.get("match_id") or ""),
                "file": item.get("file") or "",
                "result": "win" if item.get("is_win") is True else "lose" if item.get("is_win") is False else "unknown",
                "source_focus": item.get("source_focus") or topic_labels[topic_id],
                "review_evidence": item.get("review_evidence") or "该报告未提供单独证据文本。",
                "next_action": item.get("next_action") or "打开报告查看下一局行动清单。",
                "success_metric": item.get("success_metric") or "以报告内验收标准为准。",
                "priority": item.get("review_priority") or "unknown",
            }
            for item in sorted_items
        ]
        trends.append({
            "topic_id": topic_id,
            "focus": topic_labels[topic_id],
            "page": _topic_page_filename(topic_id),
            "count": len(representative_items),
            "finding_count": len(items),
            "priority": priority,
            "heroes": heroes,
            "source_focuses": sorted({item["source_focus"] for item in sorted_items}),
            "next_action": actions[0] if actions else "打开报告查看下一局行动清单。",
            "success_metric": metrics[0] if metrics else "以报告内验收标准为准。",
            "examples": examples,
            "findings": detailed_findings,
        })

    return sorted(
        trends,
        key=lambda trend: (
            {"high": 0, "medium": 1, "low": 2, "unknown": 3}.get(trend["priority"], 3),
            -trend["count"],
            trend["focus"],
        ),
    )


def _topic_page_filename(topic_id):
    raw = str(topic_id or "unknown")
    token = re.sub(r"[^a-z0-9]+", "-", raw.lower().replace("_", "-")).strip("-")
    if raw.startswith("custom::") or not token:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
        token = f"custom-{digest}"
    return f"trend-{token}.html"


def _practice_token(value, fallback):
    raw = str(value or "")
    if raw.startswith("custom::"):
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
        return f"custom-{digest}"
    token = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).strip("-")
    return token or fallback


def _filtered_topic_href(topic_page, **params):
    clean_params = {key: value for key, value in params.items() if value}
    if not clean_params:
        return topic_page
    return f"{topic_page}?{urlencode(clean_params)}"


def _trend_result_counts(trend):
    counts = {"win": 0, "lose": 0, "unknown": 0}
    for finding in trend.get("findings") or []:
        result = finding.get("result") if finding.get("result") in counts else "unknown"
        counts[result] += 1
    if not any(counts.values()):
        for example in trend.get("examples") or []:
            result = example.get("result") if example.get("result") in counts else "unknown"
            counts[result] += 1
    return counts


def _primary_trend_hero(trend):
    hero_counts = defaultdict(int)
    for finding in trend.get("findings") or []:
        hero = finding.get("hero")
        if hero:
            hero_counts[str(hero)] += 1
    if hero_counts:
        return sorted(hero_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    heroes = trend.get("heroes") or []
    return str(heroes[0]) if heroes else ""


def _render_practice_evidence_links(trend, topic_page):
    counts = _trend_result_counts(trend)
    primary_hero = _primary_trend_hero(trend)
    links = [
        (
            "失败证据",
            counts["lose"],
            _filtered_topic_href(topic_page, result="lose"),
        ),
        (
            "胜利样本",
            counts["win"],
            _filtered_topic_href(topic_page, result="win"),
        ),
    ]
    if primary_hero:
        links.append((
            f"{primary_hero} 专项",
            None,
            _filtered_topic_href(topic_page, hero=primary_hero),
        ))
    rendered = []
    for label, count, href in links:
        text = label if count is None else f"{label} {count}"
        rendered.append(f'<a href="{html.escape(href, quote=True)}">{html.escape(text)}</a>')
    return (
        '<div class="practice-evidence-links" aria-label="训练证据入口">'
        f'{"".join(rendered)}'
        '</div>'
    )


def _render_practice_checklist(trend, index):
    token = _practice_token(trend.get("topic_id"), f"topic-{index}")
    focus = trend.get("focus") or "需要查看报告"
    action = trend.get("next_action") or "打开报告查看下一局行动清单。"
    metric = trend.get("success_metric") or "以报告内验收标准为准。"
    checkpoints = (
        ("赛前锁定", f"本局只盯一个主题：{focus}。"),
        ("对局中执行", action),
        ("赛后验收", metric),
    )
    items = []
    for item_index, (label, text) in enumerate(checkpoints, start=1):
        check_id = f"practice-{token}-{item_index}"
        check_key = f"{token}:{item_index}"
        items.append(
            '<label class="practice-check-item">'
            f'<input id="{html.escape(check_id, quote=True)}" type="checkbox" '
            f'data-practice-check="{html.escape(check_key, quote=True)}">'
            f'<span><strong>{html.escape(label)}</strong>{html.escape(text)}</span>'
            '</label>'
        )
    return (
        '<section class="practice-checklist" aria-label="下一局检查点">'
        '<div class="practice-checklist-head">'
        '<strong>下一局检查点</strong>'
        '<span data-practice-progress>0 / 3</span>'
        '</div>'
        f'{"".join(items)}'
        '</section>'
    )


def _render_practice_plan_text(trends, manifest):
    latest = manifest.get("latest_match") or {}
    lines = [
        "Dota 2 下一局训练清单",
        "玩家 173776719",
        f"基于 {manifest.get('report_count') or 0} 场复盘、{manifest.get('finding_count') or 0} 条教练证据生成。",
    ]
    if latest.get("hero") and latest.get("match_id"):
        lines.append(f"最新复盘：{latest.get('hero')} #{latest.get('match_id')}")
    lines.append("")

    for index, trend in enumerate(trends[:5], start=1):
        focus = trend.get("focus") or "需要查看报告"
        action = trend.get("next_action") or "打开报告查看下一局行动清单。"
        metric = trend.get("success_metric") or "以报告内验收标准为准。"
        topic_page = trend.get("page") or "index.html"
        primary_hero = _primary_trend_hero(trend)
        lines.extend([
            f"第 {index} 优先级：{focus}",
            f"- 出现：{trend.get('count') or 0} 局 / {trend.get('finding_count') or trend.get('count') or 0} 条证据",
            f"- 下一局动作：{action}",
            f"- 验收标准：{metric}",
            f"- 失败证据：{_filtered_topic_href(topic_page, result='lose')}",
            f"- 胜利样本：{_filtered_topic_href(topic_page, result='win')}",
        ])
        if primary_hero:
            lines.append(f"- 英雄专项：{_filtered_topic_href(topic_page, hero=primary_hero)}")
        lines.extend([
            "- 检查点：赛前锁定本主题；对局中执行动作；赛后按验收标准复盘。",
            "",
        ])

    return "\n".join(lines).rstrip() + "\n"


def _render_match_brief_text(trends, manifest):
    latest = manifest.get("latest_match") or {}
    lines = [
        "Dota 2 赛前执行卡",
        "玩家 173776719",
        f"基于 {manifest.get('report_count') or 0} 场复盘、{manifest.get('finding_count') or 0} 条教练证据生成。",
    ]
    if latest.get("hero") and latest.get("match_id"):
        lines.append(f"最新复盘：{latest.get('hero')} #{latest.get('match_id')}")
    lines.append("")

    for index, trend in enumerate(trends[:3], start=1):
        focus = trend.get("focus") or "需要查看报告"
        action = trend.get("next_action") or "打开报告查看下一局行动清单。"
        metric = trend.get("success_metric") or "以报告内验收标准为准。"
        topic_page = trend.get("page") or "index.html"
        lines.extend([
            f"承诺 {index}：{focus}",
            f"- 出现：{trend.get('count') or 0} 局 / {trend.get('finding_count') or trend.get('count') or 0} 条证据",
            f"- 对局中只盯：{action}",
            f"- 赛后复核：{metric}",
            f"- 失败证据：{_filtered_topic_href(topic_page, result='lose')}",
            f"- 失败证据摘录：{_trend_failure_evidence(trend)}",
            f"- 胜利样本：{_filtered_topic_href(topic_page, result='win')}",
            f"- 胜利样本摘录：{_trend_win_evidence(trend)}",
            "",
        ])

    return "\n".join(lines).rstrip() + "\n"


def _trend_failure_evidence(trend):
    return _trend_result_evidence(
        trend,
        "lose",
        "该主题暂无单独失败证据文本，打开完整证据页查看。",
        fallback_to_any=True,
    )


def _trend_win_evidence(trend):
    return _trend_result_evidence(
        trend,
        "win",
        "暂无胜利样本；本主题先按失败证据执行，后续胜局会自动补入。",
        fallback_to_any=False,
    )


def _trend_result_evidence(trend, result, fallback, fallback_to_any):
    findings = trend.get("findings") or []
    for finding in findings:
        if finding.get("result") == result and finding.get("review_evidence"):
            return finding.get("review_evidence")
    if fallback_to_any:
        for finding in findings:
            if finding.get("review_evidence"):
                return finding.get("review_evidence")
    return fallback


def _render_match_brief(trends, reports, output_path, manifest=None):
    newest = reports[0] if reports else {}
    manifest = manifest or _build_site_manifest(reports, trends)
    latest = manifest.get("latest_match") or {}
    latest_file = html.escape(latest.get("file") or newest.get("file") or "index.html", quote=True)
    latest_hero = html.escape(latest.get("hero") or newest.get("hero") or "未知英雄")
    latest_match_id = html.escape(str(latest.get("match_id") or newest.get("match_id") or ""))
    latest_focus = html.escape(latest.get("review_focus") or newest.get("review_focus") or "需要查看报告")
    report_count = html.escape(str(manifest.get("report_count") or 0))
    finding_count = html.escape(str(manifest.get("finding_count") or 0))
    topic_count = html.escape(str(manifest.get("topic_count") or 0))

    cards = []
    command_links = []
    for index, trend in enumerate(trends[:3], start=1):
        focus = html.escape(trend.get("focus") or "需要查看报告")
        action = html.escape(trend.get("next_action") or "打开报告查看下一局行动清单。")
        metric = html.escape(trend.get("success_metric") or "以报告内验收标准为准。")
        failure_evidence = html.escape(_trend_failure_evidence(trend))
        win_evidence = html.escape(_trend_win_evidence(trend))
        topic_page_raw = trend.get("page") or "index.html"
        failure_href = html.escape(_filtered_topic_href(topic_page_raw, result="lose"), quote=True)
        win_href = html.escape(_filtered_topic_href(topic_page_raw, result="win"), quote=True)
        commitment_id = f"brief-commitment-{index}"
        command_links.append(
            f'<a class="brief-command-link" href="#{commitment_id}"><span>承诺 {index}</span><strong>{focus}</strong></a>'
        )
        cards.append(
            f"""
            <article class="brief-card" id="{commitment_id}">
                <div class="brief-card-top">
                    <span class="brief-rank">承诺 {index}</span>
                    <span>{html.escape(str(trend.get('count') or 0))} 局出现</span>
                </div>
                <h2>{focus}</h2>
                <div class="brief-step"><strong>对局中只盯</strong><span>{action}</span></div>
                <div class="brief-step"><strong>赛后复核</strong><span>{metric}</span></div>
                <div class="brief-proof-grid">
                    <div class="brief-evidence"><strong>失败证据</strong><span>{failure_evidence}</span><a class="topic-report-link" href="{failure_href}">打开失败证据</a></div>
                    <div class="brief-evidence win-sample"><strong>胜利样本</strong><span>{win_evidence}</span><a class="topic-report-link" href="{win_href}">打开胜利样本</a></div>
                </div>
            </article>
            """.strip()
        )
    card_html = "".join(cards) if cards else '<div class="trend-empty">暂无可生成的赛前执行卡。</div>'
    command_bar_html = ""
    if command_links:
        command_bar_html = f"""
    <nav class="brief-command-bar" aria-label="赛前承诺导航">
        <span>赛前只盯</span>
        <div class="brief-command-track">
            {''.join(command_links)}
        </div>
    </nav>
""".rstrip()
    brief_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dota 2 赛前执行卡</title>
    <meta name="description" content="根据最近 Dota 2 复盘证据生成的下一局赛前执行卡。">
    <link rel="icon" href="data:,">
    <link rel="stylesheet" href="static/style.css">
</head>
<body class="history-page brief-page">
<div class="container history-container">
    <header class="history-header">
        <div>
            <a class="back-link" href="index.html">&larr; 比赛历史</a>
            <div class="history-eyebrow">玩家 173776719</div>
            <h1>赛前执行卡</h1>
            <p>下一局开打前只看这三件事。每一条都来自已有复盘证据，不新增推断。</p>
        </div>
        <a class="primary-link" href="{latest_file}">打开最新复盘</a>
        <a class="primary-link secondary-link" href="practice-plan.html">完整训练计划</a>
        <a class="primary-link secondary-link" href="match-brief.txt">导出执行卡</a>
    </header>

    <section class="brief-hero" aria-label="赛前摘要">
        <div>
            <span>最新复盘</span>
            <strong>{latest_hero} #{latest_match_id}</strong>
            <small>当前重点：{latest_focus}</small>
        </div>
        <div>
            <span>三条核心承诺</span>
            <strong>{min(len(trends), 3)}</strong>
            <small>死亡、转化、控图等主题按证据优先级排序。</small>
        </div>
        <div>
            <span>使用方式</span>
            <strong>30 秒</strong>
            <small>赛前读承诺；对局中只盯动作；赛后按指标复核。</small>
        </div>
    </section>

    <section class="brief-freshness" aria-label="证据覆盖">
        <strong>证据覆盖</strong>
        <span data-brief-report-count>{report_count} 场复盘</span>
        <span>{finding_count} 条教练证据</span>
        <span>{topic_count} 个训练主题</span>
        <small>只引用已生成报告和主题证据。</small>
    </section>

{command_bar_html}

    <main class="brief-grid" aria-label="三条核心承诺">
        {card_html}
    </main>

    <section class="brief-footer">
        <strong>复盘闭环</strong>
        <span>打完后回到完整训练计划勾选执行情况，再打开失败证据对照同类问题是否减少。</span>
        <a class="primary-link secondary-link" href="practice-plan.html">回到训练计划</a>
    </section>
</div>
</body>
</html>
"""
    _write_utf8(output_path, brief_html)


def _count_report_findings(reports):
    total = 0
    for report in reports:
        findings = report.get("review_findings")
        if isinstance(findings, list) and findings:
            total += len(findings)
        else:
            total += 1
    return total


def _source_fetches_for_report(report, source_fetch_times):
    match_id = str(report.get("match_id") or "")
    return dict((source_fetch_times or {}).get(match_id) or {})


def _build_source_freshness(sorted_reports, source_fetch_times):
    report_generated_values = [report.get("report_generated_at") for report in sorted_reports]
    source_fetches = [
        _source_fetches_for_report(report, source_fetch_times)
        for report in sorted_reports
    ]
    stratz_count = sum(1 for fetches in source_fetches if fetches.get("stratz_fetched_at"))
    opendota_count = sum(1 for fetches in source_fetches if fetches.get("opendota_fetched_at"))
    complete_count = sum(
        1 for fetches in source_fetches
        if fetches.get("stratz_fetched_at") and fetches.get("opendota_fetched_at")
    )
    external_values = []
    for fetches in source_fetches:
        external_values.extend([
            fetches.get("stratz_fetched_at"),
            fetches.get("opendota_fetched_at"),
            fetches.get("latest_external_fetch_at"),
        ])
    report_count = len(sorted_reports)
    if report_count and complete_count == report_count:
        status = "tracked"
    elif stratz_count or opendota_count:
        status = "partial"
    else:
        status = "source_timestamps_missing"
    return {
        "status": status,
        "basis": "report_filename_timestamp+sqlite_fetched_at" if (stratz_count or opendota_count) else "report_filename_timestamp",
        "report_timestamp_count": sum(1 for value in report_generated_values if value),
        "stratz_fetch_timestamp_report_count": stratz_count,
        "opendota_fetch_timestamp_report_count": opendota_count,
        "complete_source_timestamp_report_count": complete_count,
        "latest_report_generated_at": _latest_timestamp(report_generated_values),
        "oldest_report_generated_at": _oldest_timestamp(report_generated_values),
        "latest_external_fetch_at": _latest_timestamp(external_values),
        "oldest_external_fetch_at": _oldest_timestamp(external_values),
        "limitation": "公开页展示的是已缓存证据的抓取时间；Cloudflare Pages 发布不会重新访问 STRATZ/OpenDota。",
    }


def _build_site_manifest(reports, trends, source_fetch_times=None):
    sorted_reports = sorted(reports, key=_report_sort_key, reverse=True)
    source_fetch_times = _normalize_source_fetch_times(source_fetch_times or {})
    newest = sorted_reports[0] if sorted_reports else {}
    known_results = [report for report in sorted_reports if report.get("is_win") is not None]
    wins = sum(1 for report in known_results if report["is_win"])
    losses = len(known_results) - wins
    death_review_workbench_count = sum(
        1 for report in sorted_reports
        if (report.get("death_evidence") or {}).get("has_death_review_workbench")
    )
    death_recovery_window_count = sum(
        1 for report in sorted_reports
        if (report.get("death_evidence") or {}).get("has_death_recovery_windows")
    )
    death_coordinate_map_count = sum(
        1 for report in sorted_reports
        if (report.get("death_evidence") or {}).get("has_death_coordinate_map")
    )
    complete_death_review_count = sum(
        1 for report in sorted_reports
        if (report.get("death_evidence") or {}).get("has_complete_death_review")
    )
    decision_snapshot_count = sum(
        1 for report in sorted_reports
        if (report.get("quality_evidence") or {}).get("has_decision_snapshot")
    )
    trend_context_count = sum(
        1 for report in sorted_reports
        if (report.get("quality_evidence") or {}).get("has_trend_context")
    )
    evidence_source_count = sum(
        1 for report in sorted_reports
        if (report.get("quality_evidence") or {}).get("has_evidence_source_coverage")
    )
    manual_hit_count = sum(
        len((report.get("quality_evidence") or {}).get("manual_review_language_hits") or [])
        for report in sorted_reports
    )
    complete_quality_count = sum(
        1 for report in sorted_reports
        if (report.get("quality_evidence") or {}).get("has_complete_quality_gate")
    )
    quality_status = (
        "pass"
        if sorted_reports
        and complete_quality_count == len(sorted_reports)
        and manual_hit_count == 0
        else "needs_attention"
    )
    latest_match = {
        "hero": newest.get("hero") or "未知英雄",
        "match_id": str(newest.get("match_id") or ""),
        "file": newest.get("file") or "index.html",
        "report_generated_at": newest.get("report_generated_at"),
        "source_fetches": _source_fetches_for_report(newest, source_fetch_times),
        "ended_at": newest.get("ended_at"),
        "result": _result_key(newest) if newest else "unknown",
        "review_focus": newest.get("review_focus") or "需要查看报告",
    }
    return {
        "schema_version": 1,
        "source": "generated_public_reports",
        "player_id": "173776719",
        "report_count": len(sorted_reports),
        "finding_count": _count_report_findings(sorted_reports),
        "topic_count": len(trends),
        "high_priority_report_count": sum(1 for report in sorted_reports if report.get("review_priority") == "high"),
        "known_result_count": len(known_results),
        "wins": wins,
        "losses": losses,
        "death_review_workbench_report_count": death_review_workbench_count,
        "death_recovery_window_report_count": death_recovery_window_count,
        "death_coordinate_map_report_count": death_coordinate_map_count,
        "complete_death_review_report_count": complete_death_review_count,
        "quality_gate": {
            "status": quality_status,
            "decision_snapshot_report_count": decision_snapshot_count,
            "trend_context_report_count": trend_context_count,
            "evidence_source_report_count": evidence_source_count,
            "manual_review_language_hit_count": manual_hit_count,
            "complete_quality_report_count": complete_quality_count,
        },
        "source_freshness": _build_source_freshness(sorted_reports, source_fetch_times),
        "report_sources": [
            {
                "file": report.get("file") or "",
                "match_id": str(report.get("match_id") or ""),
                "report_generated_at": report.get("report_generated_at"),
                **_source_fetches_for_report(report, source_fetch_times),
            }
            for report in sorted_reports
        ],
        "latest_match": latest_match,
        "topics": [
            {
                "topic_id": trend.get("topic_id"),
                "focus": trend.get("focus"),
                "page": trend.get("page"),
                "match_count": trend.get("count"),
                "finding_count": trend.get("finding_count"),
            }
            for trend in trends
        ],
    }


def _render_public_time(value, missing_label="时间缺失"):
    if not value:
        return f'<span class="missing-value">{html.escape(missing_label)}</span>'
    label = html.escape(str(value).replace("T", " ").replace("Z", " UTC"))
    return f'<time datetime="{html.escape(str(value), quote=True)}">{label}</time>'


def _render_coverage_panel(manifest):
    latest = manifest.get("latest_match") or {}
    latest_file = html.escape(latest.get("file") or "index.html", quote=True)
    latest_hero = html.escape(latest.get("hero") or "未知英雄")
    latest_match_id = html.escape(str(latest.get("match_id") or ""))
    latest_label = f"{latest_hero} #{latest_match_id}".strip()
    ended_at = latest.get("ended_at")
    if ended_at:
        fallback_time = html.escape(str(ended_at).replace("T", " ").replace("Z", " UTC"))
        latest_time = (
            f'<time class="local-time" datetime="{html.escape(str(ended_at), quote=True)}" '
            f'data-ended-at="{html.escape(str(ended_at), quote=True)}">{fallback_time}</time>'
        )
    else:
        latest_time = '<span class="missing-value">结束时间缺失</span>'
    quality = manifest.get("quality_gate") or {}
    report_count = int(manifest.get("report_count") or 0)
    quality_status = quality.get("status") or "needs_attention"
    quality_status_label = "质量门禁：通过" if quality_status == "pass" else "质量门禁：需检查"
    quality_status_class = "quality-gate-pass" if quality_status == "pass" else "quality-gate-warning"
    manual_hits = int(quality.get("manual_review_language_hit_count") or 0)
    freshness = manifest.get("source_freshness") or {}
    freshness_status = freshness.get("status") or "source_timestamps_missing"
    freshness_status_label = {
        "tracked": "数据源时间：已追踪",
        "partial": "数据源时间：部分追踪",
        "source_timestamps_missing": "数据源时间：未发布",
    }.get(freshness_status, "数据源时间：需检查")
    freshness_status_class = "source-freshness-ok" if freshness_status == "tracked" else "source-freshness-warning"
    latest_report_time = _render_public_time(
        freshness.get("latest_report_generated_at") or latest.get("report_generated_at"),
        "报告时间缺失",
    )
    latest_fetch_time = _render_public_time(freshness.get("latest_external_fetch_at"), "抓取时间缺失")
    freshness_note = html.escape(
        freshness.get("limitation")
        or "公开页展示的是已缓存证据的抓取时间；Cloudflare Pages 发布不会重新访问 STRATZ/OpenDota。"
    )
    return f"""
    <section class="data-coverage" data-coverage-panel aria-label="复盘数据覆盖">
        <div class="history-title-row">
            <h2>复盘数据覆盖</h2>
            <a href="site-manifest.json">查看覆盖 JSON</a>
        </div>
        <div class="coverage-grid">
            <div class="coverage-stat"><strong>{html.escape(str(manifest.get('report_count') or 0))} 场</strong><span>已复盘比赛</span></div>
            <div class="coverage-stat"><strong>{html.escape(str(manifest.get('finding_count') or 0))} 条 finding</strong><span>教练证据</span></div>
            <div class="coverage-stat"><strong>{html.escape(str(manifest.get('topic_count') or 0))} 个训练主题</strong><span>趋势归并</span></div>
            <div class="coverage-stat"><strong>{html.escape(str(manifest.get('high_priority_report_count') or 0))} 局</strong><span>高优先级复盘</span></div>
        </div>
        <div class="coverage-subtitle">死亡复盘覆盖</div>
        <div class="coverage-grid">
            <div class="coverage-stat"><strong>{html.escape(str(manifest.get('death_review_workbench_report_count') or 0))} 局</strong><span>死亡复盘面板</span></div>
            <div class="coverage-stat"><strong>{html.escape(str(manifest.get('death_recovery_window_report_count') or 0))} 局</strong><span>恢复窗口</span></div>
            <div class="coverage-stat"><strong>{html.escape(str(manifest.get('death_coordinate_map_report_count') or 0))} 局</strong><span>坐标图</span></div>
            <div class="coverage-stat"><strong>{html.escape(str(manifest.get('complete_death_review_report_count') or 0))} 局</strong><span>完整死亡复盘</span></div>
        </div>
        <div class="quality-gate-panel" data-quality-gate-panel aria-label="复盘质量门禁">
            <div class="quality-gate-head">
                <span class="quality-gate-status {quality_status_class}">{quality_status_label}</span>
                <strong>复盘质量门禁</strong>
                <small>这些检查来自当前 public 构建，和 CI 发布前验证使用同一批报告。</small>
            </div>
            <div class="coverage-grid quality-gate-grid">
                <div class="coverage-stat"><strong>{html.escape(str(quality.get('decision_snapshot_report_count') or 0))}/{report_count}</strong><span>决策卡覆盖</span></div>
                <div class="coverage-stat"><strong>{html.escape(str(quality.get('trend_context_report_count') or 0))}/{report_count}</strong><span>趋势上下文覆盖</span></div>
                <div class="coverage-stat"><strong>{html.escape(str(quality.get('evidence_source_report_count') or 0))}/{report_count}</strong><span>证据来源覆盖</span></div>
                <div class="coverage-stat"><strong>{manual_hits}</strong><span>手工复盘旧词</span></div>
            </div>
        </div>
        <div class="source-freshness-panel" data-source-freshness-panel aria-label="数据新鲜度">
            <div class="source-freshness-head">
                <span class="source-freshness-status {freshness_status_class}">{freshness_status_label}</span>
                <strong>数据新鲜度</strong>
                <small>{freshness_note}</small>
            </div>
            <div class="coverage-grid source-freshness-grid">
                <div class="coverage-stat"><strong>{latest_report_time}</strong><span>最新报告生成</span></div>
                <div class="coverage-stat"><strong>{html.escape(str(freshness.get('stratz_fetch_timestamp_report_count') or 0))}/{report_count}</strong><span>STRATZ 抓取</span></div>
                <div class="coverage-stat"><strong>{html.escape(str(freshness.get('opendota_fetch_timestamp_report_count') or 0))}/{report_count}</strong><span>OpenDota 抓取</span></div>
                <div class="coverage-stat"><strong>{latest_fetch_time}</strong><span>最新外部抓取</span></div>
            </div>
        </div>
        <a class="coverage-latest" href="{latest_file}">
            <span>最新比赛</span>
            <strong>{latest_label}</strong>
            <small>{latest_time}</small>
        </a>
    </section>
    """.strip()


def _hero_image(slug):
    if not slug:
        return ""
    return f"{HERO_IMAGE_BASE}/{html.escape(slug, quote=True)}.png"


def _render_lineup(label, heroes):
    chips = []
    for hero in heroes:
        name = html.escape(str(hero.get("name") or "未知"))
        image_url = _hero_image(hero.get("slug"))
        image = (
            f'<img src="{image_url}" alt="" loading="lazy" width="34" height="19">'
            if image_url else ""
        )
        chips.append(f'<span class="lineup-hero" title="{name}">{image}<span>{name}</span></span>')
    content = "".join(chips) if chips else '<span class="lineup-missing">阵容数据缺失</span>'
    return f'<div class="lineup-row"><span class="lineup-label">{label}</span><div class="lineup-list">{content}</div></div>'


def _render_coach_note(report):
    priority = html.escape(_priority_label(report.get("review_priority")))
    priority_class = html.escape(str(report.get("review_priority") or "unknown"), quote=True)
    focus = html.escape(report.get("review_focus") or "需要查看报告")
    action = html.escape(report.get("next_action") or "打开报告查看下一局行动清单。")
    metric = html.escape(report.get("success_metric") or "以报告内验收标准为准。")
    return (
        f'<span class="priority-chip {priority_class}">复盘优先级 {priority}</span>'
        f'<strong>{focus}</strong>'
        f'<small>{action}</small>'
        f'<em>验收：{metric}</em>'
    )


def _render_review_queue(reports):
    queue = sorted(reports, key=_priority_rank)[:3]
    cards = []
    for report in queue:
        hero = html.escape(report.get("hero") or "未知英雄")
        file_name = html.escape(report.get("file") or "#", quote=True)
        match_id = html.escape(str(report.get("match_id") or ""))
        if report.get("is_win") is True:
            result = "胜利"
            result_class = "win"
        elif report.get("is_win") is False:
            result = "失败"
            result_class = "lose"
        else:
            result = "待确认"
            result_class = "unknown"
        cards.append(
            f"""
            <a class="review-queue-card" href="{file_name}" data-priority="{html.escape(str(report.get('review_priority') or 'unknown'), quote=True)}">
                <span class="review-queue-meta"><span class="match-result {result_class}">{result}</span><span>{hero} #{match_id}</span></span>
                <span class="review-queue-focus">{_render_coach_note(report)}</span>
            </a>
            """.strip()
        )
    return "".join(cards)


def _render_focus_trends(trends):
    cards = []
    for trend in trends:
        priority = html.escape(_priority_label(trend.get("priority")))
        priority_class = html.escape(str(trend.get("priority") or "unknown"), quote=True)
        focus = html.escape(trend.get("focus") or "需要查看报告")
        count = html.escape(str(trend.get("count") or 0))
        heroes = "、".join(html.escape(hero) for hero in trend.get("heroes", [])[:5])
        action = html.escape(trend.get("next_action") or "打开报告查看下一局行动清单。")
        metric = html.escape(trend.get("success_metric") or "以报告内验收标准为准。")
        source_focuses = trend.get("source_focuses") or []
        topic_page = html.escape(trend.get("page") or "practice-plan.html", quote=True)
        source_note = ""
        if len(source_focuses) > 1:
            labels = "、".join(html.escape(label) for label in source_focuses)
            source_note = f'\n                <p class="trend-sources">归并自 {len(source_focuses)} 种报告标签：{labels}</p>'
        examples = []
        for example in trend.get("examples", []):
            file_name = html.escape(example.get("file") or "#", quote=True)
            hero = html.escape(example.get("hero") or "未知英雄")
            match_id = html.escape(example.get("match_id") or "")
            examples.append(f'<a href="{file_name}">{hero} #{match_id}</a>')
        example_html = " ".join(examples) if examples else '<span class="missing-value">暂无示例</span>'
        cards.append(
            f"""
            <article class="trend-card">
                <div class="trend-card-top">
                    <span class="priority-chip {priority_class}">优先级 {priority}</span>
                    <span>{count} 局出现</span>
                </div>
                <h3><a class="trend-title-link" href="{topic_page}">{focus}</a></h3>
                <p class="trend-heroes">涉及英雄：{heroes or "未知"}</p>{source_note}
                <p>{action}</p>
                <p class="trend-metric">验收：{metric}</p>
                <div class="trend-examples">{example_html}</div>
            </article>
            """.strip()
        )
    if not cards:
        return '<div class="trend-empty">暂无可聚合的复盘趋势。</div>'
    return "".join(cards)


def _render_practice_plan(trends, reports, output_path, manifest=None):
    newest = reports[0] if reports else {}
    manifest = manifest or _build_site_manifest(reports, trends)
    coverage_panel = _render_coverage_panel(manifest)
    cards = []
    for index, trend in enumerate(trends[:5], start=1):
        priority = html.escape(_priority_label(trend.get("priority")))
        priority_class = html.escape(str(trend.get("priority") or "unknown"), quote=True)
        focus = html.escape(trend.get("focus") or "需要查看报告")
        action = html.escape(trend.get("next_action") or "打开报告查看下一局行动清单。")
        metric = html.escape(trend.get("success_metric") or "以报告内验收标准为准。")
        source_focuses = trend.get("source_focuses") or []
        topic_page_raw = trend.get("page") or "index.html"
        topic_page = html.escape(topic_page_raw, quote=True)
        taxonomy_note = (
            f' <span class="taxonomy-note">已归并 {len(source_focuses)} 种等价标签</span>'
            if len(source_focuses) > 1 else ""
        )
        heroes = "、".join(html.escape(hero) for hero in trend.get("heroes", [])[:5])
        evidence_links = _render_practice_evidence_links(trend, topic_page_raw)
        checklist = _render_practice_checklist(trend, index)
        examples = []
        for example in trend.get("examples", [])[:3]:
            file_name = html.escape(example.get("file") or "#", quote=True)
            hero = html.escape(example.get("hero") or "未知英雄")
            match_id = html.escape(example.get("match_id") or "")
            examples.append(f'<a href="{file_name}">{hero} #{match_id}</a>')
        example_html = " ".join(examples) if examples else '<span class="missing-value">暂无样本</span>'
        cards.append(
            f"""
            <article class="practice-card" data-practice-card data-priority="{priority_class}" data-practice-state="todo">
                <div class="practice-rank">第 {index} 优先级</div>
                <div class="practice-main">
                    <div class="practice-title-row">
                        <h2><a class="trend-title-link" href="{topic_page}">{focus}</a></h2>
                        <span class="priority-chip {priority_class}">复盘优先级 {priority}</span>
                    </div>
                    <p class="practice-meta">{html.escape(str(trend.get('count') or 0))} 局出现 · {html.escape(str(trend.get('finding_count') or trend.get('count') or 0))} 条证据 · 涉及英雄：{heroes or "未知"}{taxonomy_note}</p>
                    <div class="practice-action"><strong>下一局动作</strong><span>{action}</span></div>
                    <div class="practice-action"><strong>验收标准</strong><span>{metric}</span></div>
                    {evidence_links}
                    {checklist}
                    <div class="trend-examples">{example_html}</div>
                </div>
            </article>
            """.strip()
        )
    plan_cards = "".join(cards) if cards else '<div class="trend-empty">暂无可生成的训练计划。</div>'
    other_topics = ""
    if len(trends) > 5:
        links = " ".join(
            f'<a href="{html.escape(trend.get("page") or "index.html", quote=True)}">{html.escape(trend.get("focus") or "其他主题")}</a>'
            for trend in trends[5:]
        )
        other_topics = (
            '<nav class="practice-more-topics" aria-label="其他证据主题">'
            '<strong>其他证据主题</strong>'
            f'<span>{links}</span>'
            '</nav>'
        )
    other_topics_block = f"    {other_topics}\n" if other_topics else ""
    newest_link = html.escape(newest.get("file") or "index.html", quote=True)
    plan_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dota 2 下一次训练计划</title>
    <meta name="description" content="根据最近复盘反复问题生成的下一次 Dota 2 天梯训练计划。">
    <link rel="icon" href="data:,">
    <link rel="stylesheet" href="static/style.css">
</head>
<body class="history-page practice-page">
<div class="container history-container">
    <header class="history-header">
        <div>
            <a class="back-link" href="index.html">← 比赛历史</a>
            <div class="history-eyebrow">玩家 173776719</div>
            <h1>下一次训练计划</h1>
            <p>根据最近报告里的反复问题排序。每条只使用报告已有证据、动作和验收标准。</p>
        </div>
        <a class="primary-link" href="{newest_link}">打开最新复盘</a>
        <a class="primary-link secondary-link" href="match-brief.html">赛前执行卡</a>
        <a class="primary-link secondary-link" href="practice-plan.txt">导出训练清单</a>
    </header>
    {coverage_panel}
    <section class="practice-workbench" aria-label="训练任务工作台">
        <div class="practice-workbench-head">
            <div>
                <h2>训练任务工作台</h2>
                <p>先看失败证据，下一局只执行当前主题检查点，赛后再用验收标准复盘。</p>
            </div>
            <strong><span data-practice-visible-count>{len(cards)}</span> / {len(cards)} 项任务</strong>
        </div>
        <div class="practice-filter-row" role="group" aria-label="筛选训练任务">
            <button type="button" class="filter-button active" data-practice-filter="all" aria-pressed="true">全部任务</button>
            <button type="button" class="filter-button" data-practice-filter="high" aria-pressed="false">只看高优先级</button>
            <button type="button" class="filter-button" data-practice-filter="todo" aria-pressed="false">未完成</button>
            <button type="button" class="filter-button" data-practice-filter="done" aria-pressed="false">已完成</button>
        </div>
    </section>
    <main class="practice-list" aria-label="下一次训练计划">
        {plan_cards}
    </main>
    <div class="topic-empty-state" data-practice-empty hidden>
        <strong>没有符合当前筛选的训练任务</strong>
        <span>切回全部任务，或完成更多比赛复盘后重新生成。</span>
    </div>
{other_topics_block}</div>
<script>
(function setupPracticeWorkbench() {{
    const storageKey = 'dota-practice-checks:v1';
    const cards = Array.from(document.querySelectorAll('[data-practice-card]'));
    const checks = Array.from(document.querySelectorAll('[data-practice-check]'));
    const filterButtons = Array.from(document.querySelectorAll('[data-practice-filter]'));
    const countLabel = document.querySelector('[data-practice-visible-count]');
    const emptyState = document.querySelector('[data-practice-empty]');
    const allowedFilters = new Set(['all', 'high', 'todo', 'done']);
    const params = new URLSearchParams(window.location.search);
    let selectedFilter = allowedFilters.has(params.get('practice')) ? params.get('practice') : 'all';

    function readState() {{
        try {{
            return JSON.parse(localStorage.getItem(storageKey) || '{{}}');
        }} catch (error) {{
            return {{}};
        }}
    }}

    function writeState(state) {{
        try {{
            localStorage.setItem(storageKey, JSON.stringify(state));
        }} catch (error) {{
            return;
        }}
    }}

    let checkState = readState();

    function syncPracticeUrl() {{
        const nextParams = new URLSearchParams(window.location.search);
        if (selectedFilter === 'all') {{
            nextParams.delete('practice');
        }} else {{
            nextParams.set('practice', selectedFilter);
        }}
        const nextQuery = nextParams.toString();
        const nextUrl = nextQuery ? `${{window.location.pathname}}?${{nextQuery}}` : window.location.pathname;
        history.replaceState(null, '', nextUrl);
    }}

    function updateCardState(card) {{
        const cardChecks = Array.from(card.querySelectorAll('[data-practice-check]'));
        const done = cardChecks.filter((check) => check.checked).length;
        const total = cardChecks.length;
        const state = total > 0 && done === total ? 'done' : done > 0 ? 'todo' : 'todo';
        card.dataset.practiceState = state;
        const progress = card.querySelector('[data-practice-progress]');
        if (progress) progress.textContent = `${{done}} / ${{total}}`;
    }}

    function cardMatches(card) {{
        if (selectedFilter === 'high') return card.dataset.priority === 'high';
        if (selectedFilter === 'done') return card.dataset.practiceState === 'done';
        if (selectedFilter === 'todo') return card.dataset.practiceState !== 'done';
        return true;
    }}

    function applyPracticeFilter(options = {{}}) {{
        let visible = 0;
        cards.forEach((card) => {{
            updateCardState(card);
            const shouldShow = cardMatches(card);
            card.hidden = !shouldShow;
            if (shouldShow) visible += 1;
        }});
        filterButtons.forEach((button) => {{
            const isActive = button.dataset.practiceFilter === selectedFilter;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-pressed', String(isActive));
        }});
        if (countLabel) countLabel.textContent = String(visible);
        if (emptyState) emptyState.hidden = visible !== 0;
        if (options.syncUrl !== false) syncPracticeUrl();
    }}

    checks.forEach((check) => {{
        const key = check.dataset.practiceCheck;
        check.checked = Boolean(checkState[key]);
        check.addEventListener('change', () => {{
            checkState = readState();
            checkState[key] = check.checked;
            writeState(checkState);
            applyPracticeFilter();
        }});
    }});

    filterButtons.forEach((button) => {{
        button.addEventListener('click', () => {{
            selectedFilter = allowedFilters.has(button.dataset.practiceFilter) ? button.dataset.practiceFilter : 'all';
            applyPracticeFilter();
        }});
    }});

    applyPracticeFilter({{ syncUrl: false }});
}})();
</script>
</body>
</html>
"""
    _write_utf8(output_path, plan_html)


def _render_topic_pages(trends, public_dir):
    for trend in trends:
        focus = html.escape(trend.get("focus") or "需要查看报告")
        topic_links = []
        for topic in trends:
            topic_focus = html.escape(topic.get("focus") or "其他主题")
            topic_page = html.escape(topic.get("page") or "index.html", quote=True)
            topic_count = html.escape(str(topic.get("count") or 0))
            topic_findings = html.escape(str(topic.get("finding_count") or topic.get("count") or 0))
            is_current = topic.get("topic_id") == trend.get("topic_id")
            active_class = " active" if is_current else ""
            current_attr = ' aria-current="page"' if is_current else ""
            topic_links.append(
                f'<a class="topic-switch-link{active_class}" href="{topic_page}"{current_attr}>'
                f'<span>{topic_focus}</span><small>{topic_count} 局 / {topic_findings} 条</small>'
                '</a>'
            )
        findings = trend.get("findings") or []
        match_results = {}
        for index, finding in enumerate(findings):
            match_key = str(finding.get("match_id") or finding.get("file") or index)
            match_results.setdefault(match_key, finding.get("result") or "unknown")
        wins = sum(1 for result in match_results.values() if result == "win")
        losses = sum(1 for result in match_results.values() if result == "lose")
        hero_names = sorted({str(finding.get("hero") or "未知英雄") for finding in findings})
        hero_options = [
            '<option value="all">全部英雄</option>',
            *[
                f'<option value="{html.escape(hero_name, quote=True)}">{html.escape(hero_name)}</option>'
                for hero_name in hero_names
            ],
        ]
        evidence_cards = []
        for finding in findings:
            hero_raw = str(finding.get("hero") or "未知英雄")
            hero = html.escape(hero_raw)
            hero_value = html.escape(hero_raw, quote=True)
            match_id = html.escape(str(finding.get("match_id") or ""))
            file_name = html.escape(finding.get("file") or "index.html", quote=True)
            source_focus = html.escape(finding.get("source_focus") or trend.get("focus") or "需要查看报告")
            evidence = html.escape(finding.get("review_evidence") or "该报告未提供单独证据文本。")
            action = html.escape(finding.get("next_action") or "打开报告查看下一局行动清单。")
            metric = html.escape(finding.get("success_metric") or "以报告内验收标准为准。")
            priority = html.escape(str(finding.get("priority") or "unknown"), quote=True)
            result = finding.get("result")
            result_class = result if result in {"win", "lose"} else "unknown"
            result_text = {"win": "胜利", "lose": "失败"}.get(result, "待确认")
            evidence_cards.append(
                f"""
                <article class="topic-evidence-card" data-topic-evidence-card data-result="{result_class}" data-hero="{hero_value}">
                    <div class="topic-evidence-head">
                        <div>
                            <span class="match-result {result_class}">{result_text}</span>
                            <strong>{hero} #{match_id}</strong>
                        </div>
                        <span class="priority-chip {priority}">优先级 {_priority_label(finding.get('priority'))}</span>
                    </div>
                    <p class="topic-source-label">报告标签：{source_focus}</p>
                    <div class="topic-evidence-line"><strong>证据</strong><span>{evidence}</span></div>
                    <div class="topic-evidence-line"><strong>训练动作</strong><span>{action}</span></div>
                    <div class="topic-evidence-line"><strong>验收标准</strong><span>{metric}</span></div>
                    <a class="topic-report-link" href="{file_name}">打开本局完整复盘</a>
                </article>
                """.strip()
            )
        source_labels = "、".join(html.escape(label) for label in trend.get("source_focuses") or [])
        evidence_html = "".join(evidence_cards) if evidence_cards else '<div class="trend-empty">暂无可展示证据。</div>'
        page_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{focus} - Dota 2 训练主题证据</title>
    <meta name="description" content="玩家 173776719 的 Dota 2 {focus}训练主题完整证据。">
    <link rel="icon" href="data:,">
    <link rel="stylesheet" href="static/style.css">
</head>
<body class="history-page topic-page">
<div class="container history-container">
    <header class="history-header topic-header">
        <div>
            <a class="back-link" href="index.html">&larr; 比赛历史</a>
            <div class="history-eyebrow">训练主题证据档案</div>
            <h1>{focus} · 完整证据</h1>
            <p>逐局列出系统用于归纳这个训练主题的原始报告证据、动作和验收标准。</p>
        </div>
        <a class="primary-link secondary-link" href="practice-plan.html">返回训练计划</a>
    </header>
    <div class="topic-summary" aria-label="主题统计">
        <span><strong>{len(match_results)}</strong> 场相关比赛</span>
        <span><strong>{len(findings)}</strong> 条 finding</span>
        <span class="summary-win"><strong>{wins}</strong> 胜</span>
        <span class="summary-loss"><strong>{losses}</strong> 负</span>
    </div>
    <section class="topic-workbench" aria-label="主题证据工作台">
        <nav class="topic-switcher" aria-label="切换训练主题">
            <strong>训练主题</strong>
            {''.join(topic_links)}
        </nav>
        <div class="topic-workbench-main">
            <div class="topic-controls" aria-label="筛选当前主题证据">
                <div class="topic-count-panel" aria-live="polite">
                    <strong><span data-topic-card-count>{len(findings)}</span> / {len(findings)} 条证据</strong>
                    <span>当前主题：{focus}</span>
                </div>
                <div class="topic-filter-row" role="group" aria-label="按胜负筛选证据">
                    <button type="button" class="topic-filter-button active" data-topic-filter="all" aria-pressed="true">全部证据</button>
                    <button type="button" class="topic-filter-button" data-topic-filter="win" aria-pressed="false">只看胜利</button>
                    <button type="button" class="topic-filter-button" data-topic-filter="lose" aria-pressed="false">只看失败</button>
                    <label class="topic-hero-filter">英雄
                        <select data-topic-hero-filter>
                            {''.join(hero_options)}
                        </select>
                    </label>
                    <button type="button" class="filter-clear-button topic-clear-button" data-topic-clear-filter disabled>清除筛选</button>
                </div>
            </div>
            <section class="topic-provenance">
                <strong>归并标签</strong>
                <span>{source_labels or focus}</span>
            </section>
            <main class="topic-evidence-list" aria-label="{focus}完整证据">
                {evidence_html}
            </main>
            <div class="topic-empty-state" data-topic-empty hidden>
                <strong>没有符合当前筛选的证据</strong>
                <span>切换到全部证据，或查看其他训练主题。</span>
            </div>
        </div>
    </section>
</div>
<script>
(function setupTopicWorkbench() {{
    const filterButtons = Array.from(document.querySelectorAll('[data-topic-filter]'));
    const evidenceCards = Array.from(document.querySelectorAll('[data-topic-evidence-card]'));
    const countLabel = document.querySelector('[data-topic-card-count]');
    const emptyState = document.querySelector('[data-topic-empty]');
    const clearButton = document.querySelector('[data-topic-clear-filter]');
    const heroSelect = document.querySelector('[data-topic-hero-filter]');
    const allowedFilters = new Set(['all', 'win', 'lose']);
    const urlParams = new URLSearchParams(window.location.search);
    let selectedFilter = allowedFilters.has(urlParams.get('result')) ? urlParams.get('result') : 'all';
    const allowedHeroes = new Set(['all', ...Array.from(heroSelect ? heroSelect.options : []).map((option) => option.value)]);
    let selectedHero = allowedHeroes.has(urlParams.get('hero')) ? urlParams.get('hero') : 'all';

    function syncTopicFilterUrl() {{
        const nextParams = new URLSearchParams(window.location.search);
        if (selectedFilter === 'all') {{
            nextParams.delete('result');
        }} else {{
            nextParams.set('result', selectedFilter);
        }}
        if (selectedHero === 'all') {{
            nextParams.delete('hero');
        }} else {{
            nextParams.set('hero', selectedHero);
        }}
        const nextQuery = nextParams.toString();
        const nextUrl = nextQuery ? `${{window.location.pathname}}?${{nextQuery}}` : window.location.pathname;
        history.replaceState(null, '', nextUrl);
    }}

    function applyTopicFilter(selected, options = {{}}) {{
        selectedFilter = allowedFilters.has(selected) ? selected : 'all';
        let visible = 0;
        evidenceCards.forEach((card) => {{
            const matchesResult = selectedFilter === 'all' || card.dataset.result === selectedFilter;
            const matchesHero = selectedHero === 'all' || card.dataset.hero === selectedHero;
            const shouldShow = matchesResult && matchesHero;
            card.hidden = !shouldShow;
            if (shouldShow) visible += 1;
        }});
        filterButtons.forEach((button) => {{
            const isActive = button.dataset.topicFilter === selectedFilter;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-pressed', String(isActive));
        }});
        if (heroSelect) heroSelect.value = selectedHero;
        if (countLabel) countLabel.textContent = String(visible);
        if (emptyState) emptyState.hidden = visible !== 0;
        if (clearButton) clearButton.disabled = selectedFilter === 'all' && selectedHero === 'all';
        if (options.syncUrl !== false) syncTopicFilterUrl();
    }}

    filterButtons.forEach((button) => {{
        button.addEventListener('click', () => applyTopicFilter(button.dataset.topicFilter || 'all'));
    }});
    if (clearButton) {{
        clearButton.addEventListener('click', () => {{
            selectedHero = 'all';
            applyTopicFilter('all');
        }});
    }}
    if (heroSelect) {{
        heroSelect.addEventListener('change', () => {{
            selectedHero = allowedHeroes.has(heroSelect.value) ? heroSelect.value : 'all';
            applyTopicFilter(selectedFilter);
        }});
    }}
    applyTopicFilter(selectedFilter, {{ syncUrl: false }});
}})();
</script>
</body>
</html>
"""
        _write_utf8(public_dir / trend["page"], page_html)


def _write_focus_trends_json(trends, output_path):
    payload = {
        "schema_version": 2,
        "taxonomy_version": 1,
        "generated_from": "report_findings",
        "trends": trends,
    }
    _write_utf8(output_path, json.dumps(payload, ensure_ascii=False, indent=2))


def _write_site_manifest_json(manifest, output_path):
    _write_utf8(output_path, json.dumps(manifest, ensure_ascii=False, indent=2))


REPORT_SECTION_NAV_ITEMS = (
    ("coach-summary", "教练总结", "教练结论"),
    ("next-actions", "下一局行动清单", "下一局"),
    ("match-overview", "比赛概览", "比赛数据"),
    ("timeline-diagnosis", "时间线诊断", "时间线"),
    ("match-events", "死亡/装备事件", "事件"),
    ("review-findings", "本局主要问题证据", "问题证据"),
    ("item-analysis", "出装分析", "出装"),
)

REPORT_SECTION_NAV_SCRIPT = """<script data-report-section-navigation>
(() => {
    const links = Array.from(document.querySelectorAll('[data-report-section-link]'));
    const sections = links.map((link) => document.querySelector(link.getAttribute('href'))).filter(Boolean);
    if (!links.length || !sections.length) return;
    const activate = (sectionId) => {
        let activeLink = null;
        links.forEach((link) => {
            const isActive = link.getAttribute('href') === `#${sectionId}`;
            link.classList.toggle('active', isActive);
            if (isActive) {
                link.setAttribute('aria-current', 'location');
                activeLink = link;
            }
            else link.removeAttribute('aria-current');
        });
        if (activeLink && activeLink.parentElement) {
            const track = activeLink.parentElement;
            const left = activeLink.offsetLeft - ((track.clientWidth - activeLink.offsetWidth) / 2);
            track.scrollTo({ left: Math.max(0, left), behavior: 'auto' });
        }
    };
    links.forEach((link) => link.addEventListener('click', () => activate(link.getAttribute('href').slice(1))));
    window.addEventListener('hashchange', () => {
        if (window.location.hash) activate(window.location.hash.slice(1));
    });
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            const visible = entries.filter((entry) => entry.isIntersecting)
                .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
            if (visible) activate(visible.target.id);
        }, { rootMargin: '-18% 0px -68% 0px', threshold: [0.01, 0.35] });
        sections.forEach((section) => observer.observe(section));
    }
    activate(window.location.hash.slice(1) || sections[0].id);
})();
</script>"""


def _ensure_report_section_navigation(text):
    if 'class="report-section-nav"' in text:
        return text

    available = []
    for section_id, heading, label in REPORT_SECTION_NAV_ITEMS:
        pattern = re.compile(
            rf'(<div class="section(?: [^"]*)?")(\s*>\s*<div class="section-header">[^<]*{re.escape(heading)}</div>)'
        )
        text, replacements = pattern.subn(rf'\1 id="{section_id}"\2', text, count=1)
        if replacements:
            available.append((section_id, label))

    if not available:
        return text

    if 'id="report-top"' not in text:
        if '<div class="header">' in text:
            text = text.replace('<div class="header">', '<div class="header" id="report-top">', 1)
        else:
            text = text.replace('<body>', '<body><span class="report-top-anchor" id="report-top"></span>', 1)

    first_section_id = available[0][0]
    if 'class="skip-link"' not in text:
        text = text.replace('<body>', f'<body><a class="skip-link" href="#{first_section_id}">跳到复盘正文</a>', 1)

    links = ''.join(
        f'<a class="report-section-link" href="#{html.escape(section_id, quote=True)}" data-report-section-link>{html.escape(label)}</a>'
        for section_id, label in available
    )
    navigation = (
        '<nav class="report-section-nav" aria-label="报告章节">'
        '<div class="report-section-nav-track">'
        '<span class="report-section-nav-label">本局复盘</span>'
        f'{links}'
        '<a class="report-top-link" href="#report-top" aria-label="返回报告顶部" title="返回报告顶部">&uarr;</a>'
        '</div></nav>'
    )
    first_section = re.search(r'<div class="section(?: [^"]*)?" id="', text)
    if first_section:
        text = text[:first_section.start()] + navigation + text[first_section.start():]
    text = text.replace('</body>', f'{REPORT_SECTION_NAV_SCRIPT}</body>', 1)
    return text


def _neighbor_result_text(report):
    if report.get("is_win") is True:
        return "胜利"
    if report.get("is_win") is False:
        return "失败"
    return "待确认"


def _render_neighbor_link(label, report):
    if not report:
        return (
            f'<span class="neighbor-card disabled">'
            f'<span class="neighbor-label">{html.escape(label)}</span>'
            f'<strong>没有相邻比赛</strong>'
            f'<small>当前已经是这一侧的边界。</small>'
            f'</span>'
        )
    file_name = html.escape(report.get("file") or "#", quote=True)
    hero = html.escape(report.get("hero") or "未知英雄")
    match_id = html.escape(str(report.get("match_id") or ""))
    result = html.escape(_neighbor_result_text(report))
    focus = html.escape(report.get("review_focus") or "需要查看报告")
    return (
        f'<a class="neighbor-card" href="{file_name}">'
        f'<span class="neighbor-label">{html.escape(label)}</span>'
        f'<strong>{hero} #{match_id}</strong>'
        f'<small>{result} · {focus}</small>'
        f'</a>'
    )


def _render_report_neighbors(current_index, reports):
    newer = reports[current_index - 1] if current_index > 0 else None
    older = reports[current_index + 1] if current_index + 1 < len(reports) else None
    position = f"第 {current_index + 1} / {len(reports)} 场"
    return (
        '<nav class="report-neighbors" aria-label="相邻比赛">'
        '<div class="neighbor-heading">'
        '<span>相邻比赛</span>'
        f'<strong>{html.escape(position)}</strong>'
        '</div>'
        '<div class="neighbor-grid">'
        f'{_render_neighbor_link("上一局（更新）", newer)}'
        f'{_render_neighbor_link("下一局（更早）", older)}'
        '</div>'
        '</nav>'
    )


def _inject_report_navigation(public_dir, reports):
    reports = sorted(reports, key=_report_sort_key, reverse=True)
    for index, report in enumerate(reports):
        path = public_dir / report["file"]
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        text = re.sub(r'\s*<nav class="report-neighbors"[\s\S]*?</nav>', "", text, count=1)
        neighbors = _render_report_neighbors(index, reports)
        context_deck = (
            '<div class="report-context-deck" data-report-context-deck>'
            f'{neighbors}'
            '</div>'
        )
        back_link_match = re.search(r'(<a class="back-link"[\s\S]*?</a>)', text)
        if back_link_match:
            insert_at = back_link_match.end()
            text = text[:insert_at] + "\n" + context_deck + text[insert_at:]
        else:
            text = text.replace("<body>", f"<body>\n{context_deck}", 1)
        text = _ensure_report_section_navigation(text)
        _write_utf8(path, text)


def _render_report_source_provenance(report, source_fetch_times):
    match_id = str(report.get("match_id") or "")
    report_generated_at = report.get("report_generated_at")
    fetches = _source_fetches_for_report(report, source_fetch_times)
    stratz_fetched_at = fetches.get("stratz_fetched_at")
    opendota_fetched_at = fetches.get("opendota_fetched_at")
    source_count = sum(bool(value) for value in (stratz_fetched_at, opendota_fetched_at))
    status_label = "来源完整" if source_count == 2 else ("来源部分可用" if source_count else "来源时间未记录")

    def attribute(name, value):
        return f' {name}="{html.escape(str(value or ""), quote=True)}"'

    return (
        '<details class="report-source-provenance" aria-label="证据时间"'
        ' data-report-source-provenance'
        f'{attribute("data-match-id", match_id)}'
        f'{attribute("data-report-generated-at", report_generated_at)}'
        f'{attribute("data-stratz-fetched-at", stratz_fetched_at)}'
        f'{attribute("data-opendota-fetched-at", opendota_fetched_at)}>'
        '<summary class="source-provenance-summary">'
        '<span>证据时间</span>'
        f'<strong>{html.escape(status_label)}</strong>'
        '<small>展开完整时间</small>'
        '</summary>'
        '<div class="source-provenance-body">'
        '<div class="source-provenance-grid">'
        '<div><span>报告生成</span>'
        f'{_render_public_time(report_generated_at, "未记录")}</div>'
        '<div><span>STRATZ 抓取</span>'
        f'{_render_public_time(stratz_fetched_at, "未记录")}</div>'
        '<div><span>OpenDota 抓取</span>'
        f'{_render_public_time(opendota_fetched_at, "未记录")}</div>'
        '</div>'
        '<small>本报告只使用以上时间点已缓存证据；Cloudflare 发布不会实时重抓比赛数据。</small>'
        '</div>'
        '</details>'
    )


def _evidence_source_counts(evidence_sources):
    total = len(evidence_sources)
    complete = sum(1 for item in evidence_sources if item.get("status") == "available")
    partial = sum(1 for item in evidence_sources if item.get("status") == "partial")
    missing = sum(1 for item in evidence_sources if item.get("status") == "missing")
    usable = complete + partial
    return {
        "total": total,
        "complete": complete,
        "usable": usable,
        "partial": partial,
        "missing": missing,
    }


def _evidence_status_label(status):
    return {
        "available": "完整",
        "partial": "部分",
        "missing": "缺失",
    }.get(status, "待确认")


def _evidence_execution_guidance(counts):
    if counts["total"] <= 0:
        return ("执行信号：", "证据覆盖未记录，先确认本局数据完整性。")
    if counts["missing"] == 0 and counts["partial"] == 0:
        return ("执行信号：", "本局建议由完整证据支撑，可直接按行动清单执行并复核。")
    if counts["missing"] == 0:
        return ("执行信号：", "本局建议可执行；部分证据只按已覆盖范围复核，不扩大归因。")
    return ("执行信号：", "优先执行完整/部分证据对应建议；缺失证据项不作为本局归因。")


def _render_report_evidence_completeness(evidence_sources):
    counts = _evidence_source_counts(evidence_sources)
    if counts["total"] <= 0:
        return ""
    status_class = "complete" if counts["missing"] == 0 and counts["partial"] == 0 else "attention"
    status_label = "证据完整" if status_class == "complete" else "证据有缺口"
    guidance_label, guidance_text = _evidence_execution_guidance(counts)
    attrs = " ".join(
        f'data-evidence-{key}="{html.escape(str(value), quote=True)}"'
        for key, value in counts.items()
    )
    chips = []
    detail_rows = []
    for item in evidence_sources:
        status = item.get("status") or "unknown"
        label = item.get("label") or "未命名证据"
        source = item.get("source") or "来源未记录"
        coverage = item.get("coverage") or "覆盖未记录"
        chips.append(
            f'<span class="evidence-completeness-chip {html.escape(status, quote=True)}">'
            f'{html.escape(label)}<small>{html.escape(_evidence_status_label(status))}</small>'
            '</span>'
        )
        detail_rows.append(
            '<li>'
            f'<strong>{html.escape(label)}</strong>'
            f'<span>{html.escape(source)} · {html.escape(coverage)}</span>'
            '</li>'
        )
    return (
        f'<section class="report-evidence-completeness {status_class}" data-report-evidence-completeness {attrs} '
        'aria-label="本局证据完整度">'
        '<div class="evidence-completeness-summary">'
        '<span>本局证据完整度</span>'
        f'<strong>{counts["complete"]}/{counts["total"]} 类完整</strong>'
        f'<small>可用/部分 {counts["usable"]}/{counts["total"]} · 缺失 {counts["missing"]}</small>'
        '</div>'
        '<div class="evidence-completeness-status">'
        f'<span>{html.escape(status_label)}</span>'
        '</div>'
        '<div class="evidence-completeness-guidance">'
        f'<strong>{html.escape(guidance_label)}</strong>'
        f'<span>{html.escape(guidance_text)}</span>'
        '</div>'
        '<div class="evidence-completeness-chips" aria-label="证据类覆盖">'
        f'{"".join(chips)}'
        '</div>'
        '<details class="evidence-completeness-details">'
        '<summary>查看证据类明细</summary>'
        f'<ul>{"".join(detail_rows)}</ul>'
        '</details>'
        '</section>'
    )


def _inject_report_source_provenance(public_dir, reports, source_fetch_times):
    for report in reports:
        path = public_dir / report["file"]
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r'\s*<(?:section|details) class="report-source-provenance"[\s\S]*?</(?:section|details)>',
            "",
            text,
            count=1,
        )
        provenance = _render_report_source_provenance(report, source_fetch_times)
        neighbors_match = re.search(r'(<nav class="report-neighbors"[\s\S]*?</nav>)', text)
        if neighbors_match:
            insert_at = neighbors_match.end()
            text = text[:insert_at] + "\n" + provenance + text[insert_at:]
        else:
            back_link_match = re.search(r'(<a class="back-link"[\s\S]*?</a>)', text)
            if back_link_match:
                insert_at = back_link_match.end()
                text = text[:insert_at] + "\n" + provenance + text[insert_at:]
            else:
                text = text.replace("<body>", f"<body>\n{provenance}", 1)
        _write_utf8(path, text)


def _inject_report_evidence_completeness(public_dir, reports):
    for report in reports:
        path = public_dir / report["file"]
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r'\s*<section class="[^"]*report-evidence-completeness[^"]*"[\s\S]*?</section>',
            "",
            text,
            count=1,
        )
        evidence_sources = _read_evidence_sources_from_text(text)
        summary = _render_report_evidence_completeness(evidence_sources)
        if not summary:
            _write_utf8(path, text)
            continue
        provenance_match = re.search(r'(<details class="report-source-provenance"[\s\S]*?</details>)', text)
        if provenance_match:
            insert_at = provenance_match.end()
            text = text[:insert_at] + "\n" + summary + text[insert_at:]
        else:
            context_match = re.search(r'(<div class="report-context-deck"[^>]*>)', text)
            if context_match:
                insert_at = context_match.end()
                text = text[:insert_at] + "\n" + summary + text[insert_at:]
            else:
                text = text.replace("<body>", f"<body>\n{summary}", 1)
        _write_utf8(path, text)


def _trend_for_report(report, trends):
    topic_id, _, _ = _classify_focus(report.get("review_focus"))
    for trend in trends:
        if trend.get("topic_id") == topic_id:
            return trend
    return None


def _render_report_trend_context(report, trend, report_count):
    focus = html.escape(trend.get("focus") or report.get("review_focus") or "需要查看报告")
    topic_page = html.escape(trend.get("page") or "review-trends.json", quote=True)
    match_count = int(trend.get("count") or 0)
    finding_count = int(trend.get("finding_count") or 0)
    examples = []
    seen = set()
    for finding in trend.get("findings") or []:
        match_id = str(finding.get("match_id") or "")
        if not match_id or match_id in seen:
            continue
        seen.add(match_id)
        hero = html.escape(finding.get("hero") or "未知英雄")
        file_name = html.escape(finding.get("file") or "#", quote=True)
        examples.append(
            f'<a href="{file_name}">{hero} #{html.escape(match_id)}</a>'
        )
        if len(examples) >= 3:
            break
    examples_html = (
        '<div class="trend-context-examples" aria-label="同类问题样本">'
        + "".join(examples)
        + "</div>"
        if examples else ""
    )
    return (
        '<section class="report-trend-context" aria-label="近期同类问题">'
        '<div class="trend-context-copy">'
        '<span>近期同类问题</span>'
        f'<strong>{focus}</strong>'
        f'<small>最近 {report_count} 场中 {match_count} 场出现；共 {finding_count} 条证据。</small>'
        '</div>'
        f'{examples_html}'
        f'<a class="trend-context-link" href="{topic_page}">完整趋势证据</a>'
        '</section>'
    )


def _inject_report_trend_context(public_dir, reports, trends):
    trend_by_file = {
        report.get("file"): _trend_for_report(report, trends)
        for report in reports
    }
    report_count = len(reports)
    for report in reports:
        trend = trend_by_file.get(report.get("file"))
        if not trend:
            continue
        path = public_dir / report["file"]
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r'\s*<section class="[^"]*report-trend-context[^"]*"[\s\S]*?</section>',
            "",
            text,
            count=1,
        )
        decision_match = re.search(r'(<section[^>]*id="decision-snapshot"[\s\S]*?</section>)', text)
        if not decision_match:
            continue
        insert_at = decision_match.end()
        trend_context = _render_report_trend_context(report, trend, report_count)
        text = text[:insert_at] + "\n" + trend_context + text[insert_at:]
        _write_utf8(path, text)


def _report_sort_key(report):
    ended_at = report.get("ended_at")
    if not ended_at:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _render_index(reports, output_path=None, focus_trends=None, manifest=None):
    output_path = Path(output_path or PUBLIC_DIR / "index.html")
    reports = sorted(reports, key=_report_sort_key, reverse=True)
    newest = reports[0]
    known_results = [report for report in reports if report.get("is_win") is not None]
    wins = sum(1 for report in known_results if report["is_win"])
    losses = len(known_results) - wins
    win_rate = round(wins / len(known_results) * 100) if known_results else 0
    report_rows = []
    high_priority_count = sum(1 for report in reports if report.get("review_priority") == "high")
    focus_trends = focus_trends if focus_trends is not None else _build_focus_trends(reports)
    manifest = manifest or _build_site_manifest(reports, focus_trends)
    coverage_panel = _render_coverage_panel(manifest)

    for report in reports:
        hero_name = html.escape(report["hero"])
        hero_image_url = _hero_image(report.get("hero_slug"))
        hero_image = (
            f'<img class="match-hero-image" src="{hero_image_url}" alt="" loading="lazy" width="96" height="54">'
            if hero_image_url else '<span class="match-hero-placeholder" aria-hidden="true"></span>'
        )
        if report.get("is_win") is True:
            result_class, result_text = "win", "胜利"
        elif report.get("is_win") is False:
            result_class, result_text = "lose", "失败"
        else:
            result_class, result_text = "unknown", "待确认"
        result_key = _result_key(report)

        ended_at = report.get("ended_at")
        if ended_at:
            fallback_time = html.escape(ended_at.replace("T", " ").replace("Z", " UTC"))
            ended_html = (
                f'<time class="local-time" datetime="{html.escape(ended_at, quote=True)}" '
                f'data-ended-at="{html.escape(ended_at, quote=True)}">{fallback_time}</time>'
            )
        else:
            ended_html = '<span class="missing-value">数据缺失</span>'

        kda = report.get("kda") or {}
        kda_text = " / ".join(str(kda.get(key, "-")) for key in ("kills", "deaths", "assists"))
        score = report.get("score") or {}
        score_text = f"{score.get('team', '-')} - {score.get('enemy', '-')}"
        matchup = _render_lineup("我方阵容", report.get("allies")) + _render_lineup("敌方阵容", report.get("enemies"))
        coach_note = _render_coach_note(report)
        priority_key = html.escape(str(report.get("review_priority") or "unknown"), quote=True)
        focus_text = str(report.get("review_focus") or "")
        action_text = str(report.get("next_action") or "")
        search_text = html.escape(" ".join([report["hero"], str(report["match_id"]), focus_text, action_text]), quote=True)
        report_rows.append(
            f"""
            <a class="match-row" role="row" href="{html.escape(report['file'], quote=True)}" aria-label="打开 {hero_name} 比赛 {html.escape(report['match_id'])} 复盘" data-result="{result_key}" data-priority="{priority_key}" data-hero="{hero_name}" data-focus="{html.escape(focus_text, quote=True)}" data-search="{search_text}">
                <span class="match-cell hero-cell" role="cell">{hero_image}<span><strong>{hero_name}</strong><small>#{html.escape(report['match_id'])}</small></span></span>
                <span class="match-cell" role="cell" data-label="结果"><span class="match-result {result_class}">{result_text}</span></span>
                <span class="match-cell time-cell" role="cell" data-label="结束时间">{ended_html}</span>
                <span class="match-cell mono-cell" role="cell" data-label="时长">{_format_duration(report.get('duration_seconds'))}</span>
                <span class="match-cell mono-cell" role="cell" data-label="K / D / A">{html.escape(kda_text)}</span>
                <span class="match-cell mono-cell" role="cell" data-label="比分">{html.escape(score_text)}</span>
                <span class="match-cell coach-cell" role="cell" data-label="本局训练重点">{coach_note}</span>
                <span class="match-cell matchup-cell" role="cell">{matchup}</span>
                <span class="match-open" aria-hidden="true">&#8250;</span>
            </a>
            """.strip()
        )

    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dota 2 天梯复盘历史</title>
    <meta name="description" content="玩家 173776719 的 Dota 2 天梯比赛复盘历史。">
    <link rel="icon" href="data:,">
    <link rel="stylesheet" href="static/style.css">
</head>
<body class="history-page">
<div class="container history-container">
    <header class="history-header">
        <div>
            <div class="history-eyebrow">玩家 173776719</div>
            <h1>Dota 2 比赛复盘</h1>
            <p>按真实比赛结束时间排列，点击任意一局查看证据与下一局行动建议。</p>
        </div>
        <a class="primary-link" href="{html.escape(newest['file'], quote=True)}">打开最新复盘</a>
        <a class="primary-link secondary-link" href="practice-plan.html">下一次训练计划</a>
        <a class="primary-link secondary-link" href="match-brief.html">赛前执行卡</a>
    </header>

    <div class="history-summary" aria-label="历史比赛统计">
        <span><strong>{len(reports)}</strong> 场已复盘</span>
        <span class="summary-win"><strong>{wins}</strong> 胜</span>
        <span class="summary-loss"><strong>{losses}</strong> 负</span>
        <span><strong>{win_rate}%</strong> 胜率</span>
        <span><strong>{high_priority_count}</strong> 局高优先级复盘</span>
    </div>

    {coverage_panel}

    <section class="history-filters" aria-label="筛选比赛">
        <div class="history-filter-header">
            <div>
                <h2>筛选比赛</h2>
                <p>按英雄、比赛号、复盘问题、胜负和优先级快速定位。</p>
            </div>
            <div class="filter-status">
                <span data-match-count>显示 {len(reports)} / {len(reports)} 场</span>
                <button type="button" class="filter-clear-button" data-clear-filters>清除筛选</button>
            </div>
        </div>
        <label class="search-box" for="match-search">
            <span>搜索</span>
            <input id="match-search" type="search" placeholder="英雄、比赛号或问题关键词" autocomplete="off">
        </label>
        <div class="filter-row" aria-label="按胜负筛选">
            <button type="button" class="filter-button active" data-filter-result="all" aria-pressed="true">全部结果</button>
            <button type="button" class="filter-button" data-filter-result="win" aria-pressed="false">只看胜利</button>
            <button type="button" class="filter-button" data-filter-result="lose" aria-pressed="false">只看失败</button>
        </div>
        <div class="filter-row" aria-label="按复盘优先级筛选">
            <button type="button" class="filter-button active" data-filter-priority="all" aria-pressed="true">全部优先级</button>
            <button type="button" class="filter-button" data-filter-priority="high" aria-pressed="false">高优先级</button>
            <button type="button" class="filter-button" data-filter-priority="medium" aria-pressed="false">中优先级</button>
            <button type="button" class="filter-button" data-filter-priority="low" aria-pressed="false">低优先级</button>
        </div>
    </section>

    <section class="review-queue" aria-label="优先复盘队列">
        <div class="history-title-row">
            <h2>优先复盘</h2>
            <span>按报告证据优先级、胜负和死亡成本排序</span>
        </div>
        <div class="review-queue-grid">
            {_render_review_queue(reports)}
        </div>
    </section>

    <section class="trend-board" aria-label="最近反复问题">
        <div class="history-title-row">
            <h2>最近反复问题</h2>
            <a href="review-trends.json">查看结构化数据</a>
        </div>
        <div class="trend-grid">
            {_render_focus_trends(focus_trends)}
        </div>
    </section>

    <main class="history-panel">
        <div class="history-title-row">
            <h2>比赛历史</h2>
            <span>最新比赛优先，每局附带本局训练重点</span>
        </div>
        <div class="match-table" role="table" aria-label="比赛历史列表">
            <div class="match-table-head" role="row">
                <span role="columnheader">英雄 / 比赛</span>
                <span role="columnheader">结果</span>
                <span role="columnheader">结束时间</span>
                <span role="columnheader">时长</span>
                <span role="columnheader">K / D / A</span>
                <span role="columnheader">比分</span>
                <span role="columnheader">本局训练重点</span>
                <span role="columnheader">对阵信息</span>
                <span aria-hidden="true"></span>
            </div>
            {''.join(report_rows)}
        </div>
        <div class="match-empty-state" data-empty-state hidden>
            <strong>没有匹配的比赛</strong>
            <span>换一个英雄、比赛号、复盘问题，或清除胜负/优先级筛选。</span>
        </div>
    </main>
</div>
<script>
document.querySelectorAll('[data-ended-at]').forEach((element) => {{
    const date = new Date(element.dataset.endedAt);
    if (!Number.isNaN(date.getTime())) {{
        element.textContent = new Intl.DateTimeFormat('zh-CN', {{
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', hour12: false
        }}).format(date);
        element.title = `本地时间 ${{element.textContent}}`;
    }}
}});

const filterState = {{ result: 'all', priority: 'all', query: '' }};
const matchRows = Array.from(document.querySelectorAll('.match-row'));
const countLabel = document.querySelector('[data-match-count]');
const searchInput = document.getElementById('match-search');
const emptyState = document.querySelector('[data-empty-state]');
const clearFiltersButton = document.querySelector('[data-clear-filters]');
const urlParams = new URLSearchParams(window.location.search);
const allowedResults = new Set(['all', 'win', 'lose']);
const allowedPriorities = new Set(['all', 'high', 'medium', 'low']);
filterState.result = allowedResults.has(urlParams.get('result')) ? urlParams.get('result') : 'all';
filterState.priority = allowedPriorities.has(urlParams.get('priority')) ? urlParams.get('priority') : 'all';
filterState.query = urlParams.get('q') || '';
if (searchInput) searchInput.value = filterState.query;

function setActiveButton(buttons, selected) {{
    buttons.forEach((button) => {{
        const value = button.dataset.filterResult || button.dataset.filterPriority;
        const isActive = value === selected;
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-pressed', String(isActive));
    }});
}}

function syncFilterUrl() {{
    const nextParams = new URLSearchParams();
    if (filterState.result !== 'all') nextParams.set('result', filterState.result);
    if (filterState.priority !== 'all') nextParams.set('priority', filterState.priority);
    if (filterState.query.trim()) nextParams.set('q', filterState.query.trim());
    const nextQuery = nextParams.toString();
    const nextUrl = nextQuery ? `${{window.location.pathname}}?${{nextQuery}}` : window.location.pathname;
    history.replaceState(null, '', nextUrl);
}}

function applyMatchFilters() {{
    let visible = 0;
    const query = filterState.query.trim().toLowerCase();
    matchRows.forEach((row) => {{
        const matchesResult = filterState.result === 'all' || row.dataset.result === filterState.result;
        const matchesPriority = filterState.priority === 'all' || row.dataset.priority === filterState.priority;
        const matchesQuery = !query || (row.dataset.search || '').toLowerCase().includes(query);
        const shouldShow = matchesResult && matchesPriority && matchesQuery;
        row.hidden = !shouldShow;
        if (shouldShow) visible += 1;
    }});
    if (countLabel) countLabel.textContent = `显示 ${{visible}} / ${{matchRows.length}} 场`;
    if (emptyState) emptyState.hidden = visible !== 0;
    if (clearFiltersButton) {{
        const hasActiveFilter = filterState.result !== 'all' || filterState.priority !== 'all' || Boolean(filterState.query.trim());
        clearFiltersButton.disabled = !hasActiveFilter;
    }}
}}

document.querySelectorAll('[data-filter-result]').forEach((button) => {{
    button.addEventListener('click', () => {{
        filterState.result = button.dataset.filterResult || 'all';
        setActiveButton(document.querySelectorAll('[data-filter-result]'), filterState.result);
        applyMatchFilters();
        syncFilterUrl();
    }});
}});

document.querySelectorAll('[data-filter-priority]').forEach((button) => {{
    button.addEventListener('click', () => {{
        filterState.priority = button.dataset.filterPriority || 'all';
        setActiveButton(document.querySelectorAll('[data-filter-priority]'), filterState.priority);
        applyMatchFilters();
        syncFilterUrl();
    }});
}});

if (searchInput) {{
    searchInput.addEventListener('input', () => {{
        filterState.query = searchInput.value;
        applyMatchFilters();
        syncFilterUrl();
    }});
}}
if (clearFiltersButton) {{
    clearFiltersButton.addEventListener('click', () => {{
        filterState.result = 'all';
        filterState.priority = 'all';
        filterState.query = '';
        if (searchInput) searchInput.value = '';
        setActiveButton(document.querySelectorAll('[data-filter-result]'), filterState.result);
        setActiveButton(document.querySelectorAll('[data-filter-priority]'), filterState.priority);
        applyMatchFilters();
        syncFilterUrl();
    }});
}}
setActiveButton(document.querySelectorAll('[data-filter-result]'), filterState.result);
setActiveButton(document.querySelectorAll('[data-filter-priority]'), filterState.priority);
applyMatchFilters();
</script>
</body>
</html>
"""
    _write_utf8(output_path, index_html)


def build_pages_site(source, public_dir=PUBLIC_DIR, source_fetch_times=None, source_db_path=None):
    source = Path(source)
    public_dir = Path(public_dir)
    if not source.exists():
        raise SystemExit(f"Report source directory does not exist: {source}")

    public_dir.mkdir(parents=True, exist_ok=True)
    for old_report in public_dir.glob("*.html"):
        old_report.unlink()

    _copy_static_assets(public_dir)
    reports = _copy_reports(source, public_dir)
    _inject_report_navigation(public_dir, reports)
    reports = [_parse_report(public_dir / report["file"]) for report in reports]
    if source_fetch_times is None:
        source_fetch_times = _load_source_fetch_times(
            [report.get("match_id") for report in reports],
            source_db_path,
        )
    source_fetch_times = _normalize_source_fetch_times(source_fetch_times or {})
    _inject_report_source_provenance(public_dir, reports, source_fetch_times)
    _inject_report_evidence_completeness(public_dir, reports)
    focus_trends = _build_focus_trends(reports)
    _inject_report_trend_context(public_dir, reports, focus_trends)
    reports = [_parse_report(public_dir / report["file"]) for report in reports]
    site_manifest = _build_site_manifest(reports, focus_trends, source_fetch_times=source_fetch_times)
    _write_focus_trends_json(focus_trends, public_dir / "review-trends.json")
    _write_site_manifest_json(site_manifest, public_dir / "site-manifest.json")
    _render_topic_pages(focus_trends, public_dir)
    _render_practice_plan(
        focus_trends,
        sorted(reports, key=_report_sort_key, reverse=True),
        public_dir / "practice-plan.html",
        manifest=site_manifest,
    )
    _render_match_brief(
        focus_trends,
        sorted(reports, key=_report_sort_key, reverse=True),
        public_dir / "match-brief.html",
        manifest=site_manifest,
    )
    _write_utf8(public_dir / "practice-plan.txt", _render_practice_plan_text(focus_trends, site_manifest))
    _write_utf8(public_dir / "match-brief.txt", _render_match_brief_text(focus_trends, site_manifest))
    _render_index(reports, output_path=public_dir / "index.html", focus_trends=focus_trends, manifest=site_manifest)
    print(f"Built {len(reports)} reports into {public_dir}")


def main():
    parser = argparse.ArgumentParser(description="Build static Cloudflare Pages output from local Dota reports.")
    parser.add_argument("--source", default=os.environ.get("DOTA_REVIEW_REPORT_DIR", str(DEFAULT_SOURCE)))
    parser.add_argument("--source-db", default=os.environ.get("DOTA_REVIEW_DB_PATH", str(SOURCE_DB_PATH)))
    args = parser.parse_args()
    build_pages_site(args.source, source_db_path=args.source_db)


if __name__ == "__main__":
    main()
