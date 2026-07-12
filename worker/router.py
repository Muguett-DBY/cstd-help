import re
from dataclasses import dataclass, field

from worker.contracts import ServiceError


MATCH_DETAIL_RE = re.compile(r"^/api/matches/(?P<match_id>[^/]+)$")
REVIEW_STATUS_RE = re.compile(r"^/api/reviews/(?P<match_id>[^/]+)/status$")
REVIEW_RE = re.compile(r"^/api/reviews/(?P<match_id>[^/]+)$")


@dataclass
class ApiResponse:
    status: int
    payload: dict
    headers: dict = field(default_factory=lambda: {
        "Cache-Control": "no-store",
        "Content-Type": "application/json; charset=utf-8",
    })


def _error(status, code, message):
    return ApiResponse(status, {"error": {"code": code, "message": message}})


def _match_id(match):
    value = match.group("match_id")
    if not value.isdigit():
        raise ServiceError("INVALID_MATCH_ID", "比赛ID必须是数字。", 400)
    return int(value)


async def route_request(method, path, service):
    method = str(method or "GET").upper()
    path = str(path or "/")
    try:
        if path == "/api/health":
            if method != "GET":
                return _error(405, "METHOD_NOT_ALLOWED", "该接口不支持此请求方式。")
            return ApiResponse(200, {"status": "ok", "account_id": service.account_id})

        if path == "/api/matches":
            if method != "GET":
                return _error(405, "METHOD_NOT_ALLOWED", "比赛列表只能读取。")
            return ApiResponse(200, await service.get_matches())

        if path == "/api/matches/refresh":
            if method != "POST":
                return _error(405, "METHOD_NOT_ALLOWED", "刷新比赛列表必须由按钮发起。")
            return ApiResponse(200, await service.refresh_matches())

        match = MATCH_DETAIL_RE.fullmatch(path)
        if match:
            if method != "GET":
                return _error(405, "METHOD_NOT_ALLOWED", "对局详情只能读取。")
            return ApiResponse(200, await service.get_match_detail(_match_id(match)))

        match = REVIEW_STATUS_RE.fullmatch(path)
        if match:
            if method != "GET":
                return _error(405, "METHOD_NOT_ALLOWED", "复盘状态只能读取。")
            return ApiResponse(200, await service.review_status(_match_id(match)))

        match = REVIEW_RE.fullmatch(path)
        if match:
            if method != "POST":
                return _error(405, "METHOD_NOT_ALLOWED", "生成复盘必须由分析按钮发起。")
            payload = await service.generate_review(_match_id(match))
            status = 202 if payload.get("status") == "processing" else 200
            return ApiResponse(status, payload)

        return _error(404, "NOT_FOUND", "没有找到这个接口。")
    except ServiceError as exc:
        return ApiResponse(exc.status, exc.as_payload())
    except Exception:
        return _error(500, "INTERNAL_ERROR", "服务暂时无法完成请求，请稍后重试。")
