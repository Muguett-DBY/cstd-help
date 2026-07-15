import bz2
import importlib
import math
import re
import tempfile
import threading
from bisect import bisect_left
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

import requests


MAX_COMPRESSED_REPLAY_BYTES = 600 * 1024 * 1024
MAX_DECOMPRESSED_REPLAY_BYTES = 2 * 1024 * 1024 * 1024
REPLAY_CHUNK_BYTES = 1024 * 1024
REPLAY_DOWNLOAD_ATTEMPTS = 4
REPLAY_ALL_PLAYER_SAMPLE_TICKS = 300
REPLAY_ALL_PLAYER_POSITION_SAMPLE_TICKS = 60
REPLAY_TARGET_SAMPLE_TICKS = 30
VALVE_REPLAY_HOST = re.compile(r"^replay\d+\.valve\.net$", re.IGNORECASE)
_REPLAY_PARSE_LOCK = threading.Lock()


class ReplayEvidenceError(RuntimeError):
    pass


def normalize_replay_url(value, match_id=None):
    if not isinstance(value, str) or not value.strip():
        raise ReplayEvidenceError("REPLAY_URL_MISSING")
    parsed = urlsplit(value.strip())
    hostname = (parsed.hostname or "").lower()
    if not VALVE_REPLAY_HOST.fullmatch(hostname):
        raise ReplayEvidenceError("REPLAY_HOST_NOT_ALLOWED")
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ReplayEvidenceError("REPLAY_SCHEME_NOT_ALLOWED")
    if parsed.username or parsed.password or parsed.port not in (None, 443, 80):
        raise ReplayEvidenceError("REPLAY_URL_INVALID")
    if match_id is not None and not re.fullmatch(
        rf"/570/{int(match_id)}_\d+\.dem\.bz2",
        parsed.path,
    ):
        raise ReplayEvidenceError("REPLAY_PATH_MISMATCH")
    return urlunsplit((parsed.scheme.lower(), hostname, parsed.path, "", ""))


def replay_url_from_match(match_detail, match_id):
    detail = match_detail or {}
    replay_url = detail.get("replay_url")
    if not replay_url:
        cluster = detail.get("cluster")
        replay_salt = detail.get("replay_salt")
        if cluster is not None and replay_salt is not None:
            replay_url = (
                f"http://replay{int(cluster)}.valve.net/570/"
                f"{int(match_id)}_{int(replay_salt)}.dem.bz2"
            )
    return normalize_replay_url(replay_url, match_id=match_id)


