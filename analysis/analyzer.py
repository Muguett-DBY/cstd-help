import ast
import json
import os
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(BASE_DIR, "analysis", "rules")


def _load_json(filename):
    path = os.path.join(RULES_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


HERO_ID_TO_NAME = {}
HERO_NAME_TO_ID = {}
HERO_ID_TO_SLUG = {}

ITEM_FALLBACKS = {
    7: "Javelin",
    50: "Phase Boots",
    63: "Power Treads",
    65: "Hand of Midas",
    77: "Null Talisman",
    108: "Aghanim's Scepter",
    110: "Refresher Orb",
    112: "Assault Cuirass",
    116: "Black King Bar",
    119: "Shiva's Guard",
    135: "Monkey King Bar",
    139: "Butterfly",
    141: "Daedalus",
    143: "Skull Basher",
    145: "Battle Fury",
    147: "Manta Style",
    152: "Shadow Blade",
    154: "Sange and Yasha",
    156: "Satanic",
    158: "Mjollnir",
    160: "Eye of Skadi",
    164: "Helm of the Dominator",
    208: "Abyssal Blade",
    214: "Tranquil Boots",
    220: "Boots of Travel 2",
    235: "Octarine Core",
    254: "Glimmer Cape",
    277: "Yasha and Kaya",
    598: "Mage Slayer",
    600: "Overwhelming Blink",
    603: "Swift Blink",
    939: "Harpoon",
    1097: "Disperser",
    1852: "Essence Distiller",
    1856: "Crella's Crozier",
}

ITEM_KEY_FALLBACKS = {
    "bfury": (145, "Battle Fury"),
    "battle_fury": (145, "Battle Fury"),
    "black_king_bar": (116, "Black King Bar"),
    "bkb": (116, "Black King Bar"),
    "manta": (147, "Manta Style"),
    "manta_style": (147, "Manta Style"),
    "abyssal_blade": (208, "Abyssal Blade"),
    "skadi": (160, "Eye of Skadi"),
    "eye_of_skadi": (160, "Eye of Skadi"),
    "butterfly": (139, "Butterfly"),
    "monkey_king_bar": (135, "Monkey King Bar"),
    "power_treads": (63, "Power Treads"),
    "phase_boots": (50, "Phase Boots"),
    "hand_of_midas": (65, "Hand of Midas"),
}

ABILITY_FALLBACKS = {
    5003: "Mana Break",
    5004: "Blink",
    5005: "Counterspell",
    5006: "Mana Void",
    7314: "Counterspell",
}


def _init_hero_maps():
    global HERO_ID_TO_NAME, HERO_NAME_TO_ID, HERO_ID_TO_SLUG
    if HERO_ID_TO_NAME:
        return
    heroes = _load_json("heroes.json")
    for raw_id, info in heroes.items():
        try:
            hero_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if not isinstance(info, dict):
            continue
        hero_name = info.get("name")
        if not hero_name:
            continue
        HERO_ID_TO_NAME[hero_id] = hero_name
        HERO_NAME_TO_ID[hero_name.lower()] = hero_id
        HERO_ID_TO_SLUG[hero_id] = info.get("slug") or f"hero-{hero_id}"


def get_hero_name(hero_id):
    _init_hero_maps()
    return HERO_ID_TO_NAME.get(hero_id, f"Hero#{hero_id}")


def get_hero_info(hero_id, display_name=None):
    _init_hero_maps()
    return {
        "id": hero_id,
        "name": display_name or get_hero_name(hero_id),
        "slug": HERO_ID_TO_SLUG.get(hero_id, f"hero-{hero_id}"),
    }


def analyze_match(match_data, stratz_data=None, opendota_data=None, d2pt_data=None):
    _init_hero_maps()
    hero_name = get_hero_name(match_data.get("hero_id"))
    duration = match_data.get("duration", 0)
    duration_min = duration / 60 if duration else 0
    account_id = match_data.get("account_id")
    stratz_player = _extract_stratz_player(stratz_data, account_id, match_data)
    opendota_player = _extract_opendota_player(opendota_data, account_id, match_data)
    context = _build_match_context(
        match_data,
        stratz_data,
        stratz_player,
        opendota_player=opendota_player,
        opendota_data=opendota_data,
    )

    result = {
        "match_id": match_data.get("match_id"),
        "hero_name": hero_name,
        "hero_id": match_data.get("hero_id"),
        "is_win": match_data.get("radiant_win") == 1 and match_data.get("is_radiant") == 1 or
                  match_data.get("radiant_win") == 0 and match_data.get("is_radiant") == 0,
        "duration_min": round(duration_min, 1),
        "context": context,
        "data_quality": {},
        "derived": {},
        "timeline": {},
        "events": {},
        "review_findings": [],
        "role_profile": {},
        "kda": {},
        "farm": {},
        "items": {},
        "skills": {},
        "timing": {},
        "comparison": {},
        "issues": [],
        "highlights": [],
        "suggestions": [],
    }

    kills = match_data.get("kills", 0) or 0
    deaths = match_data.get("deaths", 0) or 0
    assists = match_data.get("assists", 0) or 0
    kda_ratio = (kills + assists) / max(deaths, 1)
    result["kda"] = {
        "kills": kills, "deaths": deaths, "assists": assists,
        "kda_ratio": round(kda_ratio, 2),
    }
    result["match_metadata"] = _build_match_metadata(result, match_data)

    lh = match_data.get("last_hits", 0) or 0
    dn = match_data.get("denies", 0) or 0
    gpm = match_data.get("gold_per_min", 0) or 0
    xpm = match_data.get("xp_per_min", 0) or 0
    hd = match_data.get("hero_damage", 0) or 0
    td = match_data.get("tower_damage", 0) or 0
    nh = match_data.get("net_worth", 0) or 0

    result["farm"] = {
        "last_hits": lh, "denies": dn, "gpm": gpm, "xpm": xpm,
        "hero_damage": hd, "tower_damage": td, "net_worth": nh,
    }
    result["derived"] = _build_derived_metrics(result, match_data)
    result["role_profile"] = _build_role_profile(context, result["derived"])

    items = []
    for i in range(6):
        item_id = match_data.get(f"item_{i}", 0) or 0
        if item_id:
            items.append(item_id)
    result["items"]["final_items"] = items
    result["items"]["final_item_details"] = [_item_detail(item_id) for item_id in items]

    result["skills"]["upgrades"] = _extract_ability_upgrades(match_data, stratz_player)
    result["timeline"] = _build_timeline(
        match_data,
        stratz_player,
        duration_min,
        opendota_player=opendota_player,
        role_profile=result["role_profile"],
    )
    result["events"] = _build_events(
        stratz_player,
        opendota_player=opendota_player,
        opendota_data=opendota_data,
        expected_deaths=deaths,
    )
    result["events"]["post_item_windows"] = _build_post_item_windows(result["events"], result["timeline"])

    benchmarks = _load_json("benchmarks.json")
    role = _benchmark_role(context)
    result["comparison"] = _compare_with_benchmarks(result["farm"], duration_min, role)

    counters = _load_json("counters.json")
    enemy_heroes = context.get("enemy_heroes", [])
    if hero_name in counters.get("strong_against", {}):
        strong = counters["strong_against"][hero_name]
        weak_against = [h for h in enemy_heroes if h in strong]
        if weak_against:
            result["issues"].append({
                "type": "hero_matchup",
                "severity": "high",
                "message": f"对手阵容中存在需要重点处理的对位英雄: {', '.join(weak_against)}",
            })

    if d2pt_data:
        result["d2pt"] = d2pt_data
        _compare_with_d2pt(result, d2pt_data)

    result["data_quality"] = _build_data_quality(match_data, stratz_data, stratz_player, result, opendota_data=opendota_data)
    result["review_findings"] = _build_review_findings(result)
    _generate_suggestions(result)

    return result


def _truthy(value):
    return value in (True, 1, "1", "true", "True")


def _extract_stratz_player(stratz_data, account_id, match_data):
    if not stratz_data:
        return None

    players = stratz_data.get("players") or []
    if not players:
        return None

    if account_id is not None:
        for player in players:
            steam_account = player.get("steamAccount") or {}
            if steam_account.get("id") == account_id:
                return player

    hero_id = match_data.get("hero_id")
    is_radiant = _truthy(match_data.get("is_radiant"))
    for player in players:
        hero = player.get("hero") or {}
        if hero.get("id") == hero_id and _truthy(player.get("isRadiant")) == is_radiant:
            return player

    return None


def _extract_opendota_player(opendota_data, account_id, match_data):
    if not opendota_data:
        return None
    players = opendota_data.get("players") or []
    if account_id is not None:
        for index, player in enumerate(players):
            if player.get("account_id") == account_id:
                item = dict(player)
                item["_player_index"] = index
                return item
    hero_id = match_data.get("hero_id")
    player_slot = match_data.get("player_slot")
    for index, player in enumerate(players):
        if player.get("hero_id") == hero_id and player.get("player_slot") == player_slot:
            item = dict(player)
            item["_player_index"] = index
            return item
    return None


def _build_match_context(match_data, stratz_data, stratz_player, opendota_player=None, opendota_data=None):
    is_radiant = _truthy(match_data.get("is_radiant"))
    obs_count = len((opendota_player or {}).get("obs_log") or [])
    sen_count = len((opendota_player or {}).get("sen_log") or [])
    context = {
        "side": "Radiant" if is_radiant else "Dire",
        "hero_name": get_hero_name(match_data.get("hero_id")),
        "role": None,
        "lane": None,
        "raw_role": None,
        "opendota_lane_role": (opendota_player or {}).get("lane_role"),
        "opendota_lane": (opendota_player or {}).get("lane"),
        "is_roaming": bool((opendota_player or {}).get("is_roaming")),
        "observer_wards": obs_count,
        "sentry_wards": sen_count,
        "vision_events": obs_count + sen_count,
        "ally_lineup": [],
        "enemy_lineup": [],
        "ally_heroes": [],
        "enemy_heroes": [],
        "team_kills": None,
        "enemy_kills": None,
    }

    if stratz_player:
        context["role"] = stratz_player.get("position") or stratz_player.get("role")
        context["lane"] = stratz_player.get("lane")
        context["raw_role"] = stratz_player.get("role")
    elif context["opendota_lane_role"] in {1, 2, 3, 4}:
        lane_labels = {1: "优势路", 2: "中路", 3: "劣势路", 4: "野区"}
        context["lane"] = f"{lane_labels[context['opendota_lane_role']]}（OpenDota）"

    if is_radiant:
        context["team_kills"] = match_data.get("radiant_score")
        context["enemy_kills"] = match_data.get("dire_score")
    else:
        context["team_kills"] = match_data.get("dire_score")
        context["enemy_kills"] = match_data.get("radiant_score")

    if stratz_data:
        for player in stratz_data.get("players") or []:
            hero = player.get("hero") or {}
            hero_id = hero.get("id") or player.get("heroId")
            name = hero.get("displayName") or get_hero_name(hero_id)
            if not name:
                continue
            entry = get_hero_info(hero_id, display_name=name)
            if _truthy(player.get("isRadiant")) == is_radiant:
                context["ally_lineup"].append(entry)
            else:
                context["enemy_lineup"].append(entry)

    players = (opendota_data or {}).get("players") or []
    if players:
        ordered_players = sorted(players, key=lambda player: player.get("player_slot") or 0)
        radiant = [get_hero_info(player.get("hero_id")) for player in ordered_players if (player.get("player_slot") or 0) < 128]
        dire = [get_hero_info(player.get("hero_id")) for player in ordered_players if (player.get("player_slot") or 0) >= 128]
        context["ally_lineup"] = radiant if is_radiant else dire
        context["enemy_lineup"] = dire if is_radiant else radiant

    context["ally_heroes"] = [hero["name"] for hero in context["ally_lineup"]]
    context["enemy_heroes"] = [hero["name"] for hero in context["enemy_lineup"]]

    return context


def _iso_utc(timestamp):
    if not isinstance(timestamp, (int, float)) or timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_match_metadata(result, match_data):
    start_time = match_data.get("start_time")
    duration = match_data.get("duration") or 0
    ended_at = start_time + duration if isinstance(start_time, (int, float)) else None
    context = result.get("context") or {}
    kda = result.get("kda") or {}
    return {
        "schema_version": 1,
        "match_id": match_data.get("match_id"),
        "hero": get_hero_info(match_data.get("hero_id"), display_name=result.get("hero_name")),
        "is_win": bool(result.get("is_win")),
        "side": context.get("side"),
        "started_at": _iso_utc(start_time),
        "ended_at": _iso_utc(ended_at),
        "duration_seconds": duration,
        "kda": {
            "kills": kda.get("kills", 0),
            "deaths": kda.get("deaths", 0),
            "assists": kda.get("assists", 0),
        },
        "score": {
            "team": context.get("team_kills"),
            "enemy": context.get("enemy_kills"),
        },
        "allies": context.get("ally_lineup") or [],
        "enemies": context.get("enemy_lineup") or [],
    }


def _parse_jsonish(value):
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(value)
                return parsed if isinstance(parsed, list) else []
            except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
                continue
    return []


def _extract_ability_upgrades(match_data, stratz_player):
    stratz_abilities = None
    if stratz_player:
        stratz_abilities = stratz_player.get("abilityUpgrade") or stratz_player.get("abilities")
    if stratz_abilities:
        upgrades = []
        for index, upgrade in enumerate(stratz_abilities or []):
            if not isinstance(upgrade, dict):
                continue
            ability_id = upgrade.get("abilityId") or upgrade.get("ability_id")
            item = dict(upgrade)
            item.setdefault("level", index + 1)
            item["name"] = ABILITY_FALLBACKS.get(ability_id, str(ability_id))
            item["source"] = "stratz"
            upgrades.append(item)
        return upgrades

    upgrades = []
    for index, ability_id in enumerate(_parse_jsonish(match_data.get("ability_upgrades"))):
        if isinstance(ability_id, dict):
            ability_id = ability_id.get("abilityId") or ability_id.get("ability_id")
        if not ability_id:
            continue
        upgrades.append({
            "abilityId": ability_id,
            "level": index + 1,
            "name": ABILITY_FALLBACKS.get(ability_id, str(ability_id)),
            "source": "opendota",
        })
    return upgrades


def _build_derived_metrics(result, match_data):
    duration = result.get("duration_min") or 0
    farm = result.get("farm", {})
    kda = result.get("kda", {})
    context = result.get("context", {})
    team_kills = context.get("team_kills") or 0

    def per_min(value):
        return round(value / duration, 2) if duration else 0

    derived = {
        "lh_per_min": per_min(farm.get("last_hits", 0)),
        "denies_per_min": per_min(farm.get("denies", 0)),
        "hero_damage_per_min": per_min(farm.get("hero_damage", 0)),
        "tower_damage_per_min": per_min(farm.get("tower_damage", 0)),
        "deaths_per_10_min": round((kda.get("deaths", 0) / duration) * 10, 2) if duration else 0,
        "net_worth_per_min": per_min(farm.get("net_worth", 0)),
    }
    if team_kills:
        derived["kill_participation_pct"] = round(
            (kda.get("kills", 0) + kda.get("assists", 0)) / max(team_kills, 1) * 100,
            1,
        )
    return derived


def _as_number_list(values):
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        if isinstance(value, (int, float)):
            result.append(value)
    return result


def _sum_slice(values, start, end):
    return sum(values[start:min(end, len(values))])


def _avg_slice(values, start, end):
    sliced = values[start:min(end, len(values))]
    return round(sum(sliced) / len(sliced), 1) if sliced else 0


def _phase_summary(label, start, end, stats):
    lh = _sum_slice(stats.get("lastHitsPerMinute", []), start, end)
    denies = _sum_slice(stats.get("deniesPerMinute", []), start, end)
    hero_damage = _sum_slice(stats.get("heroDamagePerMinute", []), start, end)
    tower_damage = _sum_slice(stats.get("towerDamagePerMinute", []), start, end)
    minutes = max(min(end, len(stats.get("lastHitsPerMinute", []))) - start, 0)
    return {
        "label": label,
        "minutes": minutes,
        "last_hits": int(lh),
        "denies": int(denies),
        "lh_per_min": round(lh / minutes, 1) if minutes else 0,
        "avg_gpm": _avg_slice(stats.get("goldPerMinute", []), start, end),
        "avg_xpm": _avg_slice(stats.get("experiencePerMinute", []), start, end),
        "hero_damage": int(hero_damage),
        "tower_damage": int(tower_damage),
    }


def _find_low_efficiency_windows(lh_by_min, role_profile):
    if not lh_by_min:
        return []
    if role_profile.get("id") == "support":
        return []
    threshold = 4 if role_profile.get("lane_farm_sensitive") else 2
    windows = []
    start = None
    for idx, value in enumerate(lh_by_min):
        low = value <= threshold
        if low and start is None:
            start = idx
        if (not low or idx == len(lh_by_min) - 1) and start is not None:
            end = idx + 1 if low and idx == len(lh_by_min) - 1 else idx
            if end - start >= 2:
                windows.append({
                    "label": f"低效率窗口 {start}-{end}分钟",
                    "start_minute": start,
                    "end_minute": end,
                    "avg_lh": round(sum(lh_by_min[start:end]) / max(end - start, 1), 1),
                    "reason": "该窗口连续补刀偏少，系统会结合事件日志判断是被压制、转线、参战还是刷野路线断档。",
                })
            start = None
    return windows[:5]


def _top_windows(values, label, window_size=5, limit=3):
    if not values:
        return []
    windows = []
    for start in range(0, len(values), window_size):
        end = min(start + window_size, len(values))
        total = sum(values[start:end])
        if total > 0:
            windows.append({
                "label": f"{label} {start}-{end}分钟",
                "start_minute": start,
                "end_minute": end,
                "total": int(total),
            })
    return sorted(windows, key=lambda item: item["total"], reverse=True)[:limit]


def _diff_cumulative(values):
    numbers = _as_number_list(values)
    if not numbers:
        return []
    diffs = []
    previous = 0
    for value in numbers[1:]:
        diffs.append(max(value - previous, 0))
        previous = value
    return diffs


def _opendota_minute_stats(opendota_player):
    if not opendota_player:
        return None
    lh = _diff_cumulative(opendota_player.get("lh_t"))
    gold = _diff_cumulative(opendota_player.get("gold_t"))
    xp = _diff_cumulative(opendota_player.get("xp_t"))
    if not (lh or gold or xp):
        return None
    return {
        "lastHitsPerMinute": lh,
        "deniesPerMinute": [],
        "goldPerMinute": gold,
        "experiencePerMinute": xp,
        "heroDamagePerMinute": [],
        "towerDamagePerMinute": [],
        "source": "opendota_parsed_logs",
    }


def _stratz_playback_cs_minute_stats(stratz_player, duration_min):
    playback = (stratz_player or {}).get("playbackData") or {}
    events = playback.get("csEvents") or []
    if not events:
        return None
    max_minute = max(int(duration_min or 0), 1)
    event_minutes = []
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("time"), (int, float)):
            continue
        minute = int(event["time"] // 60)
        if minute < 0:
            continue
        event_minutes.append(minute)
        max_minute = max(max_minute, minute + 1)
    if not event_minutes:
        return None
    last_hits = [0] * max_minute
    for minute in event_minutes:
        last_hits[minute] += 1
    return {
        "lastHitsPerMinute": last_hits,
        "deniesPerMinute": [],
        "goldPerMinute": [],
        "experiencePerMinute": [],
        "heroDamagePerMinute": [],
        "towerDamagePerMinute": [],
        "source": "stratz_playback_cs",
    }


def _timeline_source_label(source):
    labels = {
        "opendota_parsed_logs": "OpenDota解析日志",
        "stratz_stats": "STRATZ分钟数组",
        "stratz_playback_cs": "STRATZ补刀事件",
    }
    if not source:
        return ""
    return " + ".join(labels.get(part, part) for part in source.split("+"))


def _build_timeline(match_data, stratz_player, duration_min, opendota_player=None, role_profile=None):
    opendota_stats = _opendota_minute_stats(opendota_player)
    playback_cs_stats = _stratz_playback_cs_minute_stats(stratz_player, duration_min)
    stats = (stratz_player or {}).get("stats") or {}
    stratz_normalized = {
        "lastHitsPerMinute": _as_number_list(stats.get("lastHitsPerMinute")),
        "deniesPerMinute": _as_number_list(stats.get("deniesPerMinute")),
        "goldPerMinute": _as_number_list(stats.get("goldPerMinute")),
        "experiencePerMinute": _as_number_list(stats.get("experiencePerMinute")),
        "heroDamagePerMinute": _as_number_list(stats.get("heroDamagePerMinute")),
        "towerDamagePerMinute": _as_number_list(stats.get("towerDamagePerMinute")),
    }
    if opendota_stats:
        normalized = {}
        source_parts = ["opendota_parsed_logs"]
        for key in [
            "lastHitsPerMinute",
            "deniesPerMinute",
            "goldPerMinute",
            "experiencePerMinute",
            "heroDamagePerMinute",
            "towerDamagePerMinute",
        ]:
            normalized[key] = opendota_stats.get(key) or stratz_normalized.get(key) or []
            if not opendota_stats.get(key) and stratz_normalized.get(key) and "stratz_stats" not in source_parts:
                source_parts.append("stratz_stats")
        source = "+".join(source_parts)
    elif playback_cs_stats and not stratz_normalized.get("lastHitsPerMinute"):
        normalized = {}
        source_parts = ["stratz_playback_cs"]
        for key in [
            "lastHitsPerMinute",
            "deniesPerMinute",
            "goldPerMinute",
            "experiencePerMinute",
            "heroDamagePerMinute",
            "towerDamagePerMinute",
        ]:
            normalized[key] = playback_cs_stats.get(key) or stratz_normalized.get(key) or []
            if not playback_cs_stats.get(key) and stratz_normalized.get(key) and "stratz_stats" not in source_parts:
                source_parts.append("stratz_stats")
        source = "+".join(source_parts)
    else:
        normalized = stratz_normalized
        source = "stratz_stats"
    lh_by_min = normalized["lastHitsPerMinute"]
    if not lh_by_min:
        return {
            "available": False,
            "ten_min_last_hits": None,
            "twenty_min_last_hits": None,
            "phases": [],
            "low_efficiency_windows": [],
            "damage_windows": [],
            "tower_windows": [],
            "source": None,
        }

    role_profile = role_profile or _build_role_profile({
        "role": (stratz_player or {}).get("position") or (stratz_player or {}).get("role"),
        "raw_role": (stratz_player or {}).get("role"),
    })
    phase_bounds = [(0, 10), (10, 20), (20, 30)]
    if len(lh_by_min) > 30:
        phase_bounds.append((30, len(lh_by_min)))
    phases = [
        _phase_summary(f"{start}-{end}", start, end, normalized)
        for start, end in phase_bounds
        if start < len(lh_by_min)
    ]
    return {
        "available": True,
        "source": source,
        "source_label": _timeline_source_label(source),
        "duration_minutes_observed": len(lh_by_min),
        "ten_min_last_hits": int(_sum_slice(lh_by_min, 0, 10)),
        "twenty_min_last_hits": int(_sum_slice(lh_by_min, 0, 20)) if len(lh_by_min) >= 20 else None,
        "ten_min_denies": int(_sum_slice(normalized["deniesPerMinute"], 0, 10)),
        "twenty_min_avg_gpm": _avg_slice(normalized["goldPerMinute"], 0, 20),
        "phases": phases,
        "low_efficiency_windows": _find_low_efficiency_windows(lh_by_min, role_profile),
        "damage_windows": _top_windows(normalized["heroDamagePerMinute"], "输出窗口"),
        "tower_windows": _top_windows(normalized["towerDamagePerMinute"], "推塔窗口"),
        "last_hits_by_minute": lh_by_min,
        "gold_by_minute": normalized["goldPerMinute"],
        "hero_damage_by_minute": normalized["heroDamagePerMinute"],
        "tower_damage_by_minute": normalized["towerDamagePerMinute"],
    }


def _event_minute(event):
    value = event.get("time") if isinstance(event, dict) else None
    return round(value / 60, 1) if isinstance(value, (int, float)) else None


def _normalize_timed_events(events, item_events=False, source=None):
    normalized = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        minute = _event_minute(event)
        if minute is None:
            continue
        item = {"time": event.get("time"), "minute": minute}
        if item_events:
            item_id = event.get("itemId") or event.get("item_id") or event.get("item")
            item["item_id"] = item_id
            item["item_name"] = _item_detail(item_id).get("name") if item_id else "Unknown"
        if source:
            item["source"] = source
        normalized.append(item)
    return sorted(normalized, key=lambda item: item["time"])


def _normalize_opendota_purchase_events(events):
    normalized = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        minute = _event_minute(event)
        if minute is None:
            continue
        key = event.get("key")
        item_id, item_name = ITEM_KEY_FALLBACKS.get(key, (None, None))
        if item_name is None:
            item_name = key.replace("_", " ").title() if isinstance(key, str) else "Unknown"
        normalized.append({
            "time": event.get("time"),
            "minute": minute,
            "item_id": item_id,
            "item_name": item_name,
            "source": "opendota",
        })
    return sorted(normalized, key=lambda item: item["time"])


def _normalize_opendota_timed_events(events):
    normalized = _normalize_timed_events(events)
    for item in normalized:
        item["source"] = "opendota"
    return normalized


def _normalize_opendota_vision_events(events, ward_type):
    normalized = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        minute = _event_minute(event)
        if minute is None:
            continue
        normalized.append({
            "time": event.get("time"),
            "minute": max(minute, 0),
            "ward_type": ward_type,
            "key": event.get("key"),
            "source": "opendota",
        })
    return sorted(normalized, key=lambda item: item["time"])


KEY_ITEM_IDS = {65, 116, 135, 139, 145, 147, 160, 208}
KEY_ITEM_NAMES = {
    "Battle Fury",
    "Black King Bar",
    "Manta Style",
    "Abyssal Blade",
    "Eye of Skadi",
    "Butterfly",
    "Monkey King Bar",
    "Hand of Midas",
}
FARM_ACCELERATION_ITEM_NAMES = {"Battle Fury", "Hand of Midas", "Maelstrom", "Mjollnir", "Radiance"}

PRIORITY_LABELS = {
    "high": "高优先级",
    "medium": "中优先级",
    "low": "低优先级",
}

CATEGORY_LABELS = {
    "closing": "终结比赛",
    "lane_farm": "前10分钟资源",
    "resource_continuity": "中后期资源连续性",
    "death_review": "死亡成本",
    "item_timing": "装备后转化",
    "map_impact": "地图影响力",
    "support_vision": "视野/控图",
    "review_focus": "复盘重点",
}


def _key_purchases(purchases):
    result = []
    seen = set()
    for item in purchases:
        item_id = item.get("item_id")
        item_name = item.get("item_name")
        if item_id in KEY_ITEM_IDS or item_name in KEY_ITEM_NAMES:
            key = item_id or item_name
            if key not in seen:
                result.append(item)
                seen.add(key)
    return result


def _extract_deaths_from_teamfights(opendota_data, opendota_player):
    if not opendota_data or not opendota_player:
        return []
    player_index = opendota_player.get("_player_index")
    if player_index is None:
        return []
    deaths = []
    for fight in opendota_data.get("teamfights") or []:
        players = fight.get("players") or []
        if player_index >= len(players):
            continue
        player_fight = players[player_index] or {}
        death_count = player_fight.get("deaths") or 0
        if death_count <= 0:
            continue
        event_time = fight.get("last_death") or fight.get("end") or fight.get("start")
        if not isinstance(event_time, (int, float)):
            continue
        for _ in range(death_count):
            deaths.append({
                "time": event_time,
                "minute": round(event_time / 60, 1),
                "source": "opendota_teamfights",
                "position": player_fight.get("deaths_pos") or {},
            })
    return sorted(deaths, key=lambda item: item["time"])


def _build_events(stratz_player, opendota_player=None, opendota_data=None, expected_deaths=0):
    playback = (stratz_player or {}).get("playbackData") or {}
    stratz_purchases = _normalize_timed_events(playback.get("purchaseEvents"), item_events=True, source="stratz")
    stratz_deaths = _normalize_timed_events(playback.get("deathEvents"), source="stratz")
    stratz_kills = _normalize_timed_events(playback.get("killEvents"), source="stratz")
    stratz_assists = _normalize_timed_events(playback.get("assistEvents"), source="stratz")

    opendota_purchases = []
    opendota_deaths = []
    opendota_teamfight_deaths = []
    opendota_kills = []
    opendota_assists = []
    opendota_observer_wards = []
    opendota_sentry_wards = []
    valve_replay_deaths = _normalize_timed_events(
        (opendota_data or {}).get("replay_death_events"),
        source="valve_replay",
    )
    if opendota_player:
        opendota_purchases = _normalize_opendota_purchase_events(opendota_player.get("purchase_log"))
        opendota_deaths = _normalize_opendota_timed_events(opendota_player.get("death_log"))
        opendota_teamfight_deaths = _extract_deaths_from_teamfights(opendota_data, opendota_player)
        opendota_kills = _normalize_opendota_timed_events(opendota_player.get("kills_log"))
        opendota_assists = _normalize_opendota_timed_events(
            opendota_player.get("assists_log") or opendota_player.get("assist_log")
        )
        opendota_observer_wards = _normalize_opendota_vision_events(opendota_player.get("obs_log"), "observer")
        opendota_sentry_wards = _normalize_opendota_vision_events(opendota_player.get("sen_log"), "sentry")

    source_parts = set()

    purchases = opendota_purchases or stratz_purchases
    if opendota_purchases:
        source_parts.add("opendota_parsed_logs")
    elif stratz_purchases:
        source_parts.add("stratz_playback")

    death_candidates = [
        (valve_replay_deaths, "valve_replay", 3),
        (opendota_deaths, "opendota_parsed_logs", 2),
        (stratz_deaths, "stratz_playback", 1),
        (opendota_teamfight_deaths, "opendota_teamfights", 0),
    ]
    available_death_candidates = [candidate for candidate in death_candidates if candidate[0]]
    if available_death_candidates:
        deaths, death_source, _ = max(
            available_death_candidates,
            key=lambda candidate: (
                bool(expected_deaths and len(candidate[0]) == int(expected_deaths)),
                min(len(candidate[0]), int(expected_deaths or len(candidate[0]))),
                candidate[2],
            ),
        )
        source_parts.add(death_source)
    else:
        deaths = []

    kills = opendota_kills or stratz_kills
    if opendota_kills:
        source_parts.add("opendota_parsed_logs")
    elif stratz_kills:
        source_parts.add("stratz_playback")

    assists = opendota_assists or stratz_assists
    if opendota_assists:
        source_parts.add("opendota_parsed_logs")
    elif stratz_assists:
        source_parts.add("stratz_playback")

    vision_events = opendota_observer_wards + opendota_sentry_wards
    if vision_events:
        source_parts.add("opendota_vision")

    source = "+".join(sorted(source_parts)) if source_parts else None
    expected_deaths = int(expected_deaths or 0)
    observed_deaths = len(deaths)
    missing_deaths = max(expected_deaths - observed_deaths, 0)
    if expected_deaths:
        death_coverage_label = f"已定位 {observed_deaths}/{expected_deaths} 次死亡"
    elif observed_deaths:
        death_coverage_label = f"已定位 {observed_deaths} 次死亡"
    else:
        death_coverage_label = "本局没有记录到死亡"
    return {
        "available": bool(source),
        "source": source,
        "purchases": purchases,
        "key_purchases": _key_purchases(purchases),
        "deaths": deaths,
        "death_count_expected": expected_deaths,
        "death_count_observed": observed_deaths,
        "death_count_missing": missing_deaths,
        "death_timeline_complete": missing_deaths == 0,
        "death_coverage_label": death_coverage_label,
        "death_gap_note": (
            f"公共数据源未提供剩余 {missing_deaths} 次死亡的分钟级事件。"
            if missing_deaths else ""
        ),
        "kills": kills,
        "assists": assists,
        "observer_wards": opendota_observer_wards,
        "sentry_wards": opendota_sentry_wards,
        "vision_events": sorted(vision_events, key=lambda item: item["time"]),
        "has_purchase_timeline": bool(purchases),
        "has_fight_log": bool(deaths or kills or assists),
        "has_vision_log": bool(vision_events),
        "missing": {
            "purchases": not bool(purchases),
            "deaths": not bool(deaths),
            "fights": not bool(deaths or kills or assists),
            "vision": not bool(vision_events),
        },
    }


def _build_post_item_windows(events, timeline, window_seconds=120):
    key_purchases = events.get("key_purchases") or []
    if not key_purchases:
        return []
    fight_events = (events.get("kills") or []) + (events.get("assists") or [])
    lh_by_minute = timeline.get("last_hits_by_minute") or []
    gold_by_minute = timeline.get("gold_by_minute") or []
    tower_by_minute = timeline.get("tower_damage_by_minute") or []
    windows = []
    for purchase in key_purchases[:8]:
        purchase_time = purchase.get("time")
        if not isinstance(purchase_time, (int, float)):
            continue
        item_name = purchase.get("item_name", "Unknown")
        start_minute = int(purchase_time // 60)
        if item_name in FARM_ACCELERATION_ITEM_NAMES:
            end_minute = start_minute + 5
            lh_gain = int(sum(lh_by_minute[start_minute:end_minute]))
            avg_gpm = _avg_slice(gold_by_minute, start_minute, end_minute)
            windows.append({
                "item_name": item_name,
                "minute": purchase.get("minute"),
                "window_type": "farm_acceleration",
                "window_label": "后5分钟刷钱",
                "lh_gain": lh_gain,
                "avg_gpm": avg_gpm,
                "summary": f"{item_name}后5分钟{lh_gain}补/{avg_gpm}GPM",
            })
            continue

        end_time = purchase_time + window_seconds
        end_minute = int(end_time // 60)
        kills_or_assists = sum(
            1 for event in fight_events
            if isinstance(event.get("time"), (int, float)) and purchase_time <= event["time"] <= end_time
        )
        tower_damage = int(sum(tower_by_minute[start_minute:end_minute]))
        windows.append({
            "item_name": item_name,
            "minute": purchase.get("minute"),
            "window_type": "map_conversion",
            "window_label": "后2分钟地图转化",
            "kills_or_assists": kills_or_assists,
            "tower_damage": tower_damage,
            "summary": f"{item_name}后2分钟参战{kills_or_assists}次/推塔{tower_damage}",
        })
    return windows


def _support_profile():
    return {
        "id": "support",
        "label": "辅助位",
        "lane_farm_sensitive": False,
        "focus": ["死亡成本", "参战", "视野", "技能释放窗口"],
    }


def _build_role_profile(context, derived=None):
    role = (context.get("role") or "").upper()
    raw_role = (context.get("raw_role") or "").upper()
    derived = derived or {}
    if "POSITION_1" in role:
        return {
            "id": "pos1",
            "label": "1号位",
            "lane_farm_sensitive": True,
            "focus": ["对线补刀", "关键装备时机", "死亡成本", "经济转地图目标"],
        }
    if "POSITION_2" in role:
        return {
            "id": "pos2",
            "label": "2号位",
            "lane_farm_sensitive": True,
            "focus": ["对线补刀", "节奏启动", "死亡成本", "经济转地图目标"],
        }
    if "POSITION_3" in role:
        return {
            "id": "pos3",
            "label": "3号位",
            "lane_farm_sensitive": False,
            "focus": ["参战率", "承伤/死亡", "先手窗口", "推塔/控图贡献"],
        }
    if "POSITION_4" in role or "POSITION_5" in role or raw_role == "SUPPORT":
        return _support_profile()

    vision_events = context.get("vision_events") or 0
    lh_per_min = derived.get("lh_per_min") or 0
    if vision_events >= 8 and lh_per_min <= 6:
        return _support_profile()

    lane = context.get("lane")
    if lane and lane.endswith("（OpenDota）"):
        return {
            "id": "unknown_lane",
            "label": f"{lane.removesuffix('（OpenDota）')}（位置未细分）",
            "lane_farm_sensitive": True,
            "focus": ["死亡成本", "经济效率", "地图目标"],
        }

    return {
        "id": "unknown",
        "label": "未知位置",
        "lane_farm_sensitive": True,
        "focus": ["死亡成本", "经济效率", "地图目标"],
    }


MAP_CONVERSION_SUCCESS_METRIC = "强势装后2分钟参战>=1或推塔伤害>=300"
FARM_ACCELERATION_SUCCESS_METRIC = "刷钱装后5分钟补刀>=40或平均GPM>=600"


def _default_training_goal(category):
    defaults = {
        "lane_farm": "下一局先把前10分钟资源路线打完整，让系统能用分钟级补刀线验收。",
        "resource_continuity": "下一局10分钟后每次集合前先推出一条安全线，减少连续断补窗口。",
        "death_review": "下一局把死亡压到每10分钟最多1次，避免连续短时间重复阵亡。",
        "item_timing": "下一局每件关键装备成型后立刻绑定一个可记录的地图动作。",
        "map_impact": "下一局把刷钱路线接到推塔、参战或控图目标上。",
        "closing": "下一局关键装备成型后30秒内给出盾、塔、双线压力三选一的明确动作。",
        "review_focus": "下一局只追踪前10分钟资源、关键装备后转化、死亡成本三项。",
    }
    return defaults.get(category, "下一局围绕本条证据执行一个可记录动作。")


def _default_success_metric(category):
    defaults = {
        "lane_farm": "10分钟补刀不低于本局；前10分钟低效率窗口=0。",
        "resource_continuity": "10分钟后低效率窗口不超过1个；单个窗口不超过2分钟。",
        "death_review": "每10分钟死亡不高于1.0；连续5分钟内死亡簇=0。",
        "item_timing": f"{FARM_ACCELERATION_SUCCESS_METRIC}；{MAP_CONVERSION_SUCCESS_METRIC}。",
        "map_impact": "参战率>=40%；关键装备后2分钟至少完成一次地图动作。",
        "closing": f"{MAP_CONVERSION_SUCCESS_METRIC}；25分钟后死亡不超过2次。",
        "review_focus": "下一份报告三项都有事件证据，且没有新增高优先级问题。",
    }
    return defaults.get(category, "下一份报告能用事件或分钟数据直接验收。")


def _finding(priority, category, evidence, why_it_matters, action, replay_check,
             training_goal=None, success_metric=None):
    return {
        "priority": priority,
        "priority_label": PRIORITY_LABELS.get(priority, priority),
        "category": category,
        "category_label": CATEGORY_LABELS.get(category, category),
        "evidence": evidence,
        "why_it_matters": why_it_matters,
        "action": action,
        "replay_check": replay_check,
        "training_goal": training_goal or _default_training_goal(category),
        "success_metric": success_metric or _default_success_metric(category),
    }


def _death_cluster_labels(deaths, gap_minutes=5):
    minutes = sorted(
        item.get("minute") for item in deaths
        if isinstance(item.get("minute"), (int, float))
    )
    if len(minutes) < 2:
        return []
    clusters = []
    current = [minutes[0]]
    for minute in minutes[1:]:
        if minute - current[-1] <= gap_minutes:
            current.append(minute)
            continue
        if len(current) >= 2:
            clusters.append(current)
        current = [minute]
    if len(current) >= 2:
        clusters.append(current)
    return [f"{cluster[0]}-{cluster[-1]}分钟" for cluster in clusters]


def _item_window_goal_details(post_windows):
    low_farm = []
    low_conversion = []
    for window in post_windows or []:
        if window.get("window_type") == "farm_acceleration":
            lh_gain = window.get("lh_gain") or 0
            avg_gpm = window.get("avg_gpm") or 0
            if lh_gain < 40 and avg_gpm < 600:
                low_farm.append(window.get("summary", ""))
        elif window.get("window_type") == "map_conversion":
            kills_or_assists = window.get("kills_or_assists") or 0
            tower_damage = window.get("tower_damage") or 0
            if kills_or_assists < 1 and tower_damage < 300:
                low_conversion.append(window.get("summary", ""))
    low_farm = [item for item in low_farm if item]
    low_conversion = [item for item in low_conversion if item]
    low_names = []
    for window in post_windows or []:
        summary = window.get("summary", "")
        if summary in low_farm or summary in low_conversion:
            low_names.append(window.get("item_name", "关键装备"))
    return {
        "low_farm": low_farm,
        "low_conversion": low_conversion,
        "low_names": low_names,
    }


def _build_review_findings(result):
    findings = []
    timeline = result.get("timeline", {})
    events = result.get("events", {})
    derived = result.get("derived", {})
    farm = result.get("farm", {})
    role_profile = result.get("role_profile", {})
    role_id = role_profile.get("id")

    if timeline.get("available") and role_profile.get("lane_farm_sensitive"):
        ten_lh = timeline.get("ten_min_last_hits")
        low_windows = timeline.get("low_efficiency_windows", [])
        early_low_windows = [w for w in low_windows if w.get("start_minute", 999) < 10]
        if ten_lh is not None and (ten_lh < 45 or early_low_windows):
            target_lh = ten_lh
            if ten_lh < 60:
                target_lh = min(60, ten_lh + 5)
            findings.append(_finding(
                "high",
                "lane_farm",
                f"10分钟补刀 {ten_lh}，前10分钟低效率窗口 {len(early_low_windows)} 个。",
                "核心位前10分钟资源会直接影响第一件关键装备和之后能否接管地图。",
                "下一局前10分钟优先保证安全线和附近野区连续收取，除非队友明确形成高胜率击杀。",
                "系统按低效率窗口标记异常分钟；结合购买/击杀事件判断是被压线、转线、参战还是刷野路线断档。",
                f"下一局先把前10分钟低效率窗口清零，再冲10分钟{target_lh}补。",
                f"10分钟补刀>={target_lh}；前10分钟低效率窗口=0。",
            ))
    elif role_id in ("pos1", "pos2", "unknown"):
        findings.append(_finding(
            "medium",
            "lane_farm",
            f"总补刀 {farm.get('last_hits', 0)}，LH/min {derived.get('lh_per_min', 0)}；缺少分钟级补刀时间线。",
            "没有时间线就无法定位对线期还是中期刷钱路线出了问题。",
            "当前报告只按总量指标给低置信度判断；后续抓取会继续请求分钟数组，拿到后自动重跑对线期诊断。",
            "系统缺少前10分钟每分钟补刀数组，暂时不能定位具体异常分钟。",
            "下一局先保证数据抓取拿到分钟级补刀线；有时间线后才对对线期下结论。",
            "数据验收：下一份报告包含10分钟补刀和前10分钟低效率窗口。",
        ))

    late_low_windows = [
        w for w in timeline.get("low_efficiency_windows", [])
        if w.get("start_minute", 0) >= 10
    ]
    if late_low_windows and role_id in ("pos1", "pos2", "unknown"):
        evidence = "；".join(
            f"{w.get('start_minute')}-{w.get('end_minute')}分钟 {w.get('avg_lh')}补/分钟"
            for w in late_low_windows[:3]
        )
        findings.append(_finding(
            "medium",
            "resource_continuity",
            f"中后期低效率窗口: {evidence}。",
            "核心位中后期长时间无补刀通常意味着死亡、被迫集合、兵线未推出或地图区域丢失。",
            "下一局中后期每次集合前先推至少一条安全线；若队伍不开雾/不控盾，优先保持两路兵线压力。",
            "系统已标记这些异常分钟，优先和死亡、购买、击杀事件时间点交叉核对。",
            f"下一局10分钟后把低效率窗口从{len(late_low_windows)}个压到最多1个；集合前先推出一条安全线。",
            "10分钟后低效率窗口不超过1个；单个低效率窗口不超过2分钟。",
        ))

    if events.get("deaths"):
        death_events = events["deaths"]
        listed_deaths = death_events if len(death_events) <= 12 else death_events[:12]
        death_minutes = ", ".join(str(item.get("minute")) for item in listed_deaths)
        if len(death_events) > len(listed_deaths):
            death_minutes += " 等"
        coverage = events.get("death_coverage_label") or f"已定位 {len(events['deaths'])} 次死亡"
        missing_note = events.get("death_gap_note")
        priority = "high" if events.get("death_count_expected", 0) >= 2 else "medium"
        evidence = (
            f"{coverage}，时间: {death_minutes}分钟；每10分钟死亡 {derived.get('deaths_per_10_min', 0)}。"
        )
        if missing_note:
            evidence += f" {missing_note}"
        cluster_labels = _death_cluster_labels(events["deaths"])
        replay_check = "系统已定位的死亡分钟优先检查装备冷却、队友距离、敌方控制威胁和撤退路线。"
        death_action = "下一局每次带线或参团前先判断敌方关键控制、己方TP支援、撤退路线和买活/盾时间。"
        if cluster_labels:
            replay_check += " 连续死亡簇: " + "、".join(cluster_labels[:4]) + "。"
            death_action = "下一局一旦死亡，复活后3分钟只接安全线、队友身边战斗或已有视野目标；再带线或参团前先确认敌方关键控制、己方TP支援和撤退路线。"
        findings.append(_finding(
            priority,
            "death_review",
            evidence,
            "核心或节奏位的连续死亡会直接交出地图区域和关键目标时间。",
            death_action,
            replay_check,
            "下一局把死亡压到每10分钟最多1次；25分钟后死亡不超过2次。",
            "每10分钟死亡不高于1.0；25分钟后死亡不超过2次；连续5分钟内死亡簇=0。",
        ))
    elif result.get("kda", {}).get("deaths", 0) > 0:
        parsed_logs = "opendota_parsed_logs" in (result.get("events", {}).get("source") or "")
        action = (
            "OpenDota 已解析但未返回 death_log 或团战死亡分钟；系统只能记录死亡总数，不能生成分钟级死亡诊断。"
            if parsed_logs else
            "系统会继续请求 OpenDota 事件日志；拿到死亡时间线后自动重跑报告。"
        )
        replay_check = (
            "当前数据源只能确认死亡总数，不能定位具体死亡分钟。"
            if parsed_logs else
            "当前缺少 death_log，系统不能计算每次死亡前30秒的地图状态和技能资源。"
        )
        findings.append(_finding(
            "medium",
            "death_review",
            f"本局死亡 {result.get('kda', {}).get('deaths', 0)} 次，但缺少死亡事件时间线。",
            "只看死亡总数无法判断是对线被抓、中期带线送节奏，还是后期团战选择错误。",
            action,
            replay_check,
            "下一局优先让系统拿到死亡时间线；拿到后按死亡分钟分阶段修正带线和参团风险。",
            "数据验收：下一份报告死亡覆盖率=100%；否则只记录数据缺口，不给分钟级死亡结论。",
        ))

    if role_id == "support":
        observer_wards = events.get("observer_wards") or []
        sentry_wards = events.get("sentry_wards") or []
        vision_total = len(observer_wards) + len(sentry_wards)
        if vision_total:
            ward_minutes = [item.get("minute") for item in (observer_wards + sentry_wards)[:8]]
            ward_text = "、".join(str(minute) for minute in ward_minutes if minute is not None)
            findings.append(_finding(
                "medium",
                "support_vision",
                f"视野事件: 观察守卫 {len(observer_wards)}，岗哨 {len(sentry_wards)}。",
                "辅助位的视野动作直接决定队伍能否安全带线、控盾、先手或反开。",
                "下一局把视野动作绑定到两类时间点：关键目标前60秒、死亡复活后的第一波出门。",
                f"系统已记录视野分钟: {ward_text}。" if ward_text else "系统已记录视野事件数量。",
                "下一局每次控盾、推塔或守高前先补一组观察/岗哨；死亡后第一波出门优先补入口视野。",
                f"观察+岗哨总数不低于{vision_total}；25分钟后每次死亡后3分钟内至少补1个视野事件。",
            ))
        else:
            findings.append(_finding(
                "medium",
                "support_vision",
                "公共数据源未提供本局眼位事件。",
                "辅助位缺少视野事件时，报告无法判断死亡是否来自视野断档或目标区被反控。",
                "下一局优先保证解析日志里出现眼位事件；系统拿到事件后会自动生成控图复盘。",
                "系统当前没有 obs_log/sen_log。",
                "下一局每个关键目标前60秒先补视野动作，让报告能记录控图节奏。",
                "数据验收：下一份报告包含观察守卫/岗哨事件。",
            ))

    if events.get("purchases"):
        key_purchases = events.get("key_purchases") or []
        evidence = "；".join(f"{item['item_name']} {item['minute']}分钟" for item in key_purchases[:4])
        post_windows = events.get("post_item_windows") or []
        if key_purchases and post_windows:
            post_summary = "；".join(item.get("summary", "") for item in post_windows[:4] if item.get("summary"))
            goal_details = _item_window_goal_details(post_windows)
            check_parts = [f"系统已计算关键装备后的对应窗口: {post_summary}"]
            if goal_details["low_farm"]:
                check_parts.append("低刷钱窗口: " + "；".join(goal_details["low_farm"][:3]))
            if goal_details["low_conversion"]:
                check_parts.append("低转化窗口: " + "；".join(goal_details["low_conversion"][:3]))
            replay_check = "；".join(check_parts) + "。"
            low_names = "、".join(goal_details["low_names"][:3])
            if low_names:
                training_goal = f"下一局 {low_names} 成型后立刻执行预设动作，避免装备完成后的空转窗口。"
            else:
                training_goal = "下一局继续保持刷钱装后不断线，强势装后立刻接推塔、参战或控图动作。"
        elif key_purchases:
            replay_check = "系统已列出关键装备时间；当前公共数据源未提供足够的击杀/推塔分钟数据计算装备后转化。"
            training_goal = "下一局关键装备成型后立刻绑定一个地图动作，让系统能在2分钟窗口内验收。"
        should_add_item_finding = bool(key_purchases and not post_windows)
        if key_purchases and post_windows:
            should_add_item_finding = bool(goal_details["low_farm"] or goal_details["low_conversion"])
        if key_purchases and should_add_item_finding:
            if role_id == "support":
                why = "辅助关键装要转成救人、反开、控图或保护关键目标，不能只停留在面板经济。"
                action = "下一局保命装或团队装完成后2分钟内完成一次守塔、做视野、反开或跟核心推进。"
                success_metric = "关键装后2分钟至少出现1次参战、推塔或视野事件；观察+岗哨总数不下降。"
            else:
                why = "刷钱装要转成连续资源增长，强势装要转成参战、推塔、控盾或逼高，否则经济只停留在面板上。"
                action = "下一局刷钱装完成后保持5分钟不断线刷线野；强势装完成后2分钟内明确一个地图动作：控盾、推塔、逼高、入侵或带线牵制。"
                success_metric = f"{FARM_ACCELERATION_SUCCESS_METRIC}；{MAP_CONVERSION_SUCCESS_METRIC}。"
            findings.append(_finding(
                "medium",
                "item_timing",
                evidence,
                why,
                action,
                replay_check,
                training_goal,
                success_metric,
            ))
    else:
        findings.append(_finding(
            "medium",
            "item_timing",
            "缺少购买时间线，只能看到最终装备。",
            "没有装备时间点就无法判断节奏慢在打钱、死亡、回家购买还是决策犹豫。",
            "当前只按最终装备给低置信度判断；后续抓取会继续请求 purchase_log，拿到后自动计算关键装备时机。",
            "系统缺少关键装备完成时间，暂时不能计算装备后2分钟内的地图转化。",
            "下一局先保证系统拿到关键购买时间线；拿到后再按装备后2/5分钟窗口验收。",
            "数据验收：下一份报告包含关键购买时间和装备后转化窗口。",
        ))

    kill_participation = derived.get("kill_participation_pct")
    if kill_participation is not None and kill_participation < 40 and result.get("duration_min", 0) >= 20:
        findings.append(_finding(
            "medium",
            "map_impact",
            f"参战率 {kill_participation}%。",
            "过低参战率说明刷钱路线和队伍目标脱节，尤其会延迟关键装备后的推进节奏。",
            "下一局把刷钱路线设计成能顺路压塔、控盾或支援队友，而不是远离目标单刷。",
            "系统检查每次队友开战时你是否能通过提前推线/TP/Blink 进入战场。",
            "下一局每条刷钱路线都要顺路覆盖一座塔、一条高价值兵线或一次支援入口。",
            "参战率>=40%；关键装备后2分钟至少完成一次参战或推塔动作。",
        ))

    if not result.get("is_win") and result.get("duration_min", 0) >= 45 and farm.get("gpm", 0) >= 600:
        key_purchases = (events.get("key_purchases") or [])[:4]
        late_deaths = [item for item in events.get("deaths", []) if item.get("minute", 0) >= 25]
        tower_windows = (timeline.get("tower_windows") or [])[:3]
        check_parts = []
        if key_purchases:
            check_parts.append("关键装备: " + "、".join(f"{item.get('item_name')} {item.get('minute')}分钟" for item in key_purchases))
        if late_deaths:
            check_parts.append("25分钟后死亡: " + "、".join(f"{item.get('minute')}分" for item in late_deaths[:6]))
        if tower_windows:
            check_parts.append("推塔窗口: " + "、".join(f"{item.get('label')} {item.get('total')}" for item in tower_windows))
        replay_check = (
            "系统已定位终结相关证据窗口：" + "；".join(check_parts) + "。"
            if check_parts else
            "系统只能确认高经济长局失利，公共数据源未提供足够目标事件窗口。"
        )
        findings.insert(0, _finding(
            "high",
            "closing",
            f"失败局时长 {result.get('duration_min', 0)} 分钟，GPM {farm.get('gpm', 0)}。",
            "高经济长局失利的问题不在打钱总量，而是关键装备窗口没有稳定转成盾、高地或关键买活差。",
            "下一局关键装备成型后主动呼叫控盾/逼塔；若无法上高，至少压两路线并逼敌方回防。",
            replay_check,
            "下一局第三件关键装后30秒内做一次明确指令：控盾、逼塔或双线压制；无法上高时持续压两路线。",
            f"{MAP_CONVERSION_SUCCESS_METRIC}；25分钟后死亡不超过2次；45分钟后低效率窗口不超过1个。",
        ))

    if not findings:
        findings.append(_finding(
            "low",
            "review_focus",
            "核心数据没有暴露明显短板。",
            "这类局要靠事件细节找增益点，而不是从总面板硬找问题。",
            "系统优先检查三个点：前10分钟资源、第一件关键装备后2分钟、每次死亡前30秒。",
            "确认是否存在可以复制到下一局的稳定习惯和需要剔除的高风险动作。",
            "下一局继续围绕前10分钟资源、关键装备后转化、死亡成本三项复查。",
            "下一份报告三项都有事件证据，且没有新增高优先级问题。",
        ))
    return findings[:5]


def _item_detail(item_id):
    items_db = _load_json("items.json")
    info = items_db.get(str(item_id), {}) if isinstance(items_db, dict) else {}
    name = ITEM_FALLBACKS.get(item_id) or info.get("display") or info.get("displayName") or info.get("name")
    return {
        "id": item_id,
        "name": name or f"Item #{item_id}",
        "cost": info.get("cost"),
        "category": info.get("category"),
    }


def _benchmark_role(context):
    role = (context.get("role") or "").upper()
    raw_role = (context.get("raw_role") or "").upper()
    if "POSITION_2" in role:
        return "mid"
    if "POSITION_1" in role or raw_role == "CORE":
        return "carry"
    return "carry"


def _build_data_quality(match_data, stratz_data, stratz_player, result, opendota_data=None):
    available = ["opendota_core_stats"]
    limitations = []
    score = 35

    if result.get("items", {}).get("final_items"):
        available.append("final_item_slots")
        score += 5
    if result.get("skills", {}).get("upgrades"):
        available.append("ability_build")
        score += 8
    if stratz_player:
        available.append("stratz_player_detail")
        score += 25
    else:
        if len(result.get("context", {}).get("ally_lineup") or []) == 5 and len(result.get("context", {}).get("enemy_lineup") or []) == 5:
            limitations.append("缺少Stratz位置字段；完整阵容已由OpenDota补齐，具体1-5号位不做推断")
        else:
            limitations.append("缺少Stratz位置字段，且OpenDota未提供完整10人阵容")

    if result.get("context", {}).get("enemy_heroes"):
        available.append("draft_context")
        score += 10

    timeline = result.get("timeline", {})
    events = result.get("events", {})
    role_profile = result.get("role_profile", {})
    has_lh_timeline = bool(match_data.get("lh_t") or timeline.get("available"))
    has_gold_timeline = bool(match_data.get("gold_t") or timeline.get("available"))
    has_purchase_log = bool(match_data.get("purchase_log") or events.get("has_purchase_timeline"))
    has_fight_log = bool(match_data.get("kills_log") or events.get("has_fight_log"))
    has_vision_log = bool(events.get("has_vision_log"))

    if has_lh_timeline and has_gold_timeline:
        available.append("lane_timeline")
        if timeline.get("source") == "opendota_parsed_logs":
            available.append("opendota_parsed_logs")
        if "stratz_playback_cs" in (timeline.get("source") or ""):
            available.append("stratz_playback_cs")
        score += 12
    else:
        limitations.append("缺少10分钟补刀/经济时间线，不能评价对线期具体失误")

    if has_purchase_log:
        available.append("purchase_timeline")
        event_source = events.get("source") or ""
        if "opendota_parsed_logs" in event_source:
            available.append("opendota_event_logs")
        if "stratz_playback" in event_source:
            available.append("stratz_playback")
        if "opendota_teamfights" in event_source:
            available.append("opendota_teamfights")
        score += 8
        if events.get("purchases") and not events.get("key_purchases"):
            limitations.append("购买时间线可用，但没有识别到关键装备完成点；装备后转化不作为本局主要问题")
    else:
        limitations.append("缺少购买时间线，不能判断关键装备时机")

    if "valve_replay" in (events.get("source") or ""):
        available.append("valve_replay_death_events")
        score += 5

    if has_fight_log:
        available.append("fight_log")
        score += 7
    else:
        limitations.append("缺少团战/击杀日志，不能还原每次死亡和团战站位")

    if has_vision_log:
        available.append("vision_events")
        score += 7

    expected_deaths = (result.get("kda") or {}).get("deaths", 0) or 0
    observed_deaths = (result.get("events") or {}).get("death_count_observed")
    if observed_deaths is None:
        observed_deaths = len((result.get("events") or {}).get("deaths") or [])
    if expected_deaths > observed_deaths:
        limitations.append(f"死亡时间线不完整：公共数据源定位{observed_deaths}/{expected_deaths}次死亡")

    if role_profile.get("id") == "support" and not has_vision_log:
        limitations.append("辅助位缺少视野事件，不能精确评价插眼/排眼质量")

    for warning in (stratz_data or {}).get("_fetch_warnings", []):
        limitations.append(f"STRATZ抓取限制: {warning}")
    for warning in (opendota_data or {}).get("_fetch_warnings", []):
        limitations.append(f"OpenDota抓取状态: {warning}")

    return {
        "score": min(score, 100),
        "available": available,
        "limitations": limitations,
    }


def _compare_with_benchmarks(farm, duration_min, role):
    benchmarks = _load_json("benchmarks.json")
    role_bench = benchmarks.get(role, {}).get("legendary", {})

    comparison = {}

    actual_lh = farm["last_hits"]
    actual_gpm = farm["gpm"]

    if duration_min >= 30:
        bench_lh = role_bench.get("30min_last_hits", {"excellent": 250, "good": 220, "average": 190, "poor": 150})
        bench_gpm = role_bench.get("30min_gpm", {"excellent": 700, "good": 620, "average": 540, "poor": 450})
    elif duration_min >= 20:
        bench_lh = role_bench.get("20min_last_hits", {"excellent": 150, "good": 130, "average": 110, "poor": 90})
        bench_gpm = role_bench.get("20min_gpm", {"excellent": 600, "good": 530, "average": 460, "poor": 380})
    else:
        bench_lh = role_bench.get("10min_last_hits", {"excellent": 65, "good": 55, "average": 45, "poor": 35})
        bench_gpm = role_bench.get("10min_gpm", {"excellent": 500, "good": 430, "average": 370, "poor": 300})

    def _rate(actual, bench):
        if actual >= bench["excellent"]:
            return "excellent"
        elif actual >= bench["good"]:
            return "good"
        elif actual >= bench["average"]:
            return "average"
        else:
            return "poor"

    comparison["last_hits"] = {
        "actual": actual_lh,
        "benchmark": bench_lh,
        "rating": _rate(actual_lh, bench_lh),
        "label": f"总补刀 ({int(duration_min)}分钟)",
    }

    comparison["gpm"] = {
        "actual": actual_gpm,
        "benchmark": bench_gpm,
        "rating": _rate(actual_gpm, bench_gpm),
        "label": "GPM",
    }

    actual_dmg = farm["hero_damage"]
    if actual_dmg > 0:
        dmg_bench = {"excellent": 40000, "good": 30000, "average": 20000, "poor": 12000}
        comparison["hero_damage"] = {
            "actual": actual_dmg,
            "benchmark": dmg_bench,
            "rating": _rate(actual_dmg, dmg_bench),
            "label": "英雄伤害",
        }

    return comparison


def _get_enemy_heroes(match_data):
    return []


def _compare_with_d2pt(result, d2pt_data):
    if not d2pt_data:
        return

    d2pt_skills = d2pt_data.get("skill_build", [])
    player_skills = result.get("skills", {}).get("upgrades", [])

    if d2pt_skills and player_skills:
        diff_count = 0
        for i, skill in enumerate(d2pt_skills):
            if i < len(player_skills):
                d2pt_id = skill.get("ability_id")
                player_id = player_skills[i].get("abilityId") or player_skills[i].get("ability_id")
                if d2pt_id != player_id:
                    diff_count += 1
        if diff_count > 0:
            result["issues"].append({
                "type": "skill_build",
                "severity": "medium",
                "message": f"你的技能加点与D2PT推荐有{diff_count}处不同",
                "details": {"diff_count": diff_count},
            })

    d2pt_talents = d2pt_data.get("talents", [])
    if d2pt_talents:
        result["d2pt_talents"] = d2pt_talents


def _generate_suggestions(result):
    if result.get("review_findings"):
        result["suggestions"] = [
            {
                "priority": finding.get("priority", "low"),
                "category": finding.get("category", "review"),
                "message": finding.get("action", ""),
            }
            for finding in result["review_findings"]
        ]
        return

    farm = result["farm"]
    duration = result["duration_min"]
    derived = result.get("derived", {})
    comparison = result.get("comparison", {})

    if duration >= 10:
        expected_lh = int(duration * 5.5)
        actual_lh = farm["last_hits"]
        lh_rating = (comparison.get("last_hits") or {}).get("rating")
        if actual_lh < expected_lh * 0.8 or lh_rating in ("poor", "average"):
            result["suggestions"].append({
                "priority": "high",
                "category": "farm",
                "message": f"补刀效率需要优先复盘: {duration}分钟{actual_lh}正补，LH/min {derived.get('lh_per_min', 0)}。先看前10分钟漏刀、拉野和刷野路线。",
            })

    if duration >= 25 and farm["hero_damage"] > 0:
        damage_per_min = derived.get("hero_damage_per_min", 0)
        if damage_per_min < 350:
            result["suggestions"].append({
                "priority": "medium",
                "category": "fight_impact",
                "message": f"英雄伤害/分钟为{damage_per_min}，偏低。复盘关键装备成型后是否及时逼塔、打盾或切入后排。",
            })

    if result["kda"]["kda_ratio"] < 2 or derived.get("deaths_per_10_min", 0) >= 1.8:
        result["suggestions"].append({
            "priority": "high",
            "category": "survival",
            "message": f"死亡成本偏高: KDA {result['kda']['kda_ratio']}，每10分钟死亡{derived.get('deaths_per_10_min', 0)}次。复盘每次死亡前30秒的小地图信息、TP/闪烁退路和敌方关键控制。",
        })

    kill_participation = derived.get("kill_participation_pct")
    if kill_participation is not None and duration >= 20 and kill_participation < 35:
        result["suggestions"].append({
            "priority": "medium",
            "category": "map_impact",
            "message": f"参战率约{kill_participation}%，偏低。确认刷钱路线是否能顺路压塔、控盾或支援队友，而不是只堆个人经济。",
        })

    if not result.get("is_win") and duration >= 45 and farm.get("gpm", 0) >= 600:
        result["suggestions"].append({
            "priority": "high",
            "category": "closing",
            "message": "高经济长局失利，优先复盘关键装备窗口：关键装备后是否控盾、带线牵制后逼高、以及买活时间内的团战选择。",
        })

    if not result.get("suggestions"):
        result["suggestions"].append({
            "priority": "low",
            "category": "review_focus",
            "message": "核心数据没有暴露明显短板。下一步应等事件解析后检查三件事：前10分钟对线资源、第一件关键装备时机、每次死亡前30秒的视野和站位。",
        })


def generate_match_summary(analyses):
    if not analyses:
        return {}

    total = len(analyses)
    wins = sum(1 for a in analyses if a.get("is_win"))
    total_kills = sum(a["kda"]["kills"] for a in analyses)
    total_deaths = sum(a["kda"]["deaths"] for a in analyses)
    total_assists = sum(a["kda"]["assists"] for a in analyses)
    avg_gpm = sum(a["farm"]["gpm"] for a in analyses) / max(total, 1)
    avg_lh = sum(a["farm"]["last_hits"] for a in analyses) / max(total, 1)

    return {
        "total_matches": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(wins / max(total, 1) * 100, 1),
        "avg_kills": round(total_kills / max(total, 1), 1),
        "avg_deaths": round(total_deaths / max(total, 1), 1),
        "avg_assists": round(total_assists / max(total, 1), 1),
        "avg_kda": round((total_kills + total_assists) / max(total_deaths, 1), 2),
        "avg_gpm": round(avg_gpm),
        "avg_lh": round(avg_lh),
    }
