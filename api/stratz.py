import json

import requests

from config import ACCOUNT_ID, STRATZ_API_KEY, STRATZ_GRAPHQL_URL


class StratzClient:
    def __init__(self):
        self.url = STRATZ_GRAPHQL_URL.split("?", 1)[0]
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        if STRATZ_API_KEY:
            self.session.headers.update({"Authorization": f"Bearer {STRATZ_API_KEY}"})
        self.last_warning = None

    def _execute(self, query, variables=None):
        self.last_warning = None
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            resp = self.session.post(self.url, json=payload, timeout=15)
            if resp.status_code == 403:
                text = resp.text.lower()
                if "bearer token" in text:
                    print("  Stratz: Bearer token missing or rejected. Check STRATZ_API.txt.")
                elif "cloudflare" in text or "challenge" in text:
                    print("  Stratz: Blocked by Cloudflare (IP/region restriction). Skipping.")
                    self.last_warning = "Stratz playback/core query was blocked by Cloudflare"
                else:
                    print("  Stratz: API key expired or invalid (403). Skipping.")
                    self.last_warning = "Stratz API key expired or invalid"
                return None
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                print(f"  Stratz GraphQL errors: {data['errors']}")
                self.last_warning = "Stratz GraphQL returned field errors"
            return data.get("data")
        except requests.exceptions.RequestException as e:
            print(f"  Stratz API error: {e}")
            self.last_warning = f"Stratz API error: {e}"
            return None

    def get_match_detail(self, match_id, include_playback=True, account_id=ACCOUNT_ID):
        query = """
        query GetMatchDetail($matchId: Long!) {
            match(id: $matchId) {
                id
                durationSeconds
                didRadiantWin
                startDateTime
                radiantKills
                direKills
                players {
                    isRadiant
                    steamAccount {
                        id
                    }
                    hero {
                        id
                        displayName
                    }
                    kills
                    deaths
                    assists
                    networth
                    goldPerMinute
                    experiencePerMinute
                    heroDamage
                    towerDamage
                    heroHealing
                    numLastHits
                    numDenies
                    level
                    gold
                    goldSpent
                    position
                    lane
                    role
                    abilities {
                        abilityId
                        time
                        level
                    }
                    item0Id
                    item1Id
                    item2Id
                    item3Id
                    item4Id
                    item5Id
                    neutral0Id
                    stats {
                        lastHitsPerMinute
                        goldPerMinute
                        experiencePerMinute
                        heroDamagePerMinute
                        towerDamagePerMinute
                        deniesPerMinute
                    }
                }
            }
        }
        """
        variables = {"matchId": match_id}
        data = self._execute(query, variables)
        if data and data.get("match"):
            match = data["match"]
            match["_fetch_warnings"] = []
            if include_playback:
                warning = self._merge_playback_detail(
                    match,
                    match_id,
                    account_id=account_id,
                )
                if warning:
                    match["_fetch_warnings"].append(warning)
            return match
        return None

    def _merge_playback_detail(self, match, match_id, account_id=ACCOUNT_ID):
        query = """
        query GetMatchPlayback($matchId: Long!, $steamId: Long!) {
            match(id: $matchId) {
                id
                parsedDateTime
                isStats
                towerStatusRadiant
                towerStatusDire
                barracksStatusRadiant
                barracksStatusDire
                towerDeaths {
                    time
                    npcId
                    isRadiant
                    attacker
                }
                playbackData {
                    towerDeathEvents { time radiant dire }
                    roshanEvents {
                        time hp maxHp createTime x y totalDamageTaken
                        item0 item1 item2 item3 item4 item5
                    }
                    wardEvents {
                        time positionX positionY fromPlayer wardType action playerDestroyed
                    }
                }
                players(steamAccountId: $steamId) {
                    playerSlot
                    steamAccount { id }
                    hero { id }
                    isRadiant
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
                    stats {
                        killEvents {
                            time target byAbility byItem gold xp positionX positionY
                            isSolo isGank isInvisible isSmoke isTpRecently
                        }
                        deathEvents {
                            time attacker target byAbility byItem goldFed xpFed timeDead
                            positionX positionY goldLost isWardWalkThrough isAttemptTpOut
                            isDieBack isBurst isEngagedOnDeath hasHealAvailable isTracked
                        }
                        assistEvents { time target gold xp positionX positionY }
                        itemPurchases { time itemId }
                        wards { time type positionX positionY }
                        wardDestruction { time gold experience isWard }
                        actionsPerMinute
                        actionReport {
                            moveToPosition moveToTarget attackPosition attackTarget
                            castPosition castTarget castNoTarget heldPosition
                            glyphCast scanUsed pingUsed
                        }
                        campStack
                        runes { time rune action gold positionX positionY }
                        courierKills { time positionX positionY }
                        heroDamageReceivedPerMinute
                        itemUsed { itemId count }
                        abilityCastReport { abilityId count }
                        towerDamageReport { npcId damage damageCreeps damageFromAbility }
                    }
                }
            }
        }
        """
        data = self._execute(
            query,
            {"matchId": match_id, "steamId": int(account_id)},
        )
        if not data or not data.get("match"):
            return self.last_warning or "Stratz playback query unavailable"

        rich_match = data["match"]
        for key in (
            "parsedDateTime",
            "isStats",
            "towerStatusRadiant",
            "towerStatusDire",
            "barracksStatusRadiant",
            "barracksStatusDire",
            "towerDeaths",
            "playbackData",
        ):
            if key in rich_match:
                match[key] = rich_match[key]

        playback_players = rich_match.get("players") or []
        target_players = match.get("players") or []
        for target in target_players:
            playback = self._find_matching_playback_player(target, playback_players)
            if not playback:
                continue
            if "playbackData" in playback:
                target["playbackData"] = playback.get("playbackData") or {}
            if "stats" in playback:
                merged_stats = dict(target.get("stats") or {})
                merged_stats.update(playback.get("stats") or {})
                target["stats"] = merged_stats
        return self.last_warning

    def request_match_reparse(self, match_id):
        query = """
        mutation RetryMatchDownload($matchId: Long!) {
            retryMatchDownload(matchId: $matchId)
        }
        """
        data = self._execute(query, {"matchId": int(match_id)})
        return bool(data and data.get("retryMatchDownload"))

    def _find_matching_playback_player(self, target, playback_players):
        target_account_id = (target.get("steamAccount") or {}).get("id")
        target_hero_id = (target.get("hero") or {}).get("id")
        target_is_radiant = target.get("isRadiant")
        if target_account_id is not None:
            for player in playback_players:
                if (player.get("steamAccount") or {}).get("id") == target_account_id:
                    return player
        for player in playback_players:
            if ((player.get("hero") or {}).get("id") == target_hero_id and
                    player.get("isRadiant") == target_is_radiant):
                return player
        return None

    def get_player_matches(self, account_id, take=10):
        query = """
        query GetPlayerMatches($steamId: Long!, $take: Int!) {
            player(steamAccountId: $steamId) {
                steamAccountId
                matchCount
                winCount
                matches(request: { take: $take, orderBy: DESC }) {
                    id
                    didRadiantWin
                    durationSeconds
                    startDateTime
                    players {
                        steamAccount {
                            id
                        }
                        isRadiant
                        hero {
                            id
                            displayName
                        }
                        kills
                        deaths
                        assists
                        networth
                        goldPerMinute
                        experiencePerMinute
                        heroDamage
                        numLastHits
                        numDenies
                        level
                    }
                }
            }
        }
        """
        variables = {"steamId": account_id, "take": take}
        data = self._execute(query, variables)
        if data and data.get("player"):
            return data["player"]
        return None


if __name__ == "__main__":
    from config import STRATZ_API_KEY
    if not STRATZ_API_KEY:
        print("No Stratz API key found!")
    else:
        client = StratzClient()
        result = client.get_match_detail(8234567890)
        if result:
            print(f"Match {result.get('id')}: {result.get('durationSeconds')}s")
        else:
            print("No match data returned")