def _number(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        return None
    return value


def _event_type(event):
    value = getattr(event, "log_type", None)
    return str(getattr(value, "value", value) or "").upper()


def _event_time(event, game_start_tick=None):
    value = _number(getattr(event, "game_time_s", None))
    if value is not None:
        return int(value)
    tick = _number(getattr(event, "tick", None))
    if tick is None or game_start_tick is None:
        return None
    return int(round((tick - game_start_tick) / 30))


def _diff_cumulative(values, limit=None):
    numbers = [_number(value) for value in (values or [])]
    if any(value is None for value in numbers):
        return []
    if len(numbers) < 2:
        return []
    diffs = []
    for previous, value in zip(numbers, numbers[1:]):
        delta = value - previous
        if delta < 0:
            return []
        diffs.append(delta)
    return diffs[:limit] if isinstance(limit, int) and limit >= 0 else diffs


def _nearest_position(position_log, target_tick):
    samples = [
        sample for sample in (position_log or [])
        if isinstance(sample, (list, tuple))
        and len(sample) >= 3
        and all(_number(value) is not None for value in sample[:3])
    ]
    if not samples or _number(target_tick) is None:
        return None
    ticks = [sample[0] for sample in samples]
    index = bisect_left(ticks, target_tick)
    if index == 0:
        sample = samples[0]
    elif index >= len(samples):
        sample = samples[-1]
    else:
        before = samples[index - 1]
        after = samples[index]
        sample = before if target_tick - before[0] <= after[0] - target_tick else after
    sample_tick, world_x, world_y = sample[:3]
    return {
        "position": {
            "x": round(world_x / 128, 2),
            "y": round(world_y / 128, 2),
        },
        "world_position": {"x": round(world_x, 2), "y": round(world_y, 2)},
        "sample_tick": int(sample_tick),
        "sample_delta_seconds": round((sample_tick - target_tick) / 30, 2),
    }


def _match_player(match_detail, account_id):
    for player in (match_detail or {}).get("players") or []:
        if player.get("account_id") == int(account_id):
            return player
    return None


def _replay_player_id_from_slot(slot):
    if isinstance(slot, bool) or not isinstance(slot, int):
        return None
    if 0 <= slot <= 9:
        return slot
    if 128 <= slot <= 132:
        return slot - 123
    return None


def _replay_player_id_from_match_detail(match_detail, account_id):
    player = _match_player(match_detail, account_id)
    if not player:
        return None
    return _replay_player_id_from_slot(player.get("player_slot"))


def _replay_hero_ids(match_detail):
    result = {}
    for player in (match_detail or {}).get("players") or []:
        player_id = _replay_player_id_from_slot(player.get("player_slot"))
        hero_id = player.get("hero_id")
        if player_id is not None and isinstance(hero_id, int) and not isinstance(hero_id, bool):
            result[player_id] = hero_id
    return result


def _death_nearby_context(
    *,
    death_tick,
    target_player_id,
    target_position,
    snapshots,
    hero_ids=None,
    radius_units=1600,
    max_sample_delta_ticks=90,
):
    if (
        _number(death_tick) is None
        or not isinstance(target_player_id, int)
        or _number((target_position or {}).get("x")) is None
        or _number((target_position or {}).get("y")) is None
    ):
        return None

    nearest_by_player = {}
    for sample in snapshots or []:
        player_id = getattr(sample, "player_id", None)
        tick = _number(getattr(sample, "tick", None))
        x = _number(getattr(sample, "x", None))
        y = _number(getattr(sample, "y", None))
        if (
            not isinstance(player_id, int)
            or player_id == target_player_id
            or tick is None
            or x is None
            or y is None
        ):
            continue
        delta = abs(tick - death_tick)
        if delta > max_sample_delta_ticks:
            continue
        current = nearest_by_player.get(player_id)
        if current is None or delta < current[0]:
            nearest_by_player[player_id] = (delta, sample)

    target_is_radiant = target_player_id <= 4
    target_x = float(target_position["x"])
    target_y = float(target_position["y"])
    allies = []
    enemies = []
    sampled_players = 0
    for player_id, (delta_ticks, sample) in nearest_by_player.items():
        life_state = _number(getattr(sample, "life_state", None))
        if life_state is None:
            continue
        sampled_players += 1
        if life_state != 0:
            continue
        distance = int(round(math.hypot(float(sample.x) - target_x, float(sample.y) - target_y)))
        item = {
            "player_id": player_id,
            "hero_id": (hero_ids or {}).get(player_id),
            "distance_units": distance,
            "sample_delta_seconds": round(delta_ticks / 30, 2),
        }
        same_team = (player_id <= 4) == target_is_radiant
        (allies if same_team else enemies).append(item)

    allies.sort(key=lambda item: item["distance_units"])
    enemies.sort(key=lambda item: item["distance_units"])
    allies_in_radius = [item for item in allies if item["distance_units"] <= radius_units]
    enemies_in_radius = [item for item in enemies if item["distance_units"] <= radius_units]
    return {
        "source": "valve_replay_all_player_positions",
        "radius_units": radius_units,
        "sample_resolution_seconds": REPLAY_ALL_PLAYER_POSITION_SAMPLE_TICKS // 30,
        "sampled_other_players": sampled_players,
        "coverage_complete": sampled_players == 9,
        "allies_within_radius_count": len(allies_in_radius),
        "enemies_within_radius_count": len(enemies_in_radius),
        "allies_within_radius": allies_in_radius,
        "enemies_within_radius": enemies_in_radius,
        "nearest_ally": allies[0] if allies else None,
        "nearest_enemy": enemies[0] if enemies else None,
    }


def _validation_checks(replay_player, api_player):
    if not api_player:
        return []
    checks = []
    labels = {
        "kills": "击杀",
        "deaths": "死亡",
        "assists": "助攻",
        "last_hits": "补刀",
        "denies": "反补",
        "hero_damage": "英雄伤害",
        "tower_damage": "建筑伤害",
    }
    for metric in (
        "kills",
        "deaths",
        "assists",
        "last_hits",
        "denies",
        "hero_damage",
        "tower_damage",
    ):
        api_value = _number(api_player.get(metric))
        replay_value = _number(getattr(replay_player, metric, None))
        if api_value is None or replay_value is None:
            continue
        checks.append({
            "metric": metric,
            "label": labels[metric],
            "api_value": api_value,
            "replay_value": replay_value,
            "delta": replay_value - api_value,
            "status": "matched" if replay_value == api_value else "conflict",
            "left_label": "OpenDota",
            "right_label": "Valve回放",
            "comparison": "opendota_aggregate_to_replay_aggregate",
        })
    return checks


def _raw_assist_players(message):
    players = []
    for value in getattr(message, "assist_players", None) or []:
        if isinstance(value, int) and 0 <= value <= 9 and value not in players:
            players.append(value)
    if players:
        return players

    has_field = getattr(message, "HasField", None)
    for field in ("assist_player0", "assist_player1", "assist_player2", "assist_player3"):
        try:
            present = callable(has_field) and has_field(field)
        except (ValueError, TypeError):
            present = False
        value = getattr(message, field, None)
        if present and isinstance(value, int) and 0 <= value <= 9 and value not in players:
            players.append(value)
    return players


def _parse_with_raw_assists(
    parser_module,
    replay_path,
    *,
    combat_module=None,
    player_module=None,
    capture_player_snapshots=False,
    target_player_id=None,
):
    """Preserve protobuf assist slots omitted by gem-dota 0.5.0's public model."""
    combat_module = combat_module or importlib.import_module("gem.combat.log")
    processor_class = getattr(combat_module, "CombatLogProcessor", None)
    original = getattr(processor_class, "process_s2_entry", None)
    if processor_class is None or not callable(original):
        raise ReplayEvidenceError("REPLAY_ASSIST_ADAPTER_UNAVAILABLE")

    captured_extractors = []
    original_player_extractor = None
    capturing_player_extractor = None
    if capture_player_snapshots:
        player_module = player_module or importlib.import_module("gem.extractors.players")
        original_player_extractor = getattr(player_module, "PlayerExtractor", None)
        if original_player_extractor is None:
            raise ReplayEvidenceError("REPLAY_PLAYER_STATE_ADAPTER_UNAVAILABLE")

        class CapturingPlayerExtractor(original_player_extractor):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if target_player_id is not None:
                    self._sample_interval = max(
                        int(getattr(self, "_sample_interval", 0) or 0),
                        REPLAY_ALL_PLAYER_SAMPLE_TICKS,
                    )
                self._target_state_snapshots = []
                self._last_target_state_tick = -REPLAY_TARGET_SAMPLE_TICKS
                self._all_player_position_snapshots = []
                self._last_all_player_position_tick = -REPLAY_ALL_PLAYER_POSITION_SAMPLE_TICKS
                captured_extractors.append(self)

            def _maybe_sample(self):
                parser = getattr(self, "_parser", None)
                tick = getattr(parser, "tick", None)
                if (
                    target_player_id is not None
                    and isinstance(tick, int)
                    and tick - self._last_target_state_tick >= REPLAY_TARGET_SAMPLE_TICKS
                ):
                    self._last_target_state_tick = tick
                    entity = self._canonical_hero_entity(int(target_player_id))
                    if entity is not None:
                        life_state = entity.get_int32("m_lifeState")
                        position_reader = getattr(player_module, "_pos", None)
                        position = position_reader(entity) if callable(position_reader) else None
                        assists = None
                        player_resource = getattr(self, "_player_resource", None)
                        resource_index = getattr(self, "_resource_index", None)
                        if player_resource is not None and callable(resource_index):
                            prefix = (
                                "m_vecPlayerTeamData."
                                f"{resource_index(int(target_player_id)):04d}"
                            )
                            assists = player_resource.get_int32(f"{prefix}.m_iAssists")
                        self._target_state_snapshots.append(SimpleNamespace(
                            player_id=int(target_player_id),
                            tick=tick,
                            game_time_s=getattr(parser, "game_time_s", None),
                            life_state=life_state,
                            x=position[0] if position else None,
                            y=position[1] if position else None,
                            assists=assists,
                        ))
                if (
                    target_player_id is not None
                    and isinstance(tick, int)
                    and tick - self._last_all_player_position_tick
                    >= REPLAY_ALL_PLAYER_POSITION_SAMPLE_TICKS
                ):
                    self._last_all_player_position_tick = tick
                    position_reader = getattr(player_module, "_pos", None)
                    for player_id in range(10):
                        if player_id == int(target_player_id):
                            continue
                        entity = self._canonical_hero_entity(player_id)
                        if entity is None:
                            continue
                        position = position_reader(entity) if callable(position_reader) else None
                        if not position:
                            continue
                        self._all_player_position_snapshots.append(SimpleNamespace(
                            player_id=player_id,
                            tick=tick,
                            game_time_s=getattr(parser, "game_time_s", None),
                            life_state=entity.get_int32("m_lifeState"),
                            x=position[0],
                            y=position[1],
                            assists=None,
                        ))
                return super()._maybe_sample()

        capturing_player_extractor = CapturingPlayerExtractor

    def process_with_assists(self, message, name_table, tick=0, game_time_s=None):
        original_handlers = self._handlers
        assist_players = _raw_assist_players(message)

        def attach_assists(entry):
            entry.assist_players = list(assist_players)

        self._handlers = [attach_assists, *original_handlers]
        try:
            return original(
                self,
                message,
                name_table,
                tick=tick,
                game_time_s=game_time_s,
            )
        finally:
            self._handlers = original_handlers

    with _REPLAY_PARSE_LOCK:
        processor_class.process_s2_entry = process_with_assists
        if capture_player_snapshots:
            player_module.PlayerExtractor = capturing_player_extractor
        try:
            parsed_match = parser_module.parse(str(replay_path))
            if not capture_player_snapshots:
                return parsed_match
            snapshots = []
            if captured_extractors:
                extractor = captured_extractors[-1]
                target_snapshots = list(
                    getattr(extractor, "_target_state_snapshots", None) or []
                )
                all_player_snapshots = list(
                    getattr(extractor, "_all_player_position_snapshots", None) or []
                )
                snapshots = target_snapshots + all_player_snapshots
                if not snapshots:
                    snapshots = list(getattr(extractor, "snapshots", None) or [])
            return parsed_match, snapshots
        finally:
            processor_class.process_s2_entry = original
            if capture_player_snapshots:
                player_module.PlayerExtractor = original_player_extractor


def _player_life_state_intervals(snapshots, player_id, game_start_tick=None):
    """Return replay-observed non-alive seconds grouped into death intervals."""
    state_by_second = {}
    for snapshot in snapshots or []:
        if getattr(snapshot, "player_id", None) != player_id:
            continue
        life_state = _number(getattr(snapshot, "life_state", None))
        if life_state is None:
            continue
        tick = _number(getattr(snapshot, "tick", None))
        game_time = _number(getattr(snapshot, "game_time_s", None))
        if game_time is not None:
            second_key = int(game_time)
        elif tick is not None:
            second_key = int(tick // 30)
        else:
            continue
        if game_time is not None and game_time < 0:
            continue
        # Multiple snapshots can land in one game-second. A non-alive sample
        # wins, matching gem/OpenDota's aggregate life_state_dead definition.
        state = state_by_second.setdefault(second_key, {
            "is_dead": False,
            "tick": int(tick) if tick is not None else None,
            "game_time": int(game_time) if game_time is not None else None,
        })
        if bool(life_state):
            state["is_dead"] = True
            if tick is not None:
                state["tick"] = int(tick)
            if game_time is not None:
                state["game_time"] = int(game_time)

    dead_seconds = sorted(
        second for second, state in state_by_second.items()
        if state["is_dead"]
    )
    if not dead_seconds:
        return []

    groups = []
    current = [dead_seconds[0]]
    for second in dead_seconds[1:]:
        if second == current[-1] + 1:
            current.append(second)
        else:
            groups.append(current)
            current = [second]
    groups.append(current)

    observed_seconds = sorted(state_by_second)
    intervals = []
    for group in groups:
        first_dead = group[0]
        last_dead = group[-1]
        respawn_second = next(
            (
                second for second in observed_seconds
                if second > last_dead and not state_by_second[second]["is_dead"]
            ),
            None,
        )
        first_state = state_by_second[first_dead]
        last_state = state_by_second[last_dead]
        respawn_state = state_by_second.get(respawn_second) if respawn_second is not None else None
        intervals.append({
            "start_time": first_state["game_time"],
            "last_dead_sample_time": last_state["game_time"],
            "respawn_observed_at": (
                respawn_state["game_time"] if respawn_state else None
            ),
            "start_tick": first_state["tick"],
            "last_dead_sample_tick": last_state["tick"],
            "respawn_observed_tick": respawn_state["tick"] if respawn_state else None,
            "time_dead": len(group),
            "sample_resolution_seconds": 1,
            "source": "valve_replay_life_state",
        })
    return intervals


def _attach_life_state_intervals(deaths, intervals):
    available = set(range(len(intervals or [])))
    for death in deaths or []:
        death_time = _number(death.get("time"))
        if death_time is None or not available:
            continue
        death_tick = _number(death.get("event_tick"))
        if death_tick is not None:
            candidates = [
                index for index in available
                if _number(intervals[index].get("start_tick")) is not None
                and abs(intervals[index]["start_tick"] - death_tick) <= 90
            ]
            distance = lambda candidate: abs(
                intervals[candidate]["start_tick"] - death_tick
            )
        else:
            candidates = [
                index for index in available
                if _number(intervals[index].get("start_time")) is not None
                and abs(intervals[index]["start_time"] - death_time) <= 3
            ]
            distance = lambda candidate: abs(
                intervals[candidate]["start_time"] - death_time
            )
        if not candidates:
            continue
        index = min(candidates, key=distance)
        available.remove(index)
        interval = intervals[index]
        alignment_seconds = (
            round((interval["start_tick"] - death_tick) / 30, 2)
            if death_tick is not None and interval.get("start_tick") is not None
            else interval["start_time"] - death_time
        )
        state_started_at = int(round(death_time + alignment_seconds))
        respawn_tick = _number(interval.get("respawn_observed_tick"))
        respawn_observed_at = (
            int(round(death_time + ((respawn_tick - death_tick) / 30)))
            if death_tick is not None and respawn_tick is not None
            else interval.get("respawn_observed_at")
        )
        death.update({
            "time_dead": interval["time_dead"],
            "death_state_started_at": state_started_at,
            "respawn_observed_at": respawn_observed_at,
            "death_state_alignment_seconds": alignment_seconds,
            "time_dead_source": interval["source"],
            "time_dead_resolution_seconds": interval["sample_resolution_seconds"],
        })
    return deaths


def _is_real_hero_death(entry):
    target_name = getattr(entry, "target_name", "") or ""
    return (
        _event_type(entry) == "DEATH"
        and target_name.startswith("npc_dota_hero_")
        and bool(getattr(entry, "target_is_hero", False))
        and not bool(getattr(entry, "target_is_illusion", False))
        and not bool(getattr(entry, "will_reincarnate", False))
    )


def _scoreboard_assist_events(player_state_snapshots, player_id):
    assists_by_second = {}
    for sample in player_state_snapshots or []:
        if getattr(sample, "player_id", None) != player_id:
            continue
        game_time = _number(getattr(sample, "game_time_s", None))
        assists = _number(getattr(sample, "assists", None))
        if game_time is None or game_time < 0 or assists is None:
            continue
        second = int(game_time)
        assists_by_second[second] = max(
            int(assists),
            assists_by_second.get(second, 0),
        )

    events = []
    previous = 0
    for second in sorted(assists_by_second):
        current = max(previous, assists_by_second[second])
        for _ in range(current - previous):
            events.append({
                "time": second,
                "target": None,
                "killer": None,
                "source": "valve_replay_player_resource",
                "time_resolution_seconds": 1,
            })
        previous = current
    return events


def _reconcile_assist_events(raw_events, scoreboard_events, expected_count):
    if not isinstance(expected_count, int) or len(raw_events) == expected_count:
        return raw_events
    if len(scoreboard_events) != expected_count:
        return raw_events

    unused_raw = set(range(len(raw_events)))
    reconciled = []
    for scoreboard_event in scoreboard_events:
        candidates = [
            index for index in unused_raw
            if abs(raw_events[index]["time"] - scoreboard_event["time"]) <= 2
        ]
        if not candidates:
            reconciled.append(dict(scoreboard_event))
            continue
        index = min(
            candidates,
            key=lambda candidate: abs(
                raw_events[candidate]["time"] - scoreboard_event["time"]
            ),
        )
        unused_raw.remove(index)
        event = dict(raw_events[index])
        event["verified_by"] = "valve_replay_player_resource"
        reconciled.append(event)
    return sorted(reconciled, key=lambda item: item["time"])


def _replay_fight_events(
    parsed_match,
    player,
    game_start_tick,
    player_state_snapshots=None,
):
    kills = []
    kill_signatures = set()
    for entry in getattr(player, "kills_log", None) or []:
        event_time = _event_time(entry, game_start_tick=game_start_tick)
        if not _is_real_hero_death(entry) or event_time is None or event_time < 0:
            continue
        kills.append({
            "time": event_time,
            "target": getattr(entry, "target_name", "") or None,
            "source": "valve_replay_gem",
        })
        kill_signatures.add((event_time, getattr(entry, "target_name", "") or ""))

    player_id = getattr(player, "player_id", None)
    assists = []
    for entry in getattr(parsed_match, "combat_log", None) or []:
        event_time = _event_time(entry, game_start_tick=game_start_tick)
        assist_players = getattr(entry, "assist_players", None) or []
        signature = (event_time, getattr(entry, "target_name", "") or "")
        if (
            not _is_real_hero_death(entry)
            or event_time is None
            or event_time < 0
            or player_id not in assist_players
            or signature in kill_signatures
        ):
            continue
        assists.append({
            "time": event_time,
            "target": getattr(entry, "target_name", "") or None,
            "killer": getattr(entry, "attacker_name", "") or None,
            "source": "valve_replay_gem",
        })
    assists = sorted(assists, key=lambda item: item["time"])
    scoreboard_assists = _scoreboard_assist_events(
        player_state_snapshots,
        player_id,
    )
    assists = _reconcile_assist_events(
        assists,
        scoreboard_assists,
        getattr(player, "assists", None),
    )
    return sorted(kills, key=lambda item: item["time"]), assists


def _buyback_event_time(entry, game_start_tick):
    if isinstance(entry, (int, float)) and not isinstance(entry, bool):
        return int(entry)
    if isinstance(entry, dict):
        event_time = _number(entry.get("time"))
        if event_time is None:
            event_time = _number(entry.get("game_time_s"))
        if event_time is not None:
            return int(event_time)
        tick = _number(entry.get("tick"))
        if tick is not None and game_start_tick is not None:
            return int(round((tick - game_start_tick) / 30))
        return None
    return _event_time(entry, game_start_tick=game_start_tick)


def _replay_buyback_events(parsed_match, player, game_start_tick):
    entries = list(getattr(player, "buyback_log", None) or [])
    if not entries:
        hero_name = getattr(player, "hero_name", "") or ""
        player_id = getattr(player, "player_id", None)
        for entry in getattr(parsed_match, "combat_log", None) or []:
            if _event_type(entry) != "BUYBACK":
                continue
            names = {
                getattr(entry, "target_name", None),
                getattr(entry, "attacker_name", None),
                getattr(entry, "value_name", None),
            }
            player_ids = {
                getattr(entry, "player_id", None),
                getattr(entry, "target_player_id", None),
                getattr(entry, "attacker_player_id", None),
            }
            if hero_name in names or player_id in player_ids:
                entries.append(entry)

    seen = set()
    normalized = []
    for entry in entries:
        event_time = _buyback_event_time(entry, game_start_tick)
        if event_time is None or event_time < 0 or event_time in seen:
            continue
        seen.add(event_time)
        normalized.append({
            "time": event_time,
            "source": "valve_replay_gem",
        })
    return sorted(normalized, key=lambda item: item["time"])


def _event_validation_checks(player, kills, assists, buybacks):
    checks = []
    for metric, label, expected, observed in (
        ("kill_event_times", "击杀事件时间", getattr(player, "kills", None), len(kills)),
        ("assist_event_times", "助攻事件时间", getattr(player, "assists", None), len(assists)),
        (
            "buyback_event_times",
            "买活事件时间",
            getattr(player, "buyback_count", None),
            len(buybacks),
        ),
    ):
        if not isinstance(expected, int):
            continue
        checks.append({
            "metric": metric,
            "label": label,
            "api_value": expected,
            "replay_value": observed,
            "delta": observed - expected,
            "status": "matched" if observed == expected else "conflict",
            "comparison": "replay_scoreboard_to_event_timeline",
            "left_label": "回放记分板",
            "right_label": "回放事件时间线",
        })
    return checks


def _ward_events(player, game_start_tick):
    normalized = []
    for ward in [*(getattr(player, "obs_log", None) or []), *(getattr(player, "sen_log", None) or [])]:
        tick = _number(getattr(ward, "tick", None))
        event_time = _event_time(ward, game_start_tick=game_start_tick)
        if event_time is None and tick is not None and game_start_tick is not None:
            event_time = int(round((tick - game_start_tick) / 30))
        x = _number(getattr(ward, "x", None))
        y = _number(getattr(ward, "y", None))
        item = {
            "time": event_time,
            "type": getattr(ward, "ward_type", None),
            "source": "valve_replay_gem",
        }
        if x is not None and y is not None:
            item["position"] = {"x": round(x / 128, 2), "y": round(y / 128, 2)}
        normalized.append(item)
    return sorted(
        [item for item in normalized if item.get("time") is not None],
        key=lambda item: item["time"],
    )


def build_replay_evidence(
    parsed_match,
    *,
    match_id,
    account_id,
    match_detail=None,
    parser_version=None,
    player_state_snapshots=None,
):
    parsed_match_id = int(getattr(parsed_match, "match_id", 0) or 0)
    if parsed_match_id and parsed_match_id != int(match_id):
        raise ReplayEvidenceError("REPLAY_MATCH_ID_MISMATCH")
    player = next(
        (
            item for item in (getattr(parsed_match, "players", None) or [])
            if getattr(item, "account_id", None) == int(account_id)
        ),
        None,
    )
    if player is None:
        raise ReplayEvidenceError("REPLAY_PLAYER_NOT_FOUND")

    duration_value = _number((match_detail or {}).get("duration"))
    if duration_value is None or duration_value <= 0:
        duration_value = _number(getattr(parsed_match, "duration", None))
    if duration_value is None or duration_value <= 0:
        raise ReplayEvidenceError("REPLAY_DURATION_UNAVAILABLE")
    duration_seconds = int(duration_value)
    minute_count = max(duration_seconds // 60, 1)
    game_start_tick = getattr(parsed_match, "game_start_tick", None)
    hero_name = getattr(player, "hero_name", "") or ""
    target_player_id = getattr(player, "player_id", None)
    replay_hero_ids = _replay_hero_ids(match_detail)
    state_position_log = [
        [sample.tick, sample.x, sample.y]
        for sample in (player_state_snapshots or [])
        if getattr(sample, "player_id", None) == getattr(player, "player_id", None)
        and _number(getattr(sample, "tick", None)) is not None
        and _number(getattr(sample, "x", None)) is not None
        and _number(getattr(sample, "y", None)) is not None
    ]
    position_log = state_position_log or getattr(player, "position_log", None)

    tower_damage = [0] * minute_count
    tower_damage_complete = True
    deaths = []
    for entry in getattr(parsed_match, "combat_log", None) or []:
        event_type = _event_type(entry)
        event_time = _event_time(entry, game_start_tick=game_start_tick)
        if event_time is None:
            continue
        if event_type == "DAMAGE":
            source_name = (
                getattr(entry, "damage_source_name", "")
                or getattr(entry, "attacker_name", "")
            )
            target_name = getattr(entry, "target_name", "") or ""
            if source_name == hero_name and any(
                marker in target_name for marker in ("_tower", "_rax", "_fort")
            ):
                minute = event_time // 60
                if 0 <= minute < minute_count:
                    damage_value = _number(getattr(entry, "value", None))
                    if damage_value is None:
                        tower_damage_complete = False
                    else:
                        tower_damage[minute] += int(damage_value)
        elif (
            event_type == "DEATH"
            and getattr(entry, "target_name", "") == hero_name
            and bool(getattr(entry, "target_is_hero", False))
            and not bool(getattr(entry, "target_is_illusion", False))
            and not bool(getattr(entry, "will_reincarnate", False))
            and event_time >= 0
        ):
            item = {
                "time": event_time,
                "killer": getattr(entry, "attacker_name", "") or None,
                "source": "valve_replay_gem",
            }
            if _number(getattr(entry, "tick", None)) is not None:
                item["event_tick"] = int(entry.tick)
            sampled = _nearest_position(
                position_log,
                getattr(entry, "tick", None),
            )
            if sampled:
                item.update(sampled)
                item["position_source"] = "valve_replay_position_sample"
                nearby_context = _death_nearby_context(
                    death_tick=getattr(entry, "tick", None),
                    target_player_id=target_player_id,
                    target_position=item.get("world_position"),
                    snapshots=player_state_snapshots,
                    hero_ids=replay_hero_ids,
                )
                if nearby_context:
                    item["nearby_context"] = nearby_context
            deaths.append(item)

    life_state_intervals = _player_life_state_intervals(
        player_state_snapshots,
        getattr(player, "player_id", None),
        game_start_tick=game_start_tick,
    )
    deaths = _attach_life_state_intervals(deaths, life_state_intervals)

    raw_purchase_log = getattr(player, "purchase_log", None)
    purchases = []
    for entry in raw_purchase_log or []:
        event_time = _event_time(entry, game_start_tick=game_start_tick)
        item_key = str(getattr(entry, "value_name", "") or "")
        if item_key.startswith("item_"):
            item_key = item_key[5:]
        if event_time is None or not item_key:
            continue
        purchases.append({
            "time": event_time,
            "item_key": item_key,
            "source": "valve_replay_gem",
        })

    kills, assists = _replay_fight_events(
        parsed_match,
        player,
        game_start_tick,
        player_state_snapshots=player_state_snapshots,
    )
    buybacks = _replay_buyback_events(parsed_match, player, game_start_tick)
    checks = [
        *_validation_checks(player, _match_player(match_detail, account_id)),
        *_event_validation_checks(player, kills, assists, buybacks),
    ]
    observed_dead_seconds = (
        sum(interval["time_dead"] for interval in life_state_intervals)
        if life_state_intervals else None
    )
    api_player = _match_player(match_detail, account_id) or {}
    api_dead_seconds = api_player.get("life_state_dead")
    parsed_dead_seconds = getattr(player, "life_state_dead", None)
    expected_dead_seconds = (
        api_dead_seconds if isinstance(api_dead_seconds, int) else parsed_dead_seconds
    )
    if life_state_intervals and isinstance(expected_dead_seconds, int):
        expected_label = (
            "OpenDota总死亡时长"
            if isinstance(api_dead_seconds, int)
            else "回放总死亡时长"
        )
        tolerance_seconds = max(
            int(interval.get("sample_resolution_seconds") or 0)
            for interval in life_state_intervals
        )
        delta = observed_dead_seconds - expected_dead_seconds
        within_tolerance = abs(delta) <= tolerance_seconds
        checks.append({
            "metric": "death_state_seconds",
            "label": "逐秒死亡状态",
            "api_value": expected_dead_seconds,
            "replay_value": observed_dead_seconds,
            "delta": delta,
            "status": "matched" if within_tolerance else "conflict",
            "within_tolerance": within_tolerance,
            "tolerance_seconds": tolerance_seconds,
            "comparison": "replay_life_state_intervals_to_replay_aggregate",
            "left_label": expected_label,
            "right_label": "逐秒生命状态",
        })
    validation_status = (
        "conflict" if any(item["status"] == "conflict" for item in checks)
        else "matched" if checks
        else "unverified"
    )
    raw_obs_log = getattr(player, "obs_log", None)
    raw_sen_log = getattr(player, "sen_log", None)
    vision_events = (
        _ward_events(player, game_start_tick)
        if isinstance(raw_obs_log, (list, tuple))
        and isinstance(raw_sen_log, (list, tuple))
        else None
    )
    raw_objectives = getattr(parsed_match, "objectives", None)

    def mapping_payload(value):
        if value is None:
            return None
        try:
            return dict(value)
        except (TypeError, ValueError):
            return None

    return {
        "source": "valve_replay_gem",
        "parser": {"name": "gem-dota", "version": parser_version},
        "match_id": int(match_id),
        "account_id": int(account_id),
        "player": {
            "hero_name": hero_name,
            "player_id": target_player_id,
            "lane_role": getattr(player, "lane_role", None),
            "ability_upgrades": list(getattr(player, "ability_upgrades_arr", None) or []),
        },
        "timeline": {
            "last_hits_per_minute": _diff_cumulative(getattr(player, "lh_t_min", None), minute_count),
            "denies_per_minute": _diff_cumulative(getattr(player, "dn_t_min", None), minute_count),
            "gold_per_minute": _diff_cumulative(
                getattr(player, "total_earned_gold_t_min", None),
                minute_count,
            ),
            "experience_per_minute": _diff_cumulative(
                getattr(player, "total_earned_xp_t_min", None),
                minute_count,
            ),
            "hero_damage_per_minute": _diff_cumulative(
                getattr(player, "total_hero_damage_t_min", None),
                minute_count,
            ),
            "tower_damage_per_minute": tower_damage if tower_damage_complete else [],
        },
        "deaths": sorted(deaths, key=lambda item: item["time"]),
        "death_state_intervals": life_state_intervals,
        "kills": kills,
        "assists": assists,
        "buybacks": buybacks,
        "purchases": (
            sorted(purchases, key=lambda item: item["time"])
            if isinstance(raw_purchase_log, (list, tuple)) else None
        ),
        "vision_events": vision_events,
        "objectives": (
            [dict(item) for item in raw_objectives if isinstance(item, dict)]
            if isinstance(raw_objectives, (list, tuple)) else None
        ),
        "performance": {
            "lane_efficiency_pct": getattr(player, "lane_efficiency_pct", None),
            "teamfight_participation": getattr(player, "teamfight_participation", None),
            "life_state_dead": (
                observed_dead_seconds
                if observed_dead_seconds is not None
                else getattr(player, "life_state_dead", None)
            ),
            "buyback_count": getattr(player, "buyback_count", None),
        },
        "extended": {
            "stuns": getattr(player, "stuns_dealt", None),
            "damage_taken": mapping_payload(getattr(player, "damage_taken", None)),
            "obs_placed": getattr(player, "obs_placed", None),
            "sen_placed": getattr(player, "sen_placed", None),
            "camps_stacked": getattr(player, "camps_stacked", None),
            "rune_pickups": getattr(player, "rune_pickups", None),
            "courier_kills": getattr(player, "courier_kills", None),
            "observer_kills": getattr(player, "observer_kills", None),
            "sentry_kills": getattr(player, "sentry_kills", None),
            "tower_kills": getattr(player, "tower_kills", None),
            "roshan_kills": getattr(player, "roshan_kills", None),
            "buyback_count": getattr(player, "buyback_count", None),
            "gold_spent": getattr(player, "gold_spent", None),
            "total_gold": getattr(player, "total_gold", None),
            "hero_healing": getattr(player, "hero_healing", None),
            "item_uses": mapping_payload(getattr(player, "item_uses", None)),
            "ability_uses": mapping_payload(getattr(player, "ability_uses", None)),
        },
        "validation": {
            "status": validation_status,
            "checks": checks,
        },
    }


class ValveReplayClient:
    def __init__(self, session=None, parser_module=None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "cstd-help-replay/1.0"})
        self._parser_module = parser_module

    def _parser(self):
        if self._parser_module is None:
            try:
                self._parser_module = importlib.import_module("gem")
            except ImportError as exc:
                raise ReplayEvidenceError("REPLAY_PARSER_NOT_INSTALLED") from exc
        return self._parser_module

    def _download_and_decompress(self, replay_url, match_id, target_dir):
        compressed_path = Path(target_dir) / f"{int(match_id)}.dem.bz2"
        replay_path = Path(target_dir) / f"{int(match_id)}.dem"
        complete = False
        last_error = None
        for _attempt in range(REPLAY_DOWNLOAD_ATTEMPTS):
            existing_size = compressed_path.stat().st_size if compressed_path.exists() else 0
            request_headers = {"Range": f"bytes={existing_size}-"} if existing_size else {}
            response = None
            try:
                response = self.session.get(
                    replay_url,
                    stream=True,
                    timeout=(10, 180),
                    allow_redirects=False,
                    headers=request_headers,
                )
                response.raise_for_status()
                status_code = int(getattr(response, "status_code", 200) or 200)
                is_resume = bool(existing_size and status_code == 206)
                write_mode = "ab" if is_resume else "wb"
                base_size = existing_size if is_resume else 0

                content_length = response.headers.get("Content-Length")
                try:
                    response_size = int(content_length) if content_length else None
                except (TypeError, ValueError) as exc:
                    raise ReplayEvidenceError("REPLAY_CONTENT_LENGTH_INVALID") from exc
                content_range = response.headers.get("Content-Range") or ""
                range_match = re.fullmatch(r"bytes \d+-\d+/(\d+)", content_range)
                expected_size = (
                    int(range_match.group(1))
                    if range_match else base_size + response_size
                    if response_size is not None else None
                )
                if expected_size is not None and expected_size > MAX_COMPRESSED_REPLAY_BYTES:
                    raise ReplayEvidenceError("REPLAY_COMPRESSED_TOO_LARGE")

                compressed_size = base_size
                with compressed_path.open(write_mode) as output:
                    for chunk in response.iter_content(chunk_size=REPLAY_CHUNK_BYTES):
                        if not chunk:
                            continue
                        compressed_size += len(chunk)
                        if compressed_size > MAX_COMPRESSED_REPLAY_BYTES:
                            raise ReplayEvidenceError("REPLAY_COMPRESSED_TOO_LARGE")
                        output.write(chunk)

                complete = expected_size is None or compressed_size == expected_size
                if complete:
                    break
                last_error = ReplayEvidenceError("REPLAY_DOWNLOAD_INCOMPLETE")
            except requests.exceptions.HTTPError as exc:
                raise ReplayEvidenceError("REPLAY_HTTP_STATUS") from exc
            except ReplayEvidenceError:
                raise
            except requests.exceptions.RequestException as exc:
                last_error = exc
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()

        if not complete:
            raise ReplayEvidenceError("REPLAY_DOWNLOAD_INCOMPLETE") from last_error

        decompressed_size = 0
        try:
            with bz2.open(compressed_path, "rb") as source, replay_path.open("wb") as output:
                while True:
                    chunk = source.read(REPLAY_CHUNK_BYTES)
                    if not chunk:
                        break
                    decompressed_size += len(chunk)
                    if decompressed_size > MAX_DECOMPRESSED_REPLAY_BYTES:
                        raise ReplayEvidenceError("REPLAY_DECOMPRESSED_TOO_LARGE")
                    output.write(chunk)
        except (OSError, EOFError) as exc:
            raise ReplayEvidenceError("REPLAY_ARCHIVE_INVALID") from exc
        finally:
            compressed_path.unlink(missing_ok=True)
        if decompressed_size == 0:
            raise ReplayEvidenceError("REPLAY_EMPTY")
        return replay_path

    def get_match_evidence(self, match_id, account_id, match_detail):
        replay_url = replay_url_from_match(match_detail, match_id)
        target_player_id = _replay_player_id_from_match_detail(match_detail, account_id)
        parser = self._parser()
        with tempfile.TemporaryDirectory(prefix="cstd-replay-") as temp_dir:
            replay_path = self._download_and_decompress(
                replay_url,
                match_id,
                temp_dir,
            )
            parsed_match, player_state_snapshots = _parse_with_raw_assists(
                parser,
                replay_path,
                capture_player_snapshots=True,
                target_player_id=target_player_id,
            )
            parser_version = getattr(parser, "__version__", None)
            return build_replay_evidence(
                parsed_match,
                match_id=match_id,
                account_id=account_id,
                match_detail=match_detail,
                parser_version=parser_version,
                player_state_snapshots=player_state_snapshots,
            )
