import datetime
import discord
from ryker_keywords import TARGET_USERS

async def check_target_users(cog, message: discord.Message) -> bool:
    """
    受害者與保護對象標記防護 (target_users)
    當未畢業新用戶於發言中顯式 @ 提及受害者或保護對象時，刪除訊息並執行 3 天禁言處決。
    回傳 True 表示已有處置，跳過後續檢查。
    """
    target_set = cog.get_target_users() if hasattr(cog, 'get_target_users') else TARGET_USERS
    explicit_mentions = cog._get_explicit_mentions(message)
    mentioned_target_count = sum(1 for user in explicit_mentions if user.id in target_set)
    
    if mentioned_target_count >= 1:
        try:
            await message.delete()
        except Exception:
            pass
        bot_member = message.guild.get_member(cog.bot.user.id) or await message.guild.fetch_member(cog.bot.user.id)
        if bot_member.guild_permissions.moderate_members and bot_member.top_role > message.author.top_role:
            try:
                reason = "新用戶前10筆訊息惡意標記保護對象/受害者（禁言3天等待管理員處置）"
                await message.author.timeout(datetime.timedelta(days=3), reason=reason)
                await cog._send_kill_announcement(message.channel, message.author, "新用戶於前10筆訊息內惡意標記保護對象/受害者", raw_content=message.content)
                print(f"🚨 [受害者標記模組] 已禁言 3 天惡意用戶 {message.author} ({message.author.id}) - 理由: 標記受害者/保護對象")
            except Exception as e:
                print(f"⚠️ [受害者標記模組] 處決標記受害者用戶失敗: {e}")
        return True
    return False
