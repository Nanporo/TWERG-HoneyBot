import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os

class Heartbeat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ping_url = self.load_ping_url()
        self.has_pinged = False
        if self.ping_url and self.ping_url.startswith("http"):
            print("🟢 [Heartbeat] 心跳檢測模組已載入，準備定時發送 Ping。")
            self.ping_task.start()
        else:
            print("⚠️ [Heartbeat] config.json 中未設定有效的 HEALTHCHECKS_URL，心跳檢測暫停中。")

    def load_ping_url(self) -> str:
        """從 config.json 讀取 HEALTHCHECKS_URL"""
        config_path = 'config.json'
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('HEALTHCHECKS_URL', '')
            except Exception as e:
                print(f"⚠️ [Heartbeat] 讀取 config.json 失敗: {e}")
        return ''

    def cog_unload(self):
        if self.ping_task.is_running():
            self.ping_task.cancel()

    @tasks.loop(minutes=1)
    async def ping_task(self):
        """每 1 分鐘回報心跳至 Healthchecks.io"""
        if not self.bot.is_ready():
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.ping_url, timeout=10) as resp:
                    if resp.status == 200:
                        if not self.has_pinged:
                            print("🟢 [Heartbeat] 首次心跳已成功傳送至 Healthchecks.io！")
                            self.has_pinged = True
                    else:
                        print(f"⚠️ [Heartbeat] 心跳回報異常 (HTTP {resp.status})")
        except Exception as e:
            print(f"⚠️ [Heartbeat] 無法連線至 Healthchecks.io: {e}")

    @ping_task.before_loop
    async def before_ping(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Heartbeat(bot))
