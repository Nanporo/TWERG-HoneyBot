import discord
from settings.settings_utils import load_ryker_settings, save_ryker_settings

class RykerSettingsView(discord.ui.View):
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.guild_id_str = str(guild_id)

        self.ryker_all_settings = load_ryker_settings()
        self.ryker_settings = self.ryker_all_settings.get(self.guild_id_str, {})
        self._build_components()

    def _build_components(self):
        self.clear_items()

        # 1. 監控門檻設定下拉選單 (Row 0)
        threshold = self.ryker_settings.get("monitor_threshold", 10)
        options = [
            discord.SelectOption(label="5 次發言門檻", value="5", description="極度嚴格：新用戶發言滿 5 次即畢業放行", default=(threshold == 5)),
            discord.SelectOption(label="10 次發言門檻 (預設)", value="10", description="標準防護：新用戶發言滿 10 次即畢業放行", default=(threshold == 10)),
            discord.SelectOption(label="15 次發言門檻", value="15", description="寬鬆防護：新用戶發言滿 15 次即畢業放行", default=(threshold == 15)),
            discord.SelectOption(label="20 次發言門檻", value="20", description="高強度防護：新用戶發言滿 20 次即畢業放行", default=(threshold == 20))
        ]
        self.threshold_select = discord.ui.Select(
            placeholder=f"目前發言監控門檻：{threshold} 次 (點擊調整)",
            options=options,
            row=0
        )
        self.threshold_select.callback = self.threshold_callback
        self.add_item(self.threshold_select)

        # 2. 核心模組開關按鈕組 1 (Row 1)
        # (A) 惡意破壞者黑名單比對 (bad_users)
        is_bad_users = self.ryker_settings.get("bad_users_enabled", True)
        btn_bad_users = discord.ui.Button(
            label="黑名單比對: 啟用" if is_bad_users else "黑名單比對: 停用",
            style=discord.ButtonStyle.green if is_bad_users else discord.ButtonStyle.red,
            emoji="🚨",
            row=1
        )
        btn_bad_users.callback = self._make_toggle_callback("bad_users_enabled", True)
        self.add_item(btn_bad_users)

        # (B) 受害者 / 保護對象標記防護 (target_users)
        is_target_users = self.ryker_settings.get("target_users_enabled", True)
        btn_target_users = discord.ui.Button(
            label="受害者標記: 啟用" if is_target_users else "受害者標記: 停用",
            style=discord.ButtonStyle.green if is_target_users else discord.ButtonStyle.red,
            emoji="🛡️",
            row=1
        )
        btn_target_users.callback = self._make_toggle_callback("target_users_enabled", True)
        self.add_item(btn_target_users)

        # (C) 敏感詞彙與正則比對 (bad_words)
        is_bad_words = self.ryker_settings.get("bad_words_enabled", True)
        btn_bad_words = discord.ui.Button(
            label="敏感詞比對: 啟用" if is_bad_words else "敏感詞比對: 停用",
            style=discord.ButtonStyle.green if is_bad_words else discord.ButtonStyle.red,
            emoji="🔤",
            row=1
        )
        btn_bad_words.callback = self._make_toggle_callback("bad_words_enabled", True)
        self.add_item(btn_bad_words)

        # 3. 核心模組開關按鈕組 2 (Row 2)
        # (D) 短時間圖片/附件洗板防護
        is_img_spam = self.ryker_settings.get("image_spam_enabled", True)
        btn_img_spam = discord.ui.Button(
            label="圖片洗板: 啟用" if is_img_spam else "圖片洗板: 停用",
            style=discord.ButtonStyle.green if is_img_spam else discord.ButtonStyle.red,
            emoji="🖼️",
            row=2
        )
        btn_img_spam.callback = self._make_toggle_callback("image_spam_enabled", True)
        self.add_item(btn_img_spam)

        # (E) Markdown 大字體洗板防護
        is_header_spam = self.ryker_settings.get("header_spam_enabled", True)
        btn_header_spam = discord.ui.Button(
            label="大字體洗板: 啟用" if is_header_spam else "大字體洗板: 停用",
            style=discord.ButtonStyle.green if is_header_spam else discord.ButtonStyle.red,
            emoji="📝",
            row=2
        )
        btn_header_spam.callback = self._make_toggle_callback("header_spam_enabled", True)
        self.add_item(btn_header_spam)

        # (F) EEW 地震速報連動暫停
        is_eew_pause = self.ryker_settings.get("eew_pause_enabled", True)
        btn_eew_pause = discord.ui.Button(
            label="EEW暫停: 啟用" if is_eew_pause else "EEW暫停: 停用",
            style=discord.ButtonStyle.green if is_eew_pause else discord.ButtonStyle.red,
            emoji="⚡",
            row=2
        )
        btn_eew_pause.callback = self._make_toggle_callback("eew_pause_enabled", True)
        self.add_item(btn_eew_pause)

        # 4. 全局模式與聯防按鈕 (Row 3)
        is_lurker = self.ryker_settings.get("global_monitor", False)
        btn_lurker = discord.ui.Button(
            label="潛水用戶監控: 啟用" if is_lurker else "潛水用戶監控: 停用",
            style=discord.ButtonStyle.green if is_lurker else discord.ButtonStyle.red,
            emoji="🔍",
            row=3
        )
        btn_lurker.callback = self._make_toggle_callback("global_monitor", False)
        self.add_item(btn_lurker)

        is_sync = self.ryker_settings.get("sync_ban", False)
        btn_sync = discord.ui.Button(
            label="共同BAN人: 啟用" if is_sync else "共同BAN人: 停用",
            style=discord.ButtonStyle.green if is_sync else discord.ButtonStyle.red,
            emoji="🤝",
            row=3
        )
        btn_sync.callback = self._make_toggle_callback("sync_ban", False)
        self.add_item(btn_sync)

        # 5. 返回按鈕 (Row 4)
        self.back_btn = discord.ui.Button(
            label="返回主設定",
            style=discord.ButtonStyle.secondary,
            emoji="↩️",
            row=4
        )
        self.back_btn.callback = self.back_callback
        self.add_item(self.back_btn)

    def _make_toggle_callback(self, key: str, default_val: bool):
        async def callback(interaction: discord.Interaction):
            curr = self.ryker_settings.get(key, default_val)
            self.ryker_settings[key] = not curr
            self.ryker_all_settings[self.guild_id_str] = self.ryker_settings
            save_ryker_settings(self.ryker_all_settings)
            self._build_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有伺服器管理員才能操作 Ryker 防護設定！", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="`🚨` 模組化防禦與門檻設定面板",
            description="各伺服器管理員可獨立選擇開啟或關閉以下防禦模組。",
            color=0x41809b
        )

        threshold = self.ryker_settings.get("monitor_threshold", 10)
        is_bad_users = self.ryker_settings.get("bad_users_enabled", True)
        is_target_users = self.ryker_settings.get("target_users_enabled", True)
        is_bad_words = self.ryker_settings.get("bad_words_enabled", True)
        is_img_spam = self.ryker_settings.get("image_spam_enabled", True)
        is_header_spam = self.ryker_settings.get("header_spam_enabled", True)
        is_eew_pause = self.ryker_settings.get("eew_pause_enabled", True)
        is_lurker = self.ryker_settings.get("global_monitor", False)
        is_sync = self.ryker_settings.get("sync_ban", False)

        embed.add_field(name="發言監控門檻", value=f"`{threshold}` 次發言", inline=False)

        def status_icon(flag): return "`🟢` 已啟用" if flag else "`🔴` 已停用"

        embed.add_field(name="🚨 惡意破壞者黑名單比對 (bad_users)", value=status_icon(is_bad_users), inline=True)
        embed.add_field(name="🛡️ 受害者/保護對象標記防護", value=status_icon(is_target_users), inline=True)
        embed.add_field(name="🔤 敏感詞彙與組合正則比對", value=status_icon(is_bad_words), inline=True)
        embed.add_field(name="🖼️ 短時間圖片/附件洗板防護", value=status_icon(is_img_spam), inline=True)
        embed.add_field(name="📝 Markdown 大字體洗板防護", value=status_icon(is_header_spam), inline=True)
        embed.add_field(name="⚡ EEW 地震速報連動暫停", value=status_icon(is_eew_pause), inline=True)
        embed.add_field(name="🔍 潛水用戶監控", value=status_icon(is_lurker), inline=True)
        embed.add_field(name="🤝 共同 BAN 人 (跨伺服器聯防)", value=status_icon(is_sync), inline=True)

        embed.set_footer(text="點擊下方按鈕即可動態開啟或關閉個別防禦模組。")
        return embed

    async def threshold_callback(self, interaction: discord.Interaction):
        val = int(self.threshold_select.values[0])
        self.ryker_settings["monitor_threshold"] = val
        self.ryker_all_settings[self.guild_id_str] = self.ryker_settings
        save_ryker_settings(self.ryker_all_settings)

        self._build_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def back_callback(self, interaction: discord.Interaction):
        from settings.settings_main import SettingsView
        main_view = SettingsView(self.bot, self.guild_id)
        content, embed = main_view.get_content_and_embed(interaction.guild)
        await interaction.response.edit_message(content=content, embed=embed, view=main_view)
