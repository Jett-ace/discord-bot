import random
from datetime import datetime, timedelta
import discord
from discord.ext import commands
import aiosqlite

from config import DB_PATH
from utils.database import get_user_data, update_user_data, require_enrollment, ensure_user_db, get_account_level, add_account_exp
from utils.embed import send_embed


# ===== FISHING AREAS =====
FISHING_AREAS = {
    "nilecrest": {
        "name": "Nilecrest Waters",
        "level_required": 0,
        "energy_cost": 1,
        "rarity": "Common",
        "color": 0x95A5A6,
        "icon": "🌊"
    },
    "moonflow": {
        "name": "Moonflow River",
        "level_required": 5,
        "energy_cost": 1,
        "rarity": "Uncommon",
        "color": 0x3498DB,
        "icon": "🌙"
    },
    "silverfin": {
        "name": "Silverfin River",
        "level_required": 10,
        "energy_cost": 2,
        "rarity": "Rare",
        "color": 0x9B59B6,
        "icon": "✨"
    },
    "azure": {
        "name": "Azure Tide",
        "level_required": 25,
        "energy_cost": 3,
        "rarity": "Epic",
        "color": 0xE91E63,
        "icon": "🌊"
    },
    "moonbay": {
        "name": "Moonbay",
        "level_required": 50,
        "energy_cost": 3,
        "rarity": "Legendary",
        "color": 0xFFD700,
        "icon": "🌟"
    }
}

# ===== FISHING ROD TIERS =====
FISHING_RODS = {
    1: {
        "name": "Wooden Fishing Rod",
        "emoji": "<:wooden:1458224723342262555>",
        "max_durability": 100,
        "repair_material": "wood",
        "catch_rate_bonus": 0,
        "reward_bonus": 0
    },
    2: {
        "name": "Silver Fishing Rod",
        "emoji": "<:silver:1458224796562362578>",
        "max_durability": 150,
        "repair_material": "silver_scrap",
        "catch_rate_bonus": 0.15,
        "reward_bonus": 0.20
    },
    3: {
        "name": "Golden Fishing Rod",
        "emoji": "<:gold:1458224862605873443>",
        "max_durability": 200,
        "repair_material": "gold_scrap",
        "catch_rate_bonus": 0.30,
        "reward_bonus": 0.40
    }
}

# ===== FISH DATA =====
FISH = {
    # Common - Nilecrest Waters
    "lavender_koi": {
        "name": "Lavender Koi",
        "emoji": "<:lavenderkoi:1458198976862883861>",
        "area": "nilecrest",
        "value": 2500,
        "ability": "Peaceful Aura",
        "ability_desc": "5% XP boost (passive, always active while equipped)",
        "rarity": "Common"
    },
    "lola": {
        "name": "Lola",
        "emoji": "<:lola:1458198880624836802>",
        "area": "nilecrest",
        "value": 3000,
        "ability": "Swift Current",
        "ability_desc": "Reduces energy regeneration time from 60 minutes to 50 minutes (passive, always active while equipped)",
        "rarity": "Common"
    },
    
    # Uncommon - Moonflow River
    "dune": {
        "name": "Dune",
        "emoji": "<:dune:1458198913122304070>",
        "area": "moonflow",
        "value": 8000,
        "ability": "Sandy Shield",
        "ability_desc": "+3% to all gambling winnings (passive, always active while equipped)",
        "rarity": "Uncommon"
    },
    "cotton_candy": {
        "name": "Cotton Candy",
        "emoji": "<:cottoncandy:1458199130454102230>",
        "area": "moonflow",
        "value": 10000,
        "ability": "Sweet Rush",
        "ability_desc": "10% chance to double fishing rewards (2h cooldown after proc)",
        "rarity": "Uncommon"
    },
    
    # Rare - Silverfin River
    "midnight": {
        "name": "Midnight",
        "emoji": "<:midnight:1458199228932292833>",
        "area": "silverfin",
        "value": 25000,
        "ability": "Shadow Blessing",
        "ability_desc": "+5% win chance on gambling games for 30 minutes (3h cooldown after activation)",
        "rarity": "Rare"
    },
    "purple_koi": {
        "name": "Purple Koi",
        "emoji": "<:purplekoi:1458198941417078905>",
        "area": "silverfin",
        "value": 35000,
        "ability": "Fortune Scales",
        "ability_desc": "Receive random chest every 5 hours (must stay equipped for full duration)",
        "rarity": "Rare"
    },
    
    # Epic - Azure Tide
    "ocean": {
        "name": "Ocean",
        "emoji": "<:ocean:1458199169792737413>",
        "area": "azure",
        "value": 75000,
        "ability": "Tidal Wave",
        "ability_desc": "2% chance to double multiplier on next game win (passive, no cooldown)",
        "rarity": "Epic"
    },
    "satori": {
        "name": "Satori",
        "emoji": "<:satori:1458199266525712426>",
        "area": "azure",
        "value": 100000,
        "ability": "Enlightenment",
        "ability_desc": "+25% rob success chance (2h cooldown after robbery)",
        "rarity": "Epic"
    },
    
    # Legendary - Moonbay
    "jellypop": {
        "name": "Jellypop",
        "emoji": "<:jellypop:1458199038984847626>",
        "area": "moonbay",
        "value": 250000,
        "ability": "Mystic Glow",
        "ability_desc": "Copy and use any other fish's ability once per day (24h cooldown)",
        "rarity": "Legendary"
    }
}


class FishingButtonView(discord.ui.View):
    def __init__(self, fishing_cog, ctx, area_key, area_data):
        super().__init__(timeout=10)
        self.fishing_cog = fishing_cog
        self.ctx = ctx
        self.area_key = area_key
        self.area_data = area_data
        self.clicked = False
        self.interaction = None
    
    @discord.ui.button(label="Lure In!", style=discord.ButtonStyle.success, emoji="🎣")
    async def lure_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This isn't your fishing session!", ephemeral=True)
        
        if self.clicked:
            return await interaction.response.send_message("You already clicked!", ephemeral=True)
        
        self.clicked = True
        self.interaction = interaction
        await interaction.response.defer()
        self.stop()
        # complete_fishing will be called after view.wait() returns


