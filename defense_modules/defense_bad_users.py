import datetime
import discord

async def check_bad_users(cog, message: discord.Message, bad_users_set: set[int]) -> bool:
    """
    惡意破壞者黑名單比對 (bad_users)
    若匹配成功則自動刪除訊息、執行 3 天禁言並發送處決通報卡片。
    回傳 True 表示已有處置，跳過後續檢查。
    """
    if message.author.id in bad_users_set:
        try:
            await message.delete()
        except Exception:
            pass
        bot_member = message.guild.get_member(cog.bot.user.id) or await message.guild.fetch_member(cog.bot.user.id)
        if bot_member.guild_permissions.moderate_members and bot_member.top_role > message.author.top_role:
            try:
                duration = datetime.timedelta(days=3)
                await message.author.timeout(duration, reason="匹配至 Ryker 惡意破壞者黑名單帳號 (bad_users)")
                await cog._send_kill_announcement(message.channel, message.author, "匹配至 Ryker 惡意破壞者黑名單帳號", message.content)
                print(f"🚨 [黑名單模組] 已將惡意破壞者用戶 {message.author} ({message.author.id}) 執行 3 天禁言。")
            except Exception as e:
                print(f"⚠️ [黑名單模組] 處決黑名單用戶失敗: {e}")
        return True
    return False
