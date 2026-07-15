import unittest

from analysis.analyzer import (
    _build_post_item_windows,
    _death_cluster_labels,
    _find_low_efficiency_windows,
    _generate_suggestions,
    _item_window_goal_details,
    analyze_match,
)
from analysis.evidence_contract import review_evidence_gaps
from analysis.formula_engine import build_formula_review
from api.normalization import (
    normalize_match_participants,
    normalize_player_match,
    normalize_recent_match,
)


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
    def test_recent_match_normalization_rejects_missing_required_facts(self):
        raw = {
            "match_id": 9000000001,
            "hero_id": 48,
            "player_slot": 0,
            "duration": 1200,
            "start_time": 1_700_000_000,
            "radiant_win": True,
            "kills": 4,
            "deaths": 0,
            "assists": 8,
            "lobby_type": 7,
        }

        for field in (
            "match_id", "hero_id", "player_slot", "duration", "start_time",
            "radiant_win", "kills", "deaths", "assists",
        ):
            incomplete = dict(raw)
            incomplete.pop(field)
            with self.subTest(field=field):
                self.assertIsNone(normalize_recent_match(incomplete, ACCOUNT_ID))

        for invalid_slot in (True, -1, 5, 99, 133):
            invalid = dict(raw, player_slot=invalid_slot)
            with self.subTest(player_slot=invalid_slot):
                self.assertIsNone(normalize_recent_match(invalid, ACCOUNT_ID))

    def test_participant_normalization_preserves_unknown_kda(self):
        participants = normalize_match_participants({
            "players": [{
                "account_id": ACCOUNT_ID,
                "hero_id": 48,
                "player_slot": 0,
            }],
        }, ACCOUNT_ID)

        self.assertEqual(participants[0]["kda"], {
            "kills": None,
            "deaths": None,
            "assists": None,
        })

    def test_participant_normalization_does_not_guess_side_from_invalid_slot(self):
        participants = normalize_match_participants({
            "players": [{
                "account_id": ACCOUNT_ID,
                "hero_id": 48,
                "player_slot": 99,
            }],
        }, ACCOUNT_ID)

        self.assertIsNone(participants[0]["side"])

    def test_opendota_lane_and_team_resource_rank_formula_unblocks_role(self):
        match, _stratz, opendota = _inputs()
        opendota["players"][0]["lane_role"] = 1

        analysis = analyze_match(match, opendota_data=opendota)
        role_ledger = next(
            item for item in analysis["data_quality"]["field_ledger"]
            if item["id"] == "role_position"
        )

        self.assertEqual(analysis["role_profile"]["id"], "pos1")
        self.assertEqual(analysis["role_profile"]["classification"], "formula")
        self.assertEqual(analysis["role_profile"]["farm_rank"], 1)
        self.assertIn("队内补刀第1", analysis["role_profile"]["evidence"])
        self.assertEqual(role_ledger["status"], "available")
        self.assertFalse(role_ledger["exact_position_available"])
        self.assertIn("公式", role_ledger["source"])
        self.assertNotIn("role_position", review_evidence_gaps(analysis))

    def test_safe_lane_high_farm_rate_remains_core_when_teammates_outfarm_it(self):
        match, _stratz, opendota = _inputs()
        match.update({"duration": 3300, "last_hits": 373, "gold_per_min": 641})
        player = opendota["players"][0]
        player.update({
            "lane_role": 1,
            "last_hits": 373,
            "gold_per_min": 641,
            "net_worth": 31806,
        })
        opendota["duration"] = 3300
        opendota["players"][2].update({
            "last_hits": 508,
            "gold_per_min": 855,
            "net_worth": 37498,
        })
        opendota["players"][3].update({
            "last_hits": 528,
            "gold_per_min": 702,
            "net_worth": 32600,
        })

        analysis = analyze_match(match, opendota_data=opendota)

        self.assertEqual(analysis["role_profile"]["id"], "pos1")
        self.assertEqual(analysis["role_profile"]["farm_rank"], 3)
        self.assertIn("6.8 LH/min", analysis["role_profile"]["evidence"])
        self.assertNotIn("role_position", review_evidence_gaps(analysis))

    def test_valve_replay_fills_minute_damage_and_every_death_position(self):
        match, stratz, opendota = _inputs()
        match["deaths"] = 1
        opendota["players"][0]["deaths"] = 1
        stratz_player = stratz["players"][0]
        stratz_player["stats"]["heroDamagePerMinute"] = []
        stratz_player["stats"]["towerDamagePerMinute"] = []
        replay = {
            "source": "valve_replay_gem",
            "player": {"lane_role": 1, "ability_upgrades": [1, 2]},
            "timeline": {
                "last_hits_per_minute": [9] * 20,
                "denies_per_minute": [0] * 20,
                "gold_per_minute": [620] * 20,
                "experience_per_minute": [710] * 20,
                "hero_damage_per_minute": [900] * 20,
                "tower_damage_per_minute": [210] * 20,
            },
            "deaths": [{
                "time": 900,
                "position": {"x": 101.0, "y": 111.0},
                "world_position": {"x": 12928.0, "y": 14208.0},
                "sample_delta_seconds": 0.17,
                "position_source": "valve_replay_position_sample",
                "source": "valve_replay_gem",
                "nearby_context": {
                    "source": "valve_replay_all_player_positions",
                    "radius_units": 1600,
                    "sample_resolution_seconds": 2,
                    "sampled_other_players": 9,
                    "allies_within_radius_count": 1,
                    "enemies_within_radius_count": 2,
                    "allies_within_radius": [],
                    "enemies_within_radius": [],
                    "nearest_ally": {"player_id": 1, "hero_id": 1, "distance_units": 900},
                    "nearest_enemy": {"player_id": 5, "hero_id": 2, "distance_units": 500},
                },
            }],
            "kills": [
                {"time": 600 + index * 120, "target": "npc_dota_hero_axe"}
                for index in range(4)
            ],
            "assists": [
                {"time": 630 + index * 60, "target": "npc_dota_hero_axe"}
                for index in range(8)
            ],
            "purchases": [],
            "vision_events": [],
            "objectives": [],
            "extended": {},
            "validation": {
                "status": "matched",
                "checks": [{
                    "metric": "deaths",
                    "api_value": 1,
                    "replay_value": 1,
                    "delta": 0,
                    "status": "matched",
                }],
            },
        }

        analysis = analyze_match(
            match,
            stratz_data=stratz,
            opendota_data=opendota,
            replay_data=replay,
        )

        self.assertEqual(analysis["timeline"]["hero_damage_by_minute"], [900] * 20)
        self.assertEqual(analysis["timeline"]["tower_damage_by_minute"], [210] * 20)
        self.assertIn("valve_replay_gem", analysis["timeline"]["source"])
        self.assertEqual(analysis["events"]["death_source"], "valve_replay_gem")
        self.assertEqual(analysis["events"]["death_position_count"], 1)
        self.assertEqual(
            analysis["events"]["deaths"][0]["position_source"],
            "valve_replay_position_sample",
        )
        self.assertEqual(analysis["events"]["assist_timing_count"], 8)
        self.assertTrue(analysis["events"]["fight_timing_complete"])
        self.assertIn("valve_replay_gem", analysis["events"]["fight_source"])
        self.assertNotIn("minute_damage", analysis["data_quality"]["blocking_gaps"])
        self.assertNotIn("death_positions", analysis["data_quality"]["blocking_gaps"])
        self.assertNotIn("death_nearby_players", analysis["data_quality"]["blocking_gaps"])
        self.assertEqual(
            analysis["data_quality"]["source_reconciliation"]["status"],
            "matched",
        )
        reconciled = analysis["data_quality"]["source_reconciliation"]["checks"][0]
        self.assertEqual(reconciled["left_label"], "OpenDota")
        self.assertEqual(reconciled["right_label"], "Valve回放")

        stratz_player["stats"]["deathEvents"] = [{
            "time": 900,
            "attacker": 2,
            "timeDead": 52,
            "positionX": 101,
            "positionY": 111,
        }]
        stratz_primary = analyze_match(
            match,
            stratz_data=stratz,
            opendota_data=opendota,
            replay_data=replay,
        )
        self.assertEqual(stratz_primary["events"]["death_source"], "stratz_stats")
        self.assertEqual(stratz_primary["events"]["death_nearby_context_count"], 1)
        self.assertEqual(
            stratz_primary["events"]["deaths"][0]["evidence_sources"],
            ["stratz_stats", "valve_replay_gem"],
        )
        self.assertNotIn(
            "death_nearby_players",
            stratz_primary["data_quality"]["blocking_gaps"],
        )

        replay_without_nearby = dict(replay)
        replay_without_nearby["deaths"] = [
            {key: value for key, value in replay["deaths"][0].items() if key != "nearby_context"}
        ]
        incomplete = analyze_match(
            match,
            stratz_data=stratz,
            opendota_data=opendota,
            replay_data=replay_without_nearby,
        )
        self.assertIn("death_nearby_players", incomplete["data_quality"]["blocking_gaps"])

        partial_context = dict(replay["deaths"][0]["nearby_context"])
        partial_context["sampled_other_players"] = 8
        replay_with_partial_nearby = dict(replay)
        replay_with_partial_nearby["deaths"] = [{
            **replay["deaths"][0],
            "nearby_context": partial_context,
        }]
        partial = analyze_match(
            match,
            stratz_data=stratz,
            opendota_data=opendota,
            replay_data=replay_with_partial_nearby,
        )
        self.assertEqual(partial["events"]["death_nearby_context_count"], 0)
        self.assertIn("death_nearby_players", partial["data_quality"]["blocking_gaps"])

    def test_partial_opening_minutes_do_not_create_false_lane_window(self):
        windows = _find_low_efficiency_windows(
            [1, 3, *([8] * 8)],
            {"id": "pos1", "lane_farm_sensitive": True},
        )

        self.assertEqual(windows, [])

    def test_valve_replay_fills_skills_performance_and_extended_fields(self):
        match, stratz, opendota = _inputs()
        stratz["players"][0]["abilities"] = []
        stratz["players"][0].pop("lane", None)
        stratz["players"][0].pop("position", None)
        opendota_player = opendota["players"][0]
        for field in (
            "ability_upgrades_arr", "lane_efficiency_pct", "teamfight_participation",
            "life_state_dead", "buyback_count", "stuns", "damage_taken",
            "obs_placed", "sen_placed", "observer_kills", "sentry_kills",
            "camps_stacked", "rune_pickups", "courier_kills", "tower_kills",
            "roshan_kills", "gold_spent", "total_gold", "item_uses", "ability_uses",
        ):
            opendota_player.pop(field, None)
        replay = {
            "source": "valve_replay_gem",
            "player": {"lane_role": 1, "ability_upgrades": [5059, 5058]},
            "performance": {
                "lane_efficiency_pct": 71,
                "teamfight_participation": 0.64,
                "life_state_dead": 43,
                "buyback_count": 1,
            },
            "extended": {
                "stuns": 4.5,
                "damage_taken": {"npc_dota_hero_axe": 900},
                "obs_placed": 2,
                "sen_placed": 1,
                "observer_kills": 1,
                "sentry_kills": 0,
                "camps_stacked": 2,
                "rune_pickups": 4,
                "courier_kills": 0,
                "tower_kills": 1,
                "roshan_kills": 0,
                "buyback_count": 1,
                "gold_spent": 9000,
                "total_gold": 9500,
                "item_uses": {"item_power_treads": 12},
                "ability_uses": {"morphling_waveform": 7},
            },
        }

        analysis = analyze_match(
            match,
            stratz_data=stratz,
            opendota_data=opendota,
            replay_data=replay,
        )

        self.assertEqual(
            [item["abilityId"] for item in analysis["skills"]["upgrades"]],
            [5059, 5058],
        )
        self.assertTrue(all(
            item["source"] == "valve_replay_gem"
            for item in analysis["skills"]["upgrades"]
        ))
        self.assertEqual(analysis["performance_context"]["lane_efficiency_pct"], 71)
        self.assertEqual(analysis["performance_context"]["dead_time_seconds"], 43)
        self.assertEqual(analysis["context"]["lane"], "优势路（Valve回放）")
        self.assertEqual(analysis["role_profile"]["label"], "1号位（公式识别）")
        self.assertEqual(analysis["role_profile"]["classification"], "formula")
        self.assertEqual(analysis["extended_metrics"]["combat"]["stuns_seconds"], 4.5)
        self.assertEqual(analysis["extended_metrics"]["activity"]["camps_stacked"], 2)
        self.assertIn("Valve回放", analysis["extended_metrics"]["source"])

    def test_post_item_windows_are_classified_from_real_conversion_metrics(self):
        events = {
            "key_purchases": [
                {"time": 600, "minute": 10.0, "item_name": "Black King Bar"},
                {"time": 1200, "minute": 20.0, "item_name": "Battle Fury"},
            ],
            "kills": [],
            "assists": [],
            "fight_timing_complete": True,
        }
        timeline = {
            "last_hits_by_minute": [5] * 30,
            "gold_by_minute": [400] * 30,
            "tower_damage_by_minute": [0] * 30,
        }

        windows = _build_post_item_windows(events, timeline)

        self.assertTrue(windows[0]["low_conversion"])
        self.assertEqual(windows[0]["classification"], "low_conversion")
        self.assertTrue(windows[1]["low_farm"])
        self.assertEqual(windows[1]["classification"], "low_farm")

    def test_incomplete_fight_timeline_never_becomes_false_zero_conversion(self):
        windows = _build_post_item_windows(
            {
                "key_purchases": [{
                    "time": 600,
                    "minute": 10.0,
                    "item_name": "Black King Bar",
                }],
                "kills": [],
                "assists": [],
                "fight_timing_complete": False,
            },
            {
                "last_hits_by_minute": [8] * 20,
                "gold_by_minute": [600] * 20,
                "tower_damage_by_minute": [0] * 20,
            },
        )

        self.assertEqual(windows[0]["classification"], "insufficient_data")
        self.assertFalse(windows[0]["evaluable"])
        self.assertFalse(windows[0]["low_conversion"])
        self.assertEqual(_item_window_goal_details(windows)["low_conversion"], [])

    def test_context_items_are_not_forced_into_a_two_minute_fight_window(self):
        windows = _build_post_item_windows(
            {
                "key_purchases": [
                    {"time": 600, "minute": 10.0, "item_name": "Vladmir's Offering"},
                    {"time": 900, "minute": 15.0, "item_name": "Dragon Lance"},
                    {"time": 1200, "minute": 20.0, "item_name": "Black King Bar"},
                ],
                "kills": [],
                "assists": [],
                "fight_timing_complete": True,
            },
            {
                "last_hits_by_minute": [8] * 30,
                "gold_by_minute": [650] * 30,
                "tower_damage_by_minute": [0] * 30,
            },
        )

        self.assertEqual(windows[0]["classification"], "context_only")
        self.assertEqual(windows[1]["classification"], "context_only")
        self.assertFalse(windows[0]["evaluable"])
        self.assertFalse(windows[1]["evaluable"])
        self.assertEqual(windows[2]["classification"], "low_conversion")
        self.assertEqual(
            _item_window_goal_details(windows)["low_conversion"],
            ["Black King Bar后2分钟参战0次/推塔0"],
        )

    def test_death_clusters_do_not_chain_across_an_entire_match(self):
        deaths = [
            {"minute": minute}
            for minute in (3.2, 6.8, 8.4, 12.0, 16.4, 19.5, 21.6, 26.1, 30.2)
        ]

        labels = _death_cluster_labels(deaths)

        self.assertNotIn("3.2-30.2分钟", labels)
        self.assertTrue(all(
            float(label.split("-")[1].removesuffix("分钟")) - float(label.split("-")[0]) <= 10
            for label in labels
        ))

    def test_stratz_rich_stats_fill_events_costs_objectives_and_extended_metrics(self):
        match, stratz, opendota = _inputs(include_vision=False)
        opendota["objectives"] = None
        player = opendota["players"][0]
        for field in (
            "actions_per_min", "damage_taken", "obs_placed", "sen_placed",
            "observer_kills", "sentry_kills", "camps_stacked", "rune_pickups",
            "courier_kills", "tower_kills", "item_uses", "ability_uses",
            "life_state_dead", "teamfight_participation",
        ):
            player.pop(field, None)
        player["deaths"] = 1
        match["deaths"] = 1
        stratz.update({
            "parsedDateTime": 1_700_000_100,
            "towerDeaths": [{"time": 800, "npcId": 18, "isRadiant": True, "attacker": 67}],
            "playbackData": {
                "towerDeathEvents": [{"time": 800, "radiant": 4, "dire": 0}],
                "roshanEvents": [],
                "wardEvents": [],
            },
        })
        stratz["players"].extend([
            {"isRadiant": True, "kills": 4}
            for _index in range(4)
        ])
        stratz_player = stratz["players"][0]
        stratz_player.update({"kills": 4, "deaths": 1, "assists": 8})
        stratz_player["playbackData"]["deathEvents"] = []
        stratz_player["stats"].update({
            "deathEvents": [{
                "time": 900,
                "timeDead": 45,
                "goldLost": 280,
                "goldFed": 410,
                "xpFed": 520,
                "positionX": 120,
                "positionY": 140,
                "isDieBack": False,
                "isBurst": True,
                "isEngagedOnDeath": True,
            }],
            "killEvents": [{"time": 600}],
            "assistEvents": [{"time": 720}],
            "itemPurchases": [{"time": 600, "itemId": 50}],
            "wards": [{"time": 500, "type": 0, "positionX": 100, "positionY": 110}],
            "wardDestruction": [{"time": 700, "isWard": True, "gold": 100}],
            "actionsPerMinute": [300, 360],
            "campStack": [0, 1, 1],
            "runes": [{"time": 120, "rune": "BOUNTY", "action": "PICKUP"}],
            "courierKills": [{"time": 800, "positionX": 130, "positionY": 130}],
            "heroDamageReceivedPerMinute": [500, 700],
            "itemUsed": [{"itemId": 50, "count": 12}],
            "abilityCastReport": [{"abilityId": 1, "count": 9}],
            "towerDamageReport": [{"npcId": 27, "damage": 900}],
        })

        analysis = analyze_match(match, stratz_data=stratz, opendota_data=opendota)

        self.assertEqual(analysis["events"]["death_source"], "stratz_stats")
        self.assertEqual(analysis["events"]["deaths"][0]["time_dead"], 45)
        self.assertEqual(analysis["events"]["deaths"][0]["gold_lost"], 280)
        self.assertEqual(analysis["events"]["death_cost_summary"]["total_dead_seconds"], 45)
        self.assertEqual(analysis["events"]["death_cost_summary"]["total_gold_lost"], 280)
        self.assertEqual(analysis["events"]["objectives"][0]["outcome"], "lost")
        self.assertEqual(analysis["events"]["objective_source"], "stratz_tower_deaths")
        self.assertEqual(analysis["events"]["vision_source"], "stratz_stats")
        self.assertEqual(analysis["extended_metrics"]["activity"]["actions_per_min"], 330)
        self.assertEqual(analysis["extended_metrics"]["activity"]["camps_stacked"], 1)
        self.assertEqual(analysis["extended_metrics"]["combat"]["hero_damage_taken"], 1200)
        self.assertEqual(analysis["performance_context"]["dead_time_seconds"], 45)
        self.assertEqual(analysis["performance_context"]["teamfight_participation_pct"], 60)
        death_finding = next(
            item for item in analysis["review_findings"]
            if item["category"] == "death_review"
        )
        self.assertIn("死亡事件成本", death_finding["evidence"])
        self.assertIn("丢失280金", death_finding["evidence"])
        self.assertIn("给出410金/520经验", death_finding["evidence"])

    def test_opendota_lane_role_fills_factual_role_when_stratz_position_is_missing(self):
        match, stratz, opendota = _inputs()
        stratz_player = stratz["players"][0]
        stratz_player["position"] = None
        stratz_player["lane"] = "UNKNOWN"
        stratz_player["role"] = "CORE"
        opendota_player = opendota["players"][0]
        opendota_player["lane_role"] = 1
        opendota_player["lane"] = 3

        analysis = analyze_match(match, stratz_data=stratz, opendota_data=opendota)
        role_ledger = next(
            item for item in analysis["data_quality"]["field_ledger"]
            if item["id"] == "role_position"
        )

        self.assertEqual(analysis["role_profile"]["id"], "pos1")
        self.assertEqual(analysis["role_profile"]["label"], "1号位（公式识别）")
        self.assertEqual(analysis["role_profile"]["classification"], "formula")
        self.assertEqual(role_ledger["status"], "available")
        self.assertIn("OpenDota", role_ledger["source"])

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

        self.assertEqual(fight_ledger["status"], "partial")
        self.assertEqual(fight_ledger["aggregate_expected_count"], 12)
        self.assertEqual(fight_ledger["timed_event_count"], 11)
        self.assertEqual(fight_ledger["timing_coverage_pct"], 92)
        self.assertFalse(analysis["events"]["fight_timing_complete"])
        self.assertIn("计数口径不一致", analysis["events"]["fight_timing_coverage_label"])
        self.assertIn("fight_events", analysis["data_quality"]["blocking_gaps"])
        self.assertIn("fight_events", review_evidence_gaps(analysis))
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
