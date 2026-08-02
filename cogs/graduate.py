import discord
from discord.ext import commands
from discord import app_commands
import sqlite3

class GraduateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_file = 'fkfeboy_counts.db'

    def _get_user_count(self, user_id: str) -> int:
        """讀取單一用戶的發言紀錄次數"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count FROM message_counts WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception as e:
            print(f"⚠️ [手動畢業] 讀取用戶資料庫紀錄失敗: {e}")
        return 0

    def _graduate_user(self, user_id: str) -> bool:
        """手動將指定用戶的發言次數設定為 10（畢業）"""
        now_ts = discord.utils.utcnow().timestamp()
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO message_counts (user_id, count, last_timestamp)
                    VALUES (?, 10, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        count = 10,
                        last_timestamp = excluded.last_timestamp
                """, (user_id, now_ts))
                conn.commit()
                return True
        except Exception as e:
            print(f"⚠️ [手動畢業] 手動畢業用戶至資料庫失敗: {e}")
            return False

    @app_commands.command(name="graduate", description="手動將發言未滿 10 則的用戶標記為已畢業 (僅限管理員)")
    @app_commands.describe(user="要手動畢業的用戶")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def graduate_command(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 你沒有權限使用此指令！", ephemeral=True)
            return

        user_id_str = str(user.id)
        old_count = self._get_user_count(user_id_str)

        if old_count >= 10:
            await interaction.response.send_message(
                f"ℹ️ 用戶 {user.mention} (`{user.id}`) 當前次數為 **{old_count}/10**，原本就已畢業，無需重複操作。",
                ephemeral=True
            )
            return

        success = self._graduate_user(user_id_str)
        if success:
            embed = discord.Embed(
                title="",
                description=(
                    f"已成功將用戶 {user.mention} (`{user.id}`) 的發言次數從 **{old_count}/10** 手動更新為 **10/10**（已畢業）。\n\n"
                    f"該用戶之後將不受監控。"
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
