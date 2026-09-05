import datetime
import re
import unicodedata
import discord

def is_pure_symbols_or_emojis(text: str) -> bool:
    """
    判定訊息是否純由符號、標點符號、空白、Unicode 表情或 Discord 自訂表情組成。
    若完全不含文字或數字（中英文字母、數字、CJK 字元），回傳 True。
    """
    if not text:
        return True
    # 去除 Discord 自訂表情，例如 <:name:12345678> 或 <a:name:12345678>
    cleaned = re.sub(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', '', text)
    # 檢查是否含有任何 Letter (L) 或 Number (N) 類別的字元
    return not any(unicodedata.category(ch)[0] in ('L', 'N') for ch in cleaned)

async def check_rapid_flood(cog, message: discord.Message, now_ts: float, is_new_user: bool = True) -> bool:
    """
    短時間高頻發言保護：僅限未畢業新用戶，5 秒內發送超過 3 則訊息，直接判定為惡意灌水洗板。
    處分：不刪除訊息，處以 1 小時禁言。
    回傳 True 表示已有處置，跳過後續檢查。
    """
    if not is_new_user:
        return False

    author_id_str = str(message.author.id)
    if not hasattr(cog, 'user_msg_timestamps'):
        cog.user_msg_timestamps = {}

    timestamps = cog.user_msg_timestamps.get(author_id_str, [])
    # 保留 5 秒內的發言紀錄
    timestamps = [t for t in timestamps if now_ts - t <= 5.0]
    timestamps.append(now_ts)
    cog.user_msg_timestamps[author_id_str] = timestamps

    if len(timestamps) > 3:
        # 重置計數以避免重複觸發
        cog.user_msg_timestamps[author_id_str] = []
        bot_member = message.guild.get_member(cog.bot.user.id) or await message.guild.fetch_member(cog.bot.user.id)
        if bot_member.guild_permissions.moderate_members and bot_member.top_role > message.author.top_role:
            try:
                reason_text = "新用戶短時間高頻發言洗板（5 秒內發送超過 3 則訊息）"
                await message.author.timeout(datetime.timedelta(hours=1), reason=reason_text)
                await cog._send_timeout_announcement(message.channel, message.author, reason_text, raw_content=message.content)
                print(f"🛑 [高頻發言模組] 已禁言惡意灌水新用戶 {message.author} ({message.author.id}) 1 小時 - 理由: {reason_text}")
            except Exception as e:
                print(f"⚠️ [高頻發言模組] 禁言用戶失敗: {e}")
        return True
    return False

async def check_duplicate_spam(cog, message: discord.Message, now_ts: float, is_new_user: bool) -> bool:
    """
    重複內容比對：新用戶在 30 秒內連續發送相同內容，判定為重複洗板。
    處分：不刪除訊息，處以 1 小時禁言。
    回傳 True 表示已有處置，跳過後續檢查。
    """
    if not is_new_user:
        return False

    raw_content = (message.content or "").strip()
    if not raw_content:
        return False

    author_id_str = str(message.author.id)
    if not hasattr(cog, 'user_last_msg'):
        cog.user_last_msg = {}

    last_record = cog.user_last_msg.get(author_id_str)
    if last_record:
        last_ts, last_content = last_record
        if (now_ts - last_ts <= 30.0) and (raw_content == last_content):
            # 重置該用戶的上一則訊息記錄
            cog.user_last_msg.pop(author_id_str, None)
            bot_member = message.guild.get_member(cog.bot.user.id) or await message.guild.fetch_member(cog.bot.user.id)
            if bot_member.guild_permissions.moderate_members and bot_member.top_role > message.author.top_role:
                try:
                    reason_text = "新用戶在 30 秒內連續發送相同內容重複洗板"
                    await message.author.timeout(datetime.timedelta(hours=1), reason=reason_text)
                    await cog._send_timeout_announcement(message.channel, message.author, reason_text, raw_content=message.content)
                    print(f"🛑 [重複內容模組] 已禁言重複洗板用戶 {message.author} ({message.author.id}) 1 小時 - 理由: {reason_text}")
                except Exception as e:
                    print(f"⚠️ [重複內容模組] 禁言用戶失敗: {e}")
            return True

    cog.user_last_msg[author_id_str] = (now_ts, raw_content)
    return False
