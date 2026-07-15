import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_pages_site import (
    CANONICAL_REPORT_NAME_RE,
    REPORT_NAME_RE,
    _parse_report,
    _report_sort_key,
)


WEB_DIR = ROOT / "web"
PUBLIC_DIR = ROOT / "public"
ASSET_VERSION_PLACEHOLDER = "__ASSET_VERSION__"
VERSIONED_ASSET_PATHS = (
    Path("static/workbench.css"),
    Path("static/shared.js"),
    Path("static/history.js"),
    Path("static/match.js"),
)


def _asset_version(web_dir):
    digest = hashlib.sha256()
    for relative_path in VERSIONED_ASSET_PATHS:
        digest.update(relative_path.as_posix().encode("ascii"))
        digest.update((Path(web_dir) / relative_path).read_bytes())
    return digest.hexdigest()[:12]


def _write_versioned_text(source, destination, asset_version):
    text = Path(source).read_text(encoding="utf-8")
    destination.write_text(
        text.replace(ASSET_VERSION_PLACEHOLDER, asset_version),
        encoding="utf-8",
        newline="",
    )


def _int_or_none(value):
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _seed_match(report):
    kda = report.get("kda") if isinstance(report.get("kda"), dict) else {}
    return {
        "match_id": int(report["match_id"]),
        "account_id": 173776719,
        "hero": {
            "id": report.get("hero_id"),
            "name": report.get("hero") or "未知英雄",
            "slug": report.get("hero_slug") or "",
        },
        "side": None,
        "is_win": report.get("is_win"),
        "ended_at": report.get("ended_at"),
        "duration_seconds": _int_or_none(report.get("duration_seconds")),
        "kda": {
            "kills": _int_or_none(kda.get("kills")),
            "deaths": _int_or_none(kda.get("deaths")),
            "assists": _int_or_none(kda.get("assists")),
        },
        "rank_tier": None,
        "lane": None,
        "lane_role": None,
        "is_ranked": True,
        "legacy_report": report.get("file"),
    }


def _load_seed_reports(report_dir):
    reports = []
    for path in Path(report_dir).glob("*.html"):
        if not (CANONICAL_REPORT_NAME_RE.match(path.name) or REPORT_NAME_RE.match(path.name)):
            continue
        report = _parse_report(path)
        if report.get("match_id") and report.get("ended_at"):
            reports.append(report)
    return sorted(reports, key=_report_sort_key, reverse=True)


def build_workbench_site(public_dir=PUBLIC_DIR, web_dir=WEB_DIR, report_dir=None):
    public_dir = Path(public_dir)
    web_dir = Path(web_dir)
    report_dir = Path(report_dir or public_dir)
    reports = _load_seed_reports(report_dir)
    matches = [_seed_match(report) for report in reports[:10]]

    required = (
        web_dir / "_headers",
        web_dir / "favicon.svg",
        web_dir / "index.html",
        web_dir / "match.html",
        web_dir / "static" / "workbench.css",
        web_dir / "static" / "shared.js",
        web_dir / "static" / "history.js",
        web_dir / "static" / "match.js",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Workbench source asset missing: {', '.join(missing)}")

    asset_version = _asset_version(web_dir)
    public_dir.mkdir(parents=True, exist_ok=True)
    static_dir = public_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    _write_versioned_text(
        web_dir / "index.html",
        public_dir / "index.html",
        asset_version,
    )
    _write_versioned_text(
        web_dir / "match.html",
        public_dir / "match.html",
        asset_version,
    )
    shutil.copy2(web_dir / "favicon.svg", public_dir / "favicon.svg")
    shutil.copy2(web_dir / "_headers", public_dir / "_headers")
    for source in (web_dir / "static").iterdir():
        if source.is_file():
            destination = static_dir / source.name
            if source.name in {"history.js", "match.js"}:
                _write_versioned_text(source, destination, asset_version)
            else:
                shutil.copy2(source, destination)

    latest = reports[0] if reports else {}
    payload = {
        "schema_version": 1,
        "account_id": 173776719,
        "source": "static_seed",
        "stale": True,
        "refreshed_at": latest.get("report_generated_at") or latest.get("ended_at"),
        "matches": matches,
    }
    (public_dir / "matches.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the static personal review workbench")
    parser.add_argument("--public-dir", type=Path, default=PUBLIC_DIR)
    parser.add_argument("--web-dir", type=Path, default=WEB_DIR)
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    result = build_workbench_site(args.public_dir, args.web_dir, args.report_dir)
    print(f"Workbench ready: {len(result['matches'])} seeded matches")
