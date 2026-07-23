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

bot = commands.Bot(
    command_prefix=(), 
    intents=intents, 
    owner_ids=config.get('OWNER_ID'), 
    help_command=None
)

@bot.event
async def on_ready():
    # 同步斜線指令到 Discord 伺服器
    await bot.tree.sync()
    print(f'登入成功！, 總計 {len(bot.users)} 個用戶，位於 {len(bot.guilds)} 個伺服器中。')
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

async def main():
    async with bot:
        await load_extensions()
        await bot.start(config['TOKEN'])

if __name__ == '__main__':
    asyncio.run(main())