import aiosqlite
import discord
from discord.ext import commands
from discord import ui
from config import DB_PATH
from utils.database import get_user_data, get_account_level, require_enrollment, get_game_stat
from utils.embed import send_embed


def _build_progress_bar(current: int, needed: int, segments: int = 15) -> tuple[str, int]:
    """Build a progress bar for achievements."""
    progress = 0.0 if not needed else min(1.0, float(current) / float(needed))
    filled = int(progress * segments)
    filled = max(0, min(segments, filled))
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

    @commands.command(name="profile", aliases=["p", "level"])
    async def profile(self, ctx, member: discord.Member = None):
        """Show your profile with level, balance, and achievement count."""
        if not await require_enrollment(ctx):
            return
        try:
            target = member or ctx.author
            
            # Get user data
            user_data = await get_user_data(target.id)
            level, exp, needed = await get_account_level(target.id)
            
            # Get achievements count
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT COUNT(*) FROM achievements WHERE user_id=?", (target.id,)) as cur:
                    ach_count = (await cur.fetchone())[0]
                
                # Get game stats
                cursor = await db.execute("SELECT * FROM game_stats WHERE user_id=?", (target.id,))
                stats_row = await cursor.fetchone()
                
                if stats_row:
                    # Calculate totals
                    total_wins = (stats_row[1] or 0) + (stats_row[3] or 0) + (stats_row[5] or 0) + (stats_row[7] or 0) + (stats_row[11] or 0)  # rps, c4, ttt, bj, cf wins
                    total_plays = (stats_row[2] or 0) + (stats_row[4] or 0) + (stats_row[6] or 0) + (stats_row[8] or 0) + (stats_row[10] or 0) + (stats_row[12] or 0) + (stats_row[14] or 0)  # all plays
                    total_losses = total_plays - total_wins if total_plays > total_wins else 0
                    win_rate = (total_wins / total_plays * 100) if total_plays > 0 else 0
                else:
                    total_wins = 0
                    total_plays = 0
                    total_losses = 0
                    win_rate = 0
            
            # Get premium status
            premium_cog = self.bot.get_cog('Premium')
            is_premium = False
            premium_tier = "Free"
            custom_badge = ""
            badge_display = ""
            if premium_cog:
                is_premium = await premium_cog.is_premium(target.id)
                if is_premium:
                    premium_tier = "Premium"
                    # Get custom badge if set
                    badge = await premium_cog.get_custom_badge(target.id)
                    if badge:
                        custom_badge = f" {badge}"
                        badge_display = f"\n**Badge:** {badge}"
            
            # Get bank card tier
            bank_cog = self.bot.get_cog('Bank')
            card_tier = 0
            card_display = ""
            if bank_cog:
                card_tier = await bank_cog.get_user_card_tier(target.id)
                card_names = ["", "<:platinum:1457410519534403635> Platinum", "<a:gold:1457409675963138205> Gold"]
                if card_tier > 0:
                    card_display = f" | {card_names[card_tier]}"
            
            # Build embed with custom badge in title
            embed = discord.Embed(
                title=f"{target.display_name}'s Profile{custom_badge}",
                color=0xf39c12
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            
            # Level section with progress bar
            progress = (exp / needed) * 100 if needed > 0 else 0
            bar_length = 10
            filled = int((progress / 100) * bar_length)
            bar = "▰" * filled + "▱" * (bar_length - filled)
            
            level_info = (
                f"**Level:** {level}\n"
                f"**XP:** {exp:,}/{needed:,}\n"
                f"`{bar}` {progress:.1f}%"
            )
            embed.add_field(name="Progress", value=level_info, inline=False)
            
            # Balance section with badge
            balance_info = (
                f"**Wallet:** {user_data.get('mora', 0):,} <:mora:1437958309255577681>\n"
                f"**Account:** {premium_tier}{card_display}{badge_display}"
            )
            embed.add_field(name="Balance", value=balance_info, inline=False)
            
            # Achievements section
            from utils.achievements import ACHIEVEMENTS
            total_achs = len(ACHIEVEMENTS)
            achievements_info = (
                f"**Unlocked:** {ach_count}/{total_achs}\n"
                f"Use `gachievements` to view all!"
            )
            embed.add_field(name="Achievements", value=achievements_info, inline=False)
            
            # Game Stats section
            stats_info = (
                f"**Total Games:** {total_plays:,}\n"
                f"**Wins:** {total_wins:,}\n"
                f"**Losses:** {total_losses:,}\n"
                f"**Win Rate:** {win_rate:.1f}%"
            )
            embed.add_field(name="Statistics", value=stats_info, inline=False)
            
            await send_embed(ctx, embed)
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Achievements")
            logger.error(f"Error in profile command: {e}", exc_info=True)
            await ctx.send("❌ Could not build your profile right now. Please try again.")

    @commands.command(name="achievements", aliases=["ach", "achlist", "achievementslist", "allach"])
    async def achievements_list(self, ctx):
        """Show all available achievements with their rewards and progress bars."""
        if not await require_enrollment(ctx):
            return
        try:
            from utils.achievements import ACHIEVEMENTS, ACHIEVEMENT_CATEGORIES
            
            # Get unlocked achievements
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT ach_key FROM achievements WHERE user_id=?",
                    (ctx.author.id,)
                ) as cur:
                    rows = await cur.fetchall()
            unlocked_keys = {r[0] for r in rows}
            
            # Get user stats for progress tracking
            async with aiosqlite.connect(DB_PATH) as db:
                # Get daily streak
                cursor = await db.execute("SELECT streak FROM daily_claims WHERE user_id=?", (ctx.author.id,))
                row = await cursor.fetchone()
                daily_streak = row[0] if row else 0
                
                # Get bank deposits
                cursor = await db.execute("SELECT deposited_amount FROM user_bank_deposits WHERE user_id=?", (ctx.author.id,))
                row = await cursor.fetchone()
                bank_total = row[0] if row and row[0] else 0
            
            # Get game stats
            rps_wins = await get_game_stat(ctx.author.id, 'rps_wins')
            connect4_wins = await get_game_stat(ctx.author.id, 'connect4_wins')
            tictactoe_wins = await get_game_stat(ctx.author.id, 'tictactoe_wins')
            blackjack_wins = await get_game_stat(ctx.author.id, 'blackjack_wins')
            blackjack_naturals = await get_game_stat(ctx.author.id, 'blackjack_naturals')
            slots_plays = await get_game_stat(ctx.author.id, 'slots_plays')
            slots_jackpots = await get_game_stat(ctx.author.id, 'slots_jackpots')
            coinflip_wins = await get_game_stat(ctx.author.id, 'coinflip_wins')
            coinflip_streak = await get_game_stat(ctx.author.id, 'coinflip_streak')
            mines_max_tiles = await get_game_stat(ctx.author.id, 'mines_max_tiles')
            multiplayer_games = await get_game_stat(ctx.author.id, 'multiplayer_games')
            total_earned = await get_game_stat(ctx.author.id, 'total_earned')
            max_wallet = await get_game_stat(ctx.author.id, 'max_wallet')
            rob_success = await get_game_stat(ctx.author.id, 'rob_success')
            
            # Build achievement list by category
            pages = []
            
            for cat_key, cat_info in ACHIEVEMENT_CATEGORIES.items():
                # Get achievements in this category
                cat_achs = []
                for key, meta in ACHIEVEMENTS.items():
                    if meta.get('category') == cat_key:
                        cat_achs.append((key, meta))
                
                if not cat_achs:
                    continue
                
                # Build lines for this category
                lines = []
                for key, meta in cat_achs:
                    title = meta.get('title', key)
                    desc = meta.get('description', '')
                    reward = meta.get('reward', '')
                    is_unlocked = key in unlocked_keys
                    
                    # Calculate progress for trackable achievements
                    progress_bar = None
                    if is_unlocked:
                        # Show full bar for unlocked
                        progress_bar = _build_progress_bar(100, 100, 15)
                    else:
                        # Show actual progress for locked achievements
                        if key == "daily_streak_10":
                            progress_bar = _build_progress_bar(daily_streak, 10, 15)
                        elif key == "daily_streak_20":
                            progress_bar = _build_progress_bar(daily_streak, 20, 15)
                        elif key == "daily_streak_30":
                            progress_bar = _build_progress_bar(daily_streak, 30, 15)
                        elif key == "daily_streak_50":
                            progress_bar = _build_progress_bar(daily_streak, 50, 15)
                        elif key == "daily_streak_100":
                            progress_bar = _build_progress_bar(daily_streak, 100, 15)
                        elif key == "rps_win_10":
                            progress_bar = _build_progress_bar(rps_wins, 10, 15)
                        elif key == "rps_win_50":
                            progress_bar = _build_progress_bar(rps_wins, 50, 15)
                        elif key == "rps_win_100":
                            progress_bar = _build_progress_bar(rps_wins, 100, 15)
                        elif key == "play_multiplayer_50":
                            progress_bar = _build_progress_bar(multiplayer_games, 50, 15)
                        elif key == "play_multiplayer_100":
                            progress_bar = _build_progress_bar(multiplayer_games, 100, 15)
                        elif key == "play_multiplayer_250":
                            progress_bar = _build_progress_bar(multiplayer_games, 250, 15)
                        elif key == "connect4_win_10":
                            progress_bar = _build_progress_bar(connect4_wins, 10, 15)
                        elif key == "connect4_win_25":
                            progress_bar = _build_progress_bar(connect4_wins, 25, 15)
                        elif key == "tictactoe_win_10":
                            progress_bar = _build_progress_bar(tictactoe_wins, 10, 15)
                        elif key == "tictactoe_win_25":
                            progress_bar = _build_progress_bar(tictactoe_wins, 25, 15)
                        elif key == "blackjack_win_10":
                            progress_bar = _build_progress_bar(blackjack_wins, 10, 15)
                        elif key == "blackjack_win_50":
                            progress_bar = _build_progress_bar(blackjack_wins, 50, 15)
                        elif key == "blackjack_natural_10":
                            progress_bar = _build_progress_bar(blackjack_naturals, 10, 15)
                        elif key == "slots_jackpot_1":
                            progress_bar = _build_progress_bar(slots_jackpots, 1, 15)
                        elif key == "slots_play_100":
                            progress_bar = _build_progress_bar(slots_plays, 100, 15)
                        elif key == "coinflip_win_10":
                            progress_bar = _build_progress_bar(coinflip_wins, 10, 15)
                        elif key == "coinflip_streak_5":
                            progress_bar = _build_progress_bar(coinflip_streak, 5, 15)
                        elif key == "mines_reveal_15":
                            progress_bar = _build_progress_bar(mines_max_tiles, 15, 15)
                        elif key == "earn_1m":
                            progress_bar = _build_progress_bar(total_earned, 1000000, 15)
                        elif key == "earn_10m":
                            progress_bar = _build_progress_bar(total_earned, 10000000, 15)
                        elif key == "wallet_500k":
                            progress_bar = _build_progress_bar(max_wallet, 500000, 15)
                        elif key == "bank_deposit_1m":
                            progress_bar = _build_progress_bar(bank_total, 1000000, 15)
                        elif key == "rob_success_10":
                            progress_bar = _build_progress_bar(rob_success, 10, 15)
                        elif key == "rob_success_50":
                            progress_bar = _build_progress_bar(rob_success, 50, 15)
                    
                    icon = "<a:Check:1437951818452832318>" if is_unlocked else "🔒"
                    line = f"{icon} **{title}**"
                    if desc:
                        line += f"\n└ {desc}"
                    if reward:
                        line += f"\n└ *{reward}*"
                    if progress_bar:
                        bar_str, pct = progress_bar
                        line += f"\n`{bar_str}` {pct}%"
                    
                    lines.append(line)
                
                # Split into pages if needed
                items_per_page = 6
                for i in range(0, len(lines), items_per_page):
                    page_lines = lines[i:i+items_per_page]
                    embed = discord.Embed(
                        title=f"<a:Trophy:1438199339586424925> {cat_info['name']}",
                        description="\n\n".join(page_lines),
                        color=0xf39c12
                    )
                    
                    unlocked_count = len(unlocked_keys)
                    total_count = len(ACHIEVEMENTS)
                    embed.set_footer(text=f"{unlocked_count}/{total_count} unlocked")
                    
                    pages.append(embed)
            
            if len(pages) == 0:
                await ctx.send("No achievements found.")
                return
            elif len(pages) == 1:
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

    @commands.command(name="purgeachievements", hidden=True)
    async def purge_achievements(self, ctx):
        """Purge all old achievements from the database (Owner only)."""
        if ctx.author.id != 873464016217968640:
            return await ctx.send("You don't have permission to use this command.")
        
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Get count before deletion
                cursor = await db.execute("SELECT COUNT(*) FROM achievements")
                before_count = (await cursor.fetchone())[0]
                
                # Delete all achievements
                await db.execute("DELETE FROM achievements")
                await db.commit()
            
            embed = discord.Embed(
                title="✅ Achievements Purged",
                description=f"Successfully deleted **{before_count}** achievement records from the database.",
                color=0x2ECC71
            )
            embed.add_field(
                name="Note",
                value="Users will need to re-earn achievements based on the new system.",
                inline=False
            )
            await send_embed(ctx, embed)
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Achievements")
            logger.error(f"Error purging achievements: {e}", exc_info=True)
            await ctx.send("❌ Failed to purge achievements. Please try again.")


async def setup(bot):
    await bot.add_cog(Achievements(bot))
