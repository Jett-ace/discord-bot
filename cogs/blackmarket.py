import discord
from discord.ext import commands
import aiosqlite
import random
from datetime import datetime, timedelta
from config import DB_PATH
from utils.database import get_user_data, update_user_data, require_enrollment
from utils.embed import send_embed


# Item definitions with emojis
ITEMS = {
    "lucky_dice": {
        "name": "Lucky Dice",
        "emoji": "<:dice:1457965149137670186>",
        "rarity": "Uncommon",
        "base_price": 350000,
        "description": "+5% win chance on coinflip, dice, rps for next 10 games",
        "type": "consumable",
        "duration": "10 games or 24 hours",
        "stackable": False,
        "source": "Black Market"
    },
    "golden_chip": {
        "name": "Golden Chip",
        "emoji": "<:goldenchip:1457964285207646264>",
        "rarity": "Rare",
        "base_price": 800000,
        "description": "Next winning bet gets +0.3x multiplier bonus",
        "type": "consumable",
        "duration": "Single use (next win)",
        "stackable": True,
        "max_stack": 3,
        "source": "Black Market"
    },
    "xp_booster": {
        "name": "XP Booster",
        "emoji": "<:exp:1437553839359397928>",
        "rarity": "Common",
        "base_price": 200000,
        "description": "+50% XP gain from all activities",
        "type": "consumable",
        "duration": "30 minutes",
        "stackable": False,
        "source": "Black Market, Chests"
    },
    "bankers_key": {
        "name": "Banker's Key",
        "emoji": "<a:bankerskey:1457962936076075049>",
        "rarity": "Epic",
        "base_price": 1000000,
        "description": "Permanently increase bank capacity by +300,000 mora",
        "type": "permanent",
        "duration": "Permanent",
        "stackable": True,
        "max_stack": 10,
        "source": "Black Market"
    },
    "streak_shield": {
        "name": "Daily Streak Shield",
        "emoji": "<a:shield:1457967376799629324>",
        "rarity": "Epic",
        "base_price": 1500000,
        "description": "Protects your daily streak from breaking once",
        "type": "consumable",
        "duration": "Permanent (consumed on missed daily)",
        "stackable": True,
        "max_stack": 3,
        "source": "Black Market"
    },
    "hot_streak": {
        "name": "Hot Streak Card",
        "emoji": "<:streak:1457966635838214247>",
        "rarity": "Legendary",
        "base_price": 12000000,
        "description": "Next 3 losses return 50% of bet",
        "type": "consumable",
        "duration": "3 losses or 48 hours",
        "stackable": False,
        "source": "Black Market"
    },
    "regular": {
        "name": "Regular Chest",
        "emoji": "<:regular:1437473086571286699>",
        "rarity": "Common",
        "base_price": None,  # Not purchasable
        "description": "Contains mora, XP, and has a chance for rare items",
        "type": "consumable",
        "duration": "Single use - open with 'gopen regular'",
        "stackable": True,
        "max_stack": 999,
        "source": "Daily Rewards, Game Wins"
    },
    "diamond": {
        "name": "Diamond Chest",
        "emoji": "<:dimond:1437473169475764406>",
        "rarity": "Rare",
        "base_price": None,  # Not purchasable
        "description": "Contains better mora, XP, and higher chances for rare items",
        "type": "consumable",
        "duration": "Single use - open with 'gopen diamond'",
        "stackable": True,
        "max_stack": 999,
        "source": "Daily Rewards, Game Wins"
    },
    "random": {
        "name": "Random Chest",
        "emoji": "<:random:1437977751520018452>",
        "rarity": "Special",
        "base_price": None,  # Not purchasable
        "description": "Contains random rewards: Mora, XP, items, or other chests!",
        "type": "consumable",
        "duration": "Single use - open with 'gopen random'",
        "stackable": True,
        "max_stack": 999,
        "source": "Premium Subscription, RPS Rewards"
    },
    "rigged_deck": {
        "name": "Rigged Deck",
        "emoji": "<a:deck:1457965675082551306>",
        "rarity": "Legendary",
        "base_price": 18000000,
        "description": "Guaranteed win on next blackjack game",
        "type": "consumable",
        "duration": "Single use",
        "stackable": True,
        "max_stack": 2,
        "source": "Black Market (Limited Stock)"
    },
    "plasma_canon": {
        "name": "Plasma Canon",
        "emoji": "<:plasmacanon:1457975521521434624>",
        "rarity": "Mythic",
        "base_price": 15000000,
        "description": "Offensive weapon - Fire at target to extract 6% from wallet + 15% from bank, bypasses all defenses",
        "type": "consumable",
        "duration": "Single use with grob",
        "stackable": True,
        "max_stack": 3,
        "source": "Black Market"
    },
    "special_crate": {
        "name": "Special Crate",
        "emoji": "<a:crate:1457969509770985492>",
        "rarity": "Mythic",
        "base_price": 25000000,
        "description": "Contains high-value rewards and guaranteed rare items",
        "type": "consumable",
        "duration": "Single use - open with 'gopen special'",
        "stackable": True,
        "max_stack": 5,
        "source": "Black Market"
    },
    "bank_upgrade": {
        "name": "Bank Upgrade",
        "emoji": "<:upgrade:1457983244682268695>",
        "rarity": "Legendary",
        "base_price": 15000000,
        "description": "Choose to upgrade: +2M bank deposit limit OR +250K loan limit",
        "type": "consumable",
        "duration": "Single use - choose upgrade type",
        "stackable": True,
        "max_stack": 10,
        "source": "Black Market"
    },
    "shotgun": {
        "name": "Shotgun",
        "emoji": "🔫",
        "rarity": "Uncommon",
        "base_price": 250000,
        "description": "+20% robbery success rate",
        "type": "permanent",
        "duration": "Permanent",
        "stackable": False,
        "source": "Black Market"
    },
    "thiefpack": {
        "name": "Thief Pack",
        "emoji": "🎒",
        "rarity": "Rare",
        "base_price": 400000,
        "description": "Mask + Night Vision + Lockpicker - +25% success with full set",
        "type": "consumable",
        "duration": "Single use (each item)",
        "stackable": True,
        "max_stack": 5,
        "source": "Black Market"
    },
    "guarddog": {
        "name": "Guard Dog",
        "emoji": "🐕",
        "rarity": "Uncommon",
        "base_price": 150000,
        "description": "+25% defense against robberies",
        "type": "consumable",
        "duration": "7 days",
        "stackable": False,
        "source": "Black Market"
    },
    "fence": {
        "name": "Spiky Fence",
        "emoji": "<:fench:1458002114260242454>",
        "rarity": "Common",
        "base_price": 100000,
        "description": "+5% defense against robberies",
        "type": "permanent",
        "duration": "Permanent",
        "stackable": False,
        "source": "Black Market"
    },
    "lock": {
        "name": "Lock",
        "emoji": "🔒",
        "rarity": "Common",
        "base_price": 80000,
        "description": "100% blocks ONE robbery attempt",
        "type": "consumable",
        "duration": "Single use",
        "stackable": True,
        "max_stack": 10,
        "source": "Black Market"
    }
}

