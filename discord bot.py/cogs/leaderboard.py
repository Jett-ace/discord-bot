import discord
from discord.ext import commands
import aiosqlite
from config import DB_PATH
from utils.embed import send_embed


class Leaderboard(commands.Cog):
    """Global and server leaderboards for various stats."""

    def __init__(self, bot):
        self.bot = bot
    
    async def get_user_badge(self, user_id: int) -> str:
        """Get user's custom badge if they have one set."""
        premium_cog = self.bot.get_cog('Premium')
        if premium_cog:
            badge = await premium_cog.get_custom_badge(user_id)
            if badge:
                return f" {badge}"
        return ""

    @commands.command(name="leaderboard", aliases=["lb", "top"])
    async def leaderboard(self, ctx, category: str = "mora"):
        """Show server leaderboards for various categories.
        
        Categories: mora, level, fish, wishes, achievements, streak, all
        Example: gleaderboard mora
        """
        category = category.lower()
        
        valid_categories = {
            "mora": ("Mora", "users", "mora", "<:mora:1437958309255577681>"),
            "dust": ("Tide Coins", "users", "dust", "<:mora:1437480155952975943>"),
            "level": ("Account Level", "accounts", "level", "📊"),
            "exp": ("Total EXP", "accounts", "exp", "✨"),
            "fish": ("Fish Caught", "fishing", "total_fish", "🎣"),
            "wishes": ("Total Wishes", "user_wishes", "count", "🌟"),
            "streak": ("Daily Streak", "daily_claims", "streak", "🔥"),
            "achievements": ("Achievements", None, None, "🏆"),
            "all": ("Server Rankings", None, None, "🏆")
        }
        
        if category not in valid_categories:
            await ctx.send(f"Invalid category! Use: {', '.join(valid_categories.keys())}")
            return
        
        # Get list of user IDs in the server
        server_member_ids = [member.id for member in ctx.guild.members if not member.bot]
        
        try:
            title, table, column, emoji = valid_categories[category]
            
            async with aiosqlite.connect(DB_PATH) as db:
                if category == "all":
                    # Server rankings: calculate score from multiple factors
                    placeholders = ','.join('?' * len(server_member_ids))
                    query = f"""
                        SELECT 
                            u.user_id,
                            (COALESCE(u.mora, 0) / 1000) + 
                            (COALESCE(b.deposited_amount, 0) / 1000) +
                            (COALESCE(a.level, 0) * 10000) + 
                            (COALESCE(f.total_fish, 0) * 100) + 
                            (COALESCE(w.count, 0) * 500) + 
                            (COALESCE(ach.ach_count, 0) * 5000) +
                            (COALESCE(d.streak, 0) * 1000) as total_score
                        FROM users u
                        LEFT JOIN user_bank_deposits b ON u.user_id = b.user_id
                        LEFT JOIN accounts a ON u.user_id = a.user_id
                        LEFT JOIN fishing f ON u.user_id = f.user_id
                        LEFT JOIN user_wishes w ON u.user_id = w.user_id
                        LEFT JOIN (SELECT user_id, COUNT(*) as ach_count FROM achievements GROUP BY user_id) ach ON u.user_id = ach.user_id
                        LEFT JOIN daily_claims d ON u.user_id = d.user_id AND (d.claim_type = 'regular' OR d.claim_type IS NULL)
                        WHERE u.enrolled = 1 AND u.user_id IN ({placeholders})
                        ORDER BY total_score DESC
                        LIMIT 10
                    """
                    async with db.execute(query, server_member_ids) as cursor:
                        rows = await cursor.fetchall()
                elif category == "achievements":
                    # Special handling for achievements (count from achievements table)
                    placeholders = ','.join('?' * len(server_member_ids))
                    query = f"""
                        SELECT user_id, COUNT(*) as ach_count
                        FROM achievements
                        WHERE user_id IN ({placeholders})
                        GROUP BY user_id
                        ORDER BY ach_count DESC
                        LIMIT 10
                    """
                    async with db.execute(query, server_member_ids) as cursor:
                        rows = await cursor.fetchall()
                else:
                    placeholders = ','.join('?' * len(server_member_ids))
                    
                    # Special handling for mora to include bank balance
                    if category == "mora":
                        query = f"""
                            SELECT u.user_id, (COALESCE(u.mora, 0) + COALESCE(b.deposited_amount, 0)) as total_wealth
                            FROM users u
                            LEFT JOIN user_bank_deposits b ON u.user_id = b.user_id
                            WHERE u.user_id IN ({placeholders})
                            ORDER BY total_wealth DESC
                            LIMIT 10
                        """
                    else:
                        # Special handling for streak to only show regular daily streaks
                        if category == "streak":
                            query = f"""
                                SELECT user_id, {column}
                                FROM {table}
                                WHERE user_id IN ({{placeholders}}) AND (claim_type = 'regular' OR claim_type IS NULL)
                                ORDER BY {column} DESC
                                LIMIT 10
                            """
                        else:
                            query = f"""
                                SELECT user_id, {column}
                                FROM {table}
                                WHERE user_id IN ({{placeholders}})
                                ORDER BY {column} DESC
                                LIMIT 10
                            """
                    async with db.execute(query, server_member_ids) as cursor:
                        rows = await cursor.fetchall()
                
                if not rows:
                    await ctx.send(f"No data available for {title} leaderboard yet.")
                    return
                
                embed = discord.Embed(
                    title=f"{emoji} {title} Leaderboard",
                    description=f"Top 10 players in **{ctx.guild.name}** ranked by {title.lower()}",
                    color=0xf39c12
                )
                
                # Find current user's position if not in top 10
                user_rank = None
                user_value = None
                for idx, (uid, value) in enumerate(rows, 1):
                    if uid == ctx.author.id:
                        user_rank = idx
                        user_value = value
                        break
                
                # Build leaderboard text
                lb_text = []
                medals = ["<a:Medal:1438198856910241842>", "<a:Medal2:1438198813851652117>", "<a:Medal3:1438198826799468604>"]
                
                for idx, (user_id, value) in enumerate(rows, 1):
                    try:
                        user = await self.bot.fetch_user(user_id)
                        username = user.display_name[:20]
                    except Exception:
                        username = f"User {user_id}"
                    
                    medal = medals[idx - 1] if idx <= 3 else f"`{idx}.`"
                    
                    # Format value based on category
                    if category == "all":
                        formatted_value = f"{int(value):,} pts"
                    elif category in ["mora", "exp"]:
                        formatted_value = f"{value:,}"
                    else:
                        formatted_value = str(value)
                    
                    # Get custom badge
                    badge = await self.get_user_badge(user_id)
                    
                    # Highlight current user
                    if user_id == ctx.author.id:
                        lb_text.append(f"{medal} **{username}{badge}** - **{formatted_value}** {emoji}")
                    else:
                        lb_text.append(f"{medal} {username}{badge} - {formatted_value} {emoji}")
                
                embed.add_field(
                    name="Rankings",
                    value="\n".join(lb_text),
                    inline=False
                )
                
                # Show user's rank if not in top 10
                if not user_rank:
                    async with aiosqlite.connect(DB_PATH) as db:
                        if category == "achievements":
                            rank_query = """
                                SELECT COUNT(DISTINCT t1.user_id) + 1
                                FROM (
                                    SELECT user_id, COUNT(*) as ach_count
                                    FROM achievements
                                    GROUP BY user_id
                                ) t1
                                JOIN (
                                    SELECT user_id, COUNT(*) as ach_count
                                    FROM achievements
                                    WHERE user_id = ?
                                    GROUP BY user_id
                                ) t2
                                WHERE t1.ach_count > t2.ach_count
                            """
                            value_query = """
                                SELECT COUNT(*) FROM achievements WHERE user_id = ?
                            """
                        else:
                            rank_query = f"""
                                SELECT COUNT(*) + 1
                                FROM {table}
                                WHERE {column} > (SELECT {column} FROM {table} WHERE user_id = ?)
                            """
                            value_query = f"SELECT {column} FROM {table} WHERE user_id = ?"
                        
                        async with db.execute(rank_query, (ctx.author.id,)) as cursor:
                            rank_row = await cursor.fetchone()
                            user_rank = rank_row[0] if rank_row else None
                        
                        async with db.execute(value_query, (ctx.author.id,)) as cursor:
                            value_row = await cursor.fetchone()
                            user_value = value_row[0] if value_row else 0
                
                if user_rank and user_rank > 10:
                    if category in ["mora", "exp"]:
                        formatted_value = f"{user_value:,}"
                    else:
                        formatted_value = str(user_value)
                    
                    embed.set_footer(
                        text=f"Your rank: #{user_rank} - {formatted_value}",
                        icon_url=ctx.author.display_avatar.url
                    )
                
                await send_embed(ctx, embed)
        
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Leaderboard")
            logger.error(f"Error in leaderboard command: {e}", exc_info=True)
            await ctx.send("❌ Failed to fetch leaderboard. Please try again.")


    @commands.command(name="globalleaderboard", aliases=["glb", "globaltop"])
    async def global_leaderboard(self, ctx, category: str = "mora"):
        """Show global leaderboards for various categories.
        
        Categories: mora, level, fish, wishes, achievements, streak, all
        Example: ggloballeaderboard mora
        """
        category = category.lower()
        
        valid_categories = {
            "mora": ("Mora", "users", "mora", "<:mora:1437958309255577681>"),
            "dust": ("Tide Coins", "users", "dust", "<:mora:1437480155952975943>"),
            "level": ("Account Level", "accounts", "level", ""),
            "exp": ("Total EXP", "accounts", "exp", "✨"),
            "fish": ("Fish Caught", "fishing", "total_fish", "🎣"),
            "wishes": ("Total Wishes", "user_wishes", "count", "🌟"),
            "streak": ("Daily Streak", "daily_claims", "streak", "🔥"),
            "achievements": ("Achievements", None, None, "🏆"),
            "all": ("Global Rankings", None, None, "🌎")
        }
        
        if category not in valid_categories:
            await ctx.send(f"Invalid category! Use: {', '.join(valid_categories.keys())}")
            return
        
        try:
            title, table, column, emoji = valid_categories[category]
            
            async with aiosqlite.connect(DB_PATH) as db:
                if category == "all":
                    # Global rankings: calculate score from multiple factors
                    query = """
                        SELECT 
                            u.user_id,
                            (COALESCE(u.mora, 0) / 1000) + 
                            (COALESCE(a.level, 0) * 10000) + 
                            (COALESCE(f.total_fish, 0) * 100) + 
                            (COALESCE(w.count, 0) * 500) + 
                            (COALESCE(ach.ach_count, 0) * 5000) +
                            (COALESCE(d.streak, 0) * 1000) as total_score
                        FROM users u
                        LEFT JOIN accounts a ON u.user_id = a.user_id
                        LEFT JOIN fishing f ON u.user_id = f.user_id
                        LEFT JOIN user_wishes w ON u.user_id = w.user_id
                        LEFT JOIN (SELECT user_id, COUNT(*) as ach_count FROM achievements GROUP BY user_id) ach ON u.user_id = ach.user_id
                        LEFT JOIN daily_claims d ON u.user_id = d.user_id AND (d.claim_type = 'regular' OR d.claim_type IS NULL)
                        WHERE u.enrolled = 1
                        ORDER BY total_score DESC
                        LIMIT 10
                    """
                    async with db.execute(query) as cursor:
                        rows = await cursor.fetchall()
                elif category == "achievements":
                    # Special handling for achievements (count from achievements table)
                    query = """
                        SELECT user_id, COUNT(*) as ach_count
                        FROM achievements
                        GROUP BY user_id
                        ORDER BY ach_count DESC
                        LIMIT 10
                    """
                    async with db.execute(query) as cursor:
                        rows = await cursor.fetchall()
                else:
                    # For mora category, sum wallet + bank for total wealth
                    if category == "mora":
                        query = f"""
                            SELECT u.user_id, (u.{column} + COALESCE(b.deposited_amount, 0)) as total_wealth
                            FROM {table} u
                            LEFT JOIN user_bank_deposits b ON u.user_id = b.user_id
                            ORDER BY total_wealth DESC
                            LIMIT 10
                        """
                    else:
                        query = f"""
                            SELECT user_id, {column}
                            FROM {table}
                            ORDER BY {column} DESC
                            LIMIT 10
                        """
                    async with db.execute(query) as cursor:
                        rows = await cursor.fetchall()
                
                if not rows:
                    await ctx.send(f"No data available for {title} leaderboard yet.")
                    return
                
                embed = discord.Embed(
                    title=f"{emoji} {title} Leaderboard (Global)",
                    description=f"Top 10 players globally ranked by {title.lower()}",
                    color=0x3498db
                )
                
                # Find current user's position if not in top 10
                user_rank = None
                user_value = None
                for idx, (uid, value) in enumerate(rows, 1):
                    if uid == ctx.author.id:
                        user_rank = idx
                        user_value = value
                        break
                
                # Build leaderboard text
                lb_text = []
                medals = ["<a:Medal:1438198856910241842>", "<a:Medal2:1438198813851652117>", "<a:Medal3:1438198826799468604>"]
                
                for idx, (user_id, value) in enumerate(rows, 1):
                    try:
                        user = await self.bot.fetch_user(user_id)
                        username = user.display_name[:20]
                    except Exception:
                        username = f"User {user_id}"
                    
                    medal = medals[idx - 1] if idx <= 3 else f"`{idx}.`"
                    
                    # Format value based on category
                    if category == "all":
                        formatted_value = f"{int(value):,} pts"
                    elif category in ["mora", "exp"]:
                        formatted_value = f"{value:,}"
                    else:
                        formatted_value = str(value)
                    
                    # Get custom badge
                    badge = await self.get_user_badge(user_id)
                    
                    # Highlight current user
                    if user_id == ctx.author.id:
                        lb_text.append(f"{medal} **{username}{badge}** - **{formatted_value}** {emoji}")
                    else:
                        lb_text.append(f"{medal} {username}{badge} - {formatted_value} {emoji}")
                
                embed.add_field(
                    name="Rankings",
                    value="\n".join(lb_text),
                    inline=False
                )
                
                # Show user's rank if not in top 10
                if not user_rank:
                    async with aiosqlite.connect(DB_PATH) as db:
                        if category == "achievements":
                            rank_query = """
                                SELECT COUNT(DISTINCT t1.user_id) + 1
                                FROM (
                                    SELECT user_id, COUNT(*) as ach_count
                                    FROM achievements
                                    GROUP BY user_id
                                ) t1
                                JOIN (
                                    SELECT user_id, COUNT(*) as ach_count
                                    FROM achievements
                                    WHERE user_id = ?
                                    GROUP BY user_id
                                ) t2
                                WHERE t1.ach_count > t2.ach_count
                            """
                            value_query = """
                                SELECT COUNT(*) FROM achievements WHERE user_id = ?
                            """
                        else:
                            rank_query = f"""
                                SELECT COUNT(*) + 1
                                FROM {table}
                                WHERE {column} > (SELECT {column} FROM {table} WHERE user_id = ?)
                            """
                            value_query = f"SELECT {column} FROM {table} WHERE user_id = ?"
                        
                        async with db.execute(rank_query, (ctx.author.id,)) as cursor:
                            rank_row = await cursor.fetchone()
                            user_rank = rank_row[0] if rank_row else None
                        
                        async with db.execute(value_query, (ctx.author.id,)) as cursor:
                            value_row = await cursor.fetchone()
                            user_value = value_row[0] if value_row else 0
                
                if user_rank and user_rank > 10:
                    if category in ["mora", "exp"]:
                        formatted_value = f"{user_value:,}"
                    else:
                        formatted_value = str(user_value)
                    
                    embed.set_footer(
                        text=f"Your global rank: #{user_rank} - {formatted_value}",
                        icon_url=ctx.author.display_avatar.url
                    )
                
                await send_embed(ctx, embed)
        
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Leaderboard")
            logger.error(f"Error in global leaderboard command: {e}", exc_info=True)
            await ctx.send("❌ Failed to fetch global leaderboard. Please try again.")


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
