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
from api.replay import ReplayEvidenceError, ValveReplayClient
from api.stratz import StratzClient
from config import ACCOUNT_ID


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
REPLAY_REQUIRED_GAPS = {"death_nearby_players"}
TRANSIENT_REPLAY_ERRORS = {
    "REPLAY_URL_MISSING",
    "REPLAY_HTTP_STATUS",
    "REPLAY_DOWNLOAD_INCOMPLETE",
    "REPLAY_ARCHIVE_INVALID",
    "REPLAY_EMPTY",
    "ConnectionError",
    "Timeout",
    "ChunkedEncodingError",
}
DEFAULT_EVIDENCE_ATTEMPTS = 9
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
    replay_client=None,
    analyze_fn=analyze_match,
    now=None,
    allow_replay=False,
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
    analysis = analyze_fn(
        player,
        stratz_data=stratz_data,
        opendota_data=detail,
        replay_data=None,
    )
    if not isinstance(analysis, dict):
        raise EvidenceJobError("ANALYSIS_FAILED")
    gaps = review_evidence_gaps(analysis)
    replay_data = None
    if gaps and (allow_replay or REPLAY_REQUIRED_GAPS.intersection(gaps)):
        replay_client = replay_client or ValveReplayClient()
        try:
            replay_data = replay_client.get_match_evidence(
                match_id,
                account_id,
                detail,
            )
        except ReplayEvidenceError as exc:
            raise EvidenceJobError(
                "REPLAY_FALLBACK_FAILED",
                {
                    "blocking_gaps": gaps,
                    "replay_error": str(exc),
                },
            ) from exc
        except Exception as exc:
            raise EvidenceJobError(
                "REPLAY_FALLBACK_FAILED",
                {
                    "blocking_gaps": gaps,
                    "replay_error": type(exc).__name__,
                },
            ) from exc
        validation = replay_data.get("validation") or {}
        if validation.get("status") == "conflict":
            raise EvidenceJobError(
                "REPLAY_VALIDATION_CONFLICT",
                {
                    "blocking_gaps": gaps,
                    "source_reconciliation": validation,
                },
            )
        analysis = analyze_fn(
            player,
            stratz_data=stratz_data,
            opendota_data=detail,
            replay_data=replay_data,
        )
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
        "source": (
            "github_actions_valve_replay"
            if replay_data else "github_actions_stratz_opendota"
        ),
        "analysis": analysis,
    }


def run_evidence_job_with_retry(
    match_id,
    *,
    account_id=ACCOUNT_ID,
    opendota_client=None,
    stratz_client=None,
    replay_client=None,
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
    opendota_parse_requested = False
    stratz_reparse_requested = False

    for attempt in range(1, attempt_limit + 1):
        try:
            return run_evidence_job(
                match_id,
                account_id=account_id,
                opendota_client=opendota_client,
                stratz_client=stratz_client,
                replay_client=replay_client,
                analyze_fn=analyze_fn,
                now=now,
                allow_replay=attempt == attempt_limit,
            )
        except EvidenceJobError as exc:
            is_transient = (
                exc.code in TRANSIENT_EVIDENCE_ERRORS
                or (
                    exc.code == "REPLAY_FALLBACK_FAILED"
                    and exc.details.get("replay_error") in TRANSIENT_REPLAY_ERRORS
                )
            )
            if exc.code in {
                "INCOMPLETE_EVIDENCE",
                "STRATZ_UNAVAILABLE",
                "OPENDOTA_DETAIL_UNAVAILABLE",
            } and not opendota_parse_requested:
                request_parse = getattr(opendota_client, "request_parse", None)
                if callable(request_parse):
                    try:
                        request_parse(match_id)
                    except Exception:
                        pass
                opendota_parse_requested = True
            if exc.code in {
                "INCOMPLETE_EVIDENCE",
                "STRATZ_UNAVAILABLE",
            } and not stratz_reparse_requested:
                request_reparse = getattr(stratz_client, "request_match_reparse", None)
                if callable(request_reparse):
                    try:
                        request_reparse(match_id)
                    except Exception:
                        pass
                stratz_reparse_requested = True
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
        "started_at": _utc_iso(),
    }
    exit_code = 0
    try:
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
        status["completed_at"] = _utc_iso()
        _write_json(args.status_output, status)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
