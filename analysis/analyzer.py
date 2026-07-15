import ast
import json
import math
import os
import time
from datetime import datetime, timezone

from analysis.formula_engine import build_formula_diagnostics, select_formula_findings

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
ITEM_METADATA_BY_KEY = None

ITEM_FALLBACKS = {
    1: "Blink Dagger",
    7: "Javelin",
    37: "Ghost Scepter",
    48: "Mekansm",
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
    231: "Guardian Greaves",
    232: "Aether Lens",
    235: "Octarine Core",
    254: "Glimmer Cape",
    609: "Aghanim's Shard",
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
    "blink": (1, "Blink Dagger"),
    "blink_dagger": (1, "Blink Dagger"),
    "ultimate_scepter": (108, "Aghanim's Scepter"),
    "aghanims_scepter": (108, "Aghanim's Scepter"),
    "aghanims_shard": (609, "Aghanim's Shard"),
    "aether_lens": (232, "Aether Lens"),
    "force_staff": (102, "Force Staff"),
    "glimmer_cape": (254, "Glimmer Cape"),
    "ghost": (37, "Ghost Scepter"),
    "ghost_scepter": (37, "Ghost Scepter"),
    "mekansm": (48, "Mekansm"),
    "guardian_greaves": (231, "Guardian Greaves"),
    "octarine_core": (235, "Octarine Core"),
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


def _hero_name_from_npc_key(value):
    if not isinstance(value, str) or not value:
        return None
    slug = value.removeprefix("npc_dota_hero_")
    _init_hero_maps()
    for hero_id, hero_slug in HERO_ID_TO_SLUG.items():
        if hero_slug == slug:
            return HERO_ID_TO_NAME.get(hero_id)
    return None


def _item_metadata_for_key(item_key):
    global ITEM_METADATA_BY_KEY
    if not isinstance(item_key, str) or not item_key:
        return None
    if ITEM_METADATA_BY_KEY is None:
        ITEM_METADATA_BY_KEY = {}
        items_db = _load_json("items.json")
        for raw_id, info in items_db.items():
            if not isinstance(info, dict) or not info.get("name"):
                continue
            try:
                item_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            ITEM_METADATA_BY_KEY[info["name"]] = {
                "id": item_id,
                "name": info.get("display") or info["name"],
                "cost": info.get("cost"),
                "category": info.get("category"),
            }
    return ITEM_METADATA_BY_KEY.get(item_key)


def get_hero_info(hero_id, display_name=None):
    _init_hero_maps()
    return {
        "id": hero_id,
        "name": display_name or get_hero_name(hero_id),
        "slug": HERO_ID_TO_SLUG.get(hero_id, f"hero-{hero_id}"),
    }


def analyze_match(
    match_data,
    stratz_data=None,
    opendota_data=None,
    d2pt_data=None,
    replay_data=None,
):
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
        replay_data=replay_data,
    )

    result = {
        "match_id": match_data.get("match_id"),
        "hero_name": hero_name,
        "hero_id": match_data.get("hero_id"),
        "is_win": match_data.get("radiant_win") == 1 and match_data.get("is_radiant") == 1 or
                  match_data.get("radiant_win") == 0 and match_data.get("is_radiant") == 0,
        "duration_seconds": duration,
        "duration_min": round(duration_min, 1),
        "context": context,
        "data_quality": {},
        "derived": {},
        "timeline": {},
        "events": {},
        "review_findings": [],
        "role_profile": {},
        "opendota_benchmarks": {},
        "performance_context": {},
        "extended_metrics": {},
        "formula_diagnostics": {},
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

    result["skills"]["upgrades"] = _extract_ability_upgrades(
        match_data,
        stratz_player,
        replay_data=replay_data,
    )
    result["timeline"] = _build_timeline(
        match_data,
        stratz_player,
        duration_min,
        opendota_player=opendota_player,
        role_profile=result["role_profile"],
        replay_data=replay_data,
    )
    result["events"] = _build_events(
        stratz_player,
        stratz_data=stratz_data,
        opendota_player=opendota_player,
        opendota_data=opendota_data,
        final_item_ids=items,
        expected_deaths=deaths,
        expected_kills=kills,
        expected_assists=assists,
        replay_data=replay_data,
    )
    result["events"]["death_objective_windows"] = _build_death_objective_windows(result["events"])
    result["events"]["death_objective_summary"] = _summarize_death_objective_windows(
        result["events"]["death_objective_windows"]
    )
    result["events"]["death_objective_drill"] = _build_death_objective_drill(
        result["events"]["death_objective_windows"],
        deaths=result["events"].get("deaths"),
    )
    result["events"]["post_item_windows"] = _build_post_item_windows(result["events"], result["timeline"])
    result["timeline"]["death_overlap_windows"] = _build_death_overlap_windows(result["timeline"], result["events"])
    result["timeline"]["death_recovery_windows"] = _build_death_recovery_windows(result["timeline"], result["events"])
    result["timeline"]["death_resource_deltas"] = _build_death_resource_deltas(result["timeline"], result["events"])
    result["events"]["deaths"] = _attach_death_contexts_to_deaths(result["events"], result["timeline"])
    result["events"]["death_context_count"] = sum(
        1 for death in result["events"].get("deaths") or []
        if death.get("context_lines")
    )
    result["opendota_benchmarks"] = _build_opendota_benchmark_profile(opendota_player)
    result["performance_context"] = _build_opendota_performance_context(
        opendota_player,
        duration_seconds=duration,
        death_count=deaths,
        role_profile=result["role_profile"],
        stratz_player=stratz_player,
        stratz_data=stratz_data,
        replay_data=replay_data,
    )
    result["extended_metrics"] = _build_extended_metrics(
        opendota_player,
        stratz_player=stratz_player,
        replay_data=replay_data,
    )

    benchmarks = _load_json("benchmarks.json")
    role = _benchmark_role(context)
    result["comparison"] = _compare_with_benchmarks(result["farm"], duration_min, role)

    if d2pt_data:
        result["d2pt"] = d2pt_data
        _compare_with_d2pt(result, d2pt_data)

    result["data_quality"] = _build_data_quality(
        match_data,
        stratz_data,
        stratz_player,
        result,
        opendota_data=opendota_data,
        replay_data=replay_data,
    )
    result["review_findings"] = _build_review_findings(result)
    result["formula_diagnostics"] = build_formula_diagnostics(result)
    _generate_suggestions(result)

    return result


def _truthy(value):
    return value in (True, 1, "1", "true", "True")


def _known_enum(value):
    return value is not None and str(value).strip().upper() not in {"", "NONE", "UNKNOWN"}


def _valid_player_slot(value):
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and (0 <= value <= 4 or 128 <= value <= 132)
    )


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


def _build_match_context(
    match_data,
    stratz_data,
    stratz_player,
    opendota_player=None,
    opendota_data=None,
    replay_data=None,
):
    is_radiant = _truthy(match_data.get("is_radiant"))
    obs_count = len((opendota_player or {}).get("obs_log") or [])
    sen_count = len((opendota_player or {}).get("sen_log") or [])
    context = {
        "side": "Radiant" if is_radiant else "Dire",
        "hero_name": get_hero_name(match_data.get("hero_id")),
        "role": None,
        "lane": None,
        "raw_lane": None,
        "raw_role": None,
        "opendota_lane_role": (opendota_player or {}).get("lane_role"),
        "opendota_lane": (opendota_player or {}).get("lane"),
        "replay_lane_role": ((replay_data or {}).get("player") or {}).get("lane_role"),
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
        "team_resource_ranks": {},
    }

    if stratz_player:
        position = stratz_player.get("position") if _known_enum(stratz_player.get("position")) else None
        raw_role = stratz_player.get("role") if _known_enum(stratz_player.get("role")) else None
        raw_lane = stratz_player.get("lane") if _known_enum(stratz_player.get("lane")) else None
        context["role"] = position or raw_role
        context["raw_lane"] = raw_lane
        context["lane"] = {
            "SAFE_LANE": "优势路（STRATZ）",
            "MID_LANE": "中路（STRATZ）",
            "OFF_LANE": "劣势路（STRATZ）",
            "JUNGLE": "野区（STRATZ）",
        }.get(str(raw_lane or "").upper(), raw_lane)
        context["raw_role"] = raw_role
    if context["lane"] is None and context["opendota_lane_role"] in {1, 2, 3, 4}:
        lane_labels = {1: "优势路", 2: "中路", 3: "劣势路", 4: "野区"}
        context["lane"] = f"{lane_labels[context['opendota_lane_role']]}（OpenDota）"
    if context["lane"] is None and context["replay_lane_role"] in {1, 2, 3, 4}:
        lane_labels = {1: "优势路", 2: "中路", 3: "劣势路", 4: "野区"}
        context["lane"] = f"{lane_labels[context['replay_lane_role']]}（Valve回放）"

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
        valid_players = [
            player for player in players
            if isinstance(player, dict) and _valid_player_slot(player.get("player_slot"))
        ]
        ordered_players = sorted(valid_players, key=lambda player: player["player_slot"])
        radiant = [get_hero_info(player.get("hero_id")) for player in ordered_players if player["player_slot"] < 128]
        dire = [get_hero_info(player.get("hero_id")) for player in ordered_players if player["player_slot"] >= 128]
        context["ally_lineup"] = radiant if is_radiant else dire
        context["enemy_lineup"] = dire if is_radiant else radiant

        side_players = [
            player for player in valid_players
            if (player["player_slot"] < 128) == is_radiant
        ]

        def team_rank(field):
            own_value = (opendota_player or {}).get(field)
            if not isinstance(own_value, (int, float)) or isinstance(own_value, bool):
                return None
            values = [
                player.get(field) for player in side_players
                if isinstance(player.get(field), (int, float))
                and not isinstance(player.get(field), bool)
            ]
            if len(values) != len(side_players) or not values:
                return None
            return 1 + sum(value > own_value for value in values)

        vision_values = [
            (opendota_player or {}).get(field)
            for field in ("obs_placed", "sen_placed")
        ]
        vision_actions = (
            sum(int(value) for value in vision_values)
            if all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and value >= 0
                for value in vision_values
            )
            else None
        )
        context["team_resource_ranks"] = {
            "last_hits": team_rank("last_hits"),
            "gold_per_min": team_rank("gold_per_min"),
            "net_worth": team_rank("net_worth"),
            "vision_actions": vision_actions,
        }

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


def _extract_ability_upgrades(match_data, stratz_player, replay_data=None):
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

    opendota_upgrades = _parse_jsonish(match_data.get("ability_upgrades"))
    source = "opendota"
    if not opendota_upgrades:
        opendota_upgrades = list(((replay_data or {}).get("player") or {}).get("ability_upgrades") or [])
        source = "valve_replay_gem"
    upgrades = []
    for index, ability_id in enumerate(opendota_upgrades):
        if isinstance(ability_id, dict):
            ability_id = ability_id.get("abilityId") or ability_id.get("ability_id")
        if not ability_id:
            continue
        upgrades.append({
            "abilityId": ability_id,
            "level": index + 1,
            "name": ABILITY_FALLBACKS.get(ability_id, str(ability_id)),
            "source": source,
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
    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            return []
    return list(values)


def _sum_slice(values, start, end):
    return sum(values[start:min(end, len(values))])


def _avg_slice(values, start, end):
    sliced = values[start:min(end, len(values))]
    return round(sum(sliced) / len(sliced), 1) if sliced else None


def _phase_summary(label, start, end, stats):
    last_hits = stats.get("lastHitsPerMinute", [])
    minutes = max(min(end, len(last_hits)) - start, 0)
    required_end = start + minutes

    def complete_values(key):
        values = stats.get(key, [])
        if not minutes or len(values) < required_end:
            return None
        return values[start:required_end]

    lh_values = complete_values("lastHitsPerMinute") or []
    denies_values = complete_values("deniesPerMinute")
    gold_values = complete_values("goldPerMinute")
    xp_values = complete_values("experiencePerMinute")
    hero_damage_values = complete_values("heroDamagePerMinute")
    tower_damage_values = complete_values("towerDamagePerMinute")
    lh = sum(lh_values)
    return {
        "label": label,
        "minutes": minutes,
        "last_hits": int(lh),
        "denies": int(sum(denies_values)) if denies_values is not None else None,
        "lh_per_min": round(lh / minutes, 1) if minutes else 0,
        "avg_gpm": (
            round(sum(gold_values) / len(gold_values), 1)
            if gold_values else None
        ),
        "avg_xpm": (
            round(sum(xp_values) / len(xp_values), 1)
            if xp_values else None
        ),
        "hero_damage": (
            int(sum(hero_damage_values))
            if hero_damage_values is not None else None
        ),
        "tower_damage": (
            int(sum(tower_damage_values))
            if tower_damage_values is not None else None
        ),
    }


def _find_low_efficiency_windows(lh_by_min, role_profile):
    if not lh_by_min:
        return []
    if role_profile.get("id") == "support":
        return []
    threshold = 4 if role_profile.get("lane_farm_sensitive") else 2
    windows = []
    start = None
    # The first two bins include creep-spawn and lane-arrival partial minutes.
    start_index = min(2, len(lh_by_min))
    for idx in range(start_index, len(lh_by_min)):
        value = lh_by_min[idx]
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
                    "reason": "该窗口连续补刀偏少；系统只与死亡、购买和参战事件做时间重叠，不推断具体原因。",
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
    if len(numbers) < 2:
        return []
    diffs = []
    for previous, value in zip(numbers, numbers[1:]):
        delta = value - previous
        if delta < 0:
            return []
        diffs.append(delta)
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
        "valve_replay_gem": "Valve回放原始事件（gem-dota）",
    }
    if not source:
        return ""
    return " + ".join(labels.get(part, part) for part in source.split("+"))


OPENDOTA_BENCHMARK_METRICS = [
    ("gold_per_min", "GPM"),
    ("xp_per_min", "XPM"),
    ("last_hits_per_min", "补刀/分钟"),
    ("hero_damage_per_min", "英雄伤害/分钟"),
    ("tower_damage", "推塔伤害"),
    ("kills_per_min", "击杀/分钟"),
    ("hero_healing_per_min", "治疗/分钟"),
]


def _build_opendota_benchmark_profile(opendota_player):
    raw_benchmarks = (opendota_player or {}).get("benchmarks") or {}
    metrics = []
    for key, label in OPENDOTA_BENCHMARK_METRICS:
        item = raw_benchmarks.get(key)
        if not isinstance(item, dict):
            continue
        pct = item.get("pct")
        if not isinstance(pct, (int, float)):
            continue
        pct = max(0.0, min(1.0, float(pct)))
        raw = item.get("raw")
        if key == "hero_healing_per_min" and (
            not isinstance(raw, (int, float)) or raw <= 0
        ):
            continue
        percentile = int(round(pct * 100))
        metrics.append({
            "id": key,
            "label": label,
            "raw": round(raw, 2) if isinstance(raw, float) else raw,
            "pct": round(pct, 4),
            "percentile": percentile,
            "percentile_label": f"第{percentile}百分位",
            "status": "strong" if pct >= 0.7 else "weak" if pct <= 0.3 else "normal",
        })
    metrics.sort(key=lambda item: item["pct"], reverse=True)
    weak_metrics = [item for item in metrics if item["status"] == "weak"]
    strong_metrics = [item for item in metrics if item["status"] == "strong"]
    return {
        "available": bool(metrics),
        "source": "OpenDota英雄样本百分位",
        "metrics": metrics,
        "weak_metrics": weak_metrics,
        "strong_metrics": strong_metrics,
        "summary": {
            "metric_count": len(metrics),
            "weak_count": len(weak_metrics),
            "strong_count": len(strong_metrics),
        },
    }


def _format_duration_seconds(value):
    total_seconds = max(0, int(round(value)))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}分{seconds:02d}秒"


def _valid_number(value, minimum, maximum):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and minimum <= float(value) <= maximum
    )


def _stratz_team_kill_count(stratz_data, player_is_radiant):
    players = (stratz_data or {}).get("players") or []
    side_players = [
        player for player in players
        if _truthy(player.get("isRadiant")) == _truthy(player_is_radiant)
    ]
    if not side_players:
        return None
    kills = [player.get("kills") for player in side_players]
    if not all(isinstance(value, (int, float)) for value in kills):
        return None
    return int(sum(kills))


def _build_opendota_performance_context(
    opendota_player,
    duration_seconds=0,
    death_count=0,
    role_profile=None,
    stratz_player=None,
    stratz_data=None,
    replay_data=None,
):
    player = opendota_player or {}
    stratz_player = stratz_player or {}
    stratz_stats = stratz_player.get("stats") or {}
    replay_performance = (replay_data or {}).get("performance") or {}
    role_profile = role_profile or {}
    metrics = []
    metric_sources = {}

    lane_efficiency = player.get("lane_efficiency_pct")
    lane_source = "OpenDota"
    if not _valid_number(lane_efficiency, 0, 100):
        lane_ratio = player.get("lane_efficiency")
        lane_efficiency = float(lane_ratio) * 100 if _valid_number(lane_ratio, 0, 1) else None
    if lane_efficiency is None and _valid_number(
        replay_performance.get("lane_efficiency_pct"), 0, 100
    ):
        lane_efficiency = replay_performance["lane_efficiency_pct"]
        lane_source = "Valve回放"
    lane_efficiency_pct = int(round(lane_efficiency)) if lane_efficiency is not None else None
    if lane_efficiency_pct is not None:
        metric_sources["lane_efficiency_pct"] = lane_source
        lane_attention = role_profile.get("lane_farm_sensitive") and lane_efficiency_pct < 50
        metrics.append({
            "id": "lane_efficiency",
            "label": "对线效率",
            "value_label": f"{lane_efficiency_pct}%",
            "detail": f"{lane_source}返回的本局对线阶段资源效率",
            "status": "attention" if lane_attention else "strong" if lane_efficiency_pct >= 70 else "normal",
        })

    participation = player.get("teamfight_participation")
    teamfight_participation_pct = (
        int(round(float(participation) * 100))
        if _valid_number(participation, 0, 1)
        else None
    )
    participation_source = "OpenDota"
    if teamfight_participation_pct is None:
        replay_participation = replay_performance.get("teamfight_participation")
        if _valid_number(replay_participation, 0, 1):
            teamfight_participation_pct = int(round(float(replay_participation) * 100))
            participation_source = "Valve回放"
    if teamfight_participation_pct is None:
        team_kills = _stratz_team_kill_count(
            stratz_data,
            stratz_player.get("isRadiant"),
        )
        kills = stratz_player.get("kills")
        assists = stratz_player.get("assists")
        if not isinstance(kills, (int, float)):
            kills = player.get("kills")
        if not isinstance(assists, (int, float)):
            assists = player.get("assists")
        if (
            isinstance(team_kills, int) and team_kills > 0
            and isinstance(kills, (int, float))
            and isinstance(assists, (int, float))
        ):
            teamfight_participation_pct = int(round(
                (float(kills) + float(assists)) / team_kills * 100
            ))
            participation_source = "STRATZ记分板"
    if teamfight_participation_pct is not None:
        metric_sources["teamfight_participation_pct"] = participation_source
        metrics.append({
            "id": "teamfight_participation",
            "label": "参战率",
            "value_label": f"{teamfight_participation_pct}%",
            "detail": f"{participation_source}的本局击杀参与汇总",
            "status": "attention" if teamfight_participation_pct < 40 else "strong" if teamfight_participation_pct >= 65 else "normal",
        })

    dead_time = player.get("life_state_dead")
    dead_time_seconds = int(round(dead_time)) if _valid_number(dead_time, 0, 86400) else None
    dead_time_source = "OpenDota"
    if dead_time_seconds is None and _valid_number(
        replay_performance.get("life_state_dead"), 0, 86400
    ):
        dead_time_seconds = int(round(replay_performance["life_state_dead"]))
        dead_time_source = "Valve回放"
    if dead_time_seconds is None and isinstance(stratz_stats.get("deathEvents"), list):
        observed_dead_times = [
            event.get("timeDead")
            for event in stratz_stats.get("deathEvents") or []
            if isinstance(event, dict) and _valid_number(event.get("timeDead"), 0, 3600)
        ]
        if observed_dead_times or death_count == 0:
            dead_time_seconds = int(round(sum(observed_dead_times)))
            dead_time_source = "STRATZ死亡事件"
    dead_time_share_pct = None
    average_dead_time = None
    if dead_time_seconds is not None:
        metric_sources["dead_time_seconds"] = dead_time_source
        if _valid_number(duration_seconds, 1, 86400):
            dead_time_share_pct = round((dead_time_seconds / float(duration_seconds)) * 100, 1)
        if death_count:
            average_dead_time = int(round(dead_time_seconds / death_count))
        detail_parts = []
        if dead_time_share_pct is not None:
            detail_parts.append(f"占全局{dead_time_share_pct}%")
        if average_dead_time is not None:
            detail_parts.append(f"每次死亡平均{average_dead_time}秒")
        metrics.append({
            "id": "dead_time",
            "label": "死亡占时",
            "value_label": _format_duration_seconds(dead_time_seconds),
            "detail": " · ".join(detail_parts) or f"{dead_time_source}记录的本局死亡总时长",
            "status": (
                "attention" if dead_time_share_pct is not None and dead_time_share_pct >= 18
                else "strong" if dead_time_share_pct is not None and dead_time_share_pct <= 8
                else "normal"
            ),
        })

    buybacks = player.get("buyback_count")
    buyback_source = "OpenDota"
    if buybacks is None and _valid_number(
        replay_performance.get("buyback_count"), 0, 100
    ):
        buybacks = replay_performance["buyback_count"]
        buyback_source = "Valve回放"
    buyback_count = int(buybacks) if _valid_number(buybacks, 0, 100) else None
    if buyback_count is not None:
        metric_sources["buyback_count"] = buyback_source
        metrics.append({
            "id": "buybacks",
            "label": "买活次数",
            "value_label": f"{buyback_count}次",
            "detail": f"{buyback_source}记录的本局买活次数",
            "status": "normal",
        })

    source_names = []
    for source in metric_sources.values():
        if source not in source_names:
            source_names.append(source)
    if source_names == ["OpenDota"]:
        source_label = "OpenDota对局汇总字段"
    else:
        source_label = " + ".join(source_names) if source_names else None
    return {
        "available": bool(metrics),
        "source": source_label,
        "metric_sources": metric_sources,
        "lane_efficiency_pct": lane_efficiency_pct,
        "teamfight_participation_pct": teamfight_participation_pct,
        "dead_time_seconds": dead_time_seconds,
        "dead_time_label": _format_duration_seconds(dead_time_seconds) if dead_time_seconds is not None else None,
        "dead_time_share_pct": dead_time_share_pct,
        "average_dead_time_per_death_seconds": average_dead_time,
        "buyback_count": buyback_count,
        "metrics": metrics,
    }


