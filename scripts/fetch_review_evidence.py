import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.analyzer import analyze_match
from analysis.coach_contract import select_coaching_findings
from analysis.evidence_contract import EVIDENCE_SCHEMA_VERSION, review_evidence_gaps
from api.opendota import OpenDotaClient
from api.stratz import StratzClient
from config import ACCOUNT_ID, STRATZ_API_KEY


class EvidenceJobError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _utc_iso(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_evidence_job(
    match_id,
    *,
    account_id=ACCOUNT_ID,
    opendota_client=None,
    stratz_client=None,
    analyze_fn=analyze_match,
    now=None,
):
    match_id = int(match_id)
    opendota_client = opendota_client or OpenDotaClient()
    stratz_client = stratz_client or StratzClient()
    recent = opendota_client.get_recent_matches(account_id, limit=20, lobby_type=7)
    ranked_ids = [
        int(match["match_id"])
        for match in recent or []
        if isinstance(match, dict) and str(match.get("lobby_type")) == "7" and match.get("match_id")
    ][:10]
    if match_id not in ranked_ids:
        raise EvidenceJobError("MATCH_NOT_RECENT")

    detail = opendota_client.get_match(match_id)
    player = opendota_client.parse_match_for_player(detail, account_id=account_id) if detail else None
    if not player:
        raise EvidenceJobError("OPENDOTA_DETAIL_UNAVAILABLE")

    stratz_data = stratz_client.get_match_detail(match_id, include_playback=True)
    if not stratz_data:
        raise EvidenceJobError("STRATZ_UNAVAILABLE")
    analysis = analyze_fn(player, stratz_data=stratz_data, opendota_data=detail)
    if not isinstance(analysis, dict):
        raise EvidenceJobError("ANALYSIS_FAILED")
    gaps = review_evidence_gaps(analysis)
    if gaps:
        raise EvidenceJobError("INCOMPLETE_EVIDENCE")

    analysis = dict(analysis)
    analysis["match_id"] = match_id
    analysis["review_findings"] = select_coaching_findings(analysis)
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "match_id": match_id,
        "generated_at": _utc_iso(now),
        "source": "github_actions_stratz",
        "analysis": analysis,
    }


def _write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fetch one complete review evidence package")
    parser.add_argument("--match-id", required=True, type=int)
    parser.add_argument("--evidence-output", required=True)
    parser.add_argument("--status-output", required=True)
    args = parser.parse_args(argv)
    Path(args.evidence_output).unlink(missing_ok=True)
    status = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "match_id": args.match_id,
        "completed_at": _utc_iso(),
    }
    exit_code = 0
    try:
        if not STRATZ_API_KEY:
            raise EvidenceJobError("STRATZ_SECRET_MISSING")
        payload = run_evidence_job(args.match_id)
        _write_json(args.evidence_output, payload)
        status["status"] = "ready"
    except EvidenceJobError as exc:
        status.update({"status": "failed", "error_code": exc.code})
        print(f"Evidence job failed: {exc.code}")
        exit_code = 1
    except Exception as exc:
        status.update({"status": "failed", "error_code": "UNEXPECTED_ERROR"})
        print(f"Evidence job failed: {type(exc).__name__}")
        exit_code = 1
    finally:
        _write_json(args.status_output, status)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
