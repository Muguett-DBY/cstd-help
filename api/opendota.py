import json
import requests
import time
from config import OPENDOTA_BASE_URL, ACCOUNT_ID


class OpenDotaClient:
    def __init__(self):
        self.base_url = OPENDOTA_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, endpoint, params=None, retries=3, delay=1.5):
        url = f"{self.base_url}{endpoint}"
        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 429:
                    wait = min(2 ** attempt * delay, 30)
                    print(f"  Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                if attempt == retries - 1:
                    print(f"  API error: {e}")
                    return None
                time.sleep(delay)
        return None

    def _post(self, endpoint, params=None, retries=3, delay=1.5):
        url = f"{self.base_url}{endpoint}"
        for attempt in range(retries):
            try:
                resp = self.session.post(url, params=params, timeout=30)
                if resp.status_code == 429:
                    wait = min(2 ** attempt * delay, 30)
                    print(f"  Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                if attempt == retries - 1:
                    print(f"  API error: {e}")
                    return None
                time.sleep(delay)
        return None

    def get_recent_matches(self, account_id=None, limit=20):
        aid = account_id or ACCOUNT_ID
        data = self._get(f"/players/{aid}/matches", params={"limit": limit})
        return data or []

    def get_match(self, match_id):
        return self._get(f"/matches/{match_id}")

    def request_parse(self, match_id):
        data = self._post(f"/request/{match_id}")
        if isinstance(data, dict):
            job = data.get("job") or data
            return job.get("jobId") or job.get("id")
        return None

    def get_parse_job(self, job_id):
        return self._get(f"/request/{job_id}")

    def has_parsed_player_logs(self, match_data, account_id=None):
        player = self.find_player(match_data, account_id=account_id)
        if not player:
            return False
        for key in ("purchase_log", "death_log", "kills_log", "gold_t", "lh_t", "xp_t"):
            value = player.get(key)
            if isinstance(value, list) and value:
                return True
        return False

    def get_match_with_parse(self, match_id, account_id=None, wait_seconds=90, poll_interval=15):
        match_data = self.get_match(match_id)
        if not match_data:
            return None, None
        if self.has_parsed_player_logs(match_data, account_id=account_id):
            return match_data, None

        job_id = self.request_parse(match_id)
        if not job_id or wait_seconds <= 0:
            return match_data, job_id

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            time.sleep(min(poll_interval, max(0, deadline - time.time())))
            match_data = self.get_match(match_id)
            if match_data and self.has_parsed_player_logs(match_data, account_id=account_id):
                return match_data, job_id
        return match_data, job_id

    def find_player(self, raw_match, account_id=None):
        aid = account_id or ACCOUNT_ID
        for player in (raw_match or {}).get("players", []):
            if player.get("account_id") == aid:
                return player
        return None

    def get_player_heroes(self, account_id=None):
        aid = account_id or ACCOUNT_ID
        return self._get(f"/players/{aid}/heroes")

    def get_hero_stats(self):
        return self._get("/heroStats")

    def parse_match_for_player(self, raw_match, account_id=None):
        aid = account_id or ACCOUNT_ID
        if not raw_match:
            return None

        player = self.find_player(raw_match, aid)
        if not player:
            return None

        items = [player.get(f"item_{i}", 0) or 0 for i in range(6)]
        ability_upgrades = player.get("ability_upgrades") or player.get("ability_upgrades_arr") or []

        return {
            "match_id": raw_match.get("match_id"),
            "duration": raw_match.get("duration"),
            "radiant_win": 1 if raw_match.get("radiant_win") else 0,
            "start_time": raw_match.get("start_time"),
            "game_mode": raw_match.get("game_mode"),
            "lobby_type": raw_match.get("lobby_type"),
            "radiant_score": raw_match.get("radiant_score"),
            "dire_score": raw_match.get("dire_score"),
            "account_id": aid,
            "hero_id": player.get("hero_id"),
            "player_slot": player.get("player_slot"),
            "is_radiant": 1 if player.get("player_slot", 0) < 128 else 0,
            "kills": player.get("kills"),
            "deaths": player.get("deaths"),
            "assists": player.get("assists"),
            "gold_per_min": player.get("gold_per_min"),
            "xp_per_min": player.get("xp_per_min"),
            "hero_damage": player.get("hero_damage"),
            "tower_damage": player.get("tower_damage"),
            "hero_healing": player.get("hero_healing"),
            "last_hits": player.get("last_hits"),
            "denies": player.get("denies"),
            "level": player.get("level"),
            "gold": player.get("gold"),
            "net_worth": player.get("net_worth"),
            "item_0": items[0],
            "item_1": items[1],
            "item_2": items[2],
            "item_3": items[3],
            "item_4": items[4],
            "item_5": items[5],
            "ability_upgrades": json.dumps(ability_upgrades) if ability_upgrades else None,
        }


if __name__ == "__main__":
    client = OpenDotaClient()
    matches = client.get_recent_matches(limit=3)
    print(f"Found {len(matches)} recent matches")
    for m in matches[:3]:
        print(f"  Match {m.get('match_id')}: {m.get('hero_id')}")
