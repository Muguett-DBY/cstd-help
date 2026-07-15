import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.normalization import (
    normalize_match_participants,
    normalize_player_match,
    normalize_recent_match,
)
from api.opendota import OpenDotaClient
from config import ACCOUNT_ID


MATCH_LIST_LIMIT = 10
MATCH_LIST_TTL_SECONDS = 60 * 60 * 24 * 30
MATCH_DETAIL_TTL_SECONDS = 60 * 60 * 24 * 90
MATCH_REFRESH_STATUS_TTL_SECONDS = 60 * 60 * 24


class MatchCacheJobError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _utc_iso(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_match_cache_job(
    *,
    account_id=ACCOUNT_ID,
    opendota_client=None,
    now=None,
):
    account_id = int(account_id)
    if account_id != ACCOUNT_ID:
        raise MatchCacheJobError("ACCOUNT_NOT_ALLOWED")
    client = opendota_client or OpenDotaClient()
    recent = client.get_recent_matches(account_id, limit=20, lobby_type=7)
    if not isinstance(recent, list) or not recent:
        raise MatchCacheJobError("MATCH_LIST_UNAVAILABLE")

    matches = []
    for raw_match in recent:
        normalized = normalize_recent_match(raw_match, account_id)
        if normalized and normalized.get("is_ranked"):
            matches.append(normalized)
        if len(matches) >= MATCH_LIST_LIMIT:
            break
    if not matches:
        raise MatchCacheJobError("MATCH_LIST_UNAVAILABLE")

    detail_bulk = []
    parse_preheat_match_ids = []
    for summary in matches:
        match_id = int(summary["match_id"])
        detail = client.get_match(match_id)
        player = normalize_player_match(detail, account_id)
        if not isinstance(detail, dict) or player is None:
            raise MatchCacheJobError(f"MATCH_DETAIL_UNAVAILABLE_{match_id}")
        cached_detail = {
            "match_id": match_id,
            "summary": summary,
            "player": player,
            "participants": normalize_match_participants(detail, account_id),
            "detail": detail,
        }
        detail_bulk.append({
            "key": f"match:v2:{match_id}",
            "value": json.dumps(
                cached_detail,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "expiration_ttl": MATCH_DETAIL_TTL_SECONDS,
        })
        has_parsed_logs = getattr(client, "has_parsed_player_logs", None)
        request_parse = getattr(client, "request_parse", None)
        if callable(has_parsed_logs) and callable(request_parse):
            try:
                if not has_parsed_logs(detail, account_id=account_id):
                    request_parse(match_id)
                    parse_preheat_match_ids.append(match_id)
            except Exception:
                # Match history must remain usable even when an upstream parse queue is busy.
                pass

    refreshed_at = _utc_iso(now)
    match_list = {
        "account_id": account_id,
        "matches": matches,
        "refreshed_at": refreshed_at,
        "source": "github_actions_opendota",
        "stale": False,
        "rate_limited": False,
        "refreshing": False,
    }
    ready_status = {
        "schema_version": 1,
        "account_id": account_id,
        "status": "ready",
        "completed_at": refreshed_at,
        "refreshed_at": refreshed_at,
        "match_count": len(matches),
        "parse_preheat_requested": len(parse_preheat_match_ids),
        "parse_preheat_match_ids": parse_preheat_match_ids,
    }
    detail_bulk.extend([
        {
            "key": f"matches:v1:{account_id}",
            "value": json.dumps(
                match_list,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "expiration_ttl": MATCH_LIST_TTL_SECONDS,
        },
        {
            "key": f"match-refresh-status:v1:{account_id}",
            "value": json.dumps(
                ready_status,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "expiration_ttl": MATCH_REFRESH_STATUS_TTL_SECONDS,
        },
    ])
    return match_list, detail_bulk


def _write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main(argv=None, *, opendota_client=None):
    parser = argparse.ArgumentParser(description="Fetch the fixed account match cache")
    parser.add_argument("--list-output", required=True)
    parser.add_argument("--details-output", required=True)
    parser.add_argument("--status-output", required=True)
    parser.add_argument("--publish-failure-output", required=True)
    args = parser.parse_args(argv)

    output_paths = [Path(args.list_output), Path(args.details_output)]
    for path in output_paths:
        path.unlink(missing_ok=True)
    status = {
        "schema_version": 1,
        "account_id": ACCOUNT_ID,
        "completed_at": _utc_iso(),
    }
    publish_failure = {
        "schema_version": 1,
        "account_id": ACCOUNT_ID,
        "status": "failed",
        "completed_at": _utc_iso(),
        "error_code": "KV_PUBLISH_FAILED",
    }
    exit_code = 0
    try:
        match_list, detail_bulk = run_match_cache_job(
            account_id=ACCOUNT_ID,
            opendota_client=opendota_client,
        )
        _write_json(args.list_output, match_list)
        _write_json(args.details_output, detail_bulk)
        status.clear()
        status.update(json.loads(detail_bulk[-1]["value"]))
    except MatchCacheJobError as exc:
        status.update({"status": "failed", "error_code": exc.code})
        print(f"Match cache job failed: {exc.code}")
        exit_code = 1
    except Exception as exc:
        status.update({"status": "failed", "error_code": "UNEXPECTED_ERROR"})
        print(f"Match cache job failed: {type(exc).__name__}")
        exit_code = 1
    finally:
        if exit_code:
            for path in output_paths:
                path.unlink(missing_ok=True)
        status["completed_at"] = _utc_iso()
        publish_failure["completed_at"] = _utc_iso()
        _write_json(args.status_output, status)
        _write_json(args.publish_failure_output, publish_failure)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
