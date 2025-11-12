import os
import time
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils.logger import setup_logger

# Setup logging
logger = setup_logger("DiscordBot")

# Load token
load_dotenv()
token = os.getenv('DISCORD_TOKEN')

# Setup bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True  # Needed for message events
intents.guilds = True  # Needed for guild events
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help')

# Track cooldowns and duplicate messages
cooldowns = {}
seen_messages = {}

# Load all cogs
async def load_cogs():
    for file in os.listdir('./cogs'):
        if file.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{file[:-3]}')
            except Exception as e:
                print(f"Failed to load {file[:-3]}: {e}")
    print("Successfully loaded all cogs.")

# Reload command
@bot.command()
async def reload(ctx, extension):
    if ctx.author.id != 873464016217968640:
        return await ctx.send("you dont have permission to use this command.")
    
    if extension.lower() in ['env', 'all']:
        msg = await ctx.send("<a:Loading:1437951860546732274> Reloading all cogs...")
        errors = []
        success = 0
        
        for file in os.listdir('./cogs'):
            if file.endswith('.py'):
                try:
                    await bot.reload_extension(f'cogs.{file[:-3]}')
                    success += 1
                except Exception:
                    errors.append(f"{file[:-3]}.cog not loaded")
        
        if errors:
            return await msg.edit(content=f"<a:X_:1437951830393884788> Reloaded {success} cogs\nErrors:\n" + "\n".join(errors))
        return await msg.edit(content=f"<a:Check:1437951818452832318> Reloaded all {success} cogs!")
    
    msg = await ctx.send(f"<a:Loading:1437951860546732274> Reloading {extension}...")
    try:
        await bot.reload_extension(f'cogs.{extension}')
        await msg.edit(content=f"<a:Check:1437951818452832318> Reloaded {extension}!")
    except Exception:
        await msg.edit(content=f"<a:X_:1437951830393884788> {extension}.cog not loaded")

@bot.event
async def on_ready():
    # Validate database and auto-repair if needed
    try:
        from utils.db_validator import validate_database, repair_database
        success, issues = await validate_database()
        if not success:
            logger.warning("Database validation failed. Attempting auto-repair...")
            await repair_database()
    except Exception as e:
        logger.error(f"Database validation error: {e}")
    
    # Sync slash commands silently
    try:
        await bot.tree.sync()
    except Exception:
        pass
    
    print(f"Bot ready as {bot.user.name}")

@bot.event
async def on_command(ctx):
    pass  # Silent command logging

@bot.event
async def on_message(message):
    # Ignore bots
    if message.author.bot:
        return
    
    # Check if we already saw this message
    now = time.time()
    if message.id in seen_messages:
        return
    seen_messages[message.id] = now
    
    # Clean old seen messages
    old = [mid for mid, ts in seen_messages.items() if now - ts > 3]
    for mid in old:
        del seen_messages[mid]
    
    # Get command context
    ctx = await bot.get_context(message)
    if not ctx.command:
        return
    
    # Owner bypasses cooldown
    if ctx.author.id == 873464016217968640:
        return await bot.invoke(ctx)
    
    # Check 2 second cooldown
    if ctx.author.id in cooldowns:
        time_left = 2.0 - (now - cooldowns[ctx.author.id])
        if time_left > 0:
            return await ctx.send(f"Wait {time_left:.1f}s")
    
    # Update cooldown
    cooldowns[ctx.author.id] = now
    
    # Clean old cooldowns
    old = [uid for uid, ts in cooldowns.items() if now - ts > 5]
    for uid in old:
        del cooldowns[uid]
    
    await bot.invoke(ctx)

async def main():
    async with bot:
        await load_cogs()
        await bot.start(token)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped.")
    except Exception as e:
        print(f"Bot crashed: {e}")