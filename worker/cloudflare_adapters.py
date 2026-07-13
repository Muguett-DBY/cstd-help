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
