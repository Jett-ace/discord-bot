import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime, timedelta
import random
from config import DB_PATH
from utils.database import ensure_user_db, get_user_data
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

    @commands.command(name="daily")
    async def daily(self, ctx):
        try:
            await ensure_user_db(ctx.author.id)
            now = datetime.utcnow()
            
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT last_claim, streak FROM daily_claims WHERE user_id = ?",
                    (ctx.author.id,)
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
                            color=0xe74c3c
                        )
                        embed.set_thumbnail(url=ctx.author.display_avatar.url)
                        embed.set_footer(text=f"Current Streak: {streak} day{'s' if streak != 1 else ''}")
                        return await send_embed(ctx, embed)
                    
                    if time_diff <= timedelta(hours=48):
                        streak += 1
                    else:
                        streak = 1
                else:
                    streak = 1
                
                display_streak = streak
                reward_streak = min(streak, 5)
                num_chests = reward_streak
                mora_reward = 10000
                tidecoin_reward = 5
                
                chest_types = ['common', 'exquisite', 'precious', 'luxurious']
                weights = [65, 20, 10, 5]
                
                claimed_chests = {}
                for _ in range(num_chests):
                    chest = random.choices(chest_types, weights=weights)[0]
                    claimed_chests[chest] = claimed_chests.get(chest, 0) + 1
                
                user_data = await get_user_data(ctx.author.id)
                new_mora = user_data['mora'] + mora_reward
                new_dust = user_data['dust'] + tidecoin_reward
                
                await db.execute(
                    "UPDATE users SET mora = ?, dust = ? WHERE user_id = ?",
                    (new_mora, new_dust, ctx.author.id)
                )
                
                await db.execute(
                    "INSERT OR IGNORE INTO chest_inventory (user_id, common, exquisite, precious, luxurious) VALUES (?, ?, ?, ?, ?)",
                    (ctx.author.id, 0, 0, 0, 0)
                )
                
                for chest_type, amount in claimed_chests.items():
                    await db.execute(
                        f"UPDATE chest_inventory SET {chest_type} = {chest_type} + ? WHERE user_id = ?",
                        (amount, ctx.author.id)
                    )
                
                await db.execute("""
                    INSERT OR REPLACE INTO daily_claims (user_id, last_claim, streak)
                    VALUES (?, ?, ?)
                """, (ctx.author.id, now.isoformat(), display_streak))
                
                await db.commit()
            
            achievements_earned = []
            if display_streak == 50:
                achievements_earned.append("daily_streak_50")
            elif display_streak == 100:
                achievements_earned.append("daily_streak_100")
            elif display_streak == 200:
                achievements_earned.append("daily_streak_200")
            elif display_streak == 365:
                achievements_earned.append("daily_streak_365")
            elif display_streak == 500:
                achievements_earned.append("daily_streak_500")
            elif display_streak == 1000:
                achievements_earned.append("daily_streak_1000")
            
            if achievements_earned:
                from utils.achievements import get_achievement_meta
                from utils.database import award_achievement
                
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "INSERT OR IGNORE INTO chest_inventory (user_id, common, exquisite, precious, luxurious) VALUES (?, ?, ?, ?, ?)",
                        (ctx.author.id, 0, 0, 0, 0)
                    )
                    
                    for ach_key in achievements_earned:
                        # Use the centralized award_achievement function
                        meta = get_achievement_meta(ach_key)
                        try:
                            await award_achievement(
                                ctx.author.id, 
                                ach_key, 
                                meta.get('title', ach_key), 
                                meta.get('description', '')
                            )
                            
                            # Award bonus chests for daily streak achievements
                            for _ in range(5):
                                chest = random.choices(chest_types, weights=weights)[0]
                                claimed_chests[chest] = claimed_chests.get(chest, 0) + 1
                            
                            for chest_type, amount in claimed_chests.items():
                                await db.execute(
                                    f"UPDATE chest_inventory SET {chest_type} = {chest_type} + ? WHERE user_id = ?",
                                    (amount, ctx.author.id)
                                )
                        except Exception as e:
                            print(f"Error awarding achievement {ach_key}: {e}")
                    
                    await db.commit()
            
            # Build header text
            header_text = f"Current Streak: {display_streak} day{'s' if display_streak != 1 else ''} • Come back in 24 hours!\n\n"
            if achievements_earned:
                from utils.achievements import get_achievement_meta
                ach_title = get_achievement_meta(achievements_earned[0]).get('title', 'Achievement')
                header_text = f"🏆 Achievement Unlocked: {ach_title}!\n" + header_text
            
            header_text += "<a:Check:1437951818452832318> You've claimed your daily rewards!"
            
            embed = discord.Embed(
                title="Daily Rewards Claimed!",
                description=header_text,
                color=0x2ecc71
            )
            
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            
            chest_icons = {
                'common': '<:cajitadelexplorador:1437473147833286676>',
                'exquisite': '<:cajitaplatino:1437473086571286699>',
                'precious': '<:cajitapremium:1437473125095837779>',
                'luxurious': '<:cajitadiamante:1437473169475764406>'
            }
            
            rewards_text = ""
            for chest_type, amount in claimed_chests.items():
                icon = chest_icons.get(chest_type, '📦')
                rewards_text += f"{icon} {amount}x {chest_type.capitalize()} Chest\n"
            
            rewards_text += f"\n<:mora:1437958309255577681> {mora_reward:,} Mora\n"
            rewards_text += f"<:mora:1437480155952975943> {tidecoin_reward} Tide Coins"
            
            embed.add_field(
                name="<:gem1_72x72:1437942609849876680> Rewards Received",
                value=rewards_text,
                inline=False
            )
            
            if display_streak > 1:
                bonus_text = f"**Streak Bonus Active!**\n"
                if reward_streak < 5:
                    bonus_text += f"+{reward_streak - 1} bonus chest{'s' if reward_streak > 2 else ''}!"
                else:
                    bonus_text += f"Maximum bonus reached! (+4 chests)"
                
                embed.add_field(
                    name="Daily Streak",
                    value=bonus_text,
                    inline=False
                )
            
            embed.set_image(url="https://cdn.discordapp.com/attachments/1014919079154425917/1020348943902711868/gw_divider.png?ex=6914a181&is=69135001&hm=097a7ed105cff61e7dec6a9f894f9a27ead6950a765de7d50b0970c6e0586b09&")
            await send_embed(ctx, embed)
        
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Daily")
            logger.error(f"Error in daily command: {e}", exc_info=True)
            await ctx.send("❌ Something went wrong while claiming your daily rewards. Please try again in a moment.")

    @commands.command(name="resetdaily")
    async def reset_daily(self, ctx):
        """Reset your daily claim cooldown (Owner only)."""
        if ctx.author.id != 873464016217968640:
            return await ctx.send("You don't have permission to use this command.")
        
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM daily_claims WHERE user_id = ?", (ctx.author.id,))
                await db.commit()
            
            await ctx.send("<a:Check:1437951818452832318> Daily cooldown reset! You can claim again.")
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Daily")
            logger.error(f"Error resetting daily: {e}")
            await ctx.send("❌ Failed to reset cooldown. Please try again.")


async def setup(bot):
    await bot.add_cog(Daily(bot))
