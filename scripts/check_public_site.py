from html.parser import HTMLParser
from pathlib import Path


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
    style_path = PUBLIC_DIR / "static" / "style.css"
    if not index_path.exists():
        raise SystemExit("public/index.html is missing")
    if not style_path.exists():
        raise SystemExit("public/static/style.css is missing")

    reports = sorted(path for path in PUBLIC_DIR.glob("*.html") if path.name != "index.html")
    if not reports:
        raise SystemExit("public contains no report HTML files")

    index_html = index_path.read_text(encoding="utf-8")
    if "Dota 2 天梯复盘报告" not in index_html:
        raise SystemExit("index page has the wrong title")

    for report in reports:
        text = report.read_text(encoding="utf-8")
        missing = [item for item in REQUIRED_REPORT_TEXT if item not in text]
        if missing:
            raise SystemExit(f"{report.name} is missing required report sections: {', '.join(missing)}")
        title = _title_for(report)
        if not title or title.startswith("复盘报告"):
            raise SystemExit(f"{report.name} title must start with the hero name")

    print(f"Validated {len(reports)} report pages in {PUBLIC_DIR}")


if __name__ == "__main__":
    main()
