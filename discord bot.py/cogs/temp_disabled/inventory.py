import random

import aiosqlite
import discord
from discord.ext import commands

from config import DB_PATH
from utils.constants import rarity_emojis
from utils.database import (
    add_account_exp,
    add_user_item,
    award_achievement,
    change_chest_type_count,
    ensure_user_db,
    get_account_level,
    get_chest_inventory,
    get_shop_item_purchases_today,
    get_user_data,
    get_user_item_count,
    get_user_pulls,
    grant_level_rewards,
    update_user_data,
    require_enrollment,
)
from utils.embed import send_embed


class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Shop items keyed by numeric ID for easy purchase via `gbuy <id> <amount>`
        # id: {key, name, price, daily_cap}
        self.shop_items = {
            1: {
                "key": "random",
                "name": "<:random:1437977751520018452> Random Chest",
                "price": 5_000,
                "daily_cap": 20,
            },
            2: {
                "key": "exp_bottle",
                "name": "EXP Bottle (250 EXP)",
                "price": 15_000,
                "daily_cap": 100,
            },
            3: {
                "key": "rod_shard",
                "name": "🔧 Rod Shard",
                "price": 10_000,
                "daily_cap": 10,
            },
            4: {
                "key": "fish_bait",
                "name": "🪱 Fish Bait",
                "price": 5_000,
                "daily_cap": 20,
            },
        }

    @commands.command(name="chest")
    async def open_chest(self, ctx, *inv_args):
        """Open chests. Usage examples:
        - `gchest` opens 1 common chest
        - `gchest 3` opens 3 common chests
        - `gchest exquisite 2` opens 2 exquisite chests
        Accepts flexible parsing; chest type and amount can be provided in any order.
        """
        if not await require_enrollment(ctx):
            return
        try:
            # flexible args parsing: chest type and amount
            # Now enforce: when opening more than 1 chest, the user MUST specify the chest type.
            allowed = ("common", "exquisite", "precious", "luxurious")
            chest_type = "common"
            qty = 1
            parts = ctx.message.content.strip().split()
            args = parts[1:]

            if len(args) == 0:
                chest_type = "common"
                qty = 1
            elif len(args) == 1:
                # single token: could be a type or an amount
                if args[0].isdigit():
                    qty = int(args[0])
                    # require explicit type when qty > 1
                    if qty > 1:
                        await ctx.send(
                            "When opening more than 1 chest you must specify the chest type. Example: `gchest common 10`\nValid types: common, exquisite, precious, luxurious"
                        )
                        return
                    chest_type = "common"
                else:
                    chest_type = args[0].lower()
                    qty = 1
            else:
                # two or more args: first is type, second is amount
                chest_type = args[0].lower()
                try:
                    qty = int(args[1])
                except Exception:
                    await ctx.send(
                        "Please provide a numeric amount. Usage: `gchest <type> <amount>`"
                    )
                    return

            if qty < 1:
                await ctx.send("Amount must be at least 1.")
                return

            # normalize and validate chest type
            if chest_type not in allowed:
                await ctx.send(
                    "Unknown chest type. Valid types: common, exquisite, precious, luxurious"
                )
                return

            inv = await get_chest_inventory(ctx.author.id)
            available = inv.get(chest_type, 0)
            if available < qty:
                await ctx.send(f"You only have {available} {chest_type} chest(s).")
                return

            total_mora = 0
            total_dust = 0
            total_fates = 0
            total_bottles = 0

            for _ in range(qty):
                if chest_type == "common":
                    reward_mora = random.randint(200, 600)
                    reward_dust = random.randint(10, 25)
                    reward_fate = 1 if random.random() < 0.05 else 0
                    # common: 80% chance to give 1 bottle, 10% chance to double to 2
                    bottles = 0
                    if random.random() < 0.80:
                        bottles = 1
                        if random.random() < 0.10:
                            bottles = 2
                    total_bottles += bottles
                elif chest_type == "exquisite":
                    reward_mora = random.randint(500, 1100)
                    reward_dust = random.randint(25, 55)
                    reward_fate = 1 if random.random() < 0.15 else 0
                    # exquisite: 1 bottle guaranteed, 10% chance to double
                    bottles = 1
                    if random.random() < 0.10:
                        bottles = 2
                    total_bottles += bottles
                elif chest_type == "precious":
                    reward_mora = random.randint(1000, 2200)
                    reward_dust = random.randint(50, 120)
                    reward_fate = 1
                    # precious may sometimes grant an extra fate (10%)
                    if random.random() < 0.10:
                        reward_fate += 1
                    # precious: 1 bottle guaranteed, 50% chance to double
                    bottles = 1
                    if random.random() < 0.50:
                        bottles = 2
                    total_bottles += bottles
                elif chest_type == "luxurious":
                    reward_mora = random.randint(2000, 4200)
                    reward_dust = random.randint(100, 260)
                    reward_fate = 1
                    # luxurious: 20% chance to double fate
                    if random.random() < 0.20:
                        reward_fate += 1
                    # luxurious: gives 2 bottles, 20% chance to double to 4
                    bottles = 2
                    if random.random() < 0.20:
                        bottles = 4
                    total_bottles += bottles
                else:
                    # treat unknown as common
                    reward_mora = random.randint(200, 600)
                    reward_dust = random.randint(10, 25)
                    reward_fate = 1 if random.random() < 0.05 else 0

                total_mora += reward_mora
                total_dust += reward_dust
                total_fates += reward_fate
                # decrement one chest immediately to ensure it's consumed even if later steps fail
                try:
                    await change_chest_type_count(ctx.author.id, chest_type, -1)
                except ValueError as ve:
                    # not enough chests (race or concurrent change); stop and inform user
                    await ctx.send(f"Could not open {chest_type} chest: {ve}")
                    break
                except Exception as e:
                    print(
                        f"Failed to decrement {chest_type} chest for user {ctx.author.id} during open loop: {e}"
                    )
                    await ctx.send("Internal error while opening the chest.")
                    break

            # apply accumulated rewards once
            data = await get_user_data(ctx.author.id)
            data["mora"] += total_mora
            data["dust"] += total_dust
            data["fates"] += total_fates
            await update_user_data(
                ctx.author.id, mora=data["mora"], dust=data["dust"], fates=data["fates"]
            )

            # cap bottles to a maximum of 5 across the entire open operation
            if total_bottles > 0:
                capped = min(total_bottles, 5)
                try:
                    await add_user_item(ctx.author.id, "exp_bottle", capped)
                except Exception as e:
                    print(f"Failed to add exp bottles to user inventory: {e}")
                total_bottles = capped

            # Award a simple "first chest" achievement (idempotent)
            try:
                await award_achievement(
                    ctx.author.id,
                    "first_chest",
                    "Opened a Chest",
                    "You opened your first chest.",
                )
            except Exception:
                pass

            # award account EXP for opening chests (tunable per chest rarity)
            try:
                chest_exp_map = {
                    "common": 10,
                    "exquisite": 25,
                    "precious": 50,
                    "luxurious": 100,
                }
                gained_exp = chest_exp_map.get(chest_type, 10) * qty
                await add_account_exp(ctx.author.id, gained_exp, source="chest")
            except Exception as e:
                print(f"Error awarding account EXP for chest open: {e}")
            
            # Update quest progress
            try:
                quests_cog = self.bot.get_cog('Quests')
                if quests_cog:
                    await quests_cog.update_quest_progress(ctx.author.id, 'chest', qty)
            except:
                pass

            # inventory updated; no debug logging here

            # Try to get custom emoji; fallback to unicode icons
            mora_emoji = "<:mora:1437958309255577681>"
            dust_emoji = "<:mora:1437480155952975943>"
            fate_emoji = "<:fate:1437488656767254528>"

            # Chest icons
            chest_icons = {
                "common": "<:cajitadelexplorador:1437473147833286676>",
                "exquisite": "<:cajitaplatino:1437473086571286699>",
                "precious": "<:cajitapremium:1437473125095837779>",
                "luxurious": "<:cajitadiamante:1437473169475764406>",
            }
            chest_icon = chest_icons.get(chest_type, "")

            embed = discord.Embed(
                title=f"{chest_icon} Opened {qty} {chest_type.capitalize()} Chest{'s' if qty != 1 else ''}!",
                color=0xFFD700,  # Gold color
            )

            # Build rewards list like inventory format
            rewards = []
            rewards.append(f"{mora_emoji}  Mora : `{total_mora:,}`")
            rewards.append(f"{dust_emoji}  Tide Coins : `{total_dust}`")
            if total_fates:
                rewards.append(f"{fate_emoji}  Intertwined Fate(s) : `{total_fates}`")
            if total_bottles:
                rewards.append(
                    f"<:exp:1437553839359397928>  EXP Bottle(s) : `{total_bottles}`"
                )

            embed.description = "\n".join(rewards)
            await send_embed(ctx, embed)
        except Exception as e:
            from utils.logger import setup_logger

            logger = setup_logger("Inventory")
            logger.error(f"Error in chest command: {e}", exc_info=True)
            await ctx.send("❌ There was an error opening the chest. Please try again.")

    @commands.command(name="inventory", aliases=["inv"])
    async def inventory(self, ctx):
        # inventory command invoked
        if not await require_enrollment(ctx):
            return

        await ensure_user_db(ctx.author.id)
        data = await get_user_data(ctx.author.id)
        chest_inv = await get_chest_inventory(ctx.author.id)
        items = []
        if data["fates"] > 0:
            items.append(
                f"<:fate:1437488656767254528>  Intertwined Fates : `{data['fates']}`"
            )
        chest_icons = {
            "common": "<:cajitadelexplorador:1437473147833286676>",
            "exquisite": "<:cajitaplatino:1437473086571286699>",
            "precious": "<:cajitapremium:1437473125095837779>",
            "luxurious": "<:cajitadiamante:1437473169475764406>",
        }
        for k in ("common", "exquisite", "precious", "luxurious"):
            cnt = chest_inv.get(k, 0)
            if cnt:
                items.append(f"{chest_icons[k]}  {k.capitalize()} Chests : `{cnt}`")

        try:
            bottles = await get_user_item_count(ctx.author.id, "exp_bottle")
            if bottles:
                items.append(f"<:exp:1437553839359397928>  EXP Bottles : `{bottles}`")

            hydro_essence = await get_user_item_count(ctx.author.id, "hydro_essence")
            if hydro_essence:
                items.append(
                    f"<:essence:1437463601479942385>  Hydro Essence : `{hydro_essence}`"
                )

            hydro_crystal = await get_user_item_count(ctx.author.id, "hydro_crystal")
            if hydro_crystal:
                items.append(
                    f"<:crystal:1437458982989205624>  Hydro Crystal : `{hydro_crystal}`"
                )

            rod_shards = await get_user_item_count(ctx.author.id, "rod_shard")
            if rod_shards:
                items.append(f"🔧  Rod Shards : `{rod_shards}`")

            fish_bait = await get_user_item_count(ctx.author.id, "fish_bait")
            if fish_bait:
                items.append(f"🪱  Fish Bait : `{fish_bait}`")
        except Exception:
            pass

        description = "\n".join(items) if items else "No items in inventory."
        from cogs.settings import get_user_embed_color
        color = await get_user_embed_color(ctx.author.id, "inv", 0x2ECC71)
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Inventory",
            description=description,
            color=color,
        )
        await send_embed(ctx, embed)

    @commands.group(name="shop", invoke_without_command=True)
    async def shop(self, ctx):
        """Show shop items and pricing."""
        # Get daily purchases for this user
        bought_random = await get_shop_item_purchases_today(ctx.author.id, "random")
        bought_bottles = await get_shop_item_purchases_today(
            ctx.author.id, "exp_bottle"
        )

        embed = discord.Embed(title="Shop", color=0x3498DB)
        lines = []

        lines.append(
            f"1. <:random:1437977751520018452> Random Chest - `{5_000:,}` <:mora:1437958309255577681> - {bought_random}/20"
        )

        lines.append(
            f"2. <:exp:1437553839359397928> EXP Bottle - `{15_000:,}` <:mora:1437958309255577681> - {bought_bottles}/100"
        )

        embed.description = "\n".join(lines)
        await send_embed(ctx, embed)

    @shop.command(name="buy")
    async def shop_buy(self, ctx, item: str = None, amount: int = 1):
        """Buy items from the shop. Usage: gshop buy random 3"""
        try:
            # Allow string names or numeric IDs passed as string
            item_key = None
            if item is None:
                await ctx.send("Usage: `gshop buy <item> <amount>`\nExample: `gshop buy chest 5`")
                return
            # try parse as ID
            try:
                iid = int(item)
                entry = self.shop_items.get(iid)
                if not entry:
                    await ctx.send(f"No shop item with id {iid}.")
                    return
                item_key = entry["key"]
                PRICE = entry["price"]
                DAILY_CAP = entry["daily_cap"]
            except Exception:
                # treat as name
                item_l = item.lower()
                if item_l in ("random", "random_chest", "chest", "randomchest"):
                    item_key = "random"
                    PRICE = 5_000
                    DAILY_CAP = 20
                elif item_l in ("exp bottle", "exp_bottle", "expbottle", "bottle"):
                    item_key = "exp_bottle"
                    PRICE = 15_000
                    DAILY_CAP = 100
                elif item_l in ("rod shard", "rod_shard", "rodshard", "shard"):
                    item_key = "rod_shard"
                    PRICE = 10_000
                    DAILY_CAP = 10
                elif item_l in ("fish bait", "fish_bait", "fishbait", "bait"):
                    item_key = "fish_bait"
                    PRICE = 5_000
                    DAILY_CAP = 20
                else:
                    await ctx.send(
                        "Usage: `gshop buy <id|name> <amount>` - supported: `random`, `exp bottle`, `rod shard`, `fish bait`."
                    )
                    return

            # clamp amount
            try:
                qty = int(amount)
            except Exception:
                qty = 1
            if qty < 1:
                await ctx.send("Amount must be at least 1.")
                return

            # daily cap (use per-item counter for item-specific caps)
            if item_key in ("exp_bottle", "random", "rod_shard", "fish_bait"):
                bought_today = await get_shop_item_purchases_today(
                    ctx.author.id, item_key
                )
            else:
                bought_today = await get_shop_item_purchases_today(
                    ctx.author.id, item_key
                )
            remaining = max(0, DAILY_CAP - bought_today)
            if remaining <= 0:
                await ctx.send(
                    "You've reached the daily purchase limit for this item. Come back tomorrow."
                )
                return
            if qty > remaining:
                await ctx.send(
                    f"You can only buy up to {remaining} more of this item today."
                )
                return
            total_cost = PRICE * qty
            data = await get_user_data(ctx.author.id)
            if data.get("mora", 0) < total_cost:
                await ctx.send(
                    f"You need {total_cost:,} Mora to buy {qty} chest(s). Your balance: {data.get('mora', 0):,} Mora."
                )
                return

            if item_key in ("exp_bottle", "rod_shard", "fish_bait"):
                # store items in user inventory
                try:
                    # ensure user rows exist
                    await ensure_user_db(ctx.author.id)
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("BEGIN")
                        # check balance
                        async with db.execute(
                            "SELECT mora FROM users WHERE user_id=?", (ctx.author.id,)
                        ) as cur:
                            row = await cur.fetchone()
                            cur_mora = int(row[0] or 0) if row else 0
                        if cur_mora < total_cost:
                            await db.execute("ROLLBACK")
                            await ctx.send(
                                f"You need {total_cost:,} Mora to buy {qty} item(s). Your balance: {cur_mora:,} Mora."
                            )
                            return
                        new_mora = cur_mora - total_cost
                        await db.execute(
                            "UPDATE users SET mora=? WHERE user_id=?",
                            (new_mora, ctx.author.id),
                        )

                        # upsert user_items for the item
                        await db.execute(
                            "INSERT OR IGNORE INTO user_items (user_id, item_key, count) VALUES (?, ?, ?)",
                            (ctx.author.id, item_key, 0),
                        )
                        await db.execute(
                            "UPDATE user_items SET count = count + ? WHERE user_id=? AND item_key=?",
                            (qty, ctx.author.id, item_key),
                        )
                        # upsert per-item and global daily counters
                        today = __import__("datetime").date.today().isoformat()
                        await db.execute(
                            "INSERT INTO shop_item_purchases (user_id, date, item_key, count) VALUES (?, ?, ?, ?) ON CONFLICT(user_id, date, item_key) DO UPDATE SET count = shop_item_purchases.count + ?",
                            (ctx.author.id, today, item_key, qty, qty),
                        )
                        await db.execute(
                            "INSERT INTO shop_purchases (user_id, date, count) VALUES (?, ?, ?) ON CONFLICT(user_id, date) DO UPDATE SET count = shop_purchases.count + ?",
                            (ctx.author.id, today, qty, qty),
                        )

                        await db.commit()

                    # Show updated progress
                    new_bought = bought_today + qty
                    # Set title and emoji based on item type
                    if item_key == "exp_bottle":
                        title = "EXP Bottle Purchase"
                        emoji = "<:exp:1437553839359397928>"
                        daily_cap_display = f"{new_bought}/100"
                    elif item_key == "rod_shard":
                        title = "Rod Shard Purchase"
                        emoji = "🔧"
                        daily_cap_display = f"{new_bought}/10"
                    elif item_key == "fish_bait":
                        title = "Fish Bait Purchase"
                        emoji = "🪱"
                        daily_cap_display = f"{new_bought}/20"
                    else:
                        title = "Item Purchase"
                        emoji = ""
                        daily_cap_display = f"{new_bought}/{DAILY_CAP}"

                    embed = discord.Embed(title=title, color=0x1ABC9C)
                    parts = [
                        f"Spent: `{total_cost:,}` <:mora:1437958309255577681>",
                        f"Added: `{qty}` {emoji} {item_key.replace('_', ' ').title()}(s)",
                        f"Daily progress: {daily_cap_display}",
                    ]
                    embed.description = "\n".join(parts)
                    await send_embed(ctx, embed)
                except Exception as e:
                    print(f"Failed to complete {item_key} purchase: {e}")
                    await ctx.send("Could not complete purchase right now.")
            else:
                # choose chest types using weights: common 60, exquisite 25, precious 15, luxurious 10 (weights will be normalized)
                weights = {
                    "common": 60,
                    "exquisite": 25,
                    "precious": 15,
                    "luxurious": 10,
                }
                types = list(weights.keys())
                w = list(weights.values())

                # compute awarded chest counts first (no DB ops yet)
                awarded = {k: 0 for k in types}
                for _ in range(qty):
                    pick = random.choices(types, weights=w, k=1)[0]
                    awarded[pick] += 1

                # perform DB updates in one transaction
                try:
                    await ensure_user_db(ctx.author.id)
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("BEGIN")
                        # check balance
                        async with db.execute(
                            "SELECT mora FROM users WHERE user_id=?", (ctx.author.id,)
                        ) as cur:
                            row = await cur.fetchone()
                            cur_mora = int(row[0] or 0) if row else 0
                        if cur_mora < total_cost:
                            await db.execute("ROLLBACK")
                            await ctx.send(
                                f"You need {total_cost:,} Mora to buy {qty} chest(s). Your balance: {cur_mora:,} Mora."
                            )
                            return
                        new_mora = cur_mora - total_cost
                        await db.execute(
                            "UPDATE users SET mora=? WHERE user_id=?",
                            (new_mora, ctx.author.id),
                        )

                        # ensure chest_inventory row exists
                        await db.execute(
                            "INSERT OR IGNORE INTO chest_inventory (user_id, common, exquisite, precious, luxurious) VALUES (?, ?, ?, ?, ?)",
                            (ctx.author.id, 0, 0, 0, 0),
                        )
                        # apply awarded chest increments
                        for k, amt in awarded.items():
                            if amt:
                                await db.execute(
                                    f"UPDATE chest_inventory SET {k} = {k} + ? WHERE user_id=?",
                                    (amt, ctx.author.id),
                                )

                        # update legacy chests.count
                        async with db.execute(
                            "SELECT count FROM chests WHERE user_id=?", (ctx.author.id,)
                        ) as cur2:
                            crow = await cur2.fetchone()
                            legacy = int(crow[0] or 0) if crow else 0
                        legacy_new = legacy + sum(awarded.values())
                        await db.execute(
                            "INSERT OR IGNORE INTO chests (user_id, count) VALUES (?, 0)",
                            (ctx.author.id,),
                        )
                        await db.execute(
                            "UPDATE chests SET count = ? WHERE user_id=?",
                            (legacy_new, ctx.author.id),
                        )

                        # increment daily purchases
                        today = __import__("datetime").date.today().isoformat()
                        # Track per-item for 'random'
                        await db.execute(
                            "INSERT INTO shop_item_purchases (user_id, date, item_key, count) VALUES (?, ?, ?, ?) ON CONFLICT(user_id, date, item_key) DO UPDATE SET count = shop_item_purchases.count + ?",
                            (ctx.author.id, today, "random", qty, qty),
                        )
                        await db.execute(
                            "INSERT INTO shop_purchases (user_id, date, count) VALUES (?, ?, ?) ON CONFLICT(user_id, date) DO UPDATE SET count = shop_purchases.count + ?",
                            (ctx.author.id, today, qty, qty),
                        )

                        await db.commit()

                    # Show updated progress
                    new_bought = bought_today + qty

                    embed = discord.Embed(title="Shop Purchase", color=0xFFD700)
                    parts = [f"Spent: `{total_cost:,}` <:mora:1437958309255577681>"]

                    chest_icons = {
                        "common": "<:cajitadelexplorador:1437473147833286676>",
                        "exquisite": "<:cajitaplatino:1437473086571286699>",
                        "precious": "<:cajitapremium:1437473125095837779>",
                        "luxurious": "<:cajitadiamante:1437473169475764406>",
                    }

                    chest_parts = []
                    for k in types:
                        if awarded.get(k, 0):
                            icon = chest_icons.get(k, "")
                            chest_parts.append(f"{icon} {awarded[k]}x {k}")
                    if chest_parts:
                        parts.append("You received:\n" + "\n".join(chest_parts))

                    parts.append(f"\nDaily progress: {new_bought}/20")
                    embed.description = "\n".join(parts)
                    await send_embed(ctx, embed)
                except Exception as e:
                    print(f"Failed to complete chest shop purchase: {e}")
                    await ctx.send("Could not complete purchase right now.")
        except Exception as e:
            print(f"Error in shop buy: {e}")
            await ctx.send("Could not complete purchase right now.")

    @commands.command(name="buy")
    async def buy(self, ctx, item_id: int, amount: int = 1):
        """Quick alias to buy by numeric shop id: `gbuy 1 5`"""
        try:
            # delegate to shop_buy by passing the id as a string (shop_buy accepts id or name)
            await self.shop_buy(ctx, str(item_id), amount)
        except Exception as e:
            print(f"Error in buy alias: {e}")
            await ctx.send(
                "Could not process quick buy. Try `gshop buy <id> <amount>`."
            )

    @commands.command(name="bal")
    async def balance(self, ctx):
        if not await require_enrollment(ctx):
            return
        data = await get_user_data(ctx.author.id)
        from cogs.settings import get_user_embed_color
        color = await get_user_embed_color(ctx.author.id, "bal", 0xF1C40F)
        embed = discord.Embed(
            title=f"<:mora:1437958309255577681> {ctx.author.display_name}'s Wallet",
            color=color,
        )
        embed.add_field(
            name="<:mora:1437958309255577681> Mora",
            value=f"`{data['mora']:,}`",
            inline=True,
        )
        embed.add_field(
            name="<:mora:1437480155952975943> Tide Coins",
            value=f"`{data['dust']:,}`",
            inline=True,
        )
        await send_embed(ctx, embed)

    @commands.command(name="mci")
    async def my_card_info(self, ctx, *, card_name: str):
        try:
            from utils.database import get_card_info
            from utils.constants import characters, rarity_emojis
            
            card = await get_card_info(ctx.author.id, card_name)
            if not card:
                await ctx.send(f"You don't own the card {card_name}.")
                return
            
            # Get full character data from constants
            char_data = next((c for c in characters if c['name'].lower() == card['name'].lower()), None)

            # choose embed color by rarity
            if card['rarity'] == 'SSR':
                color = 0xFFD700  # Gold
            elif card['rarity'] == 'SR':
                color = 0x9B59B6  # Purple
            else:
                color = 0x2ECC71  # Green
            
            # Get rarity emoji
            rarity_emoji = rarity_emojis.get(card['rarity'], card['rarity'])

            # Build rich embed with description and image
            embed = discord.Embed(
                title=card['name'],
                description=char_data['description'] if char_data else "A legendary Servant.",
                color=color
            )
            embed.set_thumbnail(url=f"https://cdn.discordapp.com/emojis/{rarity_emoji.split(':')[2].rstrip('>')}")
            
            # Statistics section
            stats = (
                f"**Power:** {card['power_level']:,}\n"
                f"**Health:** {card['current_hp']:,}\n"
                f"**Attack:** {card['current_atk']:,}\n"
                f"**Level:** {card['level']} ({card['exp']:,}/{card['exp_needed']:,})"
            )
            embed.add_field(name="Statistics:", value=stats, inline=False)
            
            # Class section
            class_info = f"**Class:** {card.get('class', 'Unknown')}"
            embed.add_field(name="", value=class_info, inline=False)
            
            # Set character image at bottom
            if char_data and char_data.get('image'):
                embed.set_image(url=char_data['image'])
            
            embed.set_footer(text=f"This card belongs to {ctx.author.name}")
            await send_embed(ctx, embed)

        except Exception as e:
            await ctx.send("Something went wrong while fetching that card.")
            print(f"Error in gmci: {e}")

    @commands.command(name="mycards", aliases=["mc", "servants"])
    async def mycards(self, ctx, *, rarity_filter: str = None):
        """Show owned Servants. Optional filter: `gmc 5 star` or `gmc 4` to show only that rarity.
        Servants are listed from lowest rarity to highest by default.
        """
        pulls = await get_user_pulls(ctx.author.id)
        if not pulls:
            await ctx.send("No Servants. Use `gwish` to summon.")
            return
        # helper to extract numeric rarity (e.g., '5★' -> 5)
        import re

        def rarity_num(r):
            try:
                if isinstance(r, int):
                    return int(r)
                m = re.search(r"(\d+)", str(r))
                return int(m.group(1)) if m else 0
            except Exception:
                return 0

        # optional filtering by rarity (e.g., '5 star', '5', '5★')
        if rarity_filter:
            rf = rarity_filter.lower().strip()
            m = re.search(r"(\d+)", rf)
            if m:
                want = int(m.group(1))
                pulls = [p for p in pulls if rarity_num(p[1]) == want]
            else:
                # try textual numbers (e.g., 'five')
                txt_map = {"three": 3, "four": 4, "five": 5}
                for word, num in txt_map.items():
                    if word in rf:
                        pulls = [p for p in pulls if rarity_num(p[1]) == num]
                        break

        # sort by rarity number ascending (lowest to highest), then by name
        pulls.sort(key=lambda x: (rarity_num(x[1]), x[0]))
        items_per_page = 5
        pages = [
            pulls[i : i + items_per_page] for i in range(0, len(pulls), items_per_page)
        ]
        total_pages = len(pages)
        current_page = 0

        def create_embed(page_index):
            title_suffix = f" ({page_index + 1}/{total_pages})"
            if rarity_filter:
                title = f"{ctx.author.display_name}'s {rarity_filter.strip()} Servant Collection{title_suffix}"
            else:
                title = f"{ctx.author.display_name}'s Servant Collection{title_suffix}"
            embed = discord.Embed(title=title, color=0x00FF00)
            
            for card in pages[page_index]:
                name, rarity, count, relics, servant_class, hp, atk = card
                embed.add_field(
                    name=f"**{name}** ({rarity})",
                    value=f"Class: {servant_class} | HP: {hp} | ATK: {atk}",
                    inline=False,
                )
            return embed

        message = await send_embed(ctx, create_embed(current_page))

        class CardPaginator(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)

            @discord.ui.button(label="⬅️", style=discord.ButtonStyle.gray)
            async def previous(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                nonlocal current_page
                if current_page > 0:
                    current_page -= 1
                    await interaction.response.edit_message(
                        embed=create_embed(current_page)
                    )
                else:
                    await interaction.response.defer()

            @discord.ui.button(label="➡️", style=discord.ButtonStyle.gray)
            async def next(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                nonlocal current_page
                if current_page < total_pages - 1:
                    current_page += 1
                    await interaction.response.edit_message(
                        embed=create_embed(current_page)
                    )
                else:
                    await interaction.response.defer()

        # attach the paginator view to the message we just sent
        await message.edit(view=CardPaginator())

    # Temporary admin audit/repair commands removed — no longer needed after migration

    @commands.command(name="relicinventory", aliases=["rinv"])
    async def relicinventory(self, ctx):
        pulls = await get_user_pulls(ctx.author.id)
        relic_items = [p for p in pulls if p[3] > 0]
        if not relic_items:
            await ctx.send("You don't have any relics yet.")
            return
        description = "\n".join(
            [f"{p[0]} ({p[1]}) | Relics: {p[3]}" for p in relic_items]
        )
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Relic Inventory",
            description=description,
        )
        await send_embed(ctx, embed)

    @commands.group(name="level", invoke_without_command=True)
    async def level(self, ctx):
        """Show your account level and EXP progress. Use `glevel rewards` to check upcoming rewards."""
        try:
            level, exp, needed = await get_account_level(ctx.author.id)
            stage = (level // 20) + 1

            # Compute a compact progress bar similar to the attached mockup.
            from utils.embed import create_progress_bar

            progress_bar = create_progress_bar(exp, needed, segments=15)

            # Ranks concept: show (stage - 1) as "Ranks"
            ranks = max(0, stage - 1)

            # Build embed with thumbnail (user avatar) and compact layout
            # dark purple chosen for embed color to match requested style
            embed = discord.Embed(
                title="Level Progression:",
                description=f"`{progress_bar}`",
                color=0x6A0DAD,
            )
            # small summary fields on the left (no emoji)
            embed.add_field(name="Level", value=f"{level}", inline=True)
            embed.add_field(name="Ranks", value=f"{ranks}", inline=True)
            progress = exp / needed if needed > 0 else 0
            embed.add_field(
                name="EXP Progress",
                value=f"`{exp}/{needed}` ({int(progress * 100)}%)",
                inline=False,
            )

            # Short directions to claim rewards (details available via the Check Rewards button)
            embed.add_field(
                name="Level Rewards",
                value="Claim level rewards with `glevel rewards` (interactive) or `glevel claimall` to claim all unclaimed rewards.",
                inline=False,
            )

            class RewardsView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=None)

                @discord.ui.button(
                    label="Check Rewards", style=discord.ButtonStyle.primary
                )
                async def check(
                    self, interaction: discord.Interaction, button: discord.ui.Button
                ):
                    # compute next level rewards (preview only)
                    lvl = level + 1
                    next_stage = (lvl // 20) + 1
                    per_lvl_mora = 1000 * next_stage
                    desc = (
                        f"Per level: <:cajitadelexplorador:1437473147833286676> 1x Common Chest, {per_lvl_mora:,} Mora (Stage {next_stage}).\n"
                        f"Every 10th level: additional {5000 * next_stage:,} Mora + <:cajitaplatino:1437473086571286699> 1x Exquisite Chest.\n"
                        "Every 20th level: a Stage badge."
                    )
                    embed2 = discord.Embed(
                        title=f"Rewards preview for level {lvl}",
                        description=desc,
                        color=0x2ECC71,
                    )
                    await interaction.response.send_message(
                        embed=embed2, ephemeral=True
                    )

            await send_embed(ctx, embed, view=RewardsView())
        except Exception as e:
            print(f"Error in !level: {e}")
            await ctx.send("Could not fetch level info right now.")

    @commands.command(name="use")
    async def use_item(self, ctx, item: str = None, amount: int = 1):
        """Use a consumable item from your inventory."""
        try:
            if item is None:
                await ctx.send("Usage: `guse <item> <amount>`\nExample: `guse bottle 5`")
                return

            item_l = item.lower()
            if item_l in ("bottle", "exp bottle", "exp_bottle", "expbottle"):
                qty = max(1, int(amount))
                # check user has enough bottles
                have = await get_user_item_count(ctx.author.id, "exp_bottle")
                if have < qty:
                    await ctx.send(f"You only have `{have}` bottle(s).")
                    return
                # Send processing message for large amounts
                if qty >= 20:
                    msg = await ctx.send(f"<a:Loading:1437951860546732274> Processing {qty} bottles...")
                
                # consume bottles
                try:
                    await add_user_item(ctx.author.id, "exp_bottle", -qty)
                except ValueError as ve:
                    if qty >= 20:
                        await msg.delete()
                    await ctx.send(str(ve))
                    return
                
                # Get starting level
                from utils.database import get_account_level
                start_level, _, _ = await get_account_level(ctx.author.id)
                
                # grant EXP
                exp_per_bottle = 250
                gained = exp_per_bottle * qty
                try:
                    await add_account_exp(ctx.author.id, gained, source="use_bottle")
                except Exception as e:
                    print(f"Failed to grant EXP from bottles: {e}")

                # Get final exp progress
                current_level, current_exp, exp_needed = await get_account_level(
                    ctx.author.id
                )

                # Delete processing message if exists
                if qty >= 20:
                    await msg.delete()
                
                # Show level ups if any
                levels_gained = current_level - start_level
                level_up_text = f"\n🎉 **Level Up!** {start_level} → {current_level}" if levels_gained > 0 else ""
                
                await ctx.send(
                    f"<:exp:1437553839359397928> Used **{qty}x EXP Bottle(s)**\n"
                    f"**{gained:,}** EXP gained{level_up_text}\n"
                    f"*EXP Progress: {current_exp:,}/{exp_needed:,}*"
                )
            else:
                await ctx.send("Unknown item. Currently supported: `bottle`.")
        except Exception as e:
            print(f"Error in use command: {e}")
            await ctx.send("Could not use item right now.")

    @level.command(name="rewards")
    async def level_rewards(self, ctx):
        """Show claimable level rewards and allow claiming via buttons."""
        try:
            level, exp, needed = await get_account_level(ctx.author.id)

            # find which levels up to current are already claimed
            import aiosqlite

            from config import DB_PATH

            claimed_levels = set()
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT level FROM level_claims WHERE user_id=? AND claimed=1",
                    (ctx.author.id,),
                ) as cur:
                    rows = await cur.fetchall()
                    for r in rows:
                        try:
                            claimed_levels.add(int(r[0]))
                        except Exception:
                            pass

            all_levels = set(range(1, level + 1))
            unclaimed = sorted(list(all_levels - claimed_levels))

            if not unclaimed:
                embed = discord.Embed(
                    title="No unclaimed level rewards",
                    description=f"You are level `{level}` and have no pending level rewards to claim. Use `glevel` to preview upcoming rewards.",
                    color=0x95A5A6,
                )
                await send_embed(ctx, embed)
                return

            # build embed listing unclaimed levels (limit to first 10 for UI clarity)
            display_levels = unclaimed[:10]
            desc = "\n".join(
                [f"Level {level_num}: reward available" for level_num in display_levels]
            )
            if len(unclaimed) > len(display_levels):
                desc += f"\n...and {len(unclaimed) - len(display_levels)} more"

            embed = discord.Embed(
                title="Unclaimed Level Rewards", description=desc, color=0x2ECC71
            )

            class ClaimView(discord.ui.View):
                def __init__(self, user_id, levels):
                    super().__init__(timeout=None)
                    self.user_id = user_id
                    self.levels = levels
                    # create a button per level (up to 10)
                    for level_num in levels:
                        btn = discord.ui.Button(
                            label=f"Claim L{level_num}",
                            style=discord.ButtonStyle.primary,
                        )

                        # bind level_num to the callback
                        async def make_cb(
                            interaction: discord.Interaction, _lvl=level_num
                        ):
                            if interaction.user.id != ctx.author.id:
                                await interaction.response.send_message(
                                    "This is not your reward to claim.", ephemeral=True
                                )
                                return
                            # attempt to grant rewards
                            try:
                                ok = await grant_level_rewards(self.user_id, _lvl)
                                if ok:
                                    await interaction.response.send_message(
                                        f"Claimed rewards for level {_lvl}.",
                                        ephemeral=True,
                                    )
                                    # disable the button that was pressed
                                    for item in self.children:
                                        if (
                                            isinstance(item, discord.ui.Button)
                                            and item.label == f"Claim L{_lvl}"
                                        ):
                                            item.disabled = True
                                    try:
                                        await interaction.message.edit(view=self)
                                    except Exception:
                                        pass
                                else:
                                    await interaction.response.send_message(
                                        f"Rewards for level {_lvl} were already claimed.",
                                        ephemeral=True,
                                    )
                            except Exception as e:
                                print(f"Error claiming level rewards: {e}")
                                await interaction.response.send_message(
                                    "Failed to claim rewards. Try again later.",
                                    ephemeral=True,
                                )

                        btn.callback = make_cb
                        self.add_item(btn)

            view = ClaimView(ctx.author.id, display_levels)
            await send_embed(ctx, embed, view=view)

        except Exception as e:
            print(f"Error in !level rewards: {e}")
            await ctx.send("Could not fetch level rewards right now.")

    @level.command(name="claimall")
    async def level_claimall(self, ctx):
        """Claim all unclaimed level rewards up to your current level."""
        try:
            level, exp, needed = await get_account_level(ctx.author.id)

            # Fetch claimed levels
            import aiosqlite

            from config import DB_PATH

            claimed_levels = set()
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT level FROM level_claims WHERE user_id=? AND claimed=1",
                    (ctx.author.id,),
                ) as cur:
                    rows = await cur.fetchall()
                    for r in rows:
                        try:
                            claimed_levels.add(int(r[0]))
                        except Exception:
                            pass

            all_levels = set(range(1, level + 1))
            unclaimed = sorted(list(all_levels - claimed_levels))

            if not unclaimed:
                await ctx.send("You have no unclaimed level rewards.")
                return

            claimed_now = []
            for lvl in unclaimed:
                try:
                    ok = await grant_level_rewards(ctx.author.id, lvl)
                    if ok:
                        claimed_now.append(lvl)
                except Exception:
                    # continue on failure for best-effort
                    continue

            if not claimed_now:
                await ctx.send(
                    "Could not claim your level rewards at this time. Try again later."
                )
                return

            # summarize results
            embed = discord.Embed(title="Level Rewards Claimed", color=0x2ECC71)
            embed.description = f"Claimed rewards for {len(claimed_now)} level(s): {', '.join(str(level_num) for level_num in claimed_now)}."
            embed.add_field(
                name="Note",
                value="Rewards include chests and sometimes Mora or badges. Check `ginventory` and your wallet for results.",
                inline=False,
            )
            await send_embed(ctx, embed)
        except Exception as e:
            print(f"Error in level claimall: {e}")
            await ctx.send("Could not claim level rewards right now.")


async def setup(bot):
    # avoid adding the cog twice if the extension is reloaded or setup called multiple times
    if bot.get_cog("Inventory") is None:
        await bot.add_cog(Inventory(bot))
    else:
        print("Inventory cog already loaded; skipping add_cog")
