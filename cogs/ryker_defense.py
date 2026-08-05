import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import sqlite3
import re
import difflib
import datetime
from ryker_keywords import (
    BAD_WORDS, 
    REGEX_PATTERNS, 
    NICKNAME_EXCLUDED_WORDS, 
    EXEMPTED_INTERJECTIONS, 
    TARGET_USERS,
    SEED_BAD_USERS
)
from cogs.owner import is_user_trusted
from cogs.server_check import is_server_authorized
from settings.settings_utils import send_server_log

# 引入 6 大模組化防禦組件
from defense_modules.defense_eew import process_eew_event, is_eew_paused
from defense_modules.defense_bad_users import check_bad_users
from defense_modules.defense_target_users import check_target_users
from defense_modules.defense_image_spam import check_image_spam
from defense_modules.defense_header_spam import check_header_spam
from defense_modules.defense_bad_words import check_bad_words

def get_ryker_settings() -> dict:
    settings_file = 'ryker_settings.json'
    if not os.path.exists(settings_file):
        return {}
    try:
        with open(settings_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_ryker_settings(data: dict):
    settings_file = 'ryker_settings.json'
    try:
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"⚠️ [幹男防護] 儲存 ryker_settings.json 失敗: {e}")

class RykerAdminActionView(discord.ui.View):
    """供管理員快速處置處決/洗板用戶的按鈕 UI 視圖"""
    def __init__(self, target_user: discord.User | discord.Member, timeout: float = 86400):
        super().__init__(timeout=timeout)
        self.target_user = target_user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ 無法在此處驗證管理員權限。", ephemeral=True)
            return False

        is_muted = False
        try:
            is_muted = interaction.user.is_timed_out()
        except Exception:
            if getattr(interaction.user, "timed_out_until", None):
                is_muted = interaction.user.timed_out_until > discord.utils.utcnow()

        if is_muted:
            await interaction.response.send_message("❌ 你正在被禁言，無法進行操作！", ephemeral=True)
            return False

        perms = interaction.user.guild_permissions
        if not (perms.administrator or perms.ban_members):
            await interaction.response.send_message("❌ 你必須擁有伺服器管理員或封鎖成員權限才能執行此操作！", ephemeral=True)
            return False

        # 身分組階層防越權檢查：非伺服器群主不能處置身分組高於或等於自己的成員
        if isinstance(self.target_user, discord.Member) and interaction.user.id != interaction.guild.owner_id:
            if interaction.user.top_role <= self.target_user.top_role:
                await interaction.response.send_message("❌ 你無法對身分組順位高於或等於自己的成員執行處置！", ephemeral=True)
                return False

        return True

    @discord.ui.button(label="停權（全域）", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            bot_member = interaction.guild.get_member(interaction.client.user.id) or await interaction.guild.fetch_member(interaction.client.user.id)
            if not bot_member.guild_permissions.ban_members:
                await interaction.response.send_message("⚠️ 機器人缺少「封鎖成員」權限，無法執行停權。", ephemeral=True)
                return

            await interaction.guild.ban(
                discord.Object(id=self.target_user.id),
                reason=f"管理員 {interaction.user} ({interaction.user.id}) 按鈕操作：停權（全域）",
                delete_message_seconds=0
            )

            print(f"🔨 [幹男防護 - 按鈕BAN] 伺服器: {interaction.guild.name} ({interaction.guild.id}) | 操作人: {interaction.user} ({interaction.user.id}) | 被操作人: {self.target_user} ({self.target_user.id})")

            # 自動將管理員點擊處決的惡意帳號寫入 ryker_targets.db 黑名單庫 (bad_users)
            db_added_msg = ""
            cog = interaction.client.get_cog("RykerDefenseCog")
            if cog:
                added_by_info = f"管理員 {interaction.user} ({interaction.user.id}) [於 {interaction.guild.name}] 按鈕處決"
                success = cog.add_bad_user(self.target_user.id, added_by_info)
                if success:
                    db_added_msg = "\n🛡️ **黑名單連動**：已自動將該帳號加入惡意帳號庫 (bad_users)！"

            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(view=self)
            
            sync_msg = ""
            # 檢查共同 BAN 人 (跨伺服器聯防封鎖)
            all_settings = get_ryker_settings()
            curr_g_settings = all_settings.get(str(interaction.guild.id), {})
            if curr_g_settings.get("sync_ban", False):
                banned_guilds = []
                for g in interaction.client.guilds:
                    if g.id == interaction.guild.id:
                        continue
                    if is_server_authorized(g.id) and all_settings.get(str(g.id), {}).get("sync_ban", False):
                        b_member = g.get_member(interaction.client.user.id)
                        if b_member and b_member.guild_permissions.ban_members:
                            try:
                                await g.ban(discord.Object(id=self.target_user.id), reason=f"Ryker 跨伺服器聯防封鎖 (源自伺服器 {interaction.guild.name})")
                                banned_guilds.append(g.name)
                                print(f"🤝 [幹男防護 - 聯防同步BAN] 目標伺服器: {g.name} ({g.id}) | 源自伺服器: {interaction.guild.name} ({interaction.guild.id}) | 操作人: {interaction.user} ({interaction.user.id}) | 被操作人: {self.target_user} ({self.target_user.id})")
                                
                                # 抄送紀錄至聯防目標伺服器的專屬日誌頻道
                                embed_sync_log = discord.Embed(
                                    description=(
                                        f"🤝 **[跨伺服器聯防] 同步預先封鎖**\n\n"
                                        f"• **源自伺服器**：**{interaction.guild.name}**\n"
                                        f"• **觸發管理員**：{interaction.user.mention} (`{interaction.user.id}`)\n"
                                        f"• **封鎖用戶**：<@{self.target_user.id}> (`{self.target_user.id}`)\n"
                                        f"• **狀態**：本伺服器已自動同步執行封鎖預防進入"
                                    ),
                                    color=discord.Color.dark_red()
                                )
                                embed_sync_log.set_footer(text="TWERG HoneyBot - 跨伺服器聯防日誌")
                                await send_server_log(g, embed_sync_log)
                            except Exception:
                                pass
                if banned_guilds:
                    sync_msg = f"\n🤝 **跨伺服器聯防**：已同步預先封鎖至 {len(banned_guilds)} 個伺服器 ({', '.join(banned_guilds)})。"

            await interaction.followup.send(
                f"🔨 已由管理員 {interaction.user.mention} 成功將用戶 {self.target_user.mention} (`{self.target_user.name}`) **停權（全域封鎖）**。{sync_msg}{db_added_msg}"
            )

            # 抄送紀錄至目前伺服器的專屬日誌頻道
            embed_local_log = discord.Embed(
                description=(
                    f"🔨 **[管理員處決] 停權（全域）**\n\n"
                    f"• **操作管理員**：{interaction.user.mention} (`{interaction.user.id}`)\n"
                    f"• **處決用戶**：{self.target_user.mention} (`{self.target_user.id}`)\n"
                    f"• **狀態**：已於本伺服器封鎖，並已同步加入惡意帳號庫！"
                ),
                color=discord.Color.red()
            )
            embed_local_log.set_footer(text="TWERG HoneyBot - 伺服器防護日誌")
            await send_server_log(interaction.guild, embed_local_log)
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ 機器人權限不足或對象層級高於機器人，無法執行停權。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"⚠️ 執行停權時發生錯誤: {e}", ephemeral=True)

    @discord.ui.button(label="踢出", style=discord.ButtonStyle.secondary, emoji="👢")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            bot_member = interaction.guild.get_member(interaction.client.user.id) or await interaction.guild.fetch_member(interaction.client.user.id)
            if not bot_member.guild_permissions.kick_members:
                await interaction.response.send_message("⚠️ 機器人缺少「踢出成員」權限，無法執行踢出。", ephemeral=True)
                return

            member = interaction.guild.get_member(self.target_user.id)
            if not member:
                try:
                    member = await interaction.guild.fetch_member(self.target_user.id)
                except discord.NotFound:
                    member = None

            if member:
                await member.kick(reason=f"管理員 {interaction.user} ({interaction.user.id}) 按鈕操作：踢出伺服器")
                print(f"👢 [幹男防護 - 按鈕踢出] 伺服器: {interaction.guild.name} ({interaction.guild.id}) | 操作人: {interaction.user} ({interaction.user.id}) | 被操作人: {self.target_user} ({self.target_user.id})")
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(view=self)
                await interaction.followup.send(
                    f"👢 已由管理員 {interaction.user.mention} 成功將用戶 {self.target_user.mention} (`{self.target_user.name}`) **踢出伺服器**。"
                )
            else:
                await interaction.response.send_message(f"⚠️ 用戶 `{self.target_user.name}` 已不在伺服器中。", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ 機器人權限不足或對象層級高於機器人，無法執行踢出。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"⚠️ 執行踢出時發生錯誤: {e}", ephemeral=True)

    @discord.ui.button(label="解除禁言", style=discord.ButtonStyle.success, emoji="🔓")
    async def untimeout_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            bot_member = interaction.guild.get_member(interaction.client.user.id) or await interaction.guild.fetch_member(interaction.client.user.id)
            if not bot_member.guild_permissions.moderate_members:
                await interaction.response.send_message("⚠️ 機器人缺少「停權成員 (Timeout)」權限，無法解除禁言。", ephemeral=True)
                return

            member = interaction.guild.get_member(self.target_user.id)
            if not member:
                try:
                    member = await interaction.guild.fetch_member(self.target_user.id)
                except discord.NotFound:
                    member = None

            if member:
                await member.timeout(None, reason=f"管理員 {interaction.user} ({interaction.user.id}) 按鈕操作：解除禁言")
                print(f"🔓 [幹男防護 - 按鈕解禁] 伺服器: {interaction.guild.name} ({interaction.guild.id}) | 操作人: {interaction.user} ({interaction.user.id}) | 被操作人: {self.target_user} ({self.target_user.id})")
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(view=self)
                await interaction.followup.send(
                    f"🔓 已由管理員 {interaction.user.mention} 成功解除用戶 {self.target_user.mention} (`{self.target_user.name}`) 的禁言狀態。"
                )
            else:
                await interaction.response.send_message(f"⚠️ 用戶 `{self.target_user.name}` 已不在伺服器中。", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ 機器人權限不足或對象層級高於機器人，無法解除禁言。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"⚠️ 執行解除禁言時發生錯誤: {e}", ephemeral=True)

