import argparse
import html
import os
import re
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"C:\Users\12031\Desktop\REVIEW_REPORT")
PUBLIC_DIR = ROOT / "public"
STATIC_SOURCE = ROOT / "report" / "static"
REPORT_NAME_RE = re.compile(r"^(?P<hero>.+)_(?P<match_id>\d{8,})_(?P<stamp>\d{8}_\d{6})\.html$")


def _display_hero(raw_name):
    return raw_name.replace("_", " ")


def _parse_report(path):
    match = REPORT_NAME_RE.match(path.name)
    if match:
        hero = _display_hero(match.group("hero"))
        match_id = match.group("match_id")
        stamp = match.group("stamp")
        generated_at = datetime.strptime(stamp, "%Y%m%d_%H%M%S")
    else:
        hero = path.stem
        match_id = ""
        generated_at = datetime.fromtimestamp(path.stat().st_mtime)

    return {
        "file": path.name,
        "hero": hero,
        "match_id": match_id,
        "generated_at": generated_at,
        "size": path.stat().st_size,
    }


def _copy_static_assets():
    if STATIC_SOURCE.exists():
        shutil.copytree(STATIC_SOURCE, PUBLIC_DIR / "static", dirs_exist_ok=True)


def _copy_reports(source):
    reports = sorted(source.glob("*.html"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not reports:
        raise SystemExit(f"No HTML reports found in {source}")

    for report in reports:
        shutil.copy2(report, PUBLIC_DIR / report.name)
    return [_parse_report(report) for report in reports]


def _render_index(reports):
    newest = reports[0]
    report_cards = []
    for report in reports:
        date_text = report["generated_at"].strftime("%Y-%m-%d %H:%M")
        report_cards.append(
            f"""
            <a class="report-card" href="{html.escape(report['file'])}">
                <div class="report-hero">{html.escape(report['hero'])}</div>
                <div class="report-meta">比赛ID {html.escape(report['match_id'] or '未知')}</div>
                <div class="report-meta">{html.escape(date_text)}</div>
            </a>
            """.strip()
        )

    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dota 2 天梯复盘报告</title>
    <link rel="icon" href="data:,">
    <link rel="stylesheet" href="static/style.css">
</head>
<body>
<div class="container">
    <div class="header site-header">
        <h1>Dota 2 天梯复盘报告</h1>
        <div class="subtitle">玩家 ID 173776719 | 最新报告：{html.escape(newest['hero'])} | 共 {len(reports)} 份报告</div>
        <a class="primary-link" href="{html.escape(newest['file'])}">打开最新复盘</a>
    </div>

    <div class="section priority-section">
        <div class="section-header">报告列表</div>
        <div class="section-body">
            <div class="report-grid">
                {"".join(report_cards)}
            </div>
        </div>
    </div>
</div>
</body>
</html>
"""
    (PUBLIC_DIR / "index.html").write_text(index_html, encoding="utf-8")


def build_pages_site(source):
    source = Path(source)
    if not source.exists():
        raise SystemExit(f"Report source directory does not exist: {source}")

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    for old_report in PUBLIC_DIR.glob("*.html"):
        old_report.unlink()

    _copy_static_assets()
    reports = _copy_reports(source)
    _render_index(reports)
    print(f"Built {len(reports)} reports into {PUBLIC_DIR}")


def main():
    parser = argparse.ArgumentParser(description="Build static Cloudflare Pages output from local Dota reports.")
    parser.add_argument("--source", default=os.environ.get("DOTA_REVIEW_REPORT_DIR", str(DEFAULT_SOURCE)))
    args = parser.parse_args()
    build_pages_site(args.source)


if __name__ == "__main__":
    main()