RARITY_COLORS = {
    "Common": 0x95A5A6,
    "Uncommon": 0x2ECC71,
    "Rare": 0x3498DB,
    "Epic": 0x9B59B6,
    "Legendary": 0xF1C40F,
    "Mythic": 0xE74C3C
}


async def restock_market(user_id):
    """Restock user's personal Black Market with 12-hour rotation (rarer items appear less often)"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if we've already restocked in the last 12 hours for this user
        async with db.execute(
            "SELECT last_restock FROM black_market_stock WHERE user_id = ? LIMIT 1",
            (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
        
        if result:
            last_restock = datetime.fromisoformat(result[0])
            time_since_restock = datetime.now() - last_restock
            if time_since_restock < timedelta(hours=12):
                return  # Already restocked within last 12 hours
        
        # Clear old stock for this user
        await db.execute("DELETE FROM black_market_stock WHERE user_id = ?", (user_id,))
        
        # Rotation chances based on rarity (daily cycle)
        selected_items = []
        for item_id, item in ITEMS.items():
            # Determine if item appears today based on rarity
            appears = False
            if item["rarity"] == "Common":
                appears = random.random() < 0.90  # 90% chance to appear
            elif item["rarity"] == "Uncommon":
                appears = random.random() < 0.75  # 75% chance
            elif item["rarity"] == "Rare":
                appears = random.random() < 0.60  # 60% chance
            elif item["rarity"] == "Epic":
                appears = random.random() < 0.40  # 40% chance
            elif item["rarity"] == "Legendary":
                appears = random.random() < 0.25  # 25% chance
            else:  # Mythic
                appears = random.random() < 0.05  # 5% chance (EXTREMELY RARE)
            
            if appears:
                selected_items.append((item_id, item))
        
        # Ensure at least 7 items are selected
        if len(selected_items) < 7:
            # Add random items until we have 7
            remaining_items = [(iid, itm) for iid, itm in ITEMS.items() if iid not in [x[0] for x in selected_items]]
            needed = 7 - len(selected_items)
            selected_items.extend(random.sample(remaining_items, min(needed, len(remaining_items))))
        
        # Insert selected items into stock
        for item_id, item in selected_items:
            # Set stock quantities based on rarity (REDUCED)
            if item["rarity"] == "Common":
                stock = random.randint(3, 6)
            elif item["rarity"] == "Uncommon":
                stock = random.randint(2, 4)
            elif item["rarity"] == "Rare":
                stock = random.randint(1, 3)
            elif item["rarity"] == "Epic":
                stock = random.randint(1, 2)
            elif item["rarity"] == "Legendary":
                # Rigged Deck always has stock of 1
                if item_id == "rigged_deck":
                    stock = 1
                else:
                    stock = 1
            else:  # Mythic
                stock = 1
            
            # Insert into stock with user_id
            await db.execute("""
                INSERT INTO black_market_stock (user_id, item_id, stock, price, last_restock)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, item_id, stock, item["base_price"], datetime.now().isoformat()))
        
        await db.commit()


class BlackMarket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="bm", aliases=["blackmarket", "shop"])
    async def black_market(self, ctx):
        """View your personal Black Market"""
        if not await require_enrollment(ctx):
            return

        # Auto-restock if new day (daily rotation)
        await restock_market(ctx.author.id)

        data = await get_user_data(ctx.author.id)
        mora = data.get("mora", 0)

        embed = discord.Embed(
            title="🎴 Black Market",
            description=f"**Your Personal Market** - Unique to you!\n**Rotates every 12 hours** - Different items each rotation!\nYour balance: **{mora:,}** <:mora:1437958309255577681>\n\nUse `gbuy <item>` to purchase",
            color=0x9B59B6
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        # Get current stock for this user
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT item_id, stock, price FROM black_market_stock WHERE user_id = ? ORDER BY price DESC",
                (ctx.author.id,)
            ) as cursor:
                stocks = await cursor.fetchall()

        for item_id, stock, price in stocks:
            if item_id not in ITEMS:
                continue
            
            item = ITEMS[item_id]
            
            # Skip items that are not purchasable (price is None)
            if price is None or item.get('base_price') is None:
                continue
            
            stock_text = f"**{stock}** in stock" if stock > 0 else "**OUT OF STOCK**"
            
            value = f"{item['emoji']} **{item['name']}** - {price:,} <:mora:1437958309255577681>\n"
            value += f"└ *{item['description']}*\n"
            value += f"└ {stock_text}"
            
            embed.add_field(
                name=f"{item['rarity']} Item",
                value=value,
                inline=False
            )

        # Show player listings
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM black_market_listings"
            ) as cursor:
                listing_count = (await cursor.fetchone())[0]
            
            # Get user's last restock time
            async with db.execute(
                "SELECT last_restock FROM black_market_stock WHERE user_id = ? LIMIT 1",
                (ctx.author.id,)
            ) as cursor:
                restock_result = await cursor.fetchone()
        
        # Calculate next rotation time (12 hours from last restock)
        if restock_result:
            last_restock = datetime.fromisoformat(restock_result[0])
            next_rotation = last_restock + timedelta(hours=12)
            time_until = next_rotation - datetime.now()
            hours_left = max(0, int(time_until.total_seconds() // 3600))
            minutes_left = max(0, int((time_until.total_seconds() % 3600) // 60))
            time_text = f"{hours_left}h {minutes_left}m" if hours_left > 0 else f"{minutes_left}m"
        else:
            time_text = "now"
        
        embed.set_footer(text=f"Check out player listings (use 'gpm') | Next rotation in {time_text}")
        await ctx.send(embed=embed)

    @commands.command(name="buy")
    async def buy_item(self, ctx, *args):
        """Buy an item from your personal Black Market"""
        if not await require_enrollment(ctx):
            return

        # Auto-restock if new day
        await restock_market(ctx.author.id)

        if not args:
            return await ctx.send("<a:X_:1437951830393884788> Usage: `gbuy <item name> [amount]`\nExample: `gbuy lucky dice` or `gbuy rigged deck 2`")

        # Parse arguments - last argument might be amount
        amount = 1
        if len(args) > 1 and args[-1].isdigit():
            amount = int(args[-1])
            item_name = " ".join(args[:-1])
        else:
            item_name = " ".join(args)

        if amount < 1:
            return await ctx.send("<a:X_:1437951830393884788> Amount must be at least 1!")

        # Find item
        item_id = None
        item_name_lower = item_name.lower().replace(" ", "_")
        
        for iid, item in ITEMS.items():
            if iid == item_name_lower or item["name"].lower() == item_name.lower():
                item_id = iid
                break

        if item_id is None:
            return await ctx.send("<a:X_:1437951830393884788> Item not found! Use `gblackmarket` to see available items.")

        item = ITEMS[item_id]

        # Check stock for this user
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT stock, price FROM black_market_stock WHERE user_id = ? AND item_id = ?",
                (ctx.author.id, item_id)
            ) as cursor:
                result = await cursor.fetchone()
            
            if not result:
                return await ctx.send("<a:X_:1437951830393884788> This item isn't in today's cycle. Try again in the next cycle.")
            
            stock, price = result
            
            if stock <= 0:
                return await ctx.send(f"<a:X_:1437951830393884788> {item['emoji']} **{item['name']}** is OUT OF STOCK! Wait for tomorrow's restock or check player listings with `gpm`")

            if amount > stock:
                return await ctx.send(f"<a:X_:1437951830393884788> Not enough stock! Only **{stock}** available.")

            # Check premium status for 10% discount
            premium_cog = ctx.bot.get_cog('Premium')
            is_premium = False
            if premium_cog:
                is_premium = await premium_cog.is_premium(ctx.author.id)
            
            # Apply premium discount
            if is_premium:
                total_price = int((price * amount) * 0.90)  # 10% off
                discount_text = " (10% Premium discount applied)"
            else:
                total_price = price * amount
                discount_text = ""

            # Get user's mora directly within the same connection
            async with db.execute(
                "SELECT mora FROM users WHERE user_id = ?",
                (ctx.author.id,)
            ) as cursor:
                mora_result = await cursor.fetchone()
                mora = mora_result[0] if mora_result else 0

            if mora < total_price:
                return await ctx.send(f"<a:X_:1437951830393884788> You need {total_price:,} <:mora:1437958309255577681> to buy {amount}x {item['emoji']} **{item['name']}**. You have {mora:,}.")

            # Check if already owned and not stackable
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                (ctx.author.id, item_id)
            ) as cursor:
                inv_result = await cursor.fetchone()
                current_qty = inv_result[0] if inv_result else 0

            if not item.get("stackable", False) and current_qty > 0:
                return await ctx.send(f"<a:X_:1437951830393884788> You already own {item['emoji']} **{item['name']}** and it's not stackable!")

            if not item.get("stackable", False) and amount > 1:
                return await ctx.send(f"<a:X_:1437951830393884788> {item['emoji']} **{item['name']}** is not stackable! You can only buy 1.")

            if item.get("stackable", False):
                max_stack = item.get("max_stack", 999)
                if current_qty + amount > max_stack:
                    return await ctx.send(f"<a:X_:1437951830393884788> Purchasing {amount} would exceed the maximum stack limit ({max_stack}) for {item['emoji']} **{item['name']}**! You currently have {current_qty}.")

            # Purchase item - decrease stock
            await db.execute(
                "UPDATE black_market_stock SET stock = stock - ? WHERE user_id = ? AND item_id = ?",
                (amount, ctx.author.id, item_id)
            )
            
            # Deduct mora
            await db.execute(
                "UPDATE users SET mora = mora - ? WHERE user_id = ?",
                (total_price, ctx.author.id)
            )

            # Add to inventory
            if current_qty > 0:
                await db.execute(
                    "UPDATE inventory SET quantity = quantity + ? WHERE user_id = ? AND item_id = ?",
                    (amount, ctx.author.id, item_id)
                )
            else:
                await db.execute(
                    "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)",
                    (ctx.author.id, item_id, amount)
                )
            await db.commit()

        quantity_text = f"{amount}x " if amount > 1 else ""
        
        discount_msg = ""
        if is_premium:
            discount_msg = "\n✨ **10% Premium discount applied**"
        
        embed = discord.Embed(
            title="🎴 Purchase Successful!",
            description=f"You bought {quantity_text}{item['emoji']} **{item['name']}** for {total_price:,} <:mora:1437958309255577681>{discount_msg}\n\n**{stock-amount}** remaining in stock",
            color=RARITY_COLORS.get(item["rarity"], 0x2ECC71)
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="Effect", value=item["description"], inline=False)
        if amount > 1:
            embed.add_field(name="Quantity", value=f"{amount} items", inline=True)
        embed.set_footer(text="Use 'gi' to view your items")
        await ctx.send(embed=embed)

    @commands.command(name="sell", aliases=["list"])
    async def sell_item(self, ctx, price: int = None, *, item_name: str = None):
        """List your item for sale on the Black Market"""
        if not await require_enrollment(ctx):
            return

        if price is None or item_name is None:
            return await ctx.send("<a:X_:1437951830393884788> Usage: `gsell <price> <item name>`\nExample: `gsell 200000 lucky dice`")

        if price < 1000:
            return await ctx.send("<a:X_:1437951830393884788> Minimum listing price is 1,000 <:mora:1437958309255577681>")

        # Find item
        item_id = None
        item_name_lower = item_name.lower().replace(" ", "_")
        
        for iid, item in ITEMS.items():
            if iid == item_name_lower or item["name"].lower() == item_name.lower():
                item_id = iid
                break

        if item_id is None:
            return await ctx.send("<a:X_:1437951830393884788> Item not found!")

        # Check if user owns it
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                (ctx.author.id, item_id)
            ) as cursor:
                result = await cursor.fetchone()

            if not result or result[0] <= 0:
                return await ctx.send(f"<a:X_:1437951830393884788> You don't own {ITEMS[item_id]['emoji']} **{ITEMS[item_id]['name']}**!")

            # Remove from inventory
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                (ctx.author.id, item_id)
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                (ctx.author.id,)
            )

            # Add listing
            await db.execute(
                "INSERT INTO black_market_listings (seller_id, item_id, price, quantity, listed_at) VALUES (?, ?, ?, 1, ?)",
                (ctx.author.id, item_id, price, datetime.now().isoformat())
            )
            await db.commit()

        embed = discord.Embed(
            title="Item Listed!",
            description=f"Your {ITEMS[item_id]['emoji']} **{ITEMS[item_id]['name']}** is now listed for {price:,} <:mora:1437958309255577681>",
            color=0x3498DB
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.set_footer(text="You'll be notified when someone buys it!")
        await ctx.send(embed=embed)

    @commands.command(name="pm", aliases=["playermarket", "listings"])
    async def view_listings(self, ctx):
        """View player listings on the Black Market"""
        if not await require_enrollment(ctx):
            return

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT listing_id, seller_id, item_id, price FROM black_market_listings ORDER BY price ASC LIMIT 20"
            ) as cursor:
                listings = await cursor.fetchall()

        if not listings:
            embed = discord.Embed(
                title="Player Listings",
                description="No items listed by players yet!\n\nUse `gsell <price> <item>` to list your items.",
                color=0x95A5A6
            )
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            title="📋 Player Listings",
            description="Buy from other players with `gbuylist <listing id>`",
            color=0x000000
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        for listing_id, seller_id, item_id, price in listings:
            if item_id not in ITEMS:
                continue
            
            item = ITEMS[item_id]
            try:
                seller = await self.bot.fetch_user(seller_id)
                seller_name = seller.display_name
            except:
                seller_name = f"User {seller_id}"
            
            value = f"{item['emoji']} **{item['name']}**\n"
            value += f"└ Seller: {seller_name}\n"
            value += f"└ Price: {price:,} <:mora:1437958309255577681>"
            
            embed.add_field(
                name=f"Listing #{listing_id}",
                value=value,
                inline=False
            )

        embed.set_footer(text="Use 'gbl <id>' to purchase")
        await ctx.send(embed=embed)

    @commands.command(name="bl", aliases=["buylist", "buylisting"])
    async def buy_listing(self, ctx, listing_id: int = None):
        """Buy an item from a player listing"""
        if not await require_enrollment(ctx):
            return

        if listing_id is None:
            return await ctx.send("<a:X_:1437951830393884788> Usage: `gbl <listing id>`\nExample: `gbl 5`")

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT seller_id, item_id, price FROM black_market_listings WHERE listing_id = ?",
                (listing_id,)
            ) as cursor:
                result = await cursor.fetchone()

            if not result:
                return await ctx.send("<a:X_:1437951830393884788> Listing not found!")

            seller_id, item_id, price = result

            if seller_id == ctx.author.id:
                return await ctx.send("<a:X_:1437951830393884788> You can't buy your own listing!")

            data = await get_user_data(ctx.author.id)
            mora = data.get("mora", 0)

            if mora < price:
                return await ctx.send(f"<a:X_:1437951830393884788> You need {price:,} <:mora:1437958309255577681>. You have {mora:,}.")

            item = ITEMS[item_id]

            # Check stackability
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                (ctx.author.id, item_id)
            ) as cursor:
                inv_result = await cursor.fetchone()
                current_qty = inv_result[0] if inv_result else 0

            if not item.get("stackable", False) and current_qty > 0:
                return await ctx.send(f"<a:X_:1437951830393884788> You already own {item['emoji']} **{item['name']}** and it's not stackable!")

            # Purchase
            await update_user_data(ctx.author.id, mora=mora - price)

            # Give seller the money
            seller_data = await get_user_data(seller_id)
            await update_user_data(seller_id, mora=seller_data.get("mora", 0) + price)

            # Add to buyer inventory
            if current_qty > 0:
                await db.execute(
                    "UPDATE inventory SET quantity = quantity + 1 WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                )
            else:
                await db.execute(
                    "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, 1)",
                    (ctx.author.id, item_id)
                )

            # Remove listing
            await db.execute(
                "DELETE FROM black_market_listings WHERE listing_id = ?",
                (listing_id,)
            )
            await db.commit()

        # Notify seller
        try:
            seller = await self.bot.fetch_user(seller_id)
            notify_embed = discord.Embed(
                title="💰 Item Sold!",
                description=f"Your {item['emoji']} **{item['name']}** was purchased by **{ctx.author.display_name}** for {price:,} <:mora:1437958309255577681>!",
                color=0x2ECC71
            )
            await seller.send(embed=notify_embed)
        except:
            pass

        embed = discord.Embed(
            title="🎴 Purchase Successful!",
            description=f"You bought {item['emoji']} **{item['name']}** from the player market for {price:,} <:mora:1437958309255577681>",
            color=0x2ECC71
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="items")
    async def view_all_items(self, ctx):
        """View all available items in the game"""
        if not await require_enrollment(ctx):
            return

        # Create paginated view for items
        items_list = list(ITEMS.items())
        
        class ItemPaginator(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)
                self.current_page = 0
                self.max_page = len(items_list) - 1

            def get_embed(self):
                item_id, item = items_list[self.current_page]
                embed = discord.Embed(
                    title=f"{item['emoji']} {item['name']}",
                    description=item['description'],
                    color=RARITY_COLORS.get(item['rarity'], 0x2ECC71)
                )
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
                embed.set_thumbnail(url=ctx.author.display_avatar.url)  # Will show emoji in title
                
                embed.add_field(name="Rarity", value=item['rarity'], inline=True)
                embed.add_field(name="Price", value=f"{item['base_price']:,} <:mora:1437958309255577681>", inline=True)
                embed.add_field(name="Type", value=item['type'].title(), inline=True)
                embed.add_field(name="Duration", value=item['duration'], inline=False)
                embed.add_field(name="Source", value=item['source'], inline=False)
                
                embed.set_footer(text=f"Item {self.current_page + 1}/{len(items_list)} • Use gbm to view the shop")
                return embed

            @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.gray)
            async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("<a:X_:1437951830393884788> This isn't your menu!", ephemeral=True)
                
                self.current_page = (self.current_page - 1) % len(items_list)
                await interaction.response.edit_message(embed=self.get_embed(), view=self)

            @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.gray)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("<a:X_:1437951830393884788> This isn't your menu!", ephemeral=True)
                
                self.current_page = (self.current_page + 1) % len(items_list)
                await interaction.response.edit_message(embed=self.get_embed(), view=self)

        view = ItemPaginator()
        await ctx.send(embed=view.get_embed(), view=view)

    @commands.command(name="restock")
    @commands.is_owner()
    async def force_restock(self, ctx):
        """[Owner] Force restock your personal Black Market"""
        # Clear existing stock to force restock for the owner
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM black_market_stock WHERE user_id = ?", (ctx.author.id,))
            await db.commit()
        
        await restock_market(ctx.author.id)
        await ctx.send("<a:Check:1437951818452832318> Your Black Market restocked with 7 items!")


async def setup(bot):
    await bot.add_cog(BlackMarket(bot))
