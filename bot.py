import discord
from discord.ext import commands
import json
import os
import asyncio

# 讀取設定檔
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix='*', 
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