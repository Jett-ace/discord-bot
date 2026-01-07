import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH
from utils.database import require_enrollment
from utils.embed import send_embed


# Import item definitions from blackmarket
from cogs.blackmarket import ITEMS, RARITY_COLORS


class BankUpgradeView(discord.ui.View):
    def __init__(self, user_id: int, item_id: str):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.item_id = item_id
    
    @discord.ui.button(label="Deposit Limit +2M", style=discord.ButtonStyle.green, emoji="📊")
    async def deposit_upgrade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your upgrade!", ephemeral=True)
        
        async with aiosqlite.connect(DB_PATH) as db:
            # Ensure bank_capacity column exists
            try:
                await db.execute("ALTER TABLE users ADD COLUMN bank_capacity INTEGER DEFAULT 1000000")
                await db.commit()
            except:
                pass
            
            # Increase bank capacity
            await db.execute(
                "UPDATE users SET bank_capacity = COALESCE(bank_capacity, 1000000) + 2000000 WHERE user_id = ?",
                (self.user_id,)
            )
            # Remove item from inventory
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                (self.user_id, self.item_id)
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                (self.user_id,)
            )
            await db.commit()
        
        embed = discord.Embed(
            title="<a:Check:1437951818452832318> Bank Deposit Upgraded!",
            description="Your bank deposit limit increased by **+2,000,000** <:mora:1437958309255577681>!",
            color=0x2ECC71
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()
    
    @discord.ui.button(label="Loan Limit +250K", style=discord.ButtonStyle.blurple, emoji="💰")
    async def loan_upgrade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your upgrade!", ephemeral=True)
        
        async with aiosqlite.connect(DB_PATH) as db:
            # Increase loan limit
            await db.execute(
                "UPDATE users SET max_loan = COALESCE(max_loan, 500000) + 250000 WHERE user_id = ?",
                (self.user_id,)
            )
            # Remove item from inventory
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                (self.user_id, self.item_id)
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                (self.user_id,)
            )
            await db.commit()
        
        embed = discord.Embed(
            title="<a:Check:1437951818452832318> Loan Limit Upgraded!",
            description="Your maximum loan amount increased by **+250,000** <:mora:1437958309255577681>!",
            color=0x2ECC71
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        """Initialize active_items table"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS active_items (
                    user_id INTEGER,
                    item_id TEXT,
                    activated_at TEXT,
                    uses_remaining INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, item_id)
                )
            """)
            await db.commit()

    @commands.command(name="i", aliases=["inv", "inventory", "bag"])
    async def inventory(self, ctx):
        """View your inventory"""
        if not await require_enrollment(ctx):
            return

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT item_id, quantity, activated_at FROM inventory WHERE user_id = ? ORDER BY quantity DESC",
                (ctx.author.id,)
            ) as cursor:
                items = await cursor.fetchall()

        if not items:
            embed = discord.Embed(
                title=f"{ctx.author.display_name}'s Inventory",
                description="Your inventory is empty!\n\nVisit the Black Market with `gblackmarket` to purchase items.",
                color=0x95A5A6
            )
            return await ctx.send(embed=embed)

        # Check premium status
        premium_cog = self.bot.get_cog('Premium')
        custom_badge = ""
        if premium_cog:
            is_premium = await premium_cog.is_premium(ctx.author.id)
            if is_premium:
                badge = await premium_cog.get_custom_badge(ctx.author.id)
                if badge:
                    custom_badge = f" {badge}"
        
        embed = discord.Embed(
            title=f"{ctx.author.display_name}{custom_badge}'s Inventory",
            description="Use `guse <item>` to activate items",
            color=0x3498DB
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        items_text = []
        for item_id, quantity, activated_at in items:
            if item_id not in ITEMS:
                continue
            
            item = ITEMS[item_id]
            items_text.append(f"{item['emoji']} **{item['name']}**: {quantity}")
        
        embed.description = "\n".join(items_text) if items_text else "Your inventory is empty!"
        embed.set_footer(text="Use 'guse <item>' to activate items")
        await ctx.send(embed=embed)

    @commands.command(name="use")
    async def use_item(self, ctx, *, item_name: str = None):
        """Use/activate an item from your inventory"""
        if not await require_enrollment(ctx):
            return

        if item_name is None:
            return await ctx.send("<a:X_:1437951830393884788> Usage: `guse <item name>`\nExample: `guse xp booster`")

        # Find item by name or alias
        item_id = None
        item_name_lower = item_name.lower().replace(" ", "_")
        
        for iid, item in ITEMS.items():
            # Check item ID and name
            if iid == item_name_lower or item["name"].lower() == item_name.lower():
                item_id = iid
                break
            # Check aliases if they exist
            if "aliases" in item:
                for alias in item["aliases"]:
                    if alias.lower() == item_name.lower() or alias.lower().replace(" ", "_") == item_name_lower:
                        item_id = iid
                        break
            if item_id:
                break

        if item_id is None:
            return await ctx.send("<a:X_:1437951830393884788> Item not found!")

        item = ITEMS[item_id]

        # Check if user owns the item
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                (ctx.author.id, item_id)
            ) as cursor:
                result = await cursor.fetchone()

            if not result or result[0] <= 0:
                return await ctx.send(f"<a:X_:1437951830393884788> You don't own {item['emoji']} **{item['name']}**!")

            # Special handling for permanent items
            if item["type"] == "permanent":
                if item_id == "bankers_key":
                    # Ensure bank_capacity column exists
                    try:
                        await db.execute("ALTER TABLE users ADD COLUMN bank_capacity INTEGER DEFAULT 1000000")
                        await db.commit()
                    except:
                        pass
                    
                    # Apply bank capacity increase
                    await db.execute(
                        "UPDATE users SET bank_capacity = COALESCE(bank_capacity, 1000000) + 300000 WHERE user_id = ?",
                        (ctx.author.id,)
                    )
                    # Remove from inventory
                    await db.execute(
                        "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                        (ctx.author.id, item_id)
                    )
                    await db.execute(
                        "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                        (ctx.author.id,)
                    )
                    await db.commit()
                    
                    return await ctx.send(
                        f"<a:Check:1437951818452832318> {item['emoji']} **Banker's Key** used! "
                        f"Your bank capacity increased by **+300,000** <:mora:1437958309255577681>!"
                    )
            
            # Special handling for bank upgrade (choice required)
            if item_id == "bank_upgrade":
                embed = discord.Embed(
                    title="<:upgrade:1457983244682268695> Bank Upgrade",
                    description="Choose which limit to upgrade:",
                    color=0xF1C40F
                )
                embed.add_field(
                    name="📊 Bank Deposit Limit",
                    value="+2,000,000 mora deposit capacity",
                    inline=False
                )
                embed.add_field(
                    name="💰 Loan Limit",
                    value="+250,000 mora max loan amount",
                    inline=False
                )
                
                view = BankUpgradeView(ctx.author.id, item_id)
                return await ctx.send(embed=embed, view=view)
            
            # Rob items handling
            if item_id == "shotgun":
                await db.execute(
                    "INSERT OR IGNORE INTO rob_items (user_id) VALUES (?)",
                    (ctx.author.id,)
                )
                await db.execute(
                    "UPDATE rob_items SET shotgun = 1 WHERE user_id = ?",
                    (ctx.author.id,)
                )
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute("DELETE FROM inventory WHERE user_id = ? AND quantity <= 0", (ctx.author.id,))
                await db.commit()
                return await ctx.send(f"<a:Check:1437951818452832318> 🔫 **Shotgun** equipped! You now have **+20%** robbery success rate!")
            
            elif item_id == "thiefpack":
                await db.execute(
                    "INSERT OR IGNORE INTO rob_items (user_id) VALUES (?)",
                    (ctx.author.id,)
                )
                await db.execute(
                    "UPDATE rob_items SET mask = mask + 1, night_vision = night_vision + 1, lockpicker = lockpicker + 1 WHERE user_id = ?",
                    (ctx.author.id,)
                )
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute("DELETE FROM inventory WHERE user_id = ? AND quantity <= 0", (ctx.author.id,))
                await db.commit()
                return await ctx.send(f"<a:Check:1437951818452832318> 🎒 **Thief Pack** activated! Mask, Night Vision, and Lockpicker added (1 use each, +25% with full set)!")
            
            elif item_id == "guarddog":
                expires = datetime.now() + timedelta(days=7)
                await db.execute(
                    "INSERT OR IGNORE INTO rob_items (user_id) VALUES (?)",
                    (ctx.author.id,)
                )
                await db.execute(
                    "UPDATE rob_items SET guard_dog = 1, guard_dog_expires = ? WHERE user_id = ?",
                    (expires.isoformat(), ctx.author.id)
                )
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute("DELETE FROM inventory WHERE user_id = ? AND quantity <= 0", (ctx.author.id,))
                await db.commit()
                return await ctx.send(f"<a:Check:1437951818452832318> 🐕 **Guard Dog** deployed! You have **+25%** defense for the next **7 days**!")
            
            elif item_id == "fence":
                await db.execute(
                    "INSERT OR IGNORE INTO rob_items (user_id) VALUES (?)",
                    (ctx.author.id,)
                )
                await db.execute(
                    "UPDATE rob_items SET spiky_fence = 1 WHERE user_id = ?",
                    (ctx.author.id,)
                )
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute("DELETE FROM inventory WHERE user_id = ? AND quantity <= 0", (ctx.author.id,))
                await db.commit()
                return await ctx.send(f"<a:Check:1437951818452832318> 🚧 **Spiky Fence** installed! You now have **+5%** permanent defense!")
            
            elif item_id == "lock":
                await db.execute(
                    "INSERT OR IGNORE INTO rob_items (user_id) VALUES (?)",
                    (ctx.author.id,)
                )
                await db.execute(
                    "UPDATE rob_items SET lock = lock + 1 WHERE user_id = ?",
                    (ctx.author.id,)
                )
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute("DELETE FROM inventory WHERE user_id = ? AND quantity <= 0", (ctx.author.id,))
                await db.commit()
                return await ctx.send(f"<a:Check:1437951818452832318> 🔒 **Lock** installed! It will **100% block** the next robbery attempt!")

            # Check if already active for non-stackable items
            if not item.get("stackable", False):
                async with db.execute(
                    "SELECT activated_at FROM inventory WHERE user_id = ? AND item_id = ? AND activated_at IS NOT NULL",
                    (ctx.author.id, item_id)
                ) as cursor:
                    active = await cursor.fetchone()
                    
                    if active:
                        activated_time = datetime.fromisoformat(active[0])
                        
                        # Check if still active
                        if item_id == "xp_booster":
                            expiry = activated_time + timedelta(minutes=30)
                            if datetime.now() < expiry:
                                return await ctx.send(f"<a:X_:1437951830393884788> You already have an active {item['emoji']} **{item['name']}**!")

            # Activate item based on type
            if item_id == "xp_booster":
                # Activate XP booster
                await db.execute(
                    "UPDATE inventory SET activated_at = ? WHERE user_id = ? AND item_id = ?",
                    (datetime.now().isoformat(), ctx.author.id, item_id)
                )
                await db.commit()
                
                embed = discord.Embed(
                    title="<:exp:1437553839359397928> XP Booster Activated!",
                    description="You'll gain **+50% XP** from all activities for the next **30 minutes**!",
                    color=0xF1C40F
                )
                return await ctx.send(embed=embed)

            elif item_id == "streak":
                # Activate hot streak card
                await db.execute(
                    "INSERT OR REPLACE INTO active_items (user_id, item_id, activated_at, uses_remaining) VALUES (?, ?, ?, 3)",
                    (ctx.author.id, 'streak', datetime.now().isoformat())
                )
                # Remove from inventory
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                    (ctx.author.id,)
                )
                await db.commit()
                
                embed = discord.Embed(
                    title="<:streak:1457966635838214247> Hot Streak Card Activated!",
                    description="Your next **3 losses** will refund **50%** of your bet!\nValid for 48 hours.",
                    color=0xE74C3C
                )
                return await ctx.send(embed=embed)

            elif item_id == "lucky_dice":
                # Activate lucky dice
                await db.execute(
                    "INSERT OR REPLACE INTO active_items (user_id, item_id, activated_at, uses_remaining) VALUES (?, ?, ?, 10)",
                    (ctx.author.id, item_id, datetime.now().isoformat())
                )
                # Remove from inventory
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                    (ctx.author.id,)
                )
                await db.commit()
                
                embed = discord.Embed(
                    title="<:dice:1457965149137670186> Lucky Dice Activated!",
                    description="You have **+5% win chance** on coinflip, dice, and rps for your next **10 games**!\nValid for 24 hours.",
                    color=0x2ECC71
                )
                return await ctx.send(embed=embed)

            elif item_id == "lucky_horseshoe":
                # Activate lucky horseshoe
                await db.execute(
                    "INSERT OR REPLACE INTO active_items (user_id, item_id, activated_at) VALUES (?, ?, ?)",
                    (ctx.author.id, item_id, datetime.now().isoformat())
                )
                # Update activated_at in inventory instead of removing
                await db.execute(
                    "UPDATE inventory SET activated_at = ? WHERE user_id = ? AND item_id = ?",
                    (datetime.now().isoformat(), ctx.author.id, item_id)
                )
                await db.commit()
                
                embed = discord.Embed(
                    title="<:luckyhorseshoe:1458353830704975884> Lucky Horseshoe Activated!",
                    description="You have **+10% win chance** on ALL gambling games for the next **4 hours**!",
                    color=0xFFD700
                )
                return await ctx.send(embed=embed)

            elif item_id == "lucky_clover":
                # Activate lucky clover
                await db.execute(
                    "INSERT OR REPLACE INTO active_items (user_id, item_id, activated_at) VALUES (?, ?, ?)",
                    (ctx.author.id, item_id, datetime.now().isoformat())
                )
                # Update activated_at in inventory instead of removing
                await db.execute(
                    "UPDATE inventory SET activated_at = ? WHERE user_id = ? AND item_id = ?",
                    (datetime.now().isoformat(), ctx.author.id, item_id)
                )
                await db.commit()
                
                embed = discord.Embed(
                    title="🍀 Lucky Clover Activated!",
                    description="You have **+3% win chance** on ALL gambling games for the next **1 hour**!",
                    color=0x2ECC71
                )
                return await ctx.send(embed=embed)

            elif item_id == "piggy_bank":
                # One-time use permanent item - add protected balance
                try:
                    await db.execute("ALTER TABLE users ADD COLUMN piggy_balance INTEGER DEFAULT 0")
                    await db.commit()
                except:
                    pass
                
                # Add 500K to piggy bank
                await db.execute(
                    "UPDATE users SET piggy_balance = COALESCE(piggy_balance, 0) + 500000 WHERE user_id = ?",
                    (ctx.author.id,)
                )
                # Remove from inventory
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                    (ctx.author.id,)
                )
                await db.commit()
                
                return await ctx.send(
                    f"<a:Check:1437951818452832318> <:goldenbank:1458347495183876210> **Golden Piggy Bank** activated! "
                    f"Stored **500,000** <:mora:1437958309255577681> in your protected piggy bank (cannot be robbed)!"
                )

            elif item_id == "double_down":
                # Activate double down card for next win
                await db.execute(
                    "INSERT OR REPLACE INTO active_items (user_id, item_id, activated_at, uses_remaining) VALUES (?, ?, ?, 1)",
                    (ctx.author.id, item_id, datetime.now().isoformat())
                )
                # Remove from inventory
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                    (ctx.author.id,)
                )
                await db.commit()
                
                embed = discord.Embed(
                    title="<:doubledown:1458351562966565037> Double Down Card Activated!",
                    description="Your next gambling win will have **2x profit**!\nWorks on: Coinflip, Slots, Roulette, Blackjack, Hi-Lo, Tower, Mines, RPS, Wheel",
                    color=0x3498DB
                )
                return await ctx.send(embed=embed)
            
            elif item_id == "golden_chip":
                # Activate golden chip for next win
                await db.execute(
                    "INSERT OR REPLACE INTO active_items (user_id, item_id, activated_at, uses_remaining) VALUES (?, ?, ?, 1)",
                    (ctx.author.id, item_id, datetime.now().isoformat())
                )
                # Remove from inventory
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                    (ctx.author.id,)
                )
                await db.commit()
                
                embed = discord.Embed(
                    title="<:goldenchip:1457964285207646264> Golden Chip Activated!",
                    description="Your next coinflip or blackjack win will get **+30% bonus**!",
                    color=0xFFD700
                )
                return await ctx.send(embed=embed)
            
            elif item_id == "rigged_deck":
                # Activate rigged deck for next blackjack
                await db.execute(
                    "INSERT OR REPLACE INTO active_items (user_id, item_id, activated_at, uses_remaining) VALUES (?, ?, ?, 1)",
                    (ctx.author.id, item_id, datetime.now().isoformat())
                )
                # Remove from inventory
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                    (ctx.author.id,)
                )
                await db.commit()
                
                embed = discord.Embed(
                    title="<a:deck:1457965675082551306> Rigged Deck Activated!",
                    description="Your next blackjack game will be a **guaranteed win**!",
                    color=0xF1C40F
                )
                return await ctx.send(embed=embed)
            
            elif item_id == "card_counter":
                # Activate card counter for next blackjack
                await db.execute(
                    "INSERT OR REPLACE INTO active_items (user_id, item_id, activated_at, uses_remaining) VALUES (?, ?, ?, 1)",
                    (ctx.author.id, item_id, datetime.now().isoformat())
                )
                # Remove from inventory
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
                await db.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                    (ctx.author.id,)
                )
                await db.commit()
                
                embed = discord.Embed(
                    title="<a:counter:1458347417329209426> Card Counter Activated!",
                    description="Your next blackjack game will **reveal the dealer's hidden card**!",
                    color=0x9B59B6
                )
                return await ctx.send(embed=embed)

            else:
                return await ctx.send(f"<a:X_:1437951830393884788> **{item['name']}** cannot be used.")


async def setup(bot):
    await bot.add_cog(Inventory(bot))
