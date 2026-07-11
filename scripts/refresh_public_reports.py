import argparse
import json
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.ai_analyst import analyze_with_ai
from analysis.analyzer import analyze_match, get_hero_name
from analysis.d2pt import get_hero_build
from api.opendota import OpenDotaClient
from api.stratz import StratzClient
from config import ACCOUNT_ID
from report.generator import generate_report
from scripts.build_pages_site import CANONICAL_REPORT_NAME_RE, build_pages_site


PUBLIC_DIR = ROOT / "public"
REQUIRED_FINDING_FIELDS = ("evidence", "action", "replay_check")


@dataclass
class RefreshResult:
    discovered: int = 0
    missing: int = 0
    requested_parse: int = 0
    ready: int = 0
    generated: int = 0
    deferred: int = 0
    skipped: int = 0
    changed: bool = False
    latest_match_id: str = ""
    report_files: tuple = ()


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_report_paths(public_dir):
    public_dir = Path(public_dir)
    return sorted(
        path for path in public_dir.glob("*.html")
        if CANONICAL_REPORT_NAME_RE.match(path.name)
    )


def _published_match_ids(public_dir):
    return {
        match.group("match_id")
        for path in _canonical_report_paths(public_dir)
        if (match := CANONICAL_REPORT_NAME_RE.match(path.name))
    }


def _timeline_evidence_status(analysis):
    sources = ((analysis or {}).get("data_quality") or {}).get("evidence_sources") or []
    if isinstance(sources, dict):
        item = sources.get("timeline") or {}
        return item.get("status")
    for item in sources:
        if isinstance(item, dict) and item.get("id") == "timeline":
            return item.get("status")
    return None


def analysis_is_publishable(analysis):
    if _timeline_evidence_status(analysis) not in {"available", "partial"}:
        return False
    findings = (analysis or {}).get("review_findings") or []
    if not findings:
        return False
    return all(
        isinstance(finding, dict)
        and all(str(finding.get(field) or "").strip() for field in REQUIRED_FINDING_FIELDS)
        for finding in findings
    )


def _ranked_recent_matches(matches, lobby_type):
    ranked = []
    seen = set()
    for match in matches or []:
        if not isinstance(match, dict) or str(match.get("lobby_type")) != str(lobby_type):
            continue
        match_id = match.get("match_id")
        if match_id is None or str(match_id) in seen:
            continue
        seen.add(str(match_id))
        ranked.append(match)
    return ranked


def _stratz_data_for_match(client, match_id):
    if client is None:
        return None, None
    detail = client.get_match_detail(match_id, include_playback=True)
    if detail:
        return detail, _utc_now()
    warning = getattr(client, "last_warning", None)
    if warning:
        return {"players": [], "_fetch_warnings": [warning]}, None
    return None, None


def _copy_existing_reports(public_dir, source_dir):
    copied = []
    for path in _canonical_report_paths(public_dir):
        target = Path(source_dir) / path.name
        shutil.copy2(path, target)
        copied.append(target)
    return copied


