import logging
from datetime import datetime, timezone

from analysis.formula_engine import (
    FORMULA_VERSION,
    REVIEW_SCHEMA_VERSION,
    build_formula_review,
)
from analysis.evidence_contract import (
    EVIDENCE_SCHEMA_VERSION,
    evidence_cache_key,
    evidence_payload_is_ready,
    evidence_status_key,
    review_evidence_gaps,
)
from api.normalization import (
    normalize_match_participants,
    normalize_player_match,
    normalize_recent_match,
)
from worker.contracts import ServiceError


logger = logging.getLogger(__name__)


MATCH_LIST_SCHEMA_VERSION = 1
MATCH_DETAIL_SCHEMA_VERSION = 2
MATCH_LIST_LIMIT = 10
REFRESH_COOLDOWN_SECONDS = 60
MATCH_LIST_TTL_SECONDS = 60 * 60 * 24 * 30
MATCH_DETAIL_TTL_SECONDS = 60 * 60 * 24 * 90
MATCH_REFRESH_STATUS_TTL_SECONDS = 60 * 60 * 24
MATCH_REFRESH_PROCESSING_TIMEOUT_SECONDS = 60 * 10
MATCH_REFRESH_RETRY_AFTER_SECONDS = 3
REVIEW_TTL_SECONDS = 60 * 60 * 24 * 180
PARSE_STATE_TTL_SECONDS = 60 * 60 * 6
PARSE_REQUEST_COOLDOWN_SECONDS = 60 * 30
EVIDENCE_REQUEST_COOLDOWN_SECONDS = 60 * 5
REVIEW_RETRY_AFTER_SECONDS = 5
REMOTE_EVIDENCE_WAIT_SECONDS = 90


def _utc_iso(value):
    if isinstance(value, str):
        return value
    if not isinstance(value, datetime):
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_job_id(payload):
    if isinstance(payload, (int, str)):
        return payload
    if not isinstance(payload, dict):
        return None
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    return job.get("jobId") or job.get("id")


