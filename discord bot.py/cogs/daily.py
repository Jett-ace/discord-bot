import random
from datetime import datetime, timedelta

import aiosqlite
import discord
from discord.ext import commands

from config import DB_PATH
from utils.database import ensure_user_db, get_user_data, require_enrollment
from utils.embed import send_embed


class Daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS daily_claims (
                    user_id INTEGER NOT NULL,
                    last_claim TEXT NOT NULL,
                    streak INTEGER DEFAULT 1,
                    claim_type TEXT DEFAULT 'regular',
                    PRIMARY KEY (user_id, claim_type)
                )
            """)
            # Add claim_type column if it doesn't exist
            try:
                await db.execute("ALTER TABLE daily_claims ADD COLUMN claim_type TEXT DEFAULT 'regular'")
            except:
                pass  # Column already exists
            await db.commit()
    
    @commands.command(name="start")
    async def start(self, ctx):
        """Start playing the bot and get your starting bonus!"""
        from utils.database import is_enrolled
        # Check if already enrolled
        if await is_enrolled(ctx.author.id):
            return await ctx.send("❌ You've already started! Use `ghelp` to see available commands.")
        
        # Create or update user account
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if user exists
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (ctx.author.id,))
            row = await cursor.fetchone()
            
            if row:
                # User exists, just set enrolled flag
                await db.execute(
                    "UPDATE users SET enrolled = 1 WHERE user_id = ?",
                    (ctx.author.id,)
                )
            else:
                # New user, create with starting bonus
                await db.execute(
                    "INSERT INTO users (user_id, mora, dust, fates, enrolled) VALUES (?, ?, ?, ?, ?)",
                    (ctx.author.id, 50000, 0, 0, 1)
                )
            await db.commit()
        
        # Now ensure all other tables are set up
        await ensure_user_db(ctx.author.id)
        
        embed = discord.Embed(
            title="✅ Welcome to the Bot!",
            description=f"Welcome {ctx.author.mention}! You've started your journey!",
            color=0x2ECC71
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(
            name="Starting Gift",
            value="You received `50,000` <:mora:1437958309255577681> to get started!",
            inline=False
        )
        embed.add_field(
            name="Get Started",
            value=(
                "`ghelp` - View all commands\n"
                "`gdaily` - Claim daily rewards\n"
                "`gcoinflip` - Play games\n"
                "`gbal` - Check your balance"
            ),
            inline=False
        )
        await send_embed(ctx, embed)
    
    @commands.command(name="unenroll", aliases=["removeplayer"])
    async def unenroll(self, ctx, member: discord.Member = None):
        """Remove a player from the database (OWNER ONLY)
        
        Usage: gunenroll @user
        This will delete ALL data for the user from the database.
        """
        # Owner only check
        if ctx.author.id != 873464016217968640:
            return await ctx.send("nice try bozo.")
        
        if not member:
            return await ctx.send("Usage: `gunenroll @user`")
        
        target_id = member.id
        
        # Confirmation
        confirm_embed = discord.Embed(
            title="⚠️ Confirm User Removal",
            description=f"Are you sure you want to remove {member.mention} from the database?\n\n**This will delete ALL their data:**\n- Mora, Dust, Fates\n- Characters/Pulls\n- Achievements\n- Daily streak\n- Bank deposits/loans\n- Inventory items\n- Everything else",
            color=0xE74C3C
        )
        confirm_embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        confirm_embed.set_footer(text="React with Check to confirm or X to cancel (30 seconds)")
        msg = await send_embed(ctx, confirm_embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            
            if str(reaction.emoji) == "❌":
                await ctx.send("❌ Removal cancelled.")
                return
            
            # Delete from all tables
            async with aiosqlite.connect(DB_PATH) as db:
                tables = [
                    "users", "pulls", "user_wishes", "chests", "chest_inventory",
                    "accounts", "daily_claims", "user_loans", "user_bank_deposits",
                    "achievements", "badges", "fishing", "caught_fish", "pets",
                    "quests", "user_items", "shop_purchases", "game_limits",
                    "user_settings", "trades"
                ]
                
                deleted_count = 0
                for table in tables:
                    try:
                        result = await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (target_id,))
                        deleted_count += result.rowcount
                    except Exception:
                        pass  # Table might not exist or no data
                
                await db.commit()
            
            embed = discord.Embed(
                title="✅ User Removed",
                description=f"{member.mention} has been completely removed from the database.",
                color=0x2ECC71
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embed.add_field(
                name="Records Deleted",
                value=f"`{deleted_count}` database entries removed",
                inline=False
            )
            await send_embed(ctx, embed)
            
        except TimeoutError:
            await ctx.send("⏱️ Removal timed out. Cancelled.")

    @commands.command(name="daily")
    async def daily(self, ctx):
        try:
            if not await require_enrollment(ctx):
                return
            
            await ensure_user_db(ctx.author.id)
            now = datetime.utcnow()

            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT last_claim, streak FROM daily_claims WHERE user_id = ? AND (claim_type = 'regular' OR claim_type IS NULL)",
                    (ctx.author.id,),
                ) as cursor:
                    row = await cursor.fetchone()

                if row:
                    last_claim_str, streak = row
                    last_claim = datetime.fromisoformat(last_claim_str)
                    time_diff = now - last_claim

                    if time_diff < timedelta(hours=24):
                        time_left = timedelta(hours=24) - time_diff
                        hours = int(time_left.total_seconds() // 3600)
                        minutes = int((time_left.total_seconds() % 3600) // 60)

                        embed = discord.Embed(
                            title="Daily Rewards",
                            description=f"<a:X_:1437951830393884788> You've already claimed your daily rewards!\n\nCome back in **{hours}h {minutes}m**",
                            color=0xE74C3C,
                        )
                        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
                        embed.set_thumbnail(url=ctx.author.display_avatar.url)
                        embed.set_footer(
                            text=f"Current Streak: {streak} day{'s' if streak != 1 else ''}"
                        )
                        return await send_embed(ctx, embed)

                    if time_diff <= timedelta(hours=48):
                        streak += 1
                    else:
                        streak = 1
                else:
                    streak = 1

                display_streak = streak
                
                # Get user level for scaling
                from utils.database import get_account_level
                user_level, _, _ = await get_account_level(ctx.author.id)
                
                # Check premium status for 3x rewards
                is_premium = False
                try:
                    premium_cog = self.bot.get_cog('Premium')
                    if premium_cog:
                        is_premium = await premium_cog.is_premium(ctx.author.id)
                except:
                    pass
                
                # Base rewards
                base_mora = 25000
                
                # Level bonus: +500 Mora per level
                level_bonus = user_level * 500
                
                # Streak bonus: 5% per day, max 50% at 10 days
                streak_bonus_percent = min(streak * 5, 50)
                mora_reward = int((base_mora + level_bonus) * (1 + streak_bonus_percent / 100))
                
                # Premium bonus: 3x rewards
                if is_premium:
                    mora_reward = mora_reward * 3

                user_data = await get_user_data(ctx.author.id)
                new_mora = user_data["mora"] + mora_reward

                await db.execute(
                    "UPDATE users SET mora = ? WHERE user_id = ?",
                    (new_mora, ctx.author.id),
                )

                await db.execute(
                    """
                    INSERT OR REPLACE INTO daily_claims (user_id, last_claim, streak, claim_type)
                    VALUES (?, ?, ?, 'regular')
                """,
                    (ctx.author.id, now.isoformat(), display_streak),
                )
                
                # Grant +2 fishing energy
                from utils.database import add_fishing_energy
                await add_fishing_energy(ctx.author.id, 2, is_premium)
                
                # Give 0-2 regular chests with streak-based odds
                # Base: 50% for first chest, 30% for second chest
                # Each streak day adds +2% to both chances (max +40% at 20 streak)
                streak_bonus_chest = min(display_streak * 2, 40)
                first_chest_chance = 0.50 + (streak_bonus_chest / 100)
                second_chest_chance = 0.30 + (streak_bonus_chest / 100)
                
                chest_count = 0
                if random.random() < first_chest_chance:
                    chest_count += 1
                    if random.random() < second_chest_chance:
                        chest_count += 1
                
                if chest_count > 0:
                    await db.execute("""
                        INSERT INTO inventory (user_id, item_id, quantity)
                        VALUES (?, 'regular_chest', ?)
                        ON CONFLICT(user_id, item_id) DO UPDATE SET
                            quantity = quantity + ?
                    """, (ctx.author.id, chest_count, chest_count))

                await db.commit()

            achievements_earned = []
            if display_streak == 10:
                achievements_earned.append("daily_streak_10")
            elif display_streak == 20:
                achievements_earned.append("daily_streak_20")
            elif display_streak == 30:
                achievements_earned.append("daily_streak_30")
            elif display_streak == 50:
                achievements_earned.append("daily_streak_50")
            elif display_streak == 100:
                achievements_earned.append("daily_streak_100")

            if achievements_earned:
                from utils.achievements import get_achievement_meta
                from utils.database import award_achievement

                async with aiosqlite.connect(DB_PATH) as db:
                    for ach_key in achievements_earned:
                        # Use the centralized award_achievement function
                        meta = get_achievement_meta(ach_key)
                        try:
                            await award_achievement(
                                ctx.author.id,
                                ach_key,
                                str(meta.get("title", ach_key)),
                                meta.get("description", ""),
                            )

                            # Award 50k Mora for daily streak achievements
                            await db.execute(
                                "UPDATE users SET mora = mora + 50000 WHERE user_id = ?",
                                (ctx.author.id,)
                            )
                        except Exception as e:
                            print(f"Error awarding achievement {ach_key}: {e}")

                    await db.commit()

            # Build achievement header if earned
            achievement_header = ""
            if achievements_earned:
                from utils.achievements import get_achievement_meta
                ach_title = get_achievement_meta(achievements_earned[0]).get(
                    "title", "Achievement"
                )
                achievement_header = f"🏆 Achievement Unlocked: {ach_title}!\n\n"

            embed = discord.Embed(
                title="Daily Rewards Claimed!",
                description=f"{achievement_header}**Rewards:**",
                color=0x2ECC71
            )

            embed.set_author(
                name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)

            # Rewards section
            rewards_text = f"<:mora:1437958309255577681> Mora: {mora_reward:,}"
            if is_premium:
                rewards_text += " (3x Premium)"
            if chest_count > 0:
                rewards_text += f"\n<:regular:1437473086571286699> Regular Chest: {chest_count}x"
            rewards_text += "\n<:energy:1459189042574004224> Fishing Energy: +2"
            
            embed.add_field(
                name="\u200b",
                value=rewards_text,
                inline=False,
            )

            # Bonuses section
            bonus_lines = []
            bonus_lines.append(f"Level {user_level}: {level_bonus:,} <:mora:1437958309255577681>")
            if display_streak > 1:
                streak_mora = int((base_mora + level_bonus) * (streak_bonus_percent / 100))
                if is_premium:
                    streak_mora *= 3
                bonus_lines.append(f"Streak x{display_streak}: {streak_mora:,} <:mora:1437958309255577681>")
            
            embed.add_field(
                name="Bonuses",
                value="\n".join(bonus_lines),
                inline=False
            )

            embed.set_image(
                url="https://cdn.discordapp.com/attachments/1014919079154425917/1020348943902711868/gw_divider.png?ex=6914a181&is=69135001&hm=097a7ed105cff61e7dec6a9f894f9a27ead6950a765de7d50b0970c6e0586b09&"
            )
            
            # Update quest progress
            try:
                quests_cog = self.bot.get_cog('Quests')
                if quests_cog:
                    await quests_cog.update_quest_progress(ctx.author.id, 'daily', 1)
            except:
                pass
            
            await send_embed(ctx, embed)

        except Exception as e:
            from utils.logger import setup_logger

            logger = setup_logger("Daily")
            logger.error(f"Error in bundle command: {e}", exc_info=True)
            await ctx.send(
                "❌ Something went wrong while claiming your bundle rewards. Please try again in a moment."
            )

    @commands.command(name="bundle", aliases=["bd"])
    async def premium_daily(self, ctx):
        """Claim bundle rewards (every 12 hours) - Enhanced rewards for premium members!"""
        try:
            if not await require_enrollment(ctx):
                return
            
            # Check if user is premium
            is_premium = False
            try:
                premium_cog = self.bot.get_cog('Premium')
                if premium_cog:
                    is_premium = await premium_cog.is_premium(ctx.author.id)
            except:
                pass
            
            if not is_premium:
                embed = discord.Embed(
                    title="⭐ Premium Feature",
                    description="This command is only available for **Premium** subscribers!",
                    color=0xE74C3C
                )
                embed.add_field(
                    name="Regular Daily",
                    value="Use `gdaily` for the regular daily rewards.",
                    inline=False
                )
                embed.add_field(
                    name="How to Subscribe",
                    value="Use `gpremium` to learn about Premium benefits!",
                    inline=False
                )
                return await send_embed(ctx, embed)
            
            await ensure_user_db(ctx.author.id)
            now = datetime.utcnow()

            async with aiosqlite.connect(DB_PATH) as db:
                # Check premium daily claim separately
                async with db.execute(
                    "SELECT last_claim, streak FROM daily_claims WHERE user_id = ? AND claim_type = 'premium'",
                    (ctx.author.id,),
                ) as cursor:
                    row = await cursor.fetchone()

                if row:
                    last_claim_str, streak = row
                    last_claim = datetime.fromisoformat(last_claim_str)
                    time_diff = now - last_claim

                    if time_diff < timedelta(hours=12):
                        time_left = timedelta(hours=12) - time_diff
                        hours = int(time_left.total_seconds() // 3600)
                        minutes = int((time_left.total_seconds() % 3600) // 60)

                        embed = discord.Embed(
                            title="<:bundle>1458318375590822068: Bundle Rewards",
                            description=f"<a:X_:1437951830393884788> You've already claimed your bundle rewards!\n\nCome back in **{hours}h {minutes}m**",
                            color=0xE74C3C,
                        )
                        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
                        embed.set_thumbnail(url=ctx.author.display_avatar.url)
                        embed.set_footer(
                            text=f"Current Streak: {streak} day{'s' if streak != 1 else ''}"
                        )
                        return await send_embed(ctx, embed)

                    if time_diff <= timedelta(hours=24):
                        streak += 1
                    else:
                        streak = 1
                else:
                    streak = 1

                display_streak = streak
                
                # Get user level for scaling
                from utils.database import get_account_level
                user_level, _, _ = await get_account_level(ctx.author.id)
                
                # Premium daily rewards: 3x base mora
                base_mora = 25000 * 3  # 75,000 base for premium
                
                # Level bonus: +500 Mora per level
                level_bonus = user_level * 500
                
                # Streak bonus: 5% per day, max 50% at 10 days
                streak_bonus_percent = min(streak * 5, 50)
                mora_reward = int((base_mora + level_bonus) * (1 + streak_bonus_percent / 100))

                user_data = await get_user_data(ctx.author.id)
                new_mora = user_data["mora"] + mora_reward

                await db.execute(
                    "UPDATE users SET mora = ? WHERE user_id = ?",
                    (new_mora, ctx.author.id),
                )

                # Create premium daily claim entry
                await db.execute(
                    """
                    INSERT OR REPLACE INTO daily_claims (user_id, last_claim, streak, claim_type)
                    VALUES (?, ?, ?, 'premium')
                """,
                    (ctx.author.id, now.isoformat(), display_streak),
                )
                
                # Grant +1 fishing energy
                from utils.database import add_fishing_energy
                await add_fishing_energy(ctx.author.id, 1, True)  # is_premium = True
                
                # Give random item (weighted)
                random_items = [
                    "lucky_dice", "streak", "shield", "lockpick",
                    "lucky_dice", "streak", "shield", "lockpick"  # Double weight for common items
                ]
                random_item = random.choice(random_items)
                
                await db.execute("""
                    INSERT INTO inventory (user_id, item_id, quantity)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, item_id) DO UPDATE SET
                        quantity = quantity + 1
                """, (ctx.author.id, random_item))
                
                # Give 2 chests from diamond, regular, and random
                chest_types = ["diamond", "regular", "random"]
                awarded_chests = []
                for _ in range(2):
                    chest_type = random.choice(chest_types)
                    awarded_chests.append(chest_type)
                    await db.execute("""
                        INSERT INTO inventory (user_id, item_id, quantity)
                        VALUES (?, ?, 1)
                        ON CONFLICT(user_id, item_id) DO UPDATE SET
                            quantity = quantity + 1
                    """, (ctx.author.id, chest_type))

                await db.commit()

            # Build header text
            header_text = f"**Streak:** {display_streak} - Next claim in 12 hours\n\n**Rewards:**"

            embed = discord.Embed(
                title="Bundle Claimed!", 
                description=header_text, 
                color=0xFFD700
            )

            embed.set_author(
                name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url
            )
            
            # Set bundle emoji as thumbnail
            import re
            bundle_emoji = "<:bundle:1458318375590822068>"
            match = re.match(r'<(a?):[^:]+:(\d+)>', bundle_emoji)
            if match:
                animated, emoji_id = match.groups()
                ext = 'gif' if animated else 'png'
                emoji_url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{ext}'
                embed.set_thumbnail(url=emoji_url)

            # Item name mapping (removed lucky_clover)
            item_names = {
                "lucky_dice": "<:dice:1457965149137670186> Lucky Dice",
                "streak": "<:streak:1457966635838214247> Hot Streak Card",
                "shield": "<:shield:1437977751897526303> Shield",
                "lockpick": "<:lock:1437977751826087978> Lockpick"
            }

            # Chest emoji mapping
            chest_emojis = {
                "diamond": "<:dimond:1437473169475764406>",
                "regular": "<:regular:1437473086571286699>",
                "random": "<:random:1437977751520018452>"
            }
            
            # Build chest display - stack duplicates
            from collections import Counter
            chest_counts = Counter(awarded_chests)
            chest_lines = []
            for chest_type, count in chest_counts.items():
                emoji = chest_emojis.get(chest_type, "")
                name = chest_type.capitalize()
                if count > 1:
                    chest_lines.append(f"{emoji} {name} Chest: {count}x")
                else:
                    chest_lines.append(f"{emoji} {name} Chest: 1x")

            # Organized rewards display
            rewards_lines = []
            for line in chest_lines:
                rewards_lines.append(line)
            rewards_lines.append(item_names.get(random_item, random_item) + ": 1x")
            rewards_lines.append("<:energy:1459189042574004224> Fishing Energy: +1")
            
            embed.add_field(
                name="\u200b",
                value="\n".join(rewards_lines),
                inline=False
            )
            
            # Bonuses section
            bonus_lines = []
            bonus_lines.append(f"Level {user_level}: {level_bonus:,} <:mora:1437958309255577681>")
            if display_streak > 1:
                streak_mora = int((base_mora + level_bonus) * (streak_bonus_percent / 100))
                bonus_lines.append(f"Streak {display_streak}: {streak_mora:,} <:mora:1437958309255577681>")
            
            embed.add_field(
                name="Bonuses",
                value="\n".join(bonus_lines),
                inline=False
            )

            embed.set_image(
                url="https://cdn.discordapp.com/attachments/1014919079154425917/1020348943902711868/gw_divider.png?ex=6914a181&is=69135001&hm=097a7ed105cff61e7dec6a9f894f9a27ead6950a765de7d50b0970c6e0586b09&"
            )
            
            await send_embed(ctx, embed)

        except Exception as e:
            from utils.logger import setup_logger

            logger = setup_logger("Daily")
            logger.error(f"Error in bundle command: {e}", exc_info=True)
            await ctx.send(
                "❌ Something went wrong while claiming your bundle rewards. Please try again in a moment."
            )

    @commands.command(name="resetdaily")
    async def reset_daily(self, ctx):
        """Reset your daily claim cooldown (Owner only)."""
        if ctx.author.id != 873464016217968640:
            return await ctx.send("You don't have permission to use this command.")

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Only delete regular daily claims, NOT premium bundle claims
                await db.execute(
                    "DELETE FROM daily_claims WHERE user_id = ? AND (claim_type = 'regular' OR claim_type IS NULL)", (ctx.author.id,)
                )
                await db.commit()

            await ctx.send(
                "<a:Check:1437951818452832318> Daily cooldown reset! You can claim again."
            )
        except Exception as e:
            from utils.logger import setup_logger

            logger = setup_logger("Daily")
            logger.error(f"Error resetting daily: {e}")
            await ctx.send("❌ Failed to reset cooldown. Please try again.")

    @commands.command(name="resetbundle")
    async def reset_bundle(self, ctx):
        """Reset your bundle claim cooldown (Owner only)."""
        if ctx.author.id != 873464016217968640:
            return await ctx.send("You don't have permission to use this command.")

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Only delete premium bundle claims, NOT regular daily claims
                await db.execute(
                    "DELETE FROM daily_claims WHERE user_id = ? AND claim_type = 'premium'", (ctx.author.id,)
                )
                await db.commit()

            await ctx.send(
                "<a:Check:1437951818452832318> Cooldown successfully reset."
            )
        except Exception as e:
            from utils.logger import setup_logger

            logger = setup_logger("Daily")
            logger.error(f"Error resetting bundle: {e}")
            await ctx.send("❌ Failed to reset cooldown. Please try again.")


async def setup(bot):
    await bot.add_cog(Daily(bot))
