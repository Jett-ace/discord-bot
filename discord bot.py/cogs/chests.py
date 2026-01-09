import discord
from discord.ext import commands
import aiosqlite
import random
from config import DB_PATH
from utils.database import get_user_data, update_user_data, require_enrollment
from utils.embed import send_embed


# Chest types with emojis (regular and diamond are found from games/daily, NOT purchasable)
CHEST_TYPES = {
    "regular": {
        "name": "Regular Chest",
        "emoji": "<:regular:1437473086571286699>",
        "rewards": {
            "mora": (10000, 50000),
            "xp": (100, 500),
            "items": {
                "wormbait": 0.15,         # 15% chance - Common bait
                "scorpion": 0.08,         # 8% chance - Uncommon bait
                "xp_booster": 0.003,      # 0.3% chance
                "lucky_dice": 0.002,      # 0.2% chance
                "golden_chip": 0.001,     # 0.1% chance
            }
        }
    },
    "diamond": {
        "name": "Diamond Chest",
        "emoji": "<:dimond:1437473169475764406>",
        "rewards": {
            "mora": (50000, 150000),
            "xp": (500, 1500),
            "items": {
                # Bait items - give 3-7 instead of 1
                "wormbait": 0.08,         # 8% - Common (but gives 3-7)
                "scorpion": 0.06,         # 6% - Common (but gives 3-7)
                
                # Common items (higher odds)
                "xp_booster": 0.15,       # 15% - Common
                "fence": 0.12,            # 12% - Common
                "lock": 0.10,             # 10% - Common
                "lucky_dice": 0.09,       # 9% - Common
                
                # Uncommon items
                "shotgun": 0.08,          # 8% - Uncommon
                "guarddog": 0.07,         # 7% - Uncommon
                "golden_chip": 0.06,      # 6% - Uncommon
                "thiefpack": 0.05,        # 5% - Uncommon
                
                # Rare items
                "double_down": 0.04,      # 4% - Rare
                "bankers_key": 0.035,     # 3.5% - Rare
                "streak_shield": 0.03,    # 3% - Rare
                "ninjapack": 0.025,       # 2.5% - Rare
                
                # Epic items
                "hot_streak": 0.02,       # 2% - Epic
                "card_counter": 0.015,    # 1.5% - Epic
                "piggy_bank": 0.012,      # 1.2% - Epic
                "rigged_deck": 0.01,      # 1% - Epic
                "bank_upgrade": 0.008,    # 0.8% - Epic
                
                # Legendary items (ULTRA RARE)
                "lucky_horseshoe": 0.005, # 0.5% - Legendary
                "plasma_canon": 0.003,    # 0.3% - Legendary
                "special_crate": 0.001,   # 0.1% - Legendary
            }
        }
    }
}

# Item emojis mapping
ITEM_EMOJIS = {
    "wormbait": "<:wormbait:1458986452871282698>",
    "scorpion": "<:scorpion:1458986549722087586>",
    "lucky_dice": "<:dice:1457965149137670186>",
    "golden_chip": "<:goldenchip:1457964285207646264>",
    "xp_booster": "<:exp:1437553839359397928>",
    "bankers_key": "<a:bankerskey:1457962936076075049>",
    "streak_shield": "<a:shield:1457967376799629324>",
    "hot_streak": "<:streak:1457966635838214247>",
    "rigged_deck": "<a:deck:1457965675082551306>",
    "plasma_canon": "<:plasmacanon:1457975521521434624>",
    "card_counter": "<a:counter:1458347417329209426>",
    "double_down": "<:doubledown:1458351562966565037>",
    "piggy_bank": "<:goldenbank:1458347495183876210>",
    "lucky_horseshoe": "<:luckyhorseshoe:1458353830704975884>",
    "bank_upgrade": "<:upgrade:1457983244682268695>",
    "shotgun": "<:shotgun:1458773713418977364>",
    "thiefpack": "🎒",
    "guarddog": "🐕",
    "fence": "<:fench:1458002114260242454>",
    "lock": "🔒",
    "ninjapack": "<:ninja:1458503378450780408>",
    "special_crate": "<a:crate:1457969509770985492>"
}

