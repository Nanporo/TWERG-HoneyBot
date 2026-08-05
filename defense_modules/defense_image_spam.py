import datetime
import discord

async def check_image_spam(cog, message: discord.Message, now_ts: float) -> bool:
    """
    短時間圖片/附件洗板防護 (60 秒內發送 5 則圖片/附件)
    觸發時刪除訊息並執行 1 小時禁言處置。
    回傳 True 表示已有處置，跳過後續檢查。
    """
    author_id_str = str(message.author.id)
    has_attachments = len(message.attachments) > 0
    user_img_history = cog.user_img_history.get(author_id_str, [])
    user_img_history = [t for t in user_img_history if now_ts - t <= 60]
    
    if has_attachments:
        user_img_history.append(now_ts)
        cog.user_img_history[author_id_str] = user_img_history

    if len(user_img_history) >= 5:
        try:
            await message.delete()
        except Exception:
            pass
        bot_member = message.guild.get_member(cog.bot.user.id) or await message.guild.fetch_member(cog.bot.user.id)
        if bot_member.guild_permissions.moderate_members and bot_member.top_role > message.author.top_role:
            try:
                reason_text = "新用戶 60 秒內連續發送 5 則圖片/附件訊息洗板"
                await message.author.timeout(datetime.timedelta(hours=1), reason=reason_text)
                await cog._send_timeout_announcement(message.channel, message.author, reason_text, raw_content=message.content)
                print(f"🛑 [圖片洗板模組] 已禁言圖片洗板用戶 {message.author} ({message.author.id}) 1小時 - 理由: {reason_text}")
            except Exception as e:
                print(f"⚠️ [圖片洗板模組] 禁言圖片洗板用戶失敗: {e}")
        return True
    return False
