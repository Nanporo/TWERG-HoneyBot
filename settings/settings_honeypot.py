import discord
from settings.settings_utils import load_config

class HoneypotSettingsView(discord.ui.View):
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.message = None
        self.config = load_config()
        self.twerg_id = int(self.config.get("TWERG_SERVER_ID") or self.config.get("SERVER_ID", 518699949500661760))
        self.is_twerg = (self.guild_id == self.twerg_id)
        self._build_components()

    def _build_components(self):
        self.clear_items()
        # 返回按鈕 (Row 0)
        self.back_btn = discord.ui.Button(
            label="返回主設定",
            style=discord.ButtonStyle.secondary,
            emoji="↩️",
            row=0
        )
        self.back_btn.callback = self.back_callback
        self.add_item(self.back_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有伺服器管理員才能查看蜜罐防護設定！", ephemeral=True)
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

    def build_embed(self, guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed(
            title="`🍯` 蜜罐頻道防護設定",
            description="蜜罐頻道防護為 TWERG 主伺服器專屬的誘捕機制。",
            color=0x41809b
        )

        if self.is_twerg:
            hp_id = self.config.get("HONEYPOT_ID")
            hp_channel = guild.get_channel(int(hp_id)) if hp_id else None
            hp_str = f"🟢 {hp_channel.mention}" if hp_channel else "`🔴` 未設定"
            status_desc = "已於 TWERG 主伺服器正常啟用。任何非白名單成員在蜜罐頻道內發言將立即被自動 BAN 出伺服器。"
        else:
            hp_str = "`🚫` 非本伺服器功能"
            status_desc = "蜜罐防護目前僅開放在 TWERG 主伺服器運作。"

        embed.add_field(name="蜜罐頻道對應", value=hp_str, inline=False)
        embed.add_field(name="說明與運作狀態", value=status_desc, inline=False)
        embed.set_footer(text="可於 /設定 白名單中指定免受蜜罐處決的身份組")

        return embed

    async def back_callback(self, interaction: discord.Interaction):
        from settings.settings_main import SettingsView
        main_view = SettingsView(self.bot, self.guild_id)
        main_view.message = self.message
        content, embed = main_view.get_content_and_embed(interaction.guild)
        await interaction.response.edit_message(content=content, embed=embed, view=main_view)
