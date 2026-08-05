import ssl
import certifi

# Fix for "ssl.SSLError: [ASN1: NOT_ENOUGH_DATA] not enough data" on Windows
orig_create_default_context = ssl.create_default_context

def patched_create_default_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None):
    if cafile is None and capath is None and cadata is None:
        cafile = certifi.where()
    return orig_create_default_context(purpose, cafile=cafile, capath=capath, cadata=cadata)

ssl.create_default_context = patched_create_default_context

import discord
from discord.ext import commands
import json
import os
import asyncio
import sys

# 讀取設定檔
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
except FileNotFoundError:
    sys.exit("❌ 錯誤：找不到 config.json 檔案！請先根據 README.md 的指示建立設定檔。")
except json.JSONDecodeError as e:
    sys.exit(f"❌ 錯誤：config.json 格式錯誤！請檢查是否漏了引號、逗號或是直接貼上了中文提示詞。\n詳細錯誤：{e}")

intents = discord.Intents.default()
intents.members = False
intents.message_content = True

owner_id_cfg = config.get('OWNER_ID')
if isinstance(owner_id_cfg, list):
    owner_ids = set(owner_id_cfg)
elif isinstance(owner_id_cfg, int):
    owner_ids = {owner_id_cfg}
else:
    owner_ids = None

bot = commands.Bot(
    command_prefix=(), 
    intents=intents, 
    owner_ids=owner_ids, 
    help_command=None,
    allowed_mentions=discord.AllowedMentions().none()
)

@bot.event
async def on_ready():
    # 同步斜線指令到 Discord 伺服器 (全域與特許擁有者伺服器)
    await bot.tree.sync()
    for gid in [518699949500661760, 897116721159233576]:
        try:
            await bot.tree.sync(guild=discord.Object(id=gid))
        except Exception as e:
            print(f"⚠️ [Tree Sync] 同步特許伺服器 ({gid}) 斜線指令失敗: {e}")

    total_members = sum(guild.member_count for guild in bot.guilds if guild.member_count)
    print(f'登入成功！, 總計 {total_members} 個成員，位於 {len(bot.guilds)} 個伺服器中。')
    activity = discord.Activity(type=discord.ActivityType.watching, name='地震監視')
    await bot.change_presence(activity=activity)

@bot.event
async def on_guild_join(guild):
    print(f'New guild joined: {guild.name} (id: {guild.id}). This guild has {guild.member_count} members!')

@bot.event
async def on_guild_remove(guild):
    print(f'I have been removed from: {guild.name} (id: {guild.id})')

async def load_extensions():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith(('_', '.')):
            await bot.load_extension(f'cogs.{filename[:-3]}')

def get_bot_token(config: dict) -> str:
    """支援直接 TOKEN、切分 TOKEN_PARTS 陣列、或 TOKEN_PART1 + TOKEN_PART2 的組合讀取"""
    token = config.get('TOKEN')
    if token and isinstance(token, str) and token.strip() and token.strip() != "YOUR_BOT_TOKEN_HERE" and token.strip() != "DISCORD_TOKEN_HERE":
        return token.strip()

    # 1. 檢查 TOKEN_PARTS 陣列
    parts = config.get('TOKEN_PARTS')
    if isinstance(parts, list) and parts:
        combined = "".join([str(p).strip() for p in parts if p]).strip()
        if combined:
            return combined

    # 2. 檢查 TOKEN_PART1, TOKEN_PART2, TOKEN_PART3
    p1 = str(config.get('TOKEN_PART1', '') or '').strip()
    p2 = str(config.get('TOKEN_PART2', '') or '').strip()
    p3 = str(config.get('TOKEN_PART3', '') or '').strip()
    combined_parts = f"{p1}{p2}{p3}".strip()
    if combined_parts:
        return combined_parts

    return ""

async def main():
    token = get_bot_token(config)
    if not token:
        sys.exit("❌ 錯誤：找不到有效的 Discord Bot Token！請在 config.json 設定 'TOKEN' 或切分設定 'TOKEN_PART1' + 'TOKEN_PART2'。")

    async with bot:
        await load_extensions()
        await bot.start(token)

if __name__ == '__main__':
    asyncio.run(main())