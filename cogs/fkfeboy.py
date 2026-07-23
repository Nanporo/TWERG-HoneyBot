import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os

class FkfeboyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings_file = 'fkfeboy_settings.json'
        self.counts_file = 'fkfeboy_counts.json'
        # 用於記錄新使用者的發言次數 (user_id -> count)
        self.message_counts = self._load_counts()
        self._cached_settings = None
        self._last_mtime = 0
        
        # 啟動自動清理任務
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    def _load_counts(self):
        if os.path.exists(self.counts_file):
            try:
                with open(self.counts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # 自動遷移舊版資料格式：從純數字轉為包含時間戳的字典 {"c": 次數, "t": 時間戳}
                now_ts = discord.utils.utcnow().timestamp()
                for k, v in data.items():
                    if isinstance(v, int):
                        data[k] = {"c": v, "t": now_ts}
                return data
            except Exception:
                pass
        return {}

    def _save_counts(self):
        with open(self.counts_file, 'w', encoding='utf-8') as f:
            json.dump(self.message_counts, f, ensure_ascii=False)

    # 如果沒有生成 fkfeboy_settings.json 就自動生成一個，以下是預設值
    # 包含在 TWERG 常被 at 的特定用戶 ID，可使情況自行修改或是後續修改 json 來調整
    def get_settings(self):
        default_settings = {
            "target_users": [
                964849855396741130,
                1356782484565790840, # 應該是台灣 Online 的管理員
                782499307717656596, 
                815574915901554699, # ExpTech 的管理員
                69370157784371200, # 這人 ID 怎麼比別人少1碼
            ],
            "bad_words": [
                "幹破", "放炸彈", "破狗", "破草", "王八蛋", "好好跟你說", "主機板", 
                "操你媽的", "炸你", "死賤貨", "殺小", "雞巴", "炸群", "鬼態度", "好好講"
            ]
        }
        if not os.path.exists(self.settings_file):
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(default_settings, f, ensure_ascii=False, indent=4)
            self._cached_settings = default_settings
            self._last_mtime = os.path.getmtime(self.settings_file)
            return self._cached_settings

        # 檢查檔案的最後修改時間，如果有更新才重新讀取硬碟，否則使用記憶體內的快取
        current_mtime = os.path.getmtime(self.settings_file)
        if self._cached_settings is None or current_mtime > self._last_mtime:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                try: 
                    self._cached_settings = json.load(f)
                    self._last_mtime = current_mtime
                except json.JSONDecodeError: 
                    return default_settings
        
        return self._cached_settings

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        if not self.message_counts:
            return
            
        now_ts = discord.utils.utcnow().timestamp()
        ninety_days_sec = 90 * 24 * 60 * 60  # 90天的秒數
        keys_to_delete = []
        
        for author_id, data in self.message_counts.items():
            if isinstance(data, dict):
                # 如果最後發言時間距離現在超過 90 天，則列入刪除名單
                if now_ts - data.get("t", now_ts) > ninety_days_sec:
                    keys_to_delete.append(author_id)
                    
        if keys_to_delete:
            for k in keys_to_delete:
                del self.message_counts[k]
            self._save_counts()
            
    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 忽略機器人與私訊
        if message.author.bot or message.guild is None:
            return

        # 1. 檢查帳號的註冊時間是否小於 3 個月 (以 90 天計算)
        # message.author.created_at 是 UTC 帶有時區的 datetime，必須用 utcnow 比對
        now = discord.utils.utcnow()
        if (now - message.author.created_at).days > 90:
            return

        # JSON 格式的 key 必須是字串，轉換 ID 型別
        author_id = str(message.author.id)
        
        # 取得用戶紀錄，預設為 {"c": 0, "t": 0}
        user_record = self.message_counts.get(author_id, {"c": 0, "t": 0})
        
        # 2. 檢查他進入伺服器後發布的前 10 筆訊息
        # 如果已經達到 10 筆，就不再進行後續防禦流程與硬碟寫入 (節省效能)
        if user_record["c"] >= 10:
            return

        # 更新次數與最後發言的時間戳記
        new_count = user_record["c"] + 1
        self.message_counts[author_id] = {
            "c": new_count,
            "t": discord.utils.utcnow().timestamp()
        }
        self._save_counts()

        # 輸出訊息到 OUTPUT_ID
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                bot_config = json.load(f)
            output_id = bot_config.get("OUTPUT_ID")
            if output_id:
                output_channel = self.bot.get_channel(int(output_id))
                if output_channel:
                    await output_channel.send(f"⚠️ 新用戶 {message.author.mention} ({author_id}) 觸發了計數，目前次數：**{new_count}/10**")
        except Exception as e:
            print(f"⚠️ [幹男防護] 發送 counts 統計訊息時發生錯誤: {e}")

        # 讀取外部設定
        settings = self.get_settings()
        target_users = set(settings.get("target_users", []))
        bad_words = settings.get("bad_words", [])

        mentioned_target_count = sum(1 for user in message.mentions if user.id in target_users)
        has_bad_word = any(word in message.content for word in bad_words)

        # 3. 條件一：如果包含同時 at 了普通用戶的其中 2 人，則直接 ban
        # 或者條件二：at 了 1 位普通用戶，並且包含違規字眼，也是直接 ban

        if mentioned_target_count >= 2 or (mentioned_target_count == 1 and has_bad_word):
            try:
                reason = "觸發幹婆你男娘防禦：惡意標記特定普通用戶"
                await message.author.ban(reason=reason, delete_message_seconds=1800)
                print(f"🚨 [幹男防護] 已 Ban 惡意用戶 {message.author} ({message.author.id}) - 理由: 惡意標記")
            except discord.Forbidden:
                print(f"⚠️ [幹男防護] 機器人權限不足，無法 Ban 用戶 {message.author}")
            except discord.HTTPException as e:
                print(f"⚠️ [幹男防護] Ban 用戶時發生錯誤: {e}")
            
            return # 觸發 Ban 後直接結束，不繼續檢查

        if has_bad_word:
            try:
                reason = "觸發幹婆你男娘防禦：發布恐嚇或不當字眼"
                await message.author.kick(reason=reason)
                print(f"🚨 [幹男防護] 已 Kick 惡意用戶 {message.author} ({message.author.id}) - 理由: 恐嚇言論")
            except discord.Forbidden:
                print(f"⚠️ [幹男防護] 機器人權限不足，無法 Kick 用戶 {message.author}")
            except discord.HTTPException as e:
                print(f"⚠️ [幹男防護] Kick 用戶時發生錯誤: {e}")

    @app_commands.command(name="counts", description="查看目前的發言統計 (僅限管理員)")
    @app_commands.default_permissions(administrator=True)
    async def counts_command(self, interaction: discord.Interaction):
        if not self.message_counts:
            await interaction.response.send_message("目前沒有任何統計資料。", ephemeral=True)
            return

        lines = []
        for author_id, data in self.message_counts.items():
            count = data.get("c", 0) if isinstance(data, dict) else data
            try:
                created_ts = int(discord.utils.snowflake_time(int(author_id)).timestamp())
                created_str = f"<t:{created_ts}:d>"
            except Exception:
                created_str = "未知"
            lines.append(f"• <@{author_id}>\n　創建: {created_str} | 次數: **{count}**")
            
        content = "\n\n".join(lines)
        if len(content) > 4000:
            content = content[:4000] + "\n\n... (訊息過長已截斷)"
            
        embed = discord.Embed(title="📊 發言統計", description=content, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(FkfeboyCog(bot))
