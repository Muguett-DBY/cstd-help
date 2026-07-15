import json
from datetime import datetime, timezone

from analysis.analyzer import _item_detail, get_hero_info


RANKED_LOBBY_TYPE = 7


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _int_or_none(value):
    return int(value) if _is_number(value) else None


def _win_flag(value):
    if isinstance(value, bool):
        return value
    if _is_number(value) and value in (0, 1):
        return bool(value)
    return None


def _valid_player_slot(value):
    return isinstance(value, int) and not isinstance(value, bool) and (
        0 <= value <= 4 or 128 <= value <= 132
    )


def _is_radiant(player_slot):
    return _valid_player_slot(player_slot) and player_slot < 128


def _player_won(player_slot, radiant_win):
    return radiant_win if _is_radiant(player_slot) else not radiant_win


def _ended_at(start_time, duration):
    if not _is_number(start_time) or not _is_number(duration):
        return None
    timestamp = max(0, int(start_time) + int(duration))
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_recent_match(raw_match, account_id):
    if not isinstance(raw_match, dict):
        return None
    match_id = raw_match.get("match_id")
    hero_id = raw_match.get("hero_id")
    player_slot = raw_match.get("player_slot")
    duration = raw_match.get("duration")
    start_time = raw_match.get("start_time")
    radiant_win = _win_flag(raw_match.get("radiant_win"))
    kills = raw_match.get("kills")
    deaths = raw_match.get("deaths")
    assists = raw_match.get("assists")
    if (
        not _is_number(match_id)
        or int(match_id) <= 0
        or not _is_number(hero_id)
        or int(hero_id) <= 0
        or not _valid_player_slot(player_slot)
        or not _is_number(duration)
        or int(duration) <= 0
        or not _is_number(start_time)
        or int(start_time) <= 0
        or radiant_win is None
        or any(
            not _is_number(value) or int(value) < 0
            for value in (kills, deaths, assists)
        )
    ):
        return None

    duration = int(duration)
    lobby_type = raw_match.get("lobby_type")
    return {
        "match_id": int(match_id),
        "account_id": int(account_id),
        "hero": get_hero_info(int(hero_id)),
        "player_slot": player_slot,
        "side": "radiant" if _is_radiant(player_slot) else "dire",
        "is_win": _player_won(player_slot, radiant_win),
        "radiant_win": radiant_win,
        "start_time": int(start_time),
        "ended_at": _ended_at(start_time, duration),
        "duration_seconds": duration,
        "kda": {
            "kills": int(kills),
            "deaths": int(deaths),
            "assists": int(assists),
        },
        "rank_tier": raw_match.get("average_rank") or raw_match.get("rank_tier"),
        "lane": raw_match.get("lane"),
        "lane_role": raw_match.get("lane_role"),
        "is_roaming": raw_match.get("is_roaming"),
        "game_mode": raw_match.get("game_mode"),
        "lobby_type": lobby_type,
        "is_ranked": lobby_type == RANKED_LOBBY_TYPE,
    }


def normalize_player_match(raw_match, account_id):
    if not isinstance(raw_match, dict):
        return None
    player = next(
        (
            item for item in raw_match.get("players", [])
            if isinstance(item, dict) and item.get("account_id") == account_id
        ),
        None,
    )
    if player is None:
        return None

    items = [player.get(f"item_{index}", 0) or 0 for index in range(6)]
    ability_upgrades = player.get("ability_upgrades") or player.get("ability_upgrades_arr") or []
    radiant_win = _win_flag(raw_match.get("radiant_win"))
    player_slot = player.get("player_slot")
    normalized = {
        "match_id": raw_match.get("match_id"),
        "duration": raw_match.get("duration"),
        "radiant_win": int(radiant_win) if radiant_win is not None else None,
        "start_time": raw_match.get("start_time"),
        "game_mode": raw_match.get("game_mode"),
        "lobby_type": raw_match.get("lobby_type"),
        "radiant_score": raw_match.get("radiant_score"),
        "dire_score": raw_match.get("dire_score"),
        "account_id": account_id,
        "hero_id": player.get("hero_id"),
        "player_slot": player_slot,
        "is_radiant": 1 if _is_radiant(player_slot) else 0 if _valid_player_slot(player_slot) else None,
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
        "ability_upgrades": json.dumps(ability_upgrades) if ability_upgrades else None,
    }
    for index, item_id in enumerate(items):
        normalized[f"item_{index}"] = item_id
    for field in (
        "actions_per_min", "stuns", "obs_placed", "sen_placed", "observer_kills",
        "sentry_kills", "camps_stacked", "rune_pickups", "courier_kills",
        "tower_kills", "roshan_kills", "buyback_count", "lane_efficiency_pct",
        "teamfight_participation", "life_state_dead", "gold_spent", "total_gold",
    ):
        normalized[field] = player.get(field)
    return normalized


def normalize_match_participants(raw_match, account_id):
    if not isinstance(raw_match, dict):
        return []
    participants = []
    for index, player in enumerate(raw_match.get("players") or []):
        if not isinstance(player, dict) or not _is_number(player.get("hero_id")):
            continue
        player_slot = player.get("player_slot")
        item_ids = [player.get(f"item_{item_index}") for item_index in range(6)]
        neutral_item = player.get("item_neutral") or player.get("item_6")
        if neutral_item:
            item_ids.append(neutral_item)
        items = [
            _item_detail(int(item_id))
            for item_id in item_ids
            if _is_number(item_id) and int(item_id) > 0
        ]
        participants.append({
            "index": index,
            "account_id": player.get("account_id"),
            "is_self": player.get("account_id") == int(account_id),
            "hero": get_hero_info(int(player["hero_id"])),
            "player_slot": player_slot,
            "side": (
                "radiant" if _is_radiant(player_slot)
                else "dire" if _valid_player_slot(player_slot)
                else None
            ),
            "personaname": player.get("personaname"),
            "kda": {
                "kills": _int_or_none(player.get("kills")),
                "deaths": _int_or_none(player.get("deaths")),
                "assists": _int_or_none(player.get("assists")),
            },
            "level": player.get("level"),
            "net_worth": player.get("net_worth"),
            "gold_per_min": player.get("gold_per_min"),
            "xp_per_min": player.get("xp_per_min"),
            "last_hits": player.get("last_hits"),
            "denies": player.get("denies"),
            "hero_damage": player.get("hero_damage"),
            "tower_damage": player.get("tower_damage"),
            "hero_healing": player.get("hero_healing"),
            "stuns": player.get("stuns"),
            "actions_per_min": player.get("actions_per_min"),
            "obs_placed": player.get("obs_placed"),
            "sen_placed": player.get("sen_placed"),
            "camps_stacked": player.get("camps_stacked"),
            "lane": player.get("lane"),
            "lane_role": player.get("lane_role"),
            "items": items,
        })
    return participants
