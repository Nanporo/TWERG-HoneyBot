import datetime
import difflib
import discord
from ryker_keywords import (
    BAD_WORDS,
    REGEX_PATTERNS,
    NICKNAME_EXCLUDED_WORDS,
    EXEMPTED_INTERJECTIONS
)

def normalize_text(text: str) -> str:
    """歸一化文字：全角轉半角、大寫轉小寫、繁體轉簡體並剔除雜訊"""
    if not text:
        return ""
    # 全角轉半角
    res = []
    for char in text:
        code = ord(char)
        if code == 12288: # 全角空格
            res.append(' ')
        elif 65281 <= code <= 65374: # 全角英數標點
            res.append(chr(code - 65248))
        else:
            res.append(char)
    s = "".join(res).lower()
    
    # 簡易繁簡轉換表 (常見關鍵字)
    t2s = {
        '幹': '干', '驚': '惊', '爆': '爆', '炸': '炸', '彈': '弹',
        '殺': '杀', '死': '死', '爛': '烂', '賤': '贱', '雞': '鸡'
    }
    for t_char, s_char in t2s.items():
        s = s.replace(t_char, s_char)
    return s

async def check_bad_words(cog, message: discord.Message) -> bool:
    """
    敏感詞彙與組合正則特徵比對 (bad_words / REGEX_PATTERNS)
    比對範圍：靜態 BAD_WORDS + 動態自訂詞庫 (custom_bad_words DB)
    匹配成功時刪除訊息並執行 3 天禁言處決。
    回傳 True 表示已有處置，跳過後續檢查。
    """
    from settings.settings_utils import get_custom_bad_words

    raw_content = message.content or ""
    norm_content = normalize_text(raw_content)

    # 合併靜態底層詞庫 + 動態自訂詞庫（GLOBAL + 本伺服器）
    dynamic_words = get_custom_bad_words(str(message.guild.id))
    all_words = list(BAD_WORDS) + dynamic_words

    # 1. 關鍵字比對 (all_words)
    matched_word = None
    for bw in all_words:
        if bw in raw_content or bw in norm_content:
            matched_word = bw
            break

    # 2. 組合式正則比對 (REGEX_PATTERNS)
    matched_regex = None
    if not matched_word:
        for pattern in REGEX_PATTERNS:
            if pattern.search(raw_content) or pattern.search(norm_content):
                matched_regex = pattern.pattern
                break

    if matched_word or matched_regex:
        try:
            await message.delete()
        except Exception:
            pass
        bot_member = message.guild.get_member(cog.bot.user.id) or await message.guild.fetch_member(cog.bot.user.id)
        if bot_member.guild_permissions.moderate_members and bot_member.top_role > message.author.top_role:
            try:
                reason = f"匹配至違規敏感詞彙或特徵正則 ({matched_word or '組合正則特徵'})"
                await message.author.timeout(datetime.timedelta(days=3), reason=reason)
                await cog._send_kill_announcement(message.channel, message.author, f"發言匹配至違規敏感詞/正則 ({matched_word or '正則特徵'})", raw_content=raw_content)
                print(f"🚨 [敏感詞模組] 已禁言 3 天違規用戶 {message.author} ({message.author.id}) - 匹配詞: {matched_word or matched_regex}")
            except Exception as e:
                print(f"⚠️ [敏感詞模組] 處決違規用戶失敗: {e}")
        return True
    return False

