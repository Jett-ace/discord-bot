"""Daily Quest System - Rotating objectives for player engagement"""
import random
from datetime import datetime, timedelta
import discord
from discord.ext import commands
import aiosqlite

from config import DB_PATH
from utils.database import get_user_data, update_user_data, add_account_exp, add_chest_with_type, require_enrollment
from utils.embed import send_embed


QUEST_TYPES = {
    "wish": {
        "name": "Wish Upon a Star",
        "description": "Make {target} wishes",
        "icon": "🌟",
        "targets": [3, 5, 10],
        "rewards": {"mora": 3000, "exp": 300}
    },
    "fish": {
        "name": "Gone Fishing",
        "description": "Catch {target} fish",
        "icon": "🎣",
        "targets": [5, 10, 15],
        "rewards": {"mora": 2500, "exp": 250}
    },
    "chest": {
        "name": "Treasure Hunter",
        "description": "Open {target} chests",
        "icon": "📦",
        "targets": [3, 5, 8],
        "rewards": {"mora": 4000, "exp": 400}
    },
    "battle": {
        "name": "Warrior Spirit",
        "description": "Win {target} battles",
        "icon": "⚔️",
        "targets": [2, 3, 5],
        "rewards": {"mora": 5000, "exp": 500}
    },
    "daily": {
        "name": "Daily Routine",
        "description": "Claim your daily reward",
        "icon": "📅",
        "targets": [1],
        "rewards": {"mora": 2000, "exp": 200}
    },
    "dispatch": {
        "name": "Send Dispatches",
        "description": "Send {target} dispatches",
        "icon": "🗺️",
        "targets": [2, 3, 5],
        "rewards": {"mora": 3500, "exp": 350}
    }
}


