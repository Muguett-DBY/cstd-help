EVIDENCE_SCHEMA_VERSION = 4
EVIDENCE_TTL_SECONDS = 60 * 60 * 24 * 180
EVIDENCE_STATUS_TTL_SECONDS = 60 * 60 * 24


def review_evidence_gaps(analysis):
    data_quality = (analysis or {}).get("data_quality") or {}
    if isinstance(data_quality.get("blocking_gaps"), list):
        return list(dict.fromkeys(str(item) for item in data_quality["blocking_gaps"] if item))

    timeline = (analysis or {}).get("timeline") or {}
    events = (analysis or {}).get("events") or {}
    gaps = []
    if not timeline.get("available"):
        gaps.append("minute_timeline")

    expected_deaths = int(events.get("death_count_expected") or 0)
    observed_deaths = len(events.get("deaths") or [])
    if expected_deaths > observed_deaths:
        gaps.append("death_timeline")

    if not (events.get("has_purchase_timeline") or events.get("purchases")):
        gaps.append("purchase_timeline")
    return gaps


def evidence_cache_key(match_id):
    return f"review-evidence:v{EVIDENCE_SCHEMA_VERSION}:{int(match_id)}"


def evidence_status_key(match_id):
    return f"review-evidence-status:v{EVIDENCE_SCHEMA_VERSION}:{int(match_id)}"


def evidence_payload_is_ready(payload, match_id):
    if not isinstance(payload, dict):
        return False
    if payload.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        return False
    if int(payload.get("match_id") or 0) != int(match_id):
        return False
    analysis = payload.get("analysis")
    return isinstance(analysis, dict) and not review_evidence_gaps(analysis)
