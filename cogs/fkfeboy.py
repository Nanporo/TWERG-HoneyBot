import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import sqlite3
import re
import difflib
import datetime

class FkfeboyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings_file = 'fkfeboy_settings.json'
        self.db_file = 'fkfeboy_counts.db'
        self._cached_settings = None
        self._last_mtime = 0
        self.user_msg_history = {}  # 近期用戶發言歷史記錄 {user_id: [(timestamp, norm_content, raw_content)]}
        self.user_img_history = {}  # 近期用戶圖片發言歷史記錄 {user_id: [timestamp, ...]}
        self.user_header_history = {}  # 近期用戶標題大字發言歷史記錄 {user_id: [is_header_bool, ...]}
        self.eew_pause_until = 0.0  # 地震速報連動暫停截止時間戳 (UTC timestamp)

        # 初始化 SQLite 資料庫並進行自動移轉
        self._init_db()
        self._migrate_from_json()

        # 啟動自動清理任務
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    def _normalize_text(self, text: str) -> str:
        """過濾文字中的標點符號、空格、特殊字元並統一轉小寫，防止繞過關鍵字"""
        if not text:
            return ""
        # 移除空格、標點符號與特殊符號
        return re.sub(r'[\s\W_]+', '', text, flags=re.UNICODE).lower()

    def _init_db(self):
        """初始化 SQLite 資料庫與表格結構"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS message_counts (
                        user_id TEXT PRIMARY KEY,
                        count INTEGER NOT NULL DEFAULT 0,
                        last_timestamp REAL NOT NULL
                    )
                """)
                conn.commit()
        except Exception as e:
            print(f"⚠️ [幹男防護] 初始化 SQLite 資料庫失敗: {e}")

    def _migrate_from_json(self):
        """若存在舊版 fkfeboy_counts.json，無感無縫轉移至 SQLite 資料庫"""
        json_file = 'fkfeboy_counts.json'
        if os.path.exists(json_file):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if isinstance(data, dict) and data:
                    now_ts = discord.utils.utcnow().timestamp()
                    rows = []
                    for k, v in data.items():
                        count = v.get("c", 0) if isinstance(v, dict) else int(v)
                        last_ts = v.get("t", now_ts) if isinstance(v, dict) else now_ts
                        rows.append((str(k), count, last_ts))

                    with sqlite3.connect(self.db_file) as conn:
                        cursor = conn.cursor()
                        cursor.executemany("""
                            INSERT INTO message_counts (user_id, count, last_timestamp)
                            VALUES (?, ?, ?)
                            ON CONFLICT(user_id) DO UPDATE SET
                                count = excluded.count,
                                last_timestamp = excluded.last_timestamp
                        """, rows)
                        conn.commit()

                # 完成轉移後重命名備份檔，防止重複移轉
                bak_file = json_file + '.bak'
                if os.path.exists(bak_file):
                    os.remove(bak_file)
                os.rename(json_file, bak_file)
                print("✅ [幹男防護] 已成功將舊版 fkfeboy_counts.json 無感無縫轉移至 SQLite 資料庫！")
            except Exception as e:
                print(f"⚠️ [幹男防護] 自動轉移既有 JSON 資料至 SQLite 時發生錯誤: {e}")

    def _get_user_record(self, user_id: str):
        """讀取單一用戶的發言紀錄 {"c": count, "t": timestamp}"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count, last_timestamp FROM message_counts WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                if row:
                    return {"c": row[0], "t": row[1]}
        except Exception as e:
            print(f"⚠️ [幹男防護] 讀取用戶資料庫紀錄失敗: {e}")
        return {"c": 0, "t": 0.0}

    def _increment_user_count(self, user_id: str) -> int:
        """更新並累加單一用戶的發言次數，返回最新次數"""
        now_ts = discord.utils.utcnow().timestamp()
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO message_counts (user_id, count, last_timestamp)
                    VALUES (?, 1, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        count = message_counts.count + 1,
                        last_timestamp = excluded.last_timestamp
                """, (user_id, now_ts))
                conn.commit()

                cursor.execute("SELECT count FROM message_counts WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                return row[0] if row else 1
        except Exception as e:
            print(f"⚠️ [幹男防護] 更新用戶發言次數至資料庫失敗: {e}")
            return 1

    async def _send_kill_announcement(self, channel: discord.TextChannel, author: discord.User, reason_summary: str, raw_content: str = None):
        """當成功封鎖惡意用戶時，在觸發頻道與 CONSOLE 頻道發送通報 Embed"""
        embed = None
        try:
            content_display = f"```\n{raw_content[:500]}\n```" if raw_content else "*(無內容或暱稱觸發)*"
            embed = discord.Embed(
                title="",
                description=(
                    f"已匹配到惡意用戶 {author.mention} (`{author.name}`)\n"
                    f"已執行封鎖並清除近期訊息。\n\n"
                    f"**原因**：{reason_summary}。\n"
                    f"**原訊息內容**：\n{content_display}\n"
                    f"請管理員再次檢查用戶紀錄，以免誤 BAN。"
                ),
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=author.display_avatar.url)
            embed.set_footer(text="TWERG HoneyBot 防護系統")
            await channel.send(embed=embed, content="🚨 惡意用戶已驅逐")
        except Exception as e:
            print(f"⚠️ [幹男防護] 無法在頻道 {channel.id} 發送擊殺通報訊息: {e}")

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
                            await console_channel.send(embed=embed, content="🚨 惡意用戶已驅逐")
            except Exception as ce:
                print(f"⚠️ [幹男防護] 無法在 CONSOLE 頻道發送擊殺通報: {ce}")

    async def _send_timeout_announcement(self, channel: discord.TextChannel, author: discord.User, reason_summary: str, raw_content: str = None):
        """當自動處決禁言洗板用戶時，在觸發頻道與 CONSOLE 頻道發送 Embed 通報"""
        embed = None
        try:
            content_display = f"```\n{raw_content[:500]}\n```" if raw_content else "*(無內容)*"
            embed = discord.Embed(
                title="",
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
            await channel.send(embed=embed, content="🚨 新用戶重複洗板已自動禁言")
        except Exception as e:
            print(f"⚠️ [幹男防護] 無法發送禁言通報訊息: {e}")

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
                            await console_channel.send(embed=embed, content="🚨 新用戶重複洗板已自動禁言")
            except Exception as ce:
                print(f"⚠️ [幹男防護] 無法在 CONSOLE 頻道發送禁言通報: {ce}")

    def _get_explicit_mentions(self, message: discord.Message) -> list[discord.User]:
        """
        過濾並僅保留訊息中「主動手動標記」的用戶，排除因 Discord 「回覆訊息 (Reply)」自動帶入的 @提及。
        """
        if not message.mentions:
            return []

        # 若訊息不是「回覆訊息」(message.reference 為 None)，所有 mentions 皆視為手動 at
        if message.reference is None:
            return message.mentions

        raw_content = message.content or ""
        explicit_mentions = []
        for user in message.mentions:
            # 手動在訊息中輸入標記時，訊息內容會包含 <@ID> 或 <@!ID>
            if f"<@{user.id}>" in raw_content or f"<@!{user.id}>" in raw_content:
                explicit_mentions.append(user)

        return explicit_mentions

    def get_settings(self):
        """
        讀取或初始化幹男防禦設定檔 (fkfeboy_settings.json)。
        若 JSON 已存在，自動升級並合併廣泛化與詞根化的預設關鍵字。
        """
        default_settings = {
            "global_monitor": False,
            "target_users": [
                964849855396741130,
                1356782484565790840, # 台灣 Online 管理員 / 頑固苗獨份子
                782499307717656596, 
                815574915901554699, # ExpTech 管理員 / eggrollpvp
                69370157784371200, 
                675922096425009184, # Yoyo0901
                277499904266338304, # YoWoApple
                682208921921912863,
            ],

            # 移除多餘的偵測或成員可能發出詞彙 by commandcat
            # Use str.lower()
            "bad_words": [
                # 1. 傳統粗口、公然侮辱與威脅詞根
                "幹破", "幹爆", "放炸彈", "破狗", "破草", "王八蛋", "好好跟你說", "主機板", "主機版", "電路板", "電路版", 
                "操你媽", "幹你娘", "幹妳娘", "炸你", "死賤貨", "賤貨", "殺小", 
                "雞巴", "機掰", "機八", "炸群", "鬼態度", "好好講", "賤狗", "死狗", "走狗", "狗嘴",
                "死西八", "西八", "破麻", "綠茶婊", "妓女", "妓女之子", "混蛋狗", "混蛋", "排擠狗",
                "拎北", "拎爸", "💣",

                # 2. 人身攻擊、智力/身障侮辱、詛咒、威脅與騷擾詞根
                "低能", "智障", "弱智", "腦殘", "腦癱", "賤畜", "破b", "死出來",
                "欠壓", "壓s", "欠幹", "欠操", "死全家", "全家死", "家也會被震垮", 
                "震垮", "憨點", "憨包", "三寶", "s全家", "s人", "賴你媽逼", 
                "死機掰", "貪破你娘", "死破狗", "管理狗", "欠插殺", "欠插", "支持炸群", "炸你們群",
                "你媽死", "媽死", "死人", "染疫", "nmsl", "NMSL", "c8", "解鎖", "沒種", "狗啃",
                "捅死", "pvp", "PVP", "死腦筋", "噴人", "瞎掰", "躲封鎖", "躲封", "炸一次", "鎖一次",
                "ㄙㄌㄋ", "78毛", "屁眼", "屁股毛", "肛門", "菊花", "陰莖", "陰道", "懶叫", "公然騷擾",
                "fkass", "asshole", "fuckass", "btchmod",

                # 3. 政治仇恨攻擊與侮辱性稱呼詞根
                "藍白", "白藍", "藍狗", "白狗", "藍豬", "白豬", "小草", "草包", "雜草",
                "藍草", "白草", "柯粉", "蔥粉", "黃狗", "綠狗", "綠共", "塔綠班",

                # 4. 假地震恐嚇、恐攻與場館威脅
                "毀滅", "巨震", "大噴發", "預報", "預測", "預側", 
                "雙北毀", "開香檳", "香檳", "靈氣強震", "3主震", "選我正解", "正解",
                "computex", "101世貿", "南港館", "綁起來", "炸掉", "賴先生", "恐龍", "暴龍",
                "宿舍", "欠捅", "欠炸", "屎"
            ]
        }

        if not os.path.exists(self.settings_file):
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(default_settings, f, ensure_ascii=False, indent=4)
            self._cached_settings = default_settings
            self._last_mtime = os.path.getmtime(self.settings_file)
            return self._cached_settings

        current_mtime = os.path.getmtime(self.settings_file)
        if self._cached_settings is None or current_mtime > self._last_mtime:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                try: 
                    settings = json.load(f)
                except json.JSONDecodeError: 
                    settings = default_settings

            self._cached_settings = settings
            self._last_mtime = current_mtime

        # 確保程式碼內新增的 default_settings (如 global_monitor, target_users 與 bad_words) 必定強制併入快取與 JSON 檔中
        updated = False
        if "global_monitor" not in self._cached_settings:
            self._cached_settings["global_monitor"] = False
            updated = True

        # set[str]
        existing_bad_words = set(map(str, self._cached_settings.get("bad_words", [])))
        for bw in default_settings["bad_words"]:
            if bw not in existing_bad_words:
                self._cached_settings.setdefault("bad_words", []).append(bw)
                updated = True

        # set[int]
        existing_targets = set(map(int, self._cached_settings.get("target_users", [])))
        for tu in default_settings["target_users"]:
            if tu not in existing_targets:
                self._cached_settings.setdefault("target_users", []).append(tu)
                updated = True

        if updated:
            try:
                with open(self.settings_file, 'w', encoding='utf-8') as wf:
                    json.dump(self._cached_settings, wf, ensure_ascii=False, indent=4)
                self._last_mtime = os.path.getmtime(self.settings_file)
            except Exception as e:
                print(f"⚠️ [幹男防護] 同步寫入設定檔失敗: {e}")

        return self._cached_settings

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """每日清理超過 90 天未再發言的歷史用戶紀錄"""
        now_ts = discord.utils.utcnow().timestamp()
        ninety_days_sec = 7776000  # 90天的秒數
        limit_ts = now_ts - ninety_days_sec
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM message_counts WHERE last_timestamp < ?", (limit_ts,))
                conn.commit()
        except Exception as e:
            print(f"⚠️ [幹男防護] 自動清理舊發言紀錄時發生錯誤: {e}")
            
    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        await self.bot.wait_until_ready()

    def _get_eew_channel_id(self) -> int:
        """從 config.json 獲取 EEW 地震速報頻道 ID (預設為 1227229429965656124)"""
        try:
            if os.path.exists('config.json'):
                with open('config.json', 'r', encoding='utf-8') as f:
                    bot_config = json.load(f)
                    return int(bot_config.get("EEW_CHANNEL_ID", 1227229429965656124))
        except Exception as e:
            print(f"⚠️ [幹男防護] 讀取 EEW_CHANNEL_ID 失敗: {e}")
        return 1227229429965656124

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        eew_channel_id = self._get_eew_channel_id()
        now_ts = discord.utils.utcnow().timestamp()

        #【EEW 地震速報連動觸發】：排除訊息編輯，僅於速報頻道發送新訊息時觸發暫停防禦 10 分鐘
        if message.channel.id == eew_channel_id:
            self.eew_pause_until = now_ts + 600.0  # 暫停防禦 10 分鐘 (600秒)
            pause_time_str = datetime.datetime.fromtimestamp(self.eew_pause_until, tz=datetime.timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')
            log_msg = f"⚠️ [地震速報連動] 偵測到 EEW 頻道 ({eew_channel_id}) 發送新訊息！防禦機制已自動暫停 10 分鐘 (至 {pause_time_str})"
            print(log_msg)

            # 抄送至 Console / Output 通報頻道
            try:
                if os.path.exists('config.json'):
                    with open('config.json', 'r', encoding='utf-8') as f:
                        bot_config = json.load(f)
                    console_id = bot_config.get("CONSOLE_ID")
                    output_id = bot_config.get("OUTPUT_ID")
                    target_channels = set()
                    if console_id: target_channels.add(int(console_id))
                    if output_id: target_channels.add(int(output_id))

                    for cid in target_channels:
                        ch = self.bot.get_channel(cid)
                        if ch and ch.id != message.channel.id:
                            embed = discord.Embed(
                                title="🚨 [地震速報連動] EEW 發動",
                                description=f"檢測到速報頻道 {message.channel.mention} 收到新地震通知！\n**防禦機制已自動暫停 10 分鐘**（將於 `{pause_time_str}` 恢復）。",
                                color=discord.Color.yellow()
                            )
                            embed.set_footer(text="TWERG HoneyBot 連動防禦系統")
                            await ch.send(embed=embed)
            except Exception as e:
                print(f"⚠️ [幹男防護] 發送 EEW 暫停防禦通報時發生錯誤: {e}")
            return

        # 若處於 EEW 地震 10 分鐘暫停防禦期間，直接跳過後續防禦檢測
        if now_ts < self.eew_pause_until:
            return

        # 忽略機器人、系統訊息與私訊
        if message.author.bot or message.guild is None or message.is_system():
            return

        # 免疫檢查：伺服器管理員、排除身份組或身份組層級不低於機器人者免受懲罰
        if isinstance(message.author, discord.Member):
            excluded_roles = [518700481011253269]
            if os.path.exists('honeypot_settings.json'):
                try:
                    with open('honeypot_settings.json', 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        guild_data = data.get(str(message.guild.id), {})
                        if isinstance(guild_data, dict):
                            excluded_roles.extend(guild_data.get("excluded_roles", []))
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

        author_id = str(message.author.id)
        
        # 從 SQLite 讀取用戶紀錄
        user_record = self._get_user_record(author_id)
        
        # 2. 檢查他發布的前 10 筆訊息
        # 如果已經達到 10 筆，就不再進行後續記錄與防禦流程 (節省效能)
        if user_record["c"] >= 10:
            return

        # 更新 SQLite 記錄並回傳最新發言次數 (所有未滿10次的非免疫用戶，不論新舊帳號皆進行後台計數)
        new_count = self._increment_user_count(author_id)

        # 1. 雙重判斷門檻：
        # - 帳號註冊時間在 180 天 (6 個月) 以內 (is_new_account)
        # - 或 加入伺服器時間在 90 天以內 (is_recent_join)
        now = discord.utils.utcnow()
        account_age_days = (now - message.author.created_at).days
        joined_at = getattr(message.author, 'joined_at', None)
        join_age_seconds = (now - joined_at).total_seconds() if joined_at else None
        join_age_days = int(join_age_seconds // 86400) if join_age_seconds is not None else None

        is_new_account = account_age_days <= 180
        is_recent_join = join_age_days is not None and join_age_days <= 90
        is_very_recent_join = join_age_seconds is not None and join_age_seconds <= 900  # 剛進伺服器 15 分鐘 (900 秒) 內

        # 讀取外部設定 (全域監控開關)
        settings = self.get_settings()
        global_monitor = settings.get("global_monitor", False)

        # 防禦檢查與頻道通報門檻：
        # 若 global_monitor 為 False 且既不是 6 個月內新創帳號，也不是 90 天內剛加入的成員，則僅於後台記錄次數，不執行防禦與通報
        should_defend = global_monitor or is_new_account or is_recent_join
        if not should_defend:
            return

        # 輸出訊息到 OUTPUT_ID
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                bot_config = json.load(f)
            output_id = bot_config.get("OUTPUT_ID")
            if output_id:
                output_channel = self.bot.get_channel(int(output_id))
                if output_channel:
                    join_str = f"{join_age_days}天" if join_age_days is not None else "未知"
                    tag_prefix = "[全域監控] " if global_monitor and not (is_new_account or is_recent_join) else ""
                    await output_channel.send(
                        f"⚠️ {tag_prefix}用戶 {message.author.mention} ({author_id}) 觸發了計數 "
                        f"[帳號:{account_age_days}天 | 進群:{join_str}]，目前次數：**{new_count}/10**"
                    )
        except Exception as e:
            print(f"⚠️ [幹男防護] 發送 counts 統計訊息時發生錯誤: {e}")

        target_users = set(settings.get("target_users", []))
        bad_words = settings.get("bad_words", [])

        explicit_mentions = self._get_explicit_mentions(message)
        mentioned_target_count = sum(1 for user in explicit_mentions if user.id in target_users)

        #【精準擊殺規則 1】：新用戶前 10 筆訊息內，只要標記任何保護對象 (管理員/VIP) -> 先刪除訊息再 BAN
        if mentioned_target_count >= 1:
            try:
                await message.delete()
            except Exception:
                pass

            bot_member = message.guild.get_member(self.bot.user.id) or await message.guild.fetch_member(self.bot.user.id)
            if not bot_member.guild_permissions.ban_members or bot_member.top_role <= message.author.top_role:
                print(f"⚠️ [幹男防護] 機器人權限不足，無法 Ban 用戶 {message.author}")
                return
            
            try:
                reason = "觸發幹婆你男娘防禦：新用戶前10筆訊息惡意標記保護對象"
                await message.author.ban(reason=reason, delete_message_seconds=1800)
                print(f"🚨 [幹男防護] 已 Ban 惡意用戶 {message.author} ({message.author.id}) - 理由: 前10筆訊息標記保護對象")
                await self._send_kill_announcement(message.channel, message.author, "新用戶於前10筆訊息內惡意標記保護對象", raw_content=message.content)
            except discord.Forbidden:
                print(f"⚠️ [幹男防護] 機器人權限不足，無法 Ban 用戶 {message.author}")
            except discord.HTTPException as e:
                print(f"⚠️ [幹男防護] Ban 用戶時發生錯誤: {e}")
            return

        #【精準禁言規則 3】：新用戶短時間 (60秒) 內連續發送 5 則包含圖片/附件的訊息 -> 禁言 1 小時
        has_attachments = len(message.attachments) > 0
        now_ts = discord.utils.utcnow().timestamp()

        # 追蹤與過濾近 60 秒內發送圖片/附件的歷史紀錄
        user_img_history = self.user_img_history.get(author_id, [])
        user_img_history = [t for t in user_img_history if now_ts - t <= 60]

        if has_attachments:
            user_img_history.append(now_ts)
            self.user_img_history[author_id] = user_img_history

        # 觸發條件：短時間 (60秒) 內發送 5 則包含圖片/附件的訊息
        if len(user_img_history) >= 5:
            try:
                await message.delete()
            except Exception:
                pass

            bot_member = message.guild.get_member(self.bot.user.id) or await message.guild.fetch_member(self.bot.user.id)
            if not bot_member.guild_permissions.moderate_members or bot_member.top_role <= message.author.top_role:
                print(f"⚠️ [幹男防護] 機器人權限不足，無法禁言用戶 {message.author}")
                return
            try:
                reason_text = "新用戶 60 秒內連續發送 5 則圖片/附件訊息洗板"
                if isinstance(message.author, discord.Member):
                    await message.author.timeout(datetime.timedelta(hours=1), reason=f"觸發幹婆你男娘防禦：{reason_text}")
                print(f"🛑 [幹男防護] 已禁言圖片洗板用戶 {message.author} ({message.author.id}) 1小時 - 理由: {reason_text}")
                await self._send_timeout_announcement(message.channel, message.author, reason_text, raw_content=message.content)
            except discord.Forbidden:
                print(f"⚠️ [幹男防護] 機器人權限不足，無法禁言用戶 {message.author}")
            except discord.HTTPException as e:
                print(f"⚠️ [幹男防護] 禁言用戶時發生錯誤: {e}")
            return

        #【精準禁言規則 5】：大字體洗板與組合騷擾打擊
        is_header_format = any(line.strip().startswith('#') for line in (message.content or "").splitlines())
        user_headers = self.user_header_history.get(author_id, [])
        user_headers.append(is_header_format)
        self.user_header_history[author_id] = user_headers

        # 條件 1 (組合打擊)：前 2 則訊息內使用「#」大字體 ＋ 標記任何成員 (排除 Reply 自動提及)
        is_early_header_mention = (new_count <= 2) and is_header_format and (len(explicit_mentions) > 0)
        # 條件 2 (門檻縮短)：連續 2 則訊息均包含「#」大字體 Markdown 格式
        is_consecutive_headers = len(user_headers) >= 2 and all(user_headers[-2:])

        if is_early_header_mention or is_consecutive_headers:
            try:
                await message.delete()
            except Exception:
                pass

            try:
                if is_early_header_mention:
                    reason_text = "新用戶於前 2 則訊息使用「#」大字體並標記成員進行騷擾"
                else:
                    reason_text = "新用戶連續 2 則訊息皆使用「#」大字體 Markdown 格式洗板"

                if isinstance(message.author, discord.Member):
                    await message.author.timeout(datetime.timedelta(hours=1), reason=f"觸發幹婆你男娘防禦：{reason_text}")
                print(f"🚨 [幹男防護] 已禁言大字騷擾/洗板用戶 {message.author} ({message.author.id}) 1小時 - 理由: {reason_text}")
                await self._send_timeout_announcement(message.channel, message.author, reason_text, raw_content=message.content)
            except discord.Forbidden:
                print(f"⚠️ [幹男防護] 機器人權限不足，無法禁言用戶 {message.author}")
            except discord.HTTPException as e:
                print(f"⚠️ [幹男防護] 禁言用戶時發生錯誤: {e}")
            return

        # 文字內容、附件檔名與顯示暱稱關鍵字檢測（包含正規化與原字串比對）
        attachment_names = " ".join(att.filename for att in message.attachments) if message.attachments else ""
        raw_content = ((message.content or "") + " " + attachment_names).strip()
        norm_content = self._normalize_text(raw_content)
        
        # 僅比對用戶於伺服器設定的暱稱 (nick) 或全域顯示名稱 (global_name)，不比對 Discord 英文 ID/帳號句柄 (name)
        raw_name = (getattr(message.author, 'nick', None) or getattr(message.author, 'global_name', None) or "")
        norm_name = self._normalize_text(raw_name)

        #【精準擊殺規則 4】：新用戶重複或高度相似訊息洗板禁言邏輯 (已排除 @標記影響與短句誤判)
        # 1. 剔除 Discord Mentions (使用者/身分組/頻道標記)，只留純文字比對，防止連 Ping 或變更標記被誤判
        text_without_mentions = re.sub(r'<[@#][!&]?\d+>', '', raw_content).strip()
        norm_text_no_mentions = self._normalize_text(text_without_mentions)

        # 2. 歷史發言處理 (保留近 60 秒發言紀錄)
        history = self.user_msg_history.get(author_id, [])
        history = [h for h in history if now_ts - h[0] <= 60]

        exact_duplicate_count = 0
        similar_count = 0

        for past_ts, past_norm, past_raw in history:
            # 完整原文（正規化後）完全相同
            if norm_content and norm_content == past_norm:
                exact_duplicate_count += 1
            # 剔除 @標記後的文字內容完全相同
            elif norm_text_no_mentions and norm_text_no_mentions == self._normalize_text(re.sub(r'<[@#][!&]?\d+>', '', past_raw)):
                similar_count += 1
            # 高度相似性比對：僅在非 Mention 文字長度 >= 8 字元時進行 (閥值提高至 90%)
            elif len(norm_text_no_mentions) >= 8:
                past_no_mention = self._normalize_text(re.sub(r'<[@#][!&]?\d+>', '', past_raw))
                if len(past_no_mention) >= 8:
                    ratio = difflib.SequenceMatcher(None, norm_text_no_mentions, past_no_mention).ratio()
                    if ratio >= 0.90:
                        similar_count += 1

        history.append((now_ts, norm_content, raw_content))
        self.user_msg_history[author_id] = history

        # 觸發洗板防誤判條件：
        # - 完全相同訊息允許發送 3 次 (第 4 次觸發: exact_duplicate_count >= 3)
        # - 扣除標記後高度相似訊息允許發送 5 次 (第 6 次觸發: similar_count >= 5)
        # - 近 60 秒內發言總數達到 7 次以上 (極高頻率洗板)
        is_spam = (exact_duplicate_count >= 3) or (similar_count >= 5) or (len(history) >= 7)

        if is_spam:
            try:
                await message.delete()
            except Exception:
                pass

            bot_member = message.guild.get_member(self.bot.user.id) or await message.guild.fetch_member(self.bot.user.id)
            if not bot_member.guild_permissions.moderate_members or bot_member.top_role <= message.author.top_role:
                print(f"⚠️ [幹男防護] 機器人權限不足，無法禁言用戶 {message.author}")
                return
            try:
                if exact_duplicate_count >= 3:
                    reason_text = "新用戶發送超過 3 次完全相同訊息洗板"
                elif similar_count >= 5:
                    reason_text = "新用戶發送超過 5 次高度相似訊息洗板"
                else:
                    reason_text = "新用戶 60 秒內高頻發言 (>= 7 次) 洗板"

                if isinstance(message.author, discord.Member):
                    await message.author.timeout(datetime.timedelta(hours=1), reason=f"觸發幹婆你男娘防禦：{reason_text}")
                print(f"🛑 [幹男防護] 已禁言洗板用戶 {message.author} ({message.author.id}) 1小時 - 理由: {reason_text}")
                await self._send_timeout_announcement(message.channel, message.author, reason_text, raw_content=raw_content)
            except discord.Forbidden:
                print(f"⚠️ [幹男防護] 機器人權限不足，無法禁言用戶 {message.author}")
            except discord.HTTPException as e:
                print(f"⚠️ [幹男防護] 禁言用戶時發生錯誤: {e}")
            return

        # 1. 傳統與擴充關鍵字庫比對
        content_has_bad_word = any(word in raw_content or word in norm_content for word in bad_words)
        
        # 暱稱比對嚴格化：排除容易造成誤 BAN 的通用/短詞 (如 pvp, 正解, 小草, 宿舍等)，僅比對高風險嚴重侮辱/恐嚇關鍵字
        nickname_excluded_words = {
            "pvp", "PVP", "c8", "C8", "小草", "白草", "藍草", "雜草", "草包", "藍白", "白藍", 
            "柯粉", "蔥粉", "黃狗", "綠狗", "綠共", "塔綠班", "正解", "選我正解", "香檳", "開香檳", 
            "預測", "預報", "預側", "COMPUTEX", "101世貿", "南港館", "宿舍", "屎", "解鎖", 
            "沒種", "噴人", "瞎掰", "躲封鎖", "躲封", "炸一次", "鎖一次", "三寶", "憨點", "憨包", 
            "主機板", "鬼態度", "好好講", "好好跟你說", "殺小", "雙北毀", "大噴發", "巨震", "毀滅"
        }
        
        name_has_bad_word = False
        # 僅限定於剛進伺服器 15 分鐘 (is_very_recent_join) 內進行暱稱比對
        if raw_name and is_very_recent_join:
            name_has_bad_word = any(
                (word in raw_name or word in norm_name)
                for word in bad_words
                if word not in nickname_excluded_words
            )

        # 2.【組合式特徵正則比對】(結合實際攻擊截圖特徵)
        regex_patterns = [
            # 組合A：展場/地點/家/宿舍 + 放炸彈/炸掉/💣 (Computex, 101世貿, 南港館, 女友家, 宿舍)
            r'(computex|101|世貿|南港|展場|展館|你家|女友家|學校|宿舍).*?(放|炸|💣|炸彈|爆破|綁)',
            r'(放|炸|💣|炸彈|爆破|綁).*?(computex|101|世貿|南港|展場|展館|你家|女友家|學校|宿舍)',
            
            # 組合B：詛咒/全家/親屬/死亡/追殺/恐嚇 (S全家, 死狗, 捅死, 西八, 妓女, 綠茶婊, 混蛋, 鎖一次...炸一次, 欠炸宿舍, 欠捅)
            r'(s|死|殺|炸|捅)(全家|人|狗|親|爸|媽|娘|死)',
            r'(家裡|你家|妳家).*?(s|死|毀|垮|炸)',
            r'(你|妳|他|她)媽(死|染疫|亡|逼)',
            r'(賤|死|破|混蛋|排擠)(狗|嘴|b|B|麻)',
            r'(機|雞)(掰|八)',
            r'(c|C)8|nmsl|NMSL|pvp|PVP|ㄙㄌㄋ',
            r'78(毛)?|拎(北|爸)',
            r'💣(掉|爆|毀)?',
            r'(管理|破)(狗|豬|畜)',
            r'欠(插|壓|幹|操|殺|捅|炸)',
            r'(賴|操|幹|幹爆)你媽(逼|個)?',
            r'鎖(一|1)次.*?(炸|加|開)',
            r'(鎖|開|加|炸)(一|1)次',

            # 組合C：假地震恐嚇 (如 7.4/7.8/3主震 + 6小時/毀滅/噴發)
            r'(\d+\.\d+|\d+級|\d+主震).*?(小時|毀滅|噴發|巨震|預測|預報|正解|大地震)',
            r'(雙北|台北|台灣|大屯|火山).*?(毀滅|噴發|大噴發|巨震)',

            # 組合D：猥褻/性器官與騷擾詞彙 (如 屁眼/肛門/菊花/懶叫/關心...屁眼)
            r'(屁眼|肛門|菊花|懶叫|陰莖|陰道)',
            r'(關心|每天關心).*?(屁眼|肛門|菊花|器官|健康)',

            # 組合E：英文侮辱詞根與惡意用戶名變形 (如 fkass, fuckass, btchmod, asshole)
            r'(fk|fuck)(ass|btch|bitch|mod|er|ing)',
            r'(asshole|fuckass|btchmod)',
            r'\b(fuck|bitch|btch|asshole)\b'
        ]

        has_regex_match = any(
            re.search(pat, raw_content, re.IGNORECASE) or re.search(pat, norm_content, re.IGNORECASE)
            for pat in regex_patterns
        )

        # 地震群單純感嘆詞豁免白名單 (如單字「幹」或三字「幹你娘/幹妳娘」純感嘆時免受 BAN 懲罰)
        exempted_interjections = {"幹", "幹你娘", "幹妳娘"}

        # 檢查命中的 bad_words 是否全屬於豁免感嘆詞
        matched_bad_words = [word for word in bad_words if word in raw_content or word in norm_content]
        is_only_interjection_matched = matched_bad_words and all(bw in exempted_interjections for bw in matched_bad_words)

        # 判定是否包含其他攻擊性內容：如果只命中豁免感嘆詞、且無正則恐嚇、無暱稱違規，則進行豁免
        if is_only_interjection_matched and not name_has_bad_word and not has_regex_match:
            content_has_bad_word = False

        has_bad_word = content_has_bad_word or name_has_bad_word or has_regex_match

        #【精準擊殺規則 2】：發言或暱稱包含違規/恐嚇/正則特徵 -> 嘗試刪除訊息、直接 BAN 並發送頻道通報
        if has_bad_word:
            try:
                await message.delete()
            except Exception:
                pass

            bot_member = message.guild.get_member(self.bot.user.id) or await message.guild.fetch_member(self.bot.user.id)
            if not bot_member.guild_permissions.ban_members or bot_member.top_role <= message.author.top_role:
                print(f"⚠️ [幹男防護] 機器人權限不足，無法 Ban 用戶 {message.author}")
                return
            
            try:
                reason = "觸發幹婆你男娘防禦：發布恐嚇言論、炸彈威脅、政治仇恨或不當暱稱"
                await message.author.ban(reason=reason, delete_message_seconds=1800)
                print(f"🚨 [幹男防護] 已 Ban 惡意用戶 {message.author} ({message.author.id}) - 理由: 命中攻擊關鍵字或正則特徵")
                await self._send_kill_announcement(message.channel, message.author, "發布恐嚇言論、炸彈威脅、政治仇恨或不當暱稱", raw_content=raw_content)
            except discord.Forbidden:
                print(f"⚠️ [幹男防護] 機器人權限不足，無法 Ban 用戶 {message.author}")
            except discord.HTTPException as e:
                print(f"⚠️ [幹男防護] Ban 用戶時發生錯誤: {e}")

    @app_commands.command(name="counts", description="查看目前的發言統計 (僅限管理員)")
    @app_commands.default_permissions(administrator=True)
    async def counts_command(self, interaction: discord.Interaction):
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM message_counts WHERE count < 10")
                pending_count = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM message_counts WHERE count >= 10")
                completed_count = cursor.fetchone()[0]

                # 優先抓出還在監控中 (count < 10) 的用戶，最多列出 30 筆
                cursor.execute("SELECT user_id, count FROM message_counts WHERE count < 10 ORDER BY count DESC LIMIT 30")
                pending_rows = cursor.fetchall()
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢資料庫時發生錯誤: {e}", ephemeral=True)
            return

        settings = self.get_settings()
        global_monitor = settings.get("global_monitor", False)
        status_str = "已開啟 🟢 (已包含潛水舊用戶)" if global_monitor else "已關閉 🔴 (僅限新帳號/新成員)"

        summary_header = (
            f"🛡️ **全域監控狀態**：{status_str}\n"
            f"📊 **統計總覽**：監控中 (`<10`次)：**{pending_count}** 人 | 已畢業 (`>=10`次)：**{completed_count}** 人\n"
            f"───────────────────────────"
        )

        lines = [summary_header]

        if pending_rows:
            lines.append("🔍 **目前監控中用戶 (未滿 10 次)**：")
            for author_id, count in pending_rows:
                try:
                    created_ts = int(discord.utils.snowflake_time(int(author_id)).timestamp())
                    created_str = f"<t:{created_ts}:d>"
                except Exception:
                    created_str = "未知"
                lines.append(f"• <@{author_id}> ── 創建: {created_str} | 次數: **{count}/10**")
        else:
            lines.append("✅ 目前沒有任何未滿 10 次的監控中用戶。")

        content = "\n".join(lines)
        if len(content) > 4000:
            content = content[:4000] + "\n... (訊息過長已截斷)"

        embed = discord.Embed(title="📊 發言統計 (SQLite)", description=content, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(FkfeboyCog(bot))
