import discord
from discord.ext import commands
from discord import app_commands
import sys
import os

class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 自訂權限檢查：確認觸發者是否為機器人擁有者
    async def is_owner(interaction: discord.Interaction) -> bool:
        return interaction.user.id == interaction.client.owner_id

    @app_commands.command(name="push", description="強制推送訊息到指定頻道")
    @app_commands.describe(channel_id="頻道 ID (數字)", message="要推送的訊息")
    @app_commands.check(is_owner)
    async def push_message(self, interaction: discord.Interaction, channel_id: str, message: str):
        try:
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await channel.send(message)
                # ephemeral=True 讓這條成功提示只有你看得到，不會洗版
                await interaction.response.send_message('✅ 訊息推送成功！', ephemeral=True)
            else:
                await interaction.response.send_message('錯誤：無法找到該頻道。', ephemeral=True)
        except ValueError:
            await interaction.response.send_message('錯誤：頻道 ID 格式不正確。', ephemeral=True)

    @app_commands.command(name="restart", description="重新啟動機器人")
    @app_commands.check(is_owner)
    async def restart(self, interaction: discord.Interaction):
        await interaction.response.send_message('重新啟動中...', ephemeral=True)
        # 重啟目前的 Python 進程
        os.execv(sys.executable, ['python'] + sys.argv)

    @app_commands.command(name="shutdown", description="關閉機器人")
    @app_commands.check(is_owner)
    async def shutdown(self, interaction: discord.Interaction):
        await interaction.response.send_message('關機了，再見💤', ephemeral=True)
        await self.bot.close()

    # 捕捉因為不是擁有者而產生的 CheckFailure 錯誤
    @push_message.error
    @restart.error
    @shutdown.error
    async def owner_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("錯誤：你沒有權限使用這個指令。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Owner(bot))