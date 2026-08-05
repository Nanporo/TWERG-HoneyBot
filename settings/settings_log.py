import discord
from settings.settings_utils import load_guild_settings, save_guild_settings

class LogSettingsView(discord.ui.View):
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.guild_id_str = str(guild_id)

        self.hp_settings = load_guild_settings(self.guild_id)
        self._build_components()

    def _build_components(self):
        self.clear_items()

        # 1. 防護日誌頻道選單 (Row 0)
        self.log_channel_select = discord.ui.ChannelSelect(
            placeholder="選擇本伺服器防護日誌紀錄頻道 (可選, 清除則停用)",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=0
        )
        self.log_channel_select.callback = self.log_channel_callback
        self.add_item(self.log_channel_select)

        # 2. 返回按鈕 (Row 1)
        self.back_btn = discord.ui.Button(
            label="返回主設定",
            style=discord.ButtonStyle.secondary,
            emoji="↩️",
            row=1
        )
        self.back_btn.callback = self.back_callback
        self.add_item(self.back_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有伺服器管理員才能操作防護日誌設定！", ephemeral=True)
            return False
        return True

    def build_embed(self, guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed(
            title="`📡` 本伺服器獨立防護日誌設定",
            description="指定一個文字頻道作為本伺服器的防護事件紀錄日誌，不會收到機器人其他伺服器的無關 Console 底層調試訊息。",
            color=0x41809b
        )

        log_ch_id = self.hp_settings.get("log_channel_id")
        log_ch = guild.get_channel(int(log_ch_id)) if log_ch_id else None
        log_str = f"🟢 {log_ch.mention}" if log_ch else "`🔴` 未設定 (僅記錄於中央主日誌)"

        embed.add_field(name="目前防護日誌頻道", value=log_str, inline=False)
        embed.add_field(
            name="📋 包含的紀錄事件類型",
            value=(
                "• 🚨 **蜜罐自動 BAN** (蜜罐頻道發言處決)\n"
                "• 🚨 **陷阱身份組自動 BAN** (提及陷阱身份組處決)\n"
                "• 🚨 **惡意帳號自動處決** (3 天禁言通報)\n"
                "• 🔨 **管理員按鈕處決** (管理員處決與黑名單自動加入紀錄)\n"
                "• 🤝 **跨伺服器聯防同步 BAN** (源自其他伺服器的聯防預先封鎖紀錄)"
            ),
            inline=False
        )
        embed.set_footer(text="點擊下方選單指定本伺服器的文字頻道")

        return embed

    async def log_channel_callback(self, interaction: discord.Interaction):
        if self.log_channel_select.values:
            cid = self.log_channel_select.values[0].id
            self.hp_settings["log_channel_id"] = cid
        else:
            self.hp_settings["log_channel_id"] = None

        save_guild_settings(self.guild_id, self.hp_settings)

        self._build_components()
        await interaction.response.edit_message(embed=self.build_embed(interaction.guild), view=self)

    async def back_callback(self, interaction: discord.Interaction):
        from settings.settings_main import SettingsView
        main_view = SettingsView(self.bot, self.guild_id)
        content, embed = main_view.get_content_and_embed(interaction.guild)
        await interaction.response.edit_message(content=content, embed=embed, view=main_view)
