import json
from urllib.parse import urlencode

from analysis.analyzer import analyze_match


OPENDOTA_BASE_URL = "https://api.opendota.com/api"
STRATZ_GRAPHQL_URL = "https://api.stratz.com/graphql"
GITHUB_API_URL = "https://api.github.com"


STRATZ_CORE_QUERY = """
query GetMatchDetail($matchId: Long!) {
  match(id: $matchId) {
    id durationSeconds didRadiantWin startDateTime radiantKills direKills
    players {
      isRadiant steamAccount { id } hero { id displayName }
      kills deaths assists networth goldPerMinute experiencePerMinute
      heroDamage towerDamage heroHealing numLastHits numDenies level gold goldSpent
      position lane role abilities { abilityId time level }
      item0Id item1Id item2Id item3Id item4Id item5Id neutral0Id
      stats {
        lastHitsPerMinute goldPerMinute experiencePerMinute
        heroDamagePerMinute towerDamagePerMinute deniesPerMinute
      }
    }
  }
}
""".strip()


STRATZ_PLAYBACK_QUERY = """
query GetMatchPlayback($matchId: Long!) {
  match(id: $matchId) {
    id
    players {
      playerSlot steamAccount { id } hero { id } isRadiant
      playbackData {
        purchaseEvents { time itemId }
        deathEvents { time }
        killEvents { time }
        assistEvents { time }
        csEvents { time }
        goldEvents { time }
        inventoryEvents { time }
        playerUpdatePositionEvents { time x y }
      }
    }
  }
}
""".strip()


def parse_ai_output(output):
    if isinstance(output, dict):
        return output
    if not isinstance(output, str):
        raise ValueError("Workers AI output must be JSON text")
    text = output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in ("```", "```json"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Workers AI output must be a JSON object")
    return payload


def _coerce_js_value(value):
    if isinstance(value, (str, dict, list)):
        return value
    to_py = getattr(value, "to_py", None)
    if callable(to_py):
        try:
            return to_py()
        except Exception:
            return value
    return value


def _to_js_request(value):
    try:
        from js import Object
        from pyodide.ffi import to_js
    except (ImportError, ModuleNotFoundError):
        return value
    return to_js(value, dict_converter=Object.fromEntries)


def _extract_ai_output(response, depth=0):
    converted = _coerce_js_value(response)

    if isinstance(converted, dict):
        if "conclusion" in converted or "finding_order" in converted:
            return converted
        if depth < 3:
            for field in ("response", "output"):
                value = converted.get(field)
                if value is not None:
                    extracted = _extract_ai_output(value, depth + 1)
                    if isinstance(extracted, (str, dict)):
                        return extracted
        choices = _coerce_js_value(converted.get("choices"))
        if isinstance(choices, list) and choices:
            choice = _coerce_js_value(choices[0])
            if isinstance(choice, dict):
                message = _coerce_js_value(choice.get("message"))
                if isinstance(message, dict):
                    content = _coerce_js_value(message.get("content"))
                    if isinstance(content, (str, dict)):
                        return content

    for field in ("response", "output"):
        try:
            value = _coerce_js_value(getattr(response, field))
        except Exception:
            continue
        if isinstance(value, (str, dict)):
            return value
    return converted


class CloudflareCache:
    def __init__(self, binding):
        self.binding = binding

    async def get_json(self, key):
        value = await self.binding.get(key)
        if not value:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return value

    async def put_json(self, key, value, expiration_ttl=None):
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if expiration_ttl:
            await self.binding.put(key, payload, expirationTtl=int(expiration_ttl))
        else:
            await self.binding.put(key, payload)


class CloudflareDotaGateway:
    def __init__(self, fetcher=None, stratz_api_key=""):
        self.fetcher = fetcher
        self.stratz_api_key = str(stratz_api_key or "").strip()

    async def _fetch(self, url, **options):
        fetcher = self.fetcher
        if fetcher is None:
            from workers import fetch
            fetcher = fetch
        response = await fetcher(url, **options)
        if not getattr(response, "ok", False):
            raise RuntimeError(f"upstream returned HTTP {getattr(response, 'status', 0)}")
        return await response.json()

    async def recent_ranked_matches(self, account_id, limit):
        query = urlencode({"limit": int(limit), "lobby_type": 7})
        return await self._fetch(
            f"{OPENDOTA_BASE_URL}/players/{int(account_id)}/matches?{query}",
            headers={"Accept": "application/json"},
        )

    async def match_detail(self, match_id):
        return await self._fetch(
            f"{OPENDOTA_BASE_URL}/matches/{int(match_id)}",
            headers={"Accept": "application/json"},
        )

    async def request_parse(self, match_id):
        return await self._fetch(
            f"{OPENDOTA_BASE_URL}/request/{int(match_id)}",
            method="POST",
            headers={"Accept": "application/json"},
        )

    async def stratz_detail(self, match_id):
        if not self.stratz_api_key:
            return None
        core = await self._graphql(STRATZ_CORE_QUERY, {"matchId": int(match_id)})
        match = (core.get("data") or {}).get("match") if isinstance(core, dict) else None
        if not isinstance(match, dict):
            return None
        result = dict(match)
        result["_fetch_warnings"] = []
        try:
            playback = await self._graphql(STRATZ_PLAYBACK_QUERY, {"matchId": int(match_id)})
            playback_match = (playback.get("data") or {}).get("match") if isinstance(playback, dict) else None
            if isinstance(playback_match, dict):
                self._merge_playback(result, playback_match.get("players") or [])
            else:
                result["_fetch_warnings"].append("Stratz playback query unavailable")
        except Exception:
            result["_fetch_warnings"].append("Stratz playback query unavailable")
        return result

    async def _graphql(self, query, variables):
        return await self._fetch(
            STRATZ_GRAPHQL_URL,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.stratz_api_key}",
            },
            body=json.dumps({"query": query, "variables": variables}),
        )

    @staticmethod
    def _merge_playback(match, playback_players):
        for target in match.get("players") or []:
            target_account = (target.get("steamAccount") or {}).get("id")
            target_hero = (target.get("hero") or {}).get("id")
            source = next(
                (
                    player for player in playback_players
                    if target_account is not None
                    and (player.get("steamAccount") or {}).get("id") == target_account
                ),
                None,
            )
            if source is None:
                source = next(
                    (
                        player for player in playback_players
                        if (player.get("hero") or {}).get("id") == target_hero
                        and player.get("isRadiant") == target.get("isRadiant")
                    ),
                    None,
                )
            if source and source.get("playbackData"):
                target["playbackData"] = source["playbackData"]


