import bz2
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import requests

from api.replay import (
    ReplayEvidenceError,
    ValveReplayClient,
    _death_nearby_context,
    _diff_cumulative,
    _parse_with_raw_assists,
    _player_life_state_intervals,
    _replay_player_id_from_match_detail,
    _scoreboard_assist_events,
    build_replay_evidence,
    normalize_replay_url,
)


ACCOUNT_ID = 173776719
MATCH_ID = 8894750704


def _entry(log_type, **values):
    defaults = {
        "tick": 0,
        "game_time_s": None,
        "attacker_name": "",
        "damage_source_name": "",
        "target_name": "",
        "target_is_hero": False,
        "target_is_illusion": False,
        "will_reincarnate": False,
        "assist_players": [],
        "value": 0,
        "value_name": "",
    }
    defaults.update(values)
    return SimpleNamespace(log_type=log_type, **defaults)


class ReplayEvidenceTests(unittest.TestCase):
    def test_diff_cumulative_rejects_incomplete_or_decreasing_samples(self):
        self.assertEqual(_diff_cumulative([0, 8, None, 17]), [])
        self.assertEqual(_diff_cumulative([0, 8, 7, 17]), [])

    def test_build_replay_evidence_rejects_missing_match_duration(self):
        player = SimpleNamespace(
            account_id=ACCOUNT_ID,
            hero_name="npc_dota_hero_morphling",
            player_id=0,
            kills=0,
            deaths=0,
            assists=0,
            buyback_count=0,
        )
        parsed_match = SimpleNamespace(
            match_id=MATCH_ID,
            duration=None,
            players=[player],
            combat_log=[],
            game_start_tick=0,
        )

        with self.assertRaisesRegex(ReplayEvidenceError, "REPLAY_DURATION_UNAVAILABLE"):
            build_replay_evidence(
                parsed_match,
                match_id=MATCH_ID,
                account_id=ACCOUNT_ID,
                match_detail={},
            )

    def test_build_replay_evidence_preserves_missing_optional_payloads(self):
        player = SimpleNamespace(
            account_id=ACCOUNT_ID,
            hero_name="npc_dota_hero_morphling",
            player_id=0,
            kills=0,
            deaths=0,
            assists=0,
            buyback_count=0,
        )
        parsed_match = SimpleNamespace(
            match_id=MATCH_ID,
            duration=120,
            players=[player],
            combat_log=[],
            game_start_tick=0,
        )

        evidence = build_replay_evidence(
            parsed_match,
            match_id=MATCH_ID,
            account_id=ACCOUNT_ID,
            match_detail={"duration": 120},
        )

        self.assertIsNone(evidence["purchases"])
        self.assertIsNone(evidence["vision_events"])
        self.assertIsNone(evidence["objectives"])
        self.assertIsNone(evidence["extended"]["damage_taken"])
        self.assertIsNone(evidence["extended"]["item_uses"])
        self.assertIsNone(evidence["extended"]["ability_uses"])

    def test_missing_tower_damage_value_invalidates_replay_tower_series(self):
        player = SimpleNamespace(
            account_id=ACCOUNT_ID,
            hero_name="npc_dota_hero_morphling",
            player_id=0,
            kills=0,
            deaths=0,
            assists=0,
            buyback_count=0,
        )
        parsed_match = SimpleNamespace(
            match_id=MATCH_ID,
            duration=120,
            players=[player],
            combat_log=[_entry(
                "DAMAGE",
                game_time_s=45,
                damage_source_name="npc_dota_hero_morphling",
                target_name="npc_dota_badguys_tower1_mid",
                value=None,
            )],
            game_start_tick=0,
            objectives=[],
        )

        evidence = build_replay_evidence(
            parsed_match,
            match_id=MATCH_ID,
            account_id=ACCOUNT_ID,
            match_detail={"duration": 120},
        )

        self.assertEqual(evidence["timeline"]["tower_damage_per_minute"], [])

    def test_combat_log_recovers_buyback_when_aggregate_count_is_missing(self):
        hero_name = "npc_dota_hero_morphling"
        player = SimpleNamespace(
            account_id=ACCOUNT_ID,
            hero_name=hero_name,
            player_id=0,
            kills=0,
            deaths=0,
            assists=0,
            obs_log=[],
            sen_log=[],
        )
        parsed_match = SimpleNamespace(
            match_id=MATCH_ID,
            duration=120,
            players=[player],
            combat_log=[_entry(
                "BUYBACK",
                game_time_s=80,
                target_name=hero_name,
            )],
            game_start_tick=0,
            objectives=[],
        )

        evidence = build_replay_evidence(
            parsed_match,
            match_id=MATCH_ID,
            account_id=ACCOUNT_ID,
            match_detail={"duration": 120},
        )

        self.assertEqual(evidence["buybacks"], [{
            "time": 80,
            "source": "valve_replay_gem",
        }])

    def test_death_nearby_context_counts_only_living_heroes_in_real_radius(self):
        snapshots = [
            SimpleNamespace(player_id=0, tick=300, x=1000, y=1000, life_state=0),
            SimpleNamespace(player_id=1, tick=300, x=1800, y=1000, life_state=0),
            SimpleNamespace(player_id=2, tick=300, x=1200, y=1000, life_state=2),
            SimpleNamespace(player_id=5, tick=300, x=1400, y=1000, life_state=0),
            SimpleNamespace(player_id=6, tick=300, x=2800, y=1000, life_state=0),
        ]

        context = _death_nearby_context(
            death_tick=300,
            target_player_id=0,
            target_position={"x": 1000, "y": 1000},
            snapshots=snapshots,
            hero_ids={0: 114, 1: 5, 2: 8, 5: 44, 6: 11},
        )

        self.assertEqual(context["radius_units"], 1600)
        self.assertEqual(context["allies_within_radius_count"], 1)
        self.assertEqual(context["enemies_within_radius_count"], 1)
        self.assertEqual(context["nearest_ally"]["hero_id"], 5)
        self.assertEqual(context["nearest_ally"]["distance_units"], 800)
        self.assertEqual(context["nearest_enemy"]["hero_id"], 44)
        self.assertEqual(context["nearest_enemy"]["distance_units"], 400)
        self.assertNotIn(2, [item["player_id"] for item in context["allies_within_radius"]])

    def test_death_nearby_context_never_treats_missing_life_state_as_alive(self):
        snapshots = [
            SimpleNamespace(
                player_id=player_id,
                tick=300,
                x=1000 + player_id * 100,
                y=1000,
                life_state=None if player_id == 4 else 0,
            )
            for player_id in range(1, 10)
        ]

        partial = _death_nearby_context(
            death_tick=300,
            target_player_id=0,
            target_position={"x": 1000, "y": 1000},
            snapshots=snapshots,
        )

        self.assertEqual(partial["sampled_other_players"], 8)
        self.assertFalse(partial["coverage_complete"])
        observed_ids = {
            item["player_id"]
            for group in ("allies_within_radius", "enemies_within_radius")
            for item in partial[group]
        }
        self.assertNotIn(4, observed_ids)

        snapshots[3].life_state = 0
        complete = _death_nearby_context(
            death_tick=300,
            target_player_id=0,
            target_position={"x": 1000, "y": 1000},
            snapshots=snapshots,
        )
        self.assertEqual(complete["sampled_other_players"], 9)
        self.assertTrue(complete["coverage_complete"])

    def test_scoreboard_assist_events_expand_real_cumulative_increments(self):
        events = _scoreboard_assist_events([
            SimpleNamespace(player_id=0, game_time_s=10, tick=300, assists=0),
            SimpleNamespace(player_id=0, game_time_s=11, tick=330, assists=1),
            SimpleNamespace(player_id=0, game_time_s=12, tick=360, assists=1),
            SimpleNamespace(player_id=0, game_time_s=13, tick=390, assists=3),
        ], player_id=0)

        self.assertEqual([item["time"] for item in events], [11, 13, 13])
        self.assertTrue(all(
            item["source"] == "valve_replay_player_resource"
            for item in events
        ))

    def test_replay_download_resumes_after_interrupted_chunked_transfer(self):
        replay_bytes = b"PBDEMS2\x00" + (b"verified-replay" * 1024)
        compressed = bz2.compress(replay_bytes)
        split = len(compressed) // 2

        class FakeResponse:
            def __init__(self, payload, *, status_code, headers, interrupt=False):
                self.payload = payload
                self.status_code = status_code
                self.headers = headers
                self.interrupt = interrupt

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield self.payload
                if self.interrupt:
                    raise requests.exceptions.ChunkedEncodingError("connection closed")

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.calls = []
                self.responses = [
                    FakeResponse(
                        compressed[:split],
                        status_code=200,
                        headers={"Content-Length": str(len(compressed))},
                        interrupt=True,
                    ),
                    FakeResponse(
                        compressed[split:],
                        status_code=206,
                        headers={
                            "Content-Length": str(len(compressed) - split),
                            "Content-Range": f"bytes {split}-{len(compressed) - 1}/{len(compressed)}",
                        },
                    ),
                ]

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return self.responses.pop(0)

        session = FakeSession()
        client = ValveReplayClient(session=session, parser_module=SimpleNamespace())
        with tempfile.TemporaryDirectory() as temp_dir:
            replay_path = client._download_and_decompress(
                "http://replay151.valve.net/570/8894750704_1821651240.dem.bz2",
                MATCH_ID,
                temp_dir,
            )
            self.assertEqual(Path(replay_path).read_bytes(), replay_bytes)

        self.assertEqual(
            session.calls[1][1]["headers"],
            {"Range": f"bytes={split}-"},
        )

    def test_replay_player_id_maps_radiant_and_dire_slots(self):
        self.assertEqual(
            _replay_player_id_from_match_detail(
                {"players": [{"account_id": ACCOUNT_ID, "player_slot": 3}]},
                ACCOUNT_ID,
            ),
            3,
        )
        self.assertEqual(
            _replay_player_id_from_match_detail(
                {"players": [{"account_id": ACCOUNT_ID, "player_slot": 130}]},
                ACCOUNT_ID,
            ),
            7,
        )

    def test_life_state_counts_distinct_game_seconds_when_tick_buckets_collide(self):
        intervals = _player_life_state_intervals([
            SimpleNamespace(player_id=0, game_time_s=10, tick=1000, life_state=2),
            SimpleNamespace(player_id=0, game_time_s=11, tick=1010, life_state=2),
            SimpleNamespace(player_id=0, game_time_s=12, tick=1030, life_state=0),
        ], player_id=0)

        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0]["time_dead"], 2)
        self.assertEqual(intervals[0]["start_tick"], 1000)
        self.assertEqual(intervals[0]["respawn_observed_tick"], 1030)

    def test_normalize_replay_url_preserves_valve_http_and_rejects_untrusted_hosts(self):
        normalized = normalize_replay_url(
            "http://replay151.valve.net/570/8894750704_1821651240.dem.bz2"
        )

        self.assertEqual(
            normalized,
            "http://replay151.valve.net/570/8894750704_1821651240.dem.bz2",
        )
        with self.assertRaises(ReplayEvidenceError):
            normalize_replay_url("https://example.com/8894750704.dem.bz2")

    def test_build_replay_evidence_returns_real_minute_arrays_and_death_positions(self):
        player = SimpleNamespace(
            account_id=ACCOUNT_ID,
            hero_name="npc_dota_hero_morphling",
            player_id=0,
            lane_role=1,
            kills=1,
            deaths=1,
            assists=2,
            last_hits=17,
            denies=2,
            hero_damage=250,
            tower_damage=200,
            lh_t_min=[0, 8, 17],
            dn_t_min=[0, 1, 2],
            total_earned_gold_t_min=[0, 500, 1100],
            total_earned_xp_t_min=[0, 450, 1000],
            total_hero_damage_t_min=[0, 100, 250],
            position_log=[
                (300, 12800.0, 14080.0),
                (330, 12928.0, 14208.0),
            ],
            purchase_log=[
                _entry("PURCHASE", game_time_s=65, value_name="item_power_treads"),
            ],
            kills_log=[
                _entry(
                    "DEATH",
                    game_time_s=75,
                    target_name="npc_dota_hero_axe",
                    target_is_hero=True,
                ),
            ],
            ability_upgrades_arr=[5059, 5058],
            lane_efficiency_pct=71,
            teamfight_participation=0.64,
            life_state_dead=40,
            buyback_count=1,
            buyback_log=[_entry("BUYBACK", game_time_s=80)],
            stuns_dealt=4.5,
            damage_taken={"npc_dota_hero_axe": 900},
            obs_placed=2,
            sen_placed=1,
            obs_log=[],
            sen_log=[],
            camps_stacked=2,
            rune_pickups=4,
            courier_kills=0,
            observer_kills=0,
            sentry_kills=0,
            tower_kills=1,
            roshan_kills=0,
            gold_spent=9000,
            total_gold=9500,
            hero_healing=120,
            item_uses={"item_power_treads": 12},
            ability_uses={"morphling_waveform": 7},
        )
        match = SimpleNamespace(
            match_id=MATCH_ID,
            duration=120,
            players=[player],
            combat_log=[
                _entry(
                    "DAMAGE",
                    game_time_s=70,
                    damage_source_name=player.hero_name,
                    target_name="npc_dota_badguys_tower1_mid",
                    value=200,
                ),
                _entry(
                    "DEATH",
                    tick=330,
                    game_time_s=11,
                    attacker_name="npc_dota_hero_earth_spirit",
                    target_name=player.hero_name,
                    target_is_hero=True,
                ),
                _entry(
                    "DEATH",
                    game_time_s=85,
                    attacker_name="npc_dota_hero_luna",
                    target_name="npc_dota_hero_earth_spirit",
                    target_is_hero=True,
                    assist_players=[0],
                ),
                _entry(
                    "DEATH",
                    game_time_s=75,
                    attacker_name=player.hero_name,
                    target_name="npc_dota_hero_axe",
                    target_is_hero=True,
                    assist_players=[0],
                ),
                _entry(
                    "DEATH",
                    game_time_s=90,
                    attacker_name="npc_dota_hero_luna",
                    target_name="npc_dota_lone_druid_bear1",
                    target_is_hero=True,
                    assist_players=[0],
                ),
            ],
            objectives=[],
        )
        match_detail = {
            "match_id": MATCH_ID,
            "duration": 120,
            "players": [{
                "account_id": ACCOUNT_ID,
                "player_slot": 0,
                "hero_id": 10,
                "kills": 1,
                "deaths": 1,
                "assists": 2,
                "last_hits": 17,
                "denies": 2,
                "hero_damage": 250,
                "tower_damage": 200,
                "life_state_dead": 42,
            }, {
                "account_id": 111,
                "player_slot": 1,
                "hero_id": 5,
            }, {
                "account_id": 222,
                "player_slot": 128,
                "hero_id": 44,
            }],
        }

        evidence = build_replay_evidence(
            match,
            match_id=MATCH_ID,
            account_id=ACCOUNT_ID,
            match_detail=match_detail,
            parser_version="0.5.0",
            player_state_snapshots=[
                *[
                    SimpleNamespace(
                        player_id=0,
                        game_time_s=second,
                        tick=second * 30,
                        life_state=2,
                        x=16640.0,
                        y=17920.0,
                    )
                    for second in range(11, 54)
                ],
                SimpleNamespace(
                    player_id=0,
                    game_time_s=54,
                    tick=54 * 30,
                    life_state=0,
                    x=16640.0,
                    y=17920.0,
                ),
                SimpleNamespace(
                    player_id=0,
                    game_time_s=0,
                    tick=0,
                    life_state=0,
                    assists=0,
                ),
                SimpleNamespace(
                    player_id=0,
                    game_time_s=86,
                    tick=86 * 30,
                    life_state=0,
                    assists=2,
                ),
                SimpleNamespace(
                    player_id=1,
                    game_time_s=11,
                    tick=11 * 30,
                    life_state=0,
                    x=17440.0,
                    y=17920.0,
                ),
                SimpleNamespace(
                    player_id=5,
                    game_time_s=11,
                    tick=11 * 30,
                    life_state=0,
                    x=17040.0,
                    y=17920.0,
                ),
            ],
        )

        self.assertEqual(evidence["source"], "valve_replay_gem")
        self.assertEqual(evidence["timeline"]["last_hits_per_minute"], [8, 9])
        self.assertEqual(evidence["timeline"]["denies_per_minute"], [1, 1])
        self.assertEqual(evidence["timeline"]["gold_per_minute"], [500, 600])
        self.assertEqual(evidence["timeline"]["hero_damage_per_minute"], [100, 150])
        self.assertEqual(evidence["timeline"]["tower_damage_per_minute"], [0, 200])
        self.assertEqual(len(evidence["deaths"]), 1)
        self.assertEqual(evidence["deaths"][0]["time"], 11)
        self.assertEqual(evidence["deaths"][0]["position"], {"x": 130.0, "y": 140.0})
        nearby = evidence["deaths"][0]["nearby_context"]
        self.assertEqual(nearby["allies_within_radius_count"], 1)
        self.assertEqual(nearby["enemies_within_radius_count"], 1)
        self.assertEqual(nearby["nearest_ally"]["hero_id"], 5)
        self.assertEqual(nearby["nearest_enemy"]["hero_id"], 44)
        self.assertEqual(evidence["deaths"][0]["time_dead"], 43)
        self.assertEqual(evidence["deaths"][0]["respawn_observed_at"], 54)
        self.assertEqual(
            evidence["deaths"][0]["time_dead_source"],
            "valve_replay_life_state",
        )
        self.assertEqual(evidence["purchases"][0]["item_key"], "power_treads")
        self.assertEqual(evidence["kills"], [{
            "time": 75,
            "target": "npc_dota_hero_axe",
            "source": "valve_replay_gem",
        }])
        self.assertEqual(len(evidence["assists"]), 2)
        self.assertEqual(evidence["assists"][0]["time"], 85)
        self.assertEqual(
            evidence["assists"][0]["target"],
            "npc_dota_hero_earth_spirit",
        )
        self.assertEqual(evidence["assists"][1]["time"], 86)
        self.assertEqual(
            evidence["assists"][1]["source"],
            "valve_replay_player_resource",
        )
        self.assertEqual(evidence["buybacks"], [{
            "time": 80,
            "source": "valve_replay_gem",
        }])
        self.assertEqual(evidence["performance"]["lane_efficiency_pct"], 71)
        self.assertEqual(evidence["performance"]["life_state_dead"], 43)
        self.assertEqual(evidence["extended"]["stuns"], 4.5)
        self.assertEqual(evidence["extended"]["damage_taken"]["npc_dota_hero_axe"], 900)
        self.assertEqual(evidence["extended"]["gold_spent"], 9000)
        self.assertEqual(evidence["validation"]["status"], "matched")
        self.assertEqual(
            next(
                item for item in evidence["validation"]["checks"]
                if item["metric"] == "buyback_event_times"
            )["status"],
            "matched",
        )
        self.assertEqual(
            next(
                item for item in evidence["validation"]["checks"]
                if item["metric"] == "death_state_seconds"
            )["status"],
            "matched",
        )
        state_check = next(
            item for item in evidence["validation"]["checks"]
            if item["metric"] == "death_state_seconds"
        )
        self.assertEqual(state_check["left_label"], "OpenDota总死亡时长")
        self.assertEqual(state_check["right_label"], "逐秒生命状态")
        self.assertEqual(state_check["delta"], 1)
        self.assertTrue(state_check["within_tolerance"])
        event_check = next(
            item for item in evidence["validation"]["checks"]
            if item["metric"] == "kill_event_times"
        )
        self.assertEqual(event_check["left_label"], "回放记分板")
        self.assertEqual(event_check["right_label"], "回放事件时间线")
        self.assertTrue(all(
            item["status"] == "matched"
            for item in evidence["validation"]["checks"]
        ))

    def test_parser_adapter_preserves_raw_assist_player_slots_and_restores_parser(self):
        emitted = []

        class FakeCombatLogProcessor:
            def __init__(self):
                self._handlers = [emitted.append]

            def process_s2_entry(self, msg, name_table, tick=0, game_time_s=None):
                entry = SimpleNamespace(tick=tick, game_time_s=game_time_s)
                for handler in self._handlers:
                    handler(entry)

        original = FakeCombatLogProcessor.process_s2_entry

        class FakeParser:
            @staticmethod
            def parse(_path):
                processor = FakeCombatLogProcessor()
                processor.process_s2_entry(
                    SimpleNamespace(assist_players=[0, 3]),
                    {},
                    tick=123,
                    game_time_s=45,
                )
                return SimpleNamespace(combat_log=emitted)

        combat_module = SimpleNamespace(CombatLogProcessor=FakeCombatLogProcessor)
        parsed = _parse_with_raw_assists(FakeParser, "fixture.dem", combat_module=combat_module)

        self.assertEqual(parsed.combat_log[0].assist_players, [0, 3])
        self.assertIs(FakeCombatLogProcessor.process_s2_entry, original)

    def test_parser_adapter_can_capture_real_player_life_state_snapshots(self):
        created = []

        class FakeCombatLogProcessor:
            def __init__(self):
                self._handlers = []

            def process_s2_entry(self, *_args, **_kwargs):
                return None

        class FakePlayerExtractor:
            def __init__(self):
                self._sample_interval = 30
                self._parser = SimpleNamespace(tick=330, game_time_s=11)
                self.snapshots = [
                    SimpleNamespace(player_id=1, game_time_s=11, life_state=0),
                ]
                created.append(self)

            def _canonical_hero_entity(self, player_id):
                return SimpleNamespace(get_int32=lambda field: 2 if field == "m_lifeState" else 0)

            def _maybe_sample(self):
                return None

        player_module = SimpleNamespace(
            PlayerExtractor=FakePlayerExtractor,
            _pos=lambda _entity: (128.0, 256.0),
        )
        original_extractor = player_module.PlayerExtractor

        class FakeParser:
            @staticmethod
            def parse(_path):
                extractor = player_module.PlayerExtractor()
                extractor._maybe_sample()
                return SimpleNamespace(match_id=MATCH_ID)

        parsed, snapshots = _parse_with_raw_assists(
            FakeParser,
            "fixture.dem",
            combat_module=SimpleNamespace(CombatLogProcessor=FakeCombatLogProcessor),
            player_module=player_module,
            capture_player_snapshots=True,
            target_player_id=0,
        )

        self.assertEqual(parsed.match_id, MATCH_ID)
        self.assertEqual(created[0]._sample_interval, 300)
        self.assertEqual([item.player_id for item in snapshots], list(range(10)))
        self.assertTrue(all(item.life_state == 2 for item in snapshots))
        self.assertEqual((snapshots[0].x, snapshots[0].y), (128.0, 256.0))
        self.assertIs(player_module.PlayerExtractor, original_extractor)

    def test_build_replay_evidence_surfaces_scoreboard_conflicts(self):
        player = SimpleNamespace(
            account_id=ACCOUNT_ID,
            hero_name="npc_dota_hero_morphling",
            player_id=0,
            lane_role=1,
            kills=7,
            deaths=1,
            assists=3,
            last_hits=17,
            denies=2,
            hero_damage=250,
            tower_damage=0,
            lh_t_min=[0, 8, 17],
            dn_t_min=[0, 1, 2],
            total_earned_gold_t_min=[0, 500, 1100],
            total_earned_xp_t_min=[0, 450, 1000],
            total_hero_damage_t_min=[0, 100, 250],
            position_log=[],
            purchase_log=[],
            kills_log=[],
            ability_upgrades_arr=[],
            obs_log=[],
            sen_log=[],
            camps_stacked=0,
            rune_pickups=0,
            courier_kills=0,
            observer_kills=0,
            sentry_kills=0,
            item_uses={},
            ability_uses={},
        )
        match = SimpleNamespace(
            match_id=MATCH_ID,
            duration=120,
            players=[player],
            combat_log=[],
            objectives=[],
        )
        detail = {
            "duration": 120,
            "players": [{"account_id": ACCOUNT_ID, "kills": 8}],
        }

        evidence = build_replay_evidence(
            match,
            match_id=MATCH_ID,
            account_id=ACCOUNT_ID,
            match_detail=detail,
        )

        self.assertEqual(evidence["validation"]["status"], "conflict")
        conflict = next(
            item for item in evidence["validation"]["checks"]
            if item["metric"] == "kills"
        )
        self.assertEqual(conflict["api_value"], 8)
        self.assertEqual(conflict["replay_value"], 7)


if __name__ == "__main__":
    unittest.main()
