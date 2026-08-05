import os
import json
import discord

def process_eew_event(cog, message: discord.Message, now_ts: float):
    """監視 EEW 通報頻道訊息，觸發全系統 3 分鐘連動暫停"""
    try:
        if os.path.exists('config.json'):
            with open('config.json', 'r', encoding='utf-8') as f:
                bot_config = json.load(f)
            eew_id = bot_config.get("EEW_CHANNEL_ID")
            if eew_id and message.channel.id == int(eew_id):
                cog.eew_pause_until = now_ts + 180.0
                print("⚡ [EEW模組] 收到 EEW 地震速報通報，全系統觸發 3 分鐘防護連動暫停。")
    except Exception as e:
        print(f"⚠️ [EEW模組] 處理地震速報觸發失敗: {e}")

def is_eew_paused(cog, now_ts: float, eew_pause_enabled: bool) -> bool:
    """檢查目前是否處於 EEW 地震暫停期"""
    return eew_pause_enabled and (now_ts < cog.eew_pause_until)
