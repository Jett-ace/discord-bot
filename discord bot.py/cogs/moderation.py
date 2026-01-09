import asyncio
from datetime import datetime
import io

import discord
from discord.ext import commands
import aiosqlite

from config import OWNER_ID, DB_PATH
from utils.constants import filtered_words
from utils.database import (
    add_chest_with_type,
    get_user_data,
    reset_wishes,
    update_user_data,
)
from utils.embed import send_embed
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
            "author": message.author,
            "content": message.content,
            "channel": message.channel,
            "created_at": message.created_at,
            "guild": message.guild,
        }

        # Clean old cache (keep last 1000 messages)
        if len(self.message_cache) > 1000:
            oldest_keys = list(self.message_cache.keys())[:100]
            for key in oldest_keys:
                del self.message_cache[key]

        # Word filtering disabled

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Track deleted messages and log them."""
        logger.debug(f"Message delete event fired: {message.id}")

        # Get guild logging settings (default: log ALL users, but not bots)
        guild_id = message.guild.id if message.guild else None
        if guild_id not in self.log_settings:
            self.log_settings[guild_id] = {
                "bots": False,
                "members": True,
                "moderators": True,  # Changed default to True
            }

        settings = self.log_settings[guild_id]

        # Check if we should log this message based on author type
        if message.author.bot:
            if not settings["bots"]:
                logger.debug("Ignoring bot message deletion (bots logging disabled)")
                return
            logger.info("Logging bot message deletion (bots logging enabled)")
        else:
            # Check if author is a moderator (has manage_messages permission)
            is_moderator = False
            if message.guild and isinstance(message.author, discord.Member):
                is_moderator = message.author.guild_permissions.manage_messages

            logger.debug(
                f"Message author: {message.author.name}, is_moderator: {is_moderator}, settings: {settings}"
            )

            if is_moderator and not settings["moderators"]:
                logger.info(
                    f"Skipping moderator message deletion from {message.author.name} (moderator logging disabled - use glogfilter to enable)"
                )
                return
            elif not is_moderator and not settings["members"]:
                logger.debug(
                    "Ignoring member message deletion (member logging disabled)"
                )
                return

            logger.info(
                f"Logging deletion of message by {message.author.name} (is_mod: {is_moderator})"
            )

        # Get message data from cache or use the message object
        if message.id in self.message_cache:
            msg_data = self.message_cache[message.id]
            logger.debug("Found message in cache")
            # Clean up cache
            del self.message_cache[message.id]
        else:
            logger.debug("Message not in cache, using message object")
            msg_data = {
                "author": message.author,
                "content": message.content,
                "channel": message.channel,
                "created_at": message.created_at,
                "guild": message.guild,
            }

        # Find the log channel (look for a channel named 'logs' or 'mod-logs')
        log_channel = None
        if msg_data["guild"]:
            logger.debug(
                f"Searching for log channel in guild: {msg_data['guild'].name}"
            )
            for channel in msg_data["guild"].text_channels:
                logger.debug(f"Checking channel: {channel.name}")
                if channel.name in [
                    "logs",
                    "mod-logs",
                    "message-logs",
                    "deleted-messages",
                ]:
                    log_channel = channel
                    logger.info(f"Found log channel: {channel.name}")
                    break

        if not log_channel:
            # No log channel found, skip logging
            logger.warning(
                f"No log channel found in guild: {msg_data['guild'].name if msg_data['guild'] else 'Unknown'}"
            )
            return

        # Get audit log to see who deleted it (with a small delay to ensure audit log is updated)
        await asyncio.sleep(0.5)  # Wait half a second for audit log to populate
        deleter = None
        try:
            async for entry in msg_data["guild"].audit_logs(
                limit=15, action=discord.AuditLogAction.message_delete
            ):
                logger.debug(
                    f"Audit log entry: target={entry.target.id}, channel={entry.extra.channel.id}, user={entry.user.name}"
                )
                if entry.target.id == msg_data["author"].id:
                    if entry.extra.channel.id == msg_data["channel"].id:
                        # Check if this deletion happened very recently (within 10 seconds to be safer)
                        time_diff = (
                            discord.utils.utcnow() - entry.created_at
                        ).total_seconds()
                        logger.debug(f"Time difference: {time_diff} seconds")
                        if time_diff < 10:
                            deleter = entry.user
                            logger.info(
                                f"Found deleter from audit log: {deleter.name} (time_diff: {time_diff}s)"
                            )
                            break
        except discord.Forbidden:
            # Bot doesn't have audit log permissions
            logger.warning("Bot lacks View Audit Log permission")
            pass
        except Exception as e:
            logger.error(f"Error checking audit logs: {e}", exc_info=True)

        # Build the log embed
        embed = discord.Embed(
            title="🗑️ Message Deleted", color=0xE74C3C, timestamp=discord.utils.utcnow()
        )

        # Author info
        embed.add_field(
            name="Author",
            value=f"{msg_data['author'].mention} ({msg_data['author'].name})",
            inline=True,
        )

        # Channel info
        embed.add_field(name="Channel", value=msg_data["channel"].mention, inline=True)

        # Deleted by
        if deleter:
            embed.add_field(
                name="Deleted By",
                value=f"{deleter.mention} ({deleter.name})",
                inline=True,
            )
        else:
            # If no deleter found in audit log, assume author deleted their own message
            embed.add_field(
                name="Deleted By",
                value=f"{msg_data['author'].mention} ({msg_data['author'].name})",
                inline=True,
            )

        # Message content
        content = msg_data["content"] or "*No text content*"
        if len(content) > 1024:
            content = content[:1021] + "..."
        embed.add_field(name="Message Content", value=content, inline=False)

        # Message sent time
        sent_time = msg_data["created_at"].strftime("%B %d, %Y at %I:%M %p UTC")
        embed.add_field(name="Sent At", value=sent_time, inline=False)

        # Set author thumbnail
        embed.set_thumbnail(url=msg_data["author"].display_avatar.url)

        # Set footer
        embed.set_footer(
            text=f"User ID: {msg_data['author'].id} | Message ID: {message.id}"
        )

        try:
            await log_channel.send(embed=embed)
            logger.info(
                f"Logged deleted message from {msg_data['author']} in #{msg_data['channel'].name}"
            )
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
                if channel.name in [
                    "logs",
                    "mod-logs",
                    "message-logs",
                    "deleted-messages",
                ]:
                    log_channel = channel
                    break

        if not log_channel:
            return

        # Build the log embed
        embed = discord.Embed(
            title="✏️ Message Edited", color=0xF39C12, timestamp=discord.utils.utcnow()
        )

        # Author info
        embed.add_field(
            name="Author",
            value=f"{before.author.mention} ({before.author.name})",
            inline=True,
        )

        # Channel info
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)

        # Jump to message
        embed.add_field(
            name="Message Link",
            value=f"[Jump to Message]({after.jump_url})",
            inline=True,
        )

        # Before content
        before_content = before.content or "*No text content*"
        if len(before_content) > 1024:
            before_content = before_content[:1021] + "..."
        embed.add_field(name="Before", value=before_content, inline=False)

        # After content
        after_content = after.content or "*No text content*"
        if len(after_content) > 1024:
            after_content = after_content[:1021] + "..."
        embed.add_field(name="After", value=after_content, inline=False)

        # Set author thumbnail
        embed.set_thumbnail(url=before.author.display_avatar.url)

        # Set footer
        embed.set_footer(text=f"User ID: {before.author.id} | Message ID: {before.id}")

        try:
            await log_channel.send(embed=embed)
            logger.debug(
                f"Logged edited message from {before.author} in #{before.channel.name}"
            )
        except Exception as e:
            logger.error(f"Failed to send edit log: {e}")

    @commands.command()
    @commands.has_role("cybr")
    async def purge(self, ctx, member: discord.Member = None):
        from utils.database import purge_inventory_db, reset_wishes, update_user_data

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
        Usage: gmsgp 10
        Requires Manage Messages permission.
        """
        if count <= 0:
            await ctx.send(
                "Please specify a positive number of messages to purge.", delete_after=5
            )
            return

        if count > 100:
            await ctx.send(
                "⚠️ Maximum 100 messages can be purged at once.", delete_after=5
            )
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
            await ctx.send(
                "❌ I don't have permission to delete messages in this channel.",
                delete_after=5,
            )
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to purge messages: {e}", delete_after=5)
        except Exception as e:
            logger.error(f"Error in msgp: {e}", exc_info=True)
            await ctx.send("❌ Failed to purge messages.", delete_after=5)

    @commands.command(name="grant", aliases=["give"])
    async def grant(self, ctx, item: str, amount: int, member: str = None):
        """Grant items to a user. Usage: ggrant <item> <amount> [@member or user_id]
        Supports ALL items from the black market, chests, and currencies.
        Use item name, ID, or alias (e.g., 'dice', 'hot streak', 'xp', 'dia')
        Special: mora, tidecoins, fate
        Only the OWNER_ID can use this command.
        """
        from config import OWNER_ID
        from utils.database import add_user_item, get_user_data, update_user_data
        from cogs.blackmarket import ITEMS

        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't have permission to use this command.")
            return

        if amount <= 0:
            await ctx.send("Amount must be greater than zero.")
            return

        # Handle member/user_id parameter
        target_member = None
        if member is None:
            target_member = ctx.author
        else:
            # Try to convert mention to member
            try:
                target_member = await commands.MemberConverter().convert(ctx, member)
            except:
                # Try to convert as user ID
                try:
                    user_id = int(member)
                    target_member = ctx.guild.get_member(user_id)
                    if target_member is None:
                        # Try fetching the user if not in guild
                        try:
                            target_member = await self.bot.fetch_user(user_id)
                        except:
                            await ctx.send(f"❌ Could not find user with ID: {user_id}")
                            return
                except ValueError:
                    await ctx.send("❌ Invalid user mention or ID.")
                    return
        
        item_input = item.lower()

        # Ensure DB row exists
        data = await get_user_data(target_member.id)

        # Special currencies
        if item_input in ("mora", "gold"):
            data["mora"] += amount
            await update_user_data(target_member.id, mora=data["mora"])
            await ctx.send(f"<a:Y_:1437951897989730305> Gave {amount:,} <:mora:1437958309255577681> to {target_member.display_name}.")
            return

        if item_input in ("tide_coins", "tidecoins", "tide"):
            data["dust"] += amount
            await update_user_data(target_member.id, dust=data["dust"])
            await ctx.send(
                f"<a:Y_:1437951897989730305> Gave {amount} <:mora:1437480155952975943> Tide Coins to {target_member.display_name}."
            )
            return

        if item_input in ("fate", "fates"):
            data["fates"] += amount
            await update_user_data(target_member.id, fates=data["fates"])
            await ctx.send(
                f"<a:Y_:1437951897989730305> Gave {amount} <:fate:1437488656767254528> Intertwined Fate(s) to {target_member.display_name}."
            )
            return

        # Legacy items
        if item_input in ("hydro_essence", "hydroessence", "essence"):
            await add_user_item(target_member.id, "hydro_essence", amount)
            await ctx.send(
                f"<a:Y_:1437951897989730305> Gave {amount} <:essence:1437463601479942385> Hydro Essence to {target_member.display_name}."
            )
            return

        if item_input in ("hydro_crystal", "hydrocrystal", "crystal"):
            await add_user_item(target_member.id, "hydro_crystal", amount)
            await ctx.send(
                f"<a:Y_:1437951897989730305> Gave {amount} <:crystal:1437458982989205624> Hydro Crystal to {target_member.display_name}."
            )
            return

        if item_input in ("rod_shard", "rodshard", "shard"):
            await add_user_item(target_member.id, "rod_shard", amount)
            await ctx.send(f"<a:Y_:1437951897989730305> Gave {amount} 🔧 Rod Shard(s) to {target_member.display_name}.")
            return

        if item_input in ("fish_bait", "fishbait", "bait"):
            await add_user_item(target_member.id, "fish_bait", amount)
            await ctx.send(f"<a:Y_:1437951897989730305> Gave {amount} 🪱 Fish Bait to {target_member.display_name}.")
            return

        # Try to match item from ITEMS dictionary (supports aliases)
        item_id = None
        item_name_lower = item_input.replace(" ", "_")
        
        for iid, item_data in ITEMS.items():
            # Check item ID and name
            if iid == item_name_lower or item_data["name"].lower() == item_input:
                item_id = iid
                break
            # Check aliases if they exist
            if "aliases" in item_data:
                for alias in item_data["aliases"]:
                    if alias.lower() == item_input or alias.lower().replace(" ", "_") == item_name_lower:
                        item_id = iid
                        break
            if item_id:
                break
        
        if item_id:
            item_data = ITEMS[item_id]
            # Special handling for streak (was hot_streak in old system)
            if item_id == "streak":
                actual_id = "streak"
            else:
                actual_id = item_id
            
            async with aiosqlite.connect(DB_PATH) as db:
                # Check if user already has this item
                async with db.execute(
                    "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                    (target_member.id, actual_id)
                ) as cursor:
                    result = await cursor.fetchone()
                
                if result:
                    # Update existing
                    await db.execute(
                        "UPDATE inventory SET quantity = quantity + ? WHERE user_id = ? AND item_id = ?",
                        (amount, target_member.id, actual_id)
                    )
                else:
                    # Insert new
                    await db.execute(
                        "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)",
                        (target_member.id, actual_id, amount)
                    )
                await db.commit()
            
            await ctx.send(f"<a:Y_:1437951897989730305> Gave {amount} {item_data['emoji']} **{item_data['name']}** to {target_member.display_name}.")
            return

        await ctx.send(f"❌ Unknown item: {item}. Use `gitem` to see all available items or check item names/aliases.")
    
    @commands.command(name="grantrod", aliases=["giverod", "setrod"])
    async def grant_rod(self, ctx, tier: int = None, member: discord.Member = None):
        """Grant a fishing rod to a user. Usage: ggrantrod <1/2/3> [@user]
        Tiers: 1=Wooden, 2=Silver, 3=Golden
        Only the OWNER can use this command.
        """
        from config import OWNER_ID
        
        if ctx.author.id != OWNER_ID:
            return
        
        if tier is None or tier not in [1, 2, 3]:
            return await ctx.send("<a:X_:1437951830393884788> Usage: `ggrantrod <tier> [@user]`\nTiers: 1=Wooden, 2=Silver, 3=Golden\nExample: `ggrantrod 3` (grants yourself golden rod)")
        
        # Default to self
        target_member = member if member else ctx.author
        
        # Get fishing cog to use rod data
        fishing_cog = self.bot.get_cog('Fishing')
        if not fishing_cog:
            return await ctx.send("<a:X_:1437951830393884788> Fishing system not loaded!")
        
        # Import rod data
        from cogs.fishing import FISHING_RODS
        rod_data = FISHING_RODS[tier]
        
        # Set rod tier and full durability
        await fishing_cog.set_fishing_rod(target_member.id, tier, rod_data['max_durability'])
        
        await ctx.send(f"<a:Y_:1437951897989730305> Gave {rod_data['emoji']} **{rod_data['name']}** ({rod_data['max_durability']}/{rod_data['max_durability']} durability) to {target_member.display_name}.")
    
    @commands.command(name="fixdb", aliases=["migratedb", "updatedb"])
    async def fix_database(self, ctx):
        """Manually add ALL missing tables and columns to database (owner only)"""
        from config import OWNER_ID
        
        if ctx.author.id != OWNER_ID:
            return
        
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                added = []
                
                # === Check accounts table columns ===
                cursor = await db.execute("PRAGMA table_info('accounts')")
                cols = await cursor.fetchall()
                col_names = [c[1] for c in cols]
                
                if 'rod_tier' not in col_names:
                    await db.execute("ALTER TABLE accounts ADD COLUMN rod_tier INTEGER DEFAULT 0")
                    added.append("accounts.rod_tier")
                
                if 'rod_durability' not in col_names:
                    await db.execute("ALTER TABLE accounts ADD COLUMN rod_durability INTEGER DEFAULT 0")
                    added.append("accounts.rod_durability")
                
                if 'fishing_energy' not in col_names:
                    await db.execute("ALTER TABLE accounts ADD COLUMN fishing_energy INTEGER DEFAULT 6")
                    added.append("accounts.fishing_energy")
                
                if 'last_energy_regen' not in col_names:
                    await db.execute("ALTER TABLE accounts ADD COLUMN last_energy_regen TEXT")
                    added.append("accounts.last_energy_regen")
                
                # === Check for maintenance_whitelist table ===
                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='maintenance_whitelist'")
                if not await cursor.fetchone():
                    await db.execute("""
                        CREATE TABLE maintenance_whitelist (
                            user_id INTEGER PRIMARY KEY,
                            added_at TIMESTAMP,
                            added_by INTEGER
                        )
                    """)
                    added.append("maintenance_whitelist table")
                
                # === Check for fishing tables ===
                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='caught_fish'")
                if not await cursor.fetchone():
                    await db.execute("""
                        CREATE TABLE caught_fish (
                            user_id INTEGER,
                            fish_id TEXT,
                            quantity INTEGER DEFAULT 0,
                            fish_level INTEGER DEFAULT 1,
                            fish_exp INTEGER DEFAULT 0,
                            PRIMARY KEY (user_id, fish_id)
                        )
                    """)
                    added.append("caught_fish table")
                else:
                    # Check if fish_level and fish_exp columns exist
                    cursor = await db.execute("PRAGMA table_info('caught_fish')")
                    cols = await cursor.fetchall()
                    col_names = [c[1] for c in cols]
                    
                    if 'fish_level' not in col_names:
                        await db.execute("ALTER TABLE caught_fish ADD COLUMN fish_level INTEGER DEFAULT 1")
                        added.append("caught_fish.fish_level")
                    
                    if 'fish_exp' not in col_names:
                        await db.execute("ALTER TABLE caught_fish ADD COLUMN fish_exp INTEGER DEFAULT 0")
                        added.append("caught_fish.fish_exp")
                
                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fishing_stats'")
                if not await cursor.fetchone():
                    await db.execute("""
                        CREATE TABLE fishing_stats (
                            user_id INTEGER PRIMARY KEY,
                            total_catches INTEGER DEFAULT 0,
                            total_value INTEGER DEFAULT 0
                        )
                    """)
                    added.append("fishing_stats table")
                
                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='equipped_fish'")
                if not await cursor.fetchone():
                    await db.execute("""
                        CREATE TABLE equipped_fish (
                            user_id INTEGER,
                            slot INTEGER,
                            fish_id TEXT,
                            equipped_at TEXT,
                            PRIMARY KEY (user_id, slot)
                        )
                    """)
                    added.append("equipped_fish table")
                
                # === Check for rob_items table and columns ===
                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rob_items'")
                if not await cursor.fetchone():
                    await db.execute("""
                        CREATE TABLE rob_items (
                            user_id INTEGER PRIMARY KEY,
                            shotgun INTEGER DEFAULT 0,
                            mask INTEGER DEFAULT 0,
                            night_vision INTEGER DEFAULT 0,
                            lockpicker INTEGER DEFAULT 0,
                            guard_dog INTEGER DEFAULT 0,
                            guard_dog_expires TEXT,
                            spiky_fence INTEGER DEFAULT 0,
                            lock INTEGER DEFAULT 0,
                            ninjapack INTEGER DEFAULT 0
                        )
                    """)
                    added.append("rob_items table")
                else:
                    # Check if ninjapack column exists
                    cursor = await db.execute("PRAGMA table_info('rob_items')")
                    rob_cols = await cursor.fetchall()
                    rob_col_names = [c[1] for c in rob_cols]
                    if 'ninjapack' not in rob_col_names:
                        await db.execute("ALTER TABLE rob_items ADD COLUMN ninjapack INTEGER DEFAULT 0")
                        added.append("rob_items.ninjapack")
                
                # === Check for rob_cooldowns table ===
                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rob_cooldowns'")
                if not await cursor.fetchone():
                    await db.execute("""
                        CREATE TABLE rob_cooldowns (
                            user_id INTEGER PRIMARY KEY,
                            last_rob TEXT,
                            was_successful INTEGER DEFAULT 0
                        )
                    """)
                    added.append("rob_cooldowns table")
                else:
                    # Check if was_successful column exists
                    cursor = await db.execute("PRAGMA table_info('rob_cooldowns')")
                    cooldown_cols = await cursor.fetchall()
                    cooldown_col_names = [c[1] for c in cooldown_cols]
                    if 'was_successful' not in cooldown_col_names:
                        await db.execute("ALTER TABLE rob_cooldowns ADD COLUMN was_successful INTEGER DEFAULT 0")
                        added.append("rob_cooldowns.was_successful")
                
                await db.commit()
                
                if added:
                    await ctx.send(f"<a:Y_:1437951897989730305> **Database Updated!**\\nAdded: {', '.join(added)}")
                else:
                    await ctx.send("✅ Database is up to date! All tables and columns exist.")
        except Exception as e:
            await ctx.send(f"<a:X_:1437951830393884788> Error: {str(e)}")

    @commands.command(name="remove", aliases=["take"])
    async def remove(self, ctx, member: discord.Member, amount: int):
        """Remove mora from a user's wallet. Usage: gremove @user <amount>
        Only the OWNER can use this command.
        """
        from config import OWNER_ID
        from utils.database import get_user_data, update_user_data

        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't have permission to use this command.")
            return

        if amount <= 0:
            await ctx.send("Amount must be greater than zero.")
            return

        data = await get_user_data(member.id)
        current_mora = data.get("mora", 0)
        
        if current_mora < amount:
            await ctx.send(f"{member.display_name} only has {current_mora:,} <:mora:1437958309255577681>. Cannot remove {amount:,}.")
            return

        new_mora = current_mora - amount
        await update_user_data(member.id, mora=new_mora)
        await ctx.send(f"Removed {amount:,} <:mora:1437958309255577681> from {member.display_name}'s wallet. New balance: {new_mora:,}")

    @commands.command(name="removebank", aliases=["takebank"])
    async def remove_bank(self, ctx, member: discord.Member, amount: int):
        """Remove mora from a user's bank deposit. Usage: gremovebank @user <amount>
        Only the OWNER can use this command.
        """
        from config import OWNER_ID
        import aiosqlite
        from config import DB_PATH

        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't have permission to use this command.")
            return

        if amount <= 0:
            await ctx.send("Amount must be greater than zero.")
            return

        async with aiosqlite.connect(DB_PATH) as db:
            # Get current bank deposit
            cursor = await db.execute(
                "SELECT deposited_amount FROM user_bank_deposits WHERE user_id = ?",
                (member.id,)
            )
            row = await cursor.fetchone()
            
            if not row or row[0] == 0:
                await ctx.send(f"{member.display_name} has no bank deposits.")
                return
            
            current_deposit = row[0]
            
            if current_deposit < amount:
                await ctx.send(f"{member.display_name} only has {current_deposit:,} <:mora:1437958309255577681> in the bank. Cannot remove {amount:,}.")
                return
            
            new_deposit = current_deposit - amount
            
            # Update user's bank deposit
            await db.execute(
                "UPDATE user_bank_deposits SET deposited_amount = ? WHERE user_id = ?",
                (new_deposit, member.id)
            )
            
            # Also remove from global bank
            await db.execute(
                "UPDATE global_bank SET balance = balance - ? WHERE id = 1",
                (amount,)
            )
            
            await db.commit()
        
        await ctx.send(f"Removed {amount:,} <:mora:1437958309255577681> from {member.display_name}'s bank. New deposit: {new_deposit:,}")

    @commands.command(name="removeglobalbank", aliases=["takeglobalbank", "removeglobal"])
    async def remove_global_bank(self, ctx, amount: int):
        """Remove mora from the global bank balance. Usage: gremoveglobalbank <amount>
        Only the OWNER can use this command.
        """
        from config import OWNER_ID
        import aiosqlite
        from config import DB_PATH

        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't have permission to use this command.")
            return

        if amount <= 0:
            await ctx.send("Amount must be greater than zero.")
            return

        async with aiosqlite.connect(DB_PATH) as db:
            # Get current global bank balance
            cursor = await db.execute("SELECT balance FROM global_bank WHERE id = 1")
            row = await cursor.fetchone()
            
            if not row:
                await ctx.send("Global bank not found.")
                return
            
            current_balance = row[0]
            
            if current_balance < amount:
                await ctx.send(f"Global bank only has {current_balance:,} <:mora:1437958309255577681>. Cannot remove {amount:,}.")
                return
            
            new_balance = current_balance - amount
            
            # Update global bank
            await db.execute(
                "UPDATE global_bank SET balance = ? WHERE id = 1",
                (new_balance,)
            )
            
            await db.commit()
        
        await ctx.send(f"Removed {amount:,} <:mora:1437958309255577681> from global bank. New balance: {new_balance:,}")

    @commands.command(name="addglobalbank", aliases=["giveglobalbank", "addglobal"])
    async def add_global_bank(self, ctx, amount: int):
        """Add mora to the global bank balance. Usage: gaddglobalbank <amount>
        Only the OWNER can use this command.
        """
        from config import OWNER_ID
        import aiosqlite
        from config import DB_PATH

        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't have permission to use this command.")
            return

        if amount <= 0:
            await ctx.send("Amount must be greater than zero.")
            return

        async with aiosqlite.connect(DB_PATH) as db:
            # Get current global bank balance
            cursor = await db.execute("SELECT balance FROM global_bank WHERE id = 1")
            row = await cursor.fetchone()
            
            if not row:
                await ctx.send("Global bank not found.")
                return
            
            current_balance = row[0]
            new_balance = current_balance + amount
            
            # Update global bank
            await db.execute(
                "UPDATE global_bank SET balance = ? WHERE id = 1",
                (new_balance,)
            )
            
            await db.commit()
        
        await ctx.send(f"Added {amount:,} <:mora:1437958309255577681> to global bank. New balance: {new_balance:,}")

    @commands.command(name="givedust")
    async def give_dust(self, ctx, member: discord.Member, amount: int):
        if ctx.author.id != OWNER_ID:
            return
        try:
            data = await get_user_data(member.id)
            new_dust = data["dust"] + amount
            await update_user_data(member.id, dust=new_dust)
            await ctx.send(
                f"Gave {amount} <:mora:1437480155952975943> Tide Coins to {member.display_name}."
            )
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.command(name="setbalance", aliases=["setmora"])
    async def set_balance(self, ctx, member: discord.Member, amount: int):
        """Owner-only: Set a user's mora balance. Usage: gsetbalance @user <amount>"""
        if ctx.author.id != OWNER_ID:
            return
        
        if amount < 0:
            return await ctx.send("❌ Amount cannot be negative.")
        
        try:
            data = await get_user_data(member.id)
            old_balance = data.get('mora', 0)
            await update_user_data(member.id, mora=amount)
            
            embed = discord.Embed(
                title="💰 Balance Updated",
                description=f"Set {member.mention}'s balance",
                color=0x3498DB
            )
            embed.add_field(name="Old Balance", value=f"{old_balance:,}", inline=True)
            embed.add_field(name="New Balance", value=f"{amount:,}", inline=True)
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Error: {e}")
    
    @commands.command(name="wipeuser", aliases=["deleteuser"])
    async def wipe_user(self, ctx, member: discord.Member):
        """Owner-only: Completely wipe a user's data. Usage: gwipeuser @user"""
        if ctx.author.id != OWNER_ID:
            return
        
        # Confirmation
        confirm_msg = await ctx.send(
            f"⚠️ **WARNING**: This will permanently delete ALL data for {member.mention}!\n"
            f"React with ✅ to confirm or ❌ to cancel (30s timeout)"
        )
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
        
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            
            if str(reaction.emoji) == "❌":
                return await ctx.send("❌ User wipe cancelled.")
            
            # Delete from all tables
            import aiosqlite
            from config import DB_PATH
            
            async with aiosqlite.connect(DB_PATH) as db:
                tables = [
                    "users",
                    "user_bank_deposits",
                    "user_loans",
                    "p2p_loans",
                    "rob_cooldowns",
                    "rob_items",
                    "game_stats",
                    "transaction_logs",
                    "pulls",
                    "dispatches",
                    "achievements_progress"
                ]
                
                deleted_count = 0
                for table in tables:
                    try:
                        cursor = await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (member.id,))
                        deleted_count += cursor.rowcount
                    except:
                        pass  # Table might not exist or have different structure
                
                await db.commit()
            
            embed = discord.Embed(
                title="🗑️ User Data Wiped",
                description=f"Successfully deleted all data for {member.mention}",
                color=0xE74C3C
            )
            embed.add_field(name="Records Deleted", value=f"{deleted_count}", inline=True)
            embed.add_field(name="User ID", value=f"{member.id}", inline=True)
            await ctx.send(embed=embed)
            
        except asyncio.TimeoutError:
            await ctx.send("❌ Confirmation timeout. User wipe cancelled.")

    @commands.command(name="maintenance", aliases=["maint"])
    async def maintenance(self, ctx):
        """Owner-only: Toggle maintenance mode. When enabled, only the owner can use the bot."""
        if ctx.author.id != OWNER_ID:
            return
        
        import config
        
        # Toggle maintenance mode
        config.MAINTENANCE_MODE = not config.MAINTENANCE_MODE
        
        status = "ENABLED" if config.MAINTENANCE_MODE else "DISABLED"
        emoji = "🔧" if config.MAINTENANCE_MODE else "✅"
        
        embed = discord.Embed(
            title=f"{emoji} Maintenance Mode {status}",
            description=f"Bot is now {'under maintenance' if config.MAINTENANCE_MODE else 'operational'}",
            color=0xE67E22 if config.MAINTENANCE_MODE else 0x2ECC71
        )
        
        if config.MAINTENANCE_MODE:
            embed.add_field(
                name="Status",
                value="Only the bot owner can use commands during maintenance.",
                inline=False
            )
        else:
            embed.add_field(
                name="Status",
                value="All users can now use the bot normally.",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="madd", aliases=["maintenanceadd", "mwhitelist"])
    async def maintenance_add(self, ctx, member: discord.Member = None):
        """Add a user to maintenance mode whitelist (allows them to use bot during maintenance)"""
        if ctx.author.id != OWNER_ID:
            return
        
        if member is None:
            return await ctx.send("<a:X_:1437951830393884788> Usage: `gmadd @user`\nExample: `gmadd @JohnDoe`")
        
        from datetime import datetime
        
        # Add to whitelist
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO maintenance_whitelist (user_id, added_at, added_by) VALUES (?, ?, ?)",
                (member.id, datetime.now().isoformat(), ctx.author.id)
            )
            await db.commit()
        
        embed = discord.Embed(
            title="✅ User Whitelisted",
            description=f"{member.mention} can now use the bot during maintenance mode.",
            color=0x2ECC71
        )
        embed.set_footer(text="Use gmremove to remove from whitelist")
        await send_embed(ctx, embed)
    
    @commands.command(name="mremove", aliases=["maintenanceremove", "munwhitelist"])
    async def maintenance_remove(self, ctx, member: discord.Member = None):
        """Remove a user from maintenance mode whitelist"""
        if ctx.author.id != OWNER_ID:
            return
        
        if member is None:
            return await ctx.send("<a:X_:1437951830393884788> Usage: `gmremove @user`\nExample: `gmremove @JohnDoe`")
        
        # Remove from whitelist
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM maintenance_whitelist WHERE user_id = ?",
                (member.id,)
            )
            await db.commit()
            rows_affected = cursor.rowcount
        
        if rows_affected == 0:
            return await ctx.send(f"<a:X_:1437951830393884788> {member.mention} is not in the whitelist.")
        
        embed = discord.Embed(
            title="❌ User Removed from Whitelist",
            description=f"{member.mention} can no longer use the bot during maintenance mode.",
            color=0xE74C3C
        )
        await send_embed(ctx, embed)
    
    @commands.command(name="mlist", aliases=["maintenancelist", "mwhitelistlist"])
    async def maintenance_list(self, ctx):
        """List all users whitelisted for maintenance mode"""
        if ctx.author.id != OWNER_ID:
            return
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT user_id, added_at FROM maintenance_whitelist ORDER BY added_at DESC")
            whitelist = await cursor.fetchall()
        
        if not whitelist:
            return await ctx.send("📋 No users are currently whitelisted for maintenance mode.")
        
        embed = discord.Embed(
            title="🔧 Maintenance Whitelist",
            description=f"**{len(whitelist)}** user(s) can use the bot during maintenance:",
            color=0x3498DB
        )
        
        user_list = []
        for user_id, added_at in whitelist:
            try:
                user = await self.bot.fetch_user(user_id)
                user_list.append(f"• {user.mention} (`{user.id}`)")
            except:
                user_list.append(f"• Unknown User (`{user_id}`)")
        
        embed.add_field(name="Whitelisted Users", value="\n".join(user_list), inline=False)
        embed.set_footer(text="Use gmadd/gmremove to manage whitelist")
        await send_embed(ctx, embed)

    @commands.command(name="setprefix", aliases=["prefix"])
    async def setprefix(self, ctx, new_prefix: str = None):
        """Change the bot's command prefix. Usage: gsetprefix <new_prefix>"""
        # Check permission using the permission system
        from utils.permissions import has_permission
        if not await has_permission(ctx.author, "setprefix"):
            return await ctx.send("❌ You don't have permission to use `setprefix`! Ask an admin to grant access with `gap @role setprefix`")
        
        if not new_prefix:
            import config
            await ctx.send(f"Current prefix: `{config.PREFIX}`\nUsage: `{config.PREFIX}setprefix <new_prefix>`")
            return
        
        if len(new_prefix) > 5:
            await ctx.send("Prefix must be 5 characters or less.")
            return
        
        import config
        old_prefix = config.PREFIX
        config.PREFIX = new_prefix
        
        embed = discord.Embed(
            title="✅ Prefix Changed",
            description=f"Command prefix updated: `{old_prefix}` → `{new_prefix}`",
            color=0x2ECC71
        )
        embed.add_field(
            name="Example",
            value=f"`{new_prefix}help` `{new_prefix}slots 1000`",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @commands.command(name="cleanbadges")
    async def clean_badges(self, ctx, member: discord.Member = None):
        """Owner-only: Clean up old format badges (stage_20 -> Stage 1). Usage: gcleanbadges [@member]"""
        import aiosqlite

        from config import DB_PATH, OWNER_ID

        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't have permission to use this command.")
            return

        member = member or ctx.author

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Get all badges for the user
                async with db.execute(
                    "SELECT badge_key FROM badges WHERE user_id=?", (member.id,)
                ) as cur:
                    rows = await cur.fetchall()

                if not rows:
                    await ctx.send(f"{member.display_name} has no badges to clean.")
                    return

                # Delete old format stage badges
                await db.execute(
                    "DELETE FROM badges WHERE user_id=? AND badge_key LIKE 'stage_%'",
                    (member.id,),
                )
                deleted_count = db.total_changes
                await db.commit()

                if deleted_count > 0:
                    await ctx.send(
                        f"Cleaned {deleted_count} old format badge(s) from {member.display_name}. They will re-earn proper badges at level milestones."
                    )
                else:
                    await ctx.send(
                        f"No old format badges found for {member.display_name}."
                    )
        except Exception as e:
            print(f"Error cleaning badges: {e}")
            await ctx.send("Failed to clean badges.")

    @commands.command(name="setlevel")
    async def set_level(self, ctx, level: int, member: discord.Member = None):
        """Owner-only: Set a user's level. Usage: gsetlevel <level> [@member]"""
        import aiosqlite

        from config import DB_PATH, OWNER_ID

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
                await db.execute(
                    "UPDATE accounts SET level=?, exp=? WHERE user_id=?",
                    (level, 0, member.id),
                )
                await db.commit()

            await ctx.send(f"Set {member.display_name}'s level to {level}.")
        except Exception as e:
            print(f"Error setting level: {e}")
            await ctx.send("Failed to set level.")

    @commands.command(name="grantexp")
    async def grant_exp(self, ctx, amount: int, member: discord.Member = None):
        """Owner-only: Grant EXP to a user. Usage: ggrantexp <amount> [@member]"""
        from config import OWNER_ID
        from utils.database import add_account_exp_detailed

        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't have permission to use this command.")
            return

        member = member or ctx.author

        if amount <= 0:
            await ctx.send("Amount must be greater than zero.")
            return

        try:
            result = await add_account_exp_detailed(member.id, amount, source="admin_grant")
            await ctx.send(
                f"Granted {amount:,} EXP to {member.display_name}. Level: {result['old_level']} → {result['new_level']}"
            )
        except Exception as e:
            print(f"Error granting EXP: {e}")
            await ctx.send("Failed to grant EXP.")

    @commands.command(name="steal")
    async def steal(self, ctx, custom_name: str = None):
        """Steal an emoji or sticker from a message by replying to it. Usage: Reply to a message with !steal <name>"""
        # Check if user has admin permissions in the server OR has been granted permission
        from utils.permissions import has_permission
        
        # Allow if user has admin permissions in the server
        has_server_admin = ctx.author.guild_permissions.administrator
        has_granted_permission = await has_permission(ctx.author, "steal")
        
        if not (has_server_admin or has_granted_permission):
            return await ctx.send("❌ You need administrator permissions or granted access to use `steal`!")
        
        import re
        import aiohttp

        # Check if this is a reply
        if not ctx.message.reference:
            await ctx.send(
                "You need to reply to a message containing an emoji or sticker to steal it!"
            )
            return

        # Get the referenced message
        try:
            referenced_msg = await ctx.channel.fetch_message(
                ctx.message.reference.message_id
            )
        except:
            await ctx.send("Could not find the referenced message.")
            return

        # Check for stickers first
        if referenced_msg.stickers:
            sticker = referenced_msg.stickers[0]
            final_name = custom_name if custom_name else sticker.name

            try:
                # Download the sticker
                async with aiohttp.ClientSession() as session:
                    async with session.get(sticker.url) as resp:
                        if resp.status != 200:
                            await ctx.send("Failed to download the sticker.")
                            return
                        sticker_bytes = await resp.read()

                # Add sticker to server
                sticker_desc = getattr(sticker, 'description', None) or "Stolen sticker"
                new_sticker = await ctx.guild.create_sticker(
                    name=final_name,
                    description=sticker_desc,
                    emoji="👍",
                    file=discord.File(fp=io.BytesIO(sticker_bytes), filename=f"{final_name}.png"),
                    reason=f"Stolen by {ctx.author}"
                )

                await ctx.send(f"Successfully stole sticker: **{new_sticker.name}**")
                return

            except discord.Forbidden:
                await ctx.send("I don't have permission to add stickers to this server!")
                return
            except discord.HTTPException as e:
                if "Maximum number of stickers reached" in str(e):
                    await ctx.send("This server has reached the maximum number of stickers!")
                else:
                    await ctx.send(f"Failed to add sticker: {e}")
                return
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
                return

        # Check for custom emojis
        emoji_pattern = r"<(a?):(\w+):(\d+)>"
        matches = re.findall(emoji_pattern, referenced_msg.content)

        if not matches:
            await ctx.send("No custom emoji or sticker found in that message!")
            return

        # Use the first emoji found
        is_animated, emoji_name, emoji_id = matches[0]
        final_name = custom_name if custom_name else emoji_name

        # Construct emoji URL
        extension = "gif" if is_animated else "png"
        emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}"

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
                name=final_name, image=emoji_bytes, reason=f"Stolen by {ctx.author}"
            )

            await ctx.send(f"Successfully stole {emoji} (:{emoji.name}:)")

        except discord.Forbidden:
            await ctx.send("I don't have permission to add emojis to this server!")
        except discord.HTTPException as e:
            if "Maximum number of emojis reached" in str(e):
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

        embed = discord.Embed(title="Admin Commands", color=0xE74C3C)
        embed.add_field(
            name="User Management",
            value=(
                "`gpurge [@member]` - Purge inventory\n"
                "`gresetpulls [@member]` - Reset wish history\n"
                "`gsetlevel <level> [@member]` - Set level\n"
                "`ggrantexp <amount> [@member]` - Grant EXP"
            ),
            inline=False,
        )
        embed.add_field(
            name="Item Granting",
            value=(
                "`ggrant <item> <amount> [@member]` - Grant items\n"
                "Chests: common, exquisite, precious, luxurious\n"
                "Other: mora, tidecoins, fate, hydro_essence, hydro_crystal"
            ),
            inline=False,
        )
        embed.add_field(
            name="Item Removal",
            value=(
                "`gremove <@member> <amount>` - Remove Mora from wallet\n"
                "`gremovebank <@member> <amount>` - Remove Mora from bank\n"
                "`gremoveglobalbank <amount>` - Remove Mora from global bank\n"
                "`gaddglobalbank <amount>` - Add Mora to global bank"
            ),
            inline=False,
        )
        embed.add_field(
            name="User Management",
            value=(
                "`gsetbalance <@user> <amount>` - Set user's mora balance\n"
                "`gwipeuser <@user>` - Delete all user data (requires confirmation)"
            ),
            inline=False,
        )
        embed.add_field(
            name="Database Cleanup",
            value=("`gcleanbadges [@member]` - Clean old format badges"),
            inline=False,
        )
        embed.add_field(
            name="System",
            value=(
                "`gmaintenance` - Toggle maintenance mode (owner only)\n"
                "`gsetprefix <prefix>` - Change command prefix\n"
                "`gwipeallusers` - Wipe entire database with confirmation"
            ),
            inline=False,
        )
        embed.add_field(
            name="Moderation",
            value=(
                "`gmsgp <count>` - Purge your messages\n"
                "`gsteal` - Reply to message to steal emoji/sticker (requires Manage Emojis)\n"
                "`gresetrps <@user>` - Reset RPS cooldown for user"
            ),
            inline=False,
        )
        embed.add_field(
            name="Logging & Monitoring",
            value=(
                "`gadminlogs [limit]` - View recent transactions (default 20)\n"
                "`gplayerinfo <@user>` - View user's transaction history\n"
                "`glogtypes` - View available log types"
            ),
            inline=False,
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
        if games_cog and hasattr(games_cog, "rps_plays"):
            if member.id in games_cog.rps_plays:
                del games_cog.rps_plays[member.id]
            await ctx.send(f"Reset RPS cooldown for {member.display_name}!")
        else:
            await ctx.send("Games cog not found!")

    @commands.command(name="adminlogs", aliases=["logs"])
    async def admin_logs(self, ctx, limit: int = 20):
        """Owner-only: View recent transaction logs"""
        if ctx.author.id != OWNER_ID:
            return
        
        from utils.transaction_logger import get_recent_transactions
        
        if limit < 1 or limit > 100:
            return await ctx.send("❌ Limit must be between 1 and 100")
        
        transactions = await get_recent_transactions(limit)
        
        if not transactions:
            return await ctx.send("📋 No transactions logged yet.")
        
        embed = discord.Embed(
            title=f"Recent Transaction Logs (Last {len(transactions)})",
            color=0x3498DB
        )
        
        log_text = []
        for user_id, event_type, amount, details, timestamp in transactions:
            # Format timestamp
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%m/%d %H:%M")
            
            # Format amount
            amount_str = f"{amount:,}" if amount else "N/A"
            
            # Get user mention
            user = self.bot.get_user(user_id)
            user_str = user.mention if user else f"<@{user_id}>"
            
            # Format details
            details_str = f" - {details}" if details else ""
            
            log_text.append(f"`{time_str}` {user_str} **{event_type}** {amount_str}{details_str}")
        
        # Split into chunks if too long
        if len(log_text) <= 10:
            embed.description = "\n".join(log_text)
        else:
            # Multiple embeds for long logs
            for i in range(0, len(log_text), 10):
                chunk = log_text[i:i+10]
                if i == 0:
                    embed.description = "\n".join(chunk)
                else:
                    await ctx.send("\n".join(chunk))
        
        await ctx.send(embed=embed)
    
    @commands.command(name="playerinfo", aliases=["pinfo"])
    async def player_info(self, ctx, member: discord.Member = None):
        """Owner-only: View a user's transaction history"""
        if ctx.author.id != OWNER_ID:
            return
        
        if not member:
            return await ctx.send("Usage: `gplayerinfo @user`")
        
        from utils.transaction_logger import get_user_transactions
        from datetime import datetime
        
        transactions = await get_user_transactions(member.id, limit=30)
        
        # Get user data
        user_data = await get_user_data(member.id)
        
        embed = discord.Embed(
            title=f"Player Info: {member.display_name}",
            color=0x9B59B6
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # Add balance info
        embed.add_field(
            name="💰 Balance",
            value=f"**Mora:** {user_data.get('mora', 0):,}\n**Level:** {user_data.get('account_level', 1)}",
            inline=True
        )
        
        if not transactions:
            embed.add_field(
                name="📋 Recent Activity",
                value="No transactions logged",
                inline=False
            )
        else:
            log_text = []
            for event_type, amount, details, timestamp in transactions[:15]:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%m/%d %H:%M")
                amount_str = f"{amount:,}" if amount else ""
                details_str = f" - {details}" if details else ""
                log_text.append(f"`{time_str}` **{event_type}** {amount_str}{details_str}")
            
            embed.add_field(
                name=f"📋 Recent Activity (Last {len(log_text)})",
                value="\n".join(log_text[:15]),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="logtypes")
    async def log_types(self, ctx):
        """Owner-only: View available transaction log types"""
        if ctx.author.id != OWNER_ID:
            return
        
        embed = discord.Embed(
            title="📋 Transaction Log Types",
            description="Available event types that are logged:",
            color=0x1ABC9C
        )
        embed.add_field(
            name="Banking",
            value="`loan_taken` - User took a loan\n"
                  "`loan_repaid` - User repaid a loan\n"
                  "`deposit` - Bank deposit\n"
                  "`withdraw` - Bank withdrawal\n"
                  "`interest` - Daily interest payment",
            inline=False
        )
        embed.add_field(
            name="Games",
            value="`big_win` - Won 50k+ in a game\n"
                  "`huge_win` - Won 100k+ in a game\n"
                  "`jackpot` - Hit wheel jackpot",
            inline=False
        )
        embed.add_field(
            name="Social",
            value="`rob_success` - Successfully robbed\n"
                  "`rob_fail` - Failed robbery\n"
                  "`pay` - Sent mora to another user",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @commands.command(name="admincd", aliases=["acd"])
    async def admin_cd(self, ctx):
        """Owner-only: Show all cooldown reset commands."""
        from config import OWNER_ID

        if ctx.author.id != OWNER_ID:
            return  # Silently ignore for non-owners

        embed = discord.Embed(title="Cooldown Reset Commands", color=0x3498DB)
        embed.description = "Commands to reset user cooldowns:"

        embed.add_field(
            name="Available Resets",
            value=(
                "`gresetdaily` - Reset your daily claim cooldown\n"
                "`gfish ccd` - Reset your fishing cooldown\n"
                "`gresetrps <@user>` - Reset RPS cooldown for a user"
            ),
            inline=False,
        )

        embed.set_footer(text="Owner-only commands")
        await ctx.send(embed=embed)

    @commands.command(name="cd", aliases=["cooldown", "cooldowns"])
    async def cooldowns(self, ctx):
        """Check your current cooldowns."""
        from datetime import datetime as dt
        from datetime import timedelta

        import aiosqlite

        from config import DB_PATH

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Cooldowns", color=0x3498DB
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        cooldown_info = []

        # Check daily cooldown
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT last_claim FROM daily_claims WHERE user_id=?",
                    (ctx.author.id,),
                ) as cur:
                    row = await cur.fetchone()

                if row and row[0]:
                    last_claim = dt.fromisoformat(row[0])
                    next_claim = last_claim + timedelta(hours=24)
                    now = dt.utcnow()

                    if now >= next_claim:
                        cooldown_info.append(
                            "<a:arrow:1437968863026479258> **Next Daily:** Ready"
                        )
                    else:
                        time_left = next_claim - now
                        hours = int(time_left.total_seconds() // 3600)
                        minutes = int((time_left.total_seconds() % 3600) // 60)
                        cooldown_info.append(
                            f"<a:arrow:1437968863026479258> **Next Daily:** {hours}h {minutes}m"
                        )
                else:
                    cooldown_info.append(
                        "<a:arrow:1437968863026479258> **Next Daily:** Ready"
                    )
        except Exception:
            cooldown_info.append("<a:arrow:1437968863026479258> **Next Daily:** Ready")

        # Check bundle cooldown (premium daily)
        try:
            # Check if user is premium
            premium_cog = self.bot.get_cog('Premium')
            is_premium = False
            if premium_cog:
                is_premium = await premium_cog.is_premium(ctx.author.id)
            
            if not is_premium:
                cooldown_info.append(
                    "<a:arrow:1437968863026479258> **Next Bundle:** Premium Exclusive"
                )
            else:
                async with aiosqlite.connect(DB_PATH) as db:
                    async with db.execute(
                        "SELECT last_claim FROM daily_claims WHERE user_id=? AND claim_type='premium'",
                        (ctx.author.id,),
                    ) as cur:
                        row = await cur.fetchone()

                    if row and row[0]:
                        last_claim = dt.fromisoformat(row[0])
                        next_claim = last_claim + timedelta(hours=12)
                        now = dt.utcnow()

                        if now >= next_claim:
                            cooldown_info.append(
                                "<a:arrow:1437968863026479258> **Next Bundle:** Ready"
                            )
                        else:
                            time_left = next_claim - now
                            hours = int(time_left.total_seconds() // 3600)
                            minutes = int((time_left.total_seconds() % 3600) // 60)
                            cooldown_info.append(
                                f"<a:arrow:1437968863026479258> **Next Bundle:** {hours}h {minutes}m"
                            )
                    else:
                        cooldown_info.append(
                            "<a:arrow:1437968863026479258> **Next Bundle:** Ready"
                        )
        except Exception:
            cooldown_info.append("<a:arrow:1437968863026479258> **Next Bundle:** Ready")

        # Show next energy regen time
        try:
            from utils.database import get_fishing_energy
            from datetime import datetime, timedelta
            
            # Check if premium for energy display
            premium_cog = self.bot.get_cog('Premium')
            is_premium = False
            if premium_cog:
                is_premium = await premium_cog.is_premium(ctx.author.id)
            
            current_energy = await get_fishing_energy(ctx.author.id, is_premium)
            max_energy = 9 if is_premium else 6
            regen_minutes = 30 if is_premium else 60
            
            # Get last regen time to calculate next regen
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT last_energy_regen FROM accounts WHERE user_id = ?",
                    (ctx.author.id,)
                )
                result = await cursor.fetchone()
                
                if result and result[0] and current_energy < max_energy:
                    last_regen = datetime.fromisoformat(result[0])
                    next_regen = last_regen + timedelta(minutes=regen_minutes)
                    now = datetime.utcnow()
                    
                    if now >= next_regen:
                        cooldown_info.append(
                            f"<a:arrow:1437968863026479258> **Next Energy:** Ready ({current_energy}/{max_energy} <:energy:1459189042574004224>)"
                        )
                    else:
                        time_left = next_regen - now
                        minutes = int(time_left.total_seconds() // 60)
                        seconds = int(time_left.total_seconds() % 60)
                        cooldown_info.append(
                            f"<a:arrow:1437968863026479258> **Next Energy:** {minutes}m {seconds}s ({current_energy}/{max_energy} <:energy:1459189042574004224>)"
                        )
                elif current_energy >= max_energy:
                    cooldown_info.append(
                        f"<a:arrow:1437968863026479258> **Next Energy:** Full ({current_energy}/{max_energy} <:energy:1459189042574004224>)"
                    )
                else:
                    cooldown_info.append(
                        f"<a:arrow:1437968863026479258> **Next Energy:** Ready ({current_energy}/{max_energy} <:energy:1459189042574004224>)"
                    )
        except Exception:
            cooldown_info.append(
                "<a:arrow:1437968863026479258> **Next Energy:** Ready"
            )

        # Check RPS cooldown
        try:
            games_cog = self.bot.get_cog("Games")
            if games_cog and hasattr(games_cog, "rps_plays"):
                if ctx.author.id in games_cog.rps_plays:
                    last_play = games_cog.rps_plays[ctx.author.id]
                    now = dt.utcnow()
                    cooldown_duration = timedelta(hours=1)
                    next_play = last_play + cooldown_duration

                    if now >= next_play:
                        cooldown_info.append(
                            "<a:arrow:1437968863026479258> **Next RPS:** Ready"
                        )
                    else:
                        time_left = next_play - now
                        minutes = int(time_left.total_seconds() // 60)
                        seconds = int(time_left.total_seconds() % 60)
                        cooldown_info.append(
                            f"<a:arrow:1437968863026479258> **Next RPS:** {minutes}m {seconds}s"
                        )
                else:
                    cooldown_info.append(
                        "<a:arrow:1437968863026479258> **Next RPS:** Ready"
                    )
            else:
                cooldown_info.append(
                    "<a:arrow:1437968863026479258> **Next RPS:** Ready"
                )
        except Exception:
            cooldown_info.append("<a:arrow:1437968863026479258> **Next RPS:** Ready")

        # Check Sybau cooldown (booster only)
        try:
            admin_cog = self.bot.get_cog("Admin")
            if admin_cog and hasattr(admin_cog, "sybau_cooldowns"):
                cooldown_key = f"{ctx.guild.id}_{ctx.author.id}"
                if cooldown_key in admin_cog.sybau_cooldowns:
                    last_used = admin_cog.sybau_cooldowns[cooldown_key]
                    time_passed = (dt.utcnow() - last_used).total_seconds()
                    cooldown_seconds = 15 * 60  # 15 minutes
                    
                    if time_passed >= cooldown_seconds:
                        cooldown_info.append(
                            "<a:arrow:1437968863026479258> **Next Sybau:** Ready"
                        )
                    else:
                        remaining = int(cooldown_seconds - time_passed)
                        minutes = remaining // 60
                        seconds = remaining % 60
                        cooldown_info.append(
                            f"<a:arrow:1437968863026479258> **Next Sybau:** {minutes}m {seconds}s"
                        )
                else:
                    cooldown_info.append(
                        "<a:arrow:1437968863026479258> **Next Sybau:** Ready"
                    )
            else:
                cooldown_info.append(
                    "<a:arrow:1437968863026479258> **Next Sybau:** Ready"
                )
        except Exception:
            cooldown_info.append("<a:arrow:1437968863026479258> **Next Sybau:** Ready")

        embed.description = "\n".join(cooldown_info)

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
                color=0x2ECC71,
            )
            test_embed.set_footer(text="Message deletion tracking is active!")
            await channel.send(embed=test_embed)

            if channel.id != ctx.channel.id:
                await ctx.send(f"✅ Log channel set to {channel.mention}")
        except discord.Forbidden:
            await ctx.send(
                f"❌ I don't have permission to send messages in {channel.mention}"
            )
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
                if channel.name in [
                    "logs",
                    "mod-logs",
                    "message-logs",
                    "deleted-messages",
                ]:
                    log_channel = channel
                    break

        embed = discord.Embed(title="Message Logging Status", color=0x3498DB)

        if log_channel:
            embed.add_field(name="Status", value="✅ Active", inline=True)
            embed.add_field(name="Log Channel", value=log_channel.mention, inline=True)
            embed.add_field(
                name="Cached Messages",
                value=f"{len(self.message_cache):,}",
                inline=True,
            )
            embed.add_field(
                name="Features",
                value="- Message Deletions\n- Message Edits\n- Author & Deleter Info",
                inline=False,
            )

            # Add permissions check
            perms = log_channel.permissions_for(ctx.guild.me)
            perms_status = []
            perms_status.append(
                f"{'✅' if perms.send_messages else '❌'} Send Messages"
            )
            perms_status.append(f"{'✅' if perms.embed_links else '❌'} Embed Links")
            perms_status.append(
                f"{'✅' if perms.view_audit_log else '⚠️'} View Audit Log"
            )
            embed.add_field(
                name="Bot Permissions", value="\n".join(perms_status), inline=False
            )
        else:
            embed.add_field(name="Status", value="⚠️ No log channel found", inline=False)
            embed.add_field(
                name="Available Channels",
                value=f"Found {len(channel_list)} channels:\n"
                + ", ".join(f"`{c}`" for c in channel_list[:10]),
                inline=False,
            )
            embed.add_field(
                name="Setup",
                value="Create a channel named:\n- `logs`\n- `mod-logs`\n- `message-logs`\n- `deleted-messages`\n\nOr use `gsetlogchannel #channel`",
                inline=False,
            )

        embed.set_footer(
            text="Message logging requires audit log permissions for 'Deleted By' info"
        )
        await ctx.send(embed=embed)

    @commands.command(name="testlog")
    @commands.has_permissions(manage_messages=True)
    async def test_log(self, ctx):
        """Send a test message and delete it to test logging."""
        test_msg = await ctx.send(
            "🧪 This is a test message. It will be deleted in 3 seconds to test logging..."
        )
        await asyncio.sleep(3)
        await test_msg.delete()
        await ctx.send(
            "✅ Test message deleted. Check your log channel!", delete_after=5
        )

    @commands.command(name="logfilter", aliases=["logconfig"])
    @commands.has_permissions(administrator=True)
    async def log_filter(self, ctx):
        """Configure which types of users' deleted messages get logged (Admin only)."""
        guild_id = ctx.guild.id

        # Initialize settings if not exists
        if guild_id not in self.log_settings:
            self.log_settings[guild_id] = {
                "bots": False,
                "members": True,
                "moderators": False,
            }

        view = LogFilterView(self, guild_id)
        embed = view.create_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command(name="botsettings", aliases=["settings", "adminsettings", "config"])
    @commands.has_permissions(manage_guild=True)
    async def botsettings(self, ctx):
        """Open the bot admin settings panel (Manage Server permission required)."""
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server!")
        
        view = BotSettingsView(ctx.guild.id, self)
        embed = view.create_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command(name="blacklistchannel", aliases=["blockchannel"])
    @commands.has_permissions(manage_guild=True)
    async def blacklist_channel(self, ctx, channel: discord.TextChannel = None):
        """Blacklist a channel - bot will not respond to ANY commands there.
        
        Usage:
        g blacklistchannel - Blacklist current channel
        g blacklistchannel #channel - Blacklist specific channel
        
        Example: g blacklistchannel #off-topic
        """
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server!")
        
        target_channel = channel or ctx.channel
        
        # Disable ALL commands in the channel using wildcard
        import aiosqlite
        from config import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if already blacklisted
            cursor = await db.execute("""
                SELECT 1 FROM disabled_channels 
                WHERE guild_id = ? AND channel_id = ? AND command_name = '*'
            """, (ctx.guild.id, target_channel.id))
            
            if await cursor.fetchone():
                return await ctx.send(f"❌ {target_channel.mention} is already blacklisted!")
            
            await db.execute("""
                INSERT INTO disabled_channels (guild_id, channel_id, command_name)
                VALUES (?, ?, '*')
            """, (ctx.guild.id, target_channel.id))
            await db.commit()
        
        embed = discord.Embed(
            title="🚫 Channel Blacklisted",
            description=f"{target_channel.mention} has been blacklisted. Bot will not respond to any commands there.",
            color=0xE74C3C
        )
        await ctx.send(embed=embed)

    @commands.command(name="unblacklistchannel", aliases=["unblockchannel"])
    @commands.has_permissions(manage_guild=True)
    async def unblacklist_channel(self, ctx, channel: discord.TextChannel = None):
        """Remove channel from blacklist.
        
        Usage:
        g unblacklistchannel - Remove current channel from blacklist
        g unblacklistchannel #channel - Remove specific channel from blacklist
        
        Example: g unblacklistchannel #off-topic
        """
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server!")
        
        target_channel = channel or ctx.channel
        
        import aiosqlite
        from config import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                DELETE FROM disabled_channels 
                WHERE guild_id = ? AND channel_id = ? AND command_name = '*'
            """, (ctx.guild.id, target_channel.id))
            await db.commit()
            
            if cursor.rowcount == 0:
                return await ctx.send(f"❌ {target_channel.mention} is not blacklisted!")
        
        embed = discord.Embed(
            title="✅ Channel Unblacklisted",
            description=f"{target_channel.mention} has been removed from blacklist. Commands will work there again.",
            color=0x2ECC71
        )
        await ctx.send(embed=embed)

    @commands.command(name="health")
    async def health_check(self, ctx):
        """Display bot health status (owner only)."""
        if ctx.author.id != OWNER_ID:
            return

        try:
            import os
            import time

            import psutil

            from utils.db_validator import validate_database

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

            embed = discord.Embed(
                title="🏥 Bot Health Status", color=0x2ECC71 if db_success else 0xF39C12
            )
            embed.add_field(name="Database", value=db_status, inline=True)
            embed.add_field(
                name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True
            )
            embed.add_field(
                name="Response Time", value=f"{round(response_time)}ms", inline=True
            )
            embed.add_field(name="Guilds", value=str(guilds), inline=True)
            embed.add_field(name="Users", value=f"{total_members:,}", inline=True)
            embed.add_field(name="Cogs Loaded", value=str(cogs_loaded), inline=True)
            embed.add_field(
                name="Memory Usage", value=f"{memory_mb:.1f} MB", inline=True
            )

            if not db_success:
                embed.add_field(
                    name="Database Issues",
                    value="\n".join(f"- {issue}" for issue in db_issues[:5]),
                    inline=False,
                )

            embed.set_footer(
                text="All systems operational" if db_success else "Some issues detected"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in health check: {e}", exc_info=True)
            await ctx.send(f"❌ Health check failed: {e}")

    @commands.command(name="wipeallusers", aliases=["resetalldata", "purgeall"])
    async def wipe_all_users(self, ctx):
        """Wipe ALL users from the database (Owner only - DESTRUCTIVE!)
        
        This will delete ALL user data from ALL tables.
        """
        if ctx.author.id != 873464016217968640:
            return await ctx.send("You don't have permission to use this command.")
        
        # Confirmation
        confirm_embed = discord.Embed(
            title="⚠️ WARNING: TOTAL DATABASE WIPE",
            description=(
                "**This will DELETE ALL USERS and ALL DATA:**\n\n"
                "❌ All user accounts\n"
                "❌ All balances (Mora, items)\n"
                "❌ All bank deposits & loans\n"
                "❌ All achievements\n"
                "❌ All game stats\n"
                "❌ All premium subscriptions\n"
                "❌ All rob items & cooldowns\n"
                "❌ ALL USER DATA\n\n"
                "**This action is IRREVERSIBLE!**"
            ),
            color=0xE74C3C
        )
        confirm_embed.set_footer(text="React with Check to confirm or X to cancel (30 seconds)")
        msg = await ctx.send(embed=confirm_embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            
            if str(reaction.emoji) == "❌":
                return await ctx.send("❌ Database wipe cancelled.")
            
            # Delete from all tables
            import aiosqlite
            from config import DB_PATH
            
            async with aiosqlite.connect(DB_PATH) as db:
                tables = [
                    "users", "pulls", "user_wishes", "chests", "chest_inventory",
                    "accounts", "daily_claims", "user_loans", "user_bank_deposits",
                    "achievements", "badges", "fishing", "caught_fish", "pets",
                    "quests", "user_items", "shop_purchases", "game_limits",
                    "user_settings", "trades", "premium_users", "rob_items",
                    "rob_cooldowns", "game_stats", "fish_caught", "fish_pets"
                ]
                
                total_deleted = 0
                for table in tables:
                    try:
                        result = await db.execute(f"DELETE FROM {table}")
                        total_deleted += result.rowcount
                    except Exception as e:
                        print(f"Error deleting from {table}: {e}")
                
                # Reset global bank to 1M
                try:
                    await db.execute("UPDATE global_bank SET balance = 1000000 WHERE id = 1")
                except:
                    pass
                
                await db.commit()
            
            embed = discord.Embed(
                title="✅ Database Wiped",
                description=f"All user data has been deleted.",
                color=0x2ECC71
            )
            embed.add_field(
                name="Records Deleted",
                value=f"`{total_deleted:,}` database entries removed",
                inline=False
            )
            embed.add_field(
                name="Global Bank",
                value="Reset to 1,000,000 Mora",
                inline=False
            )
            await ctx.send(embed=embed)
            
        except TimeoutError:
            await ctx.send("⏱️ Database wipe timed out. Cancelled.")


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
        self.add_item(ToggleButton(self, "bots", "🤖 Bots", settings["bots"]))
        self.add_item(ToggleButton(self, "members", "👥 Members", settings["members"]))
        self.add_item(
            ToggleButton(self, "moderators", "🛡️ Moderators", settings["moderators"])
        )

    def create_embed(self):
        """Create the status embed."""
        settings = self.cog.log_settings[self.guild_id]

        embed = discord.Embed(
            title="🔧 Message Logging Filters",
            description="Choose which types of users' deleted messages should be logged:",
            color=0x5865F2,
        )

        def status_icon(enabled):
            return "✅ Enabled" if enabled else "❌ Disabled"

        embed.add_field(
            name="🤖 Bot Messages", value=status_icon(settings["bots"]), inline=True
        )
        embed.add_field(
            name="👥 Member Messages",
            value=status_icon(settings["members"]),
            inline=True,
        )
        embed.add_field(
            name="🛡️ Moderator Messages",
            value=status_icon(settings["moderators"]),
            inline=True,
        )

        embed.set_footer(
            text="Click buttons below to toggle - Changes apply immediately"
        )

        return embed


class ToggleButton(discord.ui.Button):
    """Button for toggling log filter settings."""

    def __init__(
        self, view: LogFilterView, setting_key: str, label: str, enabled: bool
    ):
        self.setting_key = setting_key
        style = (
            discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary
        )
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
        logger.info(
            f"Log filter updated in guild {self.parent_view.guild_id}: {self.setting_key} = {settings[self.setting_key]}"
        )


class BotSettingsView(discord.ui.View):
    """Interactive view for bot admin settings"""
    
    def __init__(self, guild_id, cog):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.cog = cog
        
        # Initialize guild settings if not exist
        if guild_id not in self.cog.log_settings:
            self.cog.log_settings[guild_id] = {
                "bots": False,
                "members": True,
                "moderators": True
            }
        
        self.update_buttons()
    
    def create_embed(self):
        """Create the settings embed"""
        embed = discord.Embed(
            title="⚙️ Bot Admin Settings",
            description="Select a category to configure server settings:",
            color=0x3498DB
        )
        
        embed.add_field(
            name="📝 Message Logs",
            value="Configure message deletion and edit logging",
            inline=False
        )
        
        embed.add_field(
            name="🔧 More Settings",
            value="Additional configuration options coming soon...",
            inline=False
        )
        
        embed.set_footer(text="Select an option from the menu below")
        return embed
    
    def update_buttons(self):
        """Update button states based on current settings"""
        self.clear_items()
        
        # Add a select menu for settings categories
        select = SettingsCategorySelect()
        self.add_item(select)
    
    async def on_timeout(self):
        """Disable buttons when view times out"""
        for item in self.children:
            item.disabled = True


class SettingsCategorySelect(discord.ui.Select):
    """Select menu for choosing settings category"""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Message Logs",
                description="Set up message deletion logging channel",
                emoji="📝",
                value="message_logs"
            ),
            discord.SelectOption(
                label="Log Filters",
                description="Configure what gets logged",
                emoji="🔧",
                value="log_filters"
            ),
        ]
        super().__init__(
            placeholder="Choose a setting category...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Check permissions
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ You need Manage Server permission to change bot settings!",
                ephemeral=True
            )
        
        choice = self.values[0]
        
        if choice == "message_logs":
            # Show channel selector
            view = ChannelSelectorView(interaction.guild)
            embed = discord.Embed(
                title="📝 Message Logs Setup",
                description="Select a channel where message deletion logs should be sent:",
                color=0x3498DB
            )
            embed.set_footer(text="Select a channel from the dropdown below")
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        elif choice == "log_filters":
            # Show log filters view (existing functionality)
            parent_view = self.view
            if hasattr(parent_view, 'cog') and hasattr(parent_view, 'guild_id'):
                view = LogFilterView(parent_view.cog, parent_view.guild_id)
                embed = view.create_embed()
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ChannelSelectorView(discord.ui.View):
    """View for selecting a log channel"""
    
    def __init__(self, guild):
        super().__init__(timeout=180)
        self.guild = guild
        
        # Add channel select menu
        self.add_item(ChannelSelect(guild))


class ChannelSelect(discord.ui.ChannelSelect):
    """Select menu for choosing a text channel"""
    
    def __init__(self, guild):
        super().__init__(
            placeholder="Choose a log channel...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )
        self.guild = guild
    
    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        
        # Test if bot can send messages
        try:
            test_embed = discord.Embed(
                title="✅ Log Channel Set",
                description=f"This channel ({channel.mention}) will now receive message deletion logs.",
                color=0x2ECC71,
            )
            test_embed.set_footer(text="Message deletion tracking is active!")
            await channel.send(embed=test_embed)
            
            await interaction.response.send_message(
                f"✅ Log channel successfully set to {channel.mention}!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {channel.mention}",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error setting log channel: {e}")
            await interaction.response.send_message(
                "❌ Failed to set log channel.",
                ephemeral=True
            )


class SettingToggleButton(discord.ui.Button):
    """Button for toggling a specific setting"""
    
    def __init__(self, label: str, enabled: bool, setting_key: str, view):
        self.setting_key = setting_key
        style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary
        emoji = "✅" if enabled else "❌"
        super().__init__(style=style, label=label, emoji=emoji)
        self.parent_view = view
    
    async def callback(self, interaction: discord.Interaction):
        # Check if user has manage_guild permission
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ You need Manage Server permission to change bot settings!",
                ephemeral=True
            )
        
        # Toggle the setting
        settings = self.parent_view.cog.log_settings[self.parent_view.guild_id]
        settings[self.setting_key] = not settings[self.setting_key]
        
        # Update the view
        self.parent_view.update_buttons()
        embed = self.parent_view.create_embed()
        
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
        logger.info(
            f"Setting updated in guild {self.parent_view.guild_id}: {self.setting_key} = {settings[self.setting_key]}"
        )


async def setup(bot):
    await bot.add_cog(Moderation(bot))