class ReviewService:
    def __init__(
        self,
        account_id,
        cache,
        dota_gateway,
        analyzer=None,
        evidence_gateway=None,
        match_refresh_gateway=None,
        prefer_remote_evidence=True,
    ):
        self.account_id = int(account_id)
        self.cache = cache
        self.dota = dota_gateway
        self.analyzer = analyzer
        self.evidence_gateway = evidence_gateway
        self.match_refresh_gateway = match_refresh_gateway
        self.prefer_remote_evidence = bool(prefer_remote_evidence)

    @property
    def match_list_key(self):
        return f"matches:v{MATCH_LIST_SCHEMA_VERSION}:{self.account_id}"

    def match_detail_key(self, match_id):
        return f"match:v{MATCH_DETAIL_SCHEMA_VERSION}:{int(match_id)}"

    @property
    def match_refresh_status_key(self):
        return f"match-refresh-status:v1:{self.account_id}"

    def review_key(self, match_id):
        return f"review:v{REVIEW_SCHEMA_VERSION}:{int(match_id)}"

    def parse_state_key(self, match_id):
        return f"parse:v3:evidence-v{EVIDENCE_SCHEMA_VERSION}:{int(match_id)}"

    def evidence_key(self, match_id):
        return evidence_cache_key(match_id)

    def evidence_status_key(self, match_id):
        return evidence_status_key(match_id)

    def _refresh_is_processing(self, status, now=None):
        if not isinstance(status, dict) or status.get("status") != "processing":
            return False
        requested_at = _parse_utc(status.get("requested_at"))
        if requested_at is None:
            return False
        now = now or datetime.now(timezone.utc)
        return (
            now.astimezone(timezone.utc) - requested_at
        ).total_seconds() < MATCH_REFRESH_PROCESSING_TIMEOUT_SECONDS

    def _cached_match_result(self, cached, refresh_status=None, *, refreshing=False, rate_limited=False):
        if isinstance(cached, dict):
            result = dict(cached)
        else:
            result = {
                "account_id": self.account_id,
                "matches": [],
                "refreshed_at": None,
                "stale": True,
            }
        result["account_id"] = self.account_id
        result["matches"] = list(result.get("matches") or [])[:MATCH_LIST_LIMIT]
        result["source"] = "cache"
        result.setdefault("stale", not bool(result["matches"]))
        result["rate_limited"] = bool(rate_limited)
        result["refreshing"] = bool(refreshing)
        result["refresh_status"] = refresh_status if isinstance(refresh_status, dict) else None
        if refreshing:
            result["retry_after_seconds"] = MATCH_REFRESH_RETRY_AFTER_SECONDS
        return result

    async def get_matches(self):
        cached = await self.cache.get_json(self.match_list_key)
        refresh_status = await self.cache.get_json(self.match_refresh_status_key)
        return self._cached_match_result(
            cached,
            refresh_status,
            refreshing=self._refresh_is_processing(refresh_status),
        )

    async def refresh_matches(self, now=None):
        now = now or datetime.now(timezone.utc)
        cached = await self.cache.get_json(self.match_list_key)
        refresh_status = await self.cache.get_json(self.match_refresh_status_key)
        if self._refresh_is_processing(refresh_status, now):
            return self._cached_match_result(
                cached,
                refresh_status,
                refreshing=True,
                rate_limited=True,
            )
        cached_time = _parse_utc(cached.get("refreshed_at")) if isinstance(cached, dict) else None
        if cached_time and (now.astimezone(timezone.utc) - cached_time).total_seconds() < REFRESH_COOLDOWN_SECONDS:
            return self._cached_match_result(cached, refresh_status, rate_limited=True)

        if self.match_refresh_gateway is not None:
            processing = {
                "status": "processing",
                "requested_at": _utc_iso(now),
                "account_id": self.account_id,
            }
            await self.cache.put_json(
                self.match_refresh_status_key,
                processing,
                expiration_ttl=MATCH_REFRESH_STATUS_TTL_SECONDS,
            )
            try:
                await self.match_refresh_gateway.dispatch()
            except Exception as exc:
                failed = {
                    "status": "failed",
                    "completed_at": _utc_iso(now),
                    "account_id": self.account_id,
                    "error_code": "DISPATCH_FAILED",
                }
                await self.cache.put_json(
                    self.match_refresh_status_key,
                    failed,
                    expiration_ttl=MATCH_REFRESH_STATUS_TTL_SECONDS,
                )
                logger.warning(
                    "Match refresh workflow dispatch failed: %s: %s",
                    type(exc).__name__,
                    exc,
                )
                raise ServiceError(
                    "REFRESH_DISPATCH_FAILED",
                    "比赛同步任务暂时无法启动，请稍后重试。",
                    502,
                ) from exc
            return self._cached_match_result(
                cached,
                processing,
                refreshing=True,
            )

        try:
            raw_matches = await self.dota.recent_ranked_matches(self.account_id, MATCH_LIST_LIMIT * 2)
        except Exception as exc:
            logger.warning(
                "OpenDota recent match refresh failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            raise ServiceError(
                "UPSTREAM_UNAVAILABLE",
                "OpenDota 暂时不可用，已保留上一次比赛列表。",
                502,
            ) from exc
        if not isinstance(raw_matches, list):
            raise ServiceError(
                "UPSTREAM_UNAVAILABLE",
                "OpenDota 没有返回有效比赛列表，已保留上一次数据。",
                502,
            )

        matches = []
        for raw_match in raw_matches:
            normalized = normalize_recent_match(raw_match, self.account_id)
            if normalized and normalized.get("is_ranked"):
                matches.append(normalized)
            if len(matches) >= MATCH_LIST_LIMIT:
                break

        payload = {
            "account_id": self.account_id,
            "matches": matches,
            "refreshed_at": _utc_iso(now),
            "source": "upstream",
            "stale": False,
            "rate_limited": False,
            "refreshing": False,
        }
        await self.cache.put_json(
            self.match_list_key,
            payload,
            expiration_ttl=MATCH_LIST_TTL_SECONDS,
        )
        ready = {
            "status": "ready",
            "completed_at": payload["refreshed_at"],
            "account_id": self.account_id,
        }
        await self.cache.put_json(
            self.match_refresh_status_key,
            ready,
            expiration_ttl=MATCH_REFRESH_STATUS_TTL_SECONDS,
        )
        payload["refresh_status"] = ready
        return payload

    async def get_match_detail(self, match_id, force_refresh=False):
        match_id = int(match_id)
        match_list = await self.get_matches()
        summary = next(
            (item for item in match_list.get("matches", []) if item.get("match_id") == match_id),
            None,
        )
        if summary is None:
            raise ServiceError(
                "MATCH_NOT_IN_RECENT_LIST",
                "这场比赛不在当前最近10局中，请先刷新比赛列表。",
                404,
            )

        cache_key = self.match_detail_key(match_id)
        cached = await self.cache.get_json(cache_key)
        if (
            not force_refresh
            and isinstance(cached, dict)
            and isinstance(cached.get("detail"), dict)
        ):
            result = dict(cached)
            result["source"] = "cache"
            return result

        try:
            detail = await self.dota.match_detail(match_id)
        except Exception as exc:
            raise ServiceError(
                "UPSTREAM_UNAVAILABLE",
                "暂时无法获取这场比赛的完整对阵数据，请稍后重试。",
                502,
            ) from exc
        player = normalize_player_match(detail, self.account_id)
        if player is None:
            raise ServiceError(
                "MATCH_NOT_FOUND",
                "OpenDota 返回的数据中没有找到你的选手记录。",
                404,
            )

        payload = {
            "match_id": match_id,
            "summary": summary,
            "player": player,
            "participants": normalize_match_participants(detail, self.account_id),
            "detail": detail,
        }
        await self.cache.put_json(
            cache_key,
            payload,
            expiration_ttl=MATCH_DETAIL_TTL_SECONDS,
        )
        result = dict(payload)
        result["source"] = "upstream"
        return result

    async def review_status(self, match_id):
        match_id = int(match_id)
        await self._require_recent_match(match_id)
        cached = await self.cache.get_json(self.review_key(match_id))
        if not isinstance(cached, dict):
            return {
                "match_id": match_id,
                "exists": False,
                "generated_at": None,
                "analysis_mode": "deterministic_formula",
                "formula_version": FORMULA_VERSION,
                "schema_version": REVIEW_SCHEMA_VERSION,
            }
        return {
            "match_id": match_id,
            "exists": True,
            "generated_at": cached.get("generated_at"),
            "analysis_mode": cached.get("analysis_mode") or "deterministic_formula",
            "formula_version": cached.get("formula_version") or FORMULA_VERSION,
            "schema_version": REVIEW_SCHEMA_VERSION,
        }

    async def generate_review(self, match_id, now=None):
        match_id = int(match_id)
        now = now or datetime.now(timezone.utc)
        await self._require_recent_match(match_id)
        cache_key = self.review_key(match_id)
        cached = await self.cache.get_json(cache_key)
        ready_evidence = None
        if (
            isinstance(cached, dict)
            and cached.get("evidence_source") != "github_actions_stratz"
        ):
            candidate = await self.cache.get_json(self.evidence_key(match_id))
            if evidence_payload_is_ready(candidate, match_id):
                ready_evidence = candidate
        if (
            isinstance(cached, dict)
            and isinstance(cached.get("analysis"), dict)
            and isinstance(cached.get("guidance"), dict)
            and cached.get("analysis_mode") == "deterministic_formula"
            and cached.get("schema_version") == REVIEW_SCHEMA_VERSION
        ):
            if ready_evidence is None:
                result = dict(cached)
                result["cached"] = True
                return result
        if ready_evidence is not None:
            cached = None

        if self.analyzer is None:
            raise ServiceError("ANALYZER_UNAVAILABLE", "复盘引擎暂时不可用。", 503)
        analysis = cached.get("analysis") if isinstance(cached, dict) else None
        evidence_source = cached.get("evidence_source") if isinstance(cached, dict) else None
        if not isinstance(analysis, dict):
            evidence_payload = ready_evidence or await self.cache.get_json(
                self.evidence_key(match_id)
            )
            if evidence_payload_is_ready(evidence_payload, match_id):
                analysis = evidence_payload["analysis"]
                evidence_source = evidence_payload.get("source") or "github_actions_stratz"
            else:
                parse_state = await self.cache.get_json(self.parse_state_key(match_id))
                evidence_status = await self.cache.get_json(self.evidence_status_key(match_id))
                if self.prefer_remote_evidence and self.evidence_gateway is not None:
                    wait_for_evidence, parse_state = await self._prefer_remote_evidence(
                        match_id,
                        now,
                        parse_state,
                        evidence_status,
                    )
                    if wait_for_evidence:
                        return {
                            "status": "processing",
                            "match_id": match_id,
                            "retry_after_seconds": REVIEW_RETRY_AFTER_SECONDS,
                            "evidence_gaps": ["stratz_enrichment"],
                            "parse_requested": False,
                            "evidence_job_requested": True,
                            "generated": False,
                        }
                detail_payload = await self.get_match_detail(
                    match_id,
                    force_refresh=bool(
                        isinstance(parse_state, dict) and parse_state.get("requested_at")
                    ),
                )
                detail = detail_payload["detail"]
                analysis = self.analyzer.analyze(
                    detail_payload["player"],
                    stratz_data=None,
                    opendota_data=detail,
                )
                if not isinstance(analysis, dict):
                    raise ServiceError("ANALYSIS_FAILED", "复盘引擎没有返回有效结果。", 502)

                evidence_gaps = review_evidence_gaps(analysis)
                if evidence_gaps:
                    parse_state = await self._request_parse_once(match_id, now, parse_state)
                    if not self.prefer_remote_evidence:
                        parse_state = await self._request_evidence_once(match_id, now, parse_state)
                    return {
                        "status": "processing",
                        "match_id": match_id,
                        "retry_after_seconds": REVIEW_RETRY_AFTER_SECONDS,
                        "evidence_gaps": evidence_gaps,
                        "parse_requested": bool(parse_state.get("requested_at")),
                        "evidence_job_requested": bool(parse_state.get("evidence_requested_at")),
                        "generated": False,
                    }
                evidence_source = "opendota_parsed"

            analysis = dict(analysis)

        guidance = build_formula_review(analysis)
        analysis["suggestions"] = [
            {
                "priority": action.get("priority", "low"),
                "category": action.get("category", "review"),
                "message": action.get("action", ""),
                "formula_score": action.get("formula_score"),
            }
            for action in guidance["next_actions"]
        ]
        analysis["formula_diagnostics"] = {
            "formula_version": guidance["formula_version"],
            "overall_score": guidance["overall_score"],
            "overall_equation": guidance["overall_equation"],
            "overall_inputs": guidance["overall_inputs"],
            "scorecards": guidance["scorecards"],
            "unscored_dimensions": guidance["unscored_dimensions"],
        }

        payload = {
            "match_id": match_id,
            "schema_version": REVIEW_SCHEMA_VERSION,
            "generated_at": _utc_iso(now),
            "cached": False,
            "analysis_mode": "deterministic_formula",
            "formula_version": FORMULA_VERSION,
            "evidence_source": evidence_source,
            "analysis": analysis,
            "guidance": guidance,
        }
        await self.cache.put_json(cache_key, payload, expiration_ttl=REVIEW_TTL_SECONDS)
        return payload

    async def _prefer_remote_evidence(self, match_id, now, parse_state=None, evidence_status=None):
        state = dict(parse_state) if isinstance(parse_state, dict) else {}
        requested_at = _parse_utc(state.get("evidence_requested_at"))
        request_age = None
        if requested_at is not None:
            request_age = (now.astimezone(timezone.utc) - requested_at).total_seconds()

        status_is_current = False
        status_value = None
        if isinstance(evidence_status, dict):
            completed_at = _parse_utc(evidence_status.get("completed_at"))
            status_value = evidence_status.get("status")
            status_is_current = bool(
                requested_at is not None
                and completed_at is not None
                and completed_at >= requested_at
                and int(evidence_status.get("match_id") or 0) == int(match_id)
            )

        if status_is_current and status_value == "failed":
            if request_age is not None and request_age >= EVIDENCE_REQUEST_COOLDOWN_SECONDS:
                state = await self._request_evidence_once(match_id, now, state)
                return bool(state.get("evidence_dispatch_accepted")), state
            return False, state
        if requested_at is not None and request_age is not None:
            if request_age < REMOTE_EVIDENCE_WAIT_SECONDS:
                return True, state
            return False, state

        state = await self._request_evidence_once(match_id, now, state)
        return bool(state.get("evidence_dispatch_accepted")), state

    async def _request_parse_once(self, match_id, now, parse_state=None):
        state = dict(parse_state) if isinstance(parse_state, dict) else {}
        requested_at = _parse_utc(state.get("requested_at"))
        if requested_at:
            elapsed = (now.astimezone(timezone.utc) - requested_at).total_seconds()
            if elapsed < PARSE_REQUEST_COOLDOWN_SECONDS:
                return state

        job_payload = None
        if hasattr(self.dota, "request_parse"):
            try:
                job_payload = await self.dota.request_parse(match_id)
            except Exception:
                job_payload = None
        state.update({
            "match_id": int(match_id),
            "requested_at": _utc_iso(now),
            "job_id": _parse_job_id(job_payload),
        })
        await self.cache.put_json(
            self.parse_state_key(match_id),
            state,
            expiration_ttl=PARSE_STATE_TTL_SECONDS,
        )
        return state

    async def _request_evidence_once(self, match_id, now, parse_state=None):
        state = dict(parse_state) if isinstance(parse_state, dict) else {}
        requested_at = _parse_utc(state.get("evidence_requested_at"))
        if requested_at:
            elapsed = (now.astimezone(timezone.utc) - requested_at).total_seconds()
            if elapsed < EVIDENCE_REQUEST_COOLDOWN_SECONDS:
                return state

        accepted = False
        if self.evidence_gateway is not None:
            try:
                result = await self.evidence_gateway.dispatch(match_id)
                accepted = bool((result or {}).get("accepted"))
            except Exception as exc:
                print(f"Evidence workflow dispatch failed: {type(exc).__name__}: {exc}")
        if accepted:
            state["evidence_requested_at"] = _utc_iso(now)
        state["evidence_dispatch_accepted"] = accepted
        await self.cache.put_json(
            self.parse_state_key(match_id),
            state,
            expiration_ttl=PARSE_STATE_TTL_SECONDS,
        )
        return state

    async def _require_recent_match(self, match_id):
        match_list = await self.get_matches()
        summary = next(
            (item for item in match_list.get("matches", []) if item.get("match_id") == int(match_id)),
            None,
        )
        if summary is None:
            raise ServiceError(
                "MATCH_NOT_IN_RECENT_LIST",
                "这场比赛不在当前最近10局中，请先刷新比赛列表。",
                404,
            )
        return summary
