import os
import time
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils.logger import setup_logger
import config

# Setup logging
logger = setup_logger("DiscordBot")

# Load token
load_dotenv()
token = os.getenv('DISCORD_TOKEN')

# Global cooldown tracker
user_cooldowns = {}
GLOBAL_COOLDOWN = 6.0  # 6 seconds between ANY commands

# Dynamic prefix function
def get_prefix(bot, message):
    # Return both "g" and "g " as valid prefixes (case-insensitive)
    # IMPORTANT: Longer prefixes must come first!
    return ["g ", "G ", "g", "G"]

# Setup bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True  # Needed for message events
intents.guilds = True  # Needed for guild events
bot = commands.Bot(command_prefix=get_prefix, intents=intents, case_insensitive=True)
bot.remove_command('help')

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
        msg = await ctx.send("<a:Loading:1437951860546732274> Reloading...")
        errors = []
        success = 0
        
        for file in os.listdir('./cogs'):
            if file.endswith('.py'):
                try:
                    await bot.reload_extension(f'cogs.{file[:-3]}')
                    success += 1
                except Exception as e:
                    errors.append(f"{file[:-3]}: {str(e)[:100]}")
        
        if errors:
            return await msg.edit(content="<a:X_:1437951830393884788> Errors:\n" + "\n".join(errors))
        return await msg.edit(content="<a:Check:1437951818452832318> Successfully reloaded.")
    
    msg = await ctx.send("<a:Loading:1437951860546732274> Reloading...")
    try:
        await bot.reload_extension(f'cogs.{extension}')
        await msg.edit(content="<a:Check:1437951818452832318> Successfully reloaded.")
    except Exception as e:
        await msg.edit(content=f"<a:X_:1437951830393884788> Error: {str(e)[:200]}")

@bot.event
async def on_command(ctx):
    """Apply global cooldown across ALL commands"""
    if ctx.author.id == 873464016217968640:  # Bot owner bypass
        return
    
    user_id = ctx.author.id
    current_time = time.time()
    
    # Check if user is on global cooldown
    if user_id in user_cooldowns:
        time_left = user_cooldowns[user_id] - current_time
        if time_left > 0:
            await ctx.send(f"⏳ Slow down! Wait {time_left:.1f}s before using another command.")
            raise commands.CommandOnCooldown(commands.BucketType.user, time_left, type=commands.BucketType.user)
    
    # Set cooldown for this user
    user_cooldowns[user_id] = current_time + GLOBAL_COOLDOWN

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
async def on_command_error(ctx, error):
    """Handle command errors and show proper usage"""
    # Missing required argument
    if isinstance(error, commands.MissingRequiredArgument):
        cmd = ctx.command
        
        # Generate appropriate example based on command
        example = ""
        if cmd.name in ['ban', 'kick']:
            example = f"\nExample: `g{cmd.name} @user Breaking rules`"
        elif cmd.name in ['mute', 'timeout']:
            example = f"\nExample: `g{cmd.name} @user 10m Spamming`"
        elif cmd.name == 'warn':
            example = f"\nExample: `g{cmd.name} @user Please follow the rules`"
        elif cmd.name in ['nick', 'nickname', 'rename']:
            example = f"\nExample: `g{cmd.name} @user NewName`"
        elif cmd.name in ['cc', 'createchannel']:
            example = f"\nExample: `g{cmd.name} announcements public`"
        elif cmd.name in ['ap', 'addperm']:
            example = f"\nExample: `g{cmd.name} @Admin ban`"
        elif cmd.name in ['rp', 'removeperm']:
            example = f"\nExample: `g{cmd.name} @Admin ban`"
        elif cmd.name == 'disable':
            example = f"\nExample: `g{cmd.name} slots #general`"
        elif cmd.name == 'enable':
            example = f"\nExample: `g{cmd.name} slots #general`"
        # Gambling commands with specific examples
        elif cmd.name in ['flip', 'coinflip', 'coin', 'cf']:
            example = f"\nExample: `gflip heads 1000` or `gflip tails all`"
        elif cmd.name in ['roulette', 'rlt']:
            example = f"\nExample: `groulette red 5000` or `groulette straight 17 1000`"
        elif cmd.name in ['rps']:
            example = f"\nExample: `grps rock` or `grps paper` or `grps scissors`"
        elif cmd.name in ['blackjack', 'bj']:
            example = f"\nExample: `gblackjack 5000` or `gbj all`"
        elif cmd.name in ['slots', 'slot', 'slotmachine']:
            example = f"\nExample: `gslots 5000` or `gslots all`"
        elif cmd.name in ['wheel', 'spin']:
            example = f"\nExample: `gwheel 5000` or `gwheel all`"
        elif cmd.name in ['mines']:
            example = f"\nExample: `gmines 5000` or `gmines all`"
        elif cmd.name in ['tower', 'climb']:
            example = f"\nExample: `gtower 5000` or `gtower all`"
        elif cmd.name in ['hilo']:
            example = f"\nExample: `ghilo 5000` or `ghilo all`"
        elif cmd.name in ['memory', 'memorymatch']:
            example = f"\nExample: `gmemory 1000` or `gmemory @user 1000`"
        elif cmd.name in ['scramble']:
            example = f"\nExample: `gscramble 1000 easy` or `gscramble 5000 hard`"
        elif cmd.name in ['trivia']:
            example = f"\nExample: `gtrivia @user 5 1000`"
        elif cmd.name in ['tictactoe', 'ttt']:
            example = f"\nExample: `gtictactoe` or `gtictactoe @user`"
        elif cmd.name in ['connect4', 'c4']:
            example = f"\nExample: `gconnect4 @user`"
        # Generic for other commands with amount/bet
        elif 'amount' in str(cmd.signature).lower() or 'bet' in str(cmd.signature).lower():
            example = f"\nExample: `g{cmd.name} 1000`"
        
        await ctx.send(f"Usage: `g{cmd.name} {cmd.signature}`{example}")
        return
    
    # Bad argument (wrong type or format)
    elif isinstance(error, commands.BadArgument):
        cmd = ctx.command
        await ctx.send(f"Invalid argument. Usage: `g{cmd.name} {cmd.signature}`")
        return
    
    # Command not found - ignore silently
    elif isinstance(error, commands.CommandNotFound):
        return
    
    # Missing permissions
    elif isinstance(error, commands.MissingPermissions):
        return await ctx.send("❌ You don't have permission to use this command.")
    
    # Command on cooldown
    elif isinstance(error, commands.CommandOnCooldown):
        return await ctx.send(f"⏳ This command is on cooldown. Try again in {error.retry_after:.1f}s")
    
    # Log other errors
    else:
        logger.error(f"Command error in {ctx.command}: {error}", exc_info=error)

