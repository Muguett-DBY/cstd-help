import unittest

from analysis.analyzer import _generate_suggestions, analyze_match
from analysis.evidence_contract import review_evidence_gaps
from analysis.formula_engine import build_formula_review
from api.normalization import normalize_match_participants, normalize_player_match


ACCOUNT_ID = 173776719


def _inputs(position="POSITION_1", include_vision=True):
    duration = 20 * 60
    match = {
        "match_id": 9000000001,
        "account_id": ACCOUNT_ID,
        "duration": duration,
        "start_time": 1_700_000_000,
        "radiant_win": 1,
        "is_radiant": 1,
        "player_slot": 0,
        "hero_id": 48,
        "kills": 4,
        "deaths": 0,
        "assists": 8,
        "gold_per_min": 620,
        "xp_per_min": 710,
        "hero_damage": 18000,
        "tower_damage": 4200,
        "hero_healing": 0,
        "last_hits": 190,
        "denies": 9,
        "level": 20,
        "net_worth": 15000,
        "item_0": 50,
    }
    player = {
        "account_id": ACCOUNT_ID,
        "player_slot": 0,
        "hero_id": 48,
        "kills": 4,
        "deaths": 0,
        "assists": 8,
        "gold_per_min": 620,
        "xp_per_min": 710,
        "hero_damage": 18000,
        "tower_damage": 4200,
        "hero_healing": 0,
        "last_hits": 190,
        "denies": 9,
        "level": 20,
        "net_worth": 15000,
        "item_0": 50,
        "lh_t": [0] + [index * 9 for index in range(1, 21)],
        "gold_t": [0] + [index * 620 for index in range(1, 21)],
        "xp_t": [0] + [index * 710 for index in range(1, 21)],
        "purchase_log": [{"time": 600, "key": "phase_boots"}],
        "kills_log": [{"time": 900, "key": "npc_dota_hero_axe"}],
        "benchmarks": {
            "gold_per_min": {"raw": 620, "pct": 0.72},
            "xp_per_min": {"raw": 710, "pct": 0.76},
            "last_hits_per_min": {"raw": 9.5, "pct": 0.68},
            "hero_damage_per_min": {"raw": 900, "pct": 0.61},
            "tower_damage": {"raw": 4200, "pct": 0.66},
        },
        "lane_efficiency_pct": 74,
        "teamfight_participation": 0.6,
        "life_state_dead": 0,
        "buyback_count": 0,
        "actions_per_min": 286,
        "stuns": 12.5,
        "damage_taken": {
            "npc_dota_hero_axe": 7000,
            "npc_dota_neutral_centaur_khan": 1200,
        },
        "obs_placed": 0,
        "sen_placed": 0,
        "observer_kills": 0,
        "sentry_kills": 0,
        "camps_stacked": 2,
        "rune_pickups": 5,
        "courier_kills": 0,
        "tower_kills": 2,
        "roshan_kills": 0,
        "item_uses": {"phase_boots": 24},
        "ability_uses": {"luna_lucent_beam": 16},
    }
    if include_vision:
        player.update({"obs_log": [], "sen_log": []})
    other_players = []
    for index in range(1, 10):
        slot = index if index < 5 else 128 + (index - 5)
        other_players.append({
            "account_id": 1000 + index,
            "player_slot": slot,
            "hero_id": 48 + index,
            "kills": 0,
            "deaths": 0,
            "assists": 0,
            "gold_per_min": 400,
            "xp_per_min": 450,
            "last_hits": 80,
            "denies": 2,
            "hero_damage": 5000,
            "tower_damage": 300,
            "net_worth": 8000,
        })
    opendota = {
        "match_id": match["match_id"],
        "duration": duration,
        "radiant_win": True,
        "players": [player, *other_players],
        "objectives": [],
        "teamfights": [],
    }
    stratz = {
        "players": [{
            "steamAccount": {"id": ACCOUNT_ID},
            "hero": {"id": 48},
            "isRadiant": True,
            "position": position,
            "role": "CORE" if position != "POSITION_5" else "SUPPORT",
            "lane": "SAFE_LANE",
            "abilities": [{"abilityId": 1, "time": 60, "level": 1}],
            "stats": {
                "lastHitsPerMinute": [9] * 20,
                "deniesPerMinute": [0] * 20,
                "goldPerMinute": [620] * 20,
                "experiencePerMinute": [710] * 20,
                "heroDamagePerMinute": [900] * 20,
                "towerDamagePerMinute": [210] * 20,
            },
            "playbackData": {
                "purchaseEvents": [{"time": 600, "itemId": 50}],
                "deathEvents": [],
                "killEvents": [{"time": 600 + index * 120} for index in range(4)],
                "assistEvents": [{"time": 630 + index * 60} for index in range(8)],
                "csEvents": [],
                "playerUpdatePositionEvents": [],
            },
        }],
    }
    return match, stratz, opendota


