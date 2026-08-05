import discord
from discord.ext import commands
from discord import app_commands

class AboutCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="關於", description="顯示 HoneyBot 機器人版本與系統資訊 About Bot")
    async def about_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            description="使用或邀請機器人即代表您同意讓機器人讀取您伺服器的訊息、使用者資訊等資料。\n機器人可能會出錯，任何操作請進行二次核可，並合理管控機器人權限。\n如果造成損害，TWERG 和機器人開發者不負擔任何責任。",
            color=discord.Color.gold()
        )
        embed.add_field(name="版本", value="2.0", inline=True)
        embed.add_field(name="開發", value="地牛記錄小組 TWERG", inline=True)
        embed.set_footer(text="TWERG HoneyBot 防護系統")
        
        await interaction.response.send_message(content="🤖 **HoneyBot 蜜罐防護機器人**", embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AboutCog(bot))
