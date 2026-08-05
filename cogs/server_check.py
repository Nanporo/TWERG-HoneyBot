import discord
from discord.ext import commands
import json
import os

def load_server_authorizations() -> dict:
    auth_file = 'server_authorizations.json'
    if not os.path.exists(auth_file):
        return {}
    try:
        with open(auth_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_server_authorizations(data: dict):
    auth_file = 'server_authorizations.json'
    try:
        with open(auth_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"⚠️ [ServerCheck] 儲存 server_authorizations.json 失敗: {e}")

def is_server_authorized(guild_id: int) -> bool:
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        twerg_id = config.get("TWERG_SERVER_ID") or config.get("SERVER_ID", 518699949500661760)
        if twerg_id and int(guild_id) == int(twerg_id):
            return True
    except Exception:
        pass

    auths = load_server_authorizations()
    g_info = auths.get(str(guild_id), {})
    return g_info.get("authorized", False)

class ServerCheck(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.twerg_server_id = self._get_twerg_server_id()

    def _get_twerg_server_id(self) -> int:
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            server_id = config.get("TWERG_SERVER_ID") or config.get("SERVER_ID", 518699949500661760)
            return int(server_id)
        except Exception as e:
            print(f"⚠️ [ServerCheck] 讀取 TWERG_SERVER_ID 發生錯誤，使用預設值: {e}")
            return 518699949500661760

    async def _notify_owner_new_guild(self, guild: discord.Guild):
        """當機器人加入新伺服器且未授權時，通報 Console 頻道與 Bot Owner"""
        auths = load_server_authorizations()
        gid_str = str(guild.id)
        
        # 若為 TWERG 主伺服器，自動授權
        if guild.id == self.twerg_server_id:
            if not auths.get(gid_str, {}).get("authorized"):
                auths[gid_str] = {
                    "authorized": True,
                    "authorized_at": discord.utils.utcnow().isoformat(),
                    "authorized_by": "System (TWERG)"
                }
                save_server_authorizations(auths)
            return

        # 若不在紀錄中，新增未授權紀錄
        if gid_str not in auths:
            auths[gid_str] = {
                "authorized": False,
                "created_at": discord.utils.utcnow().isoformat()
            }
            save_server_authorizations(auths)

            print(f"📥 [新伺服器加入] {guild.name} (ID: {guild.id}, 人數: {guild.member_count}) - 當前狀態: 未授權 (等待擁有者核准)")

            # 通報至 CONSOLE 頻道
            try:
                with open('config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                console_id = config.get("CONSOLE_ID")
                if console_id:
                    console_channel = self.bot.get_channel(int(console_id))
                    if console_channel:
                        embed = discord.Embed(
                            title="",
                            description=(
                                f"**伺服器名稱**：{guild.name}\n"
                                f"**ID**：`{guild.id}`\n"
                                f"**擁有者 ID**：`<@{guild.owner_id}>` (`{guild.owner_id}`)\n"
                                f"**成員人數**：`{guild.member_count}` 人\n\n"
                                f"⚠️ 該伺服器目前為 **未授權** 狀態。\n"
                                f"可以使用 `/授權 <伺服器ID> 動作:核准` 來核准該伺服器。"
                            ),
                            color=discord.Color.gold()
                        )
                        await console_channel.send(content="📥 機器人加入新伺服器（等待核准）", embed=embed)
            except Exception as e:
                print(f"⚠️ [ServerCheck] 發送 Console 通報失敗: {e}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self._notify_owner_new_guild(guild)

    @commands.Cog.listener()
    async def on_ready(self):
        # 初始化 TWERG 伺服器授權
        auths = load_server_authorizations()
        twerg_str = str(self.twerg_server_id)
        if twerg_str not in auths or not auths[twerg_str].get("authorized"):
            auths[twerg_str] = {
                "authorized": True,
                "authorized_at": discord.utils.utcnow().isoformat(),
                "authorized_by": "System (TWERG)"
            }
            save_server_authorizations(auths)

        for guild in self.bot.guilds:
            await self._notify_owner_new_guild(guild)

async def setup(bot):
    await bot.add_cog(ServerCheck(bot))