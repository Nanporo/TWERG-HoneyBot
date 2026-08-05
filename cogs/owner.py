import discord
from discord.ext import commands
from discord import app_commands
import sys
import os
import json
from settings.settings_utils import load_server_authorizations, save_server_authorizations

# 擁有者特許伺服器 ID (僅在此兩伺服器可見與使用)
OWNER_GUILD_IDS = [518699949500661760, 897116721159233576]

def load_trusted_users() -> list:
    trusted_file = 'trusted_users.json'
    if not os.path.exists(trusted_file):
        return []
    try:
        with open(trusted_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def save_trusted_users(data: list):
    trusted_file = 'trusted_users.json'
    try:
        with open(trusted_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"⚠️ 儲存 trusted_users.json 失敗: {e}")

def is_user_trusted(user_id: int) -> bool:
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        owner_id = config.get('OWNER_ID')
        if isinstance(owner_id, list) and user_id in owner_id:
            return True
        elif isinstance(owner_id, int) and user_id == owner_id:
            return True
    except Exception:
        pass
    
    trusted_list = load_trusted_users()
    return user_id in trusted_list

class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def is_owner(interaction: discord.Interaction) -> bool:
        if interaction.guild_id not in OWNER_GUILD_IDS:
            return False
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            owner_id = config.get('OWNER_ID')
            if isinstance(owner_id, list):
                return interaction.user.id in owner_id
            elif isinstance(owner_id, int):
                return interaction.user.id == owner_id
        except Exception:
            pass
        return await interaction.client.is_owner(interaction.user)

    @app_commands.command(name="推送", description="[擁有者] 強制推送訊息到指定頻道")
    @app_commands.describe(channel_id="頻道 ID (數字)", message="要推送的訊息")
    @app_commands.guilds(518699949500661760, 897116721159233576)
    @app_commands.check(is_owner)
    async def push_message(self, interaction: discord.Interaction, channel_id: str, message: str):
        try:
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await channel.send(message)
                await interaction.response.send_message('✅ 訊息推送成功！', ephemeral=True)
            else:
                await interaction.response.send_message('❌ 錯誤：無法找到該頻道。', ephemeral=True)
        except ValueError:
            await interaction.response.send_message('❌ 錯誤：頻道 ID 格式不正確。', ephemeral=True)

    @app_commands.command(name="重啟", description="[擁有者] 重新啟動機器人")
    @app_commands.guilds(518699949500661760, 897116721159233576)
    @app_commands.check(is_owner)
    async def restart(self, interaction: discord.Interaction):
        await interaction.response.send_message('🔄 機器人重新啟動中...', ephemeral=True)
        os.execv(sys.executable, ['python'] + sys.argv)

    @app_commands.command(name="關機", description="[擁有者] 關閉機器人")
    @app_commands.guilds(518699949500661760, 897116721159233576)
    @app_commands.check(is_owner)
    async def shutdown(self, interaction: discord.Interaction):
        await interaction.response.send_message('💤 機器人關機中，再見...', ephemeral=True)
        await self.bot.close()

    @app_commands.command(name="授權", description="[擁有者] 核准或撤銷伺服器的機器人使用權限")
    @app_commands.rename(action="動作", guild_id="伺服器id")
    @app_commands.describe(action="選擇動作 (核准 / 撤銷)", guild_id="伺服器 ID (數字)")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="核准伺服器權限", value="approve"),
            app_commands.Choice(name="撤銷伺服器權限", value="revoke")
        ]
    )
    @app_commands.guilds(518699949500661760, 897116721159233576)
    @app_commands.check(is_owner)
    async def authorize_command(self, interaction: discord.Interaction, action: app_commands.Choice[str], guild_id: str):
        auths = load_server_authorizations()
        val = action.value

        if not guild_id or not guild_id.strip().isdigit():
            await interaction.response.send_message("❌ 請提供正確的數字伺服器 ID。", ephemeral=True)
            return

        gid_str = str(guild_id).strip()
        guild = self.bot.get_guild(int(gid_str))
        gname = f"**{guild.name}**" if guild else f"`{gid_str}`"

        if val == "approve":
            auths[gid_str] = {
                "authorized": True,
                "authorized_at": discord.utils.utcnow().isoformat(),
                "authorized_by": f"{interaction.user} ({interaction.user.id})"
            }
            save_server_authorizations(auths)
            await interaction.response.send_message(f"✅ 已成功核准伺服器 {gname} (`{gid_str}`) 的使用權限！", ephemeral=True)

        elif val == "revoke":
            auths[gid_str] = {
                "authorized": False,
                "revoked_at": discord.utils.utcnow().isoformat(),
                "revoked_by": f"{interaction.user} ({interaction.user.id})"
            }
            save_server_authorizations(auths)
            await interaction.response.send_message(f"🚫 已成功撤銷伺服器 {gname} (`{gid_str}`) 的使用權限。", ephemeral=True)

    @app_commands.command(name="信任管理", description="[擁有者] 新增、刪除或查看授權操作幹男小帳清單的信任人員")
    @app_commands.rename(action="動作", user="使用者")
    @app_commands.describe(action="選擇動作 (查看 / 新增 / 刪除)", user="要操作的使用者")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="查看信任名單", value="list"),
            app_commands.Choice(name="新增信任人員", value="add"),
            app_commands.Choice(name="刪除信任人員", value="remove")
        ]
    )
    @app_commands.guilds(518699949500661760, 897116721159233576)
    @app_commands.check(is_owner)
    async def trust_command(self, interaction: discord.Interaction, action: app_commands.Choice[str], user: discord.User = None):
        trusted_list = load_trusted_users()
        val = action.value

        if val == "list":
            if not trusted_list:
                msg = "ℹ️ 目前自訂信任名單為空。（擁有者預設永遠信任）"
            else:
                user_mentions = [f"• <@{uid}> (`{uid}`)" for uid in trusted_list]
                msg = f"🤝 **目前信任人員名單**：\n" + "\n".join(user_mentions)
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if not user:
            await interaction.response.send_message("❌ 請選擇或提供要操作的使用者。", ephemeral=True)
            return

        uid = user.id
        if val == "add":
            if uid in trusted_list:
                await interaction.response.send_message(f"ℹ️ 使用者 {user.mention} (`{uid}`) 原本就在信任名單中。", ephemeral=True)
                return
            trusted_list.append(uid)
            save_trusted_users(trusted_list)
            await interaction.response.send_message(f"✅ 已成功將 {user.mention} (`{uid}`) 加入信任人員名單！", ephemeral=True)

        elif val == "remove":
            if uid not in trusted_list:
                await interaction.response.send_message(f"ℹ️ 使用者 {user.mention} (`{uid}`) 不在信任名單中。", ephemeral=True)
                return
            trusted_list.remove(uid)
            save_trusted_users(trusted_list)
            await interaction.response.send_message(f"🗑️ 已將 {user.mention} (`{uid}`) 從信任人員名單中移除。", ephemeral=True)

    @app_commands.command(name="強制退出", description="[擁有者] 強迫機器人退出指定的伺服器")
    @app_commands.rename(guild_id="伺服器id")
    @app_commands.describe(guild_id="要退出的伺服器 ID (數字)")
    @app_commands.guilds(518699949500661760, 897116721159233576)
    @app_commands.check(is_owner)
    async def leave_guild_command(self, interaction: discord.Interaction, guild_id: str):
        if not guild_id or not guild_id.strip().isdigit():
            await interaction.response.send_message("❌ 請提供正確的數字伺服器 ID。", ephemeral=True)
            return

        gid = int(guild_id.strip())
        guild = self.bot.get_guild(gid)

        if not guild:
            await interaction.response.send_message(f"❌ 錯誤：找不到 ID 為 `{gid}` 的伺服器，或機器人不在該伺服器中。", ephemeral=True)
            return

        # 保護主伺服器避免誤操作
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            twerg_id = config.get("TWERG_SERVER_ID") or config.get("SERVER_ID")
            if twerg_id and gid == int(twerg_id):
                await interaction.response.send_message("❌ 錯誤：無法對 TWERG 主伺服器執行強制退出！", ephemeral=True)
                return
        except Exception:
            pass

        guild_name = guild.name
        try:
            await guild.leave()
            await interaction.response.send_message(f"🚪 已成功強制機器人退出伺服器 **{guild_name}** (`{gid}`)！", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 退出伺服器時發生錯誤: {e}", ephemeral=True)

    @push_message.error
    @restart.error
    @shutdown.error
    @authorize_command.error
    @trust_command.error
    @leave_guild_command.error
    async def owner_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 你沒有權限或無法在該伺服器使用此指令。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Owner(bot))