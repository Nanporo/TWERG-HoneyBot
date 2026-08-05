import discord
from discord.ext import commands
import json
import os
from settings.settings_utils import send_server_log

class HoneypotCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings_file = 'honeypot_settings.json'
        
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.honeypot_channel_id = int(config.get('HONEYPOT_ID', 1512064831912411246))
            self.twerg_server_id = int(config.get('TWERG_SERVER_ID') or config.get('SERVER_ID', 518699949500661760))
        except Exception:
            self.honeypot_channel_id = 1512064831912411246
            self.twerg_server_id = 518699949500661760

    def get_settings(self, guild_id):
        default_settings = {
            "excluded_roles": [],
            "delete_messages": True
        }
        if not os.path.exists(self.settings_file):
            return default_settings
            
        with open(self.settings_file, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                guild_data = data.get(str(guild_id), {})
                if isinstance(guild_data, list):
                    migrated = default_settings.copy()
                    migrated["excluded_roles"] = guild_data
                    return migrated
                for k, v in default_settings.items():
                    if k not in guild_data:
                        guild_data[k] = v
                return guild_data
            except json.JSONDecodeError:
                return default_settings

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        # 蜜罐防護為 TWERG 伺服器專屬功能
        if message.guild.id != self.twerg_server_id:
            return

        # 僅限於蜜罐頻道內觸發
        if message.channel.id != self.honeypot_channel_id:
            return

        settings = self.get_settings(message.guild.id)
        excluded_roles = settings.get("excluded_roles", [])

        has_excluded_role = any(role.id in excluded_roles for role in message.author.roles)
        is_immune = (
            has_excluded_role or 
            message.author.guild_permissions.administrator or
            message.author.top_role >= message.guild.me.top_role
        )
        if is_immune:
            return

        try:
            warning_msg = f"有人（{message.author.mention}）在蜜罐裡面發送訊息了！\n如果你和他一樣在這裡發訊息，你就會一起飛出去！請勿作死！"
            embed = discord.Embed(description=warning_msg, color=discord.Color.red())
            embed.set_image(url="https://raw.githubusercontent.com/Nanporo/TWERG-HoneyBot/main/photos/jinggao.png")
            await message.channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ [Honeypot] 無法在蜜罐頻道發送警告圖片與訊息: {e}")

        bot_member = message.guild.get_member(self.bot.user.id) or await message.guild.fetch_member(self.bot.user.id)
        if not bot_member.guild_permissions.ban_members or bot_member.top_role <= message.author.top_role:
            print(f"⚠️ [蜜罐防護 - 權限不足] 伺服器: {message.guild.name} ({message.guild.id}) | 頻道: {message.channel.name} | 被操作人: {message.author} ({message.author.id})")
            return
        try:
            delete_seconds = 1800 if settings.get("delete_messages", True) else 0
            await message.author.ban(reason="觸發蜜罐頻道防護機制", delete_message_seconds=delete_seconds)
            print(f"🚨 [蜜罐防護 - 自動BAN] 伺服器: {message.guild.name} ({message.guild.id}) | 頻道: #{message.channel.name} ({message.channel.id}) | 被操作人: {message.author} ({message.author.id}) | 操作人: [系統自動]")
            
            embed_log = discord.Embed(
                description=(
                    f"🚨 **[蜜罐防護] 觸發自動 BAN**\n\n"
                    f"• **處置用戶**：{message.author.mention} (`{message.author.id}`)\n"
                    f"• **處置頻道**：{message.channel.mention}\n"
                    f"• **原因**：於蜜罐頻道內發送訊息\n"
                    f"• **刪除訊息**：{'近 30 分鐘' if delete_seconds > 0 else '否'}"
                ),
                color=discord.Color.red()
            )
            embed_log.set_footer(text="TWERG HoneyBot - 伺服器防護日誌")
            await send_server_log(message.guild, embed_log)
        except discord.Forbidden:
            print(f"⚠️ [蜜罐防護 - 權限不足] 伺服器: {message.guild.name} ({message.guild.id}) | 被操作人: {message.author} ({message.author.id})")
        except discord.HTTPException as e:
            print(f"⚠️ [蜜罐防護 - HTTP錯誤] 伺服器: {message.guild.name} ({message.guild.id}) | 錯誤: {e}")

async def setup(bot):
    await bot.add_cog(HoneypotCog(bot))