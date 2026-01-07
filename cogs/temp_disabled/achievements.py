import aiosqlite
import discord
from discord.ext import commands
from discord import ui
from config import DB_PATH
from utils.database import get_user_achievements, get_account_level, get_user_data, get_user_pulls, get_user_data, get_user_pulls, require_enrollment
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
        """List your achievements organized by category."""
        if not await require_enrollment(ctx):
            return
        try:
            rows = await get_user_achievements(ctx.author.id)
            if not rows:
                embed = discord.Embed(
                    title="🏆 Achievements",
                    description="You haven't unlocked any achievements yet!\n\nUse `gachievementslist` to see all available achievements.",
                    color=0x95a5a6
                )
                embed.set_thumbnail(url=ctx.author.display_avatar.url)
                return await send_embed(ctx, embed)

            # Organize by category
            from utils.achievements import ACHIEVEMENTS, ACHIEVEMENT_CATEGORIES, get_category_emoji
            
            categorized = {}
            for r in rows:
                key = r.get('key')
                meta = ACHIEVEMENTS.get(key, {})
                category = meta.get('category', 'special')
                
                if category not in categorized:
                    categorized[category] = []
                
                title = r.get('title') or key
                desc = r.get('description') or ''
                reward = meta.get('reward', '')
                
                # Format: emoji + title + description
                cat_emoji = get_category_emoji(category)
                line = f"{cat_emoji} **{title}**"
                if desc:
                    line += f" - {desc}"
                if reward:
                    line += f"\n  └ *Reward: {reward}*"
                
                categorized[category].append(line)
            
            embed = discord.Embed(
                title=f"🏆 {ctx.author.display_name}'s Achievements",
                description=f"You've unlocked **{len(rows)}** achievements!",
                color=0xf39c12
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            
            # Add fields by category
            for cat_key, achs in categorized.items():
                cat_info = ACHIEVEMENT_CATEGORIES.get(cat_key, {"name": "Other", "emoji": "🎯"})
                cat_name = cat_info["name"]
                
                # Split long categories
                chunk_size = 5
                for i in range(0, len(achs), chunk_size):
                    chunk = achs[i:i+chunk_size]
                    field_name = cat_name if i == 0 else f"{cat_name} (cont.)"
                    embed.add_field(name=field_name, value="\n\n".join(chunk), inline=False)
            
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
        if not await require_enrollment(ctx):
            return
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
            
            # Build simple achievement list without categories
            lines = []
            for key, meta in ACHIEVEMENTS.items():
                title = meta.get('title', key)
                desc = meta.get('description', '')
                reward = meta.get('reward', '')
                is_unlocked = key in unlocked_keys
                
                # Calculate progress bar for all trackable achievements
                # If unlocked, show 100% complete bar
                progress_bar = None
                if is_unlocked:
                    # For unlocked achievements, show full progress
                    if key.startswith("level_") or key.startswith("fish_") or key.startswith("all_") or key.startswith("daily_streak_"):
                        progress_bar = _build_progress_bar(100, 100, 15)
                else:
                    # For locked achievements, show actual progress
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
                
                reward_text = f" | *{reward}*" if reward else ""
                
                if progress_bar:
                    bar_str, pct = progress_bar
                    icon = "<a:Check:1437951818452832318>" if is_unlocked else "🔒"
                    lines.append(f"{icon} **{title}** - {desc}{reward_text}\n`{bar_str}` {pct}%")
                else:
                    if is_unlocked:
                        lines.append(f"<a:Check:1437951818452832318> **{title}** - {desc}{reward_text}")
                    else:
                        lines.append(f"🔒 **{title}** - {desc}{reward_text}")
            
            pages = []
            items_per_page = 8
            total_pages = (len(lines) + items_per_page - 1) // items_per_page
            
            for i in range(0, len(lines), items_per_page):
                page_lines = lines[i:i+items_per_page]
                embed = discord.Embed(title="📜 Achievement List", color=0xf39c12)
                embed.description = "\n\n".join(page_lines)
                
                unlocked_count = len(unlocked_keys)
                total_count = len(ACHIEVEMENTS)
                page_num = (i // items_per_page) + 1
                embed.set_footer(text=f"{unlocked_count}/{total_count} unlocked - Page {page_num}/{total_pages}")
                
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
        if not await require_enrollment(ctx):
            return
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
            badge_list = "\n".join([f"- {b}" for b in badges])
            embed.add_field(name="Badges", value=badge_list, inline=False)
            embed.set_footer(text=f"{len(rows)} badge{'s' if len(rows) != 1 else ''} earned")
            
            await send_embed(ctx, embed)
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Achievements")
            logger.error(f"Error in badges command: {e}", exc_info=True)
            await ctx.send("❌ Could not fetch your badges right now. Please try again.")

    @commands.command(name="profile", aliases=["p", "me"])
    async def profile(self, ctx, member: discord.Member = None):
        """Show detailed profile with stats, cards, weapons, and battle records."""
        if not await require_enrollment(ctx):
            return
        try:
            target = member or ctx.author
            
            # Clean up old badges (level-based and old rank format)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "DELETE FROM badges WHERE user_id=? AND (badge_key LIKE '%Level%' OR badge_key LIKE '%Rank 1%' OR badge_key LIKE '%Rank 2%' OR badge_key LIKE '%Rank 3%' OR badge_key LIKE '%Rank 4%' OR badge_key LIKE '%Rank 5%' OR badge_key LIKE '%Rank 6%')",
                    (target.id,)
                )
                await db.commit()
            
            # Auto-check and award any missing level achievements and rank badges
            from utils.database import check_and_award_level_achievements
            await check_and_award_level_achievements(target.id)
            
            # Get user data
            user_data = await get_user_data(target.id)
            level, exp, needed = await get_account_level(target.id)
            stage = (level // 20) + 1
            rank = max(0, stage - 1)
            
            # Get rank names
            rank_names = ["Newbie", "Explorer", "Adventurer", "Captain", "Elite", "Champion", "Legend"]
            rank_name = rank_names[min(rank, len(rank_names) - 1)]
            
            # Get card counts
            pulls = await get_user_pulls(target.id)
            total_cards = len(pulls)
            
            # Get battle stats
            battle_cog = self.bot.get_cog('Battle')
            winstreak = battle_cog.winstreaks.get(target.id, 0) if battle_cog else 0
            
            # Get badges
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT badge_key FROM badges WHERE user_id=?", (target.id,)) as cur:
                    badge_rows = await cur.fetchall()
            
            # Get achievements
            achs = await get_user_achievements(target.id)
            
            # Build embed
            from cogs.settings import get_user_embed_color
            color = await get_user_embed_color(target.id, "profile", 0x6a0dad)
            embed = discord.Embed(
                title=f"{target.display_name}'s Profile:",
                color=color
            )
            embed.set_thumbnail(url=getattr(target, 'display_avatar', target).url)
            
            # Account section with badge display
            rank_emoji = "⚔️" if rank >= 5 else "🛡️" if rank >= 3 else "✨"
            # Display all badges side by side (just emoji, no names)
            badge_display = " ".join([b[0] for b in badge_rows]) if badge_rows else "None"
            account_info = (
                f"{rank_emoji} **Account:**\n"
                f"➣ Rank: {rank_name}\n"
                f"➣ Level: {level} ({exp}/{needed})\n"
                f"➣ Badges: {badge_display}"
            )
            embed.add_field(name="\u200b", value=account_info, inline=False)
            
            # Balance section
            balance_info = (
                f"💰 **Balance:**\n"
                f"➣ Mora: {user_data.get('mora', 0):,}\n"
                f"➣ Tide Coins: {user_data.get('dust', 0):,}"
            )
            embed.add_field(name="\u200b", value=balance_info, inline=False)
            
            # Cards section
            cards_pulled = user_data.get('total_pulls', 0)
            cards_info = (
                f"🎴 **Cards:**\n"
                f"➣ Total Cards Owned: {total_cards}\n"
                f"➣ Cards Pulled: {cards_pulled}"
            )
            embed.add_field(name="\u200b", value=cards_info, inline=False)
            
            # Fights section
            fights_info = (
                f"⚔️ **Fights:**\n"
                f"➣ Winstreak: {winstreak}"
            )
            embed.add_field(name="\u200b", value=fights_info, inline=False)
            
            # Achievements section
            achievements_info = (
                f"<a:Trophy:1438199339586424925> **Achievements:**\n"
                f"➣ Total Unlocked: {len(achs)}"
            )
            embed.add_field(name="\u200b", value=achievements_info, inline=False)

            await send_embed(ctx, embed)
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Achievements")
            logger.error(f"Error in profile command: {e}", exc_info=True)
            await ctx.send("❌ Could not build your profile right now. Please try again.")

async def setup(bot):
    await bot.add_cog(Achievements(bot))
