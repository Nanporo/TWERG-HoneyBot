import discord
from discord.ext import commands
import json
import os

class TrapRolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings_file = 'honeypot_settings.json'
        self.default_excluded_role = 518700481011253269

    def get_settings(self, guild_id):
        default_settings = {
            "excluded_roles": [],
            "trap_roles": [],
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

        if not message.role_mentions:
            return

        settings = self.get_settings(message.guild.id)
        trap_roles = settings.get("trap_roles", [])
        
        mentioned_trap_roles = [role for role in message.role_mentions if role.id in trap_roles]
        if not mentioned_trap_roles:
            return

        excluded_roles = settings.get("excluded_roles", [])
        excluded_roles.append(self.default_excluded_role)

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

        try:
            delete_seconds = 1800 if settings.get("delete_messages", True) else 0
            await message.author.ban(reason=reason, delete_message_seconds=delete_seconds)
            print(f"🚨 [TrapRoles] 已封鎖惡意用戶 {message.author} ({message.author.id}) - 原因: {reason}")
        except discord.Forbidden:
            print(f"⚠️ [TrapRoles] 機器人權限不足，無法封鎖用戶 {message.author}。")
        except discord.NotFound:
            # 若已經被其他防護模組封鎖而找不到該成員，忽略此報錯以避免洗版
            pass
        except discord.HTTPException as e:
            print(f"⚠️ [TrapRoles] 封鎖用戶時發生 HTTP 錯誤: {e}")

async def setup(bot):
    await bot.add_cog(TrapRolesCog(bot))