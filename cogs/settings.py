import discord
from discord.ext import commands
from discord import app_commands
from settings.settings_main import SettingsView
from settings.settings_utils import is_server_authorized

class SettingsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings_file = 'honeypot_settings.json'

    @app_commands.command(name="設定", description="呼叫伺服器防護與系統設定面板 (僅限伺服器管理員)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def settings_command(self, interaction: discord.Interaction):
        if not is_server_authorized(interaction.guild_id):
            embed = discord.Embed(
                description="❌ 本伺服器尚未獲得機器人擁有者授權許可，暫無法開啟與調整防護功能。\n\n請聯絡機器人擁有者申請授權。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(content="🔒 **伺服器未授權**", embed=embed, ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有伺服器管理員才能使用此指令！", ephemeral=True)
            return

        view = SettingsView(self.bot, interaction.guild_id)
        content, embed = view.get_content_and_embed(interaction.guild)
        await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()

    @settings_command.error
    async def settings_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 只有伺服器管理員才能使用此指令！", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SettingsCog(bot))