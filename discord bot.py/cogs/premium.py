"""Premium Subscription System"""
import discord
from discord.ext import commands
from discord import ui
import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH
from utils.embed import send_embed


class PremiumSelectView(ui.View):
    """Interactive view for premium information"""
    
    def __init__(self, author_id, timeout=180):
        super().__init__(timeout=timeout)
        self.author_id = author_id
    
    @ui.select(
        placeholder="Select what you want to learn about...",
        options=[
            discord.SelectOption(label="Premium Perks Overview", emoji="⭐", value="overview", description="See all premium benefits"),
            discord.SelectOption(label="Game Benefits", emoji="🎮", value="games", description="Premium advantages in games"),
            discord.SelectOption(label="Economy Benefits", emoji="💰", value="economy", description="Banking, loans, and rewards"),
            discord.SelectOption(label="Exclusive Features", emoji="✨", value="exclusive", description="Premium-only features"),
            discord.SelectOption(label="Pricing & Plans", emoji="💎", value="pricing", description="View subscription options"),
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: ui.Select):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("❌ This menu isn't for you!", ephemeral=True)
        
        value = select.values[0]
        
        if value == "overview":
            embed = discord.Embed(
                title="⭐ Premium Perks Overview",
                description="Complete list of all Premium benefits!",
                color=0xFFD700
            )
            embed.add_field(
                name="🎮 Game Advantages",
                value=(
                    "<a:arrow:1437968863026479258> **Better luck** in RPS, Wheel, Coinflip, Slots\n"
                    "<a:arrow:1437968863026479258> **Increased betting limits** on all games (bet bigger!)\n"
                    "<a:arrow:1437968863026479258> **Unlimited RPS plays** (vs 5 per 5 minutes)\n"
                    "<a:arrow:1437968863026479258> **Bundle daily command** (`gbundle`)\n"
                    "<a:arrow:1437968863026479258> **3x daily rewards** (triple mora & items)\n"
                    "<a:arrow:1437968863026479258> **15% discount on Black Market items**\n"
                    "<a:arrow:1437968863026479258> **Shorter rob cooldowns** (20/40min vs 30/60min)\n"
                    "<a:arrow:1437968863026479258> **+15% rob success rate** (35% vs 20%)"
                ),
                inline=False
            )
            embed.add_field(
                name="💰 Economy Perks",
                value=(
                    "<a:arrow:1437968863026479258> **Unlimited bank deposits** (vs 5M limit)\n"
                    "<a:arrow:1437968863026479258> **1M max loans** (vs 500K)\n"
                    "<a:arrow:1437968863026479258> **3 loans per day** (vs 1 loan)\n"
                    "<a:arrow:1437968863026479258> **5M sign-up bonus + 2 Random Chests**"
                ),
                inline=False
            )
            embed.add_field(
                name="🎨 Personalization",
                value=(
                    "<a:arrow:1437968863026479258> **Custom badge** - Set emoji that appears everywhere\n"
                    "<a:arrow:1437968863026479258> **Badge on leaderboards** - Show off your style\n"
                    "<a:arrow:1437968863026479258> **Badge on profile** - Customize your identity"
                ),
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "games":
            embed = discord.Embed(
                title="🎮 Premium Game Benefits",
                description="Premium gives you subtle advantages in games!",
                color=0x9B59B6
            )
            embed.add_field(
                name="💰 Betting Limits",
                value=(
                    "<a:arrow:1437968863026479258> **3x higher limits on all games**\n"
                    "<a:arrow:1437968863026479258> Blackjack: 15M max (vs 10M)\n"
                    "<a:arrow:1437968863026479258> Other games scale with premium\n"
                    "<a:arrow:1437968863026479258> Bet bigger, win bigger"
                ),
                inline=False
            )
            embed.add_field(
                name="🎲 RPS (Rock-Paper-Scissors)",
                value=(
                    "<a:arrow:1437968863026479258> **Unlimited plays** (no cooldown)\n"
                    "<a:arrow:1437968863026479258> **+15% luck boost**\n"
                    "<a:arrow:1437968863026479258> Bot picks losing choice 15% of time\n"
                    "<a:arrow:1437968863026479258> Better win rate than normal"
                ),
                inline=False
            )
            embed.add_field(
                name="🎡 Wheel of Fortune",
                value=(
                    "<a:arrow:1437968863026479258> **10% better odds overall**\n"
                    "<a:arrow:1437968863026479258> 37% loss rate vs 47% normal\n"
                    "<a:arrow:1437968863026479258> More winning outcomes (28% 2x vs 22%)\n"
                    "<a:arrow:1437968863026479258> Win streak balancing prevents abuse"
                ),
                inline=False
            )
            embed.add_field(
                name="🪙 Coinflip",
                value=(
                    "<a:arrow:1437968863026479258> **+8% luck bonus**\n"
                    "<a:arrow:1437968863026479258> Losing flips convert to wins 8% of time\n"
                    "<a:arrow:1437968863026479258> Slight edge over normal odds"
                ),
                inline=False
            )
            embed.add_field(
                name="🎰 Slots",
                value=(
                    "<a:arrow:1437968863026479258> **10% chance to force match**\n"
                    "<a:arrow:1437968863026479258> Automatically locks highest value symbol\n"
                    "<a:arrow:1437968863026479258> Better jackpot chances"
                ),
                inline=False
            )
            embed.add_field(
                name="🃏 Blackjack",
                value=(
                    "<a:arrow:1437968863026479258> **15M max bet** (vs 10M)\n"
                    "<a:arrow:1437968863026479258> Standard game rules (fair play)\n"
                    "<a:arrow:1437968863026479258> Increased betting limit only"
                ),
                inline=False
            )
            embed.add_field(
                name="<:shotgun:1458773713418977364> Rob System",
                value=(
                    "<a:arrow:1437968863026479258> **Shorter cooldowns**: 20min success / 40min fail\n"
                    "<a:arrow:1437968863026479258> **+15% success rate** (35% base vs 20%)\n"
                    "<a:arrow:1437968863026479258> Even higher success with items\n"
                    "<a:arrow:1437968863026479258> Rob more often, succeed more often"
                ),
                inline=False
            )
            embed.add_field(
                name="<a:blackmarket:1457960838154084364> Black Market",
                value=(
                    "<a:arrow:1437968863026479258> **15% discount on all items**\n"
                    "<a:arrow:1437968863026479258> Save millions on expensive items\n"
                    "<a:arrow:1437968863026479258> Applies to every purchase"
                ),
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "economy":
            embed = discord.Embed(
                title="💰 Premium Economy Benefits",
                description="Banking, loans, and financial perks!",
                color=0x2ECC71
            )
            embed.add_field(
                name="🏦 Bank Deposits",
                value=(
                    "<a:arrow:1437968863026479258> **Unlimited deposits** (vs 5M limit)\n"
                    "<a:arrow:1437968863026479258> Store as much as you want\n"
                    "<a:arrow:1437968863026479258> Same 3% daily interest\n"
                    "<a:arrow:1437968863026479258> Perfect for high rollers"
                ),
                inline=False
            )
            embed.add_field(
                name="💳 Loans",
                value=(
                    "<a:arrow:1437968863026479258> **1M max loan amount** (vs 500K)\n"
                    "<a:arrow:1437968863026479258> **3 loans per day** (vs 1 loan)\n"
                    "<a:arrow:1437968863026479258> Same 12-hour repayment window\n"
                    "<a:arrow:1437968863026479258> Same penalty system"
                ),
                inline=False
            )
            embed.add_field(
                name="🎁 Daily Rewards",
                value=(
                    "<a:arrow:1437968863026479258> **3x mora rewards**\n"
                    "<a:arrow:1437968863026479258> **3x item rewards**\n"
                    "<a:arrow:1437968863026479258> Same streak bonuses\n"
                    "<a:arrow:1437968863026479258> Triple your daily income!"
                ),
                inline=False
            )
            embed.add_field(
                name="💎 Sign-Up Bonus",
                value=(
                    "<a:arrow:1437968863026479258> **5,000,000 mora** when you first subscribe\n"
                    "<a:arrow:1437968863026479258> **2x Random Chests** bonus items\n"
                    "<a:arrow:1437968863026479258> One-time bonus\n"
                    "<a:arrow:1437968863026479258> Start your premium journey rich!"
                ),
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "exclusive":
            embed = discord.Embed(
                title="✨ Premium Exclusive Features",
                description="Features ONLY available to Premium members!",
                color=0xE91E63
            )
            embed.add_field(
                name="⭐ Bundle Daily Rewards",
                value=(
                    "<a:arrow:1437968863026479258> **Command:** `gbundle` (or `gbd`)\n"
                    "<a:arrow:1437968863026479258> **3x mora** compared to regular daily\n"
                    "<a:arrow:1437968863026479258> **Random item** (Lucky Dice, Hot Streak, etc.)\n"
                    "<a:arrow:1437968863026479258> **2x Random Chests** every day\n"
                    "<a:arrow:1437968863026479258> Separate from regular daily (claim both!)"
                ),
                inline=False
            )
            embed.add_field(
                name="🎲 Better Game Odds",
                value=(
                    "<a:arrow:1437968863026479258> **RPS: +15% luck boost**\n"
                    "<a:arrow:1437968863026479258> **Coinflip: +8% luck bonus**\n"
                    "<a:arrow:1437968863026479258> **Wheel: 10% better odds (37% vs 47% loss)**\n"
                    "<a:arrow:1437968863026479258> **Slots: 10% force-win chance**\n"
                    "<a:arrow:1437968863026479258> **Win streak balancing for fairness**"
                ),
                inline=False
            )
            embed.add_field(
                name="🎨 Custom Badge",
                value=(
                    "<a:arrow:1437968863026479258> **Command:** `gsetbadge <emoji>`\n"
                    "<a:arrow:1437968863026479258> Set any emoji as your badge\n"
                    "<a:arrow:1437968863026479258> Appears next to your name everywhere\n"
                    "<a:arrow:1437968863026479258> Shows on leaderboards\n"
                    "<a:arrow:1437968863026479258> Shows on profile\n"
                    "<a:arrow:1437968863026479258> Make yourself stand out!"
                ),
                inline=False
            )
            embed.add_field(
                name="🎮 Unlimited RPS",
                value=(
                    "<a:arrow:1437968863026479258> No more 5 plays per 5 minutes\n"
                    "<a:arrow:1437968863026479258> Play as much as you want\n"
                    "<a:arrow:1437968863026479258> Grind mora without limits\n"
                    "<a:arrow:1437968863026479258> Combined with luck boost!"
                ),
                inline=False
            )
            embed.add_field(
                name="💰 Economy Advantages",
                value=(
                    "<a:arrow:1437968863026479258> **Unlimited bank deposits**\n"
                    "<a:arrow:1437968863026479258> **3 loans per day** (vs 1)\n"
                    "<a:arrow:1437968863026479258> **1M max loan** (vs 500K)\n"
                    "<a:arrow:1437968863026479258> **3x daily rewards**\n"
                    "<a:arrow:1437968863026479258> **15% Black Market discount**"
                ),
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "pricing":
            embed = discord.Embed(
                title="💎 Premium Pricing & Plans",
                description="Choose the plan that works for you!",
                color=0xFFD700
            )
            embed.add_field(
                name="⭐ Premium Monthly - $9.99/month",
                value=(
                    "<a:arrow:1437968863026479258> All Premium features\n"
                    "<a:arrow:1437968863026479258> 5M mora sign-up bonus\n"
                    "<a:arrow:1437968863026479258> Auto-renews monthly\n"
                    "<a:arrow:1437968863026479258> Cancel anytime"
                ),
                inline=False
            )
            embed.add_field(
                name="👑 Premium Quarterly - $25/3 months",
                value=(
                    "<a:arrow:1437968863026479258> All Premium features\n"
                    "<a:arrow:1437968863026479258> 5M mora sign-up bonus\n"
                    "<a:arrow:1437968863026479258> **Save $5** (16% discount!)\n"
                    "<a:arrow:1437968863026479258> **Best Value!**\n"
                    "<a:arrow:1437968863026479258> Auto-renews every 3 months"
                ),
                inline=False
            )
            embed.add_field(
                name="🌟 Lifetime Premium - Custom Pricing",
                value=(
                    "<a:arrow:1437968863026479258> All Premium features forever\n"
                    "<a:arrow:1437968863026479258> 5M mora sign-up bonus\n"
                    "<a:arrow:1437968863026479258> One-time payment\n"
                    "<a:arrow:1437968863026479258> Never expires\n"
                    "<a:arrow:1437968863026479258> Contact owner for pricing"
                ),
                inline=False
            )
            embed.add_field(
                name="💳 How to Subscribe",
                value=(
                    "**Payment Method:** PayPal\n"
                    "**Contact:** DM the bot owner to get started\n"
                    "**Setup:** Instant activation after payment"
                ),
                inline=False
            )
            embed.add_field(
                name="❓ Why Subscribe?",
                value=(
                    "Your subscription supports:\n"
                    "<a:arrow:1437968863026479258> 24/7 bot hosting\n"
                    "<a:arrow:1437968863026479258> Development & updates\n"
                    "<a:arrow:1437968863026479258> Server maintenance"
                ),
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class Premium(commands.Cog):
    """Premium subscription features"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        """Initialize database tables"""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS premium_users (
                        user_id INTEGER PRIMARY KEY,
                        tier TEXT DEFAULT 'basic',
                        expires_at TEXT,
                        subscribed_at TEXT,
                        lifetime INTEGER DEFAULT 0,
                        custom_badge TEXT DEFAULT NULL
                    )
                """)
                # Add custom_badge column if it doesn't exist
                try:
                    await db.execute("ALTER TABLE premium_users ADD COLUMN custom_badge TEXT DEFAULT NULL")
                except:
                    pass  # Column already exists
                await db.commit()
        except Exception as e:
            print(f"Error loading Premium cog: {e}")
    
    async def get_custom_badge(self, user_id: int) -> str:
        """Get user's custom badge emoji if they have one set"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT custom_badge FROM premium_users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row and row[0] else None
    
    async def is_premium(self, user_id: int, tier: str = None) -> bool:
        """Check if user has active premium subscription"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT tier, expires_at, lifetime FROM premium_users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return False
            
            user_tier, expires_at, lifetime = row
            
            # Lifetime premium
            if lifetime:
                return True
            
            # Check if expired
            if expires_at:
                expiry = datetime.fromisoformat(expires_at)
                if datetime.now() > expiry:
                    return False
            
            # All premium tiers have same features now
            return True
    
    async def get_premium_info(self, user_id: int):
        """Get user's premium subscription info"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT tier, expires_at, subscribed_at, lifetime FROM premium_users WHERE user_id = ?",
                (user_id,)
            )
            return await cursor.fetchone()
    
    @commands.command(name="premium")
    async def premium_info(self, ctx):
        """View premium subscription tiers and benefits - Interactive menu!"""
        
        # Main embed with select menu
        embed = discord.Embed(
            title="💎 Premium Subscription",
            description=(
                "**Use the menu below to explore Premium benefits!**\n\n"
                "Premium gives you advantages in games, economy bonuses,\n"
                "exclusive features, and more!\n\n"
                "Select a category to see detailed information (only you can see it)."
            ),
            color=0xFFD700
        )
        
        # Quick overview
        embed.add_field(
            name="✨ Premium Highlights",
            value=(
                "<a:arrow:1437968863026479258> **Better luck in games** (RPS, Coinflip, Wheel, Slots)\n"
                "<a:arrow:1437968863026479258> **Bundle daily command** (`gbundle`)\n"
                "<a:arrow:1437968863026479258> **Increased betting limits** (bet bigger!)\n"
                "<a:arrow:1437968863026479258> **3x daily rewards** (mora & items)\n"
                "<a:arrow:1437968863026479258> **Unlimited bank deposits**\n"
                "<a:arrow:1437968863026479258> **Custom badge everywhere**\n"
                "<a:arrow:1437968863026479258> **Rob bonuses & more!**"
            ),
            inline=False
        )
        
        # Show user's current status
        info = await self.get_premium_info(ctx.author.id)
        if info:
            tier, expires_at, subscribed_at, lifetime = info
            if lifetime:
                status = "✅ You have Lifetime Premium!"
            else:
                expiry = datetime.fromisoformat(expires_at)
                days_left = (expiry - datetime.now()).days
                status = f"✅ You have Premium (expires in {days_left} days)"
        else:
            status = "You're on the Free tier - Use the menu to learn about Premium!"
        
        embed.set_footer(text=status)
        
        # Create view with select menu
        view = PremiumSelectView(ctx.author.id)
        await ctx.send(embed=embed, view=view)
    
    @commands.command(name="add")
    async def grant_premium(self, ctx, user: discord.Member, duration: str = "monthly"):
        """[OWNER ONLY] Grant premium subscription to a user
        
        Usage: gadd @user monthly (30 days)
        Usage: gadd @user quarterly (90 days)
        Usage: gadd @user lifetime
        """
        # Only bot owner can use this
        if ctx.author.id != 873464016217968640:
            return await ctx.send("❌ Only the bot owner can grant premium.")
        
        duration = duration.lower()
        if duration == "monthly":
            days = 30
            plan_name = "Monthly"
        elif duration == "quarterly":
            days = 90
            plan_name = "Quarterly"
        elif duration == "lifetime":
            days = None
            plan_name = "Lifetime"
        else:
            return await ctx.send("❌ Invalid duration. Use: `monthly`, `quarterly`, or `lifetime`")
        
        subscribed_at = datetime.now()
        
        # Award 5M mora sign-up bonus + 2 random chests
        from utils.database import get_user_data, update_user_data
        import random
        user_data = await get_user_data(user.id)
        new_mora = user_data.get('mora', 0) + 5000000
        await update_user_data(user.id, mora=new_mora)
        
        # Give 2 random chests
        async with aiosqlite.connect(DB_PATH) as db:
            # Add 2 random chests to inventory
            await db.execute("""
                INSERT INTO inventory (user_id, item_id, quantity)
                VALUES (?, 'random', 2)
                ON CONFLICT(user_id, item_id) DO UPDATE SET
                    quantity = quantity + 2
            """, (user.id,))
            await db.commit()
        
        async with aiosqlite.connect(DB_PATH) as db:
            if duration == "lifetime":
                await db.execute("""
                    INSERT INTO premium_users (user_id, tier, expires_at, subscribed_at, lifetime)
                    VALUES (?, 'premium', NULL, ?, 1)
                    ON CONFLICT(user_id) DO UPDATE SET
                        tier = 'premium',
                        lifetime = 1,
                        subscribed_at = excluded.subscribed_at
                """, (user.id, subscribed_at.isoformat()))
            else:
                expires_at = datetime.now() + timedelta(days=days)
                await db.execute("""
                    INSERT INTO premium_users (user_id, tier, expires_at, subscribed_at, lifetime)
                    VALUES (?, 'premium', ?, ?, 0)
                    ON CONFLICT(user_id) DO UPDATE SET
                        tier = 'premium',
                        expires_at = excluded.expires_at,
                        subscribed_at = excluded.subscribed_at,
                        lifetime = 0
                """, (user.id, expires_at.isoformat(), subscribed_at.isoformat()))
            await db.commit()
        
        await ctx.send(
            f"✅ Granted **{plan_name} Premium** to {user.mention}!\n"
            f"🎁 Sign-up bonus: **5,000,000** <:mora:1437958309255577681>\n"
            f"📦 Bonus: **2x** <:random:1437977751520018452> Random Chests"
        )
    
    @commands.command(name="revoke")
    async def revoke_premium(self, ctx, user: discord.Member):
        """[OWNER ONLY] Revoke premium subscription from a user"""
        # Only bot owner can use this
        if ctx.author.id != 873464016217968640:
            return await ctx.send("❌ Only the bot owner can revoke premium.")
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM premium_users WHERE user_id = ?", (user.id,))
            await db.commit()
        
        await ctx.send(f"✅ Revoked premium from {user.mention}")
    
    @commands.command(name="mystatus", aliases=["subscription", "sub"])
    async def my_status(self, ctx):
        """Check your premium subscription status"""
        info = await self.get_premium_info(ctx.author.id)
        
        if not info:
            embed = discord.Embed(
                title="Your Subscription Status",
                description="You're currently on the **Free** tier.",
                color=0x95A5A6
            )
            embed.add_field(
                name="Upgrade to Premium!",
                value="Use `gpremium` to see all available tiers and benefits.",
                inline=False
            )
        else:
            tier, expires_at, subscribed_at, lifetime = info
            
            if lifetime:
                embed = discord.Embed(
                    title="Your Subscription Status",
                    description=f"🌟 You have **Lifetime {tier.upper()}**!",
                    color=0xFFD700
                )
            else:
                expiry = datetime.fromisoformat(expires_at)
                days_left = (expiry - datetime.now()).days
                
                color = 0xFFD700 if tier == "vip" else 0x5865F2
                embed = discord.Embed(
                    title="Your Subscription Status",
                    description=f"⭐ **{tier.upper()}** Subscriber",
                    color=color
                )
                embed.add_field(
                    name="Expires In",
                    value=f"{days_left} days",
                    inline=True
                )
                embed.add_field(
                    name="Subscribed Since",
                    value=datetime.fromisoformat(subscribed_at).strftime("%b %d, %Y"),
                    inline=True
                )
        
        await send_embed(ctx, embed)
    
    @commands.command(name="setbadge")
    async def set_badge(self, ctx, emoji: str = None):
        """Set a custom badge that appears on your profile (Premium only)
        
        Usage: gsetbadge <emoji>
        Example: gsetbadge 👑
        
        Use `gsetbadge clear` to remove your badge."""
        # Check if user is premium
        is_premium = await self.is_premium(ctx.author.id)
        if not is_premium:
            embed = discord.Embed(
                title="⭐ Premium Feature",
                description="Custom badges are only available for **Premium** subscribers!",
                color=0xE74C3C
            )
            embed.add_field(
                name="How to Subscribe",
                value="Contact an administrator to get Premium access.",
                inline=False
            )
            return await send_embed(ctx, embed)
        
        if emoji is None:
            # Show current badge
            current_badge = await self.get_custom_badge(ctx.author.id)
            if current_badge:
                embed = discord.Embed(
                    title="Your Custom Badge",
                    description=f"Current badge: {current_badge}",
                    color=0x5865F2
                )
                embed.add_field(
                    name="Change Badge",
                    value="Use `gsetbadge <emoji>` to change it\nUse `gsetbadge clear` to remove it",
                    inline=False
                )
            else:
                embed = discord.Embed(
                    title="No Badge Set",
                    description="You don't have a custom badge set yet!",
                    color=0x95A5A6
                )
                embed.add_field(
                    name="Set Your Badge",
                    value="Use `gsetbadge <emoji>` to set one\nExample: `gsetbadge 👑`",
                    inline=False
                )
            return await send_embed(ctx, embed)
        
        # Clear badge
        if emoji.lower() == "clear":
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE premium_users SET custom_badge = NULL WHERE user_id = ?",
                    (ctx.author.id,)
                )
                await db.commit()
            
            embed = discord.Embed(
                title="✅ Badge Cleared",
                description="Your custom badge has been removed.",
                color=0x2ECC71
            )
            return await send_embed(ctx, embed)
        
        # Validate emoji (basic check - should be 1-4 characters, includes unicode emojis)
        if len(emoji) > 100:  # Prevent abuse
            return await ctx.send("❌ Badge is too long! Use a single emoji.")
        
        # Set badge
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE premium_users SET custom_badge = ? WHERE user_id = ?",
                (emoji, ctx.author.id)
            )
            await db.commit()
        
        embed = discord.Embed(
            title="✅ Badge Updated",
            description=f"Your custom badge has been set to: {emoji}",
            color=0x2ECC71
        )
        embed.add_field(
            name="Preview",
            value=f"{ctx.author.display_name} {emoji}",
            inline=False
        )
        embed.set_footer(text="Your badge will appear on your profile!")
        await send_embed(ctx, embed)


async def setup(bot):
    await bot.add_cog(Premium(bot))
