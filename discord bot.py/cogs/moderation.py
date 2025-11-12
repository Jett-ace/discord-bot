import discord
import datetime
import asyncio
from discord.ext import commands
from utils.constants import filtered_words
from utils.database import add_chest, add_chest_with_type, get_user_data, update_user_data
from utils.database import reset_wishes
from config import OWNER_ID
from utils.logger import setup_logger

logger = setup_logger("Moderation")

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Cache recent messages for deletion tracking
        self.message_cache = {}  # {message_id: message_data}
        # Message logging settings per guild: {guild_id: {'bots': bool, 'members': bool, 'moderators': bool}}
        self.log_settings = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Cache message for deletion tracking
        self.message_cache[message.id] = {
            'author': message.author,
            'content': message.content,
            'channel': message.channel,
            'created_at': message.created_at,
            'guild': message.guild
        }
        
        # Clean old cache (keep last 1000 messages)
        if len(self.message_cache) > 1000:
            oldest_keys = list(self.message_cache.keys())[:100]
            for key in oldest_keys:
                del self.message_cache[key]

        if any(word in message.content.lower() for word in filtered_words):
            await message.delete()
            await message.channel.send(f"{message.author.mention}, your message contained banned words and was deleted.")

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Track deleted messages and log them."""
        logger.debug(f"Message delete event fired: {message.id}")
        
        # Get guild logging settings (default: log ALL users, but not bots)
        guild_id = message.guild.id if message.guild else None
        if guild_id not in self.log_settings:
            self.log_settings[guild_id] = {
                'bots': False,
                'members': True,
                'moderators': True  # Changed default to True
            }
        
        settings = self.log_settings[guild_id]
        
        # Check if we should log this message based on author type
        if message.author.bot:
            if not settings['bots']:
                logger.debug(f"Ignoring bot message deletion (bots logging disabled)")
                return
            logger.info(f"Logging bot message deletion (bots logging enabled)")
        else:
            # Check if author is a moderator (has manage_messages permission)
            is_moderator = False
            if message.guild and isinstance(message.author, discord.Member):
                is_moderator = message.author.guild_permissions.manage_messages
            
            logger.debug(f"Message author: {message.author.name}, is_moderator: {is_moderator}, settings: {settings}")
            
            if is_moderator and not settings['moderators']:
                logger.info(f"Skipping moderator message deletion from {message.author.name} (moderator logging disabled - use !logfilter to enable)")
                return
            elif not is_moderator and not settings['members']:
                logger.debug(f"Ignoring member message deletion (member logging disabled)")
                return
            
            logger.info(f"Logging deletion of message by {message.author.name} (is_mod: {is_moderator})")
        
        # Get message data from cache or use the message object
        if message.id in self.message_cache:
            msg_data = self.message_cache[message.id]
            logger.debug(f"Found message in cache")
            # Clean up cache
            del self.message_cache[message.id]
        else:
            logger.debug(f"Message not in cache, using message object")
            msg_data = {
                'author': message.author,
                'content': message.content,
                'channel': message.channel,
                'created_at': message.created_at,
                'guild': message.guild
            }
        
        # Find the log channel (look for a channel named 'logs' or 'mod-logs')
        log_channel = None
        if msg_data['guild']:
            logger.debug(f"Searching for log channel in guild: {msg_data['guild'].name}")
            for channel in msg_data['guild'].text_channels:
                logger.debug(f"Checking channel: {channel.name}")
                if channel.name in ['logs', 'mod-logs', 'message-logs', 'deleted-messages']:
                    log_channel = channel
                    logger.info(f"Found log channel: {channel.name}")
                    break
        
        if not log_channel:
            # No log channel found, skip logging
            logger.warning(f"No log channel found in guild: {msg_data['guild'].name if msg_data['guild'] else 'Unknown'}")
            return
        
        # Get audit log to see who deleted it (with a small delay to ensure audit log is updated)
        await asyncio.sleep(0.5)  # Wait half a second for audit log to populate
        deleter = None
        try:
            async for entry in msg_data['guild'].audit_logs(limit=15, action=discord.AuditLogAction.message_delete):
                logger.debug(f"Audit log entry: target={entry.target.id}, channel={entry.extra.channel.id}, user={entry.user.name}")
                if entry.target.id == msg_data['author'].id:
                    if entry.extra.channel.id == msg_data['channel'].id:
                        # Check if this deletion happened very recently (within 10 seconds to be safer)
                        time_diff = (discord.utils.utcnow() - entry.created_at).total_seconds()
                        logger.debug(f"Time difference: {time_diff} seconds")
                        if time_diff < 10:
                            deleter = entry.user
                            logger.info(f"Found deleter from audit log: {deleter.name} (time_diff: {time_diff}s)")
                            break
        except discord.Forbidden:
            # Bot doesn't have audit log permissions
            logger.warning("Bot lacks View Audit Log permission")
            pass
        except Exception as e:
            logger.error(f"Error checking audit logs: {e}", exc_info=True)
        
        # Build the log embed
        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=0xe74c3c,
            timestamp=discord.utils.utcnow()
        )
        
        # Author info
        embed.add_field(
            name="Author",
            value=f"{msg_data['author'].mention} ({msg_data['author'].name})",
            inline=True
        )
        
        # Channel info
        embed.add_field(
            name="Channel",
            value=msg_data['channel'].mention,
            inline=True
        )
        
        # Deleted by
        if deleter:
            embed.add_field(
                name="Deleted By",
                value=f"{deleter.mention} ({deleter.name})",
                inline=True
            )
        else:
            # If no deleter found in audit log, assume author deleted their own message
            embed.add_field(
                name="Deleted By",
                value=f"{msg_data['author'].mention} ({msg_data['author'].name})",
                inline=True
            )
        
        # Message content
        content = msg_data['content'] or "*No text content*"
        if len(content) > 1024:
            content = content[:1021] + "..."
        embed.add_field(
            name="Message Content",
            value=content,
            inline=False
        )
        
        # Message sent time
        sent_time = msg_data['created_at'].strftime("%B %d, %Y at %I:%M %p UTC")
        embed.add_field(
            name="Sent At",
            value=sent_time,
            inline=False
        )
        
        # Set author thumbnail
        embed.set_thumbnail(url=msg_data['author'].display_avatar.url)
        
        # Set footer
        embed.set_footer(text=f"User ID: {msg_data['author'].id} | Message ID: {message.id}")
        
        try:
            await log_channel.send(embed=embed)
            logger.info(f"Logged deleted message from {msg_data['author']} in #{msg_data['channel'].name}")
        except Exception as e:
            logger.error(f"Failed to send deletion log: {e}")

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        """Track edited messages and log them."""
        if before.author.bot:
            return
        
        # Ignore if content didn't change (embeds, pins, etc.)
        if before.content == after.content:
            return
        
        # Find the log channel
        log_channel = None
        if before.guild:
            for channel in before.guild.text_channels:
                if channel.name in ['logs', 'mod-logs', 'message-logs', 'deleted-messages']:
                    log_channel = channel
                    break
        
        if not log_channel:
            return
        
        # Build the log embed
        embed = discord.Embed(
            title="✏️ Message Edited",
            color=0xf39c12,
            timestamp=discord.utils.utcnow()
        )
        
        # Author info
        embed.add_field(
            name="Author",
            value=f"{before.author.mention} ({before.author.name})",
            inline=True
        )
        
        # Channel info
        embed.add_field(
            name="Channel",
            value=before.channel.mention,
            inline=True
        )
        
        # Jump to message
        embed.add_field(
            name="Message Link",
            value=f"[Jump to Message]({after.jump_url})",
            inline=True
        )
        
        # Before content
        before_content = before.content or "*No text content*"
        if len(before_content) > 1024:
            before_content = before_content[:1021] + "..."
        embed.add_field(
            name="Before",
            value=before_content,
            inline=False
        )
        
        # After content
        after_content = after.content or "*No text content*"
        if len(after_content) > 1024:
            after_content = after_content[:1021] + "..."
        embed.add_field(
            name="After",
            value=after_content,
            inline=False
        )
        
        # Set author thumbnail
        embed.set_thumbnail(url=before.author.display_avatar.url)
        
        # Set footer
        embed.set_footer(text=f"User ID: {before.author.id} | Message ID: {before.id}")
        
        try:
            await log_channel.send(embed=embed)
            logger.debug(f"Logged edited message from {before.author} in #{before.channel.name}")
        except Exception as e:
            logger.error(f"Failed to send edit log: {e}")

    @commands.command()
    @commands.has_role("cybr")
    async def purge(self, ctx, member: discord.Member = None):
        from utils.database import purge_inventory_db, update_user_data, reset_wishes
        member = member or ctx.author
        await purge_inventory_db(member.id)
        await update_user_data(member.id, mora=0, dust=0, fates=0)
        await reset_wishes(member.id)
        await ctx.send(f"{member.display_name}'s inventory has been purged.")

        # (removed grantall - use the single-item 'grant' command below)

    @commands.command(name="msgp")
    @commands.has_permissions(manage_messages=True)
    async def msgp(self, ctx, count: int):
        """Purge the last <count> messages in this channel (including messages from anyone).
        Usage: !msgp 10
        Requires Manage Messages permission.
        """
        if count <= 0:
            await ctx.send("Please specify a positive number of messages to purge.", delete_after=5)
            return
        
        if count > 100:
            await ctx.send("⚠️ Maximum 100 messages can be purged at once.", delete_after=5)
            return

        try:
            # Delete the command message first
            await ctx.message.delete()
            
            # Bulk delete messages (much faster than one-by-one)
            deleted = await ctx.channel.purge(limit=count)
            
            # Send confirmation (will auto-delete)
            confirm = await ctx.send(f"✅ Deleted {len(deleted)} message(s).")
            await asyncio.sleep(3)
            await confirm.delete()
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages in this channel.", delete_after=5)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to purge messages: {e}", delete_after=5)
        except Exception as e:
            logger.error(f"Error in msgp: {e}", exc_info=True)
            await ctx.send("❌ Failed to purge messages.", delete_after=5)

    @commands.command(name="grant", aliases=["give"])
    async def grant(self, ctx, item: str, amount: int, member: discord.Member = None):
        """Grant items to a user. Usage: !grant <item> <amount> [@member]
        Items: common, exquisite, precious, luxurious, mora, tidecoins, fate, hydro_essence, hydro_crystal
        Only the OWNER_ID can use this command.
        """
        from utils.database import add_chest, get_user_data, update_user_data, add_user_item, get_user_item_count
        from config import OWNER_ID

        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't have permission to use this command.")
            return

        if amount <= 0:
            await ctx.send("Amount must be greater than zero.")
            return

        member = member or ctx.author
        item_lower = item.lower()

        # Chest icons
        chest_icons = {
            'common': '<:cajitadelexplorador:1437473147833286676>',
            'exquisite': '<:cajitaplatino:1437473086571286699>',
            'precious': '<:cajitapremium:1437473125095837779>',
            'luxurious': '<:cajitadiamante:1437473169475764406>'
        }

        # Ensure DB row exists
        await purge_inventory_db(member.id) if False else None
        data = await get_user_data(member.id)

        # Check for specific chest types
        if item_lower in ("common", "exquisite", "precious", "luxurious"):
            try:
                await add_chest_with_type(member.id, item_lower, amount)
                icon = chest_icons.get(item_lower, '')
                chest_word = 'chests' if amount != 1 else 'chest'
                await ctx.send(f"Gave {icon} {amount} {item_lower} {chest_word} to {member.display_name}.")
            except Exception as e:
                print(f"Failed to grant {item_lower} chest(s): {e}")
                await ctx.send(f"Failed to grant {item_lower} chests.")
            return

        if item_lower in ("chest", "chests"):
            # grant typed common chests via admin command (backwards compatibility)
            try:
                await add_chest_with_type(member.id, 'common', amount)
                await ctx.send(f"Gave {chest_icons['common']} {amount} common chest(s) to {member.display_name}.")
            except Exception as e:
                print(f"Failed to grant chest(s): {e}")
                await ctx.send("Failed to grant chests.")
            return

        if item_lower in ("mora", "gold"):
            data['mora'] += amount
            await update_user_data(member.id, mora=data['mora'])
            await ctx.send(f"Gave {amount:,} 💰 to {member.display_name}.")
            return

        if item_lower in ("tide_coins", "tidecoins", "tide"):
            data['dust'] += amount
            await update_user_data(member.id, dust=data['dust'])
            await ctx.send(f"Gave {amount} <:mora:1437480155952975943> Tide Coins to {member.display_name}.")
            return

        if item_lower in ("fate", "fates"):
            data['fates'] += amount
            await update_user_data(member.id, fates=data['fates'])
            await ctx.send(f"Gave {amount} <:fate:1437488656767254528> Intertwined Fate(s) to {member.display_name}.")
            return

    @commands.command(name="givedust")
    async def give_dust(self, ctx, member: discord.Member, amount: int):
        if ctx.author.id != 873464016217968640:
            return
        try:
            data = await get_user_data(member.id)
            new_dust = data['dust'] + amount
            await update_user_data(member.id, dust=new_dust)
            await ctx.send(f"Gave {amount} <:mora:1437480155952975943> Tide Coins to {member.display_name}.")
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.command(name="resetpulls", aliases=["rp"])
    @commands.has_role("cybr")
    async def resetpulls(self, ctx, member: discord.Member = None):
        """Admin-only: reset pulls for a user. Usage: !resetpulls [@member]"""
        member = member or ctx.author
        await reset_wishes(member.id)
        await ctx.send(f"Reset pulls for {member.display_name}.")

    @commands.command(name="cleanbadges")
    async def clean_badges(self, ctx, member: discord.Member = None):
        """Owner-only: Clean up old format badges (stage_20 -> Stage 1). Usage: !cleanbadges [@member]"""
        from config import OWNER_ID, DB_PATH
        import aiosqlite
        
        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't have permission to use this command.")
            return
        
        member = member or ctx.author
        
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Get all badges for the user
                async with db.execute("SELECT badge_key FROM badges WHERE user_id=?", (member.id,)) as cur:
                    rows = await cur.fetchall()
                
                if not rows:
                    await ctx.send(f"{member.display_name} has no badges to clean.")
                    return
                
                # Delete old format stage badges
                await db.execute("DELETE FROM badges WHERE user_id=? AND badge_key LIKE 'stage_%'", (member.id,))
                deleted_count = db.total_changes
                await db.commit()
                
                if deleted_count > 0:
                    await ctx.send(f"Cleaned {deleted_count} old format badge(s) from {member.display_name}. They will re-earn proper badges at level milestones.")
                else:
                    await ctx.send(f"No old format badges found for {member.display_name}.")
        except Exception as e:
            print(f"Error cleaning badges: {e}")
            await ctx.send("Failed to clean badges.")

    @commands.command(name="setlevel")
    async def set_level(self, ctx, level: int, member: discord.Member = None):
        """Owner-only: Set a user's level. Usage: !setlevel <level> [@member]"""
        from config import OWNER_ID, DB_PATH
        import aiosqlite
        
        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't have permission to use this command.")
            return
        
        member = member or ctx.author
        
        if level < 0:
            await ctx.send("Level must be 0 or greater.")
            return
        
        try:
            from utils.database import ensure_user_db
            await ensure_user_db(member.id)
            
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE accounts SET level=?, exp=? WHERE user_id=?", (level, 0, member.id))
                await db.commit()
            
            await ctx.send(f"Set {member.display_name}'s level to {level}.")
        except Exception as e:
            print(f"Error setting level: {e}")
            await ctx.send("Failed to set level.")

    @commands.command(name="grantexp")
    async def grant_exp(self, ctx, amount: int, member: discord.Member = None):
        """Owner-only: Grant EXP to a user. Usage: !grantexp <amount> [@member]"""
        from config import OWNER_ID
        from utils.database import add_account_exp
        
        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't have permission to use this command.")
            return
        
        member = member or ctx.author
        
        if amount <= 0:
            await ctx.send("Amount must be greater than zero.")
            return
        
        try:
            result = await add_account_exp(member.id, amount, source='admin_grant')
            await ctx.send(f"Granted {amount:,} EXP to {member.display_name}. Level: {result['old_level']} → {result['new_level']}")
        except Exception as e:
            print(f"Error granting EXP: {e}")
            await ctx.send("Failed to grant EXP.")

    @commands.command(name="steal")
    async def steal(self, ctx):
        """Steal an emoji from a message by replying to it. Usage: Reply to a message with !steal"""
        import re
        import aiohttp
        
        # Check if this is a reply
        if not ctx.message.reference:
            await ctx.send("You need to reply to a message containing an emoji to steal it!")
            return
        
        # Get the referenced message
        try:
            referenced_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except:
            await ctx.send("Could not find the referenced message.")
            return
        
        # Extract custom emoji from the message (format: <:name:id> or <a:name:id> for animated)
        emoji_pattern = r'<(a?):(\w+):(\d+)>'
        matches = re.findall(emoji_pattern, referenced_msg.content)
        
        if not matches:
            await ctx.send("No custom emoji found in that message!")
            return
        
        # Use the first emoji found
        is_animated, emoji_name, emoji_id = matches[0]
        
        # Construct emoji URL
        extension = 'gif' if is_animated else 'png'
        emoji_url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{extension}'
        
        # Check if user has manage emojis permission
        if not ctx.author.guild_permissions.manage_emojis:
            await ctx.send("You need 'Manage Emojis' permission to use this command!")
            return
        
        try:
            # Download the emoji
            async with aiohttp.ClientSession() as session:
                async with session.get(emoji_url) as resp:
                    if resp.status != 200:
                        await ctx.send("Failed to download the emoji.")
                        return
                    emoji_bytes = await resp.read()
            
            # Add emoji to server
            emoji = await ctx.guild.create_custom_emoji(
                name=emoji_name,
                image=emoji_bytes,
                reason=f"Stolen by {ctx.author}"
            )
            
            await ctx.send(f"Successfully stole {emoji} (:{emoji.name}:)")
            
        except discord.Forbidden:
            await ctx.send("I don't have permission to add emojis to this server!")
        except discord.HTTPException as e:
            if 'Maximum number of emojis reached' in str(e):
                await ctx.send("This server has reached the maximum number of emojis!")
            else:
                await ctx.send(f"Failed to add emoji: {e}")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @commands.command(name="adminhelp", aliases=["ahelp"])
    async def admin_help(self, ctx):
        """Owner-only: Show admin commands."""
        from config import OWNER_ID
        
        if ctx.author.id != OWNER_ID:
            return  # Silently ignore for non-owners
        
        embed = discord.Embed(title="Admin Commands", color=0xe74c3c)
        embed.add_field(
            name="User Management",
            value=(
                "`!purge [@member]` - Purge inventory\n"
                "`!resetpulls [@member]` - Reset wish history\n"
                "`!setlevel <level> [@member]` - Set level\n"
                "`!grantexp <amount> [@member]` - Grant EXP"
            ),
            inline=False
        )
        embed.add_field(
            name="Item Granting",
            value=(
                "`!grant <item> <amount> [@member]` - Grant items\n"
                "Chests: common, exquisite, precious, luxurious\n"
                "Other: mora, tidecoins, fate, hydro_essence, hydro_crystal"
            ),
            inline=False
        )
        embed.add_field(
            name="Database Cleanup",
            value=(
                "`!cleanbadges [@member]` - Clean old format badges"
            ),
            inline=False
        )
        embed.add_field(
            name="Moderation",
            value=(
                "`!msgp <count>` - Purge your messages\n"
                "`!steal` - Reply to message to steal emoji (requires Manage Emojis)\n"
                "`!resetrps <@user>` - Reset RPS cooldown for user"
            ),
            inline=False
        )
        embed.set_footer(text="Owner-only commands")
        await ctx.send(embed=embed)
    
    @commands.command()
    async def resetrps(self, ctx, member: discord.Member):
        """Reset RPS cooldown for a user"""
        if ctx.author.id != OWNER_ID:
            await ctx.send("No permission!")
            return
        
        # Get games cog and reset
        games_cog = self.bot.get_cog("Games")
        if games_cog and hasattr(games_cog, 'rps_plays'):
            if member.id in games_cog.rps_plays:
                del games_cog.rps_plays[member.id]
            await ctx.send(f"Reset RPS cooldown for {member.display_name}!")
        else:
            await ctx.send("Games cog not found!")

    @commands.command(name="admincd", aliases=["acd"])
    async def admin_cd(self, ctx):
        """Owner-only: Show all cooldown reset commands."""
        from config import OWNER_ID
        
        if ctx.author.id != OWNER_ID:
            return  # Silently ignore for non-owners
        
        embed = discord.Embed(title="Cooldown Reset Commands", color=0x3498db)
        embed.description = "Commands to reset user cooldowns:"
        
        embed.add_field(
            name="Available Resets",
            value=(
                "`!resetdaily` - Reset your daily claim cooldown\n"
                "`!fish ccd` - Reset your fishing cooldown\n"
                "`!resetrps <@user>` - Reset RPS cooldown for a user"
            ),
            inline=False
        )
        
        embed.set_footer(text="Owner-only commands")
        await ctx.send(embed=embed)

    @commands.command(name="cd", aliases=["cooldown", "cooldowns"])
    async def cooldowns(self, ctx):
        """Check your current cooldowns."""
        from datetime import datetime, timedelta
        from config import DB_PATH
        import aiosqlite
        
        embed = discord.Embed(title=f"{ctx.author.display_name}'s Cooldowns", color=0x3498db)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        
        cooldown_info = []
        
        # Check daily cooldown
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT last_claim FROM daily_claims WHERE user_id=?", (ctx.author.id,)) as cur:
                    row = await cur.fetchone()
                
                if row and row[0]:
                    last_claim = datetime.fromisoformat(row[0])
                    next_claim = last_claim + timedelta(hours=24)
                    now = datetime.utcnow()
                    
                    if now >= next_claim:
                        cooldown_info.append("<a:arrow:1437968863026479258> **Next Daily:** Ready")
                    else:
                        time_left = next_claim - now
                        hours = int(time_left.total_seconds() // 3600)
                        minutes = int((time_left.total_seconds() % 3600) // 60)
                        cooldown_info.append(f"<a:arrow:1437968863026479258> **Next Daily:** {hours}h {minutes}m")
                else:
                    cooldown_info.append("<a:arrow:1437968863026479258> **Next Daily:** Ready")
        except Exception:
            cooldown_info.append("<a:arrow:1437968863026479258> **Next Daily:** Ready")
        
        # Check fishing cooldown
        try:
            fishing_cog = self.bot.get_cog("Fishing")
            if fishing_cog and hasattr(fishing_cog, '_fish_cooldowns'):
                if ctx.author.id in fishing_cog._fish_cooldowns:
                    last_fish_data = fishing_cog._fish_cooldowns[ctx.author.id]
                    last_fish_time = last_fish_data['last_fish']
                    last_cooldown = last_fish_data['cooldown_seconds']
                    
                    time_since = (datetime.utcnow() - last_fish_time).total_seconds()
                    
                    if time_since >= last_cooldown:
                        cooldown_info.append("<a:arrow:1437968863026479258> **Next Fishing:** Ready")
                    else:
                        time_left = last_cooldown - time_since
                        minutes = int(time_left // 60)
                        seconds = int(time_left % 60)
                        cooldown_info.append(f"<a:arrow:1437968863026479258> **Next Fishing:** {minutes}m {seconds}s")
                else:
                    cooldown_info.append("<a:arrow:1437968863026479258> **Next Fishing:** Ready")
            else:
                cooldown_info.append("<a:arrow:1437968863026479258> **Next Fishing:** Ready")
        except Exception:
            cooldown_info.append("<a:arrow:1437968863026479258> **Next Fishing:** Ready")
        
        # Check RPS cooldown
        try:
            games_cog = self.bot.get_cog("Games")
            if games_cog and hasattr(games_cog, 'rps_plays'):
                if ctx.author.id in games_cog.rps_plays:
                    last_play = games_cog.rps_plays[ctx.author.id]
                    now = datetime.utcnow()
                    cooldown_duration = timedelta(hours=1)
                    next_play = last_play + cooldown_duration
                    
                    if now >= next_play:
                        cooldown_info.append("<a:arrow:1437968863026479258> **Next RPS:** Ready")
                    else:
                        time_left = next_play - now
                        minutes = int(time_left.total_seconds() // 60)
                        seconds = int(time_left.total_seconds() % 60)
                        cooldown_info.append(f"<a:arrow:1437968863026479258> **Next RPS:** {minutes}m {seconds}s")
                else:
                    cooldown_info.append("<a:arrow:1437968863026479258> **Next RPS:** Ready")
            else:
                cooldown_info.append("<a:arrow:1437968863026479258> **Next RPS:** Ready")
        except Exception:
            cooldown_info.append("<a:arrow:1437968863026479258> **Next RPS:** Ready")
        
        embed.description = "\n".join(cooldown_info)
        embed.set_footer(text="Use commands when ready!")
        
        await ctx.send(embed=embed)

    @commands.command(name="setlogchannel")
    @commands.has_permissions(administrator=True)
    async def set_log_channel(self, ctx, channel: discord.TextChannel = None):
        """Set the channel for message deletion logs.
        Usage: !setlogchannel #channel-name
        
        The bot will automatically look for channels named:
        - logs
        - mod-logs
        - message-logs
        - deleted-messages
        
        Or you can specify a custom channel with this command.
        """
        if channel is None:
            channel = ctx.channel
        
        # Test if bot can send messages
        try:
            test_embed = discord.Embed(
                title="✅ Log Channel Set",
                description=f"This channel ({channel.mention}) will now receive message deletion logs.",
                color=0x2ecc71
            )
            test_embed.set_footer(text="Message deletion tracking is active!")
            await channel.send(embed=test_embed)
            
            if channel.id != ctx.channel.id:
                await ctx.send(f"✅ Log channel set to {channel.mention}")
        except discord.Forbidden:
            await ctx.send(f"❌ I don't have permission to send messages in {channel.mention}")
        except Exception as e:
            logger.error(f"Error setting log channel: {e}")
            await ctx.send("❌ Failed to set log channel.")

    @commands.command(name="logstatus")
    @commands.has_permissions(manage_messages=True)
    async def log_status(self, ctx):
        """Check message logging status."""
        # Find log channel
        log_channel = None
        channel_list = []
        if ctx.guild:
            for channel in ctx.guild.text_channels:
                channel_list.append(channel.name)
                if channel.name in ['logs', 'mod-logs', 'message-logs', 'deleted-messages']:
                    log_channel = channel
                    break
        
        embed = discord.Embed(
            title="📊 Message Logging Status",
            color=0x3498db
        )
        
        if log_channel:
            embed.add_field(
                name="Status",
                value="✅ Active",
                inline=True
            )
            embed.add_field(
                name="Log Channel",
                value=log_channel.mention,
                inline=True
            )
            embed.add_field(
                name="Cached Messages",
                value=f"{len(self.message_cache):,}",
                inline=True
            )
            embed.add_field(
                name="Features",
                value="• Message Deletions\n• Message Edits\n• Author & Deleter Info",
                inline=False
            )
            
            # Add permissions check
            perms = log_channel.permissions_for(ctx.guild.me)
            perms_status = []
            perms_status.append(f"{'✅' if perms.send_messages else '❌'} Send Messages")
            perms_status.append(f"{'✅' if perms.embed_links else '❌'} Embed Links")
            perms_status.append(f"{'✅' if perms.view_audit_log else '⚠️'} View Audit Log")
            embed.add_field(
                name="Bot Permissions",
                value="\n".join(perms_status),
                inline=False
            )
        else:
            embed.add_field(
                name="Status",
                value="⚠️ No log channel found",
                inline=False
            )
            embed.add_field(
                name="Available Channels",
                value=f"Found {len(channel_list)} channels:\n" + ", ".join(f"`{c}`" for c in channel_list[:10]),
                inline=False
            )
            embed.add_field(
                name="Setup",
                value="Create a channel named:\n• `logs`\n• `mod-logs`\n• `message-logs`\n• `deleted-messages`\n\nOr use `!setlogchannel #channel`",
                inline=False
            )
        
        embed.set_footer(text="Message logging requires audit log permissions for 'Deleted By' info")
        await ctx.send(embed=embed)

    @commands.command(name="testlog")
    @commands.has_permissions(manage_messages=True)
    async def test_log(self, ctx):
        """Send a test message and delete it to test logging."""
        test_msg = await ctx.send("🧪 This is a test message. It will be deleted in 3 seconds to test logging...")
        await asyncio.sleep(3)
        await test_msg.delete()
        await ctx.send("✅ Test message deleted. Check your log channel!", delete_after=5)

    @commands.command(name="logfilter", aliases=["logconfig"])
    @commands.has_permissions(administrator=True)
    async def log_filter(self, ctx):
        """Configure which types of users' deleted messages get logged (Admin only)."""
        guild_id = ctx.guild.id
        
        # Initialize settings if not exists
        if guild_id not in self.log_settings:
            self.log_settings[guild_id] = {
                'bots': False,
                'members': True,
                'moderators': False
            }
        
        view = LogFilterView(self, guild_id)
        embed = view.create_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command(name="health")
    async def health_check(self, ctx):
        """Display bot health status (owner only)."""
        if ctx.author.id != OWNER_ID:
            return
        
        try:
            from utils.db_validator import validate_database
            import time
            import psutil
            import os
            
            start_time = time.time()
            
            # Check database
            db_success, db_issues = await validate_database()
            db_status = "✅ Healthy" if db_success else f"⚠️ {len(db_issues)} issues"
            
            # Check bot stats
            guilds = len(self.bot.guilds)
            total_members = sum(g.member_count for g in self.bot.guilds)
            
            # Get cogs
            cogs_loaded = len(self.bot.cogs)
            
            # Memory usage
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            # Response time
            response_time = (time.time() - start_time) * 1000
            
            embed = discord.Embed(title="🏥 Bot Health Status", color=0x2ecc71 if db_success else 0xf39c12)
            embed.add_field(name="Database", value=db_status, inline=True)
            embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
            embed.add_field(name="Response Time", value=f"{round(response_time)}ms", inline=True)
            embed.add_field(name="Guilds", value=str(guilds), inline=True)
            embed.add_field(name="Users", value=f"{total_members:,}", inline=True)
            embed.add_field(name="Cogs Loaded", value=str(cogs_loaded), inline=True)
            embed.add_field(name="Memory Usage", value=f"{memory_mb:.1f} MB", inline=True)
            
            if not db_success:
                embed.add_field(
                    name="Database Issues",
                    value="\n".join(f"• {issue}" for issue in db_issues[:5]),
                    inline=False
                )
            
            embed.set_footer(text="All systems operational" if db_success else "Some issues detected")
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in health check: {e}", exc_info=True)
            await ctx.send(f"❌ Health check failed: {e}")


class LogFilterView(discord.ui.View):
    """Interactive view for configuring message logging filters."""
    
    def __init__(self, cog, guild_id):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.update_buttons()
    
    def update_buttons(self):
        """Update button styles based on current settings."""
        settings = self.cog.log_settings[self.guild_id]
        
        # Clear existing items
        self.clear_items()
        
        # Add buttons with appropriate styles
        self.add_item(ToggleButton(self, 'bots', '🤖 Bots', settings['bots']))
        self.add_item(ToggleButton(self, 'members', '👥 Members', settings['members']))
        self.add_item(ToggleButton(self, 'moderators', '🛡️ Moderators', settings['moderators']))
    
    def create_embed(self):
        """Create the status embed."""
        settings = self.cog.log_settings[self.guild_id]
        
        embed = discord.Embed(
            title="🔧 Message Logging Filters",
            description="Choose which types of users' deleted messages should be logged:",
            color=0x5865F2
        )
        
        def status_icon(enabled):
            return "✅ Enabled" if enabled else "❌ Disabled"
        
        embed.add_field(
            name="🤖 Bot Messages",
            value=status_icon(settings['bots']),
            inline=True
        )
        embed.add_field(
            name="👥 Member Messages",
            value=status_icon(settings['members']),
            inline=True
        )
        embed.add_field(
            name="🛡️ Moderator Messages",
            value=status_icon(settings['moderators']),
            inline=True
        )
        
        embed.set_footer(text="Click buttons below to toggle • Changes apply immediately")
        
        return embed


class ToggleButton(discord.ui.Button):
    """Button for toggling log filter settings."""
    
    def __init__(self, view: LogFilterView, setting_key: str, label: str, enabled: bool):
        self.setting_key = setting_key
        style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary
        super().__init__(style=style, label=label)
        self.parent_view = view
    
    async def callback(self, interaction: discord.Interaction):
        # Toggle the setting
        settings = self.parent_view.cog.log_settings[self.parent_view.guild_id]
        settings[self.setting_key] = not settings[self.setting_key]
        
        # Update the view
        self.parent_view.update_buttons()
        embed = self.parent_view.create_embed()
        
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
        logger.info(f"Log filter updated in guild {self.parent_view.guild_id}: {self.setting_key} = {settings[self.setting_key]}")


async def setup(bot):
    await bot.add_cog(Moderation(bot))
