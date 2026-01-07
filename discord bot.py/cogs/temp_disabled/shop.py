"""Shop System - Buy Mora with real money"""
import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime
from config import DB_PATH
from utils.database import get_user_data, update_user_data
from utils.embed import send_embed


class Shop(commands.Cog):
    """In-game currency shop"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        """Initialize database tables"""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS shop_purchases (
                        user_id INTEGER,
                        pack_name TEXT,
                        amount INTEGER,
                        purchase_date TEXT,
                        month_year TEXT
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS monthly_limits (
                        user_id INTEGER,
                        month_year TEXT,
                        mega_pack_count INTEGER DEFAULT 0,
                        PRIMARY KEY (user_id, month_year)
                    )
                """)
                await db.commit()
        except Exception as e:
            print(f"Error loading Shop cog: {e}")
    
    async def get_monthly_purchases(self, user_id: int, pack_name: str) -> int:
        """Get how many times a pack was purchased this month"""
        current_month = datetime.now().strftime("%Y-%m")
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT mega_pack_count FROM monthly_limits WHERE user_id = ? AND month_year = ?",
                (user_id, current_month)
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    async def increment_purchase(self, user_id: int):
        """Increment the mega pack purchase count for this month"""
        current_month = datetime.now().strftime("%Y-%m")
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO monthly_limits (user_id, month_year, mega_pack_count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, month_year) DO UPDATE SET
                    mega_pack_count = mega_pack_count + 1
            """, (user_id, current_month))
            await db.commit()
    
    @commands.command(name="shop", aliases=["store", "packs"])
    async def shop(self, ctx):
        """View available Mora packs for purchase"""
        
        # Check how many mega packs user bought this month
        purchases = await self.get_monthly_purchases(ctx.author.id, "mega")
        remaining = max(0, 2 - purchases)
        
        embed = discord.Embed(
            title="💰 Mora Shop",
            description="Buy Mora with real money to boost your wallet!",
            color=0xFFD700
        )
        
        # Mega Pack (Limited)
        embed.add_field(
            name="💎 Mega Mora Pack - $25.00",
            value=(
                f"**1,000,000** <:mora:1437958309255577681>\n"
                f"⚠️ Limited: **2 per month**\n"
                f"📊 You have **{remaining}/2** left this month"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎁 What You Get:",
            value=(
                "<a:arrow:1437968863026479258> Instant 1M Mora added to wallet\n"
                "<a:arrow:1437968863026479258> Skip the grind, dominate the games\n"
                "<a:arrow:1437968863026479258> Perfect for high-stakes betting\n"
                "<a:arrow:1437968863026479258> Limit resets monthly"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💳 How to Purchase:",
            value=(
                "1. DM the bot owner with `gbuy mega`\n"
                "2. Send payment via PayPal/Venmo/CashApp\n"
                "3. Mora instantly added to your wallet!\n"
                "4. Receipt sent via DM"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📝 Notes:",
            value=(
                "<a:arrow:1437968863026479258> Non-refundable after delivery\n"
                "<a:arrow:1437968863026479258> Purchases tracked automatically\n"
                "<a:arrow:1437968863026479258> Limit resets 1st of each month\n"
                "<a:arrow:1437968863026479258> Contact owner for bulk orders"
            ),
            inline=False
        )
        
        embed.set_footer(text="Supporting the bot helps keep it running 24/7!")
        
        await send_embed(ctx, embed)
    
    @commands.command(name="buy")
    async def buy_pack(self, ctx):
        """Instructions to buy Mora packs"""
        purchases = await self.get_monthly_purchases(ctx.author.id, "mega")
        remaining = max(0, 2 - purchases)
        
        if remaining == 0:
            return await ctx.send(
                "❌ You've reached your monthly limit of 2 Mega Packs!\n"
                "Limit resets on the 1st of next month."
            )
        
        embed = discord.Embed(
            title="💎 Purchase Mega Mora Pack",
            description="Follow these steps to buy 1,000,000 Mora for $25:",
            color=0x00FF00
        )
        
        embed.add_field(
            name="Step 1: Contact Owner",
            value="DM the bot owner to request a Mega Pack purchase",
            inline=False
        )
        
        embed.add_field(
            name="Step 2: Payment",
            value="Owner will send payment details (PayPal/Venmo/CashApp)",
            inline=False
        )
        
        embed.add_field(
            name="Step 3: Confirmation",
            value="After payment, owner uses `ggrantpack @you` to add Mora",
            inline=False
        )
        
        embed.add_field(
            name="📊 Your Status",
            value=f"You can buy **{remaining}/2** Mega Packs this month",
            inline=False
        )
        
        embed.set_footer(text="Instant delivery • Safe & secure • 100% legitimate")
        
        await send_embed(ctx, embed)
    
    @commands.command(name="grantpack")
    async def grant_pack(self, ctx, user: discord.Member):
        """[OWNER ONLY] Grant a Mega Pack to a user after payment
        
        Usage: ggrantpack @user
        This adds 1M Mora and tracks the purchase
        """
        # Only bot owner can use this
        if ctx.author.id != 873464016217968640:
            return await ctx.send("❌ Only the bot owner can grant packs.")
        
        # Check if user has reached monthly limit
        purchases = await self.get_monthly_purchases(user.id, "mega")
        if purchases >= 2:
            return await ctx.send(
                f"❌ {user.mention} has already purchased 2 Mega Packs this month!\n"
                f"They can buy more on the 1st of next month."
            )
        
        # Get user data
        user_data = await get_user_data(user.id)
        if not user_data:
            return await ctx.send("❌ User needs to use the bot first!")
        
        # Add 1M Mora to wallet
        new_wallet = user_data['wallet'] + 1_000_000
        await update_user_data(user.id, wallet=new_wallet)
        
        # Record purchase
        current_month = datetime.now().strftime("%Y-%m")
        purchase_date = datetime.now().isoformat()
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO shop_purchases (user_id, pack_name, amount, purchase_date, month_year)
                VALUES (?, ?, ?, ?, ?)
            """, (user.id, "Mega Pack", 1_000_000, purchase_date, current_month))
            await db.commit()
        
        # Increment monthly limit counter
        await self.increment_purchase(user.id)
        
        # Get updated count
        new_count = await self.get_monthly_purchases(user.id, "mega")
        remaining = 2 - new_count
        
        # Confirm to owner
        await ctx.send(
            f"✅ **Mega Pack granted to {user.mention}!**\n"
            f"💰 Added: 1,000,000 <:mora:1437958309255577681>\n"
            f"📊 Their limit: {new_count}/2 used this month"
        )
        
        # DM the user
        try:
            user_embed = discord.Embed(
                title="💎 Mega Pack Received!",
                description="Your purchase has been processed successfully!",
                color=0x00FF00
            )
            user_embed.add_field(
                name="What You Got:",
                value=f"**+1,000,000** <:mora:1437958309255577681> added to your wallet!",
                inline=False
            )
            user_embed.add_field(
                name="New Balance:",
                value=f"{new_wallet:,} <:mora:1437958309255577681>",
                inline=False
            )
            user_embed.add_field(
                name="Monthly Status:",
                value=f"Mega Packs used: **{new_count}/2**\nRemaining: **{remaining}**",
                inline=False
            )
            user_embed.set_footer(text="Thank you for supporting the bot! 💙")
            
            await user.send(embed=user_embed)
        except:
            await ctx.send("⚠️ Couldn't DM the user, but Mora was added successfully.")
    
    @commands.command(name="mypack", aliases=["packlimit", "mylimit"])
    async def my_pack_limit(self, ctx):
        """Check your Mega Pack purchase limit for this month"""
        purchases = await self.get_monthly_purchases(ctx.author.id, "mega")
        remaining = max(0, 2 - purchases)
        
        current_month = datetime.now().strftime("%B %Y")
        
        embed = discord.Embed(
            title="📊 Your Mega Pack Status",
            description=f"Month: **{current_month}**",
            color=0x5865F2
        )
        
        embed.add_field(
            name="Packs Purchased",
            value=f"{purchases}/2",
            inline=True
        )
        
        embed.add_field(
            name="Remaining",
            value=f"{remaining}/2",
            inline=True
        )
        
        if remaining > 0:
            embed.add_field(
                name="💰 Available to Buy",
                value=f"You can buy **{remaining} more** Mega Pack(s) for ${remaining * 25}",
                inline=False
            )
            embed.add_field(
                name="How to Purchase",
                value="Use `gbuy` for purchase instructions",
                inline=False
            )
        else:
            embed.add_field(
                name="❌ Limit Reached",
                value="You've bought all 2 Mega Packs this month.\nLimit resets on the 1st!",
                inline=False
            )
        
        embed.set_footer(text="Purchase history tracked automatically")
        
        await send_embed(ctx, embed)
    
    @commands.command(name="purchases", aliases=["history", "myorders"])
    async def purchase_history(self, ctx):
        """View your purchase history"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT pack_name, amount, purchase_date 
                FROM shop_purchases 
                WHERE user_id = ? 
                ORDER BY purchase_date DESC 
                LIMIT 10
            """, (ctx.author.id,))
            rows = await cursor.fetchall()
        
        if not rows:
            return await ctx.send("You haven't made any purchases yet! Use `gshop` to see available packs.")
        
        embed = discord.Embed(
            title="🧾 Your Purchase History",
            description="Last 10 purchases:",
            color=0x5865F2
        )
        
        for pack_name, amount, purchase_date in rows:
            date_obj = datetime.fromisoformat(purchase_date)
            date_str = date_obj.strftime("%b %d, %Y at %I:%M %p")
            
            embed.add_field(
                name=f"💎 {pack_name}",
                value=f"{amount:,} <:mora:1437958309255577681>\n{date_str}",
                inline=False
            )
        
        total_spent = len(rows) * 25  # Each mega pack is $25
        embed.set_footer(text=f"Total purchases: {len(rows)} • Total spent: ${total_spent}")
        
        await send_embed(ctx, embed)


async def setup(bot):
    await bot.add_cog(Shop(bot))