@bot.event
async def on_message(message):
    # Ignore bots
    if message.author.bot:
        return
    
    # Process commands first to get context
    ctx = await bot.get_context(message)
    
    # Check maintenance mode BEFORE processing commands
    from config import MAINTENANCE_MODE, OWNER_ID
    if MAINTENANCE_MODE and message.author.id != OWNER_ID:
        # Only respond if it's a valid command attempt
        if ctx.valid and ctx.command:
            await message.channel.send("🔧 Bot currently under maintenance. Please try again later.")
        return
    
    # If there's a valid command
    if ctx.command:
        command_name = ctx.command.name
        
        # Check if command is disabled in this channel (skip for owner)
        if message.author.id != OWNER_ID and message.guild:
            from utils.permissions import is_command_disabled
            if await is_command_disabled(message.channel.id, message.guild.id, command_name):
                return  # Silently ignore disabled commands
        
        # Exempt commands that don't need registration
        exempt_commands = ['start', 'help', 'reload', 'adminhelp', 'ahelp', 'setprefix']
        
        # Check if user is registered (unless using exempt commands or is owner)
        if command_name not in exempt_commands and message.author.id != OWNER_ID:
            from utils.database import is_enrolled
            if not await is_enrolled(message.author.id):
                await message.channel.send(f"❌ Please do `{config.PREFIX}start` to start playing!")
                return
        
        # Check global cooldown (skip for owner)
        if message.author.id != OWNER_ID:
            user_id = message.author.id
            current_time = time.time()
            
            if user_id in user_cooldowns:
                time_since_last = current_time - user_cooldowns[user_id]
                if time_since_last < GLOBAL_COOLDOWN:
                    remaining = GLOBAL_COOLDOWN - time_since_last
                    await message.channel.send(f"⏳ Slow down! Try again in {remaining:.1f}s")
                    return
            
            # Update cooldown time
            user_cooldowns[user_id] = current_time
    
    # Process commands
    await bot.process_commands(message)

async def main():
    async with bot:
        await load_cogs()
        try:
            await bot.start(token)
        except discord.errors.LoginFailure:
            logger.error("Invalid Discord token! Check your .env file.")
            print("❌ Invalid token. Check your DISCORD_TOKEN in .env file.")
        except Exception as e:
            logger.error(f"Connection error: {e}", exc_info=True)
            raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped.")
    except Exception as e:
        logger.error(f"Bot crashed: {e}", exc_info=True)
        print(f"Bot crashed: {e}")