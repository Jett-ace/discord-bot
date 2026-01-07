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
                    user_id INTEGER PRIMARY KEY,
                    last_claim TEXT NOT NULL,
                    streak INTEGER DEFAULT 1
                )
            """)
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
                    "SELECT last_claim, streak FROM daily_claims WHERE user_id = ?",
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
                    INSERT OR REPLACE INTO daily_claims (user_id, last_claim, streak)
                    VALUES (?, ?, ?)
                """,
                    (ctx.author.id, now.isoformat(), display_streak),
                )

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

            # Build header text
            header_text = f"Current Streak: {display_streak} day{'s' if display_streak != 1 else ''} - Come back in 24 hours!\n\n"
            if achievements_earned:
                from utils.achievements import get_achievement_meta

                ach_title = get_achievement_meta(achievements_earned[0]).get(
                    "title", "Achievement"
                )
                header_text = f"🏆 Achievement Unlocked: {ach_title}!\n" + header_text

            header_text += (
                "<a:Check:1437951818452832318> You've claimed your daily rewards!"
            )

            embed = discord.Embed(
                title="Daily Rewards Claimed!", description=header_text, color=0x2ECC71
            )

            embed.set_author(
                name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)

            rewards_text = f"<:mora:1437958309255577681> {mora_reward:,} Mora"
            if is_premium:
                rewards_text += " (3x Premium)"

            embed.add_field(
                name="<:gem1_72x72:1437942609849876680> Rewards Received",
                value=rewards_text,
                inline=False,
            )

            # Show bonuses
            bonus_text = f"**Level {user_level}:** +{level_bonus:,} <:mora:1437958309255577681>\n"
            if display_streak > 1:
                streak_bonus_percent = min(display_streak * 5, 50)
                bonus_text += f"**Streak Bonus: +{streak_bonus_percent}%**"
            
            embed.add_field(name="Bonuses", value=bonus_text, inline=False)

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
            logger.error(f"Error in daily command: {e}", exc_info=True)
            await ctx.send(
                "❌ Something went wrong while claiming your daily rewards. Please try again in a moment."
            )

    @commands.command(name="resetdaily")
    async def reset_daily(self, ctx):
        """Reset your daily claim cooldown (Owner only)."""
        if ctx.author.id != 873464016217968640:
            return await ctx.send("You don't have permission to use this command.")

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "DELETE FROM daily_claims WHERE user_id = ?", (ctx.author.id,)
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


async def setup(bot):
    await bot.add_cog(Daily(bot))
