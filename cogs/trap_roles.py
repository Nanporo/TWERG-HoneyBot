import discord
from discord.ext import commands
import json
import os
from settings.settings_utils import send_server_log, load_guild_settings

class TrapRolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_settings(self, guild_id):
        return load_guild_settings(guild_id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        if not message.role_mentions:
            return

        settings = self.get_settings(message.guild.id)
        trap_roles = settings.get("trap_roles", [])
        
        mentioned_trap_roles = [role for role in message.role_mentions if role.id in trap_roles]
        if not mentioned_trap_roles:
            return

        excluded_roles = settings.get("excluded_roles", [])

        has_excluded_role = any(role.id in excluded_roles for role in message.author.roles)
        is_immune = (
            has_excluded_role or 
            message.author.guild_permissions.administrator or
            message.author.top_role >= message.guild.me.top_role
        )
        if is_immune:
            return

        role = mentioned_trap_roles[0]
        reason = f"惡意標註陷阱身份組 (@{role.name})"

        bot_member = message.guild.get_member(self.bot.user.id) or await message.guild.fetch_member(self.bot.user.id)
        if not bot_member.guild_permissions.ban_members or bot_member.top_role <= message.author.top_role:
            print(f"⚠️ [陷阱身份組 - 權限不足] 伺服器: {message.guild.name} ({message.guild.id}) | 被操作人: {message.author} ({message.author.id})")
            return

        try:
            delete_seconds = 1800 if settings.get("delete_messages", True) else 0
            await message.author.ban(reason=reason, delete_message_seconds=delete_seconds)
            print(f"🚨 [陷阱身份組 - 自動BAN] 伺服器: {message.guild.name} ({message.guild.id}) | 頻道: #{message.channel.name} ({message.channel.id}) | 被操作人: {message.author} ({message.author.id}) | 標註身份組: @{role.name} | 操作人: [系統自動]")
            
            embed_log = discord.Embed(
                description=(
                    f"🚨 **[陷阱身份組] 觸發自動 BAN**\n\n"
                    f"• **處置用戶**：{message.author.mention} (`{message.author.id}`)\n"
                    f"• **處置頻道**：{message.channel.mention}\n"
                    f"• **原因**：標記陷阱身份組 `@{role.name}`\n"
                    f"• **刪除訊息**：{'近 30 分鐘' if delete_seconds > 0 else '否'}"
                ),
                color=discord.Color.red()
            )
            embed_log.set_footer(text="TWERG HoneyBot - 伺服器防護日誌")
            await send_server_log(message.guild, embed_log)
        except discord.Forbidden:
            print(f"⚠️ [陷阱身份組 - 權限不足] 伺服器: {message.guild.name} ({message.guild.id}) | 被操作人: {message.author} ({message.author.id})")
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            print(f"⚠️ [陷阱身份組 - HTTP錯誤] 伺服器: {message.guild.name} ({message.guild.id}) | 錯誤: {e}")

async def setup(bot):
    await bot.add_cog(TrapRolesCog(bot))