import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import json
import os
from cogs.server_check import is_server_authorized

from settings.settings_utils import load_guild_settings

class CountsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_counts = 'counts.db'
        self.db_archive = 'counts_archive.db'

    def get_guild_settings(self, guild_id: int) -> dict:
        return load_guild_settings(guild_id)

    @app_commands.command(name="發言統計", description="[管理員] 查看本伺服器目前的防護與發言統計")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def counts_command(self, interaction: discord.Interaction):
        if not is_server_authorized(interaction.guild_id):
            await interaction.response.send_message("❌ 本伺服器尚未獲得機器人擁有者授權許可，無法使用此指令。", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 你沒有權限使用此指令！", ephemeral=True)
            return

        gid_str = str(interaction.guild_id)
        g_settings = self.get_guild_settings(interaction.guild_id)
        threshold = g_settings.get("monitor_threshold", 10)
        lurker_monitor = g_settings.get("global_monitor", False)

        pending_count = 0
        completed_count = 0
        pending_rows = []

        try:
            if os.path.exists(self.db_counts):
                with sqlite3.connect(self.db_counts) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM message_counts WHERE guild_id = ?", (gid_str,))
                    pending_count = cursor.fetchone()[0]

                    cursor.execute(
                        "SELECT user_id, count FROM message_counts WHERE guild_id = ? ORDER BY count DESC LIMIT 30", 
                        (gid_str,)
                    )
                    pending_rows = cursor.fetchall()

            if os.path.exists(self.db_archive):
                with sqlite3.connect(self.db_archive) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM message_counts_archive WHERE guild_id = ?", (gid_str,))
                    completed_count = cursor.fetchone()[0]
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢資料庫時發生錯誤: {e}", ephemeral=True)
            return

        status_str = "`🟢` 已開啟 (包含潛水舊成員)" if lurker_monitor else "`🔴` 已停用 (僅限新帳號/新成員)"

        summary_header = (
            f"**潛水用戶監控**：{status_str}\n"
            f"**伺服器發言監控門檻**：`{threshold}` 次\n"
            f"───────────────────────────\n"
            f"**本伺服器統計**：\n監控中 (`<{threshold}`次)：**{pending_count}** 人\n已畢業 (`>={threshold}`次)：**{completed_count}** 人\n"
            f"───────────────────────────"
        )

        lines = [summary_header]

        if pending_rows:
            lines.append(f"🔍 **目前監控中用戶 (未滿 {threshold} 次)**：")
            for author_id, count in pending_rows:
                try:
                    created_ts = int(discord.utils.snowflake_time(int(author_id)).timestamp())
                    created_str = f"<t:{created_ts}:d>"
                except Exception:
                    created_str = "未知"
                lines.append(f"• <@{author_id}> ── 帳號建立: {created_str} | 次數: **{count}/{threshold}**")
        else:
            lines.append(f"✅ 目前本伺服器沒有任何未滿 {threshold} 次的監控中用戶。")

        content = "\n".join(lines)
        if len(content) > 4000:
            content = content[:4000] + "\n... (訊息過長已截斷)"

        embed = discord.Embed(description=content, color=discord.Color.blue())
        await interaction.response.send_message(content=f"📊 **{interaction.guild.name} 發言統計**", embed=embed, ephemeral=True)

    @counts_command.error
    async def counts_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 你沒有權限使用此指令！", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(CountsCog(bot))