ITEM_NAMES = {
    "wormbait": "Wormbait",
    "scorpion": "Scorpion",
    "lucky_dice": "Lucky Dice",
    "golden_chip": "Golden Chip",
    "xp_booster": "XP Booster",
    "bankers_key": "Banker's Key",
    "streak_shield": "Daily Streak Shield",
    "hot_streak": "Hot Streak Card",
    "rigged_deck": "Rigged Deck",
    "plasma_canon": "Plasma Cannon",
    "card_counter": "Card Counter",
    "double_down": "Double Down Card",
    "piggy_bank": "Golden Piggy Bank",
    "lucky_horseshoe": "Lucky Horseshoe",
    "bank_upgrade": "Bank Upgrade",
    "shotgun": "Shotgun",
    "thiefpack": "Thief Pack",
    "guarddog": "Guard Dog",
    "fence": "Spiky Fence",
    "lock": "Lock",
    "ninjapack": "Ninja Pack",
    "special_crate": "Special Crate"
}


class Chests(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="open", aliases=["openchest"])
    async def open_chest(self, ctx, chest_type: str = None, amount: int = 1):
        """Open chest(s) from your inventory. Max 5 at once for regular/diamond."""
        if not await require_enrollment(ctx):
            return

        if chest_type is None:
            return await ctx.send("<a:X_:1437951830393884788> Usage: `gopen <chest type> [amount]`\nTypes: `regular`, `diamond`, `special`, `random`\nExample: `gopen diamond 5`")

        # Validate amount
        if amount < 1:
            return await ctx.send("<a:X_:1437951830393884788> Amount must be at least 1!")
        if amount > 5:
            return await ctx.send("<a:X_:1437951830393884788> You can only open up to 5 chests at once!")

        chest_input = chest_type.lower().replace(" ", "")  # Remove spaces for "special crate"
        
        # Try to match chest by name or alias
        matched_chest = None
        
        # Simple matching for chest types
        if chest_input in ["regular", "reg"]:
            matched_chest = "regular"
        elif chest_input in ["diamond", "dia", "dimond"]:
            matched_chest = "diamond"
        elif chest_input in ["special", "specialcrate", "crate"]:
            if amount > 1:
                return await ctx.send("<a:X_:1437951830393884788> You can only open 1 special crate at a time!")
            return await self.open_special_crate(ctx)
        elif chest_input == "random":
            if amount > 1:
                return await ctx.send("<a:X_:1437951830393884788> You can only open 1 random chest at a time!")
            return await self.open_random_chest(ctx)
        
        # For regular and diamond chests
        if matched_chest not in ["regular", "diamond"]:
            return await ctx.send("<a:X_:1437951830393884788> Invalid chest type! Use: `regular`, `diamond`, `special`, or `random`")
        
        chest_type = matched_chest  # Use the matched chest ID

        # Check if user has the chest (stored in inventory table)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                (ctx.author.id, chest_type)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result or result[0] < amount:
            available = result[0] if result else 0
            return await ctx.send(f"<a:X_:1437951830393884788> You don't have enough {CHEST_TYPES[chest_type]['emoji']} **{CHEST_TYPES[chest_type]['name']}**! You have {available}, need {amount}.")

        # Consume chests
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ?",
                (amount, ctx.author.id, chest_type)
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0",
                (ctx.author.id, chest_type)
            )
            await db.commit()

        chest = CHEST_TYPES[chest_type]
        
        # Track totals across all chests
        total_mora = 0
        total_xp = 0
        all_items_won = []
        item_quantities = {}  # Track quantities for display (especially for multi-bait)
        
        # Open each chest
        for _ in range(amount):
            # Generate rewards
            rewards = chest["rewards"]
            mora_reward = random.randint(rewards["mora"][0], rewards["mora"][1])
            xp_reward = random.randint(rewards["xp"][0], rewards["xp"][1])
            total_mora += mora_reward
            total_xp += xp_reward

            # Guaranteed item drops based on chest type
            items_won = []
            
            if chest_type == "regular":
                # Regular chest: 1-2 guaranteed items with weighted selection
                num_items = random.randint(1, 2)
                item_pool = list(rewards["items"].keys())
                # Use actual probabilities as weights (higher prob = more common)
                weights = [rewards["items"][item] for item in item_pool]
                for _ in range(num_items):
                    if item_pool:
                        chosen = random.choices(item_pool, weights=weights, k=1)[0]
                        items_won.append(chosen)
                        # Remove chosen item to avoid duplicates in same chest
                        idx = item_pool.index(chosen)
                        item_pool.pop(idx)
                        weights.pop(idx)
            
            elif chest_type == "diamond":
                # Diamond chest: 2-4 guaranteed items with weighted selection
                num_items = random.randint(2, 4)
                item_pool = list(rewards["items"].keys())
                # Use actual probabilities as weights (higher prob = more common)
                weights = [rewards["items"][item] for item in item_pool]
                for _ in range(num_items):
                    if item_pool:
                        chosen = random.choices(item_pool, weights=weights, k=1)[0]
                        items_won.append(chosen)
                        # Remove chosen item to avoid duplicates in same chest
                        idx = item_pool.index(chosen)
                        item_pool.pop(idx)
                        weights.pop(idx)
            
            all_items_won.extend(items_won)

        # Award mora
        await update_user_data(ctx.author.id, mora=(await get_user_data(ctx.author.id))["mora"] + total_mora)

        # Award XP
        try:
            from utils.database import add_account_exp, has_xp_booster
            exp_to_add = total_xp
            if await has_xp_booster(ctx.author.id):
                exp_to_add = int(exp_to_add * 1.5)
            leveled_up, new_level, old_level = await add_account_exp(ctx.author.id, exp_to_add)
        except Exception:
            leveled_up = False
            new_level = 0

        # Award items
        if all_items_won:
            async with aiosqlite.connect(DB_PATH) as db:
                for item_id in all_items_won:
                    # For bait items from diamond chests, give 3-7 instead of 1
                    quantity_to_add = 1
                    if chest_type == "diamond" and item_id in ["wormbait", "scorpion"]:
                        quantity_to_add = random.randint(3, 7)
                    
                    # Track total quantities for display
                    if item_id not in item_quantities:
                        item_quantities[item_id] = 0
                    item_quantities[item_id] += quantity_to_add
                    
                    # Check if item exists in inventory
                    async with db.execute(
                        "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                        (ctx.author.id, item_id)
                    ) as cursor:
                        result = await cursor.fetchone()
                    
                    if result:
                        await db.execute(
                            "UPDATE inventory SET quantity = quantity + ? WHERE user_id = ? AND item_id = ?",
                            (quantity_to_add, ctx.author.id, item_id)
                        )
                    else:
                        await db.execute(
                            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)",
                            (ctx.author.id, item_id, quantity_to_add)
                        )
                await db.commit()

        # Build result embed
        chest_plural = f"{amount}x " if amount > 1 else ""
        embed = discord.Embed(
            title=f"{chest_plural}{chest['name']} Opened!",
            description="**Total Rewards:**",
            color=0x2ECC71 if all_items_won else 0x3498DB
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        # Add chest emoji as thumbnail
        import re
        chest_emoji_str = chest['emoji']
        match = re.match(r'<(a?):[^:]+:(\d+)>', chest_emoji_str)
        if match:
            animated, emoji_id = match.groups()
            ext = 'gif' if animated else 'png'
            chest_icon_url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{ext}'
            embed.set_thumbnail(url=chest_icon_url)

        embed.add_field(
            name="<:mora:1437958309255577681> Mora",
            value=f"+{total_mora:,}",
            inline=True
        )
        embed.add_field(
            name="<:exp:1437553839359397928> XP",
            value=f"+{exp_to_add:,}",
            inline=True
        )

        if all_items_won:
            # Use the tracked quantities instead of just counting list items
            # This way bait shows the actual 3-7 quantity given
            
            # Separate chests and other items
            chest_items = []
            other_items = []
            
            for item_id in sorted(item_quantities.keys()):
                count = item_quantities[item_id]
                item_line = f"{ITEM_EMOJIS[item_id]} **{ITEM_NAMES[item_id]}** x{count}" if count > 1 else f"{ITEM_EMOJIS[item_id]} **{ITEM_NAMES[item_id]}**"
                if "chest" in item_id or item_id == "special_crate":
                    chest_items.append(item_line)
                else:
                    other_items.append(item_line)
            
            # Display chests first, then other items
            items_text = "\n".join(chest_items + other_items)
            embed.add_field(
                name="Bonus Items",
                value=items_text,
                inline=False
            )

        if leveled_up:
            embed.add_field(
                name="<a:Trophy:1438199339586424925> Level Up!",
                value=f"You reached level **{new_level}**!",
                inline=False
            )

        await ctx.send(embed=embed)

    async def open_special_crate(self, ctx):
        """Open a Special Crate (guaranteed rare items)"""
        # Check if user has special crate
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = 'special_crate'",
                (ctx.author.id,)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result or result[0] <= 0:
            return await ctx.send("<a:X_:1437951830393884788> You don't have any <a:crate:1457969509770985492> **Special Crates**! Buy them from the Black Market.")

        # Consume one crate
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = 'special_crate'",
                (ctx.author.id,)
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND quantity <= 0",
                (ctx.author.id,)
            )
            await db.commit()

        # Generate rewards (MUCH better than normal chests)
        mora_reward = random.randint(2000000, 5000000)  # Increased from 1-3M to 2-5M
        xp_reward = random.randint(5000, 12000)  # Increased from 3-8K to 5-12K

        # GUARANTEED rare items (4-6 items with MUCH better odds for rares)
        num_items = random.randint(4, 6)  # Increased from 3-5 to 4-6
        
        # Weighted item pool (higher weight = more likely)
        # Balance for 25M crate - good chance at rares but not guaranteed every time
        item_weights = {
            "lucky_dice": 30,          # Most common
            "golden_chip": 25,         # Common
            "xp_booster": 20,          # Uncommon
            "battery": 18,             # Uncommon (Epic) - Energy refill
            "bankers_key": 15,         # Rare
            "double_down": 14,         # Rare (Epic)
            "rigged_deck": 12,         # Rare
            "card_counter": 10,        # Very rare (Legendary)
            "piggy_bank": 9,           # Very rare (Legendary)
            "streak_shield": 8,        # Very rare
            "hot_streak": 5,           # Ultra rare
            "plasma_canon": 3,         # Rarest
            "lucky_horseshoe": 2       # Mythic rarest! (Best from 25M crate)
        }
        
        items_won = []
        available_items = list(item_weights.keys())
        weights = list(item_weights.values())
        
        # Pick items with weighted random (no duplicates)
        for _ in range(min(num_items, len(available_items))):
            chosen = random.choices(available_items, weights=weights, k=1)[0]
            items_won.append(chosen)
            # Remove chosen item so no duplicates
            idx = available_items.index(chosen)
            available_items.pop(idx)
            weights.pop(idx)

        # Award mora
        await update_user_data(ctx.author.id, mora=(await get_user_data(ctx.author.id))["mora"] + mora_reward)

        # Award XP
        try:
            from utils.database import add_account_exp, has_xp_booster
            exp_to_add = xp_reward
            if await has_xp_booster(ctx.author.id):
                exp_to_add = int(exp_to_add * 1.5)
            leveled_up, new_level, old_level = await add_account_exp(ctx.author.id, exp_to_add)
        except Exception:
            leveled_up = False
            new_level = 0

        # Award items
        async with aiosqlite.connect(DB_PATH) as db:
            for item_id in items_won:
                async with db.execute(
                    "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                ) as cursor:
                    result = await cursor.fetchone()
                
                if result:
                    await db.execute(
                        "UPDATE inventory SET quantity = quantity + 1 WHERE user_id = ? AND item_id = ?",
                        (ctx.author.id, item_id)
                    )
                else:
                    await db.execute(
                        "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, 1)",
                        (ctx.author.id, item_id)
                    )
            await db.commit()

        # Build result embed
        embed = discord.Embed(
            title="<a:crate:1457969509770985492> Special Crate Opened!",
            description="**Premium Rewards:**",
            color=0xF1C40F
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        embed.add_field(
            name="<:mora:1437958309255577681> Mora",
            value=f"+{mora_reward:,}",
            inline=True
        )
        embed.add_field(
            name="<:exp:1437553839359397928> XP",
            value=f"+{exp_to_add:,}",
            inline=True
        )

        items_text = "\n".join([f"{ITEM_EMOJIS[i]} **{ITEM_NAMES[i]}**" for i in items_won])
        embed.add_field(
            name="Items Received",
            value=items_text,
            inline=False
        )

        if leveled_up:
            embed.add_field(
                name="<a:Trophy:1438199339586424925> Level Up!",
                value=f"You reached level **{new_level}**!",
                inline=False
            )

        await ctx.send(embed=embed)

    async def open_random_chest(self, ctx):
        """Open a Random Chest (gives you random rewards: mora, XP, items, or other chests)"""
        # Check if user has random chest
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = 'random'",
                (ctx.author.id,)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result or result[0] <= 0:
            return await ctx.send("<a:X_:1437951830393884788> You don't have any <:random:1437977751520018452> **Random Chests**!")

        # Consume one random chest
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = 'random'",
                (ctx.author.id,)
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND item_id = 'random' AND quantity <= 0",
                (ctx.author.id,)
            )
            await db.commit()

        # Define possible rewards with their drop rates
        rewards_pool = [
            # Mora rewards (30% total - reduced)
            ("mora", 50000, 150000, 0.15, "<:mora:1437958309255577681>", "Mora"),
            ("mora", 150000, 300000, 0.10, "<:mora:1437958309255577681>", "Mora"),
            ("mora", 300000, 750000, 0.05, "<:mora:1437958309255577681>", "Mora"),
            
            # XP rewards (15% total - reduced)
            ("xp", 500, 2000, 0.10, "<:exp:1437553839359397928>", "XP"),
            ("xp", 2000, 4000, 0.05, "<:exp:1437553839359397928>", "XP"),
            
            # Items - Common (higher odds)
            ("item", "xp_booster", 1, 0.12, ITEM_EMOJIS["xp_booster"], ITEM_NAMES["xp_booster"]),
            ("item", "fence", 1, 0.10, ITEM_EMOJIS["fence"], ITEM_NAMES["fence"]),
            ("item", "lock", 1, 0.08, ITEM_EMOJIS["lock"], ITEM_NAMES["lock"]),
            
            # Items - Uncommon
            ("item", "lucky_dice", 1, 0.12, ITEM_EMOJIS["lucky_dice"], ITEM_NAMES["lucky_dice"]),
            ("item", "shotgun", 1, 0.07, ITEM_EMOJIS["shotgun"], ITEM_NAMES["shotgun"]),
            ("item", "guarddog", 1, 0.06, ITEM_EMOJIS["guarddog"], ITEM_NAMES["guarddog"]),
            
            # Items - Rare
            ("item", "golden_chip", 1, 0.08, ITEM_EMOJIS["golden_chip"], ITEM_NAMES["golden_chip"]),
            ("item", "thiefpack", 1, 0.05, ITEM_EMOJIS["thiefpack"], ITEM_NAMES["thiefpack"]),
            
            # Items - Epic
            ("item", "double_down", 1, 0.04, ITEM_EMOJIS["double_down"], ITEM_NAMES["double_down"]),
            ("item", "streak_shield", 1, 0.03, ITEM_EMOJIS["streak_shield"], ITEM_NAMES["streak_shield"]),
            ("item", "bankers_key", 1, 0.02, ITEM_EMOJIS["bankers_key"], ITEM_NAMES["bankers_key"]),
            
            # Items - Legendary (SUPER RARE)
            ("item", "card_counter", 1, 0.015, ITEM_EMOJIS["card_counter"], ITEM_NAMES["card_counter"]),
            ("item", "piggy_bank", 1, 0.012, ITEM_EMOJIS["piggy_bank"], ITEM_NAMES["piggy_bank"]),
            ("item", "hot_streak", 1, 0.01, ITEM_EMOJIS["hot_streak"], ITEM_NAMES["hot_streak"]),
            ("item", "rigged_deck", 1, 0.008, ITEM_EMOJIS["rigged_deck"], ITEM_NAMES["rigged_deck"]),
            ("item", "bank_upgrade", 1, 0.006, ITEM_EMOJIS["bank_upgrade"], ITEM_NAMES["bank_upgrade"]),
            
            # Items - Mythic (ULTRA RARE)
            ("item", "lucky_horseshoe", 1, 0.005, ITEM_EMOJIS["lucky_horseshoe"], ITEM_NAMES["lucky_horseshoe"]),
            ("item", "plasma_canon", 1, 0.003, ITEM_EMOJIS["plasma_canon"], ITEM_NAMES["plasma_canon"]),
            
            # Chests (25% total - increased significantly)
            ("chest", "regular", 1, 0.15, CHEST_TYPES["regular"]["emoji"], "Regular Chest"),
            ("chest", "diamond", 1, 0.10, CHEST_TYPES["diamond"]["emoji"], "Diamond Chest"),
        ]

        # Select reward based on probabilities
        reward_types = [r[0] for r in rewards_pool]
        probabilities = [r[3] for r in rewards_pool]
        selected_reward = random.choices(rewards_pool, weights=probabilities, k=1)[0]

        reward_type = selected_reward[0]
        reward_emoji = selected_reward[4]
        reward_name = selected_reward[5]

        # Process the reward
        if reward_type == "mora":
            min_amount, max_amount = selected_reward[1], selected_reward[2]
            amount = random.randint(min_amount, max_amount)
            await update_user_data(ctx.author.id, mora=(await get_user_data(ctx.author.id))["mora"] + amount)
            reward_text = f"+{amount:,} {reward_emoji} **{reward_name}**"

        elif reward_type == "xp":
            min_amount, max_amount = selected_reward[1], selected_reward[2]
            amount = random.randint(min_amount, max_amount)
            try:
                from utils.database import add_account_exp, has_xp_booster
                exp_to_add = amount
                if await has_xp_booster(ctx.author.id):
                    exp_to_add = int(exp_to_add * 1.5)
                leveled_up, new_level, old_level = await add_account_exp(ctx.author.id, exp_to_add)
            except Exception:
                leveled_up = False
                new_level = 0
            reward_text = f"+{exp_to_add:,} {reward_emoji} **{reward_name}**"

        elif reward_type == "item":
            item_id = selected_reward[1]
            amount = selected_reward[2]
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, item_id)
                ) as cursor:
                    result = await cursor.fetchone()
                
                if result:
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
            reward_text = f"+{amount}x {reward_emoji} **{reward_name}**"
            leveled_up = False

        elif reward_type == "chest":
            chest_type = selected_reward[1]
            amount = selected_reward[2]
            
            # All chests go in inventory table
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                    (ctx.author.id, chest_type)
                ) as cursor:
                    result = await cursor.fetchone()
                
                if result:
                    await db.execute(
                        "UPDATE inventory SET quantity = quantity + ? WHERE user_id = ? AND item_id = ?",
                        (amount, ctx.author.id, chest_type)
                    )
                else:
                    await db.execute(
                        "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)",
                        (ctx.author.id, chest_type, amount)
                    )
                await db.commit()
            reward_text = f"+{amount}x {reward_emoji} **{reward_name}**"
            leveled_up = False

        # Build result embed
        embed = discord.Embed(
            title="<:random:1437977751520018452> Random Chest Opened!",
            description=f"**You received:**\n{reward_text}",
            color=0xF39C12
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        if reward_type == "xp" and leveled_up:
            embed.add_field(
                name="<a:Trophy:1438199339586424925> Level Up!",
                value=f"You reached level **{new_level}**!",
                inline=False
            )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Chests(bot))