class CompleteDataContractTests(unittest.TestCase):
    def test_match_api_normalization_keeps_extended_player_and_scoreboard_fields(self):
        _match, _stratz, opendota = _inputs()

        player = normalize_player_match(opendota, ACCOUNT_ID)
        participants = normalize_match_participants(opendota, ACCOUNT_ID)
        self_row = next(item for item in participants if item["is_self"])

        self.assertEqual(player["actions_per_min"], 286)
        self.assertEqual(player["camps_stacked"], 2)
        self.assertEqual(player["rune_pickups"], 5)
        self.assertEqual(player["obs_placed"], 0)
        self.assertEqual(self_row["last_hits"], 190)
        self.assertEqual(self_row["hero_damage"], 18000)
        self.assertEqual(self_row["tower_damage"], 4200)

    def test_analyzer_preserves_xp_and_extended_real_metrics(self):
        match, stratz, opendota = _inputs()

        analysis = analyze_match(match, stratz_data=stratz, opendota_data=opendota)

        self.assertIn("experience_by_minute", analysis["timeline"])
        self.assertIn("extended_metrics", analysis)
        self.assertEqual(analysis["timeline"]["experience_by_minute"], [710] * 20)
        self.assertEqual(analysis["extended_metrics"]["combat"]["hero_damage_taken"], 7000)
        self.assertEqual(analysis["extended_metrics"]["activity"]["actions_per_min"], 286)
        self.assertEqual(analysis["extended_metrics"]["objectives"]["tower_kills"], 2)
        self.assertEqual(analysis["extended_metrics"]["usage"]["top_item_uses"][0]["count"], 24)

    def test_field_ledger_distinguishes_zero_events_from_missing_fields(self):
        match, stratz, opendota = _inputs()

        analysis = analyze_match(match, stratz_data=stratz, opendota_data=opendota)
        self.assertIn("field_ledger", analysis["data_quality"])
        ledger = {item["id"]: item for item in analysis["data_quality"]["field_ledger"]}

        self.assertEqual(ledger["objectives"]["status"], "available")
        self.assertEqual(ledger["objectives"]["coverage_pct"], 100)
        self.assertEqual(ledger["deaths"]["status"], "not_applicable")
        self.assertEqual(ledger["minute_xp"]["status"], "available")
        self.assertEqual(ledger["extended_metrics"]["status"], "available")
        self.assertEqual(analysis["data_quality"]["blocking_gaps"], [])
        self.assertEqual(review_evidence_gaps(analysis), [])

    def test_support_vision_is_required_but_core_vision_is_informational(self):
        core_match, core_stratz, core_opendota = _inputs(include_vision=False)
        support_match, support_stratz, support_opendota = _inputs(
            position="POSITION_5",
            include_vision=False,
        )

        core = analyze_match(core_match, stratz_data=core_stratz, opendota_data=core_opendota)
        support = analyze_match(support_match, stratz_data=support_stratz, opendota_data=support_opendota)
        self.assertIn("field_ledger", core["data_quality"])
        self.assertIn("field_ledger", support["data_quality"])
        core_vision = next(item for item in core["data_quality"]["field_ledger"] if item["id"] == "vision_events")
        support_vision = next(item for item in support["data_quality"]["field_ledger"] if item["id"] == "vision_events")

        self.assertFalse(core_vision["required"])
        self.assertNotIn("vision_events", core["data_quality"]["blocking_gaps"])
        self.assertTrue(support_vision["required"])
        self.assertEqual(support_vision["status"], "missing")
        self.assertIn("vision_events", support["data_quality"]["blocking_gaps"])

    def test_partial_final_minute_does_not_create_false_timeline_gap(self):
        match, stratz, opendota = _inputs()
        match["duration"] = 20 * 60 + 59
        opendota["duration"] = match["duration"]

        analysis = analyze_match(match, stratz_data=stratz, opendota_data=opendota)

        self.assertEqual(analysis["duration_seconds"], 1259)
        self.assertNotIn("minute_lh", analysis["data_quality"]["blocking_gaps"])
        self.assertNotIn("minute_gold", analysis["data_quality"]["blocking_gaps"])
        self.assertNotIn("minute_xp", analysis["data_quality"]["blocking_gaps"])

    def test_scoreboard_totals_and_timed_fight_events_have_separate_coverage(self):
        match, stratz, opendota = _inputs()
        stratz_player = stratz["players"][0]
        stratz_player["playbackData"]["assistEvents"] = [
            {"time": 630 + index * 60}
            for index in range(7)
        ]

        analysis = analyze_match(match, stratz_data=stratz, opendota_data=opendota)
        fight_ledger = next(
            item for item in analysis["data_quality"]["field_ledger"]
            if item["id"] == "fight_events"
        )

        self.assertEqual(fight_ledger["status"], "available")
        self.assertEqual(fight_ledger["aggregate_expected_count"], 12)
        self.assertEqual(fight_ledger["timed_event_count"], 11)
        self.assertEqual(fight_ledger["timing_coverage_pct"], 92)
        self.assertFalse(analysis["events"]["fight_timing_complete"])
        self.assertIn("计数口径不一致", analysis["events"]["fight_timing_coverage_label"])
        self.assertNotIn("fight_events", analysis["data_quality"]["blocking_gaps"])
        self.assertTrue(any(
            "事件时间覆盖" in item
            for item in analysis["data_quality"]["limitations"]
        ))

    def test_legacy_suggestion_field_reuses_formula_selected_actions(self):
        match, stratz, opendota = _inputs()

        analysis = analyze_match(match, stratz_data=stratz, opendota_data=opendota)
        analysis["review_findings"].extend([
            {
                "priority": "high",
                "category": "death_position_pattern",
                "action": "不应发布坐标推断建议",
            },
            {
                "priority": "medium",
                "category": "map_impact",
                "action": "参战训练项",
            },
            {
                "priority": "low",
                "category": "closing",
                "action": "同维度次要训练项",
            },
        ])
        _generate_suggestions(analysis)
        review = build_formula_review(analysis)

        self.assertEqual(
            [item["category"] for item in analysis["suggestions"]],
            [item["category"] for item in review["next_actions"]],
        )
        self.assertNotIn(
            "death_position_pattern",
            [item["category"] for item in analysis["suggestions"]],
        )
        self.assertTrue(all(item.get("formula_score") is not None for item in analysis["suggestions"]))


if __name__ == "__main__":
    unittest.main()
