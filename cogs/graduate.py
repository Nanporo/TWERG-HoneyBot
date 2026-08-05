import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import json
import os
from cogs.server_check import is_server_authorized

class GraduateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_counts = 'ryker_counts.db'
        self.db_archive = 'ryker_archive.db'
        self.settings_file = 'ryker_settings.json'

    def get_threshold(self, guild_id: int) -> int:
        if not os.path.exists(self.settings_file):
            return 10
        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get(str(guild_id), {}).get("monitor_threshold", 10)
        except Exception:
            return 10

    def _get_user_count(self, guild_id: int, user_id: str) -> int:
        gid_str = str(guild_id)
        try:
            with sqlite3.connect(self.db_counts) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count FROM message_counts WHERE guild_id = ? AND user_id = ?", (gid_str, user_id))
                row = cursor.fetchone()
                if row:
                    return row[0]
            with sqlite3.connect(self.db_archive) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count FROM message_counts_archive WHERE guild_id = ? AND user_id = ?", (gid_str, user_id))
                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception as e:
            print(f"⚠️ [手動畢業] 讀取用戶資料庫紀錄失敗: {e}")
        return 0

    def _graduate_user(self, guild_id: int, user_id: str, threshold: int) -> bool:
        gid_str = str(guild_id)
        now_ts = discord.utils.utcnow().timestamp()
        try:
            # 寫入歸檔庫
            with sqlite3.connect(self.db_archive) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO message_counts_archive (guild_id, user_id, count, last_timestamp, archived_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        count = excluded.count,
                        last_timestamp = excluded.last_timestamp,
                        archived_at = excluded.archived_at
                """, (gid_str, user_id, threshold, now_ts, now_ts))
                conn.commit()

            # 從活躍庫移除
            with sqlite3.connect(self.db_counts) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM message_counts WHERE guild_id = ? AND user_id = ?", (gid_str, user_id))
                conn.commit()
            return True
        except Exception as e:
            print(f"⚠️ [手動畢業] 手動畢業用戶至歸檔資料庫失敗: {e}")
            return False

    @app_commands.command(name="手動畢業", description="手動將發言未達門檻的用戶標記為已畢業 (僅限管理員)")
    @app_commands.describe(user="要手動畢業的用戶")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def graduate_command(self, interaction: discord.Interaction, user: discord.User):
        if not is_server_authorized(interaction.guild_id):
            await interaction.response.send_message("❌ 本伺服器尚未獲得機器人擁有者授權許可，無法使用此指令。", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 你沒有權限使用此指令！", ephemeral=True)
            return

        threshold = self.get_threshold(interaction.guild_id)
        user_id_str = str(user.id)
        old_count = self._get_user_count(interaction.guild_id, user_id_str)

        if old_count >= threshold:
            await interaction.response.send_message(
                f"ℹ️ 用戶 {user.mention} (`{user.id}`) 當前發言紀錄為 **{old_count}/{threshold}**，原本就已畢業，無需重複操作。",
                ephemeral=True
            )
            return

        success = self._graduate_user(interaction.guild_id, user_id_str, threshold)
        if success:
            embed = discord.Embed(
                title="",
                description=(
                    f"已成功將用戶 {user.mention} (`{user.id}`) 於本伺服器的發言次數從 **{old_count}/{threshold}** 手動更新為 **{threshold}/{threshold}**（已畢業）。\n\n"
                    f"該用戶之後於本伺服器將不受監控。"
                ),
                color=discord.Color.green()
            )
            await interaction.response.send_message(content="✅ 用戶已手動畢業", embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ 更新資料庫時發生錯誤，請查看 Console 日誌。", ephemeral=True)

    @graduate_command.error
    async def graduate_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 你沒有權限使用此指令！", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GraduateCog(bot))
