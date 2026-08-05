import discord
import json
import os
import sqlite3

DB_GUILD_SETTINGS = 'guild_settings.db'
DB_SERVER_AUTHS = 'server_authorizations.db'

DEFAULT_GUILD_SETTINGS = {
    "monitor_threshold": 10,
    "bad_users_enabled": True,
    "target_users_enabled": True,
    "bad_words_enabled": True,
    "image_spam_enabled": True,
    "header_spam_enabled": True,
    "eew_pause_enabled": True,
    "global_monitor": False,
    "sync_ban": False,
    "excluded_roles": [],
    "trap_roles": [],
    "delete_messages": True,
    "log_channel_id": None
}

def load_json_file(filepath: str, default=None):
    if default is None:
        default = {}
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception:
        return default

def save_json_file(filepath: str, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"⚠️ 儲存檔案 {filepath} 失敗: {e}")

def load_config() -> dict:
    return load_json_file('config.json', {})

def _init_all_settings_dbs():
    """初始化 guild_settings.db 與 server_authorizations.db 並遷移舊版 JSON 資料"""
    try:
        # 1. 初始化 guild_settings.db
        with sqlite3.connect(DB_GUILD_SETTINGS) as conn:
            conn.cursor().execute("PRAGMA journal_mode=WAL;")
            conn.cursor().execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id TEXT PRIMARY KEY,
                    monitor_threshold INTEGER DEFAULT 10,
                    bad_users_enabled INTEGER DEFAULT 1,
                    target_users_enabled INTEGER DEFAULT 1,
                    bad_words_enabled INTEGER DEFAULT 1,
                    image_spam_enabled INTEGER DEFAULT 1,
                    header_spam_enabled INTEGER DEFAULT 1,
                    eew_pause_enabled INTEGER DEFAULT 1,
                    global_monitor INTEGER DEFAULT 0,
                    sync_ban INTEGER DEFAULT 0,
                    excluded_roles TEXT DEFAULT '[]',
                    trap_roles TEXT DEFAULT '[]',
                    delete_messages INTEGER DEFAULT 1,
                    log_channel_id TEXT DEFAULT NULL
                )
            """)
            conn.commit()

        # 2. 初始化 server_authorizations.db
        with sqlite3.connect(DB_SERVER_AUTHS) as conn:
            conn.cursor().execute("PRAGMA journal_mode=WAL;")
            conn.cursor().execute("""
                CREATE TABLE IF NOT EXISTS server_authorizations (
                    guild_id TEXT PRIMARY KEY,
                    authorized INTEGER DEFAULT 0,
                    updated_at TEXT,
                    updated_by TEXT,
                    authorized_at TEXT,
                    authorized_by TEXT
                )
            """)
            conn.commit()

        _migrate_legacy_json_files()
    except Exception as e:
        print(f"⚠️ [DB] 初始化設定資料庫失敗: {e}")

def _migrate_legacy_json_files():
    """若存在舊版 JSON 檔 (ryker_settings.json, honeypot_settings.json, server_authorizations.json)，將數據遷移至 SQLite (僅於尚未寫入 DB 時遷移，不覆蓋既有設定)"""
    # 1. 遷移 ryker_settings.json & honeypot_settings.json -> guild_settings.db
    ryker_json = load_json_file('ryker_settings.json', {})
    hp_json = load_json_file('honeypot_settings.json', {})

    if ryker_json or hp_json:
        all_guild_ids = set(ryker_json.keys()) | set(hp_json.keys())
        with sqlite3.connect(DB_GUILD_SETTINGS) as conn:
            cursor = conn.cursor()
            for gid in all_guild_ids:
                rdata = ryker_json.get(gid, {})
                hdata = hp_json.get(gid, {})

                if isinstance(hdata, list):
                    hdata = {"excluded_roles": hdata}

                threshold = rdata.get("monitor_threshold", 10)
                bad_users = 1 if rdata.get("bad_users_enabled", True) else 0
                target_users = 1 if rdata.get("target_users_enabled", True) else 0
                bad_words = 1 if rdata.get("bad_words_enabled", True) else 0
                img_spam = 1 if rdata.get("image_spam_enabled", True) else 0
                header_spam = 1 if rdata.get("header_spam_enabled", True) else 0
                eew_pause = 1 if rdata.get("eew_pause_enabled", True) else 0
                global_mon = 1 if rdata.get("global_monitor", False) else 0
                sync_ban = 1 if rdata.get("sync_ban", False) else 0

                excluded_roles = json.dumps(hdata.get("excluded_roles", []))
                trap_roles = json.dumps(hdata.get("trap_roles", []))
                del_msg = 1 if hdata.get("delete_messages", True) else 0
                log_ch = str(hdata.get("log_channel_id")) if hdata.get("log_channel_id") else None

                cursor.execute("""
                    INSERT INTO guild_settings (
                        guild_id, monitor_threshold, bad_users_enabled, target_users_enabled,
                        bad_words_enabled, image_spam_enabled, header_spam_enabled,
                        eew_pause_enabled, global_monitor, sync_ban,
                        excluded_roles, trap_roles, delete_messages, log_channel_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO NOTHING
                """, (
                    gid, threshold, bad_users, target_users, bad_words, img_spam,
                    header_spam, eew_pause, global_mon, sync_ban,
                    excluded_roles, trap_roles, del_msg, log_ch
                ))
            conn.commit()

    # 2. 遷移 server_authorizations.json -> server_authorizations.db
    auths_json = load_json_file('server_authorizations.json', {})
    if auths_json:
        with sqlite3.connect(DB_SERVER_AUTHS) as conn:
            cursor = conn.cursor()
            for gid, adata in auths_json.items():
                if not isinstance(adata, dict):
                    continue
                auth_val = 1 if adata.get("authorized", False) else 0
                updated_at = adata.get("updated_at")
                updated_by = adata.get("updated_by")
                authorized_at = adata.get("authorized_at")
                authorized_by = adata.get("authorized_by")

                cursor.execute("""
                    INSERT INTO server_authorizations (
                        guild_id, authorized, updated_at, updated_by, authorized_at, authorized_by
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO NOTHING
                """, (gid, auth_val, updated_at, updated_by, authorized_at, authorized_by))
            conn.commit()

def load_guild_settings(guild_id: int) -> dict:
    """讀取特定伺服器的設定檔"""
    gid_str = str(guild_id)
    _init_all_settings_dbs()
    try:
        with sqlite3.connect(DB_GUILD_SETTINGS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT monitor_threshold, bad_users_enabled, target_users_enabled,
                       bad_words_enabled, image_spam_enabled, header_spam_enabled,
                       eew_pause_enabled, global_monitor, sync_ban,
                       excluded_roles, trap_roles, delete_messages, log_channel_id
                FROM guild_settings WHERE guild_id = ?
            """, (gid_str,))
            row = cursor.fetchone()
            if row:
                return {
                    "monitor_threshold": row[0],
                    "bad_users_enabled": bool(row[1]),
                    "target_users_enabled": bool(row[2]),
                    "bad_words_enabled": bool(row[3]),
                    "image_spam_enabled": bool(row[4]),
                    "header_spam_enabled": bool(row[5]),
                    "eew_pause_enabled": bool(row[6]),
                    "global_monitor": bool(row[7]),
                    "sync_ban": bool(row[8]),
                    "excluded_roles": json.loads(row[9] or '[]'),
                    "trap_roles": json.loads(row[10] or '[]'),
                    "delete_messages": bool(row[11]),
                    "log_channel_id": row[12]
                }
    except Exception as e:
        print(f"⚠️ [DB] 讀取 guild_settings 失敗 (Guild: {guild_id}): {e}")
    return DEFAULT_GUILD_SETTINGS.copy()

def load_all_guild_settings() -> dict:
    """讀取全伺服器的設定檔集合 (以 string guild_id 為 key)"""
    _init_all_settings_dbs()
    all_res = {}
    try:
        with sqlite3.connect(DB_GUILD_SETTINGS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT guild_id, monitor_threshold, bad_users_enabled, target_users_enabled,
                       bad_words_enabled, image_spam_enabled, header_spam_enabled,
                       eew_pause_enabled, global_monitor, sync_ban,
                       excluded_roles, trap_roles, delete_messages, log_channel_id
                FROM guild_settings
            """)
            for row in cursor.fetchall():
                all_res[row[0]] = {
                    "monitor_threshold": row[1],
                    "bad_users_enabled": bool(row[2]),
                    "target_users_enabled": bool(row[3]),
                    "bad_words_enabled": bool(row[4]),
                    "image_spam_enabled": bool(row[5]),
                    "header_spam_enabled": bool(row[6]),
                    "eew_pause_enabled": bool(row[7]),
                    "global_monitor": bool(row[8]),
                    "sync_ban": bool(row[9]),
                    "excluded_roles": json.loads(row[10] or '[]'),
                    "trap_roles": json.loads(row[11] or '[]'),
                    "delete_messages": bool(row[12]),
                    "log_channel_id": row[13]
                }
    except Exception as e:
        print(f"⚠️ [DB] 讀取全域 guild_settings 失敗: {e}")
    return all_res

def save_guild_settings(guild_id: int, settings: dict):
    """儲存單一伺服器的設定至 guild_settings.db"""
    gid_str = str(guild_id)
    _init_all_settings_dbs()
    try:
        with sqlite3.connect(DB_GUILD_SETTINGS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO guild_settings (
                    guild_id, monitor_threshold, bad_users_enabled, target_users_enabled,
                    bad_words_enabled, image_spam_enabled, header_spam_enabled,
                    eew_pause_enabled, global_monitor, sync_ban,
                    excluded_roles, trap_roles, delete_messages, log_channel_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    monitor_threshold=excluded.monitor_threshold,
                    bad_users_enabled=excluded.bad_users_enabled,
                    target_users_enabled=excluded.target_users_enabled,
                    bad_words_enabled=excluded.bad_words_enabled,
                    image_spam_enabled=excluded.image_spam_enabled,
                    header_spam_enabled=excluded.header_spam_enabled,
                    eew_pause_enabled=excluded.eew_pause_enabled,
                    global_monitor=excluded.global_monitor,
                    sync_ban=excluded.sync_ban,
                    excluded_roles=excluded.excluded_roles,
                    trap_roles=excluded.trap_roles,
                    delete_messages=excluded.delete_messages,
                    log_channel_id=excluded.log_channel_id
            """, (
                gid_str,
                settings.get("monitor_threshold", 10),
                1 if settings.get("bad_users_enabled", True) else 0,
                1 if settings.get("target_users_enabled", True) else 0,
                1 if settings.get("bad_words_enabled", True) else 0,
                1 if settings.get("image_spam_enabled", True) else 0,
                1 if settings.get("header_spam_enabled", True) else 0,
                1 if settings.get("eew_pause_enabled", True) else 0,
                1 if settings.get("global_monitor", False) else 0,
                1 if settings.get("sync_ban", False) else 0,
                json.dumps(settings.get("excluded_roles", [])),
                json.dumps(settings.get("trap_roles", [])),
                1 if settings.get("delete_messages", True) else 0,
                str(settings.get("log_channel_id")) if settings.get("log_channel_id") else None
            ))
            conn.commit()
    except Exception as e:
        print(f"⚠️ [DB] 儲存 guild_settings 失敗 (Guild: {guild_id}): {e}")

# 相容舊 API
load_honeypot_settings = load_all_guild_settings
load_ryker_settings = load_all_guild_settings
def save_honeypot_settings(data: dict):
    for k, v in data.items():
        save_guild_settings(int(k), v)
def save_ryker_settings(data: dict):
    for k, v in data.items():
        save_guild_settings(int(k), v)

def load_server_authorizations() -> dict:
    """讀取全伺服器授權狀態資料庫"""
    _init_all_settings_dbs()
    res = {}
    try:
        with sqlite3.connect(DB_SERVER_AUTHS) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT guild_id, authorized, updated_at, updated_by, authorized_at, authorized_by FROM server_authorizations")
            for row in cursor.fetchall():
                res[row[0]] = {
                    "authorized": bool(row[1]),
                    "updated_at": row[2],
                    "updated_by": row[3],
                    "authorized_at": row[4],
                    "authorized_by": row[5]
                }
    except Exception as e:
        print(f"⚠️ [DB] 讀取 server_authorizations 失敗: {e}")
    return res

def save_server_authorizations(data: dict):
    """將全伺服器授權狀態寫入 server_authorizations.db"""
    _init_all_settings_dbs()
    try:
        with sqlite3.connect(DB_SERVER_AUTHS) as conn:
            cursor = conn.cursor()
            for gid, adata in data.items():
                if not isinstance(adata, dict):
                    continue
                cursor.execute("""
                    INSERT INTO server_authorizations (
                        guild_id, authorized, updated_at, updated_by, authorized_at, authorized_by
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        authorized=excluded.authorized,
                        updated_at=excluded.updated_at,
                        updated_by=excluded.updated_by,
                        authorized_at=excluded.authorized_at,
                        authorized_by=excluded.authorized_by
                """, (
                    str(gid),
                    1 if adata.get("authorized", False) else 0,
                    adata.get("updated_at"),
                    adata.get("updated_by"),
                    adata.get("authorized_at"),
                    adata.get("authorized_by")
                ))
            conn.commit()
    except Exception as e:
        print(f"⚠️ [DB] 儲存 server_authorizations 失敗: {e}")

def is_server_authorized(guild_id: int) -> bool:
    """查詢單一伺服器是否擁有機器人授權權限"""
    config = load_config()
    twerg_id = config.get("TWERG_SERVER_ID") or config.get("SERVER_ID", 518699949500661760)
    if twerg_id and int(guild_id) == int(twerg_id):
        return True

    _init_all_settings_dbs()
    try:
        with sqlite3.connect(DB_SERVER_AUTHS) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT authorized FROM server_authorizations WHERE guild_id = ?", (str(guild_id),))
            row = cursor.fetchone()
            if row:
                return bool(row[0])
    except Exception as e:
        print(f"⚠️ [DB] 查詢伺服器授權失敗 (Guild: {guild_id}): {e}")
    return False

async def send_server_log(guild: discord.Guild, embed: discord.Embed, view: discord.ui.View = None):
    """將伺服器專屬防護紀錄發送至該伺服器自訂的 log_channel_id"""
    if not guild:
        return
    try:
        settings = load_guild_settings(guild.id)
        log_ch_id = settings.get("log_channel_id")
        if log_ch_id:
            ch = guild.get_channel(int(log_ch_id))
            if ch:
                if view:
                    await ch.send(embed=embed, view=view)
                else:
                    await ch.send(embed=embed)
    except Exception as e:
        print(f"⚠️ [ServerLog] 發送伺服器日誌失敗 (Guild: {guild.name}): {e}")

async def setup(bot):
    pass