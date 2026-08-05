import discord
from settings.settings_utils import (
    load_honeypot_settings,
    load_ryker_settings,
    load_config,
    is_server_authorized
)
from settings.settings_roles import RoleSettingsView
from settings.settings_ryker import RykerSettingsView
from settings.settings_log import LogSettingsView
from settings.settings_honeypot import HoneypotSettingsView

class SettingsView(discord.ui.View):
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.guild_id_str = str(guild_id)
        self.message = None

        self.hp_all_settings = load_honeypot_settings()
        self.hp_settings = self.hp_all_settings.get(self.guild_id_str, {})
        
        self.ryker_all_settings = load_ryker_settings()
        self.ryker_settings = self.ryker_all_settings.get(self.guild_id_str, {})

        self.config = load_config()
        self.twerg_id = int(self.config.get("TWERG_SERVER_ID") or self.config.get("SERVER_ID", 518699949500661760))
        self.is_twerg = (self.guild_id == self.twerg_id)

        self._build_components()

    def _build_components(self):
        self.clear_items()

        # 1. 模組選擇下拉選單 (Row 0)
        options = [
            discord.SelectOption(label="白名單與身份組", value="roles", description="設定排除防護白名單與提及即封鎖的陷阱身份組", emoji="🛡️"),
            discord.SelectOption(label="Ryker 惡意帳號與門檻", value="ryker", description="設定發言監控門檻、潛水監控、聯防與 EEW 暫停", emoji="🚨"),
            discord.SelectOption(label="本伺服器防護日誌", value="log", description="設定本伺服器獨立處決與聯防日誌頻道", emoji="📡"),
            discord.SelectOption(label="蜜罐頻道防護", value="honeypot", description="查看蜜罐無聲誘捕與處決頻道狀態", emoji="🍯")
        ]

        self.select_menu = discord.ui.Select(
            placeholder="請選擇要調整的防護模組...",
            options=options,
            row=0
        )
        self.select_menu.callback = self.select_category_callback
        self.add_item(self.select_menu)

        # 2. 關閉按鈕 (Row 1)
        self.close_btn = discord.ui.Button(
            label="關閉設定",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            row=1
        )
        self.close_btn.callback = self.close_callback
        self.add_item(self.close_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_server_authorized(self.guild_id):
            await interaction.response.send_message("❌ 本伺服器尚未獲得機器人擁有者授權許可，暫無法開啟與調整設定。", ephemeral=True)
            return False
            
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有伺服器管理員才能操作此設定面板！", ephemeral=True)
            return False
        return True

    def get_content_and_embed(self, guild: discord.Guild):
        if not is_server_authorized(self.guild_id):
            embed = discord.Embed(
                description="❌ 本伺服器尚未獲得機器人擁有者授權許可，暫無法開啟與調整防護功能。\n\n請聯絡機器人擁有者申請授權。",
                color=discord.Color.red()
            )
            return "🔒 **伺服器未授權**", embed

        embed = discord.Embed(
            title="`⚙️` HoneyBot 伺服器防護設定面板",
            description="請從下方下拉選單選擇要調整或檢視的防護模組。",
            color=0x41809b
        )

        excluded_roles = self.hp_settings.get("excluded_roles", [])
        trap_roles = self.hp_settings.get("trap_roles", [])
        valid_excluded = [r for r in excluded_roles if guild.get_role(r) is not None]
        valid_trap = [r for r in trap_roles if guild.get_role(r) is not None]

        roles_status = f"`🟢` 已設定 ({len(valid_excluded)}白名單 / {len(valid_trap)}陷阱)" if (valid_excluded or valid_trap) else "`🔴` 未設定"
        
        threshold = self.ryker_settings.get("monitor_threshold", 10)
        is_lurker = self.ryker_settings.get("global_monitor", False)
        is_sync = self.ryker_settings.get("sync_ban", False)
        ryker_status = f"`🟢` 門檻: {threshold}次 (潛水:{'開' if is_lurker else '關'} | 聯防:{'開' if is_sync else '關'})"

        log_ch_id = self.hp_settings.get("log_channel_id")
        log_ch = guild.get_channel(int(log_ch_id)) if log_ch_id else None
        log_status = f"`🟢` {log_ch.mention}" if log_ch else "`🔴` 未設定"

        if self.is_twerg:
            hp_id = self.config.get("HONEYPOT_ID")
            hp_channel = guild.get_channel(int(hp_id)) if hp_id else None
            honeypot_status = f"`🟢` {hp_channel.mention}" if hp_channel else "`🔴` 未設定"
        else:
            honeypot_status = "`🚫` TWERG 專屬"

        embed.add_field(name="🛡️ 白名單與身份組", value=roles_status, inline=True)
        embed.add_field(name="🚨 Ryker 惡意帳號防護", value=ryker_status, inline=False)
        embed.add_field(name="📡 本伺服器防護日誌", value=log_status, inline=True)
        embed.add_field(name="🍯 蜜罐頻道防護", value=honeypot_status, inline=True)
        embed.set_footer(text="HoneyBot 蜜罐與惡意帳號雙重防護系統 v2.0")

        return "🛡️ **HoneyBot 防護與系統設定面板**", embed

    async def select_category_callback(self, interaction: discord.Interaction):
        val = self.select_menu.values[0]
        if val == "roles":
            view = RoleSettingsView(self.bot, self.guild_id)
            await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)
        elif val == "ryker":
            view = RykerSettingsView(self.bot, self.guild_id)
            await interaction.response.edit_message(embed=view.build_embed(), view=view)
        elif val == "log":
            view = LogSettingsView(self.bot, self.guild_id)
            await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)
        elif val == "honeypot":
            view = HoneypotSettingsView(self.bot, self.guild_id)
            await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)

    async def close_callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except Exception:
            pass
        try:
            await interaction.message.delete()
        except Exception:
            pass
        self.stop()