"""Rob System - Rob other users with items and defenses"""
import discord
from discord.ext import commands
import aiosqlite
import random
from datetime import datetime, timedelta
from config import DB_PATH
from utils.database import get_user_data, update_user_data, ensure_user_db, add_account_exp
from utils.embed import send_embed
from utils.transaction_logger import log_transaction


class Rob(commands.Cog):
    """Rob system with items and defenses"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        """Initialize database tables"""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # User items inventory
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS rob_items (
                        user_id INTEGER PRIMARY KEY,
                        shotgun INTEGER DEFAULT 0,
                        mask INTEGER DEFAULT 0,
                        night_vision INTEGER DEFAULT 0,
                        lockpicker INTEGER DEFAULT 0,
                        guard_dog INTEGER DEFAULT 0,
                        guard_dog_expires TEXT,
                        spiky_fence INTEGER DEFAULT 0,
                        lock INTEGER DEFAULT 0
                    )
                """)
                
                # Rob cooldowns
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS rob_cooldowns (
                        user_id INTEGER PRIMARY KEY,
                        last_rob TEXT,
                        was_successful INTEGER DEFAULT 0
                    )
                """)
                
                # Migration: Add was_successful column if it doesn't exist
                try:
                    await db.execute("ALTER TABLE rob_cooldowns ADD COLUMN was_successful INTEGER DEFAULT 0")
                    await db.commit()
                except:
                    pass  # Column already exists
                
                await db.commit()
        except Exception as e:
            print(f"Error loading Rob cog: {e}")
    
    async def get_user_items(self, user_id):
        """Get user's rob items from database"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT shotgun, mask, night_vision, lockpicker, guard_dog, guard_dog_expires, spiky_fence, lock FROM rob_items WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                result = await cursor.fetchone()
                if result:
                    return result
                else:
                    # Insert default values if user doesn't exist
                    await db.execute(
                        "INSERT OR IGNORE INTO rob_items (user_id) VALUES (?)",
                        (user_id,)
                    )
                    await db.commit()
                    return (0, 0, 0, 0, 0, None, 0, 0)
    
    async def check_guard_dog_expired(self, user_id):
        """Check if user's guard dog has expired and remove it"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guard_dog_expires FROM rob_items WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                result = await cursor.fetchone()
                if result and result[0]:
                    expiry = datetime.fromisoformat(result[0])
                    if datetime.now() > expiry:
                        await db.execute(
                            "UPDATE rob_items SET guard_dog = 0, guard_dog_expires = NULL WHERE user_id = ?",
                            (user_id,)
                        )
                        await db.commit()
    
    @commands.command(name="rob")
    async def rob_user(self, ctx, target: discord.Member = None):
        """Rob another user! Buy items to increase success rate
        
        Usage: grob @user
        Example: grob @someone
        
        Base success: 20%
        Cooldown: 1 hour
        
        Use `gshop` to buy items that help you rob or defend!
        """
        # Ensure both users exist in database
        await ensure_user_db(ctx.author.id)
        
        if not target:
            return await ctx.send("Usage: grob @user\\nExample: grob @someone")
        
        if target.id == ctx.author.id:
            return await ctx.send("❌ You can't rob yourself!")
        
        if target.bot:
            return await ctx.send("❌ You can't rob bots!")
        
        # Owner is unrobbable
        from config import OWNER_ID
        if target.id == OWNER_ID:
            return await ctx.send("❌ You can't rob the bot owner!")
        
        await ensure_user_db(target.id)
        
        # Check for Plasma Canon (ultimate rob weapon)
        from utils.database import has_inventory_item, consume_inventory_item
        has_plasma = await has_inventory_item(ctx.author.id, "plasma_canon")
        
        if has_plasma > 0:
            # PLASMA CANON MODE: Guaranteed success, steals from wallet AND bank, no cooldown
            target_data = await get_user_data(target.id)
            target_mora = target_data.get('mora', 0)
            
            # Check bank balance too
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT deposited_amount FROM user_bank_deposits WHERE user_id = ?",
                    (target.id,)
                ) as cursor:
                    bank_result = await cursor.fetchone()
                    bank_balance = bank_result[0] if bank_result else 0
            
            total_money = target_mora + bank_balance
            
            if total_money < 100000:
                return await ctx.send(f"<a:X_:1437951830393884788> {target.mention} doesn't have enough money to rob! (min 100,000 total)")
            
            # Consume plasma canon
            await consume_inventory_item(ctx.author.id, "plasma_canon")
            
            # Calculate stolen amount from wallet (2% × 3 = 6% of mora)
            steal_percentage = 0.06  # Triple the normal 2%
            stolen_from_wallet = int(target_mora * steal_percentage)
            stolen_from_wallet = min(stolen_from_wallet, target_mora)
            
            # Also steal from bank (15% of deposited amount)
            stolen_from_bank = int(bank_balance * 0.15)  # 15% of bank
            stolen_amount = stolen_from_wallet + stolen_from_bank
            
            # Transfer money from wallet
            robber_data = await get_user_data(ctx.author.id)
            await update_user_data(ctx.author.id, mora=robber_data['mora'] + stolen_amount)
            await update_user_data(target.id, mora=target_mora - stolen_from_wallet)
            
            # Transfer money from bank
            if stolen_from_bank > 0:
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE user_bank_deposits SET deposited_amount = deposited_amount - ? WHERE user_id = ?",
                        (stolen_from_bank, target.id)
                    )
                    await db.commit()
            
            # Award XP
            xp_reward = random.randint(150, 300)
            leveled_up, new_level, old_level = await add_account_exp(ctx.author.id, xp_reward)
            
            # Log transaction
            await log_transaction(
                ctx.author.id,
                "plasma_rob",
                stolen_amount,
                f"Plasma Canon robbed {target.display_name} ({target.id})"
            )
            
            breakdown = f"💰 Wallet: **{stolen_from_wallet:,}** <:mora:1437958309255577681>\n"
            if stolen_from_bank > 0:
                breakdown += f"🏦 Bank: **{stolen_from_bank:,}** <:mora:1437958309255577681>\n"
            breakdown += f"\n💥 **Total Extracted: {stolen_amount:,}** <:mora:1437958309255577681>"
            
            embed = discord.Embed(
                title="<:plasmacanon:1457975521521434624> INITIATING PLASMA CANON",
                description=f"**TARGET:** {target.mention}\n⚡ **FIRING...** ⚡\n\n{breakdown}",
                color=0xFF4500
            )
            embed.add_field(
                name="⚡ Weapon Efficiency",
                value="**3x wallet extraction + 15% bank breach** | All defenses neutralized",
                inline=True
            )
            embed.add_field(
                name="<:exp:1437553839359397928> Combat XP",
                value=f"+{xp_reward} XP",
                inline=True
            )
            embed.add_field(
                name="<:plasmacanon:1457975521521434624> Status",
                value="**Weapon discharged successfully**\n└ 100% accuracy\n└ Cooldown bypassed\n└ Defense systems overridden",
                inline=False
            )
            
            if leveled_up:
                embed.add_field(
                    name="<a:Trophy:1438199339586424925> Level Up!",
                    value=f"Level {old_level} <a:arrow:1437968863026479258> Level {new_level}",
                    inline=False
                )
            
            embed.set_footer(text="Plasma Canon consumed | Ready to fire again anytime")
            return await send_embed(ctx, embed)
        
        # NORMAL ROB FLOW (no plasma canon)
        # Check premium status
        premium_cog = self.bot.get_cog('Premium')
        is_premium = False
        if premium_cog:
            is_premium = await premium_cog.is_premium(ctx.author.id)
        
        # Check cooldown (premium: 20min success/40min fail, normal: 30min success/60min fail)
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT last_rob, was_successful FROM rob_cooldowns WHERE user_id = ?",
                (ctx.author.id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0]:
                last_rob = datetime.fromisoformat(row[0])
                was_successful = row[1] if len(row) > 1 else 0
                
                # Premium gets reduced cooldown
                if is_premium:
                    cooldown_minutes = 20 if was_successful else 40
                else:
                    cooldown_minutes = 30 if was_successful else 60
                cooldown = last_rob + timedelta(minutes=cooldown_minutes)
                
                if datetime.now() < cooldown:
                    time_left = cooldown - datetime.now()
                    minutes = int(time_left.total_seconds() // 60)
                    seconds = int(time_left.total_seconds() % 60)
                    premium_tip = "" if is_premium else "\n⭐ Premium users get shorter cooldowns!"
                    return await ctx.send(f"⏰ You can rob again in **{minutes}m {seconds}s**\n💡 Use <:plasmacanon:1457975521521434624> **Plasma Canon** to bypass cooldown!{premium_tip}")
        
        # Check if target has money
        target_data = await get_user_data(target.id)
        target_mora = target_data.get('mora', 0)
        
        if target_mora < 100000:
            return await ctx.send(f"❌ {target.mention} doesn't have enough money to rob! (min 100,000)")
        
        # Get robber's items
        robber_items = await self.get_user_items(ctx.author.id)
        shotgun, mask, night_vision, lockpicker, guard_dog, _, spiky_fence, lock_item = robber_items
        
        # Get victim's defense items
        victim_items = await self.get_user_items(target.id)
        v_shotgun, v_mask, v_night_vision, v_lockpicker, v_guard_dog, v_guard_dog_expires, v_spiky_fence, v_lock = victim_items
        
        # Check if victim's guard dog expired
        await self.check_guard_dog_expired(target.id)
        victim_items = await self.get_user_items(target.id)
        v_guard_dog = victim_items[4]
        
        # Check if victim has lock (100% protection, breaks after use)
        if v_lock:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE rob_items SET lock = 0 WHERE user_id = ?",
                    (target.id,)
                )
                await db.commit()
            
            embed = discord.Embed(
                title="🔒 Robbery Failed!",
                description=f"{target.mention}'s **Lock** protected them!",
                color=0xE74C3C
            )
            embed.add_field(
                name="🛡️ Defense",
                value="The lock has been broken and needs replacement.",
                inline=False
            )
            await send_embed(ctx, embed)
            return
        
        # Calculate success rate
        success_rate = 20  # Base 20%
        
        # Premium bonus
        if is_premium:
            success_rate += 15  # Premium gets +15% base success
        
        # Robber bonuses
        if shotgun:
            success_rate += 20
        if mask and night_vision and lockpicker:
            success_rate += 25  # Full thief pack bonus
        
        # Victim defenses
        defense_rate = 0
        if v_guard_dog:
            defense_rate += 25
        if v_spiky_fence:
            defense_rate += 5
        
        # Final success rate
        final_success_rate = max(5, success_rate - defense_rate)  # Minimum 5% chance
        
        # Roll for success
        roll = random.randint(1, 100)
        success = roll <= final_success_rate
        
        # Consume single-use items
        async with aiosqlite.connect(DB_PATH) as db:
            if mask:
                await db.execute(
                    "UPDATE rob_items SET mask = mask - 1 WHERE user_id = ?",
                    (ctx.author.id,)
                )
            if night_vision:
                await db.execute(
                    "UPDATE rob_items SET night_vision = night_vision - 1 WHERE user_id = ?",
                    (ctx.author.id,)
                )
            if lockpicker:
                await db.execute(
                    "UPDATE rob_items SET lockpicker = lockpicker - 1 WHERE user_id = ?",
                    (ctx.author.id,)
                )
            
            await db.commit()
        
        if success:
            # Calculate stolen amount (2% of mora)
            steal_percentage = 0.02
            stolen_amount = int(target_mora * steal_percentage)
            stolen_amount = min(stolen_amount, target_mora)  # Can't steal more than they have
            
            # Transfer money
            robber_data = await get_user_data(ctx.author.id)
            await update_user_data(ctx.author.id, mora=robber_data['mora'] + stolen_amount)
            await update_user_data(target.id, mora=target_mora - stolen_amount)
            
            # Award XP for successful robbery
            xp_reward = random.randint(50, 100)
            leveled_up, new_level, old_level = await add_account_exp(ctx.author.id, xp_reward)
            
            # Log transaction
            await log_transaction(
                ctx.author.id,
                "rob_success",
                stolen_amount,
                f"Robbed {target.display_name} ({target.id})"
            )
            
            # Set cooldown to 30 minutes for successful robbery
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """INSERT INTO rob_cooldowns (user_id, last_rob, was_successful)
                       VALUES (?, ?, 1)
                       ON CONFLICT(user_id) DO UPDATE SET last_rob = ?, was_successful = 1""",
                    (ctx.author.id, datetime.now().isoformat(), datetime.now().isoformat())
                )
                await db.commit()
            
            embed = discord.Embed(
                title="💰 Robbery Successful!",
                description=f"You robbed **{stolen_amount:,}** <:mora:1437958309255577681> from {target.mention}!",
                color=0x2ECC71
            )
            embed.add_field(
                name="Amount Stolen",
                value=f"2% of their mora",
                inline=True
            )
            embed.add_field(
                name="XP Gained",
                value=f"+{xp_reward} XP",
                inline=True
            )
            
            if leveled_up:
                embed.add_field(
                    name="<a:Trophy:1438199339586424925> Level Up!",
                    value=f"Level {old_level} <a:arrow:1437968863026479258> Level {new_level}",
                    inline=False
                )
            
            embed.set_footer(text="Cooldown: 30 minutes")
        else:
            # Set cooldown to 1 hour for failed robbery
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """INSERT INTO rob_cooldowns (user_id, last_rob, was_successful)
                       VALUES (?, ?, 0)
                       ON CONFLICT(user_id) DO UPDATE SET last_rob = ?, was_successful = 0""",
                    (ctx.author.id, datetime.now().isoformat(), datetime.now().isoformat())
                )
                await db.commit()
            
            # Take penalty for failed robbery (5k-50k)
            robber_data = await get_user_data(ctx.author.id)
            robber_mora = robber_data.get('mora', 0)
            penalty_amount = random.randint(5000, 50000)
            # Only apply penalty if robber has enough
            penalty_amount = min(penalty_amount, robber_mora)
            
            if penalty_amount > 0:
                await update_user_data(ctx.author.id, mora=robber_mora - penalty_amount)
            
            # Log transaction
            await log_transaction(
                ctx.author.id,
                "rob_fail",
                -penalty_amount if penalty_amount > 0 else 0,
                f"Failed to rob {target.display_name}, lost {penalty_amount:,} mora"
            )
            
            # Robbery failed
            embed = discord.Embed(
                title="❌ Robbery Failed!",
                description=f"You failed to rob {target.mention}!",
                color=0xE74C3C
            )
            
            if penalty_amount > 0:
                embed.add_field(
                    name="💸 Penalty",
                    value=f"Lost **{penalty_amount:,}** <:mora:1437958309255577681>",
                    inline=True
                )
            
            embed.set_footer(text="Cooldown: 1 hour")
            
            defenses = []
            if v_guard_dog:
                defenses.append("🐕 Guard Dog (-25%)")
            if v_spiky_fence:
                defenses.append("🔱 Spiky Fence (-5%)")
            
            if defenses:
                embed.add_field(
                    name="🛡️ Victim's Defenses",
                    value="\\n".join(defenses),
                    inline=False
                )
        
        await send_embed(ctx, embed)


async def setup(bot):
    await bot.add_cog(Rob(bot))
