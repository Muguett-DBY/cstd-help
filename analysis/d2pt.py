import re
import json
import requests
from bs4 import BeautifulSoup


HERO_NAME_MAP = {
    "antimage": "Anti-Mage", "axe": "Axe", "bane": "Bane",
    "bloodseeker": "Bloodseeker", "crystal_maiden": "Crystal Maiden",
    "drow_ranger": "Drow Ranger", "earthshaker": "Earthshaker",
    "juggernaut": "Juggernaut", "kunkka": "Kunkka", "lina": "Lina",
    "lion": "Lion", "mirror": "Mirror", "mirana": "Mirana",
    "morphling": "Morphling", "nevermore": "Shadow Fiend",
    "phantom_lancer": "Phantom Lancer", "puck": "Puck",
    "pudge": "Pudge", "razor": "Razor", "sand_king": "Sand King",
    "slardar": "Slardar", "sniper": "Sniper", "spectre": "Spectre",
    "storm_spirit": "Storm Spirit", "sven": "Sven", "tidehunter": "Tidehunter",
    "vengefulspirit": "Vengeful Spirit", "windrunner": "Windranger",
    "zuus": "Zeus", "zuus": "Zeus", "ember_spirit": "Ember Spirit",
    "faceless_void": "Faceless Void", "weaver": "Weaver",
    "lich": "Lich", "shadow_shaman": "Shadow Shaman",
    "tinker": "Tinker", "tiny": "Tiny", "ursa": "Ursa",
    "visage": "Visage", "lifestealer": "Lifestealer",
    "naga_siren": "Naga Siren", "furion": "Nature's Prophet",
    "death_prophet": "Death Prophet", "phantom_assassin": "Phantom Assassin",
    "pugna": "Pugna", "templar_assassin": "Templar Assassin",
    "viper": "Viper", "luna": "Luna", "dragon_knight": "Dragon Knight",
    "dazzle": "Dazzle", "ancient_apparition": "Ancient Apparition",
    "ounty_hunter": "Bounty Hunter", "shredder": "Timbersaw",
    "centaur": "Centaur Warrunner", "magnataur": "Magnus",
    "slark": "Slark", "medusa": "Medusa", "troll_warlord": "Troll Warlord",
    "ember_spirit": "Ember Spirit", "legion_commander": "Legion Commander",
    "terrorblade": "Terrorblade", "phoenix": "Phoenix",
    "abyssal_underlord": "Underlord", "pangolier": "Pangolier",
    "grimstroke": "Grimstroke", "void_spirit": "Void Spirit",
    "mars": "Mars", "snapfire": "Snapfire", "hoodwink": "Hoodwink",
    "dawnbreaker": "Dawnbreaker", "marci": "Marci", "primal_beast": "Primal Beast",
    "muerta": "Muerta", "ringmaster": "Ringmaster", "kez": "Kez",
}

ITEM_DB = {}


def _load_item_db():
    global ITEM_DB
    if ITEM_DB:
        return
    try:
        import os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "analysis", "rules", "items.json")
        with open(path, "r", encoding="utf-8") as f:
            ITEM_DB = json.load(f)
    except Exception:
        pass


def get_hero_url(hero_name):
    name = hero_name.lower().replace(" ", "_").replace("'", "")
    return f"https://dota2protracker.com/hero/{hero_name}"


def fetch_d2pt_page(hero_name):
    url = get_hero_url(hero_name)
    try:
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException as e:
        print(f"  D2PT fetch error for {hero_name}: {e}")
        return None


def parse_d2pt_data(html):
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script")
    data_payload = None

    for script in scripts:
        text = script.string or ""
        if "kit.start(" in text and "data:" in text:
            match = re.search(r'data:\s*(\[.*?\])\s*,\s*form:', text, re.DOTALL)
            if match:
                try:
                    raw = match.group(1)
                    raw = re.sub(r'([{,])\s*([a-zA-Z_]\w*)\s*:', r'\1"\2":', raw)
                    raw = re.sub(r':\s*"([^"]*?)"(?=\s*[,}\]])', lambda m: ':' + json.dumps(m.group(1)), raw)
                    data_payload = json.loads(raw)
                except json.JSONDecodeError:
                    pass
            break

    if not data_payload:
        return _parse_d2pt_html_fallback(soup)

    return _extract_build_data(data_payload)