class Quests(commands.Cog):
    """Daily Quest System"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        """Initialize database table"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS daily_quests (
                    user_id INTEGER,
                    quest_type TEXT,
                    target INTEGER,
                    progress INTEGER DEFAULT 0,
                    completed INTEGER DEFAULT 0,
                    date TEXT,
                    PRIMARY KEY (user_id, quest_type, date)
                )
            """)
            await db.commit()
    
    def _get_today_date(self):
        """Get today's date string"""
        return datetime.utcnow().strftime("%Y-%m-%d")
    
    async def _generate_daily_quests(self, user_id):
        """Generate 4 random quests for the day"""
        today = self._get_today_date()
        
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if quests already exist for today
            cursor = await db.execute(
                "SELECT COUNT(*) FROM daily_quests WHERE user_id = ? AND date = ?",
                (user_id, today)
            )
            count = (await cursor.fetchone())[0]
            
            if count > 0:
                return  # Already have quests
            
            # Select 4 random quest types
            quest_types = random.sample(list(QUEST_TYPES.keys()), min(4, len(QUEST_TYPES)))
            
            # Insert quests
            for quest_type in quest_types:
                target = random.choice(QUEST_TYPES[quest_type]["targets"])
                await db.execute(
                    """INSERT INTO daily_quests (user_id, quest_type, target, progress, completed, date)
                       VALUES (?, ?, ?, 0, 0, ?)""",
                    (user_id, quest_type, target, today)
                )
            
            await db.commit()
    
    async def _get_user_quests(self, user_id):
        """Get user's quests for today"""
        today = self._get_today_date()
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """SELECT quest_type, target, progress, completed 
                   FROM daily_quests 
                   WHERE user_id = ? AND date = ?""",
                (user_id, today)
            )
            return await cursor.fetchall()
    
    async def update_quest_progress(self, user_id, quest_type, amount=1):
        """Update progress for a specific quest type"""
        today = self._get_today_date()
        
        async with aiosqlite.connect(DB_PATH) as db:
            # Get current quest
            cursor = await db.execute(
                """SELECT target, progress, completed 
                   FROM daily_quests 
                   WHERE user_id = ? AND quest_type = ? AND date = ?""",
                (user_id, quest_type, today)
            )
            result = await cursor.fetchone()
            
            if not result:
                return  # No quest of this type today
            
            target, progress, completed = result
            
            if completed:
                return  # Already completed
            
            # Update progress
            new_progress = progress + amount
            new_completed = 1 if new_progress >= target else 0
            
            await db.execute(
                """UPDATE daily_quests 
                   SET progress = ?, completed = ? 
                   WHERE user_id = ? AND quest_type = ? AND date = ?""",
                (min(new_progress, target), new_completed, user_id, quest_type, today)
            )
            await db.commit()
            
            # Auto-claim if completed
            if new_completed and not completed:
                await self._auto_reward_quest(user_id, quest_type)
    
    async def _auto_reward_quest(self, user_id, quest_type):
        """Automatically reward quest completion"""
        rewards = QUEST_TYPES[quest_type]["rewards"]
        
        # Give rewards
        user_data = await get_user_data(user_id)
        await update_user_data(user_id, mora=user_data['mora'] + rewards["mora"])
        await add_account_exp(user_id, rewards["exp"], source="quest_complete")
    
    @commands.command(name="quests", aliases=["dailyquests", "dq"])
    async def quests(self, ctx):
        """View your daily quests and progress
        
        Complete quests to earn mora and EXP!
        Quests reset daily and are automatically completed when you reach the target.
        
        Usage: gquests
        """
        if not await require_enrollment(ctx):
            return
        # Generate quests if needed
        await self._generate_daily_quests(ctx.author.id)
        
        # Get quests
        quests = await self._get_user_quests(ctx.author.id)
        
        if not quests:
            return await ctx.send("❌ No quests available. Try again tomorrow!")
        
        embed = discord.Embed(
            title="📋 Daily Quests",
            description="Complete quests to earn rewards! Progress updates automatically.",
            color=0x3498DB
        )
        
        completed_count = 0
        
        for quest_type, target, progress, completed in quests:
            quest_info = QUEST_TYPES[quest_type]
            
            # Progress bar - Dots style
            bar_length = 10
            filled = int((progress / target) * bar_length)
            bar = "●" * filled + "○" * (bar_length - filled)
            
            # Status
            if completed:
                status = "✅ COMPLETED"
                completed_count += 1
            else:
                status = f"{progress}/{target}"
            
            # Rewards
            rewards = quest_info["rewards"]
            reward_text = f"💰 {rewards['mora']:,} <:mora:1437958309255577681> - <:exp:1437553839359397928> {rewards['exp']} EXP"
            
            embed.add_field(
                name=f"{quest_info['icon']} {quest_info['name']}",
                value=f"{quest_info['description'].format(target=target)}\n"
                      f"`{bar}` {status}\n"
                      f"{reward_text}",
                inline=False
            )
        
        embed.set_footer(text=f"Completed: {completed_count}/{len(quests)} - Resets daily at 00:00 UTC")
        
        await send_embed(ctx, embed)
    
    @commands.command(name="questprogress", aliases=["qp"])
    async def quest_progress(self, ctx):
        """Quick view of quest completion status
        
        Shows a compact summary of your daily quest progress.
        
        Usage: gquestprogress
        """
        if not await require_enrollment(ctx):
            return
        await self._generate_daily_quests(ctx.author.id)
        quests = await self._get_user_quests(ctx.author.id)
        
        if not quests:
            return await ctx.send("❌ No quests available.")
        
        completed = sum(1 for q in quests if q[3] == 1)
        total = len(quests)
        
        progress_text = []
        for quest_type, target, progress, is_completed in quests:
            quest_info = QUEST_TYPES[quest_type]
            status = "✅" if is_completed else f"{progress}/{target}"
            progress_text.append(f"{quest_info['icon']} {quest_info['name']}: {status}")
        
        embed = discord.Embed(
            title=f"📊 Quest Progress ({completed}/{total})",
            description="\n".join(progress_text),
            color=0x2ECC71 if completed == total else 0x3498DB
        )
        
        await send_embed(ctx, embed)


async def setup(bot):
    await bot.add_cog(Quests(bot))