class RykerBatchBanView(discord.ui.View):
    """供擁有者/信任人一鍵將黑名單用戶自當前伺服器全數封鎖的按鈕視圖"""
    def __init__(self, target_list: list, author_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.target_list = target_list
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not is_user_trusted(interaction.user.id):
            await interaction.response.send_message("❌ 這個按鈕只能由指令發起者或信任人員操作！", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="一鍵封鎖清單內所有惡意帳號", style=discord.ButtonStyle.danger, emoji="⚡")
    async def batch_ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        bot_member = interaction.guild.get_member(interaction.client.user.id) or await interaction.guild.fetch_member(interaction.client.user.id)
        if not bot_member.guild_permissions.ban_members:
            await interaction.followup.send("⚠️ 機器人缺少「封鎖成員」權限，無法執行封鎖。", ephemeral=True)
            return

        banned_count = 0
        failed_count = 0

        for uid in self.target_list:
            try:
                await interaction.guild.ban(
                    discord.Object(id=uid),
                    reason=f"管理員 {interaction.user} ({interaction.user.id}) 批次清空黑名單",
                    delete_message_seconds=0
                )
                banned_count += 1
            except Exception:
                failed_count += 1

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        print(f"⚡ [幹男防護 - 一鍵BAN] 伺服器: {interaction.guild.name} ({interaction.guild.id}) | 操作人: {interaction.user} ({interaction.user.id}) | 成功: {banned_count} 人 | 失敗: {failed_count} 人")
        await interaction.followup.send(
            f"⚡ 已完成一鍵封鎖操作！成功封鎖 `{banned_count}` 個惡意帳號，失敗 `{failed_count}` 個。",
            ephemeral=True
        )

class RykerDefenseCog(commands.Cog):
    """
    Ryker 防護與發言監控系統 2.0 (獨立資料庫版)
    支援：
    1. 雙資料庫體系：counts.db (活躍) + counts_archive.db (歸檔)
    2. ryker_targets.db：優先惡意帳號黑名單
    3. EEW 速報連動暫停與跨伺服器聯防封鎖
    4. 完整移植所有敏感詞、組合正則特徵、大字體洗板、圖片洗板、重複訊息比對與暱稱比對防線
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_counts = 'counts.db'
        self.db_archive = 'counts_archive.db'
        self.db_badusers = 'ryker_badusers.db'
        self.db_targets = self.db_badusers
        
        self.user_msg_history = {}     # {author_id_str: [(timestamp, norm_content, raw_content)]}
        self.user_img_history = {}     # {author_id_str: [timestamp, ...]}
        self.user_header_history = {}  # {author_id_str: [is_header_bool, ...]}
        self.eew_pause_until = 0.0     # 地震速報連動暫停截止時間戳

        # 初始化資料庫
        self._init_all_dbs()
        self._migrate_legacy_dbs()

        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    def _normalize_text(self, text: str) -> str:
        """過濾文字中的標點符號、空格、特殊字元並統一轉小寫，防止繞過關鍵字"""
        if not text:
            return ""
        return re.sub(r'[\s\W_]+', '', text, flags=re.UNICODE).lower()

    def _get_explicit_mentions(self, message: discord.Message) -> list[discord.User]:
        """過濾並僅保留訊息中「主動手動標記」的用戶，排除因 Discord 「回覆訊息 (Reply)」自動帶入的 @提及。"""
        if not message.mentions:
            return []
        if message.reference is None:
            return message.mentions
        raw_content = message.content or ""
        explicit_mentions = []
        for user in message.mentions:
            if f"<@{user.id}>" in raw_content or f"<@!{user.id}>" in raw_content:
                explicit_mentions.append(user)
        return explicit_mentions

    def _init_all_dbs(self):
        """初始化 counts.db, counts_archive.db 與 ryker_targets.db"""
        try:
            # 1. 活躍計數庫
            with sqlite3.connect(self.db_counts) as conn:
                conn.cursor().execute("PRAGMA journal_mode=WAL;")
                conn.cursor().execute("""
                    CREATE TABLE IF NOT EXISTS message_counts (
                        guild_id TEXT,
                        user_id TEXT,
                        count INTEGER NOT NULL DEFAULT 0,
                        last_timestamp REAL NOT NULL,
                        PRIMARY KEY (guild_id, user_id)
                    )
                """)
                conn.commit()

            # 2. 歸檔計數庫
            with sqlite3.connect(self.db_archive) as conn:
                conn.cursor().execute("PRAGMA journal_mode=WAL;")
                conn.cursor().execute("""
                    CREATE TABLE IF NOT EXISTS message_counts_archive (
                        guild_id TEXT,
                        user_id TEXT,
                        count INTEGER NOT NULL DEFAULT 0,
                        last_timestamp REAL NOT NULL,
                        archived_at REAL NOT NULL,
                        PRIMARY KEY (guild_id, user_id)
                    )
                """)
                conn.commit()

            # 3. Ryker 優先黑名單庫
            self._init_targets_db()

        except Exception as e:
            print(f"⚠️ [幹男防護] 初始化 SQLite 資料庫失敗: {e}")

    def _init_targets_db(self):
        """初始化 ryker_badusers.db 並建立 bad_users 與 target_users 資料表"""
        with sqlite3.connect(self.db_badusers) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bad_users (
                    user_id TEXT PRIMARY KEY,
                    added_by TEXT,
                    added_at REAL,
                    note TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS target_users (
                    user_id TEXT PRIMARY KEY,
                    added_by TEXT,
                    added_at REAL,
                    note TEXT
                )
            """)
            conn.commit()

            cursor.execute("SELECT COUNT(*) FROM bad_users")
            row = cursor.fetchone()
            if row and row[0] == 0 and SEED_BAD_USERS:
                now_ts = discord.utils.utcnow().timestamp()
                seed_rows = [(str(uid), "系統預設種子", now_ts, "初始化種子惡意帳號") for uid in SEED_BAD_USERS]
                cursor.executemany("""
                    INSERT OR IGNORE INTO bad_users (user_id, added_by, added_at, note)
                    VALUES (?, ?, ?, ?)
                """, seed_rows)
                conn.commit()

            cursor.execute("SELECT COUNT(*) FROM target_users")
            row_t = cursor.fetchone()
            if row_t and row_t[0] == 0 and TARGET_USERS:
                now_ts = discord.utils.utcnow().timestamp()
                seed_target_rows = [(str(uid), "系統預設種子", now_ts, "初始化受害者與保護對象") for uid in TARGET_USERS]
                cursor.executemany("""
                    INSERT OR IGNORE INTO target_users (user_id, added_by, added_at, note)
                    VALUES (?, ?, ?, ?)
                """, seed_target_rows)
                conn.commit()
                print(f"✅ [幹男防護] 已將 {len(TARGET_USERS)} 個預設受害者/保護對象寫入 ryker_badusers.db (target_users)")

    def get_bad_users(self) -> set[int]:
        """從 ryker_badusers.db 讀取目前所有的 Ryker 惡意破壞者帳號 ID (bad_users) 集合"""
        try:
            with sqlite3.connect(self.db_badusers) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM bad_users")
                rows = cursor.fetchall()
                return {int(r[0]) for r in rows if r[0].isdigit()}
        except Exception as e:
            print(f"⚠️ [幹男防護] 讀取 ryker_badusers.db (bad_users) 失敗: {e}")
            return set()

    def get_target_users(self) -> set[int]:
        """從 ryker_badusers.db 讀取目前所有的受害者/保護對象 (target_users) ID 集合"""
        try:
            with sqlite3.connect(self.db_badusers) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM target_users")
                rows = cursor.fetchall()
                db_set = {int(r[0]) for r in rows if r[0].isdigit()}
                return db_set.union(TARGET_USERS)
        except Exception as e:
            print(f"⚠️ [幹男防護] 讀取 ryker_badusers.db (target_users) 失敗: {e}")
            return set(TARGET_USERS)

    def add_bad_user(self, user_id: int, added_by: str) -> bool:
        """動態新增惡意帳號至 ryker_badusers.db (bad_users) 並同步剝奪其歷史畢業紀錄"""
        uid_str = str(user_id)
        now_ts = discord.utils.utcnow().timestamp()
        try:
            with sqlite3.connect(self.db_badusers) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO bad_users (user_id, added_by, added_at, note)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        added_by = excluded.added_by,
                        added_at = excluded.added_at
                """, (uid_str, added_by, now_ts, "動態新增"))
                conn.commit()

            # 清除活躍庫與歸檔庫中該帳號的歷史畢業紀錄 (剝奪畢業身分)
            with sqlite3.connect(self.db_counts) as conn:
                conn.cursor().execute("DELETE FROM message_counts WHERE user_id = ?", (uid_str,))
                conn.commit()
            with sqlite3.connect(self.db_archive) as conn:
                conn.cursor().execute("DELETE FROM message_counts_archive WHERE user_id = ?", (uid_str,))
                conn.commit()
            return True
        except Exception as e:
            print(f"⚠️ [幹男防護] 新增惡意帳號 (bad_users) 至 DB 失敗: {e}")
            return False

    def add_target_user(self, user_id: int, added_by: str) -> bool:
        """動態新增受害者/保護對象至 ryker_badusers.db (target_users)"""
        uid_str = str(user_id)
        now_ts = discord.utils.utcnow().timestamp()
        try:
            with sqlite3.connect(self.db_badusers) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO target_users (user_id, added_by, added_at, note)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        added_by = excluded.added_by,
                        added_at = excluded.added_at
                """, (uid_str, added_by, now_ts, "動態新增"))
                conn.commit()
            return True
        except Exception as e:
            print(f"⚠️ [幹男防護] 新增受害者 (target_users) 至 DB 失敗: {e}")
            return False

    def remove_bad_user(self, user_id: int) -> bool:
        """從 ryker_badusers.db 移除惡意帳號 (bad_users)"""
        try:
            with sqlite3.connect(self.db_badusers) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM bad_users WHERE user_id = ?", (str(user_id),))
                conn.commit()
                return True
        except Exception as e:
            print(f"⚠️ [幹男防護] 從 DB 刪除惡意帳號 (bad_users) 失敗: {e}")
            return False

    def remove_target_user(self, user_id: int) -> bool:
        """從 ryker_badusers.db 移除受害者/保護對象 (target_users)"""
        try:
            with sqlite3.connect(self.db_badusers) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM target_users WHERE user_id = ?", (str(user_id),))
                conn.commit()
                return True
        except Exception as e:
            print(f"⚠️ [幹男防護] 從 DB 刪除受害者 (target_users) 失敗: {e}")
            return False

    def get_user_count(self, guild_id: int, user_id: int) -> int:
        """讀取單一用戶在特定伺服器的發言次數 (活躍庫 -> 歸檔庫)"""
        gid_str, uid_str = str(guild_id), str(user_id)
        try:
            with sqlite3.connect(self.db_counts) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count FROM message_counts WHERE guild_id = ? AND user_id = ?", (gid_str, uid_str))
                row = cursor.fetchone()
                if row:
                    return row[0]
            with sqlite3.connect(self.db_archive) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count FROM message_counts_archive WHERE guild_id = ? AND user_id = ?", (gid_str, uid_str))
                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception:
            pass
        return 0

    def is_user_archived(self, guild_id: int, user_id: int) -> bool:
        """檢查用戶是否已經在該伺服器歸檔畢業"""
        gid_str, uid_str = str(guild_id), str(user_id)
        try:
            with sqlite3.connect(self.db_archive) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM message_counts_archive WHERE guild_id = ? AND user_id = ?", (gid_str, uid_str))
                return cursor.fetchone() is not None
        except Exception:
            return False

    def increment_user_count(self, guild_id: int, user_id: int, threshold: int = 10) -> int:
        """計數累加，達到 threshold 即歸檔移至 counts_archive.db"""
        gid_str, uid_str = str(guild_id), str(user_id)
        now_ts = discord.utils.utcnow().timestamp()

        if self.is_user_archived(guild_id, user_id):
            return threshold + 1

        try:
            with sqlite3.connect(self.db_counts) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO message_counts (guild_id, user_id, count, last_timestamp)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        count = message_counts.count + 1,
                        last_timestamp = excluded.last_timestamp
                """, (gid_str, uid_str, now_ts))
                conn.commit()

                cursor.execute("SELECT count FROM message_counts WHERE guild_id = ? AND user_id = ?", (gid_str, uid_str))
                row = cursor.fetchone()
                new_count = row[0] if row else 1

            if new_count >= threshold:
                self._archive_user(guild_id, user_id, new_count, now_ts)

            return new_count
        except Exception as e:
            print(f"⚠️ [幹男防護] 計數累加失敗: {e}")
            return 1

    def _archive_user(self, guild_id: int, user_id: int, count: int, last_ts: float):
        """將已達發言門檻畢業的用戶移入歸檔庫"""
        gid_str, uid_str = str(guild_id), str(user_id)
        now_ts = discord.utils.utcnow().timestamp()
        try:
            with sqlite3.connect(self.db_archive) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO message_counts_archive (guild_id, user_id, count, last_timestamp, archived_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        count = excluded.count,
                        last_timestamp = excluded.last_timestamp,
                        archived_at = excluded.archived_at
                """, (gid_str, uid_str, count, last_ts, now_ts))
                conn.commit()

            with sqlite3.connect(self.db_counts) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM message_counts WHERE guild_id = ? AND user_id = ?", (gid_str, uid_str))
                conn.commit()
        except Exception as e:
            print(f"⚠️ [幹男防護] 歸檔用戶紀錄失敗: {e}")

    async def _send_kill_announcement(self, channel: discord.TextChannel, author: discord.User, reason_summary: str, raw_content: str = None):
        """處決通報 (發送 3 天禁言通報卡片與快捷按鈕)"""
        embed = None
        try:
            content_display = f"```\n{raw_content[:500]}\n```" if raw_content else "*(無內容或暱稱觸發)*"
            embed = discord.Embed(
                description=(
                    f"🚨 已匹配到 Ryker 惡意用戶 {author.mention} (`{author.name}`)\n"
                    f"已執行 **3 天禁言** 處置，等待管理員進行後續處決操作。\n\n"
                    f"**原因**：{reason_summary}。\n"
                    f"**原訊息內容**：\n{content_display}\n"
                    f"請管理員檢查用戶紀錄並進行處決封鎖。"
                ),
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=author.display_avatar.url)
            embed.set_footer(text="TWERG HoneyBot - Ryker 防護系統")
            await channel.send(
                content="🚨 Ryker 惡意用戶已自動禁言 3 天（等待管理員處理）",
                embed=embed,
                view=RykerAdminActionView(author)
            )
        except Exception as e:
            print(f"⚠️ [幹男防護] 發送通報訊息失敗: {e}")

        # 抄送紀錄至本伺服器專屬日誌頻道
        if embed:
            try:
                await send_server_log(channel.guild, embed, view=RykerAdminActionView(author))
            except Exception as se:
                print(f"⚠️ [幹男防護] 無法在伺服器日誌頻道發送通報: {se}")

        # 同步抄送 Console
        try:
            if os.path.exists('config.json'):
                with open('config.json', 'r', encoding='utf-8') as f:
                    bot_config = json.load(f)
                console_id = bot_config.get("CONSOLE_ID")
                if console_id:
                    console_channel = self.bot.get_channel(int(console_id))
                    if console_channel and console_channel.id != channel.id:
                        await console_channel.send(
                            content="🚨 Ryker 惡意用戶已自動禁言 3 天（等待管理員處理）",
                            embed=embed,
                            view=RykerAdminActionView(author)
                        )
        except Exception as ce:
            print(f"⚠️ [幹男防護] 無法在 CONSOLE 頻道發送通報: {ce}")

    async def _send_timeout_announcement(self, channel: discord.TextChannel, author: discord.User, reason_summary: str, raw_content: str = None):
        """洗板處置通報 (發送 1 小時禁言通報卡片與快捷按鈕)"""
        embed = None
        try:
            content_display = f"```\n{raw_content[:500]}\n```" if raw_content else "*(無內容)*"
            embed = discord.Embed(
                description=(
                    f"🛑 已對涉嫌洗板用戶 {author.mention} (`{author.name}`) 執行 **1 小時禁言** 處置。\n\n"
                    f"**原因**：{reason_summary}。\n"
                    f"**觸發訊息**：\n{content_display}\n"
                    f"請管理員注意是否有持續騷擾行為。"
                ),
                color=discord.Color.orange()
            )
            embed.set_thumbnail(url=author.display_avatar.url)
            embed.set_footer(text="TWERG HoneyBot 防護系統")
            await channel.send(
                content="🚨 新用戶重複洗板已自動禁言 1 小時",
                embed=embed,
                view=RykerAdminActionView(author)
            )
        except Exception as e:
            print(f"⚠️ [幹男防護] 無法發送洗板禁言通報訊息: {e}")

        # 抄送紀錄至本伺服器專屬日誌頻道
        if embed:
            try:
                await send_server_log(channel.guild, embed, view=RykerAdminActionView(author))
            except Exception as se:
                print(f"⚠️ [幹男防護] 無法在伺服器日誌頻道發送通報: {se}")

        # 同時抄送至 CONSOLE_ID 頻道
        if embed:
            try:
                if os.path.exists('config.json'):
                    with open('config.json', 'r', encoding='utf-8') as f:
                        bot_config = json.load(f)
                    console_id = bot_config.get("CONSOLE_ID")
                    if console_id:
                        console_channel = self.bot.get_channel(int(console_id))
                        if console_channel and console_channel.id != channel.id:
                            await console_channel.send(
                                content="🚨 新用戶重複洗板已自動禁言 1 小時",
                                embed=embed,
                                view=RykerAdminActionView(author)
                            )
            except Exception as ce:
                print(f"⚠️ [幹男防護] 無法在 CONSOLE 頻道發送洗板禁言通報: {ce}")

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """每日自動清理歷史快取與超過 90 天未再發言的記錄"""
        now_ts = discord.utils.utcnow().timestamp()
        cutoff_msg = now_ts - 300
        for uid in list(self.user_msg_history.keys()):
            self.user_msg_history[uid] = [item for item in self.user_msg_history[uid] if item[0] >= cutoff_msg]
            if not self.user_msg_history[uid]:
                del self.user_msg_history[uid]

        ninety_days_sec = 7776000
        limit_ts = now_ts - ninety_days_sec
        try:
            with sqlite3.connect(self.db_counts) as conn:
                conn.cursor().execute("DELETE FROM message_counts WHERE last_timestamp < ?", (limit_ts,))
                conn.commit()
        except Exception as e:
            print(f"⚠️ [幹男防護] 自動清理舊發言紀錄時發生錯誤: {e}")

    @app_commands.command(name="ryker", description="查看 Ryker 惡意帳號名單與一鍵封鎖操作")
    @app_commands.rename(action="動作", user_id="使用者id")
    @app_commands.describe(action="選擇動作 (查看 / 新增 / 刪除)", user_id="要新增或刪除的用戶 ID (數字)")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="查看惡意帳號清單", value="list"),
            app_commands.Choice(name="新增惡意帳號 (限信任者)", value="add"),
            app_commands.Choice(name="刪除惡意帳號 (限信任者)", value="remove")
        ]
    )
    @app_commands.guilds(518699949500661760, 897116721159233576)
    async def ryker_command(self, interaction: discord.Interaction, action: app_commands.Choice[str] = None, user_id: str = None):
        if not is_server_authorized(interaction.guild_id):
            await interaction.response.send_message("❌ 本伺服器尚未獲得機器人擁有者授權許可，無法使用此指令。", ephemeral=True)
            return

        val = action.value if action else "list"
        bad_users_set = self.get_bad_users()

        if val == "list":
            if not bad_users_set:
                await interaction.response.send_message("ℹ️ 目前 Ryker 惡意帳號庫 (bad_users) 為空。", ephemeral=True)
                return

            bad_list = list(bad_users_set)
            lines = ["🚨 **Ryker 惡意破壞者帳號黑名單 (bad_users)**："]
            for uid in bad_list:
                lines.append(f"• <@{uid}> (`{uid}`)")

            content = "\n".join(lines)
            if len(content) > 3800:
                content = content[:3800] + "\n... (列表過長已截斷)"

            embed = discord.Embed(
                description=content,
                color=discord.Color.red()
            )
            embed.set_footer(text="點擊下方按鈕可一鍵將此清單所有惡意帳號自本伺服器封鎖。")
            view = RykerBatchBanView(bad_list, interaction.user.id)
            await interaction.response.send_message(content="🛡️ **Ryker 惡意破壞者帳號管理 (bad_users)**", embed=embed, view=view, ephemeral=True)
            return

        # 新增/刪除動作需要權限檢查 (信任的人)
        if not is_user_trusted(interaction.user.id):
            await interaction.response.send_message("❌ 你不是「信任的人」，沒有權限增刪 Ryker 惡意帳號庫 (bad_users)！", ephemeral=True)
            return

        # 解析輸入內容中的所有數字 ID (支援以空白、逗號、換行等分隔多個 ID)
        raw_input = user_id or ""
        parsed_ids = [int(x) for x in re.findall(r'\d{16,20}', raw_input)]
        if not parsed_ids:
            await interaction.response.send_message("❌ 請提供至少一個正確的數字用戶 ID (16~20 位數字)。\n💡 提示：支援一次輸入多個 ID (可用逗號或空白分隔)。", ephemeral=True)
            return

        added_by_str = f"{interaction.user} ({interaction.user.id})"

        if val == "add":
            newly_added = []
            already_existed = []
            failed = []

            for uid in parsed_ids:
                if uid in bad_users_set:
                    already_existed.append(uid)
                else:
                    success = self.add_bad_user(uid, added_by_str)
                    if success:
                        newly_added.append(uid)
                        bad_users_set.add(uid)
                    else:
                        failed.append(uid)

            lines = ["✅ **Ryker 惡意帳號 (bad_users) 批次新增結果**："]
            if newly_added:
                mentions = ", ".join([f"<@{uid}> (`{uid}`)" for uid in newly_added])
                lines.append(f"• 🟢 **成功新增 ({len(newly_added)} 人)**：{mentions}")
                lines.append("🛡️ *已自動剝奪上述帳號所有歷史畢業紀錄，後續一有發言將立即處決！*")
            if already_existed:
                lines.append(f"• ℹ️ **原本已在庫中 ({len(already_existed)} 人)**：{', '.join([str(u) for u in already_existed])}")
            if failed:
                lines.append(f"• ❌ **寫入失敗 ({len(failed)} 人)**：{', '.join([str(u) for u in failed])}")

            await interaction.response.send_message("\n".join(lines), ephemeral=True)

        elif val == "remove":
            newly_removed = []
            not_found = []
            failed = []

            for uid in parsed_ids:
                if uid not in bad_users_set:
                    not_found.append(uid)
                else:
                    success = self.remove_bad_user(uid)
                    if success:
                        newly_removed.append(uid)
                        bad_users_set.discard(uid)
                    else:
                        failed.append(uid)

            lines = ["🗑️ **Ryker 惡意帳號 (bad_users) 批次刪除結果**："]
            if newly_removed:
                lines.append(f"• 🟢 **成功移除 ({len(newly_removed)} 人)**：{', '.join([str(u) for u in newly_removed])}")
            if not_found:
                lines.append(f"• ℹ️ **不在庫中 ({len(not_found)} 人)**：{', '.join([str(u) for u in not_found])}")
            if failed:
                lines.append(f"• ❌ **刪除失敗 ({len(failed)} 人)**：{', '.join([str(u) for u in failed])}")

            await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="target_users", description="查看與增刪受害者/保護對象名單 (target_users)")
    @app_commands.rename(action="動作", user_id="使用者id")
    @app_commands.describe(action="選擇動作 (查看 / 新增 / 刪除)", user_id="要新增或刪除的用戶 ID (數字)")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="查看受害者/保護對象清單", value="list"),
            app_commands.Choice(name="新增受害者/保護對象 (限信任者)", value="add"),
            app_commands.Choice(name="刪除受害者/保護對象 (限信任者)", value="remove")
        ]
    )
    @app_commands.guilds(518699949500661760, 897116721159233576)
    async def target_users_command(self, interaction: discord.Interaction, action: app_commands.Choice[str] = None, user_id: str = None):
        if not is_server_authorized(interaction.guild_id):
            await interaction.response.send_message("❌ 本伺服器尚未獲得機器人擁有者授權許可，無法使用此指令。", ephemeral=True)
            return

        val = action.value if action else "list"
        target_set = self.get_target_users()

        if val == "list":
            if not target_set:
                await interaction.response.send_message("ℹ️ 目前受害者/保護對象庫 (target_users) 為空。", ephemeral=True)
                return

            target_list = list(target_set)
            lines = ["🛡️ **受害者與保護對象名單 (target_users)**："]
            for uid in target_list:
                lines.append(f"• <@{uid}> (`{uid}`)")

            content = "\n".join(lines)
            if len(content) > 3800:
                content = content[:3800] + "\n... (列表過長已截斷)"

            embed = discord.Embed(
                description=content,
                color=discord.Color.blue()
            )
            embed.set_footer(text="未畢業新用戶若在發言中顯式 @ 提及上述對象，將自動執行 3 天禁言處決。")
            await interaction.response.send_message(content="🛡️ **受害者與保護對象名單管理**", embed=embed, ephemeral=True)
            return

        # 新增/刪除動作需要權限檢查 (信任的人)
        if not is_user_trusted(interaction.user.id):
            await interaction.response.send_message("❌ 你不是「信任的人」，沒有權限增刪受害者/保護對象名單！", ephemeral=True)
            return

        # 解析輸入內容中的所有數字 ID (支援以空白、逗號、換行等分隔多個 ID)
        raw_input = user_id or ""
        parsed_ids = [int(x) for x in re.findall(r'\d{16,20}', raw_input)]
        if not parsed_ids:
            await interaction.response.send_message("❌ 請提供至少一個正確的數字用戶 ID (16~20 位數字)。\n💡 提示：支援一次輸入多個 ID (可用逗號或空白分隔)。", ephemeral=True)
            return

        added_by_str = f"{interaction.user} ({interaction.user.id})"

        if val == "add":
            newly_added = []
            already_existed = []
            failed = []

            for uid in parsed_ids:
                if uid in target_set:
                    already_existed.append(uid)
                else:
                    success = self.add_target_user(uid, added_by_str)
                    if success:
                        newly_added.append(uid)
                        target_set.add(uid)
                    else:
                        failed.append(uid)

            lines = ["✅ **受害者/保護對象 (target_users) 批次新增結果**："]
            if newly_added:
                mentions = ", ".join([f"<@{uid}> (`{uid}`)" for uid in newly_added])
                lines.append(f"• 🟢 **成功新增 ({len(newly_added)} 人)**：{mentions}")
                lines.append("🛡️ *後續未畢業用戶一在發言中 @ 標記上述對象將立即處決！*")
            if already_existed:
                lines.append(f"• ℹ️ **原本已在庫中 ({len(already_existed)} 人)**：{', '.join([str(u) for u in already_existed])}")
            if failed:
                lines.append(f"• ❌ **寫入失敗 ({len(failed)} 人)**：{', '.join([str(u) for u in failed])}")

            await interaction.response.send_message("\n".join(lines), ephemeral=True)

        elif val == "remove":
            newly_removed = []
            not_found = []
            failed = []

            for uid in parsed_ids:
                if uid not in target_set:
                    not_found.append(uid)
                else:
                    success = self.remove_target_user(uid)
                    if success:
                        newly_removed.append(uid)
                        target_set.discard(uid)
                    else:
                        failed.append(uid)

            lines = ["🗑️ **受害者/保護對象 (target_users) 批次刪除結果**："]
            if newly_removed:
                lines.append(f"• 🟢 **成功移除 ({len(newly_removed)} 人)**：{', '.join([str(u) for u in newly_removed])}")
            if not_found:
                lines.append(f"• ℹ️ **不在庫中 ({len(not_found)} 人)**：{', '.join([str(u) for u in not_found])}")
            if failed:
                lines.append(f"• ❌ **刪除失敗 ({len(failed)} 人)**：{', '.join([str(u) for u in failed])}")

            await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="syncban", description="[擁有者/信任者] 手動執行跨伺服器聯防封鎖")
    @app_commands.rename(user_id="使用者id", reason="封鎖原因")
    @app_commands.describe(user_id="要聯防封鎖的用戶 ID (可輸入多個，以空白或逗號分隔)", reason="封鎖原因 (選填)")
    @app_commands.guilds(518699949500661760, 897116721159233576)
    async def syncban_command(self, interaction: discord.Interaction, user_id: str, reason: str = "擁有者/信任管理員手動執行跨伺服器聯防封鎖"):
        if not is_server_authorized(interaction.guild_id):
            await interaction.response.send_message("❌ 本伺服器尚未獲得機器人擁有者授權許可，無法使用此指令。", ephemeral=True)
            return

        if not is_user_trusted(interaction.user.id):
            await interaction.response.send_message("❌ 你不是「信任的人」，沒有權限手動發動跨伺服器聯防封鎖！", ephemeral=True)
            return

        parsed_ids = [int(x) for x in re.findall(r'\d{16,20}', user_id or "")]
        if not parsed_ids:
            await interaction.response.send_message("❌ 請提供至少一個正確的數字用戶 ID (16~20 位數字)。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        added_by_str = f"擁有者/信任者 {interaction.user} ({interaction.user.id}) 手動跨伺服器聯防"
        all_settings = get_ryker_settings()

        results = []
        for uid in parsed_ids:
            # 1. 自動寫入 bad_users 黑名單庫並剝奪歷史畢業紀錄
            self.add_bad_user(uid, added_by_str)

            banned_guilds = []
            failed_guilds = []

            for g in self.bot.guilds:
                if not is_server_authorized(g.id):
                    continue
                g_sync = all_settings.get(str(g.id), {}).get("sync_ban", False)
                if not g_sync:
                    continue

                b_member = g.get_member(self.bot.user.id)
                if b_member and b_member.guild_permissions.ban_members:
                    try:
                        await g.ban(discord.Object(id=uid), reason=f"{reason} (發動者: {interaction.user})")
                        banned_guilds.append(g.name)

                        embed_log = discord.Embed(
                            description=(
                                f"🤝 **[擁有者手動聯防] 同步預先封鎖**\n\n"
                                f"• **發動管理員**：{interaction.user.mention} (`{interaction.user.id}`)\n"
                                f"• **封鎖對象**：<@{uid}> (`{uid}`)\n"
                                f"• **封鎖原因**：{reason}\n"
                                f"• **狀態**：本伺服器已成功執行預先封鎖"
                            ),
                            color=discord.Color.dark_red()
                        )
                        embed_log.set_footer(text="TWERG HoneyBot - 手動聯防日誌")
                        await send_server_log(g, embed_log)
                    except Exception as e:
                        failed_guilds.append(f"{g.name} ({e})")

            res_str = f"• **<@{uid}> (`{uid}`)**："
            if banned_guilds:
                res_str += f"\n  - 🟢 成功同步封鎖 ({len(banned_guilds)} 個伺服器): {', '.join(banned_guilds)}"
            else:
                res_str += f"\n  - ℹ️ 無其他伺服器需執行封鎖 (或開啟聯防之伺服器已全數封鎖)"
            if failed_guilds:
                res_str += f"\n  - ❌ 封鎖失敗 ({len(failed_guilds)} 個伺服器): {', '.join(failed_guilds)}"
            results.append(res_str)

        embed_resp = discord.Embed(
            title="🤝 跨伺服器聯防手動執行結果",
            description="\n\n".join(results),
            color=discord.Color.red()
        )
        embed_resp.set_footer(text="已同步寫入 bad_users 惡意帳號庫，並剝奪所有歷史畢業紀錄。")
        await interaction.followup.send(embed=embed_resp, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or message.is_system():
            return

        now_ts = discord.utils.utcnow().timestamp()

        # 檢查伺服器授權
        if not is_server_authorized(message.guild.id):
            return

        bad_users_set = self.get_bad_users()
        all_settings = get_ryker_settings()
        g_settings = all_settings.get(str(message.guild.id), {})

        # 設定參數量與 6 大防禦模組獨立開關
        threshold = g_settings.get("monitor_threshold", 10)
        lurker_mon = g_settings.get("global_monitor", False) # 潛水用戶監控
        eew_pause_enabled = g_settings.get("eew_pause_enabled", True) # EEW速報連動暫停
        bad_users_enabled = g_settings.get("bad_users_enabled", True) # 惡意帳號比對開關
        target_users_enabled = g_settings.get("target_users_enabled", True) # 受害者標記防護開關
        bad_words_enabled = g_settings.get("bad_words_enabled", True) # 敏感詞與正則比對開關
        image_spam_enabled = g_settings.get("image_spam_enabled", True) # 圖片洗板防護開關
        header_spam_enabled = g_settings.get("header_spam_enabled", True) # 大字體洗板防護開關

        author_id = message.author.id

        # ----------------------------------------------------
        # 模組 1: EEW 地震速報連動暫停模組 (defense_eew.py)
        # ----------------------------------------------------
        process_eew_event(self, message, now_ts)
        is_eew_paused_now = is_eew_paused(self, now_ts, eew_pause_enabled)

        # ----------------------------------------------------
        # 模組 2: Ryker 惡意破壞者帳號 (bad_users) 比對 (defense_bad_users.py)
        # ----------------------------------------------------
        if bad_users_enabled and not is_eew_paused_now:
            if await check_bad_users(self, message, bad_users_set):
                return

        # ----------------------------------------------------
        # 免疫身分檢查：管理員、排除身分組、最高身分組高於/等於機器人
        # ----------------------------------------------------
        if isinstance(message.author, discord.Member):
            excluded_roles = []
            if os.path.exists('honeypot_settings.json'):
                try:
                    with open('honeypot_settings.json', 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        guild_data = data.get(str(message.guild.id), {})
                        if isinstance(guild_data, dict):
                            excluded_roles = guild_data.get("excluded_roles", [])
                except Exception:
                    pass

            has_excluded_role = any(role.id in excluded_roles for role in message.author.roles)
            is_immune = (
                has_excluded_role or
                message.author.guild_permissions.administrator or
                (message.guild.me and message.author.top_role >= message.guild.me.top_role)
            )
            if is_immune:
                return

        # ----------------------------------------------------
        # 正常監控邏輯：檢查發言次數與潛水用戶監控
        # ----------------------------------------------------
        # 若未開啟潛水用戶監控，且該用戶在該伺服器已歸檔畢業 (>= threshold)，放行
        if not lurker_mon and self.is_user_archived(message.guild.id, author_id):
            return

        # 讀取/更新發言次數
        current_count = self.increment_user_count(message.guild.id, author_id, threshold)

        # 若發言次數已達門檻且未開啟潛水用戶監控，放行
        if current_count > threshold and not lurker_mon:
            return

        # ----------------------------------------------------
        # 模組 3: 標記受害者 / 保護對象防護 (defense_target_users.py)
        # (注意：即便在 EEW 地震暫停期，若管理者開啟了本模組，防護依然持續運作)
        # ----------------------------------------------------
        if target_users_enabled:
            if await check_target_users(self, message):
                return

        # 若處於 EEW 地震暫停期，僅進行上述受害者標記防護，其餘洗板與關鍵字防護全部跳過
        if is_eew_paused_now:
            return

        # ----------------------------------------------------
        # 模組 4: 短時間 (60秒) 圖片/附件洗板防護 (defense_image_spam.py)
        # ----------------------------------------------------
        if image_spam_enabled:
            if await check_image_spam(self, message, now_ts):
                return

        # ----------------------------------------------------
        # 模組 5: Markdown「#」大字體與連續樣式洗板防護 (defense_header_spam.py)
        # ----------------------------------------------------
        if header_spam_enabled:
            if await check_header_spam(self, message, current_count):
                return

        # ----------------------------------------------------
        # 模組 6: 敏感詞彙與組合正則特徵比對 (defense_bad_words.py)
        # ----------------------------------------------------
        if bad_words_enabled:
            if await check_bad_words(self, message):
                return

async def setup(bot: commands.Bot):
    await bot.add_cog(RykerDefenseCog(bot))
