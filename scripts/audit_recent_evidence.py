import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.analyzer import analyze_match
from analysis.evidence_contract import review_evidence_gaps
from api.opendota import OpenDotaClient
from api.replay import ReplayEvidenceError, ValveReplayClient
from api.stratz import StratzClient
from config import ACCOUNT_ID, STRATZ_API_KEY


def _audit_error(match_id, code):
    return {
        "match_id": int(match_id),
        "complete": False,
        "error_code": code,
        "quality_score": 0,
        "blocking_gaps": [code.lower()],
        "field_status_counts": {},
    }


def audit_recent_matches(
    *,
    account_id=ACCOUNT_ID,
    limit=10,
    opendota_client=None,
    stratz_client=None,
    replay_client=None,
    analyze_fn=analyze_match,
    allow_replay=True,
):
    opendota_client = opendota_client or OpenDotaClient()
    stratz_client = stratz_client or StratzClient()
    replay_client = replay_client or ValveReplayClient()
    recent = opendota_client.get_recent_matches(
        account_id,
        limit=max(20, int(limit)),
        lobby_type=7,
    )
    matches = [
        item for item in (recent or [])
        if isinstance(item, dict)
        and str(item.get("lobby_type")) == "7"
        and item.get("match_id")
    ][: int(limit)]

    audited = []
    for summary in matches:
        match_id = int(summary["match_id"])
        detail = opendota_client.get_match(match_id)
        if not isinstance(detail, dict):
            audited.append(_audit_error(match_id, "OPENDOTA_DETAIL_UNAVAILABLE"))
            continue
        player = opendota_client.parse_match_for_player(detail, account_id=account_id)
        if not isinstance(player, dict):
            audited.append(_audit_error(match_id, "PLAYER_DETAIL_UNAVAILABLE"))
            continue
        stratz_data = stratz_client.get_match_detail(match_id, include_playback=True)

        try:
            analysis = analyze_fn(
                player,
                stratz_data=stratz_data,
                opendota_data=detail,
                replay_data=None,
            )
        except Exception as exc:
            audited.append(_audit_error(match_id, f"ANALYSIS_{type(exc).__name__.upper()}"))
            continue
        if not isinstance(analysis, dict):
            audited.append(_audit_error(match_id, "ANALYSIS_UNAVAILABLE"))
            continue

        quality = analysis.get("data_quality") or {}
        gaps = review_evidence_gaps(analysis)
        replay_data = None
        if gaps and allow_replay:
            try:
                replay_data = replay_client.get_match_evidence(
                    match_id,
                    account_id,
                    detail,
                )
            except ReplayEvidenceError as exc:
                audited.append(_audit_error(match_id, str(exc)))
                continue
            except Exception as exc:
                audited.append(_audit_error(match_id, f"REPLAY_{type(exc).__name__.upper()}"))
                continue
            if (replay_data.get("validation") or {}).get("status") == "conflict":
                audited.append(_audit_error(match_id, "REPLAY_VALIDATION_CONFLICT"))
                continue
            try:
                analysis = analyze_fn(
                    player,
                    stratz_data=stratz_data,
                    opendota_data=detail,
                    replay_data=replay_data,
                )
            except Exception as exc:
                audited.append(_audit_error(match_id, f"ANALYSIS_{type(exc).__name__.upper()}"))
                continue
            if not isinstance(analysis, dict):
                audited.append(_audit_error(match_id, "ANALYSIS_UNAVAILABLE"))
                continue
            quality = analysis.get("data_quality") or {}

        ledger = quality.get("field_ledger") or []
        gaps = review_evidence_gaps(analysis)
        status_counts = Counter(
            item.get("status") or "unknown"
            for item in ledger
            if isinstance(item, dict)
        )
        audited.append({
            "match_id": match_id,
            "hero_name": analysis.get("hero_name") or "Unknown",
            "role": (analysis.get("role_profile") or {}).get("label") or "未知位置",
            "complete": not gaps,
            "quality_score": quality.get("score"),
            "blocking_gaps": gaps,
            "field_status_counts": dict(sorted(status_counts.items())),
            "fetch_warnings": list(
                stratz_data.get("_fetch_warnings") or []
            ) if isinstance(stratz_data, dict) else ["STRATZ_UNAVAILABLE"],
            "evidence_source": (
                "valve_replay_gem" if replay_data else "stratz_opendota"
            ),
        })

    complete_count = sum(item["complete"] for item in audited)
    return {
        "account_id": int(account_id),
        "requested_limit": int(limit),
        "match_count": len(audited),
        "complete_count": complete_count,
        "all_complete": len(audited) == int(limit) and complete_count == int(limit),
        "matches": audited,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit required STRATZ/OpenDota evidence for recent ranked matches",
    )
    parser.add_argument("--account-id", type=int, default=ACCOUNT_ID)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    if not STRATZ_API_KEY:
        print("STRATZ_API_KEY is unavailable; evidence audit cannot run.")
        return 2
    result = audit_recent_matches(account_id=args.account_id, limit=args.limit)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["matches"]:
            status = "COMPLETE" if item["complete"] else "BLOCKED"
            gaps = ",".join(item["blocking_gaps"]) or "none"
            print(
                f"{item['match_id']} {item.get('hero_name', 'Unknown')} "
                f"{item.get('role', '未知位置')} {status} "
                f"quality={item.get('quality_score')} gaps={gaps}"
            )
        print(
            f"complete={result['complete_count']}/{result['requested_limit']} "
            f"fetched={result['match_count']}"
        )
    return 0 if result["all_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
