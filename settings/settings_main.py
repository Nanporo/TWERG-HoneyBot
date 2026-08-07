import discord
from settings.settings_utils import (
    load_guild_settings,
    load_config,
    is_server_authorized
)
from settings.settings_roles import RoleSettingsView
from settings.settings_bad_users import BadUsersSettingsView
from settings.settings_log import LogSettingsView
from settings.settings_honeypot import HoneypotSettingsView

class SettingsView(discord.ui.View):
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.guild_id_str = str(guild_id)
        self.message = None

        self.guild_settings = load_guild_settings(self.guild_id)
        self.hp_settings = self.guild_settings
        self.ryker_settings = self.guild_settings

        self.config = load_config()
        self.twerg_id = int(self.config.get("TWERG_SERVER_ID") or self.config.get("SERVER_ID", 518699949500661760))
        self.is_twerg = (self.guild_id == self.twerg_id)

        self._build_components()

    def _build_components(self):
        self.clear_items()

        # 1. 功能模組導覽按鈕 (Row 0 & Row 1)
        btn_roles = discord.ui.Button(
            label="白名單與身份組",
            style=discord.ButtonStyle.primary,
            emoji="🛡️",
            row=0
        )
        btn_roles.callback = self._make_category_callback("roles")
        self.add_item(btn_roles)

        btn_ryker = discord.ui.Button(
            label="惡意帳號與門檻",
            style=discord.ButtonStyle.primary,
            emoji="🚨",
            row=0
        )
        btn_ryker.callback = self._make_category_callback("ryker")
        self.add_item(btn_ryker)

        btn_log = discord.ui.Button(
            label="伺服器防護日誌",
            style=discord.ButtonStyle.primary,
            emoji="📡",
            row=1
        )
        btn_log.callback = self._make_category_callback("log")
        self.add_item(btn_log)

        btn_honeypot = discord.ui.Button(
            label="蜜罐頻道防護",
            style=discord.ButtonStyle.primary,
            emoji="🍯",
            row=1
        )
        btn_honeypot.callback = self._make_category_callback("honeypot")
        self.add_item(btn_honeypot)

        # 2. 關閉按鈕 (Row 2)
        self.close_btn = discord.ui.Button(
            label="關閉設定",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            row=2
        )
        self.close_btn.callback = self.close_callback
        self.add_item(self.close_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_server_authorized(self.guild_id):
            await interaction.response.send_message("❌ 本伺服器尚未獲得機器人擁有者授權許可，暫無法開啟與調整設定。", ephemeral=True)
            return False
            
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有伺服器管理員才能操作此設定面板！", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            try:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except Exception:
                pass

    def get_content_and_embed(self, guild: discord.Guild):
        if not is_server_authorized(self.guild_id):
            embed = discord.Embed(
                description="❌ 本伺服器尚未獲得機器人擁有者授權許可，暫無法開啟與調整防護功能。\n\n請聯絡機器人擁有者申請授權。",
                color=discord.Color.red()
            )
            return "🔒 **伺服器未授權**", embed

        embed = discord.Embed(
            title="`⚙️` HoneyBot 伺服器防護設定面板",
            description="點擊下方按鈕可進入對應的防護模組進行詳細調整。",
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
        ryker_status = f"`🟢` 門檻: {threshold}次 (嚴格:{'開' if is_lurker else '關'} | 聯防:{'開' if is_sync else '關'})"

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
        embed.add_field(name="🚨 惡意帳號防護", value=ryker_status, inline=False)
        embed.add_field(name="📡 伺服器防護日誌", value=log_status, inline=True)
        embed.add_field(name="🍯 蜜罐頻道防護", value=honeypot_status, inline=True)
        embed.set_footer(text="TWERG HoneyBot 防護系統")

        return "🛡️ **HoneyBot 防護與系統設定面板**", embed

    def _make_category_callback(self, category: str):
        async def callback(interaction: discord.Interaction):
            if category == "roles":
                view = RoleSettingsView(self.bot, self.guild_id)
                view.message = self.message
                await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)
            elif category == "ryker":
                view = BadUsersSettingsView(self.bot, self.guild_id)
                view.message = self.message
                await interaction.response.edit_message(embed=view.build_embed(), view=view)
            elif category == "log":
                view = LogSettingsView(self.bot, self.guild_id)
                view.message = self.message
                await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)
            elif category == "honeypot":
                view = HoneypotSettingsView(self.bot, self.guild_id)
                view.message = self.message
                await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)
        return callback

    async def close_callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.edit_message(
                content="🔒 **已關閉 HoneyBot 伺服器防護設定面板。**",
                embed=None,
                view=None
            )
        except Exception:
            try:
                await interaction.delete_original_response()
            except Exception:
                pass
        self.stop()