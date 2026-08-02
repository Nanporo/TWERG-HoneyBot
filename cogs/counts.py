import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import json
import os

class CountsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_file = 'fkfeboy_counts.db'
        self.settings_file = 'fkfeboy_settings.json'

    def get_settings(self):
        default_settings = {
            "global_monitor": False
        }
        if not os.path.exists(self.settings_file):
            return default_settings
        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default_settings

    @app_commands.command(name="counts", description="查看目前的發言統計 (僅限管理員)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def counts_command(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 你沒有權限使用此指令！", ephemeral=True)
            return

        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM message_counts WHERE count < 10")
                pending_count = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM message_counts WHERE count >= 10")
                completed_count = cursor.fetchone()[0]

                # 優先抓出還在監控中 (count < 10) 的用戶，最多列出 30 筆
                cursor.execute("SELECT user_id, count FROM message_counts WHERE count < 10 ORDER BY count DESC LIMIT 30")
                pending_rows = cursor.fetchall()
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢資料庫時發生錯誤: {e}", ephemeral=True)
            return

        settings = self.get_settings()
        global_monitor = settings.get("global_monitor", False)
        status_str = "已開啟 🟢 (已包含潛水舊用戶)" if global_monitor else "已關閉 🔴 (僅限新帳號/新成員)"

        summary_header = (
            f"🛡️ **全域監控狀態**：{status_str}\n"
            f"📊 **統計總覽**：監控中 (`<10`次)：**{pending_count}** 人 | 已畢業 (`>=10`次)：**{completed_count}** 人\n"
            f"───────────────────────────"
        )

        lines = [summary_header]

        if pending_rows:
            lines.append("🔍 **目前監控中用戶 (未滿 10 次)**：")
            for author_id, count in pending_rows:
                try:
                    created_ts = int(discord.utils.snowflake_time(int(author_id)).timestamp())
                    created_str = f"<t:{created_ts}:d>"
                except Exception:
                    created_str = "未知"
                lines.append(f"• <@{author_id}> ── 創建: {created_str} | 次數: **{count}/10**")
        else:
            lines.append("✅ 目前沒有任何未滿 10 次的監控中用戶。")

        content = "\n".join(lines)
        if len(content) > 4000:
            content = content[:4000] + "\n... (訊息過長已截斷)"

        embed = discord.Embed(title="📊 發言統計 (SQLite)", description=content, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @counts_command.error
    async def counts_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 你沒有權限使用此指令！", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(CountsCog(bot))
