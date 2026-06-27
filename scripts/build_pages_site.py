import argparse
import html
import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"C:\Users\12031\Desktop\REVIEW_REPORT")
PUBLIC_DIR = ROOT / "public"
STATIC_SOURCE = ROOT / "report" / "static"
REPORT_NAME_RE = re.compile(r"^(?P<hero>.+)_(?P<match_id>\d{8,})_(?P<stamp>\d{8}_\d{6})\.html$")
HERO_IMAGE_BASE = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes"


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
        self.finding = {}
        self.done = False

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag.lower() == "div" and "finding-card" in classes and not self.in_card:
            self.in_card = True
            self.card_depth = 1
            self.finding["review_priority"] = _priority_from_classes(classes)
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
        if not self.in_card or self.done:
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
                self.done = True

    def handle_data(self, data):
        if self.in_card and self.current_field:
            self.current_parts.append(data)

    def _store_line(self, text):
        if text.startswith("证据:"):
            self.finding.setdefault("review_evidence", text.removeprefix("证据:").strip())
        elif text.startswith("训练目标:"):
            self.finding.setdefault("next_action", text.removeprefix("训练目标:").strip())
        elif text.startswith("验收标准:"):
            self.finding.setdefault("success_metric", text.removeprefix("验收标准:").strip())


def _priority_from_classes(classes):
    for priority in ("high", "medium", "low"):
        if priority in classes:
            return priority
    return "unknown"


def _normalize_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def _display_hero(raw_name):
    return raw_name.replace("_", " ")


def _read_embedded_metadata(path):
    parser = ReportMetadataParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.metadata


def _read_coach_finding(path):
    parser = CoachFindingParser()
    parser.feed(path.read_text(encoding="utf-8"))
    finding = parser.finding
    return {
        "review_focus": finding.get("review_focus") or "需要查看报告",
        "review_evidence": finding.get("review_evidence") or "",
        "next_action": finding.get("next_action") or "打开报告查看下一局行动清单。",
        "success_metric": finding.get("success_metric") or "以报告内验收标准为准。",
        "review_priority": finding.get("review_priority") or "unknown",
    }


def _normalize_lineup(value):
    return [hero for hero in (value or []) if isinstance(hero, dict) and hero.get("name")]


def _parse_report(path):
    match = REPORT_NAME_RE.match(path.name)
    fallback_hero = _display_hero(match.group("hero")) if match else path.stem
    fallback_match_id = match.group("match_id") if match else ""
    metadata = _read_embedded_metadata(path)
    coach_finding = _read_coach_finding(path)
    hero = metadata.get("hero") if isinstance(metadata.get("hero"), dict) else {}
    kda = metadata.get("kda") if isinstance(metadata.get("kda"), dict) else {}
    score = metadata.get("score") if isinstance(metadata.get("score"), dict) else {}

    return {
        "file": path.name,
        "hero": hero.get("name") or fallback_hero,
        "hero_slug": hero.get("slug") or "",
        "match_id": str(metadata.get("match_id") or fallback_match_id),
        "is_win": metadata.get("is_win") if isinstance(metadata.get("is_win"), bool) else None,
        "ended_at": metadata.get("ended_at"),
        "duration_seconds": metadata.get("duration_seconds"),
        "kda": kda,
        "score": score,
        "allies": _normalize_lineup(metadata.get("allies")),
        "enemies": _normalize_lineup(metadata.get("enemies")),
        "size": path.stat().st_size,
        **coach_finding,
    }


def _copy_static_assets(public_dir):
    if STATIC_SOURCE.exists():
        shutil.copytree(STATIC_SOURCE, public_dir / "static", dirs_exist_ok=True)


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