class Fishing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Track active fishing sessions: {user_id: {'message': Message, 'area': str, 'start_time': datetime}}
        self.active_sessions = {}
        # Track fishing cooldowns per area: {user_id: {area_key: last_fish_time}}
        self._fish_cooldowns = {}
    
    async def get_fishing_rod(self, user_id):
        """Get user's fishing rod tier and durability."""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT rod_tier, rod_durability FROM accounts WHERE user_id = ?",
                (user_id,)
            )
            result = await cursor.fetchone()
            if result:
                return result[0] or 0, result[1] or 0
            return 0, 0
    
    async def set_fishing_rod(self, user_id, tier, durability):
        """Set user's fishing rod tier and durability."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE accounts SET rod_tier = ?, rod_durability = ? WHERE user_id = ?",
                (tier, durability, user_id)
            )
            await db.commit()
    
    async def reduce_rod_durability(self, user_id, amount=1):
        """Reduce rod durability by amount."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE accounts SET rod_durability = rod_durability - ? WHERE user_id = ?",
                (amount, user_id)
            )
            await db.commit()
    
    async def cog_load(self):
        """Initialize fishing database tables"""
        async with aiosqlite.connect(DB_PATH) as db:
            # Caught fish inventory
            await db.execute("""
                CREATE TABLE IF NOT EXISTS caught_fish (
                    user_id INTEGER,
                    fish_id TEXT,
                    quantity INTEGER DEFAULT 0,
                    fish_level INTEGER DEFAULT 1,
                    fish_exp INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, fish_id)
                )
            """)
            
            # Fishing statistics
            await db.execute("""
                CREATE TABLE IF NOT EXISTS fishing_stats (
                    user_id INTEGER PRIMARY KEY,
                    total_catches INTEGER DEFAULT 0,
                    total_value INTEGER DEFAULT 0
                )
            """)
            
            # Equipped fish (pets)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS equipped_fish (
                    user_id INTEGER,
                    slot INTEGER,
                    fish_id TEXT,
                    equipped_at TEXT,
                    PRIMARY KEY (user_id, slot)
                )
            """)
            
            await db.commit()
    
    async def get_equipped_fish(self, user_id: int):
        """Get all equipped fish for a user"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT slot, fish_id FROM equipped_fish WHERE user_id = ? ORDER BY slot",
                (user_id,)
            )
            return await cursor.fetchall()
    
    async def is_premium_user(self, user_id: int):
        """Check if user has premium"""
        premium_cog = self.bot.get_cog('Premium')
        if premium_cog:
            return await premium_cog.is_premium(user_id)
        return False
    
    @commands.command(name="fish", aliases=["fishing", "cast"])
    async def fish_command(self, ctx, *, area: str = None):
        """Go fishing in different areas!
        
        Usage: gfish <area>
        Areas: nilecrest, moonflow, silverfin, azure, moonbay
        
        Requires bait: Wormbait or Scorpion
        """
        if not await require_enrollment(ctx):
            return
        await ensure_user_db(ctx.author.id)
        
        # Show fishing guide if no area specified
        if not area:
            await self.show_fishing_guide(ctx)
            return
        
        # Check if already fishing
        if ctx.author.id in self.active_sessions:
            return await ctx.send("<a:X_:1437951830393884788> You're already fishing! Wait for your current session to finish.")
        
        # Parse area name
        area = area.lower().replace(" ", "")
        
        # Handle multi-word areas
        area_map = {
            "nilecrest": "nilecrest",
            "nilecrestwaters": "nilecrest",
            "moonflow": "moonflow",
            "moonflowriver": "moonflow",
            "silverfin": "silverfin",
            "silverfinriver": "silverfin",
            "azure": "azure",
            "azuretide": "azure",
            "moonbay": "moonbay"
        }
        
        area_key = area_map.get(area)
        
        if not area_key or area_key not in FISHING_AREAS:
            return await ctx.send(
                f"<a:X_:1437951830393884788> Unknown fishing area! Use `gfish` to see all areas."
            )
        
        area_data = FISHING_AREAS[area_key]
        
        # Check if premium for energy calculation
        premium_cog = self.bot.get_cog('Premium')
        is_premium = False
        if premium_cog:
            try:
                is_premium = await premium_cog.is_premium(ctx.author.id)
            except Exception:
                pass
        
        # Check fishing energy
        from utils.database import get_fishing_energy, consume_fishing_energy
        current_energy = await get_fishing_energy(ctx.author.id, is_premium)
        energy_cost = area_data["energy_cost"]
        
        if current_energy < energy_cost:
            max_energy = 9 if is_premium else 6
            regen_time = "30 minutes" if is_premium else "1 hour"
            return await ctx.send(
                f"<a:X_:1437951830393884788> Not enough fishing energy!\n"
                f"**{area_data['name']}** requires **{energy_cost}** energy.\n"
                f"Current: **{current_energy}/{max_energy}** <:energy:1459189042574004224>\n"
                f"Energy regenerates 1 per {regen_time}."
            )
        
        # Check level requirement
        user_level, _, _ = await get_account_level(ctx.author.id)
        if user_level < area_data["level_required"]:
            embed = discord.Embed(
                title=f"🔒 {area_data['name']} Locked",
                description=f"You need to be **Level {area_data['level_required']}** to fish here.\nYour level: **{user_level}**",
                color=0xE74C3C
            )
            return await send_embed(ctx, embed)
        
        # Check if user has a fishing rod
        rod_tier, rod_durability = await self.get_fishing_rod(ctx.author.id)
        if rod_tier == 0:
            return await ctx.send(
                "<a:X_:1437951830393884788> You need a fishing rod to fish! Craft a **Wooden Fishing Rod** using `gcraftrod`."
            )
        
        if rod_durability <= 0:
            rod_data = FISHING_RODS[rod_tier]
            return await ctx.send(
                f"<a:X_:1437951830393884788> Your {rod_data['emoji']} **{rod_data['name']}** is broken!\n"
                f"Repair it using `grepairrod` with **{rod_data['repair_material']}**."
            )
        
        # Check if user has bait
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id IN ('wormbait', 'scorpion')",
                (ctx.author.id,)
            )
            bait_results = await cursor.fetchall()
        
        total_bait = sum(row[0] for row in bait_results) if bait_results else 0
        
        if total_bait == 0:
            return await ctx.send(
                "<a:X_:1437951830393884788> You don't have any bait!\n"
                "You need <:wormbait:1458986452871282698> Wormbait or <:scorpion:1458986549722087586> Scorpion to fish.\n"
                "Find them in chests or buy from the Black Market!"
            )
        
        # Consume one bait (prioritize wormbait)
        async with aiosqlite.connect(DB_PATH) as db:
            # Try to use wormbait first
            cursor = await db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = 'wormbait'",
                (ctx.author.id,)
            )
            wormbait = await cursor.fetchone()
            
            if wormbait and wormbait[0] > 0:
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = 'wormbait'",
                    (ctx.author.id,)
                )
                used_bait = "Wormbait"
                used_bait_emoji = "<:wormbait:1458986452871282698>"
            else:
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = 'scorpion'",
                    (ctx.author.id,)
                )
                used_bait = "Scorpion"
                used_bait_emoji = "<:scorpion:1458986549722087586>"
            
            # Clean up zero quantities
            await db.execute("DELETE FROM inventory WHERE quantity <= 0")
            await db.commit()
        
        # Consume fishing energy
        from utils.database import consume_fishing_energy
        energy_consumed = await consume_fishing_energy(ctx.author.id, energy_cost)
        if not energy_consumed:
            return await ctx.send("<a:X_:1437951830393884788> Failed to consume energy. Try again.")
        
        # Start fishing session
        await self.start_fishing_session(ctx, area_key, area_data, used_bait, used_bait_emoji, is_premium)
    
    async def start_fishing_session(self, ctx, area_key: str, area_data: dict, used_bait: str, used_bait_emoji: str, is_premium: bool = False):
        """Start an interactive fishing session"""
        import asyncio
        
        # Create initial embed
        embed = discord.Embed(
            title=f"{area_data['icon']} {area_data['name']}",
            description=f"You cast your {used_bait_emoji} **{used_bait}** into the water.\nBe alert for any fish!",
            color=area_data["color"]
        )
        embed.set_footer(text="Waiting for a bite...")
        
        msg = await send_embed(ctx, embed)
        
        # Store session
        self.active_sessions[ctx.author.id] = {
            'message': msg,
            'area': area_key,
            'area_data': area_data,
            'start_time': datetime.utcnow(),
            'used_bait': used_bait
        }
        
        # Random wait time (10-20 seconds)
        wait_time = random.uniform(10, 20)
        
        await asyncio.sleep(wait_time)
        
        # Check if session still active (user didn't cancel/disconnect)
        if ctx.author.id not in self.active_sessions:
            return
        
        # Fish bites! Add button
        embed.description = f"A fish has taken the bait!\nQuick, reel it in!"
        embed.set_footer(text="Click the button within 10 seconds!")
        embed.color = 0xF39C12
        
        # Create button view
        view = FishingButtonView(self, ctx, area_key, area_data)
        await msg.edit(embed=embed, view=view)
        
        # Wait for button press or timeout
        await view.wait()
        
        # Check if they clicked in time
        if view.clicked:
            # Button was clicked - process the catch
            await self.complete_fishing(ctx, area_key, area_data)
        elif ctx.author.id in self.active_sessions:
            # Timeout - fish got away
            embed.description = "The fish got away! Your bait was wasted."
            embed.color = 0xE74C3C
            embed.set_footer(text="Better luck next time!")
            await msg.edit(embed=embed, view=None)
            del self.active_sessions[ctx.author.id]
    
    async def complete_fishing(self, ctx, area_key: str, area_data: dict):
        """Complete the fishing and give rewards"""
        if ctx.author.id not in self.active_sessions:
            return
        
        session = self.active_sessions[ctx.author.id]
        msg = session['message']
        used_bait = session.get('used_bait', 'Wormbait')
        
        # Get user's fishing rod for bonuses
        rod_tier, rod_durability = await self.get_fishing_rod(ctx.author.id)
        rod_data = FISHING_RODS[rod_tier]
        
        # Check if premium for better fish catch rate
        premium_cog = self.bot.get_cog('Premium')
        is_premium = False
        if premium_cog:
            try:
                is_premium = await premium_cog.is_premium(ctx.author.id)
            except Exception:
                pass
        
        # Determine if fish was caught (20% base, 30% premium, +5% if scorpion)
        catch_rate = 0.30 if is_premium else 0.20
        if used_bait == "Scorpion":
            catch_rate += 0.05
        caught_fish_success = random.random() < catch_rate
        
        # Determine bonus rewards
        rewards = []
        caught_fish_id = None
        caught_fish = None
        fish_quantity = 0
        
        if caught_fish_success:
            # Get fish from this area
            area_fish = [f_id for f_id, f in FISH.items() if f["area"] == area_key]
            caught_fish_id = random.choice(area_fish)
            caught_fish = FISH[caught_fish_id]
            
            # Check if Cotton Candy is equipped (10% chance to double rewards)
            equipped = await self.get_equipped_fish(ctx.author.id)
            has_cotton_candy = any(fid == "cotton_candy" for _, fid in equipped)
            double_rewards = has_cotton_candy and random.random() < 0.10
            
            # Add fish to inventory
            fish_quantity = 2 if double_rewards else 1
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO caught_fish (user_id, fish_id, quantity, fish_level, fish_exp)
                    VALUES (?, ?, ?, 1, 0)
                    ON CONFLICT(user_id, fish_id) DO UPDATE SET quantity = quantity + ?
                """, (ctx.author.id, caught_fish_id, fish_quantity, fish_quantity))
                
                # Award fishing XP to the caught fish (base 50 XP per catch)
                base_fish_xp = 50 * fish_quantity
                
                # Check for XP boosters (lucky dice, hot streak, etc.)
                xp_multiplier = 1.0
                cursor = await db.execute("""
                    SELECT item_id, activated_at FROM inventory 
                    WHERE user_id = ? AND activated_at IS NOT NULL
                """, (ctx.author.id,))
                active_items = await cursor.fetchall()
                
                for item_id, activated_at in active_items:
                    activated_time = datetime.fromisoformat(activated_at)
                    now = datetime.utcnow()
                    
                    # Lucky Dice: +50% XP for 1 hour
                    if item_id == "lucky_dice":
                        if (now - activated_time).total_seconds() < 3600:
                            xp_multiplier += 0.5
                    
                    # Hot Streak: +25% XP for 30 minutes
                    if item_id == "streak":
                        if (now - activated_time).total_seconds() < 1800:
                            xp_multiplier += 0.25
                
                # Check for Lavender Koi passive (5% XP boost to fishing XP)
                equipped = await self.get_equipped_fish(ctx.author.id)
                for slot, fish_id in equipped:
                    if fish_id == "lavender_koi":
                        xp_multiplier += 0.05
                        break
                
                # Apply multiplier
                fish_xp_reward = int(base_fish_xp * xp_multiplier)
                
                # Add XP and check for level up (100 XP per level)
                cursor = await db.execute("""
                    SELECT fish_level, fish_exp FROM caught_fish 
                    WHERE user_id = ? AND fish_id = ?
                """, (ctx.author.id, caught_fish_id))
                fish_data = await cursor.fetchone()
                
                if fish_data:
                    current_level = fish_data[0]
                    current_exp = fish_data[1]
                    new_exp = current_exp + fish_xp_reward
                    
                    # Calculate level ups (100 XP per level)
                    levels_gained = 0
                    while new_exp >= 100:
                        new_exp -= 100
                        levels_gained += 1
                    
                    new_level = current_level + levels_gained
                    
                    await db.execute("""
                        UPDATE caught_fish 
                        SET fish_level = ?, fish_exp = ?
                        WHERE user_id = ? AND fish_id = ?
                    """, (new_level, new_exp, ctx.author.id, caught_fish_id))
                
                # Update stats
                await db.execute("""
                    INSERT INTO fishing_stats (user_id, total_catches, total_value)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        total_catches = total_catches + ?,
                        total_value = total_value + ?
                """, (ctx.author.id, fish_quantity, caught_fish["value"] * fish_quantity, fish_quantity, caught_fish["value"] * fish_quantity))
                
                await db.commit()
        
        # Chance for extra bait (20% chance)
        if random.random() < 0.20:
            bait_type = random.choice(["wormbait", "scorpion"])
            bait_emoji = "<:wormbait:1458986452871282698>" if bait_type == "wormbait" else "<:scorpion:1458986549722087586>"
            bait_name = "Wormbait" if bait_type == "wormbait" else "Scorpion"
            
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO inventory (user_id, item_id, quantity)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + 1
                """, (ctx.author.id, bait_type))
                await db.commit()
            
            rewards.append(f"{bait_emoji} {bait_name}")
        
        # Mora reward (10k - 50k)
        mora_reward = random.randint(10000, 50000)
        from utils.database import get_user_data, update_user_data
        user_data = await get_user_data(ctx.author.id)
        await update_user_data(ctx.author.id, mora=user_data["mora"] + mora_reward)
        rewards.append(f"<:mora:1437958309255577681> **{mora_reward:,} Mora**")
        
        # Chance for chest (15% base, increased by rod reward bonus, +5% if scorpion)
        chest_chance = 0.15 * (1 + rod_data['reward_bonus'])
        if used_bait == "Scorpion":
            chest_chance += 0.05
        if random.random() < chest_chance:
            chest_weights = {
                "common": 0.70,
                "regular": 0.20,
                "diamond": 0.08,
                "special": 0.02
            }
            
            rand = random.random()
            cumulative = 0.0
            chest_type = "common"
            
            for c_type, weight in chest_weights.items():
                cumulative += weight
                if rand < cumulative:
                    chest_type = c_type
                    break
            
            from utils.database import add_chest_with_type
            await add_chest_with_type(ctx.author.id, chest_type, 1)
            
            chest_emojis = {
                "common": "<:cajitadelexplorador:1437473147833286676>",
                "regular": "<:regular:1437473086571286699>",
                "diamond": "<:dimond:1437473169475764406>",
                "special": "<:special:1437473178971840614>"
            }
            
            rewards.append(f"{chest_emojis.get(chest_type, '')} {chest_type.capitalize()} Chest")
        
        # Chance for fishing materials (scraps and shells)
        # TideShells (12% chance, increased from 8%)
        if random.random() < 0.12:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO inventory (user_id, item_id, quantity)
                    VALUES (?, 'tideshells', 1)
                    ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + 1
                """, (ctx.author.id,))
                await db.commit()
            rewards.append("<:TideShells:1459005927389663445> **TideShells**")
        
        # Silver scrap (8% chance, increased from 5%, available from Silverfin+ areas)
        if area_data['level_required'] >= 10 and random.random() < 0.08:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO inventory (user_id, item_id, quantity)
                    VALUES (?, 'silver_scrap', 1)
                    ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + 1
                """, (ctx.author.id,))
                await db.commit()
            rewards.append("<:silverscrap:1459002718810279957> **Silver Scrap**")
        
        # Gold scrap (4% chance, increased from 2%, available from Azure+ areas)
        if area_data['level_required'] >= 25 and random.random() < 0.04:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO inventory (user_id, item_id, quantity)
                    VALUES (?, 'gold_scrap', 1)
                    ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + 1
                """, (ctx.author.id,))
                await db.commit()
            rewards.append("⚙️ **Gold Scrap**")
        
        # Useful consumable items (rare drops)
        # Lucky Dice (3% chance)
        if random.random() < 0.03:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO inventory (user_id, item_id, quantity)
                    VALUES (?, 'lucky_dice', 1)
                    ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + 1
                """, (ctx.author.id,))
                await db.commit()
            rewards.append("<:dice:1457965149137670186> **Lucky Dice**")
        
        # XP Booster (4% chance)
        if random.random() < 0.04:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO inventory (user_id, item_id, quantity)
                    VALUES (?, 'xp_booster', 1)
                    ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + 1
                """, (ctx.author.id,))
                await db.commit()
            rewards.append("<:exp:1437553839359397928> **XP Booster**")
        
        # Lucky Clover (2% chance)
        if random.random() < 0.02:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO inventory (user_id, item_id, quantity)
                    VALUES (?, 'lucky_clover', 1)
                    ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + 1
                """, (ctx.author.id,))
                await db.commit()
            rewards.append("<a:lucky_clover:1459167567154512065> **Lucky Clover**")
        
        # Golden Chip (1.5% chance, rare but useful)
        if random.random() < 0.015:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO inventory (user_id, item_id, quantity)
                    VALUES (?, 'golden_chip', 1)
                    ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + 1
                """, (ctx.author.id,))
                await db.commit()
            rewards.append("<:goldenchip:1457964285207646264> **Golden Chip**")
        
        # Award XP
        xp_reward = (area_data["level_required"] + 1) * 50
        await add_account_exp(ctx.author.id, xp_reward)
        
        # Reduce rod durability
        await self.reduce_rod_durability(ctx.author.id, 1)
        new_durability = rod_durability - 1
        
        # Build success/failure embed
        if caught_fish_success:
            embed = discord.Embed(
                title=f"🎣 Fish Caught!",
                description=f"You successfully reeled in a **{caught_fish['name']}**!",
                color=0x2ECC71
            )
            
            fish_text = f"{caught_fish['emoji']} **{caught_fish['name']}** x{fish_quantity}"
            if fish_quantity == 2:
                fish_text += " (Cotton Candy doubled your rewards!)"
            
            embed.add_field(
                name="Catch",
                value=fish_text,
                inline=False
            )
        else:
            embed = discord.Embed(
                title="🎣 Nothing Caught",
                description="You didn't catch any fish this time, but you got some bonus items!",
                color=0xF39C12
            )
        
        if rewards:
            embed.add_field(
                name="Bonus Rewards",
                value="\n".join(rewards),
                inline=False
            )
        
        embed.add_field(
            name="XP Gained",
            value=f"+{xp_reward:,} XP",
            inline=False
        )
        
        # Show rod durability
        durability_emoji = "🟢" if new_durability > rod_data['max_durability'] * 0.5 else "🟡" if new_durability > rod_data['max_durability'] * 0.2 else "🔴"
        embed.add_field(
            name=f"{rod_data['emoji']} Rod Durability",
            value=f"{durability_emoji} {new_durability}/{rod_data['max_durability']}",
            inline=True
        )
        
        # Footer with warnings
        footer_text = f"Fished in {area_data['name']}"
        if new_durability <= rod_data['max_durability'] * 0.1:
            footer_text += " • ⚠️ Your rod is about to break! Repair it soon."
        
        embed.set_footer(text=footer_text)
        
        await msg.edit(embed=embed, view=None)
        
        # Clean up session
        del self.active_sessions[ctx.author.id]
    
    async def show_fishing_guide(self, ctx):
        """Display fishing areas and requirements"""
        user_level, _, _ = await get_account_level(ctx.author.id)
        
        embed = discord.Embed(
            title="🎣 Fishing Guide",
            description="Cast your line in different waters to catch unique fish!",
            color=0x3498DB
        )
        
        for area_key, area_data in FISHING_AREAS.items():
            # Check if unlocked
            is_unlocked = user_level >= area_data["level_required"]
            status = "✅" if is_unlocked else "🔒"
            
            # Get fish in this area
            area_fish = [f for f in FISH.values() if f["area"] == area_key]
            fish_list = " ".join([f["emoji"] for f in area_fish])
            
            energy_cost = area_data["energy_cost"]
            
            field_value = (
                f"**Level Required:** {area_data['level_required']}\n"
                f"**Energy Cost:** {energy_cost} <:energy:1459189042574004224>\n"
                f"**Fish:** {fish_list}\n"
                f"**Usage:** `gfish {area_key}`"
            )
            
            embed.add_field(
                name=f"{status} {area_data['icon']} {area_data['name']} ({area_data['rarity']})",
                value=field_value,
                inline=False
            )
        
        embed.set_footer(text=f"Your Level: {user_level} • Use gfish <area> to start fishing!")
        await send_embed(ctx, embed)
    
    async def show_equipped_aquarium(self, ctx):
        """Show currently equipped fish with effects and levels"""
        equipped = await self.get_equipped_fish(ctx.author.id)
        is_premium = await self.is_premium_user(ctx.author.id)
        max_slots = 2 if is_premium else 1
        
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Aquarium",
            description="Your currently equipped fish pets",
            color=0x3498DB
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        
        if not equipped:
            embed.add_field(
                name="No Equipped Fish",
                value=f"You don't have any fish equipped!\nUse `gequipfish <fish name>` to equip a fish.\n\n**Available Slots:** {max_slots}",
                inline=False
            )
        else:
            async with aiosqlite.connect(DB_PATH) as db:
                for slot, fish_id in equipped:
                    fish_data = FISH.get(fish_id)
                    if fish_data:
                        # Get fish level and XP
                        cursor = await db.execute(
                            "SELECT fish_level, fish_exp FROM caught_fish WHERE user_id = ? AND fish_id = ?",
                            (ctx.author.id, fish_id)
                        )
                        result = await cursor.fetchone()
                        fish_level = result[0] if result else 1
                        fish_exp = result[1] if result else 0
                    
                    area_data = FISHING_AREAS[fish_data["area"]]
                    
                    field_value = (
                        f"{fish_data['emoji']} **Level {fish_level}** {fish_data['rarity']}\n"
                        f"Found in: {area_data['name']}\n"
                        f"**{fish_data['ability']}**\n"
                        f"└ {fish_data['ability_desc']}\n"
                        f"Value: {fish_data['value']:,} <:mora:1437958309255577681>"
                    )
                    
                    embed.add_field(
                        name=f"🔷 Slot {slot}",
                        value=field_value,
                        inline=False
                    )
        
        footer_text = "Use gac to see your full collection"
        if is_premium:
            footer_text += " • Premium: 2 slots unlocked!"
        else:
            footer_text += " • Get Premium for a 2nd slot!"
        
        embed.set_footer(text=footer_text)
        await send_embed(ctx, embed)
    
    async def show_full_collection(self, ctx):
        """Show the full fish collection"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT fish_id, quantity FROM caught_fish WHERE user_id = ? ORDER BY quantity DESC",
                (ctx.author.id,)
            )
            caught = await cursor.fetchall()
            
            # Get stats
            cursor = await db.execute(
                "SELECT total_catches, total_value FROM fishing_stats WHERE user_id = ?",
                (ctx.author.id,)
            )
            stats = await cursor.fetchone()
        
        if not caught:
            embed = discord.Embed(
                title="Empty Collection",
                description="You haven't caught any fish yet! Use `gfish` to start fishing.",
                color=0xE74C3C
            )
            return await send_embed(ctx, embed)
        
        # Build collection embed
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Fish Collection",
            color=0x3498DB
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        
        # Stats
        total_catches = stats[0] if stats else 0
        total_value = stats[1] if stats else 0
        unique_fish = len(caught)
        
        embed.add_field(
            name="Statistics",
            value=f"**Total Catches:** {total_catches:,}\n**Unique Fish:** {unique_fish}/9\n**Collection Value:** {total_value:,} <:mora:1437958309255577681>",
            inline=False
        )
        
        # Group by rarity
        rarities = {}
        for fish_id, qty in caught:
            fish_data = FISH.get(fish_id)
            if fish_data:
                rarity = fish_data["rarity"]
                if rarity not in rarities:
                    rarities[rarity] = []
                rarities[rarity].append((fish_data, qty))
        
        # Display by rarity order
        rarity_order = ["Common", "Uncommon", "Rare", "Epic", "Legendary"]
        
        # Get equipped fish to mark them
        equipped = await self.get_equipped_fish(ctx.author.id)
        equipped_ids = [fid for _, fid in equipped]
        
        for rarity in rarity_order:
            if rarity in rarities:
                fish_lines = []
                for fish_data, qty in rarities[rarity]:
                    # Find fish_id
                    fish_id = [k for k, v in FISH.items() if v == fish_data][0]
                    equipped_marker = " 🔷" if fish_id in equipped_ids else ""
                    fish_lines.append(f"{fish_data['emoji']} **{fish_data['name']}** x{qty}{equipped_marker}")
                
                embed.add_field(
                    name=f"{'⭐' * (rarity_order.index(rarity) + 1)} {rarity}",
                    value="\n".join(fish_lines),
                    inline=False
                )
        
        embed.set_footer(text="🔷 = Equipped • Use gequipfish <name> to equip • Use gaqua to see equipped fish")
        await send_embed(ctx, embed)
    
    @commands.command(name="equipfish", aliases=["equip", "fishequip"])
    async def equip_fish(self, ctx, *, fish_name: str = None):
        """Equip a fish as a pet for passive bonuses!
        
        Usage: gequipfish <fish name>
        Regular users: 1 fish slot
        Premium users: 2 fish slots
        """
        if not await require_enrollment(ctx):
            return
        
        if not fish_name:
            return await ctx.send("Usage: `gequipfish <fish name>`\nExample: `gequipfish lola`")
        
        # Find fish
        fish_data = None
        fish_id = None
        for fid, fdata in FISH.items():
            if fdata["name"].lower() == fish_name.lower():
                fish_data = fdata
                fish_id = fid
                break
        
        if not fish_data:
            return await ctx.send(f"<a:X_:1437951830393884788> Fish not found! Use `gaquarium` to see your fish.")
        
        # Check if user has reached the area level required for this fish
        fish_area = fish_data["area"]
        area_data = FISHING_AREAS.get(fish_area)
        if area_data:
            required_level = area_data["level_required"]
            user_level, _, _ = await get_account_level(ctx.author.id)
            
            if user_level < required_level:
                return await ctx.send(
                    f"<a:X_:1437951830393884788> You cannot equip **{fish_data['name']}** yet!\n"
                    f"You need to reach **Level {required_level}** to access {area_data['name']}.\n"
                    f"Your current level: **{user_level}**"
                )
        
        # Check if user owns this fish
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT quantity FROM caught_fish WHERE user_id = ? AND fish_id = ?",
                (ctx.author.id, fish_id)
            )
            result = await cursor.fetchone()
        
        if not result or result[0] == 0:
            return await ctx.send(f"<a:X_:1437951830393884788> You don't own any **{fish_data['name']}**! Use `gfish` to catch one.")
        
        # Check current equipped fish
        equipped = await self.get_equipped_fish(ctx.author.id)
        is_premium = await self.is_premium_user(ctx.author.id)
        max_slots = 2 if is_premium else 1
        
        # Check if already equipped
        for slot, fid in equipped:
            if fid == fish_id:
                return await ctx.send(f"<a:X_:1437951830393884788> **{fish_data['name']}** is already equipped!")
        
        # Check if slots are full
        if len(equipped) >= max_slots:
            return await ctx.send(
                f"<a:X_:1437951830393884788> All your fish slots are full! "
                f"Use `gunequipfish <fish name>` to unequip a fish first.\n"
                f"{'Premium users get 2 slots!' if not is_premium else ''}"
            )
        
        # Equip the fish
        next_slot = 1 if not equipped else max(s for s, _ in equipped) + 1
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO equipped_fish (user_id, slot, fish_id, equipped_at)
                VALUES (?, ?, ?, ?)
            """, (ctx.author.id, next_slot, fish_id, datetime.utcnow().isoformat()))
            await db.commit()
        
        # Success message
        embed = discord.Embed(
            title="✅ Fish Equipped!",
            description=f"{fish_data['emoji']} **{fish_data['name']}** is now your pet!",
            color=0x2ECC71
        )
        
        embed.add_field(
            name=f"✨ {fish_data['ability']}",
            value=fish_data['ability_desc'],
            inline=False
        )
        
        await send_embed(ctx, embed)
    
    @commands.command(name="unequipfish", aliases=["unequip", "fishunequip"])
    async def unequip_fish(self, ctx, *, fish_name: str = None):
        """Unequip a fish pet
        
        Usage: gunequipfish <fish name>
        """
        if not await require_enrollment(ctx):
            return
        
        if not fish_name:
            return await ctx.send("Usage: `gunequipfish <fish name>`\nExample: `gunequipfish lola`")
        
        # Find fish
        fish_data = None
        fish_id = None
        for fid, fdata in FISH.items():
            if fdata["name"].lower() == fish_name.lower():
                fish_data = fdata
                fish_id = fid
                break
        
        if not fish_data:
            return await ctx.send(f"<a:X_:1437951830393884788> Fish not found!")
        
        # Check if equipped
        equipped = await self.get_equipped_fish(ctx.author.id)
        is_equipped = any(fid == fish_id for _, fid in equipped)
        
        if not is_equipped:
            return await ctx.send(f"<a:X_:1437951830393884788> **{fish_data['name']}** is not equipped!")
        
        # Unequip
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM equipped_fish WHERE user_id = ? AND fish_id = ?",
                (ctx.author.id, fish_id)
            )
            await db.commit()
        
        embed = discord.Embed(
            title="❌ Fish Unequipped",
            description=f"{fish_data['emoji']} **{fish_data['name']}** has been unequipped.",
            color=0xE74C3C
        )
        
        await send_embed(ctx, embed)
    
    @commands.command(name="aquarium", aliases=["aqua", "mypets", "equippedfish"])
    async def show_pets(self, ctx):
        """View your currently equipped fish pets"""
        if not await require_enrollment(ctx):
            return
        
        equipped = await self.get_equipped_fish(ctx.author.id)
        is_premium = await self.is_premium_user(ctx.author.id)
        max_slots = 2 if is_premium else 1
        
        if not equipped:
            embed = discord.Embed(
                title="No Equipped Pets",
                description="You don't have any fish equipped!\nUse `gequipfish <fish name>` to equip a fish pet.",
                color=0xE74C3C
            )
            embed.add_field(
                name="Available Slots",
                value=f"{max_slots} slot{'s' if max_slots > 1 else ''}",
                inline=False
            )
            return await send_embed(ctx, embed)
        
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Pet Fish",
            color=0x3498DB
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        
        async with aiosqlite.connect(DB_PATH) as db:
            for slot, fish_id in equipped:
                fish_data = FISH.get(fish_id)
                if fish_data:
                    # Get fish level and XP
                    cursor = await db.execute(
                        "SELECT fish_level, fish_exp FROM caught_fish WHERE user_id = ? AND fish_id = ?",
                        (ctx.author.id, fish_id)
                    )
                    result = await cursor.fetchone()
                    fish_level = result[0] if result else 1
                    fish_exp = result[1] if result else 0
                    
                    embed.add_field(
                        name=f"Slot {slot}: {fish_data['emoji']} {fish_data['name']} (Lvl: {fish_level})",
                        value=f"**{fish_data['ability']}**\n{fish_data['ability_desc']}\n*XP: {fish_exp}/100*",
                        inline=False
                    )
        
        if is_premium:
            embed.set_footer(text="Premium: 2 fish slots unlocked!")
        else:
            embed.set_footer(text="Get Premium for a 2nd fish slot!")
        
        await send_embed(ctx, embed)
    
    async def show_fish_details(self, ctx, fish_name: str):
        """Show detailed info about a specific fish"""
        # Find fish by name
        fish_data = None
        fish_id = None
        for fid, fdata in FISH.items():
            if fdata["name"].lower() == fish_name.lower():
                fish_data = fdata
                fish_id = fid
                break
        
        if not fish_data:
            return await ctx.send(f"<a:X_:1437951830393884788> Fish not found! Use `gaquarium` to see all fish.")
        
        # Get user's quantity
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT quantity FROM caught_fish WHERE user_id = ? AND fish_id = ?",
                (ctx.author.id, fish_id)
            )
            result = await cursor.fetchone()
        
        quantity = result[0] if result else 0
        area_data = FISHING_AREAS[fish_data["area"]]
        
        embed = discord.Embed(
            title=f"{fish_data['emoji']} {fish_data['name']}",
            description=f"*{fish_data['rarity']} fish from {area_data['name']}*",
            color=area_data["color"]
        )
        
        embed.add_field(
            name="Location",
            value=f"{area_data['icon']} {area_data['name']}\n**Required Level:** {area_data['level_required']}",
            inline=True
        )
        
        embed.add_field(
            name="Value",
            value=f"{fish_data['value']:,} <:mora:1437958309255577681>",
            inline=True
        )
        
        embed.add_field(
            name="Owned",
            value=f"x{quantity}",
            inline=True
        )
        
        embed.add_field(
            name=f"✨ {fish_data['ability']}",
            value=fish_data['ability_desc'],
            inline=False
        )
        
        await send_embed(ctx, embed)
    
    @commands.command(name="tradefish", aliases=["fishtrade"])
    async def trade_fish(self, ctx, member: discord.Member = None, my_offer: str = None, their_offer: str = None):
        """Trade fish or mora with another player
        
        Usage: gtradefish @user <your_offer> <their_offer>
        
        Offer format:
        - Fish: fishname_quantity (e.g., lola_2, jellypop_1)
        - Mora: mora_amount (e.g., mora_50000)
        
        Examples:
        gtradefish @friend lola_2 jellypop_1
        gtradefish @friend koi_1 mora_100000
        gtradefish @friend mora_50000 midnight_1
        """
        if not await require_enrollment(ctx):
            return
        
        if not member or not my_offer or not their_offer:
            embed = discord.Embed(
                title="🐟 Fish Trading",
                description="Trade fish or mora with other players!",
                color=0x3498DB
            )
            embed.add_field(
                name="Usage",
                value="`gtradefish @user <your_offer> <their_offer>`",
                inline=False
            )
            embed.add_field(
                name="Offer Format",
                value=(
                    "**Fish:** `fishname_quantity`\n"
                    "Example: `lola_2`, `jellypop_1`\n\n"
                    "**Mora:** `mora_amount`\n"
                    "Example: `mora_50000`"
                ),
                inline=False
            )
            embed.add_field(
                name="Examples",
                value=(
                    "`gtradefish @friend lola_2 jellypop_1`\n"
                    "`gtradefish @friend koi_1 mora_100000`\n"
                    "`gtradefish @friend mora_50000 midnight_1`"
                ),
                inline=False
            )
            return await send_embed(ctx, embed)
        
        if member.bot:
            return await ctx.send("<a:X_:1437951830393884788> You can't trade with bots!")
        
        if member.id == ctx.author.id:
            return await ctx.send("<a:X_:1437951830393884788> You can't trade with yourself!")
        
        # Parse offers
        my_offer_data = await self.parse_trade_offer(my_offer)
        their_offer_data = await self.parse_trade_offer(their_offer)
        
        if not my_offer_data or not their_offer_data:
            return await ctx.send(
                "<a:X_:1437951830393884788> Invalid offer format!\n"
                "Use: `fishname_quantity` or `mora_amount`\n"
                "Example: `lola_2` or `mora_50000`"
            )
        
        # Validate sender's offer
        if my_offer_data['type'] == 'fish':
            fish_id, quantity = my_offer_data['fish_id'], my_offer_data['quantity']
            fish_data = FISH.get(fish_id)
            
            # Check ownership
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT quantity FROM caught_fish WHERE user_id = ? AND fish_id = ?",
                    (ctx.author.id, fish_id)
                )
                result = await cursor.fetchone()
            
            if not result or result[0] < quantity:
                return await ctx.send(
                    f"<a:X_:1437951830393884788> You don't have {quantity}x **{fish_data['name']}**!"
                )
            
            # Check if equipped
            equipped = await self.get_equipped_fish(ctx.author.id)
            if any(fid == fish_id for _, fid in equipped):
                return await ctx.send(
                    f"<a:X_:1437951830393884788> You can't trade **{fish_data['name']}** while it's equipped!"
                )
        
        elif my_offer_data['type'] == 'mora':
            amount = my_offer_data['amount']
            user_data = await get_user_data(ctx.author.id)
            if user_data['mora'] < amount:
                return await ctx.send(
                    f"<a:X_:1437951830393884788> You don't have {amount:,} <:mora:1437958309255577681>!"
                )
        
        # Validate receiver's offer
        if their_offer_data['type'] == 'fish':
            fish_id, quantity = their_offer_data['fish_id'], their_offer_data['quantity']
            fish_data = FISH.get(fish_id)
            
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT quantity FROM caught_fish WHERE user_id = ? AND fish_id = ?",
                    (member.id, fish_id)
                )
                result = await cursor.fetchone()
            
            if not result or result[0] < quantity:
                return await ctx.send(
                    f"<a:X_:1437951830393884788> {member.display_name} doesn't have {quantity}x **{fish_data['name']}**!"
                )
            
            # Check if equipped
            equipped = await self.get_equipped_fish(member.id)
            if any(fid == fish_id for _, fid in equipped):
                return await ctx.send(
                    f"<a:X_:1437951830393884788> {member.display_name} has **{fish_data['name']}** equipped and can't trade it!"
                )
        
        elif their_offer_data['type'] == 'mora':
            amount = their_offer_data['amount']
            user_data = await get_user_data(member.id)
            if user_data['mora'] < amount:
                return await ctx.send(
                    f"<a:X_:1437951830393884788> {member.display_name} doesn't have {amount:,} <:mora:1437958309255577681>!"
                )
        
        # Create trade confirmation embed
        embed = discord.Embed(
            title="🤝 Fish Trade Offer",
            description=f"{ctx.author.mention} wants to trade with {member.mention}!",
            color=0xF39C12
        )
        
        # Show offers
        my_offer_text = self.format_offer(my_offer_data)
        their_offer_text = self.format_offer(their_offer_data)
        
        embed.add_field(
            name=f"📤 {ctx.author.display_name} offers:",
            value=my_offer_text,
            inline=True
        )
        
        embed.add_field(
            name=f"📥 {member.display_name} receives:",
            value=my_offer_text,
            inline=True
        )
        
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        
        embed.add_field(
            name=f"📤 {member.display_name} offers:",
            value=their_offer_text,
            inline=True
        )
        
        embed.add_field(
            name=f"📥 {ctx.author.display_name} receives:",
            value=their_offer_text,
            inline=True
        )
        
        embed.set_footer(text=f"{member.display_name}, react with ✅ to accept or ❌ to decline")
        
        msg = await send_embed(ctx, embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        
        # Wait for reaction
        def check(reaction, user):
            return user.id == member.id and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            
            if str(reaction.emoji) == "❌":
                await ctx.send(f"{member.mention} declined the trade.")
                return
            
            # Execute trade
            async with aiosqlite.connect(DB_PATH) as db:
                # Transfer sender's offer
                if my_offer_data['type'] == 'fish':
                    fish_id, quantity = my_offer_data['fish_id'], my_offer_data['quantity']
                    
                    # Remove from sender
                    await db.execute(
                        "UPDATE caught_fish SET quantity = quantity - ? WHERE user_id = ? AND fish_id = ?",
                        (quantity, ctx.author.id, fish_id)
                    )
                    await db.execute(
                        "DELETE FROM caught_fish WHERE quantity <= 0"
                    )
                    
                    # Add to receiver
                    await db.execute("""
                        INSERT INTO caught_fish (user_id, fish_id, quantity)
                        VALUES (?, ?, ?)
                        ON CONFLICT(user_id, fish_id) DO UPDATE SET quantity = quantity + ?
                    """, (member.id, fish_id, quantity, quantity))
                
                elif my_offer_data['type'] == 'mora':
                    amount = my_offer_data['amount']
                    sender_data = await get_user_data(ctx.author.id)
                    receiver_data = await get_user_data(member.id)
                    await update_user_data(ctx.author.id, mora=sender_data['mora'] - amount)
                    await update_user_data(member.id, mora=receiver_data['mora'] + amount)
                
                # Transfer receiver's offer
                if their_offer_data['type'] == 'fish':
                    fish_id, quantity = their_offer_data['fish_id'], their_offer_data['quantity']
                    
                    # Remove from receiver
                    await db.execute(
                        "UPDATE caught_fish SET quantity = quantity - ? WHERE user_id = ? AND fish_id = ?",
                        (quantity, member.id, fish_id)
                    )
                    await db.execute(
                        "DELETE FROM caught_fish WHERE quantity <= 0"
                    )
                    
                    # Add to sender
                    await db.execute("""
                        INSERT INTO caught_fish (user_id, fish_id, quantity)
                        VALUES (?, ?, ?)
                        ON CONFLICT(user_id, fish_id) DO UPDATE SET quantity = quantity + ?
                    """, (ctx.author.id, fish_id, quantity, quantity))
                
                elif their_offer_data['type'] == 'mora':
                    amount = their_offer_data['amount']
                    sender_data = await get_user_data(ctx.author.id)
                    receiver_data = await get_user_data(member.id)
                    await update_user_data(member.id, mora=receiver_data['mora'] - amount)
                    await update_user_data(ctx.author.id, mora=sender_data['mora'] + amount)
                
                await db.commit()
            
            # Success message
            success_embed = discord.Embed(
                title="✅ Trade Complete!",
                description=f"{ctx.author.mention} and {member.mention} have completed their trade!",
                color=0x2ECC71
            )
            await send_embed(ctx, success_embed)
            
        except TimeoutError:
            await ctx.send("Trade offer expired.")
    
    async def parse_trade_offer(self, offer: str):
        """Parse a trade offer string"""
        if not offer:
            return None
        
        offer = offer.lower().strip()
        
        # Check if mora
        if offer.startswith("mora_"):
            try:
                amount = int(offer.split("_")[1])
                return {'type': 'mora', 'amount': amount}
            except:
                return None
        
        # Otherwise, it's a fish
        parts = offer.split("_")
        if len(parts) < 2:
            return None
        
        try:
            quantity = int(parts[-1])
            fish_name = "_".join(parts[:-1])
            
            # Find fish by name
            for fish_id, fish_data in FISH.items():
                if fish_data['name'].lower().replace(" ", "") == fish_name.replace(" ", ""):
                    return {'type': 'fish', 'fish_id': fish_id, 'quantity': quantity}
            
            # Try matching with underscores as spaces
            for fish_id, fish_data in FISH.items():
                if fish_data['name'].lower().replace(" ", "_") == fish_name:
                    return {'type': 'fish', 'fish_id': fish_id, 'quantity': quantity}
            
            return None
        except:
            return None
    
    def format_offer(self, offer_data):
        """Format an offer for display"""
        if offer_data['type'] == 'mora':
            return f"{offer_data['amount']:,} <:mora:1437958309255577681>"
        elif offer_data['type'] == 'fish':
            fish_data = FISH[offer_data['fish_id']]
            return f"{offer_data['quantity']}x {fish_data['emoji']} **{fish_data['name']}**"
        return "Unknown"
    
    @commands.command(name="listfish", aliases=["sellfish", "fishlist"])
    async def list_fish(self, ctx, price: int = None, *, fish_name: str = None):
        """List a fish for sale on the Player Market
        
        Usage: glistfish <price> <fish name>
        Example: glistfish 50000 jellypop
        """
        if not await require_enrollment(ctx):
            return
        
        if price is None or fish_name is None:
            return await ctx.send(
                "<a:X_:1437951830393884788> Usage: `glistfish <price> <fish name>`\n"
                "Example: `glistfish 50000 jellypop`"
            )
        
        if price < 1000:
            return await ctx.send("<a:X_:1437951830393884788> Minimum listing price is 1,000 <:mora:1437958309255577681>")
        
        # Find fish
        fish_data = None
        fish_id = None
        for fid, fdata in FISH.items():
            if fdata["name"].lower() == fish_name.lower():
                fish_data = fdata
                fish_id = fid
                break
        
        if not fish_data:
            return await ctx.send(f"<a:X_:1437951830393884788> Fish not found! Use `gaquarium` to see your fish.")
        
        # Check if user owns this fish
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT quantity FROM caught_fish WHERE user_id = ? AND fish_id = ?",
                (ctx.author.id, fish_id)
            )
            result = await cursor.fetchone()
        
        if not result or result[0] == 0:
            return await ctx.send(f"<a:X_:1437951830393884788> You don't own any **{fish_data['name']}**!")
        
        # Check if fish is equipped
        equipped = await self.get_equipped_fish(ctx.author.id)
        is_equipped = any(fid == fish_id for _, fid in equipped)
        
        if is_equipped:
            return await ctx.send(
                f"<a:X_:1437951830393884788> You can't list **{fish_data['name']}** while it's equipped!\n"
                f"Use `gunequipfish {fish_data['name'].lower()}` first."
            )
        
        # Remove from inventory and add to player market
        async with aiosqlite.connect(DB_PATH) as db:
            # Remove fish
            await db.execute(
                "UPDATE caught_fish SET quantity = quantity - 1 WHERE user_id = ? AND fish_id = ?",
                (ctx.author.id, fish_id)
            )
            await db.execute(
                "DELETE FROM caught_fish WHERE quantity <= 0"
            )
            
            # Add to player market as "fish_<fish_id>"
            await db.execute("""
                INSERT INTO black_market_listings (seller_id, item_id, price, quantity, listed_at)
                VALUES (?, ?, ?, 1, ?)
            """, (ctx.author.id, f"fish_{fish_id}", price, datetime.utcnow().isoformat()))
            
            await db.commit()
        
        embed = discord.Embed(
            title="🐟 Fish Listed!",
            description=f"Your {fish_data['emoji']} **{fish_data['name']}** is now listed for {price:,} <:mora:1437958309255577681>",
            color=0x3498DB
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.set_footer(text="You'll be notified when someone buys it! • View with gpm")
        await send_embed(ctx, embed)
    
    @commands.command(name="craftrod", aliases=["craft_rod", "makerod"])
    async def craft_rod(self, ctx):
        """Craft a Wooden Fishing Rod
        
        Requirements:
        - 1x String
        - 1x Wood
        - 250,000 Mora
        """
        if not await require_enrollment(ctx):
            return
        
        # Check if user already has a rod
        rod_tier, _ = await self.get_fishing_rod(ctx.author.id)
        if rod_tier > 0:
            return await ctx.send(
                f"<a:X_:1437951830393884788> You already have a fishing rod! "
                f"Use `gupgraderod` to upgrade it or `grepairrod` to fix it."
            )
        
        # Check materials
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT item_id, quantity FROM inventory WHERE user_id = ? AND item_id IN ('string', 'wood')",
                (ctx.author.id,)
            )
            materials = {row[0]: row[1] for row in await cursor.fetchall()}
        
        if materials.get('string', 0) < 1 or materials.get('wood', 0) < 1:
            return await ctx.send(
                "<a:X_:1437951830393884788> You don't have the required materials!\n"
                "**Required:**\n"
                "• 1x <:string:1459002611217989702> String\n"
                "• 1x <:logs:1459003610212995285> Wood\n"
                "• 250,000 <:mora:1437958309255577681>\n\n"
                "Get materials from the Black Market!"
            )
        
        # Check mora
        user_data = await get_user_data(ctx.author.id)
        if user_data['mora'] < 250000:
            return await ctx.send(
                f"<a:X_:1437951830393884788> You need **250,000** <:mora:1437958309255577681> to craft the rod! "
                f"You have: {user_data['mora']:,}"
            )
        
        # Consume materials and mora
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = 'string'",
                (ctx.author.id,)
            )
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = 'wood'",
                (ctx.author.id,)
            )
            await db.commit()
        
        await update_user_data(ctx.author.id, mora=user_data['mora'] - 250000)
        
        # Give wooden rod
        await self.set_fishing_rod(ctx.author.id, 1, 100)
        
        embed = discord.Embed(
            title="✅ Fishing Rod Crafted!",
            description="You've successfully crafted a <:wooden:1458224723342262555> **Wooden Fishing Rod**!",
            color=0x2ECC71
        )
        embed.add_field(name="Durability", value="100/100", inline=True)
        embed.add_field(name="Bonus Effects", value="None", inline=True)
        embed.set_footer(text="Use gfish <area> to start fishing! • Upgrade with gupgraderod")
        await send_embed(ctx, embed)
    
    @commands.command(name="upgraderod", aliases=["upgrade_rod", "rodupgrade"])
    async def upgrade_rod(self, ctx):
        """Upgrade your fishing rod
        
        Wooden → Silver: Fishing Template + Silver Scrap + 5 TideShells + 2M Mora
        Silver → Golden: Fishing Template + Gold Scrap + 10 TideShells + 5M Mora
        """
        if not await require_enrollment(ctx):
            return
        
        rod_tier, rod_durability = await self.get_fishing_rod(ctx.author.id)
        if rod_tier == 0:
            return await ctx.send(
                "<a:X_:1437951830393884788> You don't have a fishing rod! Craft one with `gcraftrod`."
            )
        
        if rod_tier == 3:
            return await ctx.send(
                "<a:X_:1437951830393884788> Your <:gold:1458224862605873443> **Golden Fishing Rod** is already maxed!"
            )
        
        # Determine upgrade requirements
        if rod_tier == 1:  # Wooden → Silver
            required_scrap = 'silver_scrap'
            scrap_name = "Silver Scrap"
            required_tideshells = 5
            cost = 2000000
            new_tier = 2
            new_durability = 150
        else:  # Silver → Golden
            required_scrap = 'gold_scrap'
            scrap_name = "Gold Scrap"
            required_tideshells = 10
            cost = 5000000
            new_tier = 3
            new_durability = 200
        
        # Check materials
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT item_id, quantity FROM inventory WHERE user_id = ? AND item_id IN ('fishing_template', ?, 'tideshells')",
                (ctx.author.id, required_scrap)
            )
            materials = {row[0]: row[1] for row in await cursor.fetchall()}
        
        if materials.get('fishing_template', 0) < 1 or materials.get(required_scrap, 0) < 1 or materials.get('tideshells', 0) < required_tideshells:
            return await ctx.send(
                f"<a:X_:1437951830393884788> You don't have the required materials!\n"
                f"**Required:**\n"
                f"• 1x Fishing Template\n"
                f"• 1x {scrap_name}\n"
                f"• {required_tideshells}x <:TideShells:1459005927389663445> TideShells\n"
                f"• {cost:,} <:mora:1437958309255577681>\n\n"
                f"Fish for materials or check the Black Market!"
            )
        
        # Check mora
        user_data = await get_user_data(ctx.author.id)
        if user_data['money'] < cost:
            return await ctx.send(
                f"<a:X_:1437951830393884788> You need **{cost:,}** <:mora:1437958309255577681> to upgrade! "
                f"You have: {user_data['money']:,}"
            )
        
        # Consume materials and mora
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = 'fishing_template'",
                (ctx.author.id,)
            )
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                (ctx.author.id, required_scrap)
            )
            await db.execute(
                "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = 'tideshells'",
                (required_tideshells, ctx.author.id)
            )
            await db.commit()
        
        await update_user_data(ctx.author.id, mora=user_data['mora'] - cost)
        
        # Upgrade rod
        await self.set_fishing_rod(ctx.author.id, new_tier, new_durability)
        new_rod_data = FISHING_RODS[new_tier]
        
        embed = discord.Embed(
            title="✨ Fishing Rod Upgraded!",
            description=f"Your rod has been upgraded to {new_rod_data['emoji']} **{new_rod_data['name']}**!",
            color=0xF39C12
        )
        embed.add_field(name="Durability", value=f"{new_durability}/{new_durability}", inline=True)
        embed.add_field(name="Catch Rate Bonus", value=f"+{int(new_rod_data['catch_rate_bonus']*100)}%", inline=True)
        embed.add_field(name="Reward Bonus", value=f"+{int(new_rod_data['reward_bonus']*100)}%", inline=True)
        embed.set_footer(text="Better rods catch more fish and bonus rewards!")
        await send_embed(ctx, embed)
    
    @commands.command(name="repairrod", aliases=["repair_rod", "fixrod"])
    async def repair_rod(self, ctx, amount: int = None):
        """Repair your fishing rod
        
        Wooden: 1 Wood = 10 durability
        Silver: 1 Silver Scrap = 15 durability
        Golden: 1 Gold Scrap = 20 durability
        """
        if not await require_enrollment(ctx):
            return
        
        rod_tier, rod_durability = await self.get_fishing_rod(ctx.author.id)
        if rod_tier == 0:
            return await ctx.send(
                "<a:X_:1437951830393884788> You don't have a fishing rod! Craft one with `gcraftrod`."
            )
        
        rod_data = FISHING_RODS[rod_tier]
        
        if rod_durability >= rod_data['max_durability']:
            return await ctx.send(
                f"<a:X_:1437951830393884788> Your {rod_data['emoji']} **{rod_data['name']}** is already at full durability!"
            )
        
        # Determine repair material and durability per material
        repair_material = rod_data['repair_material']
        if rod_tier == 1:
            durability_per_item = 10
            material_name = "<:logs:1459003610212995285> Wood"
        elif rod_tier == 2:
            durability_per_item = 15
            material_name = "<:silverscrap:1459002718810279957> Silver Scrap"
        else:
            durability_per_item = 20
            material_name = "<:goldscrap:1459002663193546846> Gold Scrap"
        
        # Check how much material the user has
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
                (ctx.author.id, repair_material)
            )
            result = await cursor.fetchone()
            available = result[0] if result else 0
        
        if available == 0:
            return await ctx.send(
                f"<a:X_:1437951830393884788> You don't have any **{material_name}** to repair your rod!\n"
                f"{'Get wood from the Black Market!' if rod_tier == 1 else 'Fish in higher level areas to find scraps!'}"
            )
        
        # Calculate how much durability is needed
        durability_needed = rod_data['max_durability'] - rod_durability
        items_needed = (durability_needed + durability_per_item - 1) // durability_per_item  # Ceiling division
        
        if amount is None:
            amount = min(items_needed, available)
        else:
            amount = min(amount, available, items_needed)
        
        if amount == 0:
            return await ctx.send(
                f"<a:X_:1437951830393884788> Invalid repair amount!"
            )
        
        # Calculate actual durability gained
        durability_gained = min(amount * durability_per_item, durability_needed)
        new_durability = rod_durability + durability_gained
        
        # Consume materials
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ?",
                (amount, ctx.author.id, repair_material)
            )
            await db.commit()
        
        # Update rod durability
        await self.set_fishing_rod(ctx.author.id, rod_tier, new_durability)
        
        embed = discord.Embed(
            title="🔧 Fishing Rod Repaired!",
            description=f"Used **{amount}x {material_name}** to repair your {rod_data['emoji']} **{rod_data['name']}**",
            color=0x3498DB
        )
        embed.add_field(name="Durability Restored", value=f"+{durability_gained}", inline=True)
        embed.add_field(name="Current Durability", value=f"{new_durability}/{rod_data['max_durability']}", inline=True)
        embed.set_footer(text="Keep your rod maintained for successful fishing!")
        await send_embed(ctx, embed)
    
    @commands.command(name="upgradefish", aliases=["upgrade_fish", "evolvefish"])
    async def upgrade_fish(self, ctx, *, fish_name: str = None):
        """Upgrade a fish at level 25 (requires 10 TideShells, 3 extra fish copies, 1M mora)
        
        Usage: gupgradefish <fish name>
        """
        if not await require_enrollment(ctx):
            return
        
        if not fish_name:
            return await ctx.send("Usage: `gupgradefish <fish name>`\nExample: `gupgradefish lola`")
        
        # Find fish
        fish_data = None
        fish_id = None
        for fid, fdata in FISH.items():
            if fdata["name"].lower() == fish_name.lower():
                fish_data = fdata
                fish_id = fid
                break
        
        if not fish_data:
            return await ctx.send(f"<a:X_:1437951830393884788> Fish not found!")
        
        # Check if user owns this fish
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT quantity, fish_level FROM caught_fish WHERE user_id = ? AND fish_id = ?",
                (ctx.author.id, fish_id)
            )
            result = await cursor.fetchone()
        
        if not result:
            return await ctx.send(f"<a:X_:1437951830393884788> You don't own any {fish_data['emoji']} **{fish_data['name']}**!")
        
        fish_quantity = result[0]
        fish_level = result[1]
        
        if fish_quantity < 4:
            return await ctx.send(
                f"<a:X_:1437951830393884788> You need **4 total** {fish_data['emoji']} **{fish_data['name']}** to upgrade!\n"
                f"Current: {fish_quantity}/4"
            )
        
        # Check fish level
        if fish_level < 25:
            return await ctx.send(
                f"<a:X_:1437951830393884788> Your {fish_data['emoji']} **{fish_data['name']}** must be **Level 25** to upgrade!\n"
                f"Current level: {fish_level}"
            )
        
        # Check TideShells
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = 'tideshells'",
                (ctx.author.id,)
            )
            result = await cursor.fetchone()
        
        tideshells = result[0] if result else 0
        
        if tideshells < 10:
            return await ctx.send(
                f"<a:X_:1437951830393884788> You need **10x** <:TideShells:1459005927389663445> TideShells to upgrade!\n"
                f"Current: {tideshells}/10"
            )
        
        # Check mora
        user_data = await get_user_data(ctx.author.id)
        if user_data['mora'] < 1000000:
            return await ctx.send(
                f"<a:X_:1437951830393884788> You need **1,000,000** <:mora:1437958309255577681> to upgrade!\n"
                f"Current: {user_data['mora']:,}"
            )
        
        # Consume materials
        async with aiosqlite.connect(DB_PATH) as db:
            # Remove 3 fish copies (keep 1)
            await db.execute(
                "UPDATE caught_fish SET quantity = quantity - 3 WHERE user_id = ? AND fish_id = ?",
                (ctx.author.id, fish_id)
            )
            
            # Remove TideShells
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 10 WHERE user_id = ? AND item_id = 'tideshells'",
                (ctx.author.id,)
            )
            
            # Clean up zero quantities
            await db.execute("DELETE FROM inventory WHERE quantity <= 0")
            
            await db.commit()
        
        # Deduct mora
        await update_user_data(ctx.author.id, mora=user_data['mora'] - 1000000)
        
        # TODO: Actually upgrade the fish in database (increase rarity, stats, etc.) when system is implemented
        
        embed = discord.Embed(
            title="✨ Fish Upgraded!",
            description=f"Your {fish_data['emoji']} **{fish_data['name']}** has been upgraded!",
            color=0xFFD700
        )
        
        embed.add_field(
            name="Materials Used",
            value=(
                f"• 3x {fish_data['emoji']} {fish_data['name']}\n"
                f"• 10x <:TideShells:1459005927389663445> TideShells\n"
                f"• 1,000,000 <:mora:1437958309255577681> Mora"
            ),
            inline=False
        )
        
        embed.set_footer(text="Fish upgrade system coming soon!")
        await send_embed(ctx, embed)
    
    @commands.command(name="grantenergy")
    async def grant_energy(self, ctx, user: discord.Member, amount: int):
        """Grant fishing energy to a user (Owner Only)
        
        Usage: ggrantenergy @user <amount>
        """
        from config import OWNER_ID
        if ctx.author.id != OWNER_ID:
            return
        
        if amount < 1 or amount > 50:
            return await ctx.send("<a:X_:1437951830393884788> Amount must be between 1 and 50!")
        
        # Ensure user exists in database
        from utils.database import ensure_user_db, add_fishing_energy
        await ensure_user_db(user.id)
        
        # Get current energy and max
        is_premium = await self.is_premium_user(user.id)
        max_energy = 9 if is_premium else 6
        
        # Add energy (will cap at max)
        await add_fishing_energy(user.id, amount, is_premium)
        
        embed = discord.Embed(
            title="<:energy:1459189042574004224> Energy Granted",
            description=f"Granted **{amount}** <:energy:1459189042574004224> energy to {user.mention}",
            color=0x2ECC71
        )
        embed.add_field(name="Max Capacity", value=f"{max_energy} energy", inline=False)
        await send_embed(ctx, embed)

async def setup(bot):
    await bot.add_cog(Fishing(bot))
