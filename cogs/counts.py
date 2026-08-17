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
            # 1. 自動整理：若活躍庫中有已達門檻 (>= threshold) 的紀錄，自動歸檔至 counts_archive.db
            if os.path.exists(self.db_counts) and os.path.exists(self.db_archive):
                with sqlite3.connect(self.db_counts) as conn_c:
                    cur_c = conn_c.cursor()
                    cur_c.execute(
                        "SELECT user_id, count, last_timestamp FROM message_counts WHERE guild_id = ? AND count >= ?",
                        (gid_str, threshold)
                    )
                    over_grad_rows = cur_c.fetchall()
                    if over_grad_rows:
                        now_ts = discord.utils.utcnow().timestamp()
                        with sqlite3.connect(self.db_archive) as conn_a:
                            cur_a = conn_a.cursor()
                            for uid, cnt, l_ts in over_grad_rows:
                                cur_a.execute("""
                                    INSERT INTO message_counts_archive (guild_id, user_id, count, last_timestamp, archived_at)
                                    VALUES (?, ?, ?, ?, ?)
                                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                                        count = excluded.count,
                                        last_timestamp = excluded.last_timestamp,
                                        archived_at = excluded.archived_at
                                """, (gid_str, uid, cnt, l_ts, now_ts))
                            conn_a.commit()
                        cur_c.execute(
                            "DELETE FROM message_counts WHERE guild_id = ? AND count >= ?",
                            (gid_str, threshold)
                        )
                        conn_c.commit()

            # 2. 查詢未畢業監控中名單 (依最近發言時間由新至舊排序)
            if os.path.exists(self.db_counts):
                with sqlite3.connect(self.db_counts) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT COUNT(*) FROM message_counts WHERE guild_id = ? AND count < ?", 
                        (gid_str, threshold)
                    )
                    pending_count = cursor.fetchone()[0]

                    cursor.execute(
                        "SELECT user_id, count, last_timestamp FROM message_counts WHERE guild_id = ? AND count < ? ORDER BY last_timestamp DESC LIMIT 30", 
                        (gid_str, threshold)
                    )
                    pending_rows = cursor.fetchall()

            # 3. 查詢已畢業人數
            if os.path.exists(self.db_archive):
                with sqlite3.connect(self.db_archive) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM message_counts_archive WHERE guild_id = ?", (gid_str,))
                    completed_count = cursor.fetchone()[0]
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢資料庫時發生錯誤: {e}", ephemeral=True)
            return

        status_str = "`🟢` 已開啟 (取消畢業豁免，全體成員包含已畢業老成員皆持續監控)" if lurker_monitor else "`🔴` 已停用 (預設一般模式，已畢業老成員放行)"

        summary_header = (
            f"**嚴格防護模式 (全員監控)**：{status_str}\n"
            f"**伺服器發言監控門檻**：`{threshold}` 次\n"
            f"───────────────────────────\n"
            f"**本伺服器統計**：\n監控中 (`<{threshold}`次)：**{pending_count}** 人\n已畢業 (`>={threshold}`次)：**{completed_count}** 人\n"
            f"───────────────────────────"
        )

        lines = [summary_header]

        if pending_rows:
            lines.append(f"🔍 **目前監控中用戶 (未滿 {threshold} 次，依最新發言排序)**：")
            for author_id, count, last_ts in pending_rows:
                try:
                    created_ts = int(discord.utils.snowflake_time(int(author_id)).timestamp())
                    created_str = f"<t:{created_ts}:d>"
                except Exception:
                    created_str = "未知"
                
                last_str = f"<t:{int(last_ts)}:R>" if last_ts else "無紀錄"
                lines.append(f"• <@{author_id}> ── 次數: **{count}/{threshold}** | 最近發言: {last_str} | 帳號建立: {created_str}")
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
