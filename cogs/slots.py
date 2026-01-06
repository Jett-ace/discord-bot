import asyncio
import random
import discord
from discord.ext import commands
import aiosqlite
from config import DB_PATH
from utils.database import get_user_data, update_user_data, require_enrollment, track_game_stat, check_and_award_game_achievements, add_account_exp
from utils.embed import send_embed
from utils.transaction_logger import log_transaction


class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="slots", aliases=["slot", "slotmachine"])
    async def slots(self, ctx, bet: str):
        """Play the slot machine! Match 3 symbols to win big. Usage: `gslots <bet>` or `gslots all`
        Min bet: 1,000 | Max bet: 200,000

        Payouts:
        🍒🍒🍒 - 1.5x
        🍋🍋🍋 - 2x
        🍊🍊🍊 - 3x
        🍇🍇🍇 - 6x
        💎💎💎 - 12x
        7️⃣7️⃣7️⃣ - 30x (JACKPOT!)
        """
        if not await require_enrollment(ctx):
            return
        try:
            # Check if user has unlimited betting
            from utils.database import has_unlimited_game
            unlimited = await has_unlimited_game(ctx.author.id, "slots")
            
            MIN_BET = 1_000
            MAX_BET = 200_000 if not unlimited else float('inf')

            # Parse bet
            data = await get_user_data(ctx.author.id)
            mora = data.get("mora", 0)

            if isinstance(bet, str) and bet.lower() == "all":
                bet_amount = mora  # No cap - bet all your money
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
            
            if mora < bet_amount:
                await ctx.send(
                    "<a:X_:1437951830393884788> You don't have enough Mora for that bet."
                )
                return

            # Slot symbols with weighted probabilities
            symbols = {
                "🍒": 50,  # 50% chance per reel (~12.5% win rate)
                "🍋": 35,  # 35% chance (~4.3% win rate)
                "🍊": 10,  # 10% chance (~0.1% win rate)
                "🍇": 3,   # 3% chance (rare)
                "💎": 1,   # 1% chance (very rare)
                "7️⃣": 1,  # 1% chance (jackpot)
            }

            # Create weighted list
            symbol_pool = []
            for symbol, weight in symbols.items():
                symbol_pool.extend([symbol] * weight)

            # Deduct bet amount first
            await update_user_data(ctx.author.id, mora=mora - bet_amount)

            # Animation: Show spinning slots
            spin_msg = await ctx.send("**Spinning the slots...** <a:slots:1457964817209098425>")
            await asyncio.sleep(1)

            for i in range(4):
                temp1 = random.choice(symbol_pool)
                temp2 = random.choice(symbol_pool)
                temp3 = random.choice(symbol_pool)
                await spin_msg.edit(
                    content=f"<a:slots:1457964817209098425> **[ {temp1} | {temp2} | {temp3} ]**"
                )
                await asyncio.sleep(0.5)

            # Check premium status for better odds
            premium_cog = self.bot.get_cog('Premium')
            is_premium = False
            if premium_cog:
                is_premium = await premium_cog.is_premium(ctx.author.id)

            # Spin the slots (final result)
            reel1 = random.choice(symbol_pool)
            reel2 = random.choice(symbol_pool)
            reel3 = random.choice(symbol_pool)
            
            # Premium users get 10% chance to force a matching reel
            if is_premium and not (reel1 == reel2 == reel3):
                if random.random() < 0.10:
                    # Force a match (pick the most valuable symbol of the three)
                    symbol_values = {"7️⃣": 6, "💎": 5, "🍇": 4, "🍊": 3, "🍋": 2, "🍒": 1}
                    best_symbol = max([reel1, reel2, reel3], key=lambda s: symbol_values.get(s, 0))
                    reel1 = reel2 = reel3 = best_symbol

            # Check for win
            payout_multipliers = {
                "🍒": 1.5,
                "🍋": 2,
                "🍊": 3,
                "🍇": 6,
                "💎": 12,
                "7️⃣": 30,
            }

            if reel1 == reel2 == reel3:
                # Win!
                multiplier = payout_multipliers.get(reel1, 2)
                payout = bet_amount * multiplier
                
                # Get current mora and add payout
                data = await get_user_data(ctx.author.id)
                current_mora = data.get("mora", 0)
                new_mora = current_mora + payout
                await update_user_data(ctx.author.id, mora=new_mora)
                
                # Log big wins
                net_profit = payout - bet_amount
                if net_profit >= 100000:
                    await log_transaction(ctx.author.id, "huge_win", net_profit, f"Slots: {multiplier}x multiplier")
                elif net_profit >= 50000:
                    await log_transaction(ctx.author.id, "big_win", net_profit, f"Slots: {multiplier}x multiplier")

                # Track stats and check achievements
                try:
                    await track_game_stat(ctx.author.id, "slots_wins")
                    await track_game_stat(ctx.author.id, "slots_plays")
                    await check_and_award_game_achievements(ctx.author.id, self.bot, ctx)
                except Exception:
                    pass
                
                # Award XP (70 XP for slots win, more for jackpot)
                exp_reward = 100 if reel1 == "7️⃣" else 70
                leveled_up = False
                new_level = 0
                try:
                    leveled_up, new_level, old_level = await add_account_exp(ctx.author.id, exp_reward)
                except Exception:
                    exp_reward = 0

                embed = discord.Embed(title="🎰 Slot Machine", color=0xFFD700)
                embed.set_author(
                    name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url
                )
                embed.description = f"**[ {reel1} | {reel2} | {reel3} ]**"

                if reel1 == "7️⃣":
                    embed.add_field(
                        name="🎉 JACKPOT!",
                        value=f"Won {payout:,} <:mora:1437958309255577681> ({multiplier}x)",
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name="🎉 Winner!",
                        value=f"Won {payout:,} <:mora:1437958309255577681> ({multiplier}x)",
                        inline=False,
                    )

                embed.add_field(
                    name="Net Profit",
                    value=f"+{payout - bet_amount:,} <:mora:1437958309255577681>",
                    inline=True,
                )
                
                if exp_reward > 0:
                    embed.add_field(
                        name="XP Gained",
                        value=f"+{exp_reward} XP",
                        inline=True,
                    )
                
                if leveled_up:
                    embed.add_field(
                        name="Level Up!",
                        value=f"<a:arrow:1437968863026479258> You reached level {new_level}!",
                        inline=False,
                    )
            else:
                # Loss - mora already deducted at start
                
                # Apply golden card cashback (10%)
                bank_cog = self.bot.get_cog('Bank')
                cashback = 0
                if bank_cog:
                    cashback = await bank_cog.apply_golden_cashback(ctx.author.id, bet_amount)
                
                # Track play stat (not a win)
                try:
                    await track_game_stat(ctx.author.id, "slots_plays")
                except Exception:
                    pass
                
                # Add loss to global bank
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE global_bank SET balance = balance + ? WHERE id = 1",
                        (bet_amount,)
                    )
                    await db.commit()

                embed = discord.Embed(title="🎰 Slot Machine", color=0x95A5A6)
                embed.set_author(
                    name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url
                )
                embed.description = f"**[ {reel1} | {reel2} | {reel3} ]**"
                
                loss_text = f"Lost {bet_amount:,} <:mora:1437958309255577681>"
                if cashback > 0:
                    loss_text += f"\n+{cashback:,} cashback <a:gold:1457409675963138205>"
                embed.add_field(
                    name="No match",
                    value=loss_text,
                    inline=False,
                )

            await spin_msg.edit(content=None, embed=embed)

        except Exception as e:
            print(f"Error in slots command: {e}")
            await ctx.send(
                "<a:X_:1437951830393884788> There was an error with the slot machine. Please try again."
            )


async def setup(bot):
    await bot.add_cog(Slots(bot))
