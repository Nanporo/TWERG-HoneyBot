import discord
import json
import os

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

def load_honeypot_settings() -> dict:
    return load_json_file('honeypot_settings.json', {})

def save_honeypot_settings(data: dict):
    save_json_file('honeypot_settings.json', data)

def load_ryker_settings() -> dict:
    return load_json_file('ryker_settings.json', {})

def save_ryker_settings(data: dict):
    save_json_file('ryker_settings.json', data)

def load_config() -> dict:
    return load_json_file('config.json', {})

def is_server_authorized(guild_id: int) -> bool:
    config = load_config()
    twerg_id = config.get("TWERG_SERVER_ID") or config.get("SERVER_ID", 518699949500661760)
    if twerg_id and int(guild_id) == int(twerg_id):
        return True

    auths = load_json_file('server_authorizations.json', {})
    g_info = auths.get(str(guild_id), {})
    return g_info.get("authorized", False)

async def send_server_log(guild: discord.Guild, embed: discord.Embed, view: discord.ui.View = None):
    """將伺服器專屬防護紀錄 (如蜜罐自動BAN、陷阱身份組、黑名單處決與聯防同步BAN) 發送至該伺服器自訂的 log_channel_id"""
    if not guild:
        return
    try:
        settings = load_honeypot_settings()
        g_data = settings.get(str(guild.id), {})
        log_ch_id = g_data.get("log_channel_id")
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