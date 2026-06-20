import discord
from discord.ext import commands
import json

class ServerCheck(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.allowed_server_id = self._get_allowed_server_id()

    def _get_allowed_server_id(self):
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 取得 SERVER_ID，若無設定則預設為 518699949500661760，並強制轉型為整數
            server_id = config.get("SERVER_ID", 518699949500661760)
            return int(server_id)
        except Exception as e:
            print(f"讀取 SERVER_ID 發生錯誤，使用預設值: {e}")
            return 518699949500661760

    async def _check_and_leave(self, guild):
        """檢查並退出未授權的伺服器"""
        if guild.id != self.allowed_server_id:
            print(f"發現未授權的伺服器: {guild.name} (ID: {guild.id})，正在自動退出...")
            try:
                await guild.leave()
            except discord.HTTPException as e:
                print(f"退出伺服器 {guild.name} 時發生錯誤: {e}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        # 當機器人被加入新伺服器時觸發
        await self._check_and_leave(guild)

    @commands.Cog.listener()
    async def on_ready(self):
        # 啟動時掃描目前所有的伺服器，確保沒有在離線時被加入非指定伺服器
        for guild in self.bot.guilds:
            await self._check_and_leave(guild)

async def setup(bot):
    await bot.add_cog(ServerCheck(bot))