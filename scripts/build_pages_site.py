import argparse
import html
import json
import os
import re
import shutil
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


def _display_hero(raw_name):
    return raw_name.replace("_", " ")


def _read_embedded_metadata(path):
    parser = ReportMetadataParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.metadata


def _normalize_lineup(value):
    return [hero for hero in (value or []) if isinstance(hero, dict) and hero.get("name")]


def _parse_report(path):
    match = REPORT_NAME_RE.match(path.name)
    fallback_hero = _display_hero(match.group("hero")) if match else path.stem
    fallback_match_id = match.group("match_id") if match else ""
    metadata = _read_embedded_metadata(path)
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
        report_rows.append(
            f"""
            <a class="match-row" role="row" href="{html.escape(report['file'], quote=True)}" aria-label="打开 {hero_name} 比赛 {html.escape(report['match_id'])} 复盘">
                <span class="match-cell hero-cell" role="cell">{hero_image}<span><strong>{hero_name}</strong><small>#{html.escape(report['match_id'])}</small></span></span>
                <span class="match-cell" role="cell" data-label="结果"><span class="match-result {result_class}">{result_text}</span></span>
                <span class="match-cell time-cell" role="cell" data-label="结束时间">{ended_html}</span>
                <span class="match-cell mono-cell" role="cell" data-label="时长">{_format_duration(report.get('duration_seconds'))}</span>
                <span class="match-cell mono-cell" role="cell" data-label="K / D / A">{html.escape(kda_text)}</span>
                <span class="match-cell mono-cell" role="cell" data-label="比分">{html.escape(score_text)}</span>
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
    </div>

    <main class="history-panel">
        <div class="history-title-row">
            <h2>比赛历史</h2>
            <span>最新比赛优先</span>
        </div>
        <div class="match-table" role="table" aria-label="比赛历史列表">
            <div class="match-table-head" role="row">
                <span role="columnheader">英雄 / 比赛</span>
                <span role="columnheader">结果</span>
                <span role="columnheader">结束时间</span>
                <span role="columnheader">时长</span>
                <span role="columnheader">K / D / A</span>
                <span role="columnheader">比分</span>
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
    _render_index(reports, output_path=public_dir / "index.html")
    print(f"Built {len(reports)} reports into {public_dir}")


def main():
    parser = argparse.ArgumentParser(description="Build static Cloudflare Pages output from local Dota reports.")
    parser.add_argument("--source", default=os.environ.get("DOTA_REVIEW_REPORT_DIR", str(DEFAULT_SOURCE)))
    args = parser.parse_args()
    build_pages_site(args.source)


if __name__ == "__main__":
    main()