class _GitHubWorkflowGateway:
    def __init__(self, fetcher=None, token="", repository="", workflow="", ref="main"):
        self.fetcher = fetcher
        self.token = str(token or "").strip()
        self.repository = str(repository or "").strip()
        self.workflow = str(workflow or "").strip()
        self.ref = str(ref or "main").strip()

    async def _dispatch(self, inputs=None):
        if not self.token:
            raise RuntimeError("GitHub dispatch token is unavailable")
        if not self.repository or not self.workflow or not self.ref:
            raise RuntimeError("GitHub workflow is not configured")
        fetcher = self.fetcher
        if fetcher is None:
            from workers import fetch
            fetcher = fetch
        url = (
            f"{GITHUB_API_URL}/repos/{self.repository}/actions/workflows/"
            f"{self.workflow}/dispatches"
        )
        payload = {"ref": self.ref}
        if inputs:
            payload["inputs"] = inputs
        response = await fetcher(
            url,
            method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "cstd-help-worker",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            body=json.dumps(payload),
        )
        status = int(getattr(response, "status", 0) or 0)
        if status != 204:
            raise RuntimeError(f"GitHub workflow dispatch returned HTTP {status}")
        return {"accepted": True}


class GitHubEvidenceGateway(_GitHubWorkflowGateway):
    async def dispatch(self, match_id):
        return await self._dispatch({"match_id": str(int(match_id))})


class GitHubMatchRefreshGateway(_GitHubWorkflowGateway):
    async def dispatch(self):
        return await self._dispatch()


class AnalyzerGateway:
    def analyze(self, match, *, stratz_data=None, opendota_data=None):
        return analyze_match(match, stratz_data=stratz_data, opendota_data=opendota_data)


class WorkersAIGateway:
    INSTRUCTIONS = (
        "你是Dota 2个人天梯教练，只负责给输入中的review_findings排序。"
        "按对下一局上分的影响从高到低排列索引；每个索引必须且只能出现一次。"
        "不得输出分析文字、不得新增问题、不得改写任何证据或行动。"
        "只输出一个JSON对象，唯一字段为finding_order。"
    )

    RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "finding_order": {
                "type": "array",
                "items": {"type": "integer"},
                "maxItems": 4,
            },
        },
        "required": ["finding_order"],
        "additionalProperties": False,
    }

    def __init__(self, binding, model, js_converter=None):
        self.binding = binding
        self.model = model
        self.js_converter = js_converter or _to_js_request

    async def generate(self, evidence_package):
        request = {
                "messages": [
                    {"role": "system", "content": self.INSTRUCTIONS},
                    {
                        "role": "user",
                        "content": json.dumps(
                            evidence_package,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": self.RESPONSE_SCHEMA,
                },
                "temperature": 0.2,
                "max_tokens": 3072,
            }
        response = await self.binding.run(self.model, self.js_converter(request))
        return parse_ai_output(_extract_ai_output(response))