def _extract_build_data(data_payload):
    result = {
        "items": {},
        "skill_build": [],
        "talents": [],
        "starting_items": [],
        "winrate": 0,
        "matches": 0,
    }

    if not data_payload or not isinstance(data_payload, list):
        return result

    main_data = None
    for item in data_payload:
        if isinstance(item, dict) and "data" in item:
            d = item["data"]
            if isinstance(d, dict) and "buildData" in d:
                main_data = d
                break

    if not main_data:
        return result

    build_data_list = main_data.get("buildData", [])
    if not build_data_list:
        return result

    valid_builds = [b for b in build_data_list
                    if isinstance(b.get("num_matches"), (int, float)) and b.get("num_matches", 0) > 10]
    if not valid_builds:
        return result

    best_build = max(valid_builds, key=lambda b: b.get("num_matches", 0))

    total_matches = best_build.get("num_matches", 0)
    total_wins = best_build.get("num_wins", 0)
    if total_matches > 0 and 0 < total_wins <= total_matches:
        result["matches"] = int(total_matches)
        result["winrate"] = total_wins / total_matches
    else:
        return result

    build_detail = best_build.get("build_data", {})

    items_mapping = main_data.get("itemsMapping", {})
    result["items"] = items_mapping

    skill_raw = build_detail.get("abilities_new", [])
    if skill_raw and isinstance(skill_raw, list) and len(skill_raw) > 0:
        skills = skill_raw[0] if isinstance(skill_raw[0], list) else skill_raw
        abilities_data = build_detail.get("abilities", [])
        ability_map = {}
        for a in abilities_data:
            if isinstance(a, dict):
                ability_map[a.get("ability_id")] = a.get("displayName", a.get("name", "?"))

        result["skill_build"] = []
        for i, ab_id in enumerate(skills):
            name = ability_map.get(ab_id, str(ab_id))
            result["skill_build"].append({"level": i + 1, "ability_id": ab_id, "name": name})

    talents_raw = build_detail.get("talents", [])
    result["talents"] = []
    for t in talents_raw:
        if isinstance(t, dict):
            lvl = t.get("lvl", 0)
            left = t.get("left", {})
            right = t.get("right", {})
            left_name = left.get("displayName", left.get("name", "?"))
            right_name = right.get("displayName", right.get("name", "?"))
            left_wr = left.get("win_rate", 0)
            right_wr = right.get("win_rate", 0)
            left_pick = left.get("pick_rate", 0)
            right_pick = right.get("pick_rate", 0)
            result["talents"].append({
                "level": lvl,
                "left": {"name": left_name, "win_rate": left_wr, "pick_rate": left_pick},
                "right": {"name": right_name, "win_rate": right_wr, "pick_rate": right_pick},
            })

    starting_raw = build_detail.get("starting_items_new", [])
    result["starting_items"] = []
    if starting_raw and isinstance(starting_raw, list):
        top_start = starting_raw[0] if isinstance(starting_raw[0], list) else starting_raw
        if isinstance(top_start, list) and len(top_start) > 0:
            item_ids = top_start[0] if isinstance(top_start[0], list) else top_start
            for iid in item_ids:
                if isinstance(iid, int):
                    item_info = items_mapping.get(str(iid), items_mapping.get(iid, {}))
                    name = item_info.get("displayName", item_info.get("name", str(iid))) if isinstance(item_info, dict) else str(iid)
                    result["starting_items"].append({"item_id": iid, "name": name})

    sixslot = build_detail.get("sixslot", [])
    result["popular_items"] = []
    for si in sixslot[:10]:
        if isinstance(si, dict):
            iid = si.get("item_id")
            item_info = items_mapping.get(str(iid), items_mapping.get(iid, {}))
            name = item_info.get("displayName", item_info.get("name", str(iid))) if isinstance(item_info, dict) else str(iid)
            result["popular_items"].append({
                "item_id": iid,
                "name": name,
                "pick_rate": si.get("pick_rate", 0),
            })

    return result


def _parse_d2pt_html_fallback(soup):
    result = {
        "items": {},
        "skill_build": [],
        "talents": [],
        "starting_items": [],
        "popular_items": [],
        "winrate": 0,
        "matches": 0,
    }

    winrate_el = soup.select_one(".red, .green, .yellow-new")
    if winrate_el:
        try:
            wr_text = winrate_el.get_text(strip=True).replace("%", "")
            result["winrate"] = float(wr_text) / 100
        except (ValueError, TypeError):
            pass

    return result


def get_hero_build(hero_name):
    print(f"  Fetching D2PT data for {hero_name}...")
    html = fetch_d2pt_page(hero_name)
    if not html:
        return None
    return parse_d2pt_data(html)


if __name__ == "__main__":
    data = get_hero_build("Anti-Mage")
    if data:
        print(f"Winrate: {data.get('winrate', 0)*100:.1f}%")
        print(f"Matches: {data.get('matches', 0)}")
        print(f"Skill build: {len(data.get('skill_build', []))} levels")
        print(f"Talents: {len(data.get('talents', []))} tiers")
        print(f"Popular items: {len(data.get('popular_items', []))}")
    else:
        print("No data retrieved")
