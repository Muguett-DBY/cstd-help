import json
import sqlite3
import os
from config import DB_PATH, DATA_DIR


def get_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY,
            duration INTEGER,
            radiant_win INTEGER,
            start_time INTEGER,
            game_mode INTEGER,
            lobby_type INTEGER,
            radiant_score INTEGER,
            dire_score INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER,
            account_id INTEGER,
            hero_id INTEGER,
            player_slot INTEGER,
            is_radiant INTEGER,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            gold_per_min INTEGER,
            xp_per_min INTEGER,
            hero_damage INTEGER,
            tower_damage INTEGER,
            hero_healing INTEGER,
            last_hits INTEGER,
            denies INTEGER,
            level INTEGER,
            gold INTEGER,
            net_worth INTEGER,
            item_0 INTEGER,
            item_1 INTEGER,
            item_2 INTEGER,
            item_3 INTEGER,
            item_4 INTEGER,
            item_5 INTEGER,
            ability_upgrades TEXT,
            analyzed INTEGER DEFAULT 0,
            FOREIGN KEY (match_id) REFERENCES matches(match_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stratz_details (
            match_id INTEGER PRIMARY KEY,
            player_data TEXT,
            fetched_at INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS opendota_details (
            match_id INTEGER PRIMARY KEY,
            match_data TEXT,
            parse_job_id INTEGER,
            fetched_at INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_cache (
            match_id INTEGER PRIMARY KEY,
            report_html TEXT,
            analysis_data TEXT,
            created_at INTEGER
        )
    """)

    conn.commit()
    conn.close()


def save_match(match_data):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO matches
        (match_id, duration, radiant_win, start_time, game_mode, lobby_type,
         radiant_score, dire_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        match_data.get("match_id"),
        match_data.get("duration"),
        match_data.get("radiant_win"),
        match_data.get("start_time"),
        match_data.get("game_mode"),
        match_data.get("lobby_type"),
        match_data.get("radiant_score"),
        match_data.get("dire_score"),
    ))
    conn.commit()
    conn.close()


def save_player_match(pm_data):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM player_matches WHERE match_id = ? AND account_id = ?",
        (pm_data.get("match_id"), pm_data.get("account_id")),
    )
    cursor.execute("""
        INSERT INTO player_matches
        (match_id, account_id, hero_id, player_slot, is_radiant,
         kills, deaths, assists, gold_per_min, xp_per_min,
         hero_damage, tower_damage, hero_healing, last_hits, denies,
         level, gold, net_worth, item_0, item_1, item_2, item_3,
         item_4, item_5, ability_upgrades)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pm_data.get("match_id"),
        pm_data.get("account_id"),
        pm_data.get("hero_id"),
        pm_data.get("player_slot"),
        pm_data.get("is_radiant"),
        pm_data.get("kills"),
        pm_data.get("deaths"),
        pm_data.get("assists"),
        pm_data.get("gold_per_min"),
        pm_data.get("xp_per_min"),
        pm_data.get("hero_damage"),
        pm_data.get("tower_damage"),
        pm_data.get("hero_healing"),
        pm_data.get("last_hits"),
        pm_data.get("denies"),
        pm_data.get("level"),
        pm_data.get("gold"),
        pm_data.get("net_worth"),
        pm_data.get("item_0"),
        pm_data.get("item_1"),
        pm_data.get("item_2"),
        pm_data.get("item_3"),
        pm_data.get("item_4"),
        pm_data.get("item_5"),
        pm_data.get("ability_upgrades"),
    ))
    conn.commit()
    conn.close()


def save_stratz_detail(match_id, player_data_json):
    import time
    if not isinstance(player_data_json, str):
        player_data_json = json.dumps(player_data_json, ensure_ascii=False, default=str)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO stratz_details (match_id, player_data, fetched_at)
            VALUES (?, ?, ?)
        """, (match_id, player_data_json, int(time.time())))
        conn.commit()
    finally:
        conn.close()


def get_stratz_detail(match_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT player_data FROM stratz_details WHERE match_id = ?", (match_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row["player_data"]:
        return None
    try:
        return json.loads(row["player_data"])
    except (TypeError, json.JSONDecodeError):
        return None


def save_opendota_detail(match_id, match_data, parse_job_id=None):
    import time
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO opendota_details (match_id, match_data, parse_job_id, fetched_at)
        VALUES (?, ?, ?, ?)
    """, (
        match_id,
        json.dumps(match_data, ensure_ascii=False, default=str),
        parse_job_id,
        int(time.time()),
    ))
    conn.commit()
    conn.close()


def get_opendota_detail(match_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT match_data FROM opendota_details WHERE match_id = ?", (match_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row["match_data"]:
        return None
    try:
        return json.loads(row["match_data"])
    except (TypeError, json.JSONDecodeError):
        return None


def get_recent_matches_from_db(account_id, limit=20):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pm.*, m.duration, m.radiant_win, m.start_time,
               m.radiant_score, m.dire_score
        FROM player_matches pm
        JOIN matches m ON pm.match_id = m.match_id
        JOIN (
            SELECT match_id, account_id, MAX(id) AS max_id
            FROM player_matches
            WHERE account_id = ?
            GROUP BY match_id, account_id
        ) latest ON latest.max_id = pm.id
        WHERE pm.account_id = ?
        ORDER BY m.start_time DESC
        LIMIT ?
    """, (account_id, account_id, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def is_match_analyzed(match_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM player_matches WHERE match_id = ? AND analyzed = 1", (match_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def mark_match_analyzed(match_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE player_matches SET analyzed = 1 WHERE match_id = ?", (match_id,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
