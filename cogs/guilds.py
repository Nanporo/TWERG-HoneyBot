import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from typing import Optional
from settings.settings_utils import (
    load_server_authorizations,
    save_server_authorizations,
    is_server_authorized,
    load_all_guild_settings,
    load_guild_settings,
    save_guild_settings
)

def check_is_owner(user_id: int) -> bool:
    """檢查使用者是否為機器人擁有者 (從 config.json 讀取 OWNER_ID)"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        owner_id = config.get('OWNER_ID')
        if isinstance(owner_id, list):
            return user_id in owner_id
        elif isinstance(owner_id, int):
            return user_id == owner_id
    except Exception:
        pass
    return False

def get_honeypot_settings() -> dict:
    return load_all_guild_settings()

def save_honeypot_settings(data: dict):
    for k, v in data.items():
        save_guild_settings(int(k), v)

def get_bot_config() -> dict:
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

class ServerSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="查看伺服器詳細資訊", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        guild_id = int(self.values[0])
        await self.view.show_detail(interaction, guild_id)

class GuildsView(discord.ui.View):
    def __init__(self, bot, guilds, guild_settings, author_id: int, show_stats: bool, stats_data: dict = None):
        super().__init__(timeout=300)
        self.bot = bot
        self.guilds = guilds
        self.guild_settings = guild_settings
        self.author_id = author_id
        self.show_stats = show_stats
        self.stats_data = stats_data
        
        self.per_page = 10
        self.max_list_pages = max(1, (len(self.guilds) + self.per_page - 1) // self.per_page)
        self.total_pages = self.max_list_pages + (1 if self.show_stats else 0)
        self.current_page = 0
        self.is_detail_mode = False
        self.current_detail_guild_id = None
        
        self.prev_button = discord.ui.Button(emoji="⬅️", style=discord.ButtonStyle.primary, row=0)
        self.prev_button.callback = self.prev_page
        self.page_indicator = discord.ui.Button(label="第 1 頁", style=discord.ButtonStyle.secondary, disabled=True, row=0)
        self.next_button = discord.ui.Button(emoji="➡️", style=discord.ButtonStyle.primary, row=0)
        self.next_button.callback = self.next_page
        
        self.back_button = discord.ui.Button(label="返回", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
        self.back_button.callback = self.back_to_list
        
        self.toggle_auth_button = discord.ui.Button(label="切換授權狀態", emoji="🔑", style=discord.ButtonStyle.success, row=1)
        self.toggle_auth_button.callback = self.toggle_authorization_setting

        self.toggle_del_button = discord.ui.Button(label="切換刪除訊息設定", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
        self.toggle_del_button.callback = self.toggle_delete_message_setting
        
        self.back_to_overview_btn = discord.ui.Button(label="回概覽", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
        self.back_to_overview_btn.callback = self.back_to_overview
        
        self.select_menu = None
        self.update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ 這個按鈕/選單只能由原指令使用者操作！", ephemeral=True)
            return False
        return True

    def get_guild_marks(self, guild_id_str):
        config = get_bot_config()
        marks = ""
        
        # 授權標籤
        if is_server_authorized(int(guild_id_str)):
            marks += "🟢"
        else:
            marks += "🔴"

        # TWERG 主伺服器
        twerg_id = config.get("TWERG_SERVER_ID") or config.get("SERVER_ID")
        if twerg_id and int(guild_id_str) == int(twerg_id):
            marks += "🏠"

        return marks

    def build_stats_embed(self):
        desc = (
            f"🌐 **總伺服器**：`{self.stats_data['total_guilds']}`\n"
            f"👥 **總成員數**：`{self.stats_data['total_members']}`\n"
            f"🔑 **授權伺服器**：`{self.stats_data['auth_count']}` 個伺服器\n"
            f"🛡️ **排除身份組**：`{self.stats_data['excluded_count']}` 個伺服器\n"
            f"🪤 **陷阱身份組**：`{self.stats_data['trap_count']}` 個伺服器\n"
            f"🗑️ **刪除30分訊息**：`{self.stats_data['delete_msg_count']}` 個伺服器\n"
            f"🏠 **TWERG 主伺服器**：{self.stats_data['main_server_str']}\n"
            f"🍯 **蜜罐頻道**：{self.stats_data['honeypot_channel_str']}\n"
            f"🖥️ **Console 日誌**：{self.stats_data['console_channel_str']}"
        )
        embed = discord.Embed(description=desc, color=discord.Color.gold())
        return embed

    def build_list_embed(self, list_page_index):
        start_idx = list_page_index * self.per_page
        end_idx = start_idx + self.per_page
        page_guilds = self.guilds[start_idx:end_idx]
        
        embed = discord.Embed(color=discord.Color.blue())
        for i, guild in enumerate(page_guilds):
            marks = self.get_guild_marks(str(guild.id))
            owner_name = f"<@{guild.owner_id}>" if guild.owner_id else "未知"
            embed.add_field(
                name=f"{start_idx + i + 1}. {guild.name} {marks}".strip(),
                value=f"ID: `{guild.id}`\n擁有者: {owner_name}\n人數: `{guild.member_count}` 人",
                inline=False
            )
        return embed, page_guilds

    async def build_detail_embed(self, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return discord.Embed(description="❌ 機器人可能已經退出該伺服器。", color=discord.Color.red())
            
        embed = discord.Embed(color=discord.Color.blue())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        owner_name = f"<@{guild.owner_id}>" if guild.owner_id else "未知"
        joined_time = f"<t:{int(guild.me.joined_at.timestamp())}:f>" if guild.me and guild.me.joined_at else "未知"
        created_time = f"<t:{int(guild.created_at.timestamp())}:f>" if guild.created_at else "未知"
        
        g_settings = self.guild_settings.get(str(guild.id), {})
        config = get_bot_config()
        
        is_auth = is_server_authorized(guild.id)
        auth_str = "`🟢 已核准授權`" if is_auth else "`🔴 未授權 (阻擋設定與防護)`"

        excluded_roles = g_settings.get("excluded_roles", [])
        valid_excluded = [f"<@&{r}>" for r in excluded_roles if guild.get_role(r) is not None]
        excluded_str = ", ".join(valid_excluded) if valid_excluded else "無"
        
        trap_roles = g_settings.get("trap_roles", [])
        valid_trap = [f"<@&{r}>" for r in trap_roles if guild.get_role(r) is not None]
        trap_str = ", ".join(valid_trap) if valid_trap else "無"
        
        del_msg = g_settings.get("delete_messages", True)
        del_msg_str = "`🟢` 已啟用" if del_msg else "`🔴` 已停用"
        
        hp_id = config.get("HONEYPOT_ID")
        hp_channel = guild.get_channel(int(hp_id)) if hp_id else None
        hp_str = f"🟢 {hp_channel.mention}" if hp_channel else ("⚪ 非本伺服器" if hp_id else "🔴 未設定")

        log_ch_id = g_settings.get("log_channel_id")
        log_channel = guild.get_channel(int(log_ch_id)) if log_ch_id else None
        log_str = f"🟢 {log_channel.mention}" if log_channel else "🔴 未設定 (無抄送)"
        
        marks = self.get_guild_marks(str(guild.id))
        
        embed.add_field(
            name="📌 基本資訊", 
            value=f"ID: `{guild.id}`\n擁有者: {owner_name}\n人數: `{guild.member_count}` 人\n建立時間: {created_time}\n加入時間: {joined_time}", 
            inline=False
        )
        embed.add_field(
            name="🔑 授權狀態",
            value=auth_str,
            inline=False
        )
        embed.add_field(
            name="🛡️ 蜜罐與防禦設定", 
            value=f"標籤狀態: {marks if marks else '無'}\n"
                  f"排除身份組 (白名單): {excluded_str}\n"
                  f"陷阱身份組: {trap_str}\n"
                  f"封鎖時刪除30分訊息: {del_msg_str}", 
            inline=False
        )
        embed.add_field(
            name="📡 頻道系統對應", 
            value=f"蜜罐頻道: {hp_str}\n防護日誌頻道: {log_str}", 
            inline=False
        )

        return embed

    def update_components(self):
        self.clear_items()
        
        if self.is_detail_mode:
            self.add_item(self.back_button)
            self.add_item(self.toggle_auth_button)
            self.add_item(self.toggle_del_button)
            return

        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == self.total_pages - 1
        self.page_indicator.label = f"第 {self.current_page + 1} / {self.total_pages} 頁"
        
        if self.total_pages > 1:
            self.add_item(self.prev_button)
            self.add_item(self.page_indicator)
            self.add_item(self.next_button)

        if self.current_page > 0 or not self.show_stats:
            self.add_item(self.back_to_overview_btn)

        if self.show_stats and self.current_page == 0:
            pass
        else:
            list_page_index = self.current_page - (1 if self.show_stats else 0)
            start_idx = list_page_index * self.per_page
            end_idx = start_idx + self.per_page
            page_guilds = self.guilds[start_idx:end_idx]
            
            if page_guilds:
                options = []
                for guild in page_guilds:
                    options.append(discord.SelectOption(label=guild.name[:100], value=str(guild.id), description=f"ID: {guild.id}"))
                self.select_menu = ServerSelect(options)
                self.add_item(self.select_menu)

    async def get_current_content_and_embed(self):
        if self.is_detail_mode:
            guild = self.bot.get_guild(self.current_detail_guild_id)
            gname = guild.name if guild else "未知"
            return f"🔍 **伺服器詳細資訊：{gname}**", await self.build_detail_embed(self.current_detail_guild_id)
            
        if self.show_stats and self.current_page == 0:
            return "🤖 **HoneyBot 機器人狀態與總覽**", self.build_stats_embed()
        else:
            list_page_index = self.current_page - (1 if self.show_stats else 0)
            embed, _ = self.build_list_embed(list_page_index)
            return "📋 **伺服器列表 (🟢已授權 | 🔴未授權)**", embed

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_components()
        content, embed = await self.get_current_content_and_embed()
        await interaction.response.edit_message(content=content, embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.update_components()
        content, embed = await self.get_current_content_and_embed()
        await interaction.response.edit_message(content=content, embed=embed, view=self)

    async def show_detail(self, interaction: discord.Interaction, guild_id: int):
        self.is_detail_mode = True
        self.current_detail_guild_id = guild_id
        self.update_components()
        content, embed = await self.get_current_content_and_embed()
        await interaction.response.edit_message(content=content, embed=embed, view=self)

    async def toggle_authorization_setting(self, interaction: discord.Interaction):
        if not self.current_detail_guild_id:
            return
        gid_str = str(self.current_detail_guild_id)
        auths = load_server_authorizations()
        curr_status = auths.get(gid_str, {}).get("authorized", False)
        
        auths[gid_str] = {
            "authorized": not curr_status,
            "updated_at": discord.utils.utcnow().isoformat(),
            "updated_by": f"{interaction.user} ({interaction.user.id})"
        }
        save_server_authorizations(auths)

        content, embed = await self.get_current_content_and_embed()
        await interaction.response.edit_message(content=content, embed=embed, view=self)

    async def toggle_delete_message_setting(self, interaction: discord.Interaction):
        if not self.current_detail_guild_id:
            return
        gid_str = str(self.current_detail_guild_id)
        if gid_str not in self.guild_settings:
            self.guild_settings[gid_str] = {}
        
        current_status = self.guild_settings[gid_str].get("delete_messages", True)
        self.guild_settings[gid_str]["delete_messages"] = not current_status
        
        save_guild_settings(self.current_detail_guild_id, self.guild_settings[gid_str])
        
        content, embed = await self.get_current_content_and_embed()
        await interaction.response.edit_message(content=content, embed=embed, view=self)

    async def back_to_list(self, interaction: discord.Interaction):
        self.is_detail_mode = False
        self.update_components()
        content, embed = await self.get_current_content_and_embed()
        await interaction.response.edit_message(content=content, embed=embed, view=self)

    async def back_to_overview(self, interaction: discord.Interaction):
        if not self.show_stats:
            self.show_stats = True
            self.total_pages = self.max_list_pages + 1
        self.current_page = 0
        self.update_components()
        content, embed = await self.get_current_content_and_embed()
        await interaction.response.edit_message(content=content, embed=embed, view=self)


class GuildsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def is_owner_check_interaction(interaction: discord.Interaction) -> bool:
        if check_is_owner(interaction.user.id):
            return True
        return await interaction.client.is_owner(interaction.user)

    @app_commands.command(name="伺服器列表", description="[擁有者] 顯示機器人加入的伺服器列表與狀態 Server Guilds")
    @app_commands.rename(sort_by="排序方式", search="搜尋關鍵字", feature_filter="功能篩選", guild_id="伺服器id")
    @app_commands.describe(sort_by="選擇列表排序方式", search="輸入伺服器名稱或 ID", feature_filter="篩選啟用特定功能的伺服器", guild_id="直接輸入伺服器 ID 查看詳情")
    @app_commands.choices(
        sort_by=[
            app_commands.Choice(name="人數最多", value="members_desc"),
            app_commands.Choice(name="人數最少", value="members_asc"),
            app_commands.Choice(name="最新加入", value="joined_desc"),
            app_commands.Choice(name="最早加入", value="joined_asc")
        ],
        feature_filter=[
            app_commands.Choice(name="所有伺服器", value="all"),
            app_commands.Choice(name="已授權伺服器", value="authorized"),
            app_commands.Choice(name="未授權伺服器", value="unauthorized"),
            app_commands.Choice(name="有設定排除身份組", value="excluded"),
            app_commands.Choice(name="有設定陷阱身份組", value="trap"),
            app_commands.Choice(name="TWERG 主伺服器", value="main_server")
        ]
    )
    @app_commands.guilds(518699949500661760, 897116721159233576)
    @app_commands.check(is_owner_check_interaction)
    async def guilds_command(self, interaction: discord.Interaction, 
                             sort_by: app_commands.Choice[str] = None, 
                             search: str = None, 
                             feature_filter: app_commands.Choice[str] = None, 
                             guild_id: str = None):
        await interaction.response.defer(ephemeral=True)

        guild_settings = get_honeypot_settings()
        config = get_bot_config()

        if guild_id:
            try:
                gid = int(guild_id)
                dummy_view = GuildsView(self.bot, [], guild_settings, interaction.user.id, False)
                dummy_view.is_detail_mode = True
                dummy_view.current_detail_guild_id = gid
                dummy_view.update_components()
                content, embed = await dummy_view.get_current_content_and_embed()
                await interaction.followup.send(content=content, embed=embed, view=dummy_view)
            except ValueError:
                await interaction.followup.send("❌ 錯誤的伺服器 ID 格式。")
            return

        filtered_guilds = []
        for guild in self.bot.guilds:
            if search:
                if search.lower() not in guild.name.lower() and search != str(guild.id):
                    continue
            
            if feature_filter and feature_filter.value != "all":
                g_settings = guild_settings.get(str(guild.id), {})
                val = feature_filter.value
                if val == "authorized" and not is_server_authorized(guild.id):
                    continue
                elif val == "unauthorized" and is_server_authorized(guild.id):
                    continue
                elif val == "excluded" and not g_settings.get("excluded_roles"):
                    continue
                elif val == "trap" and not g_settings.get("trap_roles"):
                    continue
                elif val == "main_server":
                    server_id = config.get("TWERG_SERVER_ID") or config.get("SERVER_ID")
                    if not server_id or guild.id != int(server_id):
                        continue
                    
            filtered_guilds.append(guild)

        sort_val = sort_by.value if sort_by else "members_desc"
        if sort_val == "members_desc":
            filtered_guilds.sort(key=lambda g: g.member_count, reverse=True)
        elif sort_val == "members_asc":
            filtered_guilds.sort(key=lambda g: g.member_count, reverse=False)
        elif sort_val == "joined_desc":
            filtered_guilds.sort(key=lambda g: g.me.joined_at if g.me and g.me.joined_at else discord.utils.utcnow(), reverse=True)
        elif sort_val == "joined_asc":
            filtered_guilds.sort(key=lambda g: g.me.joined_at if g.me and g.me.joined_at else discord.utils.utcnow(), reverse=False)

        if not filtered_guilds:
            await interaction.followup.send("❌ 找不到符合條件的伺服器。")
            return

        total_members = sum(g.member_count for g in self.bot.guilds)
        
        main_server_id = config.get("TWERG_SERVER_ID") or config.get("SERVER_ID")
        main_server = self.bot.get_guild(int(main_server_id)) if main_server_id else None
        main_server_str = f"**{main_server.name}** (`{main_server.id}`)" if main_server else (f"`{main_server_id}`" if main_server_id else "未設定")
        
        hp_id = config.get("HONEYPOT_ID")
        hp_channel = self.bot.get_channel(int(hp_id)) if hp_id else None
        hp_channel_str = hp_channel.mention if hp_channel else (f"`{hp_id}`" if hp_id else "未設定")
        
        cs_id = config.get("CONSOLE_ID")
        cs_channel = self.bot.get_channel(int(cs_id)) if cs_id else None
        cs_channel_str = cs_channel.mention if cs_channel else (f"`{cs_id}`" if cs_id else "未設定")

        stats_data = {
            "total_guilds": len(self.bot.guilds),
            "total_members": total_members,
            "auth_count": sum(1 for g in self.bot.guilds if is_server_authorized(g.id)),
            "excluded_count": sum(1 for g in self.bot.guilds if str(g.id) in guild_settings and guild_settings[str(g.id)].get("excluded_roles")),
            "trap_count": sum(1 for g in self.bot.guilds if str(g.id) in guild_settings and guild_settings[str(g.id)].get("trap_roles")),
            "delete_msg_count": sum(1 for g in self.bot.guilds if str(g.id) in guild_settings and guild_settings[str(g.id)].get("delete_messages", True)),
            "main_server_str": main_server_str,
            "honeypot_channel_str": hp_channel_str,
            "console_channel_str": cs_channel_str
        }

        show_stats = (search is None and (feature_filter is None or feature_filter.value == "all"))
        
        view = GuildsView(self.bot, filtered_guilds, guild_settings, interaction.user.id, show_stats, stats_data)
        content, embed = await view.get_current_content_and_embed()
        await interaction.followup.send(content=content, embed=embed, view=view)

    @guilds_command.error
    async def guilds_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 你沒有權限使用此指令。", ephemeral=True)
            else:
                await interaction.followup.send("❌ 你沒有權限使用此指令。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(GuildsCog(bot))