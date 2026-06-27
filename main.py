import sys
import os
import time
import argparse
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ACCOUNT_ID
from db.schema import (
    init_db,
    save_match,
    save_player_match,
    save_stratz_detail,
    save_opendota_detail,
    get_recent_matches_from_db,
    get_stratz_detail,
    get_opendota_detail,
    is_match_analyzed,
    mark_match_analyzed,
)
from api.opendota import OpenDotaClient
from api.stratz import StratzClient
from analysis.analyzer import analyze_match, generate_match_summary
from analysis.ai_analyst import analyze_with_ai
from analysis.d2pt import get_hero_build
from report.generator import generate_report


def fetch_and_store_recent(limit=5):
    print(f"\n=== Fetching {limit} recent matches from OpenDota ===")
    od_client = OpenDotaClient()
    raw_matches = od_client.get_recent_matches(ACCOUNT_ID, limit=limit)

    if not raw_matches:
        print("No matches found from OpenDota API.")
        return []

    print(f"Found {len(raw_matches)} matches from OpenDota.")

    match_ids = []
    for i, raw in enumerate(raw_matches):
        match_id = raw.get("match_id")
        if not match_id:
            continue

        print(f"\n[{i+1}/{len(raw_matches)}] Processing match {match_id}...")

        full_match = od_client.get_match(match_id)
        if not full_match:
            print(f"  Could not fetch full match data for {match_id}")
            continue
        save_opendota_detail(match_id, full_match)

        parsed = od_client.parse_match_for_player(full_match, ACCOUNT_ID)
        if not parsed:
            print(f"  Player not found in match {match_id}")
            continue

        save_match(parsed)
        save_player_match(parsed)
        match_ids.append(match_id)
        print(f"  Saved: {parsed.get('hero_name', parsed.get('hero_id'))} | "
              f"{'W' if parsed.get('radiant_win') == parsed.get('is_radiant') else 'L'} | "
              f"KDA: {parsed.get('kills')}/{parsed.get('deaths')}/{parsed.get('assists')}")

        time.sleep(1.5)

    return match_ids


def fetch_stratz_details(match_ids, force=False):
    print(f"\n=== Fetching Stratz details for {len(match_ids)} matches ===")
    stratz_client = StratzClient()

    for match_id in match_ids:
        if get_stratz_detail(match_id) and not force:
            print(f"  Match {match_id} already has Stratz detail, skipping.")
            continue

        print(f"  Fetching Stratz data for {match_id}...")
        detail = stratz_client.get_match_detail(match_id)
        if detail:
            save_stratz_detail(match_id, json.dumps(detail, ensure_ascii=False, default=str))
            print(f"    Got Stratz data: {len(detail.get('players', []))} players")
        else:
            if get_stratz_detail(match_id):
                print(f"    Live Stratz fetch failed; using cached Stratz detail for analysis.")
            else:
                print(f"    No Stratz data returned for {match_id}")
        time.sleep(2)


def ensure_opendota_detail(match_id, force=False, parse_wait=90):
    od_client = OpenDotaClient()
    cached = get_opendota_detail(match_id)
    if cached and od_client.has_parsed_player_logs(cached, account_id=ACCOUNT_ID):
        return cached
    if cached and not force and parse_wait <= 0:
        return cached

    print(f"    Fetching OpenDota detail and parsed logs for {match_id}...")
    detail, job_id = od_client.get_match_with_parse(
        match_id,
        account_id=ACCOUNT_ID,
        wait_seconds=parse_wait,
    )
    if detail:
        if job_id:
            detail.setdefault("_fetch_warnings", []).append(
                f"OpenDota parse job {job_id} requested; parsed logs "
                f"{'available' if od_client.has_parsed_player_logs(detail, account_id=ACCOUNT_ID) else 'not ready'}"
            )
        save_opendota_detail(match_id, detail, parse_job_id=job_id)
        return detail
    return cached


def analyze_matches(match_ids, force=False, parse_wait=90):
    print(f"\n=== Analyzing {len(match_ids)} matches ===")
    analyses = []

    for match_id in match_ids:
        if is_match_analyzed(match_id) and not force:
            print(f"  Match {match_id} already analyzed, using cached data.")
            continue

        print(f"\n  Analyzing match {match_id}...")
        recent = get_recent_matches_from_db(ACCOUNT_ID, limit=50)
        match_data = None
        for r in recent:
            if r.get("match_id") == match_id:
                match_data = r
                break

        if not match_data:
            print(f"    Match {match_id} not found in database")
            continue

        d2pt_data = None
        try:
            hero_name_str = _get_hero_name_from_id(match_data.get("hero_id"))
            if hero_name_str:
                d2pt_data = get_hero_build(hero_name_str)
        except Exception as e:
            print(f"    D2PT fetch error: {e}")

        stratz_data = get_stratz_detail(match_id)
        opendota_data = ensure_opendota_detail(match_id, force=force, parse_wait=parse_wait)
        analysis = analyze_match(match_data, stratz_data=stratz_data, opendota_data=opendota_data, d2pt_data=d2pt_data)
        analysis["match_id"] = match_id
        analyses.append(analysis)

    return analyses


def _get_hero_name_from_id(hero_id):
    hero_names = {
        1: "Anti-Mage", 2: "Axe", 3: "Bane", 4: "Bloodseeker",
        5: "Crystal Maiden", 6: "Drow Ranger", 7: "Earthshaker",
        8: "Juggernaut", 9: "Kunkka", 11: "Lina", 12: "Lion",
        14: "Mirana", 15: "Morphling", 16: "Shadow Fiend",
        17: "Phantom Lancer", 18: "Puck", 19: "Pudge", 20: "Razor",
        21: "Sand King", 22: "Slardar", 23: "Sniper", 24: "Spectre",
        25: "Storm Spirit", 26: "Sven", 27: "Tidehunter",
        28: "Vengeful Spirit", 29: "Windranger", 30: "Zeus",
        31: "Jakiro", 32: "Chaos Knight", 33: "Nature's Prophet",
        34: "Lich", 35: "Shadow Shaman", 36: "Medusa", 37: "Troll Warlord",
        38: "Ursa", 39: "Io", 40: "Visage", 41: "Wraith King",
        42: "Death Prophet", 43: "Phantom Assassin", 44: "Pugna",
        45: "Templar Assassin", 46: "Viper", 47: "Luna",
        48: "Dragon Knight", 49: "Dazzle", 50: "Ancient Apparition",
        51: "Bounty Hunter", 52: "Timbersaw", 53: "Brewmaster",
        54: "Earth Spirit", 55: "Terrorblade", 56: "Phoenix",
        57: "Skywrath Mage", 58: "Abaddon", 59: "Elder Titan",
        60: "Legion Commander", 61: "Techies", 62: "Ember Spirit",
        66: "Underlord", 67: "Timbersaw", 69: "Grimstroke",
        71: "Huskar", 72: "Night Stalker", 73: "Broodmother",
        74: "Weaver", 75: "Batrider", 76: "Chen", 77: "Riki",
        78: "Enchantress", 79: "Leshrac", 82: "Lycan",
        83: "Naga Siren", 86: "Rubick", 87: "Disruptor",
        88: "Keeper of the Light", 89: "Witch Doctor", 90: "Viper",
        92: "Centaur Warrunner", 93: "Magnus", 95: "Shadow Demon",
        96: "Bristleback", 97: "Tusk", 99: "Bane",
        102: "Slark", 104: "Alchemist", 105: "Invoker",
        106: "Faceless Void", 110: "Tiny", 111: "Beastmaster",
        112: "Queen of Pain", 113: "Venomancer", 119: "Doom",
        128: "Snapfire", 131: "Mars", 135: "Lone Druid",
        138: "Underlord", 139: "Monkey King", 141: "Pangolier",
        142: "Dark Willow", 145: "Void Spirit", 146: "Snapfire",
        147: "Mars", 149: "Dawnbreaker", 150: "Marci",
        151: "Primal Beast", 152: "Muerta", 154: "Ringmaster",
        156: "Kez",
    }
    return hero_names.get(hero_id)


def generate_reports(analyses):
    print(f"\n=== Generating reports for {len(analyses)} matches ===")
    reports = []

    for analysis in analyses:
        match_id = analysis.get("match_id")
        hero_name = analysis.get("hero_name")
        is_win = analysis.get("is_win")

        print(f"\n  Generating report for match {match_id} ({hero_name})...")

        print(f"  Generating evidence-based coach analysis...")
        ai_analysis = analyze_with_ai(analysis, hero_name, is_win)

        filepath = generate_report(analysis, ai_analysis)
        reports.append(filepath)

        mark_match_analyzed(match_id)

    return reports


def main():
    parser = argparse.ArgumentParser(description="DOTA2 Match Review System")
    parser.add_argument("--recent", type=int, default=3, help="Analyze N most recent matches")
    parser.add_argument("--match", type=str, help="Analyze a specific match ID")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetching from API")
    parser.add_argument("--force", "--reanalyze", action="store_true", help="Regenerate reports even if matches were already analyzed")
    parser.add_argument("--parse-wait", type=int, default=90, help="Seconds to wait for OpenDota parsed logs")
    args = parser.parse_args()

    print("=" * 60)
    print("  DOTA2 复盘分析系统 v1.0")
    print("  玩家ID:", ACCOUNT_ID)
    print("=" * 60)

    init_db()

    if args.match:
        match_ids = [int(args.match)]
    elif not args.skip_fetch:
        match_ids = fetch_and_store_recent(limit=args.recent)
    else:
        recent = get_recent_matches_from_db(ACCOUNT_ID, limit=args.recent)
        match_ids = [r["match_id"] for r in recent]

    if not match_ids:
        print("\nNo matches to analyze.")
        return

    fetch_stratz_details(match_ids, force=args.force)

    analyses = analyze_matches(match_ids, force=args.force, parse_wait=args.parse_wait)

    if not analyses:
        print("\nNo analyses generated. If these matches were already analyzed, rerun with --force.")
        return

    reports = generate_reports(analyses)

    print("\n" + "=" * 60)
    print("  分析完成！")
    print(f"  生成了 {len(reports)} 份报告:")
    for r in reports:
        print(f"    {r}")
    print("=" * 60)


if __name__ == "__main__":
    main()
