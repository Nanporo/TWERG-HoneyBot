import discord
from settings.settings_utils import load_guild_settings, save_guild_settings

class RoleSettingsView(discord.ui.View):
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.guild_id_str = str(guild_id)

        self.hp_settings = load_guild_settings(self.guild_id)
        self._build_components()

    def _build_components(self):
        self.clear_items()

        # 1. 排除防護身份組選單 (Row 0)
        self.excluded_select = discord.ui.RoleSelect(
            placeholder="請選擇排除防護的白名單身份組 (可複選)...",
            min_values=0,
            max_values=20,
            row=0
        )
        self.excluded_select.callback = self.excluded_callback
        self.add_item(self.excluded_select)

        # 2. 陷阱身份組選單 (Row 1)
        self.trap_select = discord.ui.RoleSelect(
            placeholder="選擇陷阱身份組 (提及即封鎖, 可複選)...",
            min_values=0,
            max_values=20,
            row=1
        )
        self.trap_select.callback = self.trap_callback
        self.add_item(self.trap_select)

        # 3. 按鈕組 (Row 2)
        is_del = self.hp_settings.get("delete_messages", True)
        self.toggle_del_btn = discord.ui.Button(
            label="刪除30分訊息: 已啟用" if is_del else "刪除30分訊息: 已停用",
            style=discord.ButtonStyle.green if is_del else discord.ButtonStyle.red,
            emoji="🗑️",
            row=2
        )
        self.toggle_del_btn.callback = self.toggle_del_callback
        self.add_item(self.toggle_del_btn)

        # 4. 返回按鈕 (Row 3)
        self.back_btn = discord.ui.Button(
            label="返回主設定",
            style=discord.ButtonStyle.secondary,
            emoji="↩️",
            row=3
        )
        self.back_btn.callback = self.back_callback
        self.add_item(self.back_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有伺服器管理員才能操作身份組防護設定！", ephemeral=True)
            return False
        return True

    def build_embed(self, guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed(
            title="`🛡️` 白名單與身份組防護設定",
            description="設定免疫機器人自動懲罰的白名單身份組，以及提及即自動 BAN 的陷阱身份組。",
            color=0x41809b
        )

        excluded_roles = self.hp_settings.get("excluded_roles", [])
        trap_roles = self.hp_settings.get("trap_roles", [])
        delete_messages = self.hp_settings.get("delete_messages", True)

        valid_excluded = [r for r in excluded_roles if guild.get_role(r) is not None]
        valid_trap = [r for r in trap_roles if guild.get_role(r) is not None]

        excluded_str = ", ".join([f"<@&{r}>" for r in valid_excluded]) if valid_excluded else "無"
        trap_str = ", ".join([f"<@&{r}>" for r in valid_trap]) if valid_trap else "無"
        delete_msg_str = "`🟢` 已啟用 (封鎖時同步清理近30分鐘歷史訊息)" if delete_messages else "`🔴` 已停用"

        embed.add_field(name="排除防護身份組 (白名單)", value=excluded_str, inline=False)
        embed.add_field(name="陷阱身份組 (提及即封鎖)", value=trap_str, inline=False)
        embed.add_field(name="封鎖時刪除近 30 分鐘訊息", value=delete_msg_str, inline=False)
        embed.set_footer(text="點擊下方選單隨時新增或移除身份組")

        return embed

    async def excluded_callback(self, interaction: discord.Interaction):
        roles = [r.id for r in self.excluded_select.values]
        self.hp_settings["excluded_roles"] = roles
        save_guild_settings(self.guild_id, self.hp_settings)
        
        self._build_components()
        await interaction.response.edit_message(embed=self.build_embed(interaction.guild), view=self)

    async def trap_callback(self, interaction: discord.Interaction):
        roles = [r.id for r in self.trap_select.values]
        self.hp_settings["trap_roles"] = roles
        save_guild_settings(self.guild_id, self.hp_settings)

        self._build_components()
        await interaction.response.edit_message(embed=self.build_embed(interaction.guild), view=self)

    async def toggle_del_callback(self, interaction: discord.Interaction):
        curr = self.hp_settings.get("delete_messages", True)
        self.hp_settings["delete_messages"] = not curr
        save_guild_settings(self.guild_id, self.hp_settings)

        self._build_components()
        await interaction.response.edit_message(embed=self.build_embed(interaction.guild), view=self)

    async def back_callback(self, interaction: discord.Interaction):
        from settings.settings_main import SettingsView
        main_view = SettingsView(self.bot, self.guild_id)
        content, embed = main_view.get_content_and_embed(interaction.guild)
        await interaction.response.edit_message(content=content, embed=embed, view=main_view)
