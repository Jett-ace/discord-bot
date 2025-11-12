import aiosqlite
import discord
from discord.ext import commands
from discord import ui
from config import DB_PATH
from utils.database import get_user_achievements, get_account_level
from utils.achievements import get_achievement_meta
from utils.embed import send_embed


def _build_progress_bar(exp: int, needed: int, segments: int = 15) -> tuple[str, int]:
    progress = 0.0 if not needed else min(1.0, float(exp) / float(needed))
    filled = int(progress * segments)
    filled = max(0, min(segments, filled))
    # Ensure exactly 'segments' characters
    remaining = segments - filled
    bar_filled = '▰' * filled
    bar_empty = '▱' * remaining
    return f"{bar_filled}{bar_empty}", int(progress * 100)


class AchievementPaginator(ui.View):
    def __init__(self, pages, author_id, timeout=180):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.author_id = author_id
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= len(self.pages) - 1

    @ui.button(label="◀", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)


class Achievements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="achievements", aliases=["achs", "ach"])
    async def achievements(self, ctx):
        """List your achievements."""
        try:
            rows = await get_user_achievements(ctx.author.id)
            if not rows:
                await ctx.send("You have no achievements yet.")
                return

            embed = discord.Embed(title=f"{ctx.author.display_name}'s Achievements", color=0x8e44ad)
            embed.set_thumbnail(url=getattr(ctx.author, 'display_avatar', ctx.author).url)
            
            # Compact format - title only
            achievement_lines = []
            for r in rows:
                title = r.get('title') or r.get('key')
                desc = r.get('description') or ''
                # Single line format
                achievement_lines.append(f"**{title}** - {desc}")
            
            # Split into chunks
            chunk_size = 15
            for i in range(0, len(achievement_lines), chunk_size):
                chunk = achievement_lines[i:i+chunk_size]
                field_name = "Achievements" if i == 0 else f"Achievements (cont.)"
                embed.add_field(name=field_name, value="\n".join(chunk), inline=False)
            
            embed.set_footer(text=f"{len(rows)} achievement{'s' if len(rows) != 1 else ''} unlocked")
            await send_embed(ctx, embed)
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Achievements")
            logger.error(f"Error in achievements command: {e}", exc_info=True)
            await ctx.send("❌ Could not fetch your achievements right now. Please try again.")
    
    @commands.command(name="achievementslist", aliases=["achlist", "allach"])
    async def achievements_list(self, ctx):
        """Show all available achievements with progress and rewards."""
        try:
            # Auto-check and award any missing level achievements
            from utils.database import check_and_award_level_achievements
            await check_and_award_level_achievements(ctx.author.id)
            
            from utils.achievements import ACHIEVEMENTS
            user_achs = await get_user_achievements(ctx.author.id)
            unlocked_keys = {r.get('key') for r in user_achs}
            
            # Get user level for level achievements
            user_level, _, _ = await get_account_level(ctx.author.id)
            
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT COUNT(*) FROM fish_pets WHERE user_id=?", (ctx.author.id,)) as cur:
                    total_fish = (await cur.fetchone())[0]
                
                async with db.execute("""
                    SELECT fish_name, COUNT(*) FROM fish_pets 
                    WHERE user_id=? GROUP BY fish_name
                """, (ctx.author.id,)) as cur:
                    fish_species = await cur.fetchall()
                
                async with db.execute("SELECT streak FROM daily_claims WHERE user_id=?", (ctx.author.id,)) as cur:
                    row = await cur.fetchone()
                    daily_streak = row[0] if row else 0
            
            from utils.constants import fish_pool
            common_fish = [f['name'] for f in fish_pool if f['rarity'] == 'Common']
            rare_fish = [f['name'] for f in fish_pool if f['rarity'] == 'Rare']
            mythic_fish = [f['name'] for f in fish_pool if f['rarity'] == 'Mythic']
            
            caught_species = {name for name, _ in fish_species}
            caught_common = len([n for n in caught_species if n in common_fish])
            caught_rare = len([n for n in caught_species if n in rare_fish])
            caught_mythic = len([n for n in caught_species if n in mythic_fish])
            
            lines = []
            for key, meta in ACHIEVEMENTS.items():
                title = meta.get('title', key)
                desc = meta.get('description', '')
                reward = meta.get('reward', '')
                is_unlocked = key in unlocked_keys
                
                progress_bar = None
                if not is_unlocked:
                    if key == "level_20":
                        progress_bar = _build_progress_bar(user_level, 20, 15)
                    elif key == "level_50":
                        progress_bar = _build_progress_bar(user_level, 50, 15)
                    elif key == "level_100":
                        progress_bar = _build_progress_bar(user_level, 100, 15)
                    elif key == "fish_10":
                        progress_bar = _build_progress_bar(total_fish, 10, 15)
                    elif key == "fish_50":
                        progress_bar = _build_progress_bar(total_fish, 50, 15)
                    elif key == "fish_100":
                        progress_bar = _build_progress_bar(total_fish, 100, 15)
                    elif key == "all_common_fish":
                        progress_bar = _build_progress_bar(caught_common, len(common_fish), 15)
                    elif key == "all_rare_fish":
                        progress_bar = _build_progress_bar(caught_rare, len(rare_fish), 15)
                    elif key == "all_mythic_fish":
                        progress_bar = _build_progress_bar(caught_mythic, len(mythic_fish), 15)
                    elif key == "daily_streak_50":
                        progress_bar = _build_progress_bar(daily_streak, 50, 15)
                    elif key == "daily_streak_100":
                        progress_bar = _build_progress_bar(daily_streak, 100, 15)
                    elif key == "daily_streak_200":
                        progress_bar = _build_progress_bar(daily_streak, 200, 15)
                    elif key == "daily_streak_365":
                        progress_bar = _build_progress_bar(daily_streak, 365, 15)
                    elif key == "daily_streak_500":
                        progress_bar = _build_progress_bar(daily_streak, 500, 15)
                    elif key == "daily_streak_1000":
                        progress_bar = _build_progress_bar(daily_streak, 1000, 15)
                
                reward_text = f" | {reward}" if reward else ""
                
                if is_unlocked:
                    lines.append(f"<a:Check:1437951818452832318> **{title}**\n{desc}{reward_text}")
                elif progress_bar:
                    bar_str, pct = progress_bar
                    lines.append(f"🔒 **{title}**\n{desc}{reward_text}\n`{bar_str}` {pct}%")
                else:
                    lines.append(f"🔒 **{title}**\n{desc}{reward_text}")
            
            pages = []
            items_per_page = 6
            total_pages = (len(lines) + items_per_page - 1) // items_per_page
            
            for i in range(0, len(lines), items_per_page):
                page_lines = lines[i:i+items_per_page]
                embed = discord.Embed(title="📜 Achievement List", color=0xf39c12)
                embed.description = "Track your progress across all achievements!"
                
                embed.add_field(name="Achievements", value="\n\n".join(page_lines), inline=False)
                
                unlocked_count = len(unlocked_keys)
                total_count = len(ACHIEVEMENTS)
                page_num = (i // items_per_page) + 1
                embed.set_footer(text=f"{unlocked_count}/{total_count} unlocked • Page {page_num}/{total_pages}")
                
                pages.append(embed)
            
            if len(pages) == 1:
                await send_embed(ctx, pages[0])
            else:
                view = AchievementPaginator(pages, ctx.author.id)
                message = await send_embed(ctx, pages[0], view=view)
                view.message = message
                
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Achievements")
            logger.error(f"Error in achievementslist command: {e}", exc_info=True)
            await ctx.send("❌ Could not fetch the achievements list. Please try again.")

    @commands.command(name="badges")
    async def badges(self, ctx):
        """List your awarded badges."""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT badge_key FROM badges WHERE user_id=?", (ctx.author.id,)) as cur:
                    rows = await cur.fetchall()
            if not rows:
                await ctx.send("You have no badges yet.")
                return
            
            embed = discord.Embed(title=f"{ctx.author.display_name}'s Badges", color=0x3498db)
            embed.set_thumbnail(url=getattr(ctx.author, 'display_avatar', ctx.author).url)
            
            # Display badges (they already have emojis in them)
            badges = [r[0] for r in rows]
            badge_list = "\n".join([f"• {b}" for b in badges])
            embed.add_field(name="Badges", value=badge_list, inline=False)
            embed.set_footer(text=f"{len(rows)} badge{'s' if len(rows) != 1 else ''} earned")
            
            await send_embed(ctx, embed)
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Achievements")
            logger.error(f"Error in badges command: {e}", exc_info=True)
            await ctx.send("❌ Could not fetch your badges right now. Please try again.")

    @commands.command(name="checkachievements", aliases=["fixachievements"])
    async def check_achievements(self, ctx):
        """Check and award any missing level achievements based on your current level."""
        try:
            from utils.database import check_and_award_level_achievements
            
            # First, clean up old badges (level-based and old rank format)
            async with aiosqlite.connect(DB_PATH) as db:
                deleted = await db.execute(
                    "DELETE FROM badges WHERE user_id=? AND (badge_key LIKE '%Level%' OR badge_key LIKE '%Rank 1%' OR badge_key LIKE '%Rank 2%' OR badge_key LIKE '%Rank 3%' OR badge_key LIKE '%Rank 4%' OR badge_key LIKE '%Rank 5%' OR badge_key LIKE '%Rank 6%')",
                    (ctx.author.id,)
                )
                await db.commit()
            
            # Then check and award proper achievements and rank badges
            awarded = await check_and_award_level_achievements(ctx.author.id)
            
            if awarded > 0:
                await ctx.send(f"✅ Cleaned old badges and awarded {awarded} missing achievement(s) and rank badge(s)! Check `!badges` and `!achievementslist`.")
            else:
                await ctx.send("✅ All achievements and rank badges are up to date!")
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Achievements")
            logger.error(f"Error checking achievements: {e}", exc_info=True)
            await ctx.send("❌ Could not check achievements right now.")

    @commands.command(name="profile")
    async def profile(self, ctx):
        """Show a compact profile: level progress, rank, badges and achievements."""
        try:
            # Clean up old badges (level-based and old rank format)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "DELETE FROM badges WHERE user_id=? AND (badge_key LIKE '%Level%' OR badge_key LIKE '%Rank 1%' OR badge_key LIKE '%Rank 2%' OR badge_key LIKE '%Rank 3%' OR badge_key LIKE '%Rank 4%' OR badge_key LIKE '%Rank 5%' OR badge_key LIKE '%Rank 6%')",
                    (ctx.author.id,)
                )
                await db.commit()
            
            # Auto-check and award any missing level achievements and rank badges
            from utils.database import check_and_award_level_achievements
            await check_and_award_level_achievements(ctx.author.id)
            
            level, exp, needed = await get_account_level(ctx.author.id)
            stage = (level // 20) + 1
            rank = max(0, stage - 1)
            bar, pct = _build_progress_bar(exp, needed, 15)

            # Gather achievements and badges
            achs = await get_user_achievements(ctx.author.id)
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT badge_key FROM badges WHERE user_id=?", (ctx.author.id,)) as cur:
                    badge_rows = await cur.fetchall()

            # Build embed
            embed = discord.Embed(title=f"{ctx.author.display_name}'s Profile", color=0x6a0dad)
            embed.set_thumbnail(url=getattr(ctx.author, 'display_avatar', ctx.author).url)
            
            # Level info with medals based on rank (6 ranks total)
            rank_medal = ""
            if rank >= 5:
                rank_medal = " <a:Medal:1438198856910241842>"  # Gold medal for rank 5-6 (level 150-200)
            elif rank >= 3:
                rank_medal = " <a:Medal2:1438198813851652117>"  # Silver medal for rank 3-4 (level 100-149)
            elif rank >= 1:
                rank_medal = " <a:Medal3:1438198826799468604>"  # Bronze medal for rank 1-2 (level 20-99)
            
            embed.add_field(name="Level", value=f"🔷 **{level}**{rank_medal} (Rank {rank})", inline=True)
            embed.add_field(name="EXP", value=f"`{exp}/{needed}` ({pct}%)", inline=True)
            embed.add_field(name="Progress", value=f"`{bar}`", inline=False)

            # Badges - display first 8 (they already have emojis)
            if badge_rows:
                badges = [b[0] for b in badge_rows[:8]]
                badge_list = ", ".join(badges)
                if len(badge_rows) > 8:
                    badge_list += f" (+{len(badge_rows) - 8} more)"
                embed.add_field(name=f"Badges ({len(badge_rows)})", value=badge_list, inline=False)

            # Achievements - show count with trophy
            if achs:
                embed.add_field(name="Achievements", value=f"<a:Trophy:1438199339586424925> {len(achs)} owned", inline=False)

            await send_embed(ctx, embed)
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Achievements")
            logger.error(f"Error in profile command: {e}", exc_info=True)
            await ctx.send("❌ Could not build your profile right now. Please try again.")

async def setup(bot):
    await bot.add_cog(Achievements(bot))
