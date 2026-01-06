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
                "xp_booster": 0.008,      # 0.8% chance
                "lucky_dice": 0.006,      # 0.6% chance
                "golden_chip": 0.004,     # 0.4% chance
                "bankers_key": 0.002,     # 0.2% chance
                "streak_shield": 0.0015,  # 0.15% chance
                "hot_streak": 0.001,      # 0.1% chance
                "rigged_deck": 0.0005,    # 0.05% chance (ULTRA RARE)
            }
        }
    }
}

# Item emojis mapping
ITEM_EMOJIS = {
    "lucky_dice": "<:dice:1457965149137670186>",
    "golden_chip": "<:goldenchip:1457964285207646264>",
    "xp_booster": "<:exp:1437553839359397928>",
    "bankers_key": "<a:bankerskey:1457962936076075049>",
    "streak_shield": "<a:shield:1457967376799629324>",
    "hot_streak": "<:streak:1457966635838214247>",
    "rigged_deck": "<a:deck:1457965675082551306>",
    "plasma_canon": "<:plasmacanon:1457975521521434624>"
}

ITEM_NAMES = {
    "lucky_dice": "Lucky Dice",
    "golden_chip": "Golden Chip",
    "xp_booster": "XP Booster",
    "bankers_key": "Banker's Key",
    "streak_shield": "Daily Streak Shield",
    "hot_streak": "Hot Streak Card",
    "rigged_deck": "Rigged Deck",
    "plasma_canon": "Plasma Canon"
}


class Chests(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="open", aliases=["openchest"])
    async def open_chest(self, ctx, *, chest_type: str = None):
        """Open a chest from your inventory"""
        if not await require_enrollment(ctx):
            return

        if chest_type is None:
            return await ctx.send("<a:X_:1437951830393884788> Usage: `gopen <chest type>`\nTypes: `regular`, `diamond`, `special`, `random`")

        chest_type = chest_type.lower().replace(" ", "")  # Remove spaces for "special crate"
        
        # Handle special crate separately
        if chest_type in ["special", "specialcrate"]:
            return await self.open_special_crate(ctx)
        
        # Handle random chest separately
        if chest_type == "random":
            return await self.open_random_chest(ctx)
        
        if chest_type not in CHEST_TYPES:
            return await ctx.send("<a:X_:1437951830393884788> Invalid chest type! Use: `regular`, `diamond`, `special`, or `random`")

        # Check if user has the chest (stored in inventory table)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                (ctx.author.id, chest_type)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result or result[0] <= 0:
            return await ctx.send(f"<a:X_:1437951830393884788> You don't have any {CHEST_TYPES[chest_type]['emoji']} **{CHEST_TYPES[chest_type]['name']}**!")

        # Consume one chest
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                (ctx.author.id, chest_type)
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0",
                (ctx.author.id, chest_type)
            )
            await db.commit()

        chest = CHEST_TYPES[chest_type]
        # Generate rewards
        rewards = chest["rewards"]
        mora_reward = random.randint(rewards["mora"][0], rewards["mora"][1])
        xp_reward = random.randint(rewards["xp"][0], rewards["xp"][1])

        # Check for item drops
        items_won = []
        for item_id, chance in rewards["items"].items():
            if random.random() < chance:
                items_won.append(item_id)

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
        if items_won:
            async with aiosqlite.connect(DB_PATH) as db:
                for item_id in items_won:
                    # Check if item exists in inventory
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
            title=f"{chest['emoji']} {chest['name']} Opened!",
            description="**Rewards:**",
            color=0x2ECC71 if items_won else 0x3498DB
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

        if items_won:
            items_text = "\n".join([f"{ITEM_EMOJIS[i]} **{ITEM_NAMES[i]}**" for i in items_won])
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
        mora_reward = random.randint(1000000, 3000000)
        xp_reward = random.randint(3000, 8000)

        # GUARANTEED rare items (3-5 items with better odds)
        num_items = random.randint(3, 5)
        possible_items = list(ITEM_EMOJIS.keys())
        
        # Remove items that shouldn't be in crates
        if "special_crate" in possible_items:
            possible_items.remove("special_crate")  # Can't get crate from crate
        if "plasma_canon" in possible_items:
            possible_items.remove("plasma_canon")  # Plasma canon is black market exclusive
        
        # Guarantee 3 items
        items_won = random.sample(possible_items, 3)
        
        # Remaining items are by chance (0.40 chance each for the remaining slots)
        if num_items > 3:
            remaining_items = [i for i in possible_items if i not in items_won]
            for _ in range(num_items - 3):
                if random.random() < 0.40 and remaining_items:
                    bonus_item = random.choice(remaining_items)
                    items_won.append(bonus_item)
                    remaining_items.remove(bonus_item)

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
            
            # Items (30% total - increased)
            ("item", "lucky_dice", 1, 0.12, ITEM_EMOJIS["lucky_dice"], ITEM_NAMES["lucky_dice"]),
            ("item", "golden_chip", 1, 0.08, ITEM_EMOJIS["golden_chip"], ITEM_NAMES["golden_chip"]),
            ("item", "xp_booster", 1, 0.06, ITEM_EMOJIS["xp_booster"], ITEM_NAMES["xp_booster"]),
            ("item", "streak_shield", 1, 0.03, ITEM_EMOJIS["streak_shield"], ITEM_NAMES["streak_shield"]),
            ("item", "hot_streak", 1, 0.01, ITEM_EMOJIS["hot_streak"], ITEM_NAMES["hot_streak"]),
            
            # Chests (25% total - increased significantly)
            ("chest", "regular", 1, 0.15, CHEST_TYPES["regular"]["emoji"], "Regular Chest"),
            ("chest", "diamond", 1, 0.08, CHEST_TYPES["diamond"]["emoji"], "Diamond Chest"),
            ("chest", "special_crate", 1, 0.02, "<a:crate:1457969509770985492>", "Special Crate"),
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