def _build_focus_trends(reports):
    grouped = defaultdict(list)
    for report in reports:
        focus = report.get("review_focus") or "需要查看报告"
        grouped[focus].append(report)

    trends = []
    for focus, items in grouped.items():
        sorted_items = sorted(items, key=_priority_rank)
        priority = sorted_items[0].get("review_priority") or "unknown"
        heroes = sorted({str(item.get("hero") or "未知英雄") for item in sorted_items})
        actions = [item.get("next_action") for item in sorted_items if item.get("next_action")]
        metrics = [item.get("success_metric") for item in sorted_items if item.get("success_metric")]
        examples = [
            {
                "hero": item.get("hero") or "未知英雄",
                "match_id": str(item.get("match_id") or ""),
                "file": item.get("file") or "",
                "result": "win" if item.get("is_win") is True else "lose" if item.get("is_win") is False else "unknown",
            }
            for item in sorted_items[:3]
        ]
        trends.append({
            "focus": focus,
            "count": len(items),
            "priority": priority,
            "heroes": heroes,
            "next_action": actions[0] if actions else "打开报告查看下一局行动清单。",
            "success_metric": metrics[0] if metrics else "以报告内验收标准为准。",
            "examples": examples,
        })

    return sorted(
        trends,
        key=lambda trend: (
            {"high": 0, "medium": 1, "low": 2, "unknown": 3}.get(trend["priority"], 3),
            -trend["count"],
            trend["focus"],
        ),
    )


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
    for trend in trends[:4]:
        priority = html.escape(_priority_label(trend.get("priority")))
        priority_class = html.escape(str(trend.get("priority") or "unknown"), quote=True)
        focus = html.escape(trend.get("focus") or "需要查看报告")
        count = html.escape(str(trend.get("count") or 0))
        heroes = "、".join(html.escape(hero) for hero in trend.get("heroes", [])[:5])
        action = html.escape(trend.get("next_action") or "打开报告查看下一局行动清单。")
        metric = html.escape(trend.get("success_metric") or "以报告内验收标准为准。")
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
                <h3>{focus}</h3>
                <p class="trend-heroes">涉及英雄：{heroes or "未知"}</p>
                <p>{action}</p>
                <p class="trend-metric">验收：{metric}</p>
                <div class="trend-examples">{example_html}</div>
            </article>
            """.strip()
        )
    if not cards:
        return '<div class="trend-empty">暂无可聚合的复盘趋势。</div>'
    return "".join(cards)


def _write_focus_trends_json(trends, output_path):
    payload = {
        "schema_version": 1,
        "generated_from": "report_findings",
        "trends": trends,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
        back_link_match = re.search(r'(<a class="back-link"[\s\S]*?</a>)', text)
        if back_link_match:
            insert_at = back_link_match.end()
            text = text[:insert_at] + "\n" + neighbors + text[insert_at:]
        else:
            text = text.replace("<body>", f"<body>\n{neighbors}", 1)
        path.write_text(text, encoding="utf-8")


def _report_sort_key(report):
    ended_at = report.get("ended_at")
    if not ended_at:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _render_index(reports, output_path=None):
    output_path = Path(output_path or PUBLIC_DIR / "index.html")
    reports = sorted(reports, key=_report_sort_key, reverse=True)
    newest = reports[0]
    known_results = [report for report in reports if report.get("is_win") is not None]
    wins = sum(1 for report in known_results if report["is_win"])
    losses = len(known_results) - wins
    win_rate = round(wins / len(known_results) * 100) if known_results else 0
    report_rows = []
    high_priority_count = sum(1 for report in reports if report.get("review_priority") == "high")
    focus_trends = _build_focus_trends(reports)

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
    </header>

    <div class="history-summary" aria-label="历史比赛统计">
        <span><strong>{len(reports)}</strong> 场已复盘</span>
        <span class="summary-win"><strong>{wins}</strong> 胜</span>
        <span class="summary-loss"><strong>{losses}</strong> 负</span>
        <span><strong>{win_rate}%</strong> 胜率</span>
        <span><strong>{high_priority_count}</strong> 局高优先级复盘</span>
    </div>

    <section class="history-filters" aria-label="筛选比赛">
        <div class="history-filter-header">
            <div>
                <h2>筛选比赛</h2>
                <p>按英雄、比赛号、复盘问题、胜负和优先级快速定位。</p>
            </div>
            <span data-match-count>显示 {len(reports)} / {len(reports)} 场</span>
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

function setActiveButton(buttons, selected) {{
    buttons.forEach((button) => {{
        const value = button.dataset.filterResult || button.dataset.filterPriority;
        const isActive = value === selected;
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-pressed', String(isActive));
    }});
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
}}

document.querySelectorAll('[data-filter-result]').forEach((button) => {{
    button.addEventListener('click', () => {{
        filterState.result = button.dataset.filterResult || 'all';
        setActiveButton(document.querySelectorAll('[data-filter-result]'), filterState.result);
        applyMatchFilters();
    }});
}});

document.querySelectorAll('[data-filter-priority]').forEach((button) => {{
    button.addEventListener('click', () => {{
        filterState.priority = button.dataset.filterPriority || 'all';
        setActiveButton(document.querySelectorAll('[data-filter-priority]'), filterState.priority);
        applyMatchFilters();
    }});
}});

if (searchInput) {{
    searchInput.addEventListener('input', () => {{
        filterState.query = searchInput.value;
        applyMatchFilters();
    }});
}}
</script>
</body>
</html>
"""
    output_path.write_text(index_html, encoding="utf-8")


def build_pages_site(source, public_dir=PUBLIC_DIR):
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
    _write_focus_trends_json(_build_focus_trends(reports), public_dir / "review-trends.json")
    _render_index(reports, output_path=public_dir / "index.html")
    print(f"Built {len(reports)} reports into {public_dir}")


def main():
    parser = argparse.ArgumentParser(description="Build static Cloudflare Pages output from local Dota reports.")
    parser.add_argument("--source", default=os.environ.get("DOTA_REVIEW_REPORT_DIR", str(DEFAULT_SOURCE)))
    args = parser.parse_args()
    build_pages_site(args.source)


if __name__ == "__main__":
    main()
