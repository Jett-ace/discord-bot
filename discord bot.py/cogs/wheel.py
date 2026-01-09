import asyncio
import random
import discord
from discord.ext import commands
from utils.database import get_user_data, update_user_data
from utils.embed import send_embed
from utils.transaction_logger import log_transaction
from utils.logger import setup_logger

logger = setup_logger("Wheel")


class Wheel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.premium_win_streaks = {}  # Track premium user win streaks {user_id: (wins, threshold)}

    @commands.command(name="wheel", aliases=["spin"])
    @commands.cooldown(1, 7, commands.BucketType.user)
    async def wheel_of_fortune(self, ctx, bet: str = None):
        """Spin the wheel of fortune!
        Usage: `gwheel <bet>` or `gwheel all`
        min bet: 1,000 | max bet: 200,000

        prizes:
        💸 Bankrupt - Lose bet
        🎯 0.5x - Half back
        💰 1x - Money back
        💎 2x - Double
        💵 5x - 5x win
        🌟 10x - 10x win
        👑 JACKPOT - 50x win!
        """
        try:
            MIN_BET = 1_000
            
            # Check premium status for higher bet limit
            premium_cog = self.bot.get_cog('Premium')
            is_premium = False
            if premium_cog:
                try:
                    is_premium = await premium_cog.is_premium(ctx.author.id)
                    logger.info(f"User {ctx.author.id} premium status: {is_premium}")
                except Exception as e:
                    logger.error(f"Premium check failed: {e}")
                    is_premium = False
            
            # Premium: 1M, Normal: 200K
            MAX_BET = 1_000_000 if is_premium else 200_000
            logger.info(f"User {ctx.author.id} MAX_BET set to: {MAX_BET:,}")

            # Show help embed if no bet provided
            if bet is None:
                embed = discord.Embed(
                    title="🎡 Wheel of Fortune",
                    description="Spin the wheel and test your luck!",
                    color=0xF1C40F,
                )
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
                embed.add_field(
                    name="📋 How to Play",
                    value=f"Use `gwheel <amount>` or `gwheel all`\n"
                    f"**Min bet:** {MIN_BET:,} <:mora:1437958309255577681>\n"
                    f"**Max bet:** {MAX_BET:,} <:mora:1437958309255577681>",
                    inline=False,
                )
                
                # Show different odds based on premium status
                if is_premium:
                    outcomes_text = (
                        "💸 **Bankrupt** (1%) - Lose bet + 10% penalty\n"
                        "💔 **0.2x** (15%) - Get 20% back\n"
                        "🎯 **0.5x** (21%) - Get half back\n"
                        "💰 **1.2x** (21%) - Small profit\n"
                        "💎 **2x** (28%) - Double your bet\n"
                        "💵 **5x** (9%) - 5x profit\n"
                        "🌟 **10x** (3%) - 10x profit\n"
                        "👑 **JACKPOT 50x** (2%) - Massive win!\n\n"
                        "⭐ **Premium: 10% better odds!**"
                    )
                else:
                    outcomes_text = (
                        "💸 **Bankrupt** (2%) - Lose bet + 10% penalty\n"
                        "💔 **0.2x** (22%) - Get 20% back\n"
                        "🎯 **0.5x** (23%) - Get half back\n"
                        "💰 **1.2x** (19%) - Small profit\n"
                        "💎 **2x** (22%) - Double your bet\n"
                        "💵 **5x** (5%) - 5x profit\n"
                        "🌟 **10x** (3%) - 10x profit\n"
                        "👑 **JACKPOT 50x** (2%) - Massive win!"
                    )
                
                embed.add_field(
                    name="🎯 Possible Outcomes",
                    value=outcomes_text,
                    inline=False,
                )
                embed.add_field(
                    name="💡 Examples",
                    value="`gwheel 5000` - Bet 5,000 Mora\n"
                    "`gwheel all` - Bet your max (up to 200k)",
                    inline=False,
                )
                return await ctx.send(embed=embed)

            data = await get_user_data(ctx.author.id)
            mora = int(data.get("mora", 0))

            if isinstance(bet, str) and bet.lower() == "all":
                bet_amount = int(min(mora, MAX_BET))
                if bet_amount < MIN_BET:
                    await ctx.send(
                        f"<a:X_:1437951830393884788> You need at least {MIN_BET:,} <:mora:1437958309255577681> to play."
                    )
                    return

            else:
                try:
                    bet_amount = int(str(bet).replace(",", ""))
                except Exception:
                    await ctx.send(
                        "<a:X_:1437951830393884788> Please specify a valid integer bet or use `all`."
                    )
                    return

            if bet_amount < MIN_BET:
                await ctx.send(
                    f"<a:X_:1437951830393884788> Minimum bet is {MIN_BET:,} <:mora:1437958309255577681>"
                )
                return
            if bet_amount > MAX_BET:
                await ctx.send(
                    f"<a:X_:1437951830393884788> Maximum bet is {MAX_BET:,} <:mora:1437958309255577681>"
                )
                return
            if mora < bet_amount:
                await ctx.send(
                    "<a:X_:1437951830393884788> You don't have enough Mora for that bet."
                )
                return

            await update_user_data(ctx.author.id, mora=mora - bet_amount)

            # Premium users get better odds (10% advantage)
            if is_premium:
                segments = [
                    ("💸 Bankrupt", 0, 1),      # 1%
                    ("💔 0.2x", 0.2, 15),       # 15%
                    ("🎯 0.5x", 0.5, 21),       # 21%
                    ("💰 1.2x", 1.2, 21),       # 21%
                    ("💎 2x", 2, 28),           # 28%
                    ("💵 5x", 5, 9),            # 9%
                    ("🌟 10x", 10, 3),          # 3%
                    ("👑 JACKPOT", 50, 2),      # 2%
                ]
            else:
                # Normal users: ~47% chance to lose money, ~53% to profit/break even
                segments = [
                    ("💸 Bankrupt", 0, 2),      # 2% - total loss + penalty
                    ("💔 0.2x", 0.2, 22),       # 22% - lose 80%
                    ("🎯 0.5x", 0.5, 23),       # 23% - lose 50%
                    ("💰 1.2x", 1.2, 19),       # 19% - small profit
                    ("💎 2x", 2, 22),           # 22% - double
                    ("💵 5x", 5, 5),            # 5% - 5x
                    ("🌟 10x", 10, 3),          # 3% - 10x
                    ("👑 JACKPOT", 50, 2),      # 2% - jackpot
                ]

            wheel_pool = []
            for segment, multiplier, weight in segments:
                wheel_pool.extend([(segment, multiplier)] * weight)

            # Check for lucky items for better odds
            from utils.database import has_active_item, consume_active_item
            has_dice = await has_active_item(ctx.author.id, "lucky_dice")
            has_horseshoe = await has_active_item(ctx.author.id, "lucky_horseshoe")
            
            # Calculate luck bonus (items don't stack - use best one only)
            luck_bonus = 0
            luck_item_used = None
            if has_horseshoe > 0:
                luck_bonus = 0.05  # +5% from lucky horseshoe (higher priority)
                luck_item_used = "horseshoe"
            elif has_dice > 0:
                luck_bonus = 0.03  # +3% from lucky dice
                luck_item_used = "dice"

            try:
                spin_msg = await ctx.send("**Spinning the wheel...** 🎡")
                await asyncio.sleep(1)

                for i in range(3):
                    random_seg = random.choice(wheel_pool)
                    await spin_msg.edit(
                        content=f"🎡 **Spinning the wheel...** {random_seg[0]}"
                    )
                    await asyncio.sleep(0.5)
            except (discord.errors.HTTPException, RuntimeError):
                # If animation fails due to connection issues, continue with result
                pass

            result_segment, multiplier = random.choice(wheel_pool)
            
            # Premium balancing: Force loss after win streak (4-7 wins randomly)
            if is_premium and multiplier >= 1.0:
                user_id = ctx.author.id
                
                # Initialize or get current streak
                if user_id not in self.premium_win_streaks:
                    self.premium_win_streaks[user_id] = (0, random.randint(4, 7))
                
                wins, threshold = self.premium_win_streaks[user_id]
                wins += 1
                
                # Force a loss if threshold reached
                if wins >= threshold:
                    # Force a bad outcome
                    bad_outcomes = [seg for seg in wheel_pool if seg[1] < 1.0]
                    result_segment, multiplier = random.choice(bad_outcomes)
                    # Reset with new random threshold
                    self.premium_win_streaks[user_id] = (0, random.randint(4, 7))
                    logger.info(f"Premium user {user_id} forced loss after {wins} wins")
                else:
                    # Update streak
                    self.premium_win_streaks[user_id] = (wins, threshold)
            elif is_premium and multiplier < 1.0:
                # Reset streak on natural loss
                self.premium_win_streaks[ctx.author.id] = (0, random.randint(4, 7))
            
            # Apply luck bonus: chance to reroll bad outcomes
            if luck_bonus > 0 and multiplier < 1.0:
                if random.random() < luck_bonus:
                    # Reroll for better outcome
                    result_segment, multiplier = random.choice(wheel_pool)
                    
                    # Consume the luck item that was used
                    if luck_item_used == "horseshoe":
                        await consume_active_item(ctx.author.id, "lucky_horseshoe")
                    elif luck_item_used == "dice":
                        await consume_active_item(ctx.author.id, "lucky_dice")

            if multiplier == 0:
                # Bankrupt: lose bet + 10% of remaining mora
                data = await get_user_data(ctx.author.id)
                current_mora = data.get("mora", 0)
                penalty = int(current_mora * 0.10)
                total_loss = bet_amount + penalty
                
                if penalty > 0:
                    await update_user_data(ctx.author.id, mora=current_mora - penalty)
                
                # Apply golden card cashback (10%)
                bank_cog = self.bot.get_cog('Bank')
                cashback = 0
                if bank_cog:
                    cashback = await bank_cog.apply_golden_cashback(ctx.author.id, total_loss)
                
                payout = 0
                net_profit = -total_loss
                color = 0x95A5A6
                result_text = f"You landed on {result_segment} and lost {total_loss:,} <:mora:1437958309255577681>!"
                if cashback > 0:
                    result_text += f" (+{cashback:,} cashback)"
            elif multiplier < 1:
                # Partial loss
                payout = int(bet_amount * multiplier)
                loss_amount = bet_amount - payout
                
                # Apply golden card cashback (10%)
                bank_cog = self.bot.get_cog('Bank')
                cashback = 0
                if bank_cog:
                    cashback = await bank_cog.apply_golden_cashback(ctx.author.id, loss_amount)
                
                net_profit = payout - bet_amount
                color = 0xE67E22
                result_text = f"You landed on {result_segment} and got back {payout:,} <:mora:1437958309255577681>!"
                if cashback > 0:
                    result_text += f" (+{cashback:,} cashback)"
            elif multiplier == 50:
                payout = int(bet_amount * multiplier)
                
                # Check for Golden Chip bonus (adds +30% to profit)
                from utils.database import has_active_item, consume_active_item, consume_inventory_item
                has_chip = await has_active_item(ctx.author.id, "golden_chip")
                chip_bonus = 0
                if has_chip > 0:
                    profit = payout - bet_amount
                    chip_bonus = int(profit * 0.3)
                    payout += chip_bonus
                    await consume_active_item(ctx.author.id, "golden_chip")
                    await consume_inventory_item(ctx.author.id, "golden_chip")
                
                # Check for Double Down Card (doubles profit including chip bonus!)
                has_double = await has_active_item(ctx.author.id, "double_down")
                double_bonus = 0
                if has_double > 0:
                    profit = payout - bet_amount
                    double_bonus = profit  # Double the profit
                    payout += double_bonus
                    await consume_active_item(ctx.author.id, "double_down")
                    await consume_inventory_item(ctx.author.id, "double_down")
                
                net_profit = payout - bet_amount
                color = 0xF1C40F
                result_text = f"You landed on {result_segment} and won {payout:,} <:mora:1437958309255577681>!"
                if chip_bonus > 0:
                    result_text += f" (+{chip_bonus:,} chip bonus)"
                if double_bonus > 0:
                    result_text += f" (+{double_bonus:,} double down)"
            else:
                payout = int(bet_amount * multiplier)
                
                # Check for Golden Chip bonus (adds +30% to profit)
                from utils.database import has_active_item, consume_active_item, consume_inventory_item
                has_chip = await has_active_item(ctx.author.id, "golden_chip")
                chip_bonus = 0
                if has_chip > 0 and payout > bet_amount:  # Only on profit
                    profit = payout - bet_amount
                    chip_bonus = int(profit * 0.3)
                    payout += chip_bonus
                    await consume_active_item(ctx.author.id, "golden_chip")
                    await consume_inventory_item(ctx.author.id, "golden_chip")
                
                # Check for Double Down Card (doubles profit including chip bonus!)
                has_double = await has_active_item(ctx.author.id, "double_down")
                double_bonus = 0
                if has_double > 0 and payout > bet_amount:  # Only on profit
                    profit = payout - bet_amount
                    double_bonus = profit  # Double the profit
                    payout += double_bonus
                    await consume_active_item(ctx.author.id, "double_down")
                    await consume_inventory_item(ctx.author.id, "double_down")
                
                net_profit = payout - bet_amount
                color = 0x2ECC71
                result_text = f"You landed on {result_segment} and won {payout:,} <:mora:1437958309255577681>!"
                if chip_bonus > 0:
                    result_text += f" (+{chip_bonus:,} chip bonus)"
                if double_bonus > 0:
                    result_text += f" (+{double_bonus:,} double down)"

            if payout > 0:
                data = await get_user_data(ctx.author.id)
                await update_user_data(ctx.author.id, mora=data.get("mora", 0) + payout)
                
                # Log big wins and jackpots
                net_profit = payout - bet_amount
                if multiplier == 50:
                    await log_transaction(ctx.author.id, "jackpot", net_profit, f"Wheel jackpot! Bet: {bet_amount:,}, Won: {payout:,}")
                elif net_profit >= 100000:
                    await log_transaction(ctx.author.id, "huge_win", net_profit, f"Wheel: {multiplier}x multiplier")
                elif net_profit >= 50000:
                    await log_transaction(ctx.author.id, "big_win", net_profit, f"Wheel: {multiplier}x multiplier")

            embed = discord.Embed(
                title="🎡 Wheel of Fortune", description=result_text, color=color
            )
            embed.set_author(
                name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url
            )
            embed.add_field(
                name="Bet",
                value=f"{bet_amount:,}",
                inline=True,
            )
            embed.add_field(
                name="Net Profit",
                value=f"{net_profit:+,}",
                inline=True,
            )

            try:
                if 'spin_msg' in locals():
                    await spin_msg.edit(content=None, embed=embed)
                else:
                    await ctx.send(embed=embed)
            except (discord.errors.HTTPException, RuntimeError):
                # If editing fails, send a new message
                await ctx.send(embed=embed)

        except (discord.errors.HTTPException, RuntimeError) as e:
            # Connection/session errors - silently fail as user may have disconnected
            logger.error(f"Connection error in wheel command: {e}")
            return
        except Exception as e:
            logger.error(f"Error in wheel command: {e}")
            try:
                await ctx.send(
                    "<a:X_:1437951830393884788> There was an error with the Wheel of Fortune. Please try again."
                )
            except:
                # If we can't even send error message, just log and return
                logger.error("Could not send error message due to connection issues")
                return


async def setup(bot):
    await bot.add_cog(Wheel(bot))
