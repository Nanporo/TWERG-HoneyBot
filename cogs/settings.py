import discord
from discord.ext import commands
from discord import app_commands
import json
import os

class SettingsView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.current_settings = cog.get_settings(guild_id)
        self.message = None

        # 排除防護身份組選單
        self.excluded_select = discord.ui.RoleSelect(
            placeholder="請選擇要排除防護的身份組 (可複選)...",
            min_values=0,
            max_values=20,
            row=0
        )
        self.excluded_select.callback = self.excluded_callback
        self.add_item(self.excluded_select)

        # 陷阱身份組選單
        self.trap_select = discord.ui.RoleSelect(
            placeholder="選擇陷阱身份組 (標註即封鎖, 可複選)...",
            min_values=0,
            max_values=20,
            row=1
        )
        self.trap_select.callback = self.trap_callback
        self.add_item(self.trap_select)

        # Console 輸出頻道設定
        self.console_select = discord.ui.ChannelSelect(
            placeholder="設定 Console 輸出頻道 (可清除以停用)",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=2
        )
        self.console_select.callback = self.console_callback
        self.add_item(self.console_select)

        # 刪除訊息開關按鈕
        is_del = self.current_settings.get("delete_messages", True)
        self.toggle_btn = discord.ui.Button(
            label="刪除30分內訊息: 已啟用" if is_del else "刪除30分內訊息: 已停用",
            style=discord.ButtonStyle.green if is_del else discord.ButtonStyle.red,
            row=3
        )
        self.toggle_btn.callback = self.toggle_callback
        self.add_item(self.toggle_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有伺服器管理員才能操作此設定面板！", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.delete()
            except discord.HTTPException:
                pass

    async def update_settings(self, key, value):
        data = {}
        if os.path.exists(self.cog.settings_file):
            with open(self.cog.settings_file, 'r', encoding='utf-8') as f:
                try: data = json.load(f)
                except: pass
        
        guild_data = self.cog.get_settings(self.guild_id)
        guild_data[key] = value
        data[str(self.guild_id)] = guild_data
        
        with open(self.cog.settings_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        self.current_settings = guild_data

    def generate_embed(self, guild: discord.Guild):
        excluded_roles = self.current_settings.get("excluded_roles", [])
        trap_roles = self.current_settings.get("trap_roles", [])
        delete_messages = self.current_settings.get("delete_messages", True)

        # 自動過濾已刪除的身份組
        valid_excluded = [r for r in excluded_roles if guild.get_role(r) is not None]
        valid_trap = [r for r in trap_roles if guild.get_role(r) is not None]

        excluded_roles_str = ", ".join([f"<@&{r}>" for r in valid_excluded]) if valid_excluded else "無"
        trap_roles_str = ", ".join([f"<@&{r}>" for r in valid_trap]) if valid_trap else "無"
        delete_messages_str = "已啟用" if delete_messages else "已停用"

        console_id = None
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            console_id = config.get('CONSOLE_ID')
        except Exception:
            pass

        console_id_str = f"<#{console_id}>" if console_id else "未設定"

        embed = discord.Embed(
            title="🛡️ 伺服器防護與系統設定",
            description="請使用下方選單調整各項功能：",
            color=discord.Color.blue()
        )
        embed.add_field(name="預設防護排除身份組", value=f"<@&{self.cog.default_excluded_role}>", inline=False)
        embed.add_field(name="目前排除防護身份組", value=excluded_roles_str, inline=False)
        embed.add_field(name="目前陷阱身份組", value=trap_roles_str, inline=False)
        embed.add_field(name="封鎖時刪除近30分鐘訊息", value=delete_messages_str, inline=False)
        embed.add_field(name="Console 輸出頻道", value=console_id_str, inline=False)

        return embed

    async def excluded_callback(self, interaction: discord.Interaction):
        roles = [r.id for r in self.excluded_select.values]
        await self.update_settings("excluded_roles", roles)
        role_mentions = ", ".join([r.mention for r in self.excluded_select.values])
        
        embed = self.generate_embed(interaction.guild)
        await interaction.response.edit_message(content=None, embed=embed, view=self)
        
        reply_embed = discord.Embed(description=f"✅ 已更新排除防護的身份組：\n{role_mentions if role_mentions else '無 (僅保留預設排除)'}", color=discord.Color.green())
        await interaction.followup.send(embed=reply_embed, ephemeral=True)

    async def trap_callback(self, interaction: discord.Interaction):
        roles = [r.id for r in self.trap_select.values]
        await self.update_settings("trap_roles", roles)
        role_mentions = ", ".join([r.mention for r in self.trap_select.values])
        
        embed = self.generate_embed(interaction.guild)
        await interaction.response.edit_message(content=None, embed=embed, view=self)
        
        reply_embed = discord.Embed(description=f"✅ 已更新陷阱身份組：\n{role_mentions if role_mentions else '無'}", color=discord.Color.green())
        await interaction.followup.send(embed=reply_embed, ephemeral=True)

    async def toggle_callback(self, interaction: discord.Interaction):
        new_val = not self.current_settings.get("delete_messages", True)
        await self.update_settings("delete_messages", new_val)
        self.toggle_btn.label = "刪除30分內訊息: 已啟用" if new_val else "刪除30分內訊息: 已停用"
        self.toggle_btn.style = discord.ButtonStyle.green if new_val else discord.ButtonStyle.red
        
        embed = self.generate_embed(interaction.guild)
        await interaction.response.edit_message(content=None, embed=embed, view=self)
        
        reply_embed = discord.Embed(description=f"✅ 封鎖時刪除近30分鐘訊息功能已 **{'啟用' if new_val else '停用'}**", color=discord.Color.green())
        await interaction.followup.send(embed=reply_embed, ephemeral=True)

    async def console_callback(self, interaction: discord.Interaction):
        channel_id = self.console_select.values[0].id if self.console_select.values else None
        
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            config['CONSOLE_ID'] = channel_id
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
                
            # 即時更新 ConsoleOutputCog 
            console_cog = self.cog.bot.get_cog('ConsoleOutputCog')
            if console_cog:
                console_cog.channel_id = channel_id
                if channel_id and not console_cog.send_console_task.is_running():
                    console_cog.send_console_task.start()
                elif not channel_id and console_cog.send_console_task.is_running():
                    console_cog.send_console_task.cancel()
                    
            msg = f"✅ 已成功將 Console 輸出頻道更新為 <#{channel_id}>" if channel_id else "✅ 已停用 Console 輸出轉發功能"
            
            embed = self.generate_embed(interaction.guild)
            await interaction.response.edit_message(content=None, embed=embed, view=self)
            
            reply_embed = discord.Embed(description=msg, color=discord.Color.green())
            await interaction.followup.send(embed=reply_embed, ephemeral=True)
        except Exception as e:
            err_embed = discord.Embed(description=f"❌ 更新設定發生錯誤: {e}", color=discord.Color.red())
            if interaction.response.is_done():
                await interaction.followup.send(embed=err_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=err_embed, ephemeral=True)

class SettingsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings_file = 'honeypot_settings.json'
        self.default_excluded_role = 518700481011253269
        

    def get_settings(self, guild_id):
        default_settings = {
            "excluded_roles": [],
            "trap_roles": [],
            "delete_messages": True
        }
        if not os.path.exists(self.settings_file):
            return default_settings
            
        with open(self.settings_file, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                guild_data = data.get(str(guild_id), {})
                # 相容舊版資料格式 (只有一個 list)
                if isinstance(guild_data, list):
                    migrated = default_settings.copy()
                    migrated["excluded_roles"] = guild_data
                    return migrated
                    
                for k, v in default_settings.items():
                    if k not in guild_data:
                        guild_data[k] = v
                return guild_data
            except json.JSONDecodeError:
                return default_settings

    @app_commands.command(name="設定", description="設定蜜罐防護機制、陷阱身份組與系統日誌頻道")
    @app_commands.default_permissions(administrator=True)
    async def setup_honeypot(self, interaction: discord.Interaction):
        view = SettingsView(self, interaction.guild.id)
        embed = view.generate_embed(interaction.guild)
        await interaction.response.send_message(
            embed=embed, 
            view=view,
            ephemeral=True
        )
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(SettingsCog(bot))