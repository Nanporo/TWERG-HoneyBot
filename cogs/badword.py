import discord
from discord.ext import commands
from discord import app_commands
import datetime
from cogs.owner import is_user_trusted
from cogs.server_check import is_server_authorized
from settings.settings_utils import (
    add_custom_bad_word,
    remove_custom_bad_word,
    list_custom_bad_words_detail,
)

# -------------------------------------------------------
# 自訂敏感詞管理 Cog (單一 /詞庫 指令)
# -------------------------------------------------------

class BadWordCog(commands.Cog):
    """動態自訂敏感詞庫管理 Cog"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="詞庫", description="[管理員/信任者] 管理敏感詞庫（新增 / 移除 / 列表 / 全域管理）")
    @app_commands.describe(
        操作="要執行的動作（新增、移除、列表、全域管理）",
        詞彙="要新增或移除的詞彙（查看列表時可不填）"
    )
    @app_commands.choices(操作=[
        app_commands.Choice(name="➕ 新增 (本伺服器)", value="add"),
        app_commands.Choice(name="➖ 移除 (本伺服器)", value="remove"),
        app_commands.Choice(name="📋 列表 (查看詞庫清單)", value="list"),
        app_commands.Choice(name="🌐 新增全域 (信任者 / 擁有者)", value="add_global"),
        app_commands.Choice(name="🗑️ 移除全域 (信任者 / 擁有者)", value="remove_global"),
    ])
    async def badword_command(
        self,
        interaction: discord.Interaction,
        操作: app_commands.Choice[str],
        詞彙: str = None
    ):
        # 1. 檢查伺服器授權
        if not is_server_authorized(interaction.guild_id):
            await interaction.response.send_message(
                "❌ 此伺服器尚未獲得機器人授權，無法使用此功能。", ephemeral=True
            )
            return

        # 2. 檢查使用者權限（伺服器管理員 或 信任者）
        is_admin = interaction.user.guild_permissions.administrator if isinstance(interaction.user, discord.Member) else False
        is_trusted = is_user_trusted(interaction.user.id)

        if not (is_admin or is_trusted):
            await interaction.response.send_message(
                "❌ 你沒有權限使用此指令！（需要伺服器管理員或機器人信任者權限）", ephemeral=True
            )
            return

        action = 操作.value
        word = (詞彙 or "").strip()

        # 2. 列表功能 (無需詞彙參數)
        if action == "list":
            words = list_custom_bad_words_detail(str(interaction.guild_id))
            if not words:
                await interaction.response.send_message(
                    "📋 目前尚未新增任何自訂敏感詞。\n（靜態底層詞庫不在此列出，請查閱 `ryker_keywords.py`）",
                    ephemeral=True
                )
                return

            global_words = [w for w in words if w["scope"] == "全域"]
            server_words = [w for w in words if w["scope"] == "本伺服器"]

            embed = discord.Embed(
                title="📋 自訂敏感詞庫列表",
                color=discord.Color.blurple(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text="靜態底層詞庫（ryker_keywords.py）的詞彙不在此顯示")

            if global_words:
                lines = [f"`{w['word']}` — 由 {w['added_by']}" for w in global_words]
                embed.add_field(
                    name=f"全域詞彙（{len(global_words)} 筆）",
                    value="\n".join(lines) or "（無）",
                    inline=False
                )

            if server_words:
                lines = [f"`{w['word']}` — 由 {w['added_by']}" for w in server_words]
                embed.add_field(
                    name=f"本伺服器詞彙（{len(server_words)} 筆）",
                    value="\n".join(lines) or "（無）",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 3. 其他操作需要詞彙參數
        if not word:
            await interaction.response.send_message(
                f"❌ 執行「{操作.name}」操作時，必須填寫 `詞彙` 參數！",
                ephemeral=True
            )
            return

        if len(word) > 100:
            await interaction.response.send_message("❌ 詞彙長度不可超過 100 字元。", ephemeral=True)
            return

        added_by = f"{interaction.user.display_name} ({interaction.user.id})"

        # 4. 新增至本伺服器
        if action == "add":
            success = add_custom_bad_word(str(interaction.guild_id), word, added_by)
            if success:
                embed = discord.Embed(
                    title="✅ 自訂敏感詞新增成功",
                    description=f"詞彙 `{word}` 已加入本伺服器詞庫，即時生效。",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.set_footer(text=f"新增者：{interaction.user.display_name}")
                print(f"📝 [BadWord] 新增伺服器詞彙: '{word}' by {added_by} in guild {interaction.guild_id}")
            else:
                embed = discord.Embed(
                    title="⚠️ 詞彙已存在",
                    description=f"詞彙 `{word}` 已在本伺服器詞庫或全域詞庫中，無需重複新增。",
                    color=discord.Color.orange()
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # 5. 從本伺服器移除
        elif action == "remove":
            success = remove_custom_bad_word(str(interaction.guild_id), word)
            if success:
                embed = discord.Embed(
                    title="🗑️ 自訂敏感詞移除成功",
                    description=f"詞彙 `{word}` 已從本伺服器詞庫移除。",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                print(f"🗑️ [BadWord] 移除伺服器詞彙: '{word}' by {interaction.user} in guild {interaction.guild_id}")
            else:
                embed = discord.Embed(
                    title="❌ 詞彙不存在",
                    description=f"詞彙 `{word}` 不在本伺服器詞庫中。\n（注意：全域詞彙請由 Bot 擁有者選擇「移除全域」進行移除。）",
                    color=discord.Color.red()
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # 6. 新增全域 (Bot 擁有者)
        elif action == "add_global":
            if not is_user_trusted(interaction.user.id):
                await interaction.response.send_message("❌ 此操作僅限 Bot 擁有者使用。", ephemeral=True)
                return

            success = add_custom_bad_word("GLOBAL", word, added_by)
            if success:
                embed = discord.Embed(
                    title="✅ 全域敏感詞新增成功",
                    description=f"詞彙 `{word}` 已加入**全域詞庫**，即時對所有伺服器生效。",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.set_footer(text=f"新增者：{interaction.user.display_name}")
                print(f"🌐 [BadWord] 新增全域詞彙: '{word}' by {added_by}")
            else:
                embed = discord.Embed(
                    title="⚠️ 詞彙已存在",
                    description=f"詞彙 `{word}` 已在全域詞庫中。",
                    color=discord.Color.orange()
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # 7. 移除全域 (Bot 擁有者)
        elif action == "remove_global":
            if not is_user_trusted(interaction.user.id):
                await interaction.response.send_message("❌ 此操作僅限 Bot 擁有者使用。", ephemeral=True)
                return

            success = remove_custom_bad_word("GLOBAL", word)
            if success:
                embed = discord.Embed(
                    title="🗑️ 全域敏感詞移除成功",
                    description=f"詞彙 `{word}` 已從全域詞庫移除，即時生效。",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                print(f"🌐 [BadWord] 移除全域詞彙: '{word}' by {interaction.user}")
            else:
                embed = discord.Embed(
                    title="❌ 詞彙不存在",
                    description=f"詞彙 `{word}` 不在全域詞庫中。",
                    color=discord.Color.red()
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(BadWordCog(bot))
