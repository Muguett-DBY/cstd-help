import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.analyzer import analyze_match
from analysis.evidence_contract import EVIDENCE_SCHEMA_VERSION, review_evidence_gaps
from api.opendota import OpenDotaClient
from api.stratz import StratzClient
from config import ACCOUNT_ID, STRATZ_API_KEY


class EvidenceJobError(RuntimeError):
    def __init__(self, code, details=None):
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})


TRANSIENT_EVIDENCE_ERRORS = {
    "OPENDOTA_DETAIL_UNAVAILABLE",
    "STRATZ_UNAVAILABLE",
    "INCOMPLETE_EVIDENCE",
}
DEFAULT_EVIDENCE_ATTEMPTS = 6
DEFAULT_RETRY_SECONDS = 20


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
        raise EvidenceJobError("INCOMPLETE_EVIDENCE", {"blocking_gaps": gaps})

    analysis = dict(analysis)
    analysis["match_id"] = match_id
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "match_id": match_id,
        "generated_at": _utc_iso(now),
        "source": "github_actions_stratz",
        "analysis": analysis,
    }


def run_evidence_job_with_retry(
    match_id,
    *,
    account_id=ACCOUNT_ID,
    opendota_client=None,
    stratz_client=None,
    analyze_fn=analyze_match,
    now=None,
    attempts=DEFAULT_EVIDENCE_ATTEMPTS,
    retry_seconds=DEFAULT_RETRY_SECONDS,
    sleep_fn=time.sleep,
):
    opendota_client = opendota_client or OpenDotaClient()
    stratz_client = stratz_client or StratzClient()
    attempt_limit = max(1, int(attempts))
    wait_seconds = max(0, int(retry_seconds))
    parse_requested = False

    for attempt in range(1, attempt_limit + 1):
        try:
            return run_evidence_job(
                match_id,
                account_id=account_id,
                opendota_client=opendota_client,
                stratz_client=stratz_client,
                analyze_fn=analyze_fn,
                now=now,
            )
        except EvidenceJobError as exc:
            is_transient = exc.code in TRANSIENT_EVIDENCE_ERRORS
            if exc.code == "INCOMPLETE_EVIDENCE" and not parse_requested:
                request_parse = getattr(opendota_client, "request_parse", None)
                if callable(request_parse):
                    try:
                        request_parse(match_id)
                    except Exception:
                        pass
                parse_requested = True
            if not is_transient or attempt >= attempt_limit:
                raise

            gaps = ",".join(exc.details.get("blocking_gaps") or [])
            suffix = f" ({gaps})" if gaps else ""
            print(
                f"Evidence attempt {attempt}/{attempt_limit} returned {exc.code}{suffix}; "
                f"retrying in {wait_seconds}s"
            )
            sleep_fn(wait_seconds)

    raise EvidenceJobError("INCOMPLETE_EVIDENCE")


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
    parser.add_argument("--attempts", type=int, default=DEFAULT_EVIDENCE_ATTEMPTS)
    parser.add_argument("--retry-seconds", type=int, default=DEFAULT_RETRY_SECONDS)
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
        payload = run_evidence_job_with_retry(
            args.match_id,
            attempts=args.attempts,
            retry_seconds=args.retry_seconds,
        )
        _write_json(args.evidence_output, payload)
        status["status"] = "ready"
    except EvidenceJobError as exc:
        status.update({"status": "failed", "error_code": exc.code})
        status.update(exc.details)
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