def _numeric_total(values):
    if not isinstance(values, dict):
        return 0
    return round(sum(
        float(value)
        for value in values.values()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ), 2)


def _top_usage(values, limit=8):
    if not isinstance(values, dict):
        return []
    rows = [
        {"name": str(name), "count": value}
        for name, value in values.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    rows.sort(key=lambda item: (-item["count"], item["name"]))
    return rows[:limit]


def _average_number_list(values):
    values = [
        float(value) for value in values or []
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    if not values:
        return None
    average = round(sum(values) / len(values), 1)
    return int(average) if average.is_integer() else average


def _last_number(values):
    numbers = [
        value for value in values or []
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return numbers[-1] if numbers else None


def _stratz_usage_map(rows, *, ability=False):
    usage = {}
    for row in rows or []:
        if not isinstance(row, dict) or not isinstance(row.get("count"), (int, float)):
            continue
        identifier = row.get("abilityId") if ability else row.get("itemId")
        if not identifier:
            continue
        if ability:
            name = ABILITY_FALLBACKS.get(identifier, f"Ability #{identifier}")
        else:
            name = _item_detail(identifier).get("name") or f"Item #{identifier}"
        usage[name] = usage.get(name, 0) + row["count"]
    return usage


def _build_extended_metrics(opendota_player, stratz_player=None, replay_data=None):
    player = opendota_player or {}
    stratz_player = stratz_player or {}
    stats = stratz_player.get("stats") or {}
    replay_extended = (replay_data or {}).get("extended") or {}
    damage_taken = player.get("damage_taken") if isinstance(player.get("damage_taken"), dict) else {}
    hero_damage_taken = {
        name: value
        for name, value in damage_taken.items()
        if str(name).startswith("npc_dota_hero_")
    }
    observed_fields = [
        field for field in (
            "actions_per_min", "stuns", "damage_taken", "obs_placed", "sen_placed",
            "observer_kills", "sentry_kills", "camps_stacked", "rune_pickups",
            "courier_kills", "tower_kills", "roshan_kills", "buyback_count",
            "buyback_log", "gold_spent", "total_gold", "item_uses", "ability_uses",
        )
        if field in player and player.get(field) is not None
    ]
    sources = ["OpenDota"] if observed_fields else []

    def with_replay(field, value):
        if value is None and replay_extended.get(field) is not None:
            observed_fields.append(field)
            sources.append("Valve回放")
            return replay_extended[field]
        return value

    if not damage_taken and isinstance(replay_extended.get("damage_taken"), dict):
        damage_taken = dict(replay_extended["damage_taken"])
        hero_damage_taken = {
            name: value
            for name, value in damage_taken.items()
            if str(name).startswith("npc_dota_hero_")
        }
        observed_fields.append("damage_taken")
        sources.append("Valve回放")

    actions_per_min = player.get("actions_per_min")
    if actions_per_min is None:
        actions_per_min = _average_number_list(stats.get("actionsPerMinute"))
        if actions_per_min is not None:
            observed_fields.append("actions_per_min")
            sources.append("STRATZ")
    actions_per_min = with_replay("actions_per_min", actions_per_min)

    camps_stacked = player.get("camps_stacked")
    if camps_stacked is None:
        camps_stacked = _last_number(stats.get("campStack"))
        if camps_stacked is not None:
            observed_fields.append("camps_stacked")
            sources.append("STRATZ")
    camps_stacked = with_replay("camps_stacked", camps_stacked)

    rune_pickups = player.get("rune_pickups")
    if rune_pickups is None and isinstance(stats.get("runes"), list):
        rune_pickups = sum(
            str(event.get("action") or "").upper() == "PICKUP"
            for event in stats.get("runes") or []
            if isinstance(event, dict)
        )
        observed_fields.append("rune_pickups")
        sources.append("STRATZ")
    rune_pickups = with_replay("rune_pickups", rune_pickups)

    courier_kills = player.get("courier_kills")
    if courier_kills is None and isinstance(stats.get("courierKills"), list):
        courier_kills = len(stats.get("courierKills") or [])
        observed_fields.append("courier_kills")
        sources.append("STRATZ")
    courier_kills = with_replay("courier_kills", courier_kills)

    stratz_hero_damage_taken = None
    if isinstance(stats.get("heroDamageReceivedPerMinute"), list):
        stratz_hero_damage_taken = round(sum(
            value for value in stats.get("heroDamageReceivedPerMinute") or []
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ), 2)
        observed_fields.append("hero_damage_received")
        sources.append("STRATZ")

    wards = stats.get("wards") if isinstance(stats.get("wards"), list) else None
    observer_placed = player.get("obs_placed")
    sentry_placed = player.get("sen_placed")
    if wards is not None:
        if observer_placed is None:
            observer_placed = sum(event.get("type") == 0 for event in wards if isinstance(event, dict))
            observed_fields.append("obs_placed")
        if sentry_placed is None:
            sentry_placed = sum(event.get("type") == 1 for event in wards if isinstance(event, dict))
            observed_fields.append("sen_placed")
        sources.append("STRATZ")
    observer_placed = with_replay("obs_placed", observer_placed)
    sentry_placed = with_replay("sen_placed", sentry_placed)

    ward_destruction = stats.get("wardDestruction") if isinstance(stats.get("wardDestruction"), list) else None
    total_wards_destroyed = None
    if ward_destruction is not None:
        total_wards_destroyed = len(ward_destruction)
        observed_fields.append("ward_destruction")
        sources.append("STRATZ")

    gold_spent = player.get("gold_spent")
    if gold_spent is None and isinstance(stratz_player.get("goldSpent"), (int, float)):
        gold_spent = stratz_player.get("goldSpent")
        observed_fields.append("gold_spent")
        sources.append("STRATZ")
    gold_spent = with_replay("gold_spent", gold_spent)

    item_usage = player.get("item_uses")
    if not isinstance(item_usage, dict) and isinstance(stats.get("itemUsed"), list):
        item_usage = _stratz_usage_map(stats.get("itemUsed"))
        observed_fields.append("item_uses")
        sources.append("STRATZ")
    if not isinstance(item_usage, dict) and isinstance(replay_extended.get("item_uses"), dict):
        item_usage = dict(replay_extended["item_uses"])
        observed_fields.append("item_uses")
        sources.append("Valve回放")

    ability_usage = player.get("ability_uses")
    if not isinstance(ability_usage, dict) and isinstance(stats.get("abilityCastReport"), list):
        ability_usage = _stratz_usage_map(stats.get("abilityCastReport"), ability=True)
        observed_fields.append("ability_uses")
        sources.append("STRATZ")
    if not isinstance(ability_usage, dict) and isinstance(replay_extended.get("ability_uses"), dict):
        ability_usage = dict(replay_extended["ability_uses"])
        observed_fields.append("ability_uses")
        sources.append("Valve回放")

    stuns = with_replay("stuns", player.get("stuns"))
    observer_destroyed = with_replay("observer_kills", player.get("observer_kills"))
    sentry_destroyed = with_replay("sentry_kills", player.get("sentry_kills"))
    buyback_count = with_replay("buyback_count", player.get("buyback_count"))
    total_gold = with_replay("total_gold", player.get("total_gold"))
    tower_kills = with_replay("tower_kills", player.get("tower_kills"))
    roshan_kills = with_replay("roshan_kills", player.get("roshan_kills"))
    hero_healing = with_replay("hero_healing", player.get("hero_healing"))

    observed_fields = list(dict.fromkeys(observed_fields))
    sources = list(dict.fromkeys(sources))
    if sources == ["OpenDota"]:
        source_label = "OpenDota解析后的玩家扩展字段"
    else:
        source_label = " + ".join(sources) if sources else None
    return {
        "available": bool(observed_fields),
        "source": source_label,
        "observed_fields": observed_fields,
        "combat": {
            "stuns_seconds": stuns,
            "total_damage_taken": (
                _numeric_total(damage_taken)
                if "damage_taken" in observed_fields else None
            ),
            "hero_damage_taken": (
                _numeric_total(hero_damage_taken)
                if hero_damage_taken else stratz_hero_damage_taken
            ),
            "hero_damage_taken_by_source": _top_usage(hero_damage_taken),
            "max_hero_hit": player.get("max_hero_hit"),
            "hero_healing": hero_healing,
        },
        "economy": {
            "gold_spent": gold_spent,
            "total_gold": total_gold,
            "buyback_count": buyback_count,
            "buyback_log": list(player.get("buyback_log") or []),
        },
        "vision": {
            "observer_placed": observer_placed,
            "sentry_placed": sentry_placed,
            "observer_destroyed": observer_destroyed,
            "sentry_destroyed": sentry_destroyed,
            "total_destroyed": (
                observer_destroyed + sentry_destroyed
                if observer_destroyed is not None and sentry_destroyed is not None
                else total_wards_destroyed
            ),
        },
        "activity": {
            "actions_per_min": actions_per_min,
            "camps_stacked": camps_stacked,
            "rune_pickups": rune_pickups,
            "courier_kills": courier_kills,
            "pings": player.get("pings"),
        },
        "objectives": {
            "tower_kills": tower_kills,
            "roshan_kills": roshan_kills,
        },
        "usage": {
            "top_item_uses": _top_usage(item_usage),
            "top_ability_uses": _top_usage(ability_usage),
        },
    }


def _event_source_label(source):
    labels = {
        "opendota_parsed_logs": "OpenDota解析日志",
        "opendota_opponent_kill_logs": "OpenDota对手击杀日志交叉核对",
        "opendota_death_positions": "OpenDota团战死亡坐标",
        "opendota_objectives": "OpenDota目标事件",
        "opendota_teamfights": "OpenDota团战事件",
        "opendota_vision": "OpenDota视野事件",
        "stratz_playback": "STRATZ回放事件",
        "stratz_stats": "STRATZ解析事件",
        "stratz_tower_deaths": "STRATZ建筑死亡事件",
        "stratz_position_samples": "STRATZ位置采样",
        "valve_replay": "Valve回放事件",
        "valve_replay_gem": "Valve回放原始事件（gem-dota）",
        "valve_replay_position_sample": "Valve回放实体位置采样",
    }
    if not source:
        return "未获取"
    return " + ".join(labels.get(part, part) for part in source.split("+"))


def _build_timeline(
    match_data,
    stratz_player,
    duration_min,
    opendota_player=None,
    role_profile=None,
    replay_data=None,
):
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
    replay_timeline = (replay_data or {}).get("timeline") or {}
    replay_normalized = {
        "lastHitsPerMinute": _as_number_list(replay_timeline.get("last_hits_per_minute")),
        "deniesPerMinute": _as_number_list(replay_timeline.get("denies_per_minute")),
        "goldPerMinute": _as_number_list(replay_timeline.get("gold_per_minute")),
        "experiencePerMinute": _as_number_list(replay_timeline.get("experience_per_minute")),
        "heroDamagePerMinute": _as_number_list(replay_timeline.get("hero_damage_per_minute")),
        "towerDamagePerMinute": _as_number_list(replay_timeline.get("tower_damage_per_minute")),
    }
    timeline_keys = (
        "lastHitsPerMinute",
        "deniesPerMinute",
        "goldPerMinute",
        "experiencePerMinute",
        "heroDamagePerMinute",
        "towerDamagePerMinute",
    )
    normalized = {}
    source_parts = []
    for key in timeline_keys:
        candidates = [
            ("opendota_parsed_logs", (opendota_stats or {}).get(key)),
            ("stratz_stats", stratz_normalized.get(key)),
        ]
        if key == "lastHitsPerMinute":
            candidates.append(("stratz_playback_cs", (playback_cs_stats or {}).get(key)))
        candidates.append(("valve_replay_gem", replay_normalized.get(key)))
        source_name, value = next(
            ((candidate_source, candidate_value) for candidate_source, candidate_value in candidates if candidate_value),
            (None, []),
        )
        normalized[key] = value or []
        if source_name and source_name not in source_parts:
            source_parts.append(source_name)
    source = "+".join(source_parts) if source_parts else None
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
        "ten_min_last_hits": (
            int(_sum_slice(lh_by_min, 0, 10)) if len(lh_by_min) >= 10 else None
        ),
        "twenty_min_last_hits": int(_sum_slice(lh_by_min, 0, 20)) if len(lh_by_min) >= 20 else None,
        "ten_min_denies": (
            int(_sum_slice(normalized["deniesPerMinute"], 0, 10))
            if len(normalized["deniesPerMinute"]) >= 10 else None
        ),
        "twenty_min_avg_gpm": (
            _avg_slice(normalized["goldPerMinute"], 0, 20)
            if len(normalized["goldPerMinute"]) >= 20 else None
        ),
        "phases": phases,
        "low_efficiency_windows": _find_low_efficiency_windows(lh_by_min, role_profile),
        "damage_windows": _top_windows(normalized["heroDamagePerMinute"], "输出窗口"),
        "tower_windows": _top_windows(normalized["towerDamagePerMinute"], "推塔窗口"),
        "last_hits_by_minute": lh_by_min,
        "gold_by_minute": normalized["goldPerMinute"],
        "experience_by_minute": normalized["experiencePerMinute"],
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
            item_detail = _item_detail(item_id) if item_id else {}
            item["item_id"] = item_id
            item["item_name"] = item_detail.get("name") if item_id else "Unknown"
            item["item_cost"] = item_detail.get("cost")
            item["item_category"] = item_detail.get("category")
        if source:
            item["source"] = source
        normalized.append(item)
    return sorted(normalized, key=lambda item: item["time"])


def _normalize_buyback_events(events, source):
    normalized = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        event_time = event.get("time")
        if not isinstance(event_time, (int, float)) or event_time < 0:
            continue
        item = {
            "time": int(event_time),
            "minute": round(event_time / 60, 1),
            "source": source,
        }
        for key in ("slot", "player_slot"):
            if event.get(key) is not None:
                item[key] = event[key]
        normalized.append(item)
    return sorted(normalized, key=lambda item: item["time"])


def _normalize_replay_purchase_events(events):
    normalized = []
    for event in events or []:
        if not isinstance(event, dict) or not isinstance(event.get("time"), (int, float)):
            continue
        item_key = str(event.get("item_key") or "").removeprefix("item_")
        metadata = _item_metadata_for_key(item_key) or {}
        normalized.append({
            "time": event["time"],
            "minute": round(event["time"] / 60, 1),
            "item_id": metadata.get("id"),
            "item_name": metadata.get("name") or item_key or "Unknown",
            "item_cost": metadata.get("cost"),
            "item_category": metadata.get("category"),
            "source": "valve_replay_gem",
        })
    return sorted(normalized, key=lambda item: item["time"])


def _normalize_replay_nearby_context(value):
    if not isinstance(value, dict):
        return None
    if value.get("sampled_other_players") != 9:
        return None
    normalized = {
        key: value.get(key)
        for key in (
            "source",
            "radius_units",
            "sample_resolution_seconds",
            "sampled_other_players",
            "coverage_complete",
            "allies_within_radius_count",
            "enemies_within_radius_count",
        )
        if value.get(key) is not None
    }

    def normalize_player(item):
        if not isinstance(item, dict):
            return None
        player = dict(item)
        hero_id = player.get("hero_id")
        if isinstance(hero_id, int) and not isinstance(hero_id, bool):
            player["hero_name"] = get_hero_name(hero_id)
        return player

    for key in ("allies_within_radius", "enemies_within_radius"):
        normalized[key] = [
            player
            for player in (normalize_player(item) for item in value.get(key) or [])
            if player
        ]
    for key in ("nearest_ally", "nearest_enemy"):
        normalized[key] = normalize_player(value.get(key))
    return normalized


def _normalize_replay_death_events(events):
    normalized = []
    for event in events or []:
        if not isinstance(event, dict) or not isinstance(event.get("time"), (int, float)):
            continue
        item = {
            "time": event["time"],
            "minute": round(event["time"] / 60, 1),
            "source": "valve_replay_gem",
        }
        for key in (
            "killer",
            "world_position",
            "sample_tick",
            "sample_delta_seconds",
            "time_dead",
            "death_state_started_at",
            "respawn_observed_at",
            "death_state_alignment_seconds",
            "time_dead_source",
            "time_dead_resolution_seconds",
        ):
            if event.get(key) is not None:
                item[key] = event[key]
        killer_name = _hero_name_from_npc_key(item.get("killer"))
        if killer_name:
            item["killer_hero_name"] = killer_name
        nearby_context = _normalize_replay_nearby_context(event.get("nearby_context"))
        if nearby_context:
            item["nearby_context"] = nearby_context
        position = event.get("position") or {}
        x = _clean_position_value(position.get("x"))
        y = _clean_position_value(position.get("y"))
        if x is not None and y is not None:
            item["position"] = {"x": x, "y": y}
            item["position_source"] = (
                event.get("position_source") or "valve_replay_position_sample"
            )
            sample_delta = event.get("sample_delta_seconds")
            if isinstance(sample_delta, (int, float)) and not isinstance(sample_delta, bool):
                item["position_sample_age_seconds"] = abs(float(sample_delta))
            item["position_label"] = _death_position_label(
                item["position"],
                item.get("position_sample_age_seconds"),
            )
        normalized.append(item)
    return sorted(normalized, key=lambda item: item["time"])


def _normalize_replay_vision_events(events):
    observer = []
    sentry = []
    for event in events or []:
        if not isinstance(event, dict) or not isinstance(event.get("time"), (int, float)):
            continue
        ward_type = str(event.get("type") or "").lower()
        item = {
            "time": event["time"],
            "minute": round(event["time"] / 60, 1),
            "ward_type": ward_type,
            "source": "valve_replay_gem",
        }
        position = event.get("position") or {}
        x = _clean_position_value(position.get("x"))
        y = _clean_position_value(position.get("y"))
        if x is not None and y is not None:
            item["position"] = {"x": x, "y": y}
        if ward_type == "observer":
            observer.append(item)
        elif ward_type == "sentry":
            sentry.append(item)
    return observer, sentry


def _normalize_stratz_combat_events(events, *, source="stratz_stats"):
    normalized = []
    for event in events or []:
        if not isinstance(event, dict) or not isinstance(event.get("time"), (int, float)):
            continue
        item = {
            "time": event["time"],
            "minute": round(event["time"] / 60, 1),
            "source": source,
        }
        for source_key, target_key in (
            ("target", "target"),
            ("byAbility", "ability_id"),
            ("byItem", "item_id"),
            ("gold", "gold"),
            ("xp", "xp"),
            ("isSolo", "is_solo"),
            ("isGank", "is_gank"),
            ("isInvisible", "is_invisible"),
            ("isSmoke", "is_smoke"),
            ("isTpRecently", "tp_recently"),
        ):
            if event.get(source_key) is not None:
                item[target_key] = event[source_key]
        x = _clean_position_value(event.get("positionX"))
        y = _clean_position_value(event.get("positionY"))
        if x is not None and y is not None:
            item["position"] = {"x": x, "y": y}
        normalized.append(item)
    return sorted(normalized, key=lambda item: item["time"])


def _normalize_stratz_death_events(events, source="stratz_stats"):
    normalized = []
    for event in events or []:
        if not isinstance(event, dict) or not isinstance(event.get("time"), (int, float)):
            continue
        item = {
            "time": event["time"],
            "minute": round(event["time"] / 60, 1),
            "source": source,
        }
        for source_key, target_key in (
            ("attacker", "killer_hero_id"),
            ("target", "target"),
            ("byAbility", "ability_id"),
            ("byItem", "item_id"),
            ("goldFed", "gold_fed"),
            ("xpFed", "xp_fed"),
            ("timeDead", "time_dead"),
            ("goldLost", "gold_lost"),
            ("isWardWalkThrough", "ward_walk_through"),
            ("isAttemptTpOut", "attempted_tp_out"),
            ("isDieBack", "dieback"),
            ("isBurst", "burst_death"),
            ("isEngagedOnDeath", "engaged_on_death"),
            ("hasHealAvailable", "heal_available"),
            ("isTracked", "tracked"),
        ):
            if event.get(source_key) is not None:
                item[target_key] = event[source_key]
        if isinstance(item.get("killer_hero_id"), int):
            item["killer_hero_name"] = get_hero_name(item["killer_hero_id"])
        x = _clean_position_value(event.get("positionX"))
        y = _clean_position_value(event.get("positionY"))
        if x is not None and y is not None:
            position = {"x": x, "y": y}
            item.update({
                "position": position,
                "position_source": "stratz_stats",
                "position_sample_age_seconds": 0,
                "position_label": _death_position_label(position, 0),
            })
        normalized.append(item)
    return sorted(normalized, key=lambda item: item["time"])


def _normalize_stratz_vision_events(events):
    observer = []
    sentry = []
    for event in events or []:
        if not isinstance(event, dict) or not isinstance(event.get("time"), (int, float)):
            continue
        ward_type = "observer" if event.get("type") == 0 else "sentry" if event.get("type") == 1 else None
        if not ward_type:
            continue
        item = {
            "time": event["time"],
            "minute": round(event["time"] / 60, 1),
            "ward_type": ward_type,
            "source": "stratz_stats",
        }
        x = _clean_position_value(event.get("positionX"))
        y = _clean_position_value(event.get("positionY"))
        if x is not None and y is not None:
            item["position"] = {"x": x, "y": y}
        (observer if ward_type == "observer" else sentry).append(item)
    return observer, sentry


def _build_stratz_vision_summary(stats):
    wards = stats.get("wards")
    destroyed = stats.get("wardDestruction")
    if not isinstance(wards, list) and not isinstance(destroyed, list):
        return {"available": False}
    observer = (
        sum(event.get("type") == 0 for event in wards if isinstance(event, dict))
        if isinstance(wards, list) else None
    )
    sentry = (
        sum(event.get("type") == 1 for event in wards if isinstance(event, dict))
        if isinstance(wards, list) else None
    )
    return {
        "available": True,
        "observer_placed": observer,
        "sentry_placed": sentry,
        "placed_total": observer + sentry if observer is not None and sentry is not None else None,
        "observer_kills": None,
        "sentry_kills": None,
        "kill_total": len(destroyed) if isinstance(destroyed, list) else None,
        "source": "stratz_stats",
    }


def _normalize_opendota_purchase_events(events):
    normalized = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        minute = _event_minute(event)
        if minute is None:
            continue
        key = event.get("key")
        fallback = ITEM_KEY_FALLBACKS.get(key)
        metadata = _item_metadata_for_key(key)
        if fallback:
            item_id, item_name = fallback
            item_detail = _item_detail(item_id)
        elif metadata:
            item_id = metadata["id"]
            item_name = metadata["name"]
            item_detail = metadata
        else:
            item_id = None
            item_name = key.replace("_", " ").title() if isinstance(key, str) else "Unknown"
            item_detail = {}
        normalized.append({
            "time": event.get("time"),
            "minute": minute,
            "item_key": key,
            "item_id": item_id,
            "item_name": item_name,
            "item_cost": item_detail.get("cost"),
            "item_category": item_detail.get("category"),
            "source": "opendota",
        })
    return sorted(normalized, key=lambda item: item["time"])


def _normalize_opendota_timed_events(events):
    normalized = _normalize_timed_events(events)
    for item in normalized:
        item["source"] = "opendota"
    return normalized


def _clean_position_value(value):
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    return int(value) if float(value).is_integer() else round(value, 1)


def _normalize_position_events(events, source="stratz"):
    normalized = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        event_time = event.get("time")
        x = _clean_position_value(event.get("x"))
        y = _clean_position_value(event.get("y"))
        if not isinstance(event_time, (int, float)) or x is None or y is None:
            continue
        normalized.append({
            "time": event_time,
            "minute": round(event_time / 60, 1),
            "x": x,
            "y": y,
            "source": source,
        })
    return sorted(normalized, key=lambda item: item["time"])


def _flatten_opendota_deaths_pos(deaths_pos):
    positions = []
    if not isinstance(deaths_pos, dict):
        return positions
    for raw_x, y_values in deaths_pos.items():
        x = _clean_position_value(raw_x)
        if x is None:
            continue
        iterable = y_values.items() if isinstance(y_values, dict) else [(y_values, 1)]
        for raw_y, raw_count in iterable:
            y = _clean_position_value(raw_y)
            if y is None:
                continue
            try:
                count = max(int(raw_count), 1)
            except (TypeError, ValueError):
                count = 1
            positions.extend({"x": x, "y": y} for _ in range(count))
    return positions


def _normalize_opendota_death_position_events(opendota_data, opendota_player):
    if not opendota_data or not opendota_player:
        return []
    player_index = opendota_player.get("_player_index")
    if player_index is None:
        return []
    normalized = []
    for fight in opendota_data.get("teamfights") or []:
        players = fight.get("players") or []
        if not isinstance(player_index, int) or player_index < 0 or player_index >= len(players):
            continue
        player_fight = players[player_index] or {}
        positions = _flatten_opendota_deaths_pos(player_fight.get("deaths_pos"))
        player_death_count = player_fight.get("deaths")
        if len(positions) != 1 or (
            isinstance(player_death_count, (int, float)) and int(player_death_count) != 1
        ):
            continue
        fight_start = fight.get("start")
        fight_end = fight.get("end")
        if not isinstance(fight_start, (int, float)) or not isinstance(fight_end, (int, float)):
            continue
        event_time = fight.get("last_death") or fight.get("end") or fight.get("start")
        if not isinstance(event_time, (int, float)):
            continue
        position = positions[0]
        normalized.append({
            "time": event_time,
            "minute": round(event_time / 60, 1),
            "fight_start": fight_start,
            "fight_end": fight_end,
            "x": position["x"],
            "y": position["y"],
            "source": "opendota_death_positions",
            "direct_death_position": True,
        })
    return sorted(normalized, key=lambda item: item["time"])


def _death_position_label(position, age_seconds):
    if not position:
        return ""
    if age_seconds is None:
        age_text = "采样时间差未返回"
    else:
        age_text = "死亡时" if age_seconds == 0 else f"死亡前{age_seconds}秒"
    return f"x={position.get('x')},y={position.get('y')}（{age_text}）"


def _attach_position_samples_to_deaths(deaths, position_events, max_age_seconds=45):
    if not deaths or not position_events:
        return deaths
    enriched = []
    for death in deaths:
        item = dict(death)
        if item.get("position"):
            enriched.append(item)
            continue
        death_time = item.get("time")
        if not isinstance(death_time, (int, float)):
            enriched.append(item)
            continue
        candidates = [
            event for event in position_events
            if event.get("time") <= death_time and death_time - event.get("time") <= max_age_seconds
        ]
        if candidates:
            sample = candidates[-1]
            age = int(round(death_time - sample["time"]))
            position = {"x": sample["x"], "y": sample["y"]}
            item["position"] = position
            item["position_source"] = sample.get("source")
            item["position_sample_time"] = sample.get("time")
            item["position_sample_age_seconds"] = age
            item["position_label"] = _death_position_label(position, age)
        enriched.append(item)
    return enriched


def _attach_direct_death_positions_to_deaths(deaths, position_events):
    if not deaths or not position_events:
        return deaths
    enriched = [dict(death) for death in deaths]
    used_deaths = set()
    for sample in position_events:
        fight_start = sample.get("fight_start")
        fight_end = sample.get("fight_end")
        if not isinstance(fight_start, (int, float)) or not isinstance(fight_end, (int, float)):
            continue
        candidates = []
        for index, item in enumerate(enriched):
            if index in used_deaths or item.get("position"):
                continue
            death_time = item.get("time")
            if not isinstance(death_time, (int, float)):
                continue
            if fight_start <= death_time <= fight_end:
                candidates.append((index, item))
        if len(candidates) != 1:
            continue
        death_index, item = candidates[0]
        used_deaths.add(death_index)
        death_time = item["time"]
        position = {"x": sample["x"], "y": sample["y"]}
        item["position"] = position
        item["position_source"] = sample.get("source")
        item["position_sample_time"] = sample.get("time")
        item["position_sample_delta_seconds"] = int(round(sample["time"] - death_time))
        item["position_sample_age_seconds"] = 0
        item["position_label"] = _death_position_label(position, 0)
    return enriched


def _build_death_map_points(deaths):
    points = []
    for death in deaths or []:
        position = death.get("position") or {}
        x = _clean_position_value(position.get("x"))
        y = _clean_position_value(position.get("y"))
        if x is None or y is None:
            continue
        plot_x = max(0, min(255, x))
        plot_y = 255 - max(0, min(255, y))
        minute = death.get("minute")
        if minute is None and isinstance(death.get("time"), (int, float)):
            minute = round(death["time"] / 60, 1)
        label_prefix = f"{minute}分 " if minute is not None else ""
        points.append({
            "minute": minute,
            "x": x,
            "y": y,
            "plot_x": plot_x,
            "plot_y": plot_y,
            "label": f"{label_prefix}x={x},y={y}",
            "position_label": death.get("position_label") or _death_position_label({"x": x, "y": y}, 0),
        })
    return points


def _distance_between_points(left, right):
    return ((left["x"] - right["x"]) ** 2 + (left["y"] - right["y"]) ** 2) ** 0.5


def _format_minute_list(minutes):
    return "、".join(str(minute) for minute in minutes if minute is not None)


def _build_death_position_clusters(points, radius=14):
    clusters = []
    used = set()
    for index, point in enumerate(points or []):
        if index in used:
            continue
        members = [
            (member_index, member)
            for member_index, member in enumerate(points or [])
            if member_index not in used and _distance_between_points(point, member) <= radius
        ]
        if len(members) < 2:
            continue
        member_points = [member for _, member in members]
        for member_index, _ in members:
            used.add(member_index)
        center_x = round(sum(member["x"] for member in member_points) / len(member_points), 1)
        center_y = round(sum(member["y"] for member in member_points) / len(member_points), 1)
        minutes = [member.get("minute") for member in member_points if member.get("minute") is not None]
        minutes_text = _format_minute_list(minutes)
        label_prefix = f"{minutes_text}分" if minutes_text else f"{len(member_points)}次"
        clusters.append({
            "death_count": len(member_points),
            "minutes": minutes,
            "minutes_label": f"{minutes_text}分" if minutes_text else "",
            "center_x": center_x,
            "center_y": center_y,
            "plot_x": max(0, min(255, center_x)),
            "plot_y": 255 - max(0, min(255, center_y)),
            "radius": radius,
            "points": [member.get("label") for member in member_points if member.get("label")],
            "evidence_label": (
                f"{label_prefix}重复死亡坐标簇，中心x={center_x},y={center_y}，"
                f"样本{len(member_points)}次"
            ),
        })
    return sorted(clusters, key=lambda item: (-item["death_count"], item["minutes"][0] if item["minutes"] else 999))


def _annotate_death_position_cluster_members(deaths, clusters):
    if not deaths or not clusters:
        return deaths or []
    annotated = [dict(item) for item in deaths]
    minute_to_indexes = {}
    for index, death in enumerate(annotated):
        minute = death.get("minute")
        if minute is None and isinstance(death.get("time"), (int, float)):
            minute = round(death["time"] / 60, 1)
        if minute is None:
            continue
        minute_to_indexes.setdefault(minute, []).append(index)

    for cluster_index, cluster in enumerate(clusters, start=1):
        label = f"重复簇 #{cluster_index} 中心x={cluster['center_x']},y={cluster['center_y']}"
        for minute in cluster.get("minutes") or []:
            for death_index in minute_to_indexes.get(minute, []):
                annotated[death_index]["position_cluster_id"] = cluster_index
                annotated[death_index]["position_cluster_label"] = label
    return annotated


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


VISION_SUMMARY_KEYS = (
    "obs_placed",
    "sen_placed",
    "observer_kills",
    "sentry_kills",
    "observer_uses",
    "sentry_uses",
)


def _build_opendota_vision_summary(opendota_player):
    if not isinstance(opendota_player, dict):
        return {"available": False}

    summary = {}
    for key in VISION_SUMMARY_KEYS:
        value = opendota_player.get(key)
        summary[key] = (
            int(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else None
        )
    summary["available"] = any(
        summary.get(key) is not None for key in VISION_SUMMARY_KEYS
    )
    placed_values = (summary.get("obs_placed"), summary.get("sen_placed"))
    summary["placed_total"] = (
        sum(placed_values) if all(value is not None for value in placed_values) else None
    )
    kill_values = (summary.get("observer_kills"), summary.get("sentry_kills"))
    summary["kill_total"] = (
        sum(kill_values) if all(value is not None for value in kill_values) else None
    )
    return summary


def _vision_coverage_label(events):
    vision_events = events.get("vision_events") or []
    vision_summary = events.get("vision_summary") or {}
    if not events.get("has_vision_log"):
        return "未获取插眼/排眼事件"

    parts = []
    if vision_events:
        parts.append(f"{len(vision_events)}条插眼事件")
    if vision_summary.get("available"):
        if vision_summary.get("placed_total") is not None:
            parts.append(f"插眼{vision_summary['placed_total']}个")
        else:
            if vision_summary.get("obs_placed") is not None:
                parts.append(f"观察眼{vision_summary['obs_placed']}个")
            if vision_summary.get("sen_placed") is not None:
                parts.append(f"岗哨{vision_summary['sen_placed']}个")
        if vision_summary.get("kill_total") is not None:
            parts.append(f"排眼{vision_summary['kill_total']}个")
        else:
            if vision_summary.get("observer_kills") is not None:
                parts.append(f"排观察眼{vision_summary['observer_kills']}个")
            if vision_summary.get("sentry_kills") is not None:
                parts.append(f"排岗哨{vision_summary['sentry_kills']}个")
    return "；".join(parts) if parts else "OpenDota已解析，个人视野事件0条"


KEY_ITEM_IDS = {1, 37, 48, 65, 108, 110, 116, 119, 135, 139, 145, 147, 160, 208, 231, 232, 235, 254, 609}
KEY_ITEM_NAMES = {
    "Aether Lens",
    "Aghanim's Scepter",
    "Aghanim's Shard",
    "Battle Fury",
    "Black King Bar",
    "Blink Dagger",
    "Manta Style",
    "Abyssal Blade",
    "Eye of Skadi",
    "Butterfly",
    "Force Staff",
    "Ghost Scepter",
    "Glimmer Cape",
    "Guardian Greaves",
    "Monkey King Bar",
    "Mekansm",
    "Hand of Midas",
    "Lotus Orb",
    "Octarine Core",
    "Refresher Orb",
    "Scythe of Vyse",
    "Shiva's Guard",
}
MAJOR_ITEM_MIN_COST = 1800
NON_MAJOR_ITEM_CATEGORIES = {"component", "consumable"}
FARM_ACCELERATION_ITEM_NAMES = {
    "Battle Fury",
    "Hand of Midas",
    "Maelstrom",
    "Manta Style",
    "Mjollnir",
    "Radiance",
}
MAP_CONVERSION_ITEM_NAMES = {
    "Abyssal Blade",
    "Black King Bar",
    "Blink Dagger",
    "Refresher Orb",
    "Scythe of Vyse",
}

PRIORITY_LABELS = {
    "high": "高优先级",
    "medium": "中优先级",
    "low": "低优先级",
}

CATEGORY_LABELS = {
    "closing": "终结比赛",
    "lane_farm": "前10分钟资源",
    "resource_continuity": "中后期资源连续性",
    "death_resource_overlap": "死亡打断资源",
    "death_recovery": "死亡后恢复",
    "death_resource_delta": "死亡前后资源变化",
    "death_position_pattern": "重复死亡坐标",
    "death_objective_window": "死亡后目标损失",
    "buyback_redeath": "买活后再次阵亡",
    "death_review": "死亡成本",
    "item_timing": "装备后转化",
    "map_impact": "地图影响力",
    "support_vision": "视野/控图",
    "hero_benchmark_gap": "英雄样本短板",
    "review_focus": "复盘重点",
}


def _key_purchases(purchases, final_item_ids=None):
    result = []
    seen = set()
    final_item_ids = {int(item_id) for item_id in final_item_ids or [] if item_id}
    for item in purchases:
        item_id = item.get("item_id")
        item_name = item.get("item_name")
        item_detail = _item_detail(item_id) if item_id else {}
        item_cost = item.get("item_cost")
        if not isinstance(item_cost, (int, float)):
            item_cost = item_detail.get("cost")
        item_category = item.get("item_category") or item_detail.get("category")
        curated = item_id in KEY_ITEM_IDS or item_name in KEY_ITEM_NAMES
        final_inventory_major = (
            item_id in final_item_ids
            and isinstance(item_cost, (int, float))
            and item_cost >= MAJOR_ITEM_MIN_COST
            and item_category not in NON_MAJOR_ITEM_CATEGORIES
        )
        if curated or final_inventory_major:
            key = ("id", item_id) if item_id else ("name", item_name)
            if key not in seen:
                normalized = dict(item)
                normalized["item_cost"] = item_cost
                normalized["item_category"] = item_category
                normalized["selection_reason"] = (
                    "curated_key_item" if curated else "final_inventory_major_item"
                )
                result.append(normalized)
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
            })
    return sorted(deaths, key=lambda item: item["time"])


def _extract_deaths_from_opponent_kill_logs(opendota_data, opendota_player):
    if not isinstance(opendota_data, dict) or not isinstance(opendota_player, dict):
        return []
    hero_id = opendota_player.get("hero_id")
    if not isinstance(hero_id, int):
        return []
    hero_slug = get_hero_info(hero_id).get("slug")
    if not hero_slug:
        return []
    target_key = f"npc_dota_hero_{hero_slug}"
    target_index = opendota_player.get("_player_index")
    deaths = []
    for player_index, killer in enumerate(opendota_data.get("players") or []):
        if not isinstance(killer, dict) or player_index == target_index:
            continue
        killer_hero_id = killer.get("hero_id")
        for event in killer.get("kills_log") or []:
            if not isinstance(event, dict) or event.get("key") != target_key:
                continue
            event_time = event.get("time")
            if not isinstance(event_time, (int, float)):
                continue
            deaths.append({
                "time": event_time,
                "minute": round(event_time / 60, 1),
                "source": "opendota_opponent_kill_logs",
                "killer_hero_id": killer_hero_id,
                "killer_hero_name": (
                    get_hero_name(killer_hero_id)
                    if isinstance(killer_hero_id, int)
                    else None
                ),
            })
    return sorted(deaths, key=lambda item: item["time"])


def _objective_building_label(key):
    key = str(key or "")
    lane = next((label for token, label in (
        ("_top", "上路"),
        ("_mid", "中路"),
        ("_bot", "下路"),
    ) if token in key), "")
    if "tower1" in key:
        return f"{lane}一塔", "tower"
    if "tower2" in key:
        return f"{lane}二塔", "tower"
    if "tower3" in key:
        return f"{lane}高地塔", "tower"
    if "tower4" in key:
        return "基地塔", "tower"
    if "melee_rax" in key:
        return f"{lane}近战兵营", "barracks"
    if "range_rax" in key:
        return f"{lane}远程兵营", "barracks"
    if key.endswith("_fort"):
        return "遗迹", "ancient"
    return "建筑目标", "building"


_STRATZ_BUILDING_LABELS = {
    16: ("上路一塔", "tower"),
    17: ("中路一塔", "tower"),
    18: ("下路一塔", "tower"),
    19: ("上路二塔", "tower"),
    20: ("中路二塔", "tower"),
    21: ("下路二塔", "tower"),
    22: ("上路高地塔", "tower"),
    23: ("中路高地塔", "tower"),
    24: ("下路高地塔", "tower"),
    25: ("基地塔", "tower"),
    26: ("上路一塔", "tower"),
    27: ("中路一塔", "tower"),
    28: ("下路一塔", "tower"),
    29: ("上路二塔", "tower"),
    30: ("中路二塔", "tower"),
    31: ("下路二塔", "tower"),
    32: ("上路高地塔", "tower"),
    33: ("中路高地塔", "tower"),
    34: ("下路高地塔", "tower"),
    35: ("基地塔", "tower"),
    36: ("基地塔", "tower"),
    37: ("基地塔", "tower"),
    38: ("上路近战兵营", "barracks"),
    39: ("中路近战兵营", "barracks"),
    40: ("下路近战兵营", "barracks"),
    41: ("上路远程兵营", "barracks"),
    42: ("中路远程兵营", "barracks"),
    43: ("下路远程兵营", "barracks"),
    44: ("上路近战兵营", "barracks"),
    45: ("中路近战兵营", "barracks"),
    46: ("下路近战兵营", "barracks"),
    47: ("上路远程兵营", "barracks"),
    48: ("中路远程兵营", "barracks"),
    49: ("下路远程兵营", "barracks"),
    50: ("遗迹", "ancient"),
    51: ("遗迹", "ancient"),
}


def _normalize_stratz_tower_objectives(stratz_data, stratz_player):
    player_is_radiant = (stratz_player or {}).get("isRadiant")
    if not isinstance(player_is_radiant, bool):
        return []
    player_hero_id = ((stratz_player or {}).get("hero") or {}).get("id")
    normalized = []
    for event in (stratz_data or {}).get("towerDeaths") or []:
        if not isinstance(event, dict):
            continue
        event_time = event.get("time")
        building_is_radiant = event.get("isRadiant")
        if (
            not isinstance(event_time, (int, float))
            or event_time < 0
            or not isinstance(building_is_radiant, bool)
        ):
            continue
        label, kind = _STRATZ_BUILDING_LABELS.get(
            event.get("npcId"),
            ("建筑目标", "building"),
        )
        outcome = "lost" if building_is_radiant == player_is_radiant else "gained"
        player_direct = (
            isinstance(player_hero_id, int)
            and event.get("attacker") == player_hero_id
        )
        normalized.append({
            "time": event_time,
            "minute": round(event_time / 60, 1),
            "kind": kind,
            "label": label,
            "outcome": outcome,
            "outcome_label": "我方获取" if outcome == "gained" else "我方失去",
            "display_label": f"{'获取' if outcome == 'gained' else '失去'}{label}",
            "team": "Radiant" if not building_is_radiant else "Dire",
            "player_direct": player_direct,
            "direct_label": (
                (
                    "本人最后一击（敌方建筑）"
                    if outcome == "gained"
                    else "本人完成己方建筑反补"
                )
                if player_direct else None
            ),
            "source": "stratz_tower_deaths",
            "raw_type": "stratz_tower_death",
            "raw_key": event.get("npcId"),
        })
    return sorted(normalized, key=lambda item: item["time"])


def _normalize_opendota_objectives(opendota_data, opendota_player):
    player_slot = (opendota_player or {}).get("player_slot")
    if not isinstance(player_slot, int):
        return []
    player_is_radiant = player_slot < 128
    normalized = []
    for event in (opendota_data or {}).get("objectives") or []:
        if not isinstance(event, dict):
            continue
        event_time = event.get("time")
        event_type = event.get("type")
        if not isinstance(event_time, (int, float)) or event_time < 0:
            continue

        objective_team_is_radiant = None
        kind = None
        label = None
        direct_label = None
        if event_type == "building_kill":
            key = str(event.get("key") or "")
            if "badguys" in key:
                objective_team_is_radiant = True
            elif "goodguys" in key:
                objective_team_is_radiant = False
            else:
                continue
            label, kind = _objective_building_label(key)
            direct_label = "本人最后一击"
        elif event_type == "CHAT_MESSAGE_ROSHAN_KILL":
            objective_team_is_radiant = event.get("team") == 2
            kind = "roshan"
            label = "肉山"
        elif event_type == "CHAT_MESSAGE_AEGIS":
            holder_slot = event.get("player_slot")
            if not isinstance(holder_slot, int):
                continue
            objective_team_is_radiant = holder_slot < 128
            kind = "aegis"
            label = "不朽盾"
            direct_label = "本人持盾"
        elif event_type == "CHAT_MESSAGE_MINIBOSS_KILL":
            if event.get("team") not in (2, 3):
                continue
            objective_team_is_radiant = event.get("team") == 2
            kind = "tormentor"
            label = "折磨者"
        else:
            continue

        outcome = "gained" if objective_team_is_radiant == player_is_radiant else "lost"
        event_player_slot = event.get("player_slot")
        player_direct = isinstance(event_player_slot, int) and event_player_slot == player_slot
        if event_type == "building_kill" and player_direct:
            direct_label = (
                "本人最后一击（敌方建筑）"
                if outcome == "gained"
                else "本人完成己方建筑反补"
            )
        normalized.append({
            "time": event_time,
            "minute": round(event_time / 60, 1),
            "kind": kind,
            "label": label,
            "outcome": outcome,
            "outcome_label": "我方获取" if outcome == "gained" else "我方失去",
            "display_label": f"{'获取' if outcome == 'gained' else '失去'}{label}",
            "team": "Radiant" if objective_team_is_radiant else "Dire",
            "player_direct": player_direct,
            "direct_label": direct_label if player_direct else None,
            "source": "opendota_objectives",
            "raw_type": event_type,
            "raw_key": event.get("key"),
        })
    return sorted(normalized, key=lambda item: item["time"])


def _build_death_objective_windows(events, max_after_seconds=90):
    deaths = events.get("deaths") or []
    lost_objectives = [
        item for item in events.get("objectives") or []
        if item.get("outcome") == "lost"
    ]
    windows = []
    for death in deaths:
        death_time = death.get("time")
        if not isinstance(death_time, (int, float)):
            continue
        for objective in lost_objectives:
            objective_time = objective.get("time")
            if not isinstance(objective_time, (int, float)):
                continue
            elapsed = objective_time - death_time
            if elapsed < 0 or elapsed > max_after_seconds:
                continue
            death_minute = death.get("minute")
            if death_minute is None:
                death_minute = round(death_time / 60, 1)
            elapsed_seconds = int(round(elapsed))
            evidence_label = (
                f"{death_minute}分死亡 → {objective.get('minute')}分"
                f"{objective.get('display_label')}（{elapsed_seconds}秒）"
            )
            windows.append({
                "death_time": death_time,
                "death_minute": death_minute,
                "objective_time": objective_time,
                "objective_minute": objective.get("minute"),
                "objective_kind": objective.get("kind"),
                "objective_label": objective.get("label"),
                "objective_display_label": objective.get("display_label"),
                "elapsed_seconds": elapsed_seconds,
                "evidence_label": evidence_label,
                "source": f"{objective.get('source') or 'objective_events'}+death_events",
            })
    return sorted(windows, key=lambda item: (item["death_time"], item["objective_time"]))


def _build_buyback_death_windows(buybacks, deaths, short_window_seconds=120):
    death_events = sorted(
        (
            item for item in deaths or []
            if isinstance(item.get("time"), (int, float))
        ),
        key=lambda item: item["time"],
    )
    windows = []
    for buyback in buybacks or []:
        buyback_time = buyback.get("time")
        if not isinstance(buyback_time, (int, float)):
            continue
        next_death = next(
            (item for item in death_events if item["time"] > buyback_time),
            None,
        )
        redeath_seconds = (
            int(next_death["time"] - buyback_time)
            if next_death else None
        )
        windows.append({
            "buyback_time": int(buyback_time),
            "buyback_minute": round(buyback_time / 60, 1),
            "death_time": int(next_death["time"]) if next_death else None,
            "death_minute": next_death.get("minute") if next_death else None,
            "redeath_seconds": redeath_seconds,
            "short_window_seconds": int(short_window_seconds),
            "short_redeath": (
                redeath_seconds is not None
                and redeath_seconds <= short_window_seconds
            ),
            "source": "+".join(sorted({
                str(buyback.get("source") or "buyback_events"),
                str((next_death or {}).get("source") or "death_events"),
            })),
        })
    return windows


_DEATH_OBJECTIVE_KIND_WEIGHTS = {
    "ancient": 6,
    "barracks": 5,
    "roshan": 4,
    "aegis": 4,
    "tower": 3,
    "tormentor": 2,
}


def _death_objective_kind_weight(window):
    return _DEATH_OBJECTIVE_KIND_WEIGHTS.get(window.get("objective_kind"), 1)


def _death_objective_focus_score(window):
    return (
        _death_objective_kind_weight(window),
        -int(window.get("elapsed_seconds") or 999),
    )


def _objective_drill_focus_label(display_label):
    label = str(display_label or "关键目标")
    for prefix in ("失去", "获取"):
        if label.startswith(prefix):
            label = label[len(prefix):]
            break
    if "肉山" in label or "不朽盾" in label:
        return "肉山争夺"
    if "遗迹" in label or "基地塔" in label:
        return "基地防守"
    if "兵营" in label or "高地" in label:
        return "高地防守"
    if "塔" in label:
        return f"{label}攻防"
    return label


def _build_death_objective_drill(windows, deaths=None):
    if not windows:
        return None

    windows_by_death = {}
    for index, window in enumerate(windows):
        death_time = window.get("death_time")
        group_key = ("time", death_time) if death_time is not None else ("row", index)
        windows_by_death.setdefault(group_key, []).append(window)

    def group_score(group):
        elapsed_values = [
            int(item.get("elapsed_seconds"))
            for item in group
            if isinstance(item.get("elapsed_seconds"), (int, float))
        ]
        return (
            sum(_death_objective_kind_weight(item) for item in group),
            len(group),
            -min(elapsed_values or [999]),
        )

    focus_windows = max(windows_by_death.values(), key=group_score)
    focus_windows = sorted(
        focus_windows,
        key=lambda item: (
            item.get("objective_time") is None,
            item.get("objective_time") or 0,
        ),
    )
    focus = max(focus_windows, key=_death_objective_focus_score)
    objective_label = _objective_drill_focus_label(focus.get("objective_display_label"))
    evidence = "；".join(
        str(item.get("evidence_label"))
        for item in focus_windows
        if item.get("evidence_label")
    )
    focus_death = next(
        (
            death for death in deaths or []
            if isinstance(death.get("time"), (int, float))
            and isinstance(focus.get("death_time"), (int, float))
            and abs(death["time"] - focus["death_time"]) <= 1
        ),
        None,
    )
    nearby = (focus_death or {}).get("nearby_context") or {}
    radius = nearby.get("radius_units") or 1600
    ally_count = nearby.get("allies_within_radius_count")
    enemy_count = nearby.get("enemies_within_radius_count")
    nearest_ally = nearby.get("nearest_ally") or {}
    nearest_enemy = nearby.get("nearest_enemy") or {}
    if isinstance(ally_count, int) and isinstance(enemy_count, int):
        checklist = [{
            "label": "局部人数",
            "check": f"死亡瞬间{int(radius)}范围内存活队友{ally_count}人、敌人{enemy_count}人。",
        }]
        if nearest_ally.get("distance_units") is not None:
            checklist.append({
                "label": "最近队友",
                "check": (
                    f"{nearest_ally.get('hero_name') or f'玩家{nearest_ally.get('player_id')}'}，"
                    f"距离{nearest_ally['distance_units']}单位。"
                ),
            })
        if nearest_enemy.get("distance_units") is not None:
            checklist.append({
                "label": "最近敌人",
                "check": (
                    f"{nearest_enemy.get('hero_name') or f'玩家{nearest_enemy.get('player_id')}'}，"
                    f"距离{nearest_enemy['distance_units']}单位。"
                ),
            })
        local_rule = (
            f"目标前90秒保持至少1名存活队友处于{int(radius)}范围；"
            "若可见敌人多于附近队友，停止先手并向最近队友方向撤退。"
        )
        local_check = (
            f" 焦点死亡局部人数：队友{ally_count}人、敌人{enemy_count}人；"
            "该数据由Valve回放全员位置与生命状态自动计算。"
        )
        local_metric = f"；目标相关死亡中{int(radius)}范围敌多于友为0次"
    else:
        checklist = [{
            "label": "局部人数数据",
            "check": "全员位置采样未获取，本项不作判断。",
        }]
        local_rule = "目标前90秒停止单独深入，保持与最近队友同一推进区域。"
        local_check = " 全员位置采样未获取，系统不判断未采集的支援距离、敌人数量或撤退路线。"
        local_metric = ""
    return {
        "title": "目标前90秒生存规则",
        "focus_objective": objective_label,
        "focus_death_time": focus.get("death_time"),
        "focus_death_minute": focus.get("death_minute"),
        "focus_window_count": len(focus_windows),
        "focus_severity_points": sum(
            _death_objective_kind_weight(item) for item in focus_windows
        ),
        "evidence": evidence,
        "trigger": f"下一局每次准备参与{objective_label}或同级关键目标前90秒",
        "rule": local_rule,
        "checklist": checklist,
        "training_goal": f"下一局执行「目标前90秒生存规则」，把围绕{objective_label}的死亡/目标损失窗口清零。",
        "success_metric": f"死亡后90秒内失去目标窗口为0{local_metric}。",
        "replay_check": (
            f"系统证据窗口：{evidence}；系统只自动验收死亡与目标事件的时间窗口。"
            f"{local_check}"
        ),
        "window_count": len(windows),
    }


def _summarize_death_objective_windows(windows):
    return {
        "window_count": len(windows),
        "unique_death_count": len({item.get("death_time") for item in windows}),
        "unique_objective_count": len({
            (item.get("objective_time"), item.get("objective_kind")) for item in windows
        }),
    }


def _select_complete_event_log(candidates, expected_count=0):
    available = [candidate for candidate in candidates if candidate[0]]
    if not available:
        return [], None
    expected = int(expected_count or 0)
    events, source, _priority = max(
        available,
        key=lambda candidate: (
            bool(expected and len(candidate[0]) == expected),
            min(len(candidate[0]), expected or len(candidate[0])),
            candidate[2],
        ),
    )
    return events, source


def _build_death_cost_summary(deaths):
    cost_events = [
        event for event in deaths or []
        if any(event.get(field) is not None for field in (
            "time_dead", "gold_lost", "gold_fed", "xp_fed",
        ))
    ]
    timed_events = [
        event for event in cost_events
        if isinstance(event.get("time_dead"), (int, float))
    ]
    gold_lost_events = [
        event for event in cost_events
        if isinstance(event.get("gold_lost"), (int, float))
    ]
    gold_fed_events = [
        event for event in cost_events
        if isinstance(event.get("gold_fed"), (int, float))
    ]
    xp_fed_events = [
        event for event in cost_events
        if isinstance(event.get("xp_fed"), (int, float))
    ]
    source_labels = []
    if any(
        event.get("time_dead_source") == "valve_replay_life_state"
        for event in timed_events
    ):
        source_labels.append("Valve回放逐秒生命状态")
    if any(
        event.get("source") == "stratz_stats"
        for event in cost_events
    ):
        source_labels.append("STRATZ死亡事件")
    return {
        "available": bool(cost_events),
        "covered_deaths": len(cost_events),
        "time_covered_deaths": len(timed_events),
        "gold_lost_covered_deaths": len(gold_lost_events),
        "gold_fed_covered_deaths": len(gold_fed_events),
        "xp_fed_covered_deaths": len(xp_fed_events),
        "dead_time_available": bool(timed_events),
        "gold_lost_available": bool(gold_lost_events),
        "gold_fed_available": bool(gold_fed_events),
        "xp_fed_available": bool(xp_fed_events),
        "total_dead_seconds": (
            int(sum(event["time_dead"] for event in timed_events))
            if timed_events else None
        ),
        "total_gold_lost": (
            int(sum(event["gold_lost"] for event in gold_lost_events))
            if gold_lost_events else None
        ),
        "total_gold_fed": (
            int(sum(event["gold_fed"] for event in gold_fed_events))
            if gold_fed_events else None
        ),
        "total_xp_fed": (
            int(sum(event["xp_fed"] for event in xp_fed_events))
            if xp_fed_events else None
        ),
        "dieback_count": sum(bool(event.get("dieback")) for event in cost_events),
        "burst_death_count": sum(bool(event.get("burst_death")) for event in cost_events),
        "engaged_death_count": sum(bool(event.get("engaged_on_death")) for event in cost_events),
        "source": "+".join(source_labels) if source_labels else None,
    }


def _build_events(
    stratz_player,
    stratz_data=None,
    opendota_player=None,
    opendota_data=None,
    final_item_ids=None,
    expected_deaths=0,
    expected_kills=0,
    expected_assists=0,
    replay_data=None,
):
    playback = (stratz_player or {}).get("playbackData") or {}
    stratz_stats = (stratz_player or {}).get("stats") or {}
    purchase_payload_available = (
        isinstance((opendota_player or {}).get("purchase_log"), list)
        or isinstance(stratz_stats.get("itemPurchases"), list)
        or isinstance(playback.get("purchaseEvents"), list)
        or isinstance((replay_data or {}).get("purchases"), list)
    )
    buyback_payload_available = (
        isinstance((opendota_player or {}).get("buyback_log"), list)
        or isinstance((replay_data or {}).get("buybacks"), list)
    )
    fight_payload_available = any(
        isinstance(value, list)
        for value in (
            (opendota_player or {}).get("kills_log"),
            (opendota_player or {}).get("assists_log"),
            (opendota_player or {}).get("assist_log"),
            stratz_stats.get("killEvents"),
            stratz_stats.get("assistEvents"),
            playback.get("killEvents"),
            playback.get("assistEvents"),
            (replay_data or {}).get("kills"),
            (replay_data or {}).get("assists"),
        )
    )
    vision_event_payload_available = (
        (
            isinstance((opendota_player or {}).get("obs_log"), list)
            and isinstance((opendota_player or {}).get("sen_log"), list)
        )
        or isinstance(stratz_stats.get("wards"), list)
        or isinstance((replay_data or {}).get("vision_events"), list)
    )
    opendota_objective_payload_available = (
        isinstance(opendota_data, dict)
        and isinstance(opendota_data.get("objectives"), list)
    )
    stratz_objective_payload_available = (
        isinstance(stratz_data, dict)
        and isinstance(stratz_data.get("towerDeaths"), list)
        and bool(stratz_data.get("parsedDateTime"))
    )
    replay_objective_payload_available = (
        isinstance(replay_data, dict)
        and isinstance(replay_data.get("objectives"), list)
    )
    objective_payload_available = (
        opendota_objective_payload_available
        or replay_objective_payload_available
        or stratz_objective_payload_available
    )
    stratz_purchases = _normalize_timed_events(playback.get("purchaseEvents"), item_events=True, source="stratz")
    stratz_deaths = _normalize_stratz_death_events(
        playback.get("deathEvents"),
        source="stratz",
    )
    stratz_kills = _normalize_timed_events(playback.get("killEvents"), source="stratz")
    stratz_assists = _normalize_timed_events(playback.get("assistEvents"), source="stratz")
    stratz_stats_purchases = _normalize_timed_events(
        stratz_stats.get("itemPurchases"),
        item_events=True,
        source="stratz_stats",
    )
    stratz_stats_deaths = _normalize_stratz_death_events(stratz_stats.get("deathEvents"))
    stratz_stats_kills = _normalize_stratz_combat_events(stratz_stats.get("killEvents"))
    stratz_stats_assists = _normalize_stratz_combat_events(stratz_stats.get("assistEvents"))
    stratz_observer_wards, stratz_sentry_wards = _normalize_stratz_vision_events(
        stratz_stats.get("wards")
    )
    stratz_vision_summary = _build_stratz_vision_summary(stratz_stats)
    replay_purchases = _normalize_replay_purchase_events((replay_data or {}).get("purchases"))
    replay_deaths = _normalize_replay_death_events((replay_data or {}).get("deaths"))
    replay_kills = _normalize_stratz_combat_events(
        (replay_data or {}).get("kills"),
        source="valve_replay_gem",
    )
    replay_assists = _normalize_stratz_combat_events(
        (replay_data or {}).get("assists"),
        source="valve_replay_gem",
    )
    replay_buybacks = _normalize_buyback_events(
        (replay_data or {}).get("buybacks"),
        "valve_replay_gem",
    )
    replay_observer_wards, replay_sentry_wards = _normalize_replay_vision_events(
        (replay_data or {}).get("vision_events")
    )
    stratz_positions = _normalize_position_events(
        playback.get("playerUpdatePositionEvents"),
        source="stratz_position_samples",
    )
    opendota_death_positions = []

    opendota_purchases = []
    opendota_deaths = []
    opendota_opponent_kill_deaths = []
    opendota_teamfight_deaths = []
    opendota_kills = []
    opendota_assists = []
    opendota_buybacks = []
    opendota_observer_wards = []
    opendota_sentry_wards = []
    vision_summary = {"available": False}
    valve_replay_deaths = _normalize_timed_events(
        (opendota_data or {}).get("replay_death_events"),
        source="valve_replay",
    )
    if opendota_player:
        opendota_purchases = _normalize_opendota_purchase_events(opendota_player.get("purchase_log"))
        opendota_deaths = _normalize_opendota_timed_events(opendota_player.get("death_log"))
        opendota_opponent_kill_deaths = _extract_deaths_from_opponent_kill_logs(
            opendota_data,
            opendota_player,
        )
        opendota_teamfight_deaths = _extract_deaths_from_teamfights(opendota_data, opendota_player)
        opendota_kills = _normalize_opendota_timed_events(opendota_player.get("kills_log"))
        opendota_assists = _normalize_opendota_timed_events(
            opendota_player.get("assists_log") or opendota_player.get("assist_log")
        )
        opendota_buybacks = _normalize_buyback_events(
            opendota_player.get("buyback_log"),
            "opendota_parsed_logs",
        )
        opendota_death_positions = _normalize_opendota_death_position_events(opendota_data, opendota_player)
        opendota_observer_wards = _normalize_opendota_vision_events(opendota_player.get("obs_log"), "observer")
        opendota_sentry_wards = _normalize_opendota_vision_events(opendota_player.get("sen_log"), "sentry")
        vision_summary = _build_opendota_vision_summary(opendota_player)

    source_parts = set()
    if opendota_objective_payload_available:
        objectives = _normalize_opendota_objectives(opendota_data, opendota_player)
        objective_source = "opendota_objectives"
        objective_coverage_scope = "full"
        source_parts.add("opendota_objectives")
    elif replay_objective_payload_available:
        objectives = _normalize_opendota_objectives(
            {"objectives": replay_data.get("objectives") or []},
            opendota_player,
        )
        objective_source = "valve_replay_gem"
        objective_coverage_scope = "full"
        source_parts.add("valve_replay_gem")
    elif stratz_objective_payload_available:
        objectives = _normalize_stratz_tower_objectives(stratz_data, stratz_player)
        objective_source = "stratz_tower_deaths"
        objective_coverage_scope = "buildings"
        source_parts.add("stratz_tower_deaths")
    else:
        objectives = []
        objective_source = None
        objective_coverage_scope = None

    purchases = (
        opendota_purchases
        or stratz_stats_purchases
        or stratz_purchases
        or replay_purchases
    )
    purchase_source = None
    if opendota_purchases:
        purchase_source = "opendota_parsed_logs"
        source_parts.add("opendota_parsed_logs")
    elif stratz_stats_purchases:
        purchase_source = "stratz_stats"
        source_parts.add("stratz_stats")
    elif stratz_purchases:
        purchase_source = "stratz_playback"
        source_parts.add("stratz_playback")
    elif replay_purchases:
        purchase_source = "valve_replay_gem"
        source_parts.add("valve_replay_gem")

    death_candidates = [
        (stratz_stats_deaths, "stratz_stats", 4),
        (replay_deaths, "valve_replay_gem", 4),
        (valve_replay_deaths, "valve_replay", 3),
        (opendota_opponent_kill_deaths, "opendota_opponent_kill_logs", 3),
        (opendota_deaths, "opendota_parsed_logs", 2),
        (stratz_deaths, "stratz_playback", 1),
        (opendota_teamfight_deaths, "opendota_teamfights", 0),
    ]
    available_death_candidates = [candidate for candidate in death_candidates if candidate[0]]
    death_source = None
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
    deaths = _attach_position_samples_to_deaths(deaths, stratz_positions)
    deaths = _attach_direct_death_positions_to_deaths(deaths, opendota_death_positions)
    death_position_count = len([item for item in deaths if item.get("position")])
    death_nearby_context_count = len([
        item for item in deaths
        if isinstance(item.get("nearby_context"), dict)
        and item["nearby_context"].get("sampled_other_players")
    ])
    death_map_points = _build_death_map_points(deaths)
    death_position_clusters = _build_death_position_clusters(death_map_points)
    deaths = _annotate_death_position_cluster_members(deaths, death_position_clusters)
    buybacks = opendota_buybacks or replay_buybacks
    buyback_source = (
        "opendota_parsed_logs" if opendota_buybacks
        else "valve_replay_gem" if replay_buybacks
        else None
    )
    if buyback_source:
        source_parts.add(buyback_source)
    buyback_death_windows = _build_buyback_death_windows(buybacks, deaths)
    position_sources = sorted({
        item.get("position_source")
        for item in deaths
        if item.get("position") and item.get("position_source")
    })
    if death_position_count:
        source_parts.update(position_sources)

    kills, kill_source = _select_complete_event_log(
        (
            (replay_kills, "valve_replay_gem", 4),
            (stratz_stats_kills, "stratz_stats", 3),
            (opendota_kills, "opendota_parsed_logs", 2),
            (stratz_kills, "stratz_playback", 1),
        ),
        expected_kills,
    )
    if kill_source:
        source_parts.add(kill_source)

    assists, assist_source = _select_complete_event_log(
        (
            (replay_assists, "valve_replay_gem", 4),
            (stratz_stats_assists, "stratz_stats", 3),
            (opendota_assists, "opendota_parsed_logs", 2),
            (stratz_assists, "stratz_playback", 1),
        ),
        expected_assists,
    )
    if assist_source:
        source_parts.add(assist_source)

    opendota_vision_events = opendota_observer_wards + opendota_sentry_wards
    stratz_vision_events = stratz_observer_wards + stratz_sentry_wards
    if opendota_vision_events or (
        vision_summary.get("available")
        and not stratz_vision_events
    ):
        observer_wards = opendota_observer_wards
        sentry_wards = opendota_sentry_wards
        vision_events = opendota_vision_events
        vision_source = "opendota_vision"
    elif stratz_vision_events or stratz_vision_summary.get("available"):
        observer_wards = stratz_observer_wards
        sentry_wards = stratz_sentry_wards
        vision_events = stratz_vision_events
        vision_summary = stratz_vision_summary
        vision_source = "stratz_stats"
    elif replay_observer_wards or replay_sentry_wards:
        observer_wards = replay_observer_wards
        sentry_wards = replay_sentry_wards
        vision_events = replay_observer_wards + replay_sentry_wards
        vision_summary = {
            "available": True,
            "observer_placed": len(replay_observer_wards),
            "sentry_placed": len(replay_sentry_wards),
            "source": "valve_replay_gem",
        }
        vision_source = "valve_replay_gem"
    else:
        observer_wards = []
        sentry_wards = []
        vision_events = []
        vision_source = None
    has_vision_log = bool(vision_events) or bool(vision_summary.get("available"))
    if has_vision_log:
        source_parts.add(vision_source)

    fight_sources = sorted({item for item in (kill_source, assist_source) if item})
    fight_source = "+".join(fight_sources) if fight_sources else None

    source = "+".join(sorted(source_parts)) if source_parts else None
    objective_summary = {
        "gained": sum(item["outcome"] == "gained" for item in objectives),
        "lost": sum(item["outcome"] == "lost" for item in objectives),
        "player_direct": sum(bool(item.get("player_direct")) for item in objectives),
        "total": len(objectives),
    }
    death_cost_summary = _build_death_cost_summary(deaths)
    expected_deaths = int(expected_deaths or 0)
    expected_kills = int(expected_kills or 0)
    expected_assists = int(expected_assists or 0)
    observed_deaths = len(deaths)
    missing_deaths = max(expected_deaths - observed_deaths, 0)
    timed_kills = len(kills)
    timed_assists = len(assists)
    expected_fights = expected_kills + expected_assists
    matched_timed_fights = (
        min(timed_kills, expected_kills) + min(timed_assists, expected_assists)
    )
    fight_timing_coverage_pct = (
        round(matched_timed_fights / expected_fights * 100)
        if expected_fights else 100
    )
    fight_timing_complete = (
        timed_kills == expected_kills and timed_assists == expected_assists
    )
    if fight_timing_complete:
        fight_timing_coverage_label = (
            f"击杀时间 {timed_kills}/{expected_kills}；"
            f"助攻时间 {timed_assists}/{expected_assists}；事件计数与记分板一致"
        )
    else:
        fight_timing_coverage_label = (
            f"事件源记录击杀{timed_kills}条（记分板{expected_kills}）、"
            f"助攻{timed_assists}条（记分板{expected_assists}）；"
            f"可匹配覆盖{fight_timing_coverage_pct}%，计数口径不一致"
        )
    if expected_deaths:
        death_coverage_label = f"已定位 {observed_deaths}/{expected_deaths} 次死亡"
    elif observed_deaths:
        death_coverage_label = f"已定位 {observed_deaths} 次死亡"
    else:
        death_coverage_label = "本局没有记录到死亡"
    key_purchases = _key_purchases(purchases, final_item_ids=final_item_ids)
    return {
        "available": bool(source),
        "source": source,
        "purchase_source": purchase_source,
        "death_source": death_source,
        "position_source": "+".join(position_sources) if position_sources else None,
        "fight_source": fight_source,
        "vision_source": vision_source,
        "purchases": purchases,
        "key_purchases": key_purchases,
        "deaths": deaths,
        "death_count_expected": expected_deaths,
        "death_count_observed": observed_deaths,
        "death_count_missing": missing_deaths,
        "death_timeline_complete": observed_deaths == expected_deaths,
        "death_position_count": death_position_count,
        "death_nearby_context_count": death_nearby_context_count,
        "death_cost_summary": death_cost_summary,
        "death_map_points": death_map_points,
        "death_position_clusters": death_position_clusters,
        "position_sample_count": (
            len(stratz_positions)
            + len(opendota_death_positions)
            + sum(bool(item.get("position")) for item in stratz_stats_deaths)
            + sum(bool(item.get("position")) for item in replay_deaths)
        ),
        "has_death_positions": death_position_count > 0,
        "has_death_nearby_context": death_nearby_context_count > 0,
        "death_coverage_label": death_coverage_label,
        "death_gap_note": (
            f"公共数据源未提供剩余 {missing_deaths} 次死亡的分钟级事件。"
            if missing_deaths else ""
        ),
        "buybacks": buybacks,
        "buyback_source": buyback_source,
        "buyback_death_windows": buyback_death_windows,
        "has_buyback_payload": buyback_payload_available,
        "kills": kills,
        "assists": assists,
        "kill_count_expected": expected_kills,
        "assist_count_expected": expected_assists,
        "kill_timing_count": timed_kills,
        "assist_timing_count": timed_assists,
        "fight_timing_complete": fight_timing_complete,
        "fight_timing_coverage_pct": fight_timing_coverage_pct,
        "fight_timing_coverage_label": fight_timing_coverage_label,
        "observer_wards": observer_wards,
        "sentry_wards": sentry_wards,
        "vision_events": sorted(vision_events, key=lambda item: item["time"]),
        "vision_summary": vision_summary,
        "objective_source": objective_source,
        "objective_coverage_scope": objective_coverage_scope,
        "objectives": objectives,
        "objective_summary": objective_summary,
        "has_objective_log": objective_payload_available,
        "has_objective_payload": objective_payload_available,
        "has_full_objective_payload": objective_coverage_scope == "full",
        "has_purchase_timeline": bool(purchases),
        "has_purchase_payload": purchase_payload_available,
        "has_fight_log": bool(deaths or kills or assists),
        "has_fight_payload": fight_payload_available,
        "has_vision_log": has_vision_log,
        "has_vision_event_payload": vision_event_payload_available,
        "missing": {
            "purchases": not bool(purchases),
            "deaths": not bool(deaths),
            "fights": not bool(deaths or kills or assists),
            "vision": not has_vision_log,
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
            if (
                start_minute < 0
                or len(lh_by_minute) < end_minute
                or len(gold_by_minute) < end_minute
            ):
                windows.append({
                    "item_name": item_name,
                    "minute": purchase.get("minute"),
                    "window_type": "farm_acceleration",
                    "window_label": "后5分钟刷钱",
                    "lh_gain": None,
                    "avg_gpm": None,
                    "low_farm": False,
                    "low_conversion": False,
                    "evaluable": False,
                    "classification": "insufficient_data",
                    "summary": f"{item_name}后5分钟补刀或经济分钟数组不完整，未作刷钱判定",
                })
                continue
            lh_gain = int(sum(lh_by_minute[start_minute:end_minute]))
            avg_gpm = _avg_slice(gold_by_minute, start_minute, end_minute)
            low_farm = lh_gain < 40 and avg_gpm < 600
            windows.append({
                "item_name": item_name,
                "minute": purchase.get("minute"),
                "window_type": "farm_acceleration",
                "window_label": "后5分钟刷钱",
                "lh_gain": lh_gain,
                "avg_gpm": avg_gpm,
                "low_farm": low_farm,
                "low_conversion": False,
                "evaluable": True,
                "classification": "low_farm" if low_farm else "converted",
                "summary": f"{item_name}后5分钟{lh_gain}补/{avg_gpm}GPM",
            })
            continue

        if item_name not in MAP_CONVERSION_ITEM_NAMES:
            windows.append({
                "item_name": item_name,
                "minute": purchase.get("minute"),
                "window_type": "context_only",
                "window_label": "仅记录完成时间",
                "kills_or_assists": None,
                "tower_damage": None,
                "low_farm": False,
                "low_conversion": False,
                "evaluable": False,
                "classification": "context_only",
                "summary": f"{item_name}于{purchase.get('minute')}分钟完成；该装备没有通用、可核验的固定转化窗口",
            })
            continue

        end_time = purchase_time + window_seconds
        end_minute = max(start_minute + 1, int(math.ceil(end_time / 60)))
        if (
            start_minute < 0
            or not events.get("fight_timing_complete")
            or len(tower_by_minute) < end_minute
        ):
            windows.append({
                "item_name": item_name,
                "minute": purchase.get("minute"),
                "window_type": "map_conversion",
                "window_label": "后2分钟地图转化",
                "kills_or_assists": None,
                "tower_damage": None,
                "low_farm": False,
                "low_conversion": False,
                "evaluable": False,
                "classification": "insufficient_data",
                "summary": f"{item_name}后2分钟事件时间线不完整，未作转化判定",
            })
            continue

        kills_or_assists = sum(
            1 for event in fight_events
            if isinstance(event.get("time"), (int, float)) and purchase_time <= event["time"] <= end_time
        )
        tower_damage = int(sum(tower_by_minute[start_minute:end_minute]))
        low_conversion = kills_or_assists < 1 and tower_damage < 300
        windows.append({
            "item_name": item_name,
            "minute": purchase.get("minute"),
            "window_type": "map_conversion",
            "window_label": "后2分钟地图转化",
            "kills_or_assists": kills_or_assists,
            "tower_damage": tower_damage,
            "low_farm": False,
            "low_conversion": low_conversion,
            "evaluable": True,
            "classification": "low_conversion" if low_conversion else "converted",
            "summary": f"{item_name}后2分钟参战{kills_or_assists}次/推塔{tower_damage}",
        })
    return windows


def _build_death_overlap_windows(timeline, events):
    if not timeline.get("available") or not events.get("deaths"):
        return []
    overlaps = []
    for window in timeline.get("low_efficiency_windows") or []:
        start = window.get("start_minute")
        end = window.get("end_minute")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        deaths = [
            death for death in events.get("deaths") or []
            if isinstance(death.get("minute"), (int, float)) and start <= death.get("minute") < end
        ]
        if not deaths:
            continue
        death_minutes = [death.get("minute") for death in deaths]
        overlap = dict(window)
        overlap["death_minutes"] = death_minutes
        overlap["death_count"] = len(death_minutes)
        overlap["evidence_label"] = (
            f"{window.get('label')}含 "
            f"{'、'.join(f'{minute}分死亡' for minute in death_minutes)}"
        )
        overlaps.append(overlap)
    return overlaps


def _build_death_recovery_windows(timeline, events, window_minutes=3):
    if not timeline.get("available") or not events.get("deaths"):
        return []
    lh_by_minute = timeline.get("last_hits_by_minute") or []
    gold_by_minute = timeline.get("gold_by_minute") or []
    if not lh_by_minute and not gold_by_minute:
        return []

    max_minutes = max(len(lh_by_minute), len(gold_by_minute))
    windows = []
    deaths = sorted(
        (
            death for death in events.get("deaths") or []
            if isinstance(death.get("time"), (int, float))
        ),
        key=lambda death: death["time"],
    )
    for death_index, death in enumerate(deaths):
        death_time = death.get("time")
        respawn_time = death.get("respawn_observed_at")
        window_basis = "respawn_observed_at"
        if not isinstance(respawn_time, (int, float)):
            time_dead = death.get("time_dead")
            if (
                str(death.get("source") or "").startswith("stratz")
                and isinstance(time_dead, (int, float))
                and time_dead >= 0
            ):
                respawn_time = death_time + time_dead
                window_basis = "stratz_time_dead"
            else:
                continue
        minute = death.get("minute")
        if minute is None:
            minute = round(death_time / 60, 1)
        next_death_time = next(
            (
                later["time"]
                for later in deaths[death_index + 1:]
                if later["time"] >= respawn_time
            ),
            None,
        )
        start = int(math.ceil(respawn_time / 60))
        if (
            isinstance(next_death_time, (int, float))
            and next_death_time < (start + 1) * 60
        ):
            redeath_seconds = int(round(next_death_time - respawn_time))
            windows.append({
                "death_time": death_time,
                "minute": minute,
                "respawn_time": respawn_time,
                "respawn_minute": round(respawn_time / 60, 1),
                "window_basis": window_basis,
                "start_minute": start,
                "end_minute": start,
                "window_label": None,
                "observed_minutes": 0,
                "lh_gain": None,
                "lh_per_min": None,
                "avg_gpm": None,
                "status": "interrupted",
                "status_label": "再次死亡打断",
                "next_death_time": next_death_time,
                "redeath_seconds": redeath_seconds,
                "evidence_label": (
                    f"{minute}分复活后{redeath_seconds}秒再次死亡，"
                    "未形成完整资源分钟"
                ),
            })
            continue
        if start >= max_minutes:
            continue
        end = min(start + window_minutes, max_minutes)
        if isinstance(next_death_time, (int, float)):
            end = min(end, int(next_death_time // 60))
        observed_minutes = max(end - start, 0)
        if observed_minutes <= 0:
            continue
        lh_gain = int(_sum_slice(lh_by_minute, start, end)) if lh_by_minute else None
        avg_gpm = _avg_slice(gold_by_minute, start, end) if gold_by_minute else None
        lh_per_min = round(lh_gain / observed_minutes, 1) if lh_gain is not None else None
        low_lh = lh_per_min is not None and lh_per_min < 2
        low_gold = avg_gpm is not None and avg_gpm < 260
        strong_lh = lh_per_min is not None and lh_per_min >= 4
        strong_gold = avg_gpm is not None and avg_gpm >= 420
        if lh_per_min is not None and avg_gpm is not None:
            is_low = low_lh and low_gold
        elif lh_per_min is not None:
            is_low = low_lh
        else:
            is_low = low_gold
        if is_low:
            status = "low"
            status_label = "恢复不足"
        elif strong_lh or strong_gold:
            status = "recovered"
            status_label = "已恢复资源"
        else:
            status = "partial"
            status_label = "一般恢复"
        resource_parts = []
        if lh_gain is not None:
            resource_parts.append(f"{lh_gain}补")
        if avg_gpm is not None:
            resource_parts.append(f"{avg_gpm}平均GPM")
        windows.append({
            "death_time": death_time,
            "minute": minute,
            "respawn_time": respawn_time,
            "respawn_minute": round(respawn_time / 60, 1),
            "window_basis": window_basis,
            "start_minute": start,
            "end_minute": end,
            "window_label": f"{start}-{end}分钟",
            "observed_minutes": observed_minutes,
            "lh_gain": lh_gain,
            "lh_per_min": lh_per_min,
            "avg_gpm": avg_gpm,
            "status": status,
            "status_label": status_label,
            "next_death_time": next_death_time,
            "redeath_seconds": (
                int(round(next_death_time - respawn_time))
                if isinstance(next_death_time, (int, float))
                else None
            ),
            "evidence_label": f"{minute}分复活后{start}-{end}分钟 {'/'.join(resource_parts)}",
        })
    return windows


def _build_death_resource_deltas(timeline, events, window_minutes=3):
    if not timeline.get("available") or not events.get("deaths"):
        return []
    lh_by_minute = timeline.get("last_hits_by_minute") or []
    gold_by_minute = timeline.get("gold_by_minute") or []
    if not lh_by_minute and not gold_by_minute:
        return []

    max_minutes = max(len(lh_by_minute), len(gold_by_minute))
    deltas = []
    for death in events.get("deaths") or []:
        death_time = death.get("time")
        if not isinstance(death_time, (int, float)):
            continue
        before_end = int(death_time // 60)
        has_partial_death_minute = death_time % 60 != 0
        after_start = before_end + 1 if has_partial_death_minute else before_end
        before_start = max(0, before_end - window_minutes)
        after_end = min(after_start + window_minutes, max_minutes)
        if before_start >= before_end or after_start >= after_end:
            continue

        before_lh_values = lh_by_minute[before_start:min(before_end, len(lh_by_minute))]
        after_lh_values = lh_by_minute[after_start:min(after_end, len(lh_by_minute))]
        before_gold_values = gold_by_minute[before_start:min(before_end, len(gold_by_minute))]
        after_gold_values = gold_by_minute[after_start:min(after_end, len(gold_by_minute))]

        has_lh_pair = bool(before_lh_values and after_lh_values)
        has_gold_pair = bool(before_gold_values and after_gold_values)
        if not has_lh_pair and not has_gold_pair:
            continue

        before_lh = int(sum(before_lh_values)) if has_lh_pair else None
        after_lh = int(sum(after_lh_values)) if has_lh_pair else None
        before_lh_per_min = (
            round(before_lh / len(before_lh_values), 1) if has_lh_pair else None
        )
        after_lh_per_min = (
            round(after_lh / len(after_lh_values), 1) if has_lh_pair else None
        )
        lh_per_min_delta = (
            round(after_lh_per_min - before_lh_per_min, 1) if has_lh_pair else None
        )
        before_avg_gpm = (
            round(sum(before_gold_values) / len(before_gold_values), 1) if has_gold_pair else None
        )
        after_avg_gpm = (
            round(sum(after_gold_values) / len(after_gold_values), 1) if has_gold_pair else None
        )
        avg_gpm_delta = (
            round(after_avg_gpm - before_avg_gpm, 1) if has_gold_pair else None
        )

        metric_deltas = [
            value for value in (lh_per_min_delta, avg_gpm_delta)
            if value is not None
        ]
        metric_labels = []
        if lh_per_min_delta is not None:
            metric_labels.append("补刀")
        if avg_gpm_delta is not None:
            metric_labels.append("经济")
        joined_metrics = "与".join(metric_labels)
        if all(value < 0 for value in metric_deltas):
            status = "declined"
            status_label = f"{joined_metrics}均下降" if len(metric_labels) > 1 else f"{joined_metrics}下降"
        elif all(value == 0 for value in metric_deltas):
            status = "flat"
            status_label = f"{joined_metrics}持平"
        elif all(value >= 0 for value in metric_deltas):
            status = "maintained"
            status_label = f"{joined_metrics}未下降"
        else:
            status = "mixed"
            status_label = f"{joined_metrics}变化不一致"

        minute = death.get("minute")
        if minute is None:
            minute = round(death_time / 60, 1)
        evidence_parts = []
        if lh_per_min_delta is not None:
            evidence_parts.append(
                f"补刀/分 {before_lh_per_min}→{after_lh_per_min}（{lh_per_min_delta:+.1f}）"
            )
        if avg_gpm_delta is not None:
            evidence_parts.append(
                f"平均GPM {before_avg_gpm}→{after_avg_gpm}（{avg_gpm_delta:+.1f}）"
            )
        deltas.append({
            "death_time": death_time,
            "minute": minute,
            "before_window_label": f"{before_start}-{before_end}分钟",
            "after_window_label": f"{after_start}-{after_end}分钟",
            "excluded_partial_minute": before_end if has_partial_death_minute else None,
            "before_lh": before_lh,
            "after_lh": after_lh,
            "before_lh_per_min": before_lh_per_min,
            "after_lh_per_min": after_lh_per_min,
            "lh_per_min_delta": lh_per_min_delta,
            "before_avg_gpm": before_avg_gpm,
            "after_avg_gpm": after_avg_gpm,
            "avg_gpm_delta": avg_gpm_delta,
            "status": status,
            "status_label": status_label,
            "evidence_label": f"{minute}分死亡前后：{'，'.join(evidence_parts)}",
        })
    return deltas


def _death_context_line(label, text, kind):
    return {
        "label": label,
        "text": text,
        "kind": kind,
    }


def _index_by_death_time(items):
    indexed = {}
    for item in items or []:
        death_time = item.get("death_time")
        if not isinstance(death_time, (int, float)):
            continue
        indexed.setdefault(death_time, []).append(item)
    return indexed


def _nearest_key_purchase_context(death_time, key_purchases, max_distance_seconds=180):
    if not isinstance(death_time, (int, float)):
        return None
    candidates = []
    for purchase in key_purchases or []:
        purchase_time = purchase.get("time")
        if not isinstance(purchase_time, (int, float)):
            continue
        distance = purchase_time - death_time
        if abs(distance) > max_distance_seconds:
            continue
        candidates.append((abs(distance), distance, purchase))
    if not candidates:
        return None
    _, distance, purchase = min(candidates, key=lambda item: (item[0], abs(item[1])))
    seconds = int(round(abs(distance)))
    item_name = purchase.get("item_name") or "关键装备"
    if distance <= 0:
        text = f"死亡前{seconds}秒完成 {item_name}"
    else:
        text = f"死亡后{seconds}秒完成 {item_name}"
    return _death_context_line("装备上下文", text, "purchase")


def _nearby_players_context_line(death):
    context = death.get("nearby_context") or {}
    radius = context.get("radius_units")
    ally_count = context.get("allies_within_radius_count")
    enemy_count = context.get("enemies_within_radius_count")
    if not isinstance(radius, (int, float)) or not isinstance(ally_count, int) or not isinstance(enemy_count, int):
        return None
    parts = [f"{int(radius)}范围内存活队友{ally_count}人、敌人{enemy_count}人"]
    nearest_ally = context.get("nearest_ally") or {}
    nearest_enemy = context.get("nearest_enemy") or {}
    if nearest_ally.get("distance_units") is not None:
        ally_name = nearest_ally.get("hero_name") or f"玩家{nearest_ally.get('player_id')}"
        parts.append(f"最近队友 {ally_name} {nearest_ally['distance_units']}单位")
    if nearest_enemy.get("distance_units") is not None:
        enemy_name = nearest_enemy.get("hero_name") or f"玩家{nearest_enemy.get('player_id')}"
        parts.append(f"最近敌人 {enemy_name} {nearest_enemy['distance_units']}单位")
    resolution = context.get("sample_resolution_seconds")
    if resolution is not None:
        parts.append(f"全员位置采样精度{resolution}秒")
    return _death_context_line("局部人数", "；".join(parts), "nearby-players")


def _attach_death_contexts_to_deaths(events, timeline):
    deaths = events.get("deaths") or []
    if not deaths:
        return deaths

    objective_by_death = _index_by_death_time(events.get("death_objective_windows"))
    recovery_by_death = _index_by_death_time((timeline or {}).get("death_recovery_windows"))
    delta_by_death = _index_by_death_time((timeline or {}).get("death_resource_deltas"))
    key_purchases = events.get("key_purchases") or []

    enriched = []
    for death in deaths:
        item = dict(death)
        death_time = item.get("time")
        context_lines = []

        nearby_line = _nearby_players_context_line(item)
        if nearby_line:
            context_lines.append(nearby_line)

        if isinstance(death_time, (int, float)):
            for window in objective_by_death.get(death_time, [])[:2]:
                context_lines.append(_death_context_line(
                    "目标上下文",
                    (
                        f"死亡后{window.get('elapsed_seconds')}秒"
                        f"{window.get('objective_display_label')}"
                    ),
                    "objective",
                ))

            deltas = delta_by_death.get(death_time, [])
            if deltas:
                delta = deltas[0]
                context_lines.append(_death_context_line(
                    "前后资源",
                    f"{delta.get('evidence_label')}（{delta.get('status_label')}）",
                    "resource-delta",
                ))

            recoveries = recovery_by_death.get(death_time, [])
            if recoveries:
                recovery = recoveries[0]
                context_lines.append(_death_context_line(
                    "恢复上下文",
                    f"{recovery.get('evidence_label')}（{recovery.get('status_label')}）",
                    "recovery",
                ))

            purchase_context = _nearest_key_purchase_context(death_time, key_purchases)
            if purchase_context:
                context_lines.append(purchase_context)

        if not item.get("position_label"):
            context_lines.append(_death_context_line(
                "坐标缺口",
                "公共数据源未提供这次死亡坐标；本卡只使用时间线、目标和装备事件。",
                "position-gap",
            ))

        item["context_lines"] = context_lines[:5]
        enriched.append(item)
    return enriched


def _has_meaningful_death_resource_drop(window):
    lh_delta = window.get("lh_per_min_delta")
    gpm_delta = window.get("avg_gpm_delta")
    return (
        (isinstance(lh_delta, (int, float)) and lh_delta <= -2.0)
        or (isinstance(gpm_delta, (int, float)) and gpm_delta <= -150.0)
    )


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

    lane_role = context.get("opendota_lane_role") or context.get("replay_lane_role")
    resource_ranks = context.get("team_resource_ranks") or {}
    farm_rank = resource_ranks.get("last_hits")
    gpm_rank = resource_ranks.get("gold_per_min")
    net_worth_rank = resource_ranks.get("net_worth")
    vision_actions = resource_ranks.get("vision_actions")
    lh_per_min = float(derived.get("lh_per_min") or 0)
    lane_labels = {1: "优势路", 2: "中路", 3: "劣势路", 4: "野区"}
    if lane_role in lane_labels and isinstance(farm_rank, int):
        evidence_parts = [f"OpenDota{lane_labels[lane_role]}", f"队内补刀第{farm_rank}"]
        if isinstance(gpm_rank, int):
            evidence_parts.append(f"GPM第{gpm_rank}")
        if isinstance(net_worth_rank, int):
            evidence_parts.append(f"净资产第{net_worth_rank}")
        evidence_parts.append(f"{lh_per_min:.1f} LH/min")
        formula_common = {
            "classification": "formula",
            "source": "OpenDota分路 + 队内资源排序公式",
            "evidence": "、".join(evidence_parts),
            "farm_rank": farm_rank,
            "gpm_rank": gpm_rank,
            "net_worth_rank": net_worth_rank,
            "exact_position_available": False,
        }
        if lane_role == 1 and (
            farm_rank <= 2 or (farm_rank <= 3 and lh_per_min >= 4.5)
        ):
            return {
                "id": "pos1",
                "label": "1号位（公式识别）",
                "lane_farm_sensitive": True,
                "focus": ["对线补刀", "关键装备时机", "死亡成本", "经济转地图目标"],
                **formula_common,
            }
        if lane_role == 2 and farm_rank <= 3 and lh_per_min >= 4.0:
            return {
                "id": "pos2",
                "label": "2号位（公式识别）",
                "lane_farm_sensitive": True,
                "focus": ["对线补刀", "节奏启动", "死亡成本", "经济转地图目标"],
                **formula_common,
            }
        if lane_role == 3 and farm_rank <= 3 and lh_per_min >= 3.0:
            return {
                "id": "pos3",
                "label": "3号位（公式识别）",
                "lane_farm_sensitive": False,
                "focus": ["参战率", "承伤/死亡", "先手窗口", "推塔/控图贡献"],
                **formula_common,
            }
        if farm_rank >= 4 and lane_role in {1, 3}:
            position_label = "5号位" if lane_role == 1 else "4号位"
            return {
                **_support_profile(),
                "label": f"{position_label}（公式识别）",
                "position_id": "pos5" if lane_role == 1 else "pos4",
                "vision_actions": vision_actions,
                **formula_common,
            }

    vision_events = context.get("vision_events") or 0
    lh_per_min = derived.get("lh_per_min") or 0
    if vision_events >= 8 and lh_per_min <= 6:
        return _support_profile()

    lane = context.get("raw_lane") or context.get("lane")
    stratz_lane_labels = {
        "SAFE_LANE": "优势路",
        "MID_LANE": "中路",
        "OFF_LANE": "劣势路",
        "JUNGLE": "野区",
    }
    lane_label = stratz_lane_labels.get(str(lane or "").upper())
    if lane_label:
        return {
            "id": "unknown_lane",
            "label": (
                f"{lane_label}核心（位置未细分）"
                if raw_role == "CORE"
                else f"{lane_label}（位置未细分）"
            ),
            "lane_farm_sensitive": raw_role != "SUPPORT",
            "focus": ["对线资源", "关键装备时机", "死亡成本", "地图目标"],
        }
    if lane and (
        lane.endswith("（OpenDota）")
        or lane.endswith("（Valve回放）")
        or lane.endswith("（STRATZ）")
    ):
        lane_label = (
            lane.removesuffix("（OpenDota）")
            .removesuffix("（Valve回放）")
            .removesuffix("（STRATZ）")
        )
        role_label = (
            f"{lane_label}核心（位置未细分）"
            if raw_role == "CORE"
            else f"{lane_label}（位置未细分）"
        )
        return {
            "id": "unknown_lane",
            "label": role_label,
            "lane_farm_sensitive": True,
            "focus": ["对线资源", "关键装备时机", "死亡成本", "地图目标"],
        }

    return {
        "id": "unknown",
        "label": "未知位置",
        "lane_farm_sensitive": True,
        "focus": ["死亡成本", "经济效率", "地图目标"],
    }


MAP_CONVERSION_SUCCESS_METRIC = "强势装后2分钟参战不少于1次或推塔伤害不低于300"
FARM_ACCELERATION_SUCCESS_METRIC = "刷钱装后5分钟补刀不少于40或平均GPM不低于600"


def _default_training_goal(category):
    defaults = {
        "lane_farm": "下一局先把前10分钟资源路线打完整，让系统能用分钟级补刀线验收。",
        "resource_continuity": "下一局10分钟后每次集合前先推出一条安全线，减少连续断补窗口。",
        "death_resource_overlap": "下一局把死亡重叠低效率窗口压到0，死亡后先恢复一波安全资源。",
        "death_recovery": "下一局每次死亡后3分钟内完成一波可记录的资源恢复。",
        "death_resource_delta": "下一局每次死亡后先完成一波可记录的资源恢复，再接高风险带线或集合。",
        "death_position_pattern": "下一局把重复死亡坐标簇逐一列成撤退规则，进入同类坐标前先满足撤退条件。",
        "death_review": "下一局把死亡压到每10分钟最多1次，避免连续短时间重复阵亡。",
        "item_timing": "下一局每件关键装备成型后立刻绑定一个可记录的地图动作。",
        "map_impact": "下一局把刷钱路线接到推塔、参战或控图目标上。",
        "hero_benchmark_gap": "下一局优先修正本局低于同英雄第30百分位的指标，只追一个主短板。",
        "closing": "下一局关键装备成型后30秒内给出盾、塔、双线压力三选一的明确动作。",
        "review_focus": "下一局只追踪前10分钟资源、关键装备后转化、死亡成本三项。",
    }
    return defaults.get(category, "下一局围绕本条证据执行一个可记录动作。")


def _default_success_metric(category):
    defaults = {
        "lane_farm": "10分钟补刀不低于本局；前10分钟低效率窗口为0。",
        "resource_continuity": "10分钟后低效率窗口不超过1个；单个窗口不超过2分钟。",
        "death_resource_overlap": "死亡与低效率窗口重叠为0；死亡后3分钟补刀不少于6或平均GPM不低于300。",
        "death_recovery": "死亡后3分钟补刀不少于6或平均GPM不低于300；恢复不足窗口为0。",
        "death_resource_delta": "死亡前后资源明显下降窗口不超过1个；复活后3分钟完成一波安全线或近区野区资源。",
        "death_position_pattern": "重复死亡坐标簇不超过1个；同一坐标簇内重复死亡次数不超过1次。",
        "death_review": "每10分钟死亡不高于1.0；连续5分钟内死亡簇为0。",
        "item_timing": f"{FARM_ACCELERATION_SUCCESS_METRIC}；{MAP_CONVERSION_SUCCESS_METRIC}。",
        "map_impact": "参战率不低于40%；关键装备后2分钟至少完成一次地图动作。",
        "hero_benchmark_gap": "下一份报告该主短板高于本局百分位；低于第30百分位的指标数量减少。",
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


def _next_game_count_target(current_count, reduction_ratio=0.25):
    count = max(0, int(current_count or 0))
    if count == 0:
        return 0
    return max(0, count - max(1, math.ceil(count * reduction_ratio)))


def _next_game_rate_target(current_rate, reduction_ratio=0.20):
    if not isinstance(current_rate, (int, float)) or current_rate <= 0:
        return 0
    return max(0, round(float(current_rate) * (1 - reduction_ratio), 1))


def _death_cluster_labels(deaths, gap_minutes=5, max_span_minutes=10):
    minutes = sorted(
        item.get("minute") for item in deaths
        if isinstance(item.get("minute"), (int, float))
    )
    if len(minutes) < 2:
        return []
    clusters = []
    current = [minutes[0]]
    for minute in minutes[1:]:
        if (
            minute - current[-1] <= gap_minutes
            and minute - current[0] <= max_span_minutes
        ):
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
        if window.get("evaluable") is False:
            continue
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


def _benchmark_gap_training_plan(metric, result):
    metric_id = metric.get("id")
    label = metric.get("label") or metric_id or "该指标"
    percentile = metric.get("percentile_label") or "本局百分位"
    farm = result.get("farm") or {}
    if metric_id == "tower_damage":
        return (
            "下一局每次赢下击杀或逼退敌人后先看最近兵线；兵线已到敌方建筑且撤退路线明确时，先打建筑再回到刷钱路线，兵线未到则不强行追塔。",
            "下一局至少完成1次“兵线到塔后先打建筑”的可记录转化。",
            f"兵线到塔后的建筑转化不少于1次；推塔伤害百分位从本局{percentile}提升到至少第30百分位。",
        )
    if metric_id in {"gold_per_min", "last_hits_per_min"}:
        return (
            "下一局10分钟后每次移动都绑定下一波安全线或近区野点；没有明确塔、盾或高胜率击杀窗口时，不进行超过30秒的无资源集合。",
            f"下一局只追{label}，把10分钟后无资源移动压到最少。",
            f"{label}百分位高于本局{percentile}；10分钟后低效率窗口不超过1个。",
        )
    if metric_id == "xp_per_min":
        return (
            "下一局10分钟后优先接能获得经验的安全线；必须集合时站在经验范围内，死亡后复活第一步回到安全经验来源。",
            "下一局减少离开兵线经验范围和死亡后的空走时间。",
            f"XPM百分位高于本局{percentile}；连续5分钟死亡簇为0。",
        )
    if metric_id == "hero_damage_per_min":
        return (
            "下一局团战先保证第一轮技能和普攻完整打出；敌方关键控制未出现前，不用位移技能单独深入，第一轮结束后再决定追击或撤退。",
            "下一局把每次参战转成至少一轮完整输出，而不是只追击杀数。",
            f"英雄伤害/分钟百分位高于本局{percentile}；参战率不低于本局。",
        )
    if metric_id == "kills_per_min":
        return (
            "下一局不单独追击杀；先把兵线推到河道外，再跟最近的队友对已有视野目标形成二打一或多人先手。",
            "下一局用有队友和已有视野的击杀窗口提高有效参战。",
            f"击杀/分钟百分位高于本局{percentile}；参战率不低于本局。",
        )
    return (
        f"下一局只训练{label}对应动作，并保持其他已达标指标不下降。",
        f"下一局优先把{label}从本局{percentile}往上抬。",
        f"{label}百分位高于本局{percentile}。",
    )


def _build_review_findings(result):
    findings = []
    benchmark_finding = None
    timeline = result.get("timeline", {})
    events = result.get("events", {})
    derived = result.get("derived", {})
    farm = result.get("farm", {})
    role_profile = result.get("role_profile", {})
    role_id = role_profile.get("id")
    benchmark_profile = result.get("opendota_benchmarks") or {}
    benchmark_weak = benchmark_profile.get("weak_metrics") or []
    performance_context = result.get("performance_context") or {}
    lane_efficiency_pct = performance_context.get("lane_efficiency_pct")
    teamfight_participation_pct = performance_context.get("teamfight_participation_pct")
    dead_time_label = performance_context.get("dead_time_label")
    dead_time_share_pct = performance_context.get("dead_time_share_pct")

    if benchmark_weak:
        weak_metrics = sorted(benchmark_weak, key=lambda item: item.get("pct", 1))[:3]
        evidence = "；".join(
            f"{item.get('label')} {item.get('percentile_label')}"
            for item in weak_metrics
            if item.get("label") and item.get("percentile_label")
        )
        lowest = weak_metrics[0]
        benchmark_action, benchmark_training_goal, benchmark_success_metric = (
            _benchmark_gap_training_plan(lowest, result)
        )
        benchmark_finding = _finding(
            "medium",
            "hero_benchmark_gap",
            f"OpenDota同英雄样本低位指标: {evidence}。",
            "同英雄样本百分位能区分这局是总量正常但某个维度掉队，还是所有面板都处在正常区间。",
            benchmark_action,
            "OpenDota英雄样本百分位只描述公开样本相对位置，不是职业均值；系统只核对低位指标对应的真实分钟和事件证据。",
            benchmark_training_goal,
            benchmark_success_metric,
        )

    lane_efficiency_low = (
        role_profile.get("lane_farm_sensitive")
        and isinstance(lane_efficiency_pct, (int, float))
        and lane_efficiency_pct < 50
    )
    if timeline.get("available") and role_profile.get("lane_farm_sensitive"):
        ten_lh = timeline.get("ten_min_last_hits")
        low_windows = timeline.get("low_efficiency_windows", [])
        early_low_windows = [w for w in low_windows if w.get("start_minute", 999) < 10]
        if ten_lh is not None and (ten_lh < 45 or early_low_windows or lane_efficiency_low):
            target_lh = ten_lh
            if ten_lh < 60:
                target_lh = min(60, ten_lh + 5)
            evidence = f"10分钟补刀 {ten_lh}，前10分钟低效率窗口 {len(early_low_windows)} 个"
            action = "下一局前10分钟优先保证安全线和附近野区连续收取，除非队友明确形成高胜率击杀。"
            training_goal = f"下一局先把前10分钟低效率窗口清零，再冲10分钟{target_lh}补。"
            success_metric = f"10分钟补刀不少于{target_lh}；前10分钟低效率窗口为0。"
            if lane_efficiency_low:
                target_lane_efficiency = min(100, lane_efficiency_pct + 5)
                evidence += f"，OpenDota对线效率 {lane_efficiency_pct}%"
                action += f" 以本局{lane_efficiency_pct}%为基线，下一局先提升到{target_lane_efficiency}%。"
                training_goal = f"下一局把OpenDota对线效率从{lane_efficiency_pct}%提升到{target_lane_efficiency}%，并清零前10分钟低效率窗口。"
                success_metric += f" OpenDota对线效率不低于{target_lane_efficiency}%。"
            findings.append(_finding(
                "high",
                "lane_farm",
                evidence + "。",
                "核心位前10分钟资源会直接影响第一件关键装备和之后能否接管地图。",
                action,
                "系统按低效率窗口标记异常分钟，并使用OpenDota对线效率汇总字段交叉验收；汇总值不判断效率下降原因。",
                training_goal,
                success_metric,
            ))
    elif role_id in ("pos1", "pos2", "unknown"):
        evidence = f"总补刀 {farm.get('last_hits', 0)}，LH/min {derived.get('lh_per_min', 0)}；缺少分钟级补刀时间线"
        action = "当前报告只按总量指标给低置信度判断；后续抓取会继续请求分钟数组，拿到后自动重跑对线期诊断。"
        training_goal = "下一局先保证数据抓取拿到分钟级补刀线；有时间线后才对对线期下结论。"
        success_metric = "数据验收：下一份报告包含10分钟补刀和前10分钟低效率窗口。"
        if lane_efficiency_low:
            target_lane_efficiency = min(100, lane_efficiency_pct + 5)
            evidence += f"；OpenDota对线效率 {lane_efficiency_pct}%"
            action = f"以本局{lane_efficiency_pct}%为真实基线，下一局前10分钟每次离线前先确定下一波兵线或近区野资源，把OpenDota对线效率提升到{target_lane_efficiency}%。"
            training_goal = f"下一局把OpenDota对线效率从{lane_efficiency_pct}%提升到{target_lane_efficiency}%。"
            success_metric = f"OpenDota对线效率不低于{target_lane_efficiency}%；下一份报告补齐分钟级补刀线。"
        findings.append(_finding(
            "medium",
            "lane_farm",
            evidence + "。",
            "没有时间线就无法定位对线期还是中期刷钱路线出了问题。",
            action,
            "系统使用OpenDota对线效率汇总字段确认本局结果；缺少分钟数组时不编造具体失误分钟。",
            training_goal,
            success_metric,
        ))

    late_low_windows = [
        w for w in timeline.get("low_efficiency_windows", [])
        if w.get("start_minute", 0) >= 10
    ]
    if late_low_windows and role_id in ("pos1", "pos2", "unknown", "unknown_lane"):
        evidence = "；".join(
            f"{w.get('start_minute')}-{w.get('end_minute')}分钟 {w.get('avg_lh')}补/分钟"
            for w in late_low_windows[:3]
        )
        late_window_target = _next_game_count_target(len(late_low_windows))
        findings.append(_finding(
            "medium",
            "resource_continuity",
            f"中后期低效率窗口: {evidence}。",
            "核心位中后期长时间无补刀通常意味着死亡、被迫集合、兵线未推出或地图区域丢失。",
            "下一局中后期每次集合前先推至少一条安全线；若队伍不开雾/不控盾，优先保持两路兵线压力。",
            "系统已标记这些异常分钟，优先和死亡、购买、击杀事件时间点交叉核对。",
            f"下一局10分钟后把低效率窗口从{len(late_low_windows)}个降到不超过{late_window_target}个；集合前先推出一条安全线。",
            f"10分钟后低效率窗口不超过{late_window_target}个；单个低效率窗口不超过2分钟。",
        ))

    overlap_windows = timeline.get("death_overlap_windows") or []
    if overlap_windows and role_id in ("pos1", "pos2", "unknown", "unknown_lane"):
        evidence = "；".join(
            window.get("evidence_label")
            for window in overlap_windows[:3]
            if window.get("evidence_label")
        )
        total_overlaps = sum(window.get("death_count", 0) for window in overlap_windows)
        overlap_target = _next_game_count_target(total_overlaps)
        findings.append(_finding(
            "high",
            "death_resource_overlap",
            f"死亡与低效率窗口重叠: {evidence}。",
            "死亡分钟与补刀低效率窗口重叠，说明这次阵亡已经实际打断了资源连续性，而不只是面板死亡数偏高。",
            "下一局10分钟后死亡或被迫回补后，先补回一波安全线，再决定是否继续集合、带线或进野区。",
            "系统只按死亡分钟和低效率补刀窗口做时间重叠；未采集的兵线位置、TP状态和队友距离不会写成结论。",
            f"下一局把死亡重叠低效率窗口从{total_overlaps}次降到不超过{overlap_target}次；死亡后3分钟先恢复一波安全资源。",
            f"死亡与低效率窗口重叠不超过{overlap_target}次；复活后3分钟补刀不少于6或平均GPM不低于300。",
        ))

    death_objective_windows = events.get("death_objective_windows") or []
    if death_objective_windows:
        unique_deaths = (events.get("death_objective_summary") or {}).get("unique_death_count", 0)
        drill = events.get("death_objective_drill") or {}
        focus_evidence = drill.get("evidence")
        if focus_evidence:
            focus_count = int(drill.get("focus_window_count") or 1)
            focus_minute = drill.get("focus_death_minute")
            evidence = f"最高累计损失窗口（{focus_minute}分死亡，共{focus_count}个目标）：{focus_evidence}"
            remaining_count = max(0, len(death_objective_windows) - focus_count)
            if remaining_count:
                focus_death_time = drill.get("focus_death_time")
                other_labels = [
                    window.get("evidence_label")
                    for window in death_objective_windows
                    if window.get("death_time") != focus_death_time and window.get("evidence_label")
                ]
                if remaining_count <= 2 and other_labels:
                    evidence += f"；其他相邻窗口：{'；'.join(other_labels)}"
                else:
                    evidence += f"；本局另有{remaining_count}条死亡-目标90秒相邻记录"
        else:
            evidence = "；".join(
                window.get("evidence_label")
                for window in death_objective_windows[:5]
                if window.get("evidence_label")
            )
        action = (
            f"{drill.get('trigger')}：{drill.get('rule')}"
            if drill else
            "下一局预计要接塔、肉山或高地时，提前90秒停止单独深入；若刚死亡，复活后的第一决策优先处理兵线、目标入口或明确的对侧交换。"
        )
        replay_check = "系统只标记事件先后和精确时间差，不判断死亡造成了目标损失。"
        if drill.get("replay_check"):
            replay_check += f" {drill['replay_check']}"
        focus_death_time = drill.get("focus_death_time")
        recent_purchase = None
        if isinstance(focus_death_time, (int, float)):
            candidates = [
                purchase for purchase in events.get("key_purchases") or []
                if isinstance(purchase.get("time"), (int, float))
                and 0 <= focus_death_time - purchase["time"] <= 120
            ]
            if candidates:
                recent_purchase = max(candidates, key=lambda purchase: purchase["time"])
        if recent_purchase:
            purchase_gap = int(round(focus_death_time - recent_purchase["time"]))
            item_name = recent_purchase.get("item_name") or "关键装备"
            evidence += f"；该死亡前{purchase_gap}秒完成 {item_name}"
            action += (
                f" 刚完成 {item_name} 后的首次目标接触仍执行同一规则，"
                "不因装备刚到手而跳过局部人数和最近队友撤退方向两项条件。"
            )
            replay_check += " 系统自动对齐关键购买与焦点死亡，只陈述真实时间差。"
        findings.append(_finding(
            "high" if unique_deaths >= 2 else "medium",
            "death_objective_window",
            f"死亡后90秒内失去目标: {evidence}。",
            "这些死亡与目标损失发生在同一短窗口，意味着该时段本人客观上无法持续参与防守或交换；时间邻接不等于因果归责。",
            action,
            replay_check,
            drill.get("training_goal") or f"下一局把死亡后90秒内失去目标窗口从{len(death_objective_windows)}个压到0。",
            drill.get("success_metric") or "死亡后90秒内失去目标窗口为0；25分钟后死亡不超过2次。",
        ))

    short_buyback_deaths = [
        window for window in events.get("buyback_death_windows") or []
        if window.get("short_redeath")
    ]
    if short_buyback_deaths:
        evidence_rows = [
            (
                f"{window.get('buyback_minute')}分买活，"
                f"{window.get('death_minute')}分再次死亡，"
                f"间隔{window.get('redeath_seconds')}秒"
            )
            for window in short_buyback_deaths[:3]
        ]
        findings.append(_finding(
            "high",
            "buyback_redeath",
            "；".join(evidence_rows) + "。",
            "买活消耗后在短窗口内再次死亡，会直接结束本人这一轮防守或反打的可行动时间。",
            "下一局买活后先核对己方存活人数、兵线和最近目标；120秒内除守遗迹或结束比赛外，不作为第一进场点。",
            "系统自动对齐真实 buyback_log 与下一次死亡时间；只记录事件间隔，不判断再次死亡的具体原因。",
            f"下一局把买活后120秒内再次死亡从{len(short_buyback_deaths)}次压到0。",
            "买活后120秒内再次死亡为0；买活后第一次接触前完成存活人数、兵线、目标三项检查。",
        ))

    recovery_windows = timeline.get("death_recovery_windows") or []
    low_recovery_windows = [
        window for window in recovery_windows
        if window.get("status") in {"low", "interrupted"}
    ]
    if low_recovery_windows and role_id in ("pos1", "pos2", "pos3", "unknown", "unknown_lane"):
        delta_by_minute = {
            window.get("minute"): window
            for window in timeline.get("death_resource_deltas") or []
            if window.get("minute") is not None
        }
        evidence_rows = []
        for window in low_recovery_windows[:4]:
            row_parts = [window.get("evidence_label")]
            delta = delta_by_minute.get(window.get("minute"))
            if delta and delta.get("evidence_label"):
                row_parts.append(delta["evidence_label"])
            evidence_rows.append("；".join(part for part in row_parts if part))
        evidence = "；".join(evidence_rows)
        interrupted_count = sum(
            window.get("status") == "interrupted"
            for window in low_recovery_windows
        )
        recovery_target = _next_game_count_target(len(low_recovery_windows))
        recovery_issue_label = (
            "死亡后恢复被再次死亡打断"
            if interrupted_count == len(low_recovery_windows)
            else "死亡后恢复不足或被再次死亡打断"
        )
        findings.append(_finding(
            "high",
            "death_recovery",
            f"{recovery_issue_label}: {evidence}。",
            "复活后的资源恢复偏低或在完整资源分钟形成前再次死亡，会把一次阵亡延长成连续不可行动窗口。",
            "下一局复活后第一波只执行一个可验收动作：TP安全线、收近区野，或跟队友拿已有视野目标；3分钟内先补到6补或300平均GPM，再接高风险带线。",
            "系统按真实复活时间、下一次死亡和完整分钟补刀/经济数组自动验收；未采集的死亡原因不会写成结论。",
            f"下一局把死亡后恢复不足窗口从{len(low_recovery_windows)}个降到不超过{recovery_target}个；每次复活先完成一波资源恢复。",
            f"死亡后恢复不足或中断窗口不超过{recovery_target}个；其余恢复窗口3分钟补刀不少于6或平均GPM不低于300。",
        ))

    if events.get("deaths"):
        death_events = events["deaths"]
        death_cost = events.get("death_cost_summary") or {}
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
        if dead_time_label and dead_time_share_pct is not None:
            evidence += f" 死亡占时 {dead_time_label}（{dead_time_share_pct}%）。"
        if death_cost.get("available"):
            cost_parts = []
            if death_cost.get("dead_time_available"):
                cost_parts.append(
                    f"死亡时长{_format_duration_seconds(death_cost['total_dead_seconds'])}"
                )
            if death_cost.get("gold_lost_available"):
                cost_parts.append(f"丢失{death_cost['total_gold_lost']}金")
            if death_cost.get("gold_fed_available") or death_cost.get("xp_fed_available"):
                fed_parts = []
                if death_cost.get("gold_fed_available"):
                    fed_parts.append(f"{death_cost['total_gold_fed']}金")
                if death_cost.get("xp_fed_available"):
                    fed_parts.append(f"{death_cost['total_xp_fed']}经验")
                cost_parts.append(f"给出{'/'.join(fed_parts)}")
            if cost_parts:
                evidence += (
                    f" 死亡事件成本：覆盖{death_cost.get('covered_deaths', 0)}/{len(death_events)}次，"
                    f"{'，'.join(cost_parts)}。"
                )
            tags = []
            if death_cost.get("dieback_count"):
                tags.append(f"买活后再死{death_cost['dieback_count']}次")
            if death_cost.get("burst_death_count"):
                tags.append(f"爆发死亡{death_cost['burst_death_count']}次")
            if death_cost.get("engaged_death_count"):
                tags.append(f"交战中死亡{death_cost['engaged_death_count']}次")
            if tags:
                evidence += f" STRATZ标记：{'、'.join(tags)}。"
        death_position_labels = [
            f"{item.get('minute')}分 {item.get('position_label')}"
            for item in death_events
            if item.get("position_label")
        ]
        if death_position_labels:
            evidence += f" 死亡坐标覆盖 {len(death_position_labels)}/{len(death_events)} 次。"
        nearby_deaths = [
            item for item in death_events
            if isinstance(item.get("nearby_context"), dict)
            and item["nearby_context"].get("sampled_other_players")
        ]
        outnumbered_deaths = [
            item for item in nearby_deaths
            if item["nearby_context"].get("enemies_within_radius_count", 0)
            > item["nearby_context"].get("allies_within_radius_count", 0)
        ]
        if nearby_deaths:
            nearby_radius = nearby_deaths[0]["nearby_context"].get("radius_units") or 1600
            evidence += (
                f" 回放{int(nearby_radius)}范围局部人数覆盖{len(nearby_deaths)}/{len(death_events)}次死亡；"
                f"其中{len(outnumbered_deaths)}次敌方人数多于队友"
            )
            if outnumbered_deaths:
                evidence += "，时间: " + "、".join(
                    f"{item.get('minute')}分" for item in outnumbered_deaths[:12]
                )
            evidence += "。"
        if missing_note:
            evidence += f" {missing_note}"
        cluster_labels = _death_cluster_labels(events["deaths"])
        if cluster_labels:
            evidence += " 连续死亡簇: " + "、".join(cluster_labels[:4]) + "。"
        automatic_checks = ["死亡时间"]
        if death_cost.get("dead_time_available"):
            automatic_checks.append("逐次死亡时长")
        if death_position_labels:
            automatic_checks.append("原始坐标")
        if cluster_labels:
            automatic_checks.append("连续死亡簇")
        replay_check = (
            f"系统已自动对齐{'、'.join(automatic_checks)}与相邻目标/资源事件窗口；"
            "未采集字段不会作为死亡原因写入结论。"
        )
        if death_cost.get("available"):
            source_label = death_cost.get("source") or "原始事件源"
            replay_check += (
                f" 已显示的死亡成本字段直接取自{source_label}，不由系统估算；"
                "数据源未提供的金钱或经验字段不会显示为0。"
            )
        if death_position_labels:
            replay_check += " 原始坐标明细保留在死亡事件与坐标图，不生成地图区域名。"
        death_action = "下一局每次带线或参团前先判断敌方关键控制、己方TP支援、撤退路线和买活/盾时间。"
        if cluster_labels:
            replay_check += " 连续死亡簇: " + "、".join(cluster_labels[:4]) + "。"
            death_action = "下一局一旦死亡，复活后3分钟只接安全线、队友身边战斗或已有视野目标；再带线或参团前先确认敌方关键控制、己方TP支援和撤退路线。"
        if outnumbered_deaths:
            replay_check += (
                " 局部人数直接取Valve回放全员位置与生命状态采样；"
                "只比较死亡瞬间1600单位内存活英雄，不把全图人数、战争迷雾或技能可用性写成结论。"
            )
            death_action = (
                "下一局接战前执行人数硬规则：可见敌方人数多于1600范围内队友时不先手，"
                "立即向最近队友方向撤退或等待支援；复活后的第一波仍只接安全资源或队友身边战斗。"
            )
        impact_parts = ["死亡会减少本人可行动时间"]
        if any((
            death_cost.get("gold_lost_available"),
            death_cost.get("gold_fed_available"),
            death_cost.get("xp_fed_available"),
        )):
            impact_parts.append("数据源提供的金钱/经验成本已按实际字段计入")
        impact_parts.append("目标与资源影响只按真实相邻窗口记录，不扩大为因果归责")
        current_death_rate = derived.get("deaths_per_10_min", 0) or 0
        death_rate_target = _next_game_rate_target(current_death_rate)
        post_25_deaths = sum(
            isinstance(item.get("minute"), (int, float)) and item["minute"] >= 25
            for item in death_events
        )
        post_25_target = _next_game_count_target(post_25_deaths)
        cluster_target = _next_game_count_target(len(cluster_labels))
        outnumbered_target = _next_game_count_target(len(outnumbered_deaths))
        training_goal = (
            f"下一局把每10分钟死亡从{current_death_rate}降到不超过{death_rate_target}；"
            f"25分钟后死亡从{post_25_deaths}次降到不超过{post_25_target}次；"
            f"连续死亡簇从{len(cluster_labels)}个降到不超过{cluster_target}个。"
        )
        success_metric = (
            f"每10分钟死亡不超过{death_rate_target}；"
            f"25分钟后死亡不超过{post_25_target}次；"
            f"连续5分钟内死亡簇不超过{cluster_target}个。"
        )
        if outnumbered_deaths:
            training_goal += (
                f" 先把1600范围敌多于友的死亡从{len(outnumbered_deaths)}次降到"
                f"不超过{outnumbered_target}次。"
            )
            success_metric += f" 1600范围敌多于友的死亡不超过{outnumbered_target}次。"
        findings.append(_finding(
            priority,
            "death_review",
            evidence,
            "；".join(impact_parts) + "。",
            death_action,
            replay_check,
            training_goal,
            success_metric,
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
        evidence = f"本局死亡 {result.get('kda', {}).get('deaths', 0)} 次，但缺少死亡事件时间线。"
        if dead_time_label and dead_time_share_pct is not None:
            evidence += f" OpenDota死亡占时 {dead_time_label}（{dead_time_share_pct}%）。"
        findings.append(_finding(
            "medium",
            "death_review",
            evidence,
            "只看死亡总数无法判断是对线被抓、中期带线送节奏，还是后期团战选择错误。",
            action,
            replay_check,
            "下一局优先让系统拿到死亡时间线；拿到后按死亡分钟分阶段修正带线和参团风险。",
            "数据验收：下一份报告死亡覆盖率=100%；否则只记录数据缺口，不给分钟级死亡结论。",
        ))

    resource_delta_windows = timeline.get("death_resource_deltas") or []
    dropped_resource_windows = [
        window for window in resource_delta_windows
        if _has_meaningful_death_resource_drop(window)
    ]
    if dropped_resource_windows and role_id in ("pos1", "pos2", "pos3", "unknown", "unknown_lane"):
        evidence = "；".join(
            f"{window.get('evidence_label')}（{window.get('before_window_label')}→{window.get('after_window_label')}）"
            for window in dropped_resource_windows[:4]
            if window.get("evidence_label")
        )
        resource_drop_target = _next_game_count_target(len(dropped_resource_windows))
        findings.append(_finding(
            "high" if len(dropped_resource_windows) >= 2 else "medium",
            "death_resource_delta",
            f"死亡前后资源下降窗口: {evidence}。",
            "死亡相邻阶段的补刀或经济节奏明显下滑，会让一次阵亡继续影响下一段刷钱、守塔或控图节奏。",
            "下一局每次复活后先完成一个可记录资源动作：TP安全线、收近区野，或跟队友拿已有视野目标；如果必须集合，先确认这波集合能换塔、盾或击杀。",
            "系统只比较死亡前后真实分钟数组，不判断死亡原因；报告只把这些窗口列为资源恢复验收点，不把复活路径、TP落点或无视野进入作为结论。",
            f"下一局把死亡前后资源明显下降窗口从{len(dropped_resource_windows)}个降到不超过{resource_drop_target}个。",
            f"死亡前后资源明显下降窗口不超过{resource_drop_target}个；复活后3分钟完成一波安全线或近区野区资源。",
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
        has_low_farm = False
        has_low_conversion = False
        if key_purchases and post_windows:
            post_summary = "；".join(item.get("summary", "") for item in post_windows[:4] if item.get("summary"))
            goal_details = _item_window_goal_details(post_windows)
            check_parts = [f"系统已计算关键装备后的对应窗口: {post_summary}"]
            if goal_details["low_farm"]:
                has_low_farm = True
                check_parts.append("低刷钱窗口: " + "；".join(goal_details["low_farm"][:3]))
            if goal_details["low_conversion"]:
                has_low_conversion = True
                check_parts.append("低转化窗口: " + "；".join(goal_details["low_conversion"][:3]))
            replay_check = "；".join(check_parts) + "。"
            failed_summaries = set(goal_details["low_farm"] + goal_details["low_conversion"])
            failed_windows = [
                window for window in post_windows
                if window.get("summary") in failed_summaries
            ]
            evidence = "；".join(
                f"{window.get('item_name', '关键装备')} {window.get('minute')}分钟，{window.get('summary')}"
                for window in failed_windows[:4]
            )
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
                low_names = "、".join(goal_details.get("low_names", [])[:3]) if post_windows else "关键装备"
                if has_low_farm and not has_low_conversion:
                    why = "刷钱装后的真实资源窗口偏低，会直接推迟下一件装备和下一次可控地图窗口。"
                    action = "下一局刷钱装完成后5分钟保持线野连续；集合前先收安全线，除非队伍已经形成明确的塔、盾或高胜率击杀窗口。"
                    training_goal = f"下一局 {low_names} 成型后5分钟只验收资源增长，不用参战数代替刷钱效率。"
                    success_metric = f"{FARM_ACCELERATION_SUCCESS_METRIC}。"
                elif has_low_conversion and not has_low_farm:
                    why = "强势装完成后的真实参战和建筑伤害都偏低，装备窗口没有形成可记录的地图动作。"
                    action = "下一局强势装完成后2分钟内明确一个地图动作：控盾、推塔、逼高、入侵或带线牵制。"
                    training_goal = f"下一局 {low_names} 成型后2分钟内完成一次可记录地图动作。"
                    success_metric = f"{MAP_CONVERSION_SUCCESS_METRIC}。"
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

    kill_participation = teamfight_participation_pct
    participation_source = "OpenDota参战率" if kill_participation is not None else "参战率"
    if kill_participation is None:
        kill_participation = derived.get("kill_participation_pct")
    if kill_participation is not None and kill_participation < 40 and result.get("duration_min", 0) >= 20:
        findings.append(_finding(
            "medium",
            "map_impact",
            f"{participation_source} {kill_participation}%。",
            "该实际值低于报告40%训练阈值，因此本局把可参战路线列为下一局的量化训练项；汇总字段本身不证明未参战原因。",
            "下一局把刷钱路线设计成能顺路压塔、控盾或支援队友，而不是远离目标单刷。",
            "系统使用OpenDota参战率汇总字段，并与击杀/助攻及关键装备后窗口交叉；汇总值不判断未参战原因。",
            "下一局每条刷钱路线都要顺路覆盖一座塔、一条高价值兵线或一次支援入口。",
            "参战率不低于40%；关键装备后2分钟至少完成一次参战或推塔动作。",
        ))

    if benchmark_finding:
        findings.append(benchmark_finding)

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
    return findings


def _item_detail(item_id):
    items_db = _load_json("items.json")
    info = items_db.get(str(item_id), {}) if isinstance(items_db, dict) else {}
    name = ITEM_FALLBACKS.get(item_id) or info.get("display") or info.get("displayName") or info.get("name")
    return {
        "id": item_id,
        "name": name or f"Item #{item_id}",
        "slug": info.get("name"),
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


def _field_ledger_item(
    identifier,
    label,
    source,
    *,
    required,
    applicable=True,
    expected_fields=None,
    present_fields=None,
    coverage_pct=None,
    weight=1,
    details=None,
):
    expected = list(expected_fields or [])
    present = list(present_fields or [])
    if not applicable:
        status = "not_applicable"
        coverage = 100
        missing = []
    else:
        if coverage_pct is None:
            coverage = round(len(present) / len(expected) * 100) if expected else 0
        else:
            coverage = round(max(0, min(100, coverage_pct)))
        status = "available" if coverage == 100 else "missing" if coverage == 0 else "partial"
        missing = [field for field in expected if field not in set(present)]
    coverage_label = (
        "本局不适用"
        if status == "not_applicable"
        else f"{len(present)}/{len(expected)}个字段，覆盖{coverage}%"
        if expected
        else f"覆盖{coverage}%"
    )
    item = {
        "id": identifier,
        "label": label,
        "source": source,
        "required": bool(required),
        "applicable": bool(applicable),
        "status": status,
        "coverage_pct": coverage,
        "coverage": coverage_label,
        "expected_fields": expected,
        "present_fields": present,
        "missing_fields": missing,
        "weight": weight,
    }
    item.update(details or {})
    return item


def _build_field_ledger(result, match_data, stratz_player=None, opendota_data=None):
    timeline = result.get("timeline") or {}
    events = result.get("events") or {}
    context = result.get("context") or {}
    performance = result.get("performance_context") or {}
    extended = result.get("extended_metrics") or {}
    role_id = (result.get("role_profile") or {}).get("id") or "unknown"
    deaths_expected = int((result.get("kda") or {}).get("deaths") or 0)
    kills_assists_expected = int((result.get("kda") or {}).get("kills") or 0) + int(
        (result.get("kda") or {}).get("assists") or 0
    )

    def valid_positive_number(value):
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and value > 0
        )

    identity_fields = (
        "match_id", "account_id", "hero_id", "player_slot", "duration",
        "start_time", "radiant_win", "is_radiant",
    )
    identity_present = []
    for field in identity_fields:
        value = match_data.get(field)
        if field in {"match_id", "account_id", "hero_id", "duration", "start_time"}:
            valid = valid_positive_number(value)
        elif field == "player_slot":
            valid = _valid_player_slot(value)
        else:
            valid = value in (True, False, 0, 1) and not isinstance(value, str)
        if valid:
            identity_present.append(field)

    core_fields = (
        "kills", "deaths", "assists", "gold_per_min", "xp_per_min", "last_hits",
        "denies", "hero_damage", "tower_damage", "hero_healing", "net_worth", "level",
    )
    core_present = [
        field for field in core_fields
        if isinstance(match_data.get(field), (int, float))
        and not isinstance(match_data.get(field), bool)
        and math.isfinite(float(match_data[field]))
        and match_data[field] >= 0
    ]

    players = (opendota_data or {}).get("players")
    player_rows = players if isinstance(players, list) else []
    participant_slots = (0, 1, 2, 3, 4, 128, 129, 130, 131, 132)
    participant_expected = [f"slot_{slot}" for slot in participant_slots]
    valid_participant_slots = {
        player.get("player_slot")
        for player in player_rows if isinstance(player, dict)
        and _valid_player_slot(player.get("player_slot"))
        and valid_positive_number(player.get("hero_id"))
    }
    participant_present = [
        f"slot_{slot}" for slot in participant_slots if slot in valid_participant_slots
    ]
    participant_count = len(participant_present)

    role_fields = ("role", "lane_assignment")
    role_present = []
    role_profile = result.get("role_profile") or {}
    formula_role = role_profile.get("classification") == "formula"
    if _known_enum((stratz_player or {}).get("position")) or _known_enum((stratz_player or {}).get("role")):
        role_present.append("role")
    elif formula_role:
        role_present.append("role")
    if (
        _known_enum((stratz_player or {}).get("lane"))
        or context.get("opendota_lane_role") in {1, 2, 3, 4}
        or context.get("replay_lane_role") in {1, 2, 3, 4}
    ):
        role_present.append("lane_assignment")
    if formula_role:
        role_source = role_profile.get("source") or "真实比赛数据角色公式"
    elif _known_enum((stratz_player or {}).get("position")):
        role_source = "STRATZ玩家位置"
    elif _known_enum((stratz_player or {}).get("role")) and _known_enum((stratz_player or {}).get("lane")):
        role_source = "STRATZ角色与分路"
    elif _known_enum((stratz_player or {}).get("role")) and context.get("opendota_lane_role") in {1, 2, 3, 4}:
        role_source = "STRATZ角色 + OpenDota解析分路"
    elif _known_enum((stratz_player or {}).get("role")) and context.get("replay_lane_role") in {1, 2, 3, 4}:
        role_source = "STRATZ角色 + Valve回放分路"
    elif context.get("replay_lane_role") in {1, 2, 3, 4}:
        role_source = "Valve回放分路（位置未细分）"
    else:
        role_source = "OpenDota解析分路"

    ability_sources = list(dict.fromkeys(
        item.get("source")
        for item in (result.get("skills") or {}).get("upgrades") or []
        if isinstance(item, dict) and item.get("source")
    ))
    ability_source_labels = {
        "stratz": "STRATZ",
        "opendota": "OpenDota",
        "valve_replay_gem": "Valve回放原始事件（gem-dota）",
    }
    ability_source = " + ".join(
        ability_source_labels.get(source, source) for source in ability_sources
    ) or "未获取"

    benchmark_metrics = {
        item.get("id")
        for item in (result.get("opendota_benchmarks") or {}).get("metrics") or []
        if isinstance(item, dict)
    }
    benchmark_expected = (
        "gold_per_min", "xp_per_min", "last_hits_per_min",
        "hero_damage_per_min", "tower_damage",
    )
    benchmark_present = [field for field in benchmark_expected if field in benchmark_metrics]

    performance_fields = (
        "lane_efficiency_pct", "teamfight_participation_pct",
        "dead_time_seconds", "buyback_count",
    )
    performance_present = [field for field in performance_fields if performance.get(field) is not None]

    extended_expected = (
        "actions_per_min", "stuns", "damage_taken", "obs_placed", "sen_placed",
        "observer_kills", "sentry_kills", "camps_stacked", "rune_pickups",
        "courier_kills", "tower_kills", "roshan_kills", "buyback_count",
        "item_uses", "ability_uses",
    )
    extended_observed = set(extended.get("observed_fields") or [])
    extended_present = [field for field in extended_expected if field in extended_observed]

    death_observed = int(events.get("death_count_observed") or 0)
    death_position_count = int(events.get("death_position_count") or 0)
    death_nearby_context_count = int(events.get("death_nearby_context_count") or 0)
    buybacks_expected = int(performance.get("buyback_count") or 0)
    buybacks_observed = len(events.get("buybacks") or [])
    fight_observed = len(events.get("kills") or []) + len(events.get("assists") or [])
    minute_count = int(timeline.get("duration_minutes_observed") or 0)
    # Minute arrays cover completed minutes; the final partial minute is not missing data.
    duration_seconds = int(result.get("duration_seconds") or 0)
    duration_target = max(
        1,
        duration_seconds // 60 if duration_seconds else int(result.get("duration_min") or 0),
    )

    return [
        _field_ledger_item(
            "match_identity", "比赛身份与时钟", "OpenDota比赛详情",
            required=True, expected_fields=identity_fields, present_fields=identity_present,
            weight=3,
        ),
        _field_ledger_item(
            "core_stats", "比赛核心数据", "OpenDota比赛详情",
            required=True, expected_fields=core_fields, present_fields=core_present, weight=3,
        ),
        _field_ledger_item(
            "participants", "十人对局数据", "OpenDota比赛详情",
            required=True, expected_fields=participant_expected, present_fields=participant_present,
            coverage_pct=participant_count / 10 * 100, weight=2,
        ),
        _field_ledger_item(
            "role_position", "位置与分路", role_source,
            required=True, expected_fields=role_fields, present_fields=role_present, weight=2,
            details={
                "exact_position_available": _known_enum((stratz_player or {}).get("position")),
                "classification": role_profile.get("classification") or "source_field",
                "classification_evidence": role_profile.get("evidence"),
            },
        ),
        _field_ledger_item(
            "ability_build", "技能加点", ability_source,
            required=True, expected_fields=["ability_upgrades"],
            present_fields=["ability_upgrades"] if (result.get("skills") or {}).get("upgrades") else [],
        ),
        _field_ledger_item(
            "final_items", "最终装备", "OpenDota比赛详情",
            required=True, expected_fields=["final_items"],
            present_fields=["final_items"] if (result.get("items") or {}).get("final_items") else [],
        ),
        _field_ledger_item(
            "minute_lh", "分钟补刀", timeline.get("source_label") or "未返回",
            required=True, expected_fields=["last_hits_by_minute"],
            present_fields=["last_hits_by_minute"] if timeline.get("last_hits_by_minute") else [],
            coverage_pct=min(100, minute_count / duration_target * 100), weight=2,
        ),
        _field_ledger_item(
            "minute_gold", "分钟经济", timeline.get("source_label") or "未返回",
            required=True, expected_fields=["gold_by_minute"],
            present_fields=["gold_by_minute"] if timeline.get("gold_by_minute") else [],
            coverage_pct=min(100, len(timeline.get("gold_by_minute") or []) / duration_target * 100), weight=2,
        ),
        _field_ledger_item(
            "minute_xp", "分钟经验", timeline.get("source_label") or "未返回",
            required=True, expected_fields=["experience_by_minute"],
            present_fields=["experience_by_minute"] if timeline.get("experience_by_minute") else [],
            coverage_pct=min(100, len(timeline.get("experience_by_minute") or []) / duration_target * 100), weight=2,
        ),
        _field_ledger_item(
            "minute_damage", "分钟英雄/建筑伤害", timeline.get("source_label") or "未返回",
            required=True, expected_fields=["hero_damage_by_minute", "tower_damage_by_minute"],
            present_fields=[
                field for field in ("hero_damage_by_minute", "tower_damage_by_minute")
                if timeline.get(field)
            ], weight=2,
        ),
        _field_ledger_item(
            "purchases", "购买时间", _event_source_label(events.get("purchase_source")),
            required=True, expected_fields=["purchase_events"],
            present_fields=["purchase_events"] if events.get("has_purchase_payload") and events.get("purchases") else [],
            weight=2,
        ),
        _field_ledger_item(
            "deaths", "死亡时间", "STRATZ/OpenDota死亡事件",
            required=deaths_expected > 0, applicable=deaths_expected > 0,
            expected_fields=[f"death_{index + 1}" for index in range(deaths_expected)],
            present_fields=[f"death_{index + 1}" for index in range(min(death_observed, deaths_expected))],
            coverage_pct=(death_observed / deaths_expected * 100) if deaths_expected else 100,
            weight=3,
        ),
        _field_ledger_item(
            "buyback_events", "买活时间", _event_source_label(events.get("buyback_source")),
            required=buybacks_expected > 0, applicable=buybacks_expected > 0,
            expected_fields=[f"buyback_{index + 1}" for index in range(buybacks_expected)],
            present_fields=[
                f"buyback_{index + 1}"
                for index in range(min(buybacks_observed, buybacks_expected))
            ],
            coverage_pct=(buybacks_observed / buybacks_expected * 100) if buybacks_expected else 100,
            weight=3,
            details={
                "aggregate_expected_count": buybacks_expected,
                "timed_event_count": buybacks_observed,
            },
        ),
        _field_ledger_item(
            "death_positions", "死亡坐标", "STRATZ位置采样/OpenDota团战坐标",
            required=deaths_expected > 0, applicable=deaths_expected > 0,
            expected_fields=[f"death_position_{index + 1}" for index in range(deaths_expected)],
            present_fields=[f"death_position_{index + 1}" for index in range(min(death_position_count, deaths_expected))],
            coverage_pct=(death_position_count / deaths_expected * 100) if deaths_expected else 100,
            weight=2,
        ),
        _field_ledger_item(
            "death_nearby_players", "死亡瞬间局部人数", "Valve回放全员位置与生命状态采样",
            required=deaths_expected > 0, applicable=deaths_expected > 0,
            expected_fields=[f"death_nearby_{index + 1}" for index in range(deaths_expected)],
            present_fields=[
                f"death_nearby_{index + 1}"
                for index in range(min(death_nearby_context_count, deaths_expected))
            ],
            coverage_pct=(death_nearby_context_count / deaths_expected * 100) if deaths_expected else 100,
            weight=2,
        ),
        _field_ledger_item(
            "fight_events", "个人击杀/助攻时间", _event_source_label(events.get("fight_source")),
            required=kills_assists_expected > 0, applicable=kills_assists_expected > 0,
            expected_fields=["scoreboard_kills", "scoreboard_assists", "timed_fight_events"],
            present_fields=[
                "scoreboard_kills",
                "scoreboard_assists",
                *(["timed_fight_events"] if fight_observed else []),
            ],
            coverage_pct=events.get("fight_timing_coverage_pct"),
            weight=2,
            details={
                "aggregate_expected_count": kills_assists_expected,
                "timed_event_count": fight_observed,
                "timing_coverage_pct": events.get("fight_timing_coverage_pct"),
                "timing_complete": events.get("fight_timing_complete"),
            },
        ),
        _field_ledger_item(
            "objectives", "地图目标事件", _event_source_label(events.get("objective_source")),
            required=True, expected_fields=["building_events", "major_objective_events"],
            present_fields=(
                ["building_events", "major_objective_events"]
                if events.get("has_full_objective_payload")
                else ["building_events"] if events.get("has_objective_payload") else []
            ),
            weight=2,
        ),
        _field_ledger_item(
            "vision_events", "视野事件", _event_source_label(events.get("vision_source")),
            required=role_id == "support", expected_fields=["typed_ward_events"],
            present_fields=["typed_ward_events"] if events.get("has_vision_event_payload") else [],
            weight=2,
        ),
        _field_ledger_item(
            "hero_benchmarks", "同英雄样本百分位", "OpenDota benchmarks",
            required=True, expected_fields=benchmark_expected, present_fields=benchmark_present, weight=2,
        ),
        _field_ledger_item(
            "performance_context", "对线/参战/死亡占时", performance.get("source") or "未返回",
            required=True, expected_fields=performance_fields, present_fields=performance_present, weight=2,
        ),
        _field_ledger_item(
            "extended_metrics", "扩展战斗/经济/活动数据", extended.get("source") or "未返回",
            required=True, expected_fields=extended_expected, present_fields=extended_present, weight=2,
        ),
    ]


def _field_ledger_score(field_ledger):
    required = [item for item in field_ledger if item.get("required") and item.get("applicable")]
    total_weight = sum(item.get("weight", 1) for item in required)
    if not required or total_weight <= 0:
        return 0
    weighted = sum(item.get("coverage_pct", 0) * item.get("weight", 1) for item in required)
    return round(weighted / total_weight)


def _build_evidence_sources(result):
    timeline = result.get("timeline") or {}
    events = result.get("events") or {}
    timeline_metrics = []
    if timeline.get("last_hits_by_minute"):
        timeline_metrics.append("补刀")
    if timeline.get("gold_by_minute"):
        timeline_metrics.append("经济")
    if timeline.get("hero_damage_by_minute"):
        timeline_metrics.append("英雄伤害")
    if timeline.get("tower_damage_by_minute"):
        timeline_metrics.append("推塔伤害")
    timeline_minutes = timeline.get("duration_minutes_observed") or 0
    timeline_coverage = (
        f"覆盖 {timeline_minutes} 分钟：{'、'.join(timeline_metrics)}"
        if timeline.get("available") and timeline_metrics
        else "未获取分钟级时间线"
    )

    purchases = events.get("purchases") or []
    key_purchases = events.get("key_purchases") or []
    purchase_coverage = (
        f"{len(purchases)}条购买；{len(key_purchases)}个关键装备完成点"
        if purchases else "未获取购买时间"
    )

    observed_deaths = events.get("death_count_observed") or 0
    death_positions = events.get("death_position_count") or 0
    death_nearby_contexts = events.get("death_nearby_context_count") or 0
    buyback_value = (result.get("performance_context") or {}).get("buyback_count")
    buyback_count = (
        int(buyback_value)
        if isinstance(buyback_value, (int, float)) and not isinstance(buyback_value, bool)
        else None
    )
    timed_buybacks = len(events.get("buybacks") or [])
    no_deaths = (events.get("death_count_expected") or 0) == 0 and observed_deaths == 0
    death_position_coverage = (
        f"覆盖 {death_positions}/{observed_deaths} 次已定位死亡"
        if observed_deaths else "本局没有已定位死亡"
    )
    fight_count = len(events.get("kills") or []) + len(events.get("assists") or [])
    vision_coverage = _vision_coverage_label(events)
    objective_count = len(events.get("objectives") or [])
    benchmark_profile = result.get("opendota_benchmarks") or {}
    benchmark_count = (benchmark_profile.get("summary") or {}).get("metric_count", 0)
    performance_context = result.get("performance_context") or {}
    context_coverage = []
    if performance_context.get("lane_efficiency_pct") is not None:
        context_coverage.append(f"对线效率{performance_context['lane_efficiency_pct']}%")
    if performance_context.get("teamfight_participation_pct") is not None:
        context_coverage.append(f"参战率{performance_context['teamfight_participation_pct']}%")
    if performance_context.get("dead_time_label"):
        context_coverage.append(f"死亡占时{performance_context['dead_time_label']}")
    if performance_context.get("buyback_count") is not None:
        context_coverage.append(f"买活{performance_context['buyback_count']}次")

    return [
        {
            "id": "core_stats",
            "label": "比赛核心数据",
            "source": "OpenDota比赛核心数据",
            "coverage": "KDA、GPM、XPM、补刀、伤害与最终装备",
            "status": "available",
        },
        {
            "id": "timeline",
            "label": "分钟时间线",
            "source": timeline.get("source_label") or "未获取",
            "coverage": timeline_coverage,
            "status": "available" if timeline.get("available") else "missing",
        },
        {
            "id": "purchases",
            "label": "购买时间",
            "source": _event_source_label(events.get("purchase_source")),
            "coverage": purchase_coverage,
            "status": "available" if purchases else "missing",
        },
        {
            "id": "deaths",
            "label": "死亡时间",
            "source": "不适用" if no_deaths else _event_source_label(events.get("death_source")),
            "coverage": events.get("death_coverage_label") or "未获取死亡事件",
            "status": "available" if no_deaths or events.get("death_timeline_complete") else "partial",
        },
        {
            "id": "buyback_events",
            "label": "买活时间",
            "source": (
                "未获取" if buyback_count is None
                else "不适用" if buyback_count == 0
                else _event_source_label(events.get("buyback_source"))
            ),
            "coverage": (
                "未获取买活次数，不能判断是否发生买活"
                if buyback_count is None
                else "本局没有买活" if buyback_count == 0
                else f"已定位 {timed_buybacks}/{buyback_count} 次买活"
            ),
            "status": (
                "missing" if buyback_count is None
                else "available" if buyback_count == 0 or timed_buybacks == buyback_count
                else "partial" if timed_buybacks
                else "missing"
            ),
        },
        {
            "id": "death_positions",
            "label": "死亡位置",
            "source": "不适用" if no_deaths else _event_source_label(events.get("position_source")),
            "coverage": death_position_coverage,
            "status": (
                "available" if no_deaths or (observed_deaths and death_positions == observed_deaths)
                else "partial" if death_positions
                else "missing"
            ),
        },
        {
            "id": "death_nearby_players",
            "label": "死亡瞬间局部人数",
            "source": "不适用" if no_deaths else "Valve回放全员位置与生命状态采样",
            "coverage": (
                "本局没有死亡"
                if no_deaths
                else f"覆盖 {death_nearby_contexts}/{observed_deaths} 次已定位死亡"
            ),
            "status": (
                "available"
                if no_deaths or (observed_deaths and death_nearby_contexts == observed_deaths)
                else "partial" if death_nearby_contexts
                else "missing"
            ),
        },
        {
            "id": "fight_events",
            "label": "击杀/助攻事件",
            "source": _event_source_label(events.get("fight_source")),
            "coverage": (
                events.get("fight_timing_coverage_label")
                if fight_count else "未获取个人击杀/助攻事件"
            ),
            "status": (
                "available" if events.get("fight_timing_complete")
                else "partial" if fight_count
                else "missing"
            ),
        },
        {
            "id": "objectives",
            "label": "地图目标事件",
            "source": _event_source_label(events.get("objective_source")),
            "coverage": (
                f"{objective_count}条塔、兵营、肉山、盾或折磨者事件"
                if events.get("has_full_objective_payload") and objective_count
                else "完整目标字段已返回，本局0条地图目标事件"
                if events.get("has_full_objective_payload")
                else f"{objective_count}条建筑事件；肉山、盾和折磨者等待OpenDota解析"
                if events.get("has_objective_payload")
                else "未获取地图目标事件"
            ),
            "status": (
                "available" if events.get("has_full_objective_payload")
                else "partial" if events.get("has_objective_payload")
                else "missing"
            ),
        },
        {
            "id": "vision_events",
            "label": "视野事件",
            "source": _event_source_label(events.get("vision_source")),
            "coverage": vision_coverage,
            "status": "available" if events.get("has_vision_log") else "missing",
        },
        {
            "id": "hero_benchmarks",
            "label": "英雄样本百分位",
            "source": benchmark_profile.get("source") or "未获取",
            "coverage": f"{benchmark_count}项同英雄样本百分位" if benchmark_count else "未获取英雄样本百分位",
            "status": "available" if benchmark_count else "missing",
        },
        {
            "id": "performance_context",
            "label": "分路与参战汇总",
            "source": performance_context.get("source") or "未获取",
            "coverage": "、".join(context_coverage) if context_coverage else "未获取对线、参战与死亡占时汇总",
            "status": "available" if context_coverage else "missing",
        },
    ]


def _evidence_coverage_score(evidence_sources):
    if not evidence_sources:
        return 0
    weights = {
        "available": 100,
        "partial": 70,
        "missing": 0,
    }
    total = sum(weights.get(item.get("status"), 0) for item in evidence_sources)
    return round(total / len(evidence_sources))


def _evidence_coverage_limitations(evidence_sources, explained_ids=None):
    explained_ids = set(explained_ids or ())
    limitations = []
    for item in evidence_sources or []:
        if item.get("id") in explained_ids:
            continue
        status = item.get("status")
        label = item.get("label") or item.get("id") or "证据"
        coverage = item.get("coverage") or "覆盖未记录"
        if status == "partial":
            limitations.append(f"{label}部分覆盖：{coverage}；只按已覆盖证据复核，不扩大归因")
        elif status == "missing":
            limitations.append(f"{label}缺失：{coverage}；不用于复盘归因")
    return limitations


def _normalize_source_reconciliation(validation):
    normalized = dict(validation or {})
    checks = []
    labels_by_comparison = {
        "opendota_aggregate_to_replay_aggregate": ("OpenDota", "Valve回放"),
        "replay_scoreboard_to_event_timeline": ("回放记分板", "回放事件时间线"),
        "replay_life_state_intervals_to_replay_aggregate": (
            "回放总死亡时长",
            "逐秒生命状态",
        ),
    }
    for source in normalized.get("checks") or []:
        if not isinstance(source, dict):
            continue
        item = dict(source)
        left_label, right_label = labels_by_comparison.get(
            item.get("comparison"),
            ("OpenDota", "Valve回放"),
        )
        item.setdefault("left_label", left_label)
        item.setdefault("right_label", right_label)
        checks.append(item)
    normalized["checks"] = checks
    return normalized


def _build_data_quality(
    match_data,
    stratz_data,
    stratz_player,
    result,
    opendota_data=None,
    replay_data=None,
):
    available = ["opendota_core_stats"]
    limitations = []
    score = 35
    source_reconciliation = _normalize_source_reconciliation(
        (replay_data or {}).get("validation")
    )
    if replay_data:
        available.append("valve_replay_gem")
    if source_reconciliation.get("status") == "conflict":
        conflicts = [
            item.get("metric")
            for item in source_reconciliation.get("checks") or []
            if item.get("status") == "conflict" and item.get("metric")
        ]
        limitations.append(
            "证据源对账存在冲突: "
            + "、".join(conflicts)
            + "；冲突字段不静默覆盖"
        )

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
        if (result.get("role_profile") or {}).get("classification") == "formula":
            limitations.append(
                "STRATZ精确位置字段不可用；职责由OpenDota真实分路与队内资源排序公式识别，"
                f"依据：{(result.get('role_profile') or {}).get('evidence')}"
            )
        elif len(result.get("context", {}).get("ally_lineup") or []) == 5 and len(result.get("context", {}).get("enemy_lineup") or []) == 5:
            limitations.append("缺少Stratz位置字段；完整阵容已由OpenDota补齐，具体1-5号位不做无证据判断")
        else:
            limitations.append("缺少Stratz位置字段，且OpenDota未提供完整10人阵容")

    if result.get("context", {}).get("enemy_heroes"):
        available.append("draft_context")
        score += 10

    timeline = result.get("timeline", {})
    events = result.get("events", {})
    role_profile = result.get("role_profile", {})
    has_lh_timeline = bool(timeline.get("last_hits_by_minute"))
    has_gold_timeline = bool(timeline.get("gold_by_minute"))
    has_purchase_log = bool(match_data.get("purchase_log") or events.get("has_purchase_timeline"))
    has_fight_log = bool(match_data.get("kills_log") or events.get("has_fight_log"))
    has_vision_log = bool(events.get("has_vision_log"))
    has_objective_log = bool(events.get("has_objective_log"))

    if has_lh_timeline:
        available.append("lane_timeline")
        score += 6
    else:
        limitations.append("缺少分钟补刀时间线，不能计算对线补刀与低效率窗口")
    if has_gold_timeline:
        available.append("gold_timeline")
        score += 6
    else:
        limitations.append("缺少分钟经济时间线，不能计算阶段经济与装备后刷钱转化")
    if has_lh_timeline or has_gold_timeline:
        if timeline.get("source") == "opendota_parsed_logs":
            available.append("opendota_parsed_logs")
        if "stratz_playback_cs" in (timeline.get("source") or ""):
            available.append("stratz_playback_cs")

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
        if events.get("has_death_positions"):
            for source in (events.get("position_source") or "").split("+"):
                if source and source not in available:
                    available.append(source)
        if events.get("has_death_nearby_context"):
            available.append("valve_replay_all_player_positions")
        score += 7
    else:
        limitations.append("缺少团战/击杀日志，不能还原每次死亡和团战站位")

    if has_vision_log:
        available.append("vision_events")
        score += 7

    if events.get("has_full_objective_payload"):
        available.append("opendota_objectives")
        score += 8
    elif has_objective_log:
        available.append("stratz_building_objectives")
        limitations.append("STRATZ已返回建筑死亡事件；肉山、不朽盾和折磨者事件仍等待OpenDota解析补齐")
    else:
        limitations.append("缺少地图目标事件，不能还原推塔、兵营、肉山和不朽盾时间线")

    if (result.get("opendota_benchmarks") or {}).get("available"):
        available.append("hero_benchmarks")
        score += 7

    if (result.get("performance_context") or {}).get("available"):
        performance_source = (result.get("performance_context") or {}).get("source") or ""
        available.append(
            "opendota_performance_context"
            if performance_source == "OpenDota对局汇总字段"
            else "multi_source_performance_context"
        )
        score += 5

    expected_deaths = (result.get("kda") or {}).get("deaths", 0) or 0
    observed_deaths = (result.get("events") or {}).get("death_count_observed")
    if observed_deaths is None:
        observed_deaths = len((result.get("events") or {}).get("deaths") or [])
    if expected_deaths > observed_deaths:
        limitations.append(f"死亡时间线不完整：公共数据源定位{observed_deaths}/{expected_deaths}次死亡")

    if (
        ((result.get("kda") or {}).get("kills", 0) or 0)
        + ((result.get("kda") or {}).get("assists", 0) or 0)
        and not events.get("fight_timing_complete")
    ):
        limitations.append(
            "击杀/助攻事件时间覆盖："
            f"{events.get('fight_timing_coverage_label') or '事件源未返回完整时间'}；"
            "记分板K/A汇总仍为权威总数，窗口公式只使用真实带时间事件，不补造时间点"
        )

    if role_profile.get("id") == "support" and not has_vision_log:
        limitations.append("辅助位缺少视野事件，不能精确评价插眼/排眼质量")

    for warning in (stratz_data or {}).get("_fetch_warnings", []):
        limitations.append(f"STRATZ抓取限制: {warning}")
    for warning in (opendota_data or {}).get("_fetch_warnings", []):
        limitations.append(f"OpenDota抓取状态: {warning}")

    evidence_sources = _build_evidence_sources(result)
    field_ledger = _build_field_ledger(
        result,
        match_data,
        stratz_player=stratz_player,
        opendota_data=opendota_data,
    )
    blocking_gaps = [
        item["id"]
        for item in field_ledger
        if item.get("required") and item.get("applicable") and item.get("status") != "available"
    ]
    score = _field_ledger_score(field_ledger)
    explained_ids = {"timeline", "purchases", "fight_events", "objectives"}
    if expected_deaths > observed_deaths:
        explained_ids.add("deaths")
    if role_profile.get("id") == "support" and not has_vision_log:
        explained_ids.add("vision_events")
    limitations.extend(_evidence_coverage_limitations(evidence_sources, explained_ids))
    existing_limits = set(limitations)
    for item in field_ledger:
        if item["id"] not in blocking_gaps:
            continue
        message = (
            f"{item['label']}覆盖不足：{item['coverage']}；"
            f"缺少{', '.join(item['missing_fields']) or '部分返回值'}"
        )
        if message not in existing_limits:
            limitations.append(message)
            existing_limits.add(message)

    required_items = [item for item in field_ledger if item.get("required") and item.get("applicable")]
    required_complete = sum(item.get("status") == "available" for item in required_items)

    return {
        "score": min(score, 100),
        "available": available,
        "limitations": limitations,
        "evidence_sources": evidence_sources,
        "field_ledger": field_ledger,
        "blocking_gaps": blocking_gaps,
        "source_reconciliation": source_reconciliation,
        "required_complete": not blocking_gaps,
        "coverage_summary": {
            "required_complete": required_complete,
            "required_total": len(required_items),
            "all_available": sum(item.get("status") in {"available", "not_applicable"} for item in field_ledger),
            "all_total": len(field_ledger),
        },
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
    result["suggestions"] = [
        {
            "priority": finding.get("priority", "low"),
            "category": finding.get("category", "review"),
            "message": finding.get("action", ""),
            "formula_score": finding.get("formula_score"),
        }
        for finding in select_formula_findings(result)
    ]


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
