"""User Settings System - Customize embed colors and preferences"""
import discord
from discord.ext import commands
import aiosqlite
import re

from config import DB_PATH
from utils.embed import send_embed


class Settings(commands.Cog):
    """User customization settings"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        """Initialize database tables"""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id INTEGER PRIMARY KEY,
                        inv_color TEXT DEFAULT NULL,
                        profile_color TEXT DEFAULT NULL,
                        bal_color TEXT DEFAULT NULL
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS game_limits (
                        user_id INTEGER PRIMARY KEY,
                        unlimited_games INTEGER DEFAULT 0
                    )
                """)
                await db.commit()
        except Exception as e:
            print(f"Error loading Settings cog: {e}")
    
    @commands.command(name="colorset", aliases=["setcolor"])
    async def color_set(self, ctx, embed_type: str = None, color: str = None):
        """Set custom embed color for inventory, profile, or balance
        
        Usage: gcolorset <type> <hex color>
        Types: inv, profile, bal, leaderboard, stats
        
        Examples:
        gcolorset inv #FF5733
        gcolorset profile 0x6a0dad
        gcolorset bal #2ECC71
        
        Use 'gcolorset <type> reset' to reset to default
        """
        if not embed_type or not color:
            embed = discord.Embed(
                title="🎨 Color Settings",
                description=(
                    "Customize your embed colors!\n\n"
                    "**Usage:** `gcolorset <type> <color>`\n\n"
                    "**Types:**\n"
                    "- `inv` - Inventory embed\n"
                    "- `profile` - Profile embed\n"
                    "- `bal` - Balance embed\n\n"
                    "**Examples:**\n"
                    "- `gcolorset inv #FF5733`\n"
                    "- `gcolorset profile 0x6a0dad`\n"
                    "- `gcolorset bal reset` (reset to default)"
                ),
                color=0x6a0dad
            )
            return await send_embed(ctx, embed)
        
        # Validate embed type
        embed_type = embed_type.lower()
        valid_types = ["inv", "profile", "bal"]
        if embed_type not in valid_types:
            return await ctx.send(f"❌ Invalid type! Use: `{', '.join(valid_types)}`")
        
        # Handle reset
        if color.lower() == "reset":
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    f"UPDATE user_settings SET {embed_type}_color = NULL WHERE user_id = ?",
                    (ctx.author.id,)
                )
                await db.commit()
            return await ctx.send(f"✅ Reset {embed_type} color to default!")
        
        # Parse hex color
        color = color.strip()
        # Remove # if present
        if color.startswith('#'):
            color = color[1:]
        # Remove 0x if present
        elif color.startswith('0x'):
            color = color[2:]
        
        # Validate hex
        if not re.match(r'^[0-9A-Fa-f]{6}$', color):
            return await ctx.send("❌ Invalid hex color! Use format: `#RRGGBB` or `0xRRGGBB`")
        
        # Convert to integer
        try:
            color_int = int(color, 16)
        except:
            return await ctx.send("❌ Invalid hex color!")
        
        # Save to database
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO user_settings (user_id, inv_color, profile_color, bal_color) 
                   VALUES (?, NULL, NULL, NULL) 
                   ON CONFLICT(user_id) DO NOTHING""",
                (ctx.author.id,)
            )
            await db.execute(
                f"UPDATE user_settings SET {embed_type}_color = ? WHERE user_id = ?",
                (color.upper(), ctx.author.id)
            )
            await db.commit()
        
        # Show preview
        embed = discord.Embed(
            title=f"✅ Color Set!",
            description=f"Your **{embed_type}** embed color has been changed!",
            color=color_int
        )
        await send_embed(ctx, embed)
    
    @commands.command(name="colors", aliases=["mycolors"])
    async def view_colors(self, ctx):
        """View your current custom colors"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT inv_color, profile_color, bal_color FROM user_settings WHERE user_id = ?",
                (ctx.author.id,)
            )
            row = await cursor.fetchone()
        
        if not row or all(c is None for c in row):
            embed = discord.Embed(
                title="🎨 Your Colors",
                description="You haven't set any custom colors yet!\n\nUse `gcolorset <type> <color>` to customize.",
                color=0x6a0dad
            )
        else:
            inv_color, profile_color, bal_color = row
            
            color_display = []
            if inv_color:
                color_display.append(f"**Inventory:** `#{inv_color}`")
            else:
                color_display.append("**Inventory:** Default")
            
            if profile_color:
                color_display.append(f"**Profile:** `#{profile_color}`")
            else:
                color_display.append("**Profile:** Default")
            
            if bal_color:
                color_display.append(f"**Balance:** `#{bal_color}`")
            else:
                color_display.append("**Balance:** Default")
            
            embed = discord.Embed(
                title="🎨 Your Colors",
                description="\n".join(color_display),
                color=0x6a0dad
            )
        
        await send_embed(ctx, embed)
    
    @commands.command(name="set")
    async def set_limit(self, ctx, game: str = None, state: str = None, member: discord.Member = None):
        """Toggle betting limits for games (OWNER ONLY)
        
        Usage: gset <game> <on/off> [@user]
        Games: bj (blackjack), flip, mines, slots, all
        
        Examples:
        gset bj off - Remove YOUR betting limit for blackjack
        gset all off @user - Remove all betting limits for a user
        gset flip on @user - Enable flip limit for a user
        """
        # Only allow bot owner (your ID)
        if ctx.author.id != 873464016217968640:
            return await ctx.send("nice try bozo.")
        
        if not game or not state:
            embed = discord.Embed(
                title="🎮 Game Limit Settings",
                description=(
                    "Control betting limits for minigames.\n\n"
                    "**Usage:** `gset <game> <on/off> [@user]`\n\n"
                    "**Games:**\n"
                    "- `bj` or `blackjack` - Blackjack\n"
                    "- `flip` or `coin` - Coin Flip\n"
                    "- `mines` - Mines\n"
                    "- `slots` - Slots\n"
                    "- `all` - All games\n\n"
                    "**States:**\n"
                    "- `off` - Remove 200k limit (unlimited)\n"
                    "- `on` - Enable 200k limit\n\n"
                    "**Examples:**\n"
                    "- `gset bj off` - Remove YOUR blackjack limit\n"
                    "- `gset all off @user` - Remove all limits for user\n"
                    "- `gset flip on @user` - Enable flip limit"
                ),
                color=0x6a0dad
            )
            return await send_embed(ctx, embed)
        
        # Target user (default to command author)
        target = member or ctx.author
        
        # Normalize game name
        game = game.lower()
        game_aliases = {
            "bj": "blackjack",
            "blackjack": "blackjack",
            "coin": "flip",
            "cf": "flip",
            "flip": "flip",
            "mines": "mines",
            "slots": "slots",
            "all": "all"
        }
        
        if game not in game_aliases:
            return await ctx.send(f"❌ Unknown game: `{game}`\nUse: `bj`, `flip`, `mines`, `slots`, or `all`")
        
        game_key = game_aliases[game]
        
        # Validate state
        state = state.lower()
        if state not in ["on", "off"]:
            return await ctx.send("❌ State must be `on` or `off`!")
        
        # Get current settings
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT unlimited_games FROM game_limits WHERE user_id = ?",
                (target.id,)
            )
            row = await cursor.fetchone()
            current_flags = row[0] if row else 0
        
        # Game flags (bit flags)
        BLACKJACK = 1 << 0  # 1
        FLIP = 1 << 1       # 2
        MINES = 1 << 2      # 4
        SLOTS = 1 << 3      # 8
        ALL_GAMES = BLACKJACK | FLIP | MINES | SLOTS  # 15
        
        game_flag_map = {
            "blackjack": BLACKJACK,
            "flip": FLIP,
            "mines": MINES,
            "slots": SLOTS,
            "all": ALL_GAMES
        }
        
        flag = game_flag_map[game_key]
        
        # Update flags
        if state == "off":
            # Enable unlimited (set bit)
            new_flags = current_flags | flag
            action = "removed"
        else:
            # Enable limit (clear bit)
            new_flags = current_flags & ~flag
            action = "enabled"
        
        # Save to database
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO game_limits (user_id, unlimited_games) 
                   VALUES (?, ?) 
                   ON CONFLICT(user_id) DO UPDATE SET unlimited_games = ?""",
                (target.id, new_flags, new_flags)
            )
            await db.commit()
        
        # Response
        game_name = "all games" if game_key == "all" else game_key
        limit_status = "unlimited" if state == "off" else "200k limit"
        
        embed = discord.Embed(
            title="✅ Limit Updated",
            description=f"{target.mention}'s **{game_name}** limit has been **{action}**!\n\nStatus: `{limit_status}`",
            color=0x2ECC71 if state == "off" else 0xE74C3C
        )
        await send_embed(ctx, embed)
    
    @commands.command(name="limits", aliases=["mylimits"])
    async def view_limits(self, ctx, member: discord.Member = None):
        """View betting limits for yourself or another user"""
        target = member or ctx.author
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT unlimited_games FROM game_limits WHERE user_id = ?",
                (target.id,)
            )
            row = await cursor.fetchone()
            flags = row[0] if row else 0
        
        # Game flags
        BLACKJACK = 1 << 0
        FLIP = 1 << 1
        MINES = 1 << 2
        SLOTS = 1 << 3
        
        # Check each game
        games_status = []
        games_status.append(f"**Blackjack:** {'🔓 Unlimited' if flags & BLACKJACK else '🔒 200k limit'}")
        games_status.append(f"**Coin Flip:** {'🔓 Unlimited' if flags & FLIP else '🔒 200k limit'}")
        games_status.append(f"**Mines:** {'🔓 Unlimited' if flags & MINES else '🔒 200k limit'}")
        games_status.append(f"**Slots:** {'🔓 Unlimited' if flags & SLOTS else '🔒 200k limit'}")
        
        embed = discord.Embed(
            title=f"🎮 {target.display_name}'s Game Limits",
            description="\n".join(games_status),
            color=0x6a0dad
        )
        await send_embed(ctx, embed)


async def get_user_embed_color(user_id: int, embed_type: str, default_color: int = 0x6a0dad) -> int:
    """Get user's custom embed color or default
    
    Args:
        user_id: Discord user ID
        embed_type: Type of embed ('inv', 'profile', 'bal')
        default_color: Default color if not set
    
    Returns:
        Integer color value
    """
    # Validate embed_type to prevent SQL injection
    if embed_type not in ['inv', 'profile', 'bal']:
        return default_color
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                f"SELECT {embed_type}_color FROM user_settings WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
        
        if row and row[0]:
            return int(row[0], 16)
        return default_color
    except Exception as e:
        print(f"Error getting embed color: {e}")
        return default_color


async def setup(bot):
    await bot.add_cog(Settings(bot))