def refresh_public_reports(
    public_dir=PUBLIC_DIR,
    recent_limit=50,
    max_new=25,
    parse_wait=180,
    ranked_lobby_type=7,
    dry_run=False,
    use_stratz=True,
    use_d2pt=True,
    account_id=ACCOUNT_ID,
    opendota_client=None,
    stratz_client=None,
    analyze_fn=analyze_match,
    ai_fn=analyze_with_ai,
    report_fn=generate_report,
    build_fn=build_pages_site,
    d2pt_fn=get_hero_build,
    sleep_fn=time.sleep,
):
    public_dir = Path(public_dir)
    public_dir.mkdir(parents=True, exist_ok=True)
    opendota_client = opendota_client or OpenDotaClient()
    if use_stratz and stratz_client is None:
        stratz_client = StratzClient()

    recent = opendota_client.get_recent_matches(
        account_id,
        limit=recent_limit,
        lobby_type=ranked_lobby_type,
    )
    ranked = _ranked_recent_matches(recent, ranked_lobby_type)
    published_ids = _published_match_ids(public_dir)
    missing_matches = [match for match in ranked if str(match.get("match_id")) not in published_ids]
    selected = missing_matches[:max(0, max_new)]
    result = RefreshResult(
        discovered=len(ranked),
        missing=len(missing_matches),
        skipped=max(0, len(missing_matches) - len(selected)),
        latest_match_id=str(ranked[0].get("match_id")) if ranked else "",
    )
    if not selected:
        return result

    details = {}
    opendota_fetch_times = {}
    parse_ids = []
    for match in selected:
        match_id = int(match["match_id"])
        detail = opendota_client.get_match(match_id)
        if detail:
            details[match_id] = detail
            opendota_fetch_times[match_id] = _utc_now()
        if not detail or not opendota_client.has_minute_player_logs(detail, account_id=account_id):
            if not dry_run and opendota_client.request_parse(match_id):
                parse_ids.append(match_id)

    result.requested_parse = len(parse_ids)
    if parse_ids and parse_wait > 0:
        sleep_fn(parse_wait)
        for match_id in parse_ids:
            detail = opendota_client.get_match(match_id)
            if detail:
                details[match_id] = detail
                opendota_fetch_times[match_id] = _utc_now()

    if dry_run:
        result.ready = sum(
            1 for match_id in (int(match["match_id"]) for match in selected)
            if opendota_client.has_minute_player_logs(details.get(match_id), account_id=account_id)
        )
        result.deferred = len(selected) - result.ready
        return result

    analyses = []
    d2pt_cache = {}
    for match in selected:
        match_id = int(match["match_id"])
        detail = details.get(match_id)
        match_data = opendota_client.parse_match_for_player(detail, account_id=account_id) if detail else None
        if not match_data:
            result.deferred += 1
            continue

        stratz_data = None
        stratz_fetched_at = None
        if use_stratz:
            stratz_data, stratz_fetched_at = _stratz_data_for_match(stratz_client, match_id)

        d2pt_data = None
        if use_d2pt:
            hero_name = get_hero_name(match_data.get("hero_id"))
            if hero_name not in d2pt_cache:
                try:
                    d2pt_cache[hero_name] = d2pt_fn(hero_name)
                except Exception as exc:
                    print(f"  D2PT fetch error for {hero_name}: {exc}")
                    d2pt_cache[hero_name] = None
            d2pt_data = d2pt_cache[hero_name]

        try:
            analysis = analyze_fn(
                match_data,
                stratz_data=stratz_data,
                opendota_data=detail,
                d2pt_data=d2pt_data,
            )
        except Exception as exc:
            print(f"  Analysis failed for match {match_id}: {exc}")
            result.deferred += 1
            continue
        analysis["match_id"] = match_id
        if not analysis_is_publishable(analysis):
            result.deferred += 1
            continue
        source_fetches = {"opendota_fetched_at": opendota_fetch_times.get(match_id)}
        if stratz_fetched_at:
            source_fetches["stratz_fetched_at"] = stratz_fetched_at
        source_fetches = {key: value for key, value in source_fetches.items() if value}
        analyses.append((analysis, source_fetches))

    result.ready = len(analyses)
    if not analyses:
        return result

    report_files = []
    with tempfile.TemporaryDirectory(prefix="dota-report-refresh-") as source:
        source_dir = Path(source)
        _copy_existing_reports(public_dir, source_dir)
        for analysis, source_fetches in analyses:
            try:
                coach = ai_fn(
                    analysis,
                    analysis.get("hero_name") or "Unknown",
                    bool(analysis.get("is_win")),
                )
                report_path = report_fn(
                    analysis,
                    coach,
                    output_dir=source_dir,
                    source_fetches=source_fetches,
                )
            except Exception as exc:
                print(f"  Report generation failed for match {analysis.get('match_id')}: {exc}")
                result.deferred += 1
                continue
            report_files.append(Path(report_path).name)

        if report_files:
            build_fn(source_dir, public_dir=public_dir)

    result.generated = len(report_files)
    result.changed = bool(report_files)
    result.report_files = tuple(report_files)
    return result


def _build_parser():
    parser = argparse.ArgumentParser(description="Refresh evidence-ready Dota reports in public/")
    parser.add_argument("--public-dir", default=str(PUBLIC_DIR))
    parser.add_argument("--recent", type=int, default=50)
    parser.add_argument("--max-new", type=int, default=25)
    parser.add_argument("--parse-wait", type=int, default=180)
    parser.add_argument("--ranked-lobby-type", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-stratz", action="store_true")
    parser.add_argument("--no-d2pt", action="store_true")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    result = refresh_public_reports(
        public_dir=args.public_dir,
        recent_limit=args.recent,
        max_new=args.max_new,
        parse_wait=max(0, args.parse_wait),
        ranked_lobby_type=args.ranked_lobby_type,
        dry_run=args.dry_run,
        use_stratz=not args.no_stratz,
        use_d2pt=not args.no_d2pt,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
