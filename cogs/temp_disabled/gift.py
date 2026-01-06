import discord
from discord.ext import commands
import aiosqlite
from config import DB_PATH
from utils.embed import send_embed
from utils.database import get_user_data, ensure_user_db


class Gift(commands.Cog):
    """Gift items to other users."""

    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        """Create gift history table."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS gift_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER NOT NULL,
                    receiver_id INTEGER NOT NULL,
                    item_type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    @commands.command(name="gift", aliases=["send", "transfer"])
    async def gift(self, ctx, user: discord.Member, item_type: str, amount: int = 1):
        """Gift items to another user.
        
        Available items: mora, dust, fates
        Example: !gift @username mora 5000
        Example: !gift @username fates 1
        """
        if user.bot:
            await ctx.send("❌ You cannot gift items to bots!")
            return
        
        if user.id == ctx.author.id:
            await ctx.send("❌ You cannot gift items to yourself!")
            return
        
        if amount <= 0:
            await ctx.send("❌ Amount must be positive!")
            return
        
        item_type = item_type.lower()
        valid_items = {
            "mora": ("<:mora:1437958309255577681>", "mora", 1000),
            "dust": ("<:mora:1437480155952975943>", "dust", 10),
            "tidecoin": ("<:mora:1437480155952975943>", "dust", 10),
            "tidecoins": ("<:mora:1437480155952975943>", "dust", 10),
            "fates": ("<:gem1_72x72:1437942609849876680>", "fates", 1),
            "fate": ("<:gem1_72x72:1437942609849876680>", "fates", 1)
        }
        
        if item_type not in valid_items:
            await ctx.send("❌ Invalid item! Available: mora, dust, fates")
            return
        
        emoji, db_column, min_amount = valid_items[item_type]
        
        if amount < min_amount:
            await ctx.send(f"❌ Minimum gift amount is {min_amount:,} {item_type}!")
            return
        
        try:
            await ensure_user_db(ctx.author.id)
            await ensure_user_db(user.id)
            
            sender_data = await get_user_data(ctx.author.id)
            
            # Check if sender has enough
            if sender_data[db_column] < amount:
                await ctx.send(f"❌ You don't have enough {item_type}! You have: {sender_data[db_column]:,}")
                return
            
            # Tax system (5% tax on gifts to prevent exploits)
            tax_rate = 0.05
            tax_amount = int(amount * tax_rate)
            received_amount = amount - tax_amount
            
            async with aiosqlite.connect(DB_PATH) as db:
                # Deduct from sender
                new_sender_amount = sender_data[db_column] - amount
                await db.execute(
                    f"UPDATE users SET {db_column} = ? WHERE user_id = ?",
                    (new_sender_amount, ctx.author.id)
                )
                
                # Add to receiver (after tax)
                receiver_data = await get_user_data(user.id)
                new_receiver_amount = receiver_data[db_column] + received_amount
                await db.execute(
                    f"UPDATE users SET {db_column} = ? WHERE user_id = ?",
                    (new_receiver_amount, user.id)
                )
                
                # Add tax to global bank (only for mora gifts)
                if db_column == "mora":
                    await db.execute(
                        "UPDATE global_bank SET balance = balance + ? WHERE id = 1",
                        (tax_amount,)
                    )
                
                # Log the gift
                await db.execute(
                    """
                    INSERT INTO gift_history (sender_id, receiver_id, item_type, amount)
                    VALUES (?, ?, ?, ?)
                    """,
                    (ctx.author.id, user.id, item_type, amount)
                )
                
                await db.commit()
            
            # Build success embed
            embed = discord.Embed(
                title="🎁 Gift Sent!",
                description=f"{ctx.author.mention} gifted {emoji} **{amount:,} {item_type}** to {user.mention}",
                color=0x2ecc71
            )
            
            embed.add_field(
                name="💸 Transaction Details",
                value=(
                    f"**Sent:** {amount:,}\n"
                    f"**Tax (5%):** {tax_amount:,}\n"
                    f"**Received:** {received_amount:,}"
                ),
                inline=False
            )
            
            embed.set_footer(text="Gifts have a 5% tax to prevent exploitation")
            
            await send_embed(ctx, embed)
            
            # Try to DM the receiver
            try:
                dm_embed = discord.Embed(
                    title="🎁 You received a gift!",
                    description=f"{ctx.author.display_name} sent you {emoji} **{received_amount:,} {item_type}**!",
                    color=0x9b59b6
                )
                await user.send(embed=dm_embed)
            except Exception:
                pass  # User has DMs disabled
        
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Gift")
            logger.error(f"Error in gift command: {e}", exc_info=True)
            await ctx.send("❌ Failed to send gift. Please try again.")
    
    @commands.command(name="gifthistory", aliases=["gifthist", "gh"])
    async def gift_history(self, ctx, limit: int = 10):
        """View your recent gift transactions.
        
        Example: !gifthistory
        Example: !gifthistory 20
        """
        if limit < 1 or limit > 50:
            await ctx.send("❌ Limit must be between 1 and 50!")
            return
        
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Get sent gifts
                async with db.execute(
                    """
                    SELECT receiver_id, item_type, amount, timestamp
                    FROM gift_history
                    WHERE sender_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (ctx.author.id, limit)
                ) as cursor:
                    sent_gifts = await cursor.fetchall()
                
                # Get received gifts
                async with db.execute(
                    """
                    SELECT sender_id, item_type, amount, timestamp
                    FROM gift_history
                    WHERE receiver_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (ctx.author.id, limit)
                ) as cursor:
                    received_gifts = await cursor.fetchall()
            
            if not sent_gifts and not received_gifts:
                await ctx.send("You haven't sent or received any gifts yet!")
                return
            
            embed = discord.Embed(
                title=f"🎁 {ctx.author.display_name}'s Gift History",
                color=0x9b59b6
            )
            
            # Format sent gifts
            if sent_gifts:
                sent_text = []
                for receiver_id, item_type, amount, timestamp in sent_gifts[:5]:
                    try:
                        receiver = await self.bot.fetch_user(receiver_id)
                        receiver_name = receiver.display_name[:15]
                    except Exception:
                        receiver_name = f"User {receiver_id}"
                    
                    sent_text.append(f"→ {receiver_name}: {amount:,} {item_type}")
                
                embed.add_field(
                    name="📤 Sent Gifts",
                    value="\n".join(sent_text) if sent_text else "None",
                    inline=False
                )
            
            # Format received gifts
            if received_gifts:
                received_text = []
                for sender_id, item_type, amount, timestamp in received_gifts[:5]:
                    try:
                        sender = await self.bot.fetch_user(sender_id)
                        sender_name = sender.display_name[:15]
                    except Exception:
                        sender_name = f"User {sender_id}"
                    
                    received_text.append(f"← {sender_name}: {amount:,} {item_type}")
                
                embed.add_field(
                    name="📥 Received Gifts",
                    value="\n".join(received_text) if received_text else "None",
                    inline=False
                )
            
            embed.set_footer(text=f"Showing last {limit} transactions")
            
            await send_embed(ctx, embed)
        
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Gift")
            logger.error(f"Error in gift_history command: {e}", exc_info=True)
            await ctx.send("❌ Failed to fetch gift history. Please try again.")


async def setup(bot):
    await bot.add_cog(Gift(bot))
