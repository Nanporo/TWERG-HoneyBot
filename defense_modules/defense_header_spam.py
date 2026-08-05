import datetime
import discord

async def check_header_spam(cog, message: discord.Message, current_count: int) -> bool:
    """
    Markdown「#」大字體與連續樣式洗板防護
    當極新用戶使用大字體帶標註或連續使用大字體洗板時，刪除訊息並執行 3 天禁言。
    回傳 True 表示已有處置，跳過後續檢查。
    """
    author_id_str = str(message.author.id)
    is_header_format = any(line.strip().startswith('#') for line in (message.content or "").splitlines())
    user_headers = cog.user_header_history.get(author_id_str, [])
    user_headers.append(is_header_format)
    cog.user_header_history[author_id_str] = user_headers

    explicit_mentions = cog._get_explicit_mentions(message)
    is_early_header_mention = (current_count <= 2) and is_header_format and (len(explicit_mentions) > 0)
    is_consecutive_headers = len(user_headers) >= 2 and all(user_headers[-2:])

    if is_early_header_mention or is_consecutive_headers:
        try:
            await message.delete()
        except Exception:
            pass
        bot_member = message.guild.get_member(cog.bot.user.id) or await message.guild.fetch_member(cog.bot.user.id)
        if bot_member.guild_permissions.moderate_members and bot_member.top_role > message.author.top_role:
            try:
                reason = "新用戶使用 Markdown「#」大字體洗板與組合騷擾"
                await message.author.timeout(datetime.timedelta(days=3), reason=reason)
                await cog._send_kill_announcement(message.channel, message.author, "新用戶使用大字體洗板與組合騷擾", raw_content=message.content)
                print(f"🚨 [大字體洗板模組] 已禁言 3 天惡意用戶 {message.author} ({message.author.id}) - 理由: 大字體洗板")
            except Exception as e:
                print(f"⚠️ [大字體洗板模組] 處決大字體洗板用戶失敗: {e}")
        return True
    return False
