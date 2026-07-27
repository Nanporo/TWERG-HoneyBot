import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import sqlite3
import re

class FkfeboyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings_file = 'fkfeboy_settings.json'
        self.db_file = 'fkfeboy_counts.db'
        self._cached_settings = None
        self._last_mtime = 0
        
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
        """當成功封鎖惡意用戶時，在觸發頻道發送通報 Embed"""
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

    def get_settings(self):
        """
        讀取或初始化幹男防禦設定檔 (fkfeboy_settings.json)。
        若 JSON 已存在，自動升級並合併廣泛化與詞根化的預設關鍵字。
        """
        default_settings = {
            "target_users": [
                964849855396741130,
                1356782484565790840, # 台灣 Online 管理員 / 頑固苗獨份子
                782499307717656596, 
                815574915901554699, # ExpTech 管理員 / eggrollpvp
                69370157784371200, 
                675922096425009184, # Yoyo0901
            ],
            "bad_words": [
                # 1. 傳統粗口、公然侮辱與威脅詞根
                "幹破", "幹爆", "放炸彈", "破狗", "破草", "王八蛋", "好好跟你說", "主機板", 
                "操你媽", "幹你娘", "幹妳娘", "炸你", "死賤貨", "賤貨", "殺小", 
                "雞巴", "機掰", "機八", "炸群", "鬼態度", "好好講", "賤狗", "死狗", "狗嘴",
                "死西八", "西八", "破麻", "綠茶婊", "妓女", "混蛋狗", "混蛋", "排擠狗",

                # 2. 人身攻擊、智力/身障侮辱、詛咒、威脅與騷擾詞根
                "低能", "智障", "弱智", "腦殘", "腦癱", "賤畜", "破B", "破b", "死出來",
                "欠壓", "壓S", "壓s", "欠幹", "欠操", "死全家", "全家死", "家也會被震垮", 
                "震垮", "憨點", "憨包", "三寶", "S全家", "S人", "S人了", "賴你媽逼", 
                "死機掰", "貪破你娘", "死破狗", "管理狗", "欠插殺", "欠插", "支持炸群", "炸你們群",
                "你媽死", "媽死", "死人", "染疫", "nmsl", "NMSL", "c8", "C8", "解鎖", "沒種", "狗啃",
                "捅死", "pvp", "PVP", "死腦筋", "噴人", "瞎掰", "躲封鎖", "躲封", "炸一次", "鎖一次",

                # 3. 政治仇恨攻擊與侮辱性稱呼詞根
                "藍白", "白藍", "藍狗", "白狗", "藍豬", "白豬", "小草", "草包", "雜草",
                "藍草", "白草", "柯粉", "蔥粉", "黃狗", "綠狗", "綠共", "塔綠班",

                # 4. 假地震恐嚇、恐攻與場館威脅
                "毀滅", "巨震", "大噴發", "預報", "預測", "預側", 
                "雙北毀", "開香檳", "香檳", "靈氣強震", "3主震", "選我正解", "正解",
                "COMPUTEX", "101世貿", "南港館", "綁起來", "炸掉", "賴先生", "恐龍", "暴龍",
                "宿舍", "欠捅", "欠炸"
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
                    updated = False

                    # 自動將新增的廣泛預設關鍵字與目標用戶併入既有設定檔
                    existing_bad_words = set(settings.get("bad_words", []))
                    for bw in default_settings["bad_words"]:
                        if bw not in existing_bad_words:
                            settings.setdefault("bad_words", []).append(bw)
                            updated = True

                    existing_targets = set(settings.get("target_users", []))
                    for tu in default_settings["target_users"]:
                        if tu not in existing_targets:
                            settings.setdefault("target_users", []).append(tu)
                            updated = True

                    if updated:
                        with open(self.settings_file, 'w', encoding='utf-8') as wf:
                            json.dump(settings, wf, ensure_ascii=False, indent=4)

                    self._cached_settings = settings
                    self._last_mtime = os.path.getmtime(self.settings_file)
                except json.JSONDecodeError: 
                    return default_settings

        return self._cached_settings

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """每日清理超過 90 天未再發言的歷史用戶紀錄"""
        now_ts = discord.utils.utcnow().timestamp()
        ninety_days_sec = 90 * 24 * 60 * 60  # 90天的秒數
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 忽略機器人與私訊
        if message.author.bot or message.guild is None:
            return

        # 免疫檢查：伺服器管理員或身份組層級不低於機器人者免受懲罰
        if isinstance(message.author, discord.Member):
            is_immune = (
                message.author.guild_permissions.administrator or
                (message.guild.me and message.author.top_role >= message.guild.me.top_role)
            )
            if is_immune:
                return

        # 1. 雙重判斷門檻：
        # - 帳號註冊時間在 90 天以內 (is_new_account)
        # - 或 加入伺服器時間在 30 天以內 (is_recent_join)
        now = discord.utils.utcnow()
        account_age_days = (now - message.author.created_at).days
        joined_at = getattr(message.author, 'joined_at', None)
        join_age_days = (now - joined_at).days if joined_at else None

        is_new_account = account_age_days <= 90
        is_recent_join = join_age_days is not None and join_age_days <= 30

        # 若既不是新創帳號，也不是近期剛加入的成員，則忽略防禦檢查
        if not (is_new_account or is_recent_join):
            return

        # JSON 格式的 key 必須是字串，轉換 ID 型別
        author_id = str(message.author.id)
        
        # 從 SQLite 讀取用戶紀錄
        user_record = self._get_user_record(author_id)
        
        # 2. 檢查他發布的前 10 筆訊息
        # 如果已經達到 10 筆，就不再進行後續防禦流程 (節省效能)
        if user_record["c"] >= 10:
            return

        # 更新 SQLite 記錄並回傳最新發言次數
        new_count = self._increment_user_count(author_id)

        # 輸出訊息到 OUTPUT_ID
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                bot_config = json.load(f)
            output_id = bot_config.get("OUTPUT_ID")
            if output_id:
                output_channel = self.bot.get_channel(int(output_id))
                if output_channel:
                    join_str = f"{join_age_days}天" if join_age_days is not None else "未知"
                    await output_channel.send(
                        f"⚠️ 新用戶 {message.author.mention} ({author_id}) 觸發了計數 "
                        f"[帳號:{account_age_days}天 | 進群:{join_str}]，目前次數：**{new_count}/10**"
                    )
        except Exception as e:
            print(f"⚠️ [幹男防護] 發送 counts 統計訊息時發生錯誤: {e}")

        # 讀取外部設定
        settings = self.get_settings()
        target_users = set(settings.get("target_users", []))
        bad_words = settings.get("bad_words", [])

        mentioned_target_count = sum(1 for user in message.mentions if user.id in target_users)

        # ⚡【精準擊殺規則 1】：新用戶前 10 筆訊息內，只要標記任何保護對象 (管理員/VIP) -> 直接 BAN 並發送頻道通報
        if mentioned_target_count >= 1:
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

        # 文字內容與顯示暱稱雙重關鍵字檢測（包含正規化與原字串比對）
        raw_content = message.content or ""
        norm_content = self._normalize_text(raw_content)
        
        raw_name = getattr(message.author, 'display_name', '') or ""
        norm_name = self._normalize_text(raw_name)

        # 1. 傳統與擴充關鍵字庫比對
        content_has_bad_word = any(word in raw_content or word in norm_content for word in bad_words)
        name_has_bad_word = any(word in raw_name or word in norm_name for word in bad_words)

        # 2. ⚡【組合式特徵正則比對】(結合實際攻擊截圖特徵)
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
            r'(c|C)8|nmsl|NMSL|pvp|PVP',
            r'(管理|破)(狗|豬|畜)',
            r'欠(插|壓|幹|操|殺|捅|炸)',
            r'(賴|操|幹|幹爆)你媽(逼|個)?',
            r'鎖(一|1)次.*?(炸|加|開)',
            r'(鎖|開|加|炸)(一|1)次',

            # 組合C：假地震恐嚇 (如 7.4/7.8/3主震 + 6小時/毀滅/噴發)
            r'(\d+\.\d+|\d+級|\d+主震).*?(小時|毀滅|噴發|巨震|預測|預報|正解|大地震)',
            r'(雙北|台北|台灣|大屯|火山).*?(毀滅|噴發|大噴發|巨震)'
        ]

        has_regex_match = any(
            re.search(pat, raw_content, re.IGNORECASE) or re.search(pat, norm_content, re.IGNORECASE)
            for pat in regex_patterns
        )

        has_bad_word = content_has_bad_word or name_has_bad_word or has_regex_match

        # ⚡【精準擊殺規則 2】：發言或暱稱包含違規/恐嚇/正則特徵 -> 嘗試刪除訊息、直接 BAN 並發送頻道通報
        if has_bad_word:
            try:
                await message.delete()
            except Exception:
                pass

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
                cursor.execute("SELECT user_id, count FROM message_counts ORDER BY count DESC")
                rows = cursor.fetchall()
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢資料庫時發生錯誤: {e}", ephemeral=True)
            return

        if not rows:
            await interaction.response.send_message("目前沒有任何統計資料。", ephemeral=True)
            return

        lines = []
        for author_id, count in rows:
            try:
                created_ts = int(discord.utils.snowflake_time(int(author_id)).timestamp())
                created_str = f"<t:{created_ts}:d>"
            except Exception:
                created_str = "未知"
            lines.append(f"• <@{author_id}>\n　創建: {created_str} | 次數: **{count}**")
            
        content = "\n\n".join(lines)
        if len(content) > 4000:
            content = content[:4000] + "\n\n... (訊息過長已截斷)"
            
        embed = discord.Embed(title="📊 發言統計 (SQLite)", description=content, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(FkfeboyCog(bot))
