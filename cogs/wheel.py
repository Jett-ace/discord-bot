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

    @commands.command(name="wheel", aliases=["spin"])
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
            MAX_BET = 200_000

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
                embed.add_field(
                    name="🎯 Possible Outcomes",
                    value="💸 **Bankrupt** (1%) - Lose bet + 10% penalty\n"
                    "💔 **0.2x** (20%) - Get 20% back\n"
                    "🎯 **0.5x** (24%) - Get half back\n"
                    "💰 **1.2x** (20%) - Small profit\n"
                    "💎 **2x** (24%) - Double your bet\n"
                    "💵 **5x** (6%) - 5x profit\n"
                    "🌟 **10x** (4%) - 10x profit\n"
                    "👑 **JACKPOT 50x** (1%) - Massive win!",
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
            mora = data.get("mora", 0)

            if isinstance(bet, str) and bet.lower() == "all":
                bet_amount = min(mora, MAX_BET)
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

            # Check premium status for better odds
            premium_cog = self.bot.get_cog('Premium')
            is_premium = False
            if premium_cog:
                is_premium = await premium_cog.is_premium(ctx.author.id)

            # Premium users get improved odds (lower weight on bad outcomes, higher on good)
            if is_premium:
                segments = [
                    ("💸 Bankrupt", 0, 1),      # 1% (same)
                    ("💔 0.2x", 0.2, 15),       # 15% (reduced from 20%)
                    ("🎯 0.5x", 0.5, 20),       # 20% (reduced from 24%)
                    ("💰 1.2x", 1.2, 22),       # 22% (increased from 20%)
                    ("💎 2x", 2, 26),           # 26% (increased from 24%)
                    ("💵 5x", 5, 9),            # 9% (increased from 6%)
                    ("🌟 10x", 10, 5),          # 5% (increased from 4%)
                    ("👑 JACKPOT", 50, 2),      # 2% (doubled from 1%)
                ]
            else:
                segments = [
                    ("💸 Bankrupt", 0, 1),
                    ("💔 0.2x", 0.2, 20),
                    ("🎯 0.5x", 0.5, 24),
                    ("💰 1.2x", 1.2, 20),
                    ("💎 2x", 2, 24),
                    ("💵 5x", 5, 6),
                    ("🌟 10x", 10, 4),
                    ("👑 JACKPOT", 50, 1),
                ]

            wheel_pool = []
            for segment, multiplier, weight in segments:
                wheel_pool.extend([(segment, multiplier)] * weight)

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
                color = 0x95A5A6
                result_text = f"💥 You landed on {result_segment}!\nLost your bet of {bet_amount:,} <:mora:1437958309255577681> + 10% penalty ({penalty:,} <:mora:1437958309255577681>)\nTotal loss: {total_loss:,} <:mora:1437958309255577681>"
                if cashback > 0:
                    result_text += f"\n+{cashback:,} cashback <a:gold:1457409675963138205>"
            elif multiplier < 1:
                # Partial loss
                payout = int(bet_amount * multiplier)
                loss_amount = bet_amount - payout
                
                # Apply golden card cashback (10%)
                bank_cog = self.bot.get_cog('Bank')
                cashback = 0
                if bank_cog:
                    cashback = await bank_cog.apply_golden_cashback(ctx.author.id, loss_amount)
                
                color = 0xE67E22
                result_text = f"You landed on {result_segment} and got back {payout:,} <:mora:1437958309255577681>."
                if cashback > 0:
                    result_text += f"\n+{cashback:,} cashback <a:gold:1457409675963138205>"
            elif multiplier == 50:
                payout = int(bet_amount * multiplier)
                color = 0xF1C40F
                result_text = f"<a:Trophy:1438199339586424925> **{result_segment}!!!**\nYou won {payout:,} <:mora:1437958309255577681>!\nNet profit: +{payout - bet_amount:,} <:mora:1437958309255577681>"
            else:
                payout = int(bet_amount * multiplier)
                color = 0x2ECC71
                result_text = f"You landed on {result_segment} and won {payout:,} <:mora:1437958309255577681>!\nNet profit: +{payout - bet_amount:,} <:mora:1437958309255577681>"

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
                value=f"{bet_amount:,} <:mora:1437958309255577681>",
                inline=True,
            )
            embed.add_field(name="Multiplier", value=f"{multiplier}x", inline=True)

            embed.set_footer(
                text="Outcomes: Bankrupt (1%) | 0.2x (20%) | 0.5x (24%) | 1.2x (20%) | 2x (24%) | 5x (6%) | 10x (4%) | JACKPOT (1%)"
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
