
import discord
from discord.ext import commands
import aiosqlite
import random
from config import DB_PATH
from utils.database import get_user_data, update_user_data, require_enrollment, track_game_stat, check_and_award_game_achievements, add_account_exp
from utils.embed import send_embed


# Roulette wheel layout
RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]


class Roulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.recent_spins = {}  # Track last 5 spins per user

    def get_number_color(self, number):
        """Get the color of a roulette number"""
        if number == 0:
            return "🟢", "Green"
        elif number in RED_NUMBERS:
            return "🔴", "Red"
        else:
            return "⚫", "Black"

    def check_win(self, number, bet_type, bet_value):
        """Check if the bet won and return payout multiplier"""
        # Straight up bet
        if bet_type == "straight":
            if number == bet_value:
                return 30
            return 0

        # Red/Black
        if bet_type == "red":
            if number in RED_NUMBERS:
                return 1
            return 0
        
        if bet_type == "black":
            if number in BLACK_NUMBERS:
                return 1
            return 0

        # Odd/Even (0 loses)
        if bet_type == "odd":
            if number != 0 and number % 2 == 1:
                return 1
            return 0
        
        if bet_type == "even":
            if number != 0 and number % 2 == 0:
                return 1
            return 0

        # Low/High (0 loses)
        if bet_type == "low":
            if 1 <= number <= 18:
                return 1
            return 0
        
        if bet_type == "high":
            if 19 <= number <= 36:
                return 1
            return 0

        # Dozens
        if bet_type == "dozen":
            if bet_value == 1 and 1 <= number <= 12:
                return 2
            elif bet_value == 2 and 13 <= number <= 24:
                return 2
            elif bet_value == 3 and 25 <= number <= 36:
                return 2
            return 0

        # Columns
        if bet_type == "column":
            if bet_value == 1 and number % 3 == 1 and number != 0:
                return 2
            elif bet_value == 2 and number % 3 == 2 and number != 0:
                return 2
            elif bet_value == 3 and number % 3 == 0 and number != 0:
                return 2
            return 0

        return 0

    @commands.command(name="roulette", aliases=["rlt"])
    async def roulette(self, ctx, bet_type: str = None, bet_value: str = None, amount: str = None):
        """Play roulette! Place bets on numbers, colors, or ranges.
        
        Usage:
        groulette straight <number> <amount> - Bet on single number (35:1)
        groulette red/black <amount> - Bet on color (1:1)
        groulette odd/even <amount> - Bet on odd/even (1:1)
        groulette low/high <amount> - Bet on 1-18 or 19-36 (1:1)
        groulette dozen <1/2/3> <amount> - Bet on 1-12, 13-24, or 25-36 (2:1)
        groulette column <1/2/3> <amount> - Bet on column (2:1)
        
        Examples:
        groulette straight 17 5000
        groulette red 10000
        groulette odd all
        groulette dozen 2 5000
        
        Min bet: 1,000 | No max bet
        """
        if not await require_enrollment(ctx):
            return

        if not bet_type:
            embed = discord.Embed(
                title="🎰 Roulette - How to Play",
                description=(
                    "Place bets on where the ball will land!\n\n"
                    "**Bet Types:**\n"
                    "🔴 **Straight** - Single number (35:1)\n"
                    "🔴 **Red/Black** - Color (1:1)\n"
                    "🔴 **Odd/Even** - Number type (1:1)\n"
                    "🔴 **Low/High** - 1-18 or 19-36 (1:1)\n"
                    "🔴 **Dozen** - 1-12, 13-24, or 25-36 (2:1)\n"
                    "🔴 **Column** - Column 1, 2, or 3 (2:1)\n\n"
                    "**Examples:**\n"
                    "`groulette straight 17 5000` - Bet 5K on number 17\n"
                    "`groulette red 10000` - Bet 10K on red\n"
                    "`groulette odd all` - Bet all on odd numbers\n"
                    "`groulette dozen 2 5000` - Bet 5K on dozen 2 (13-24)\n\n"
                    "**Min bet:** 1,000 <:mora:1437958309255577681> | **No max bet!**"
                ),
                color=0x9B59B6
            )
            return await send_embed(ctx, embed)

        bet_type = bet_type.lower()
        
        MIN_BET = 1_000

        # Parse bet based on type
        try:
            # Types that need a value parameter
            if bet_type in ["straight", "dozen", "column"]:
                if not bet_value or not amount:
                    await ctx.send("Usage: `groulette straight <number> <amount>` or `groulette dozen <1/2/3> <amount>`")
                    return
                
                # Validate bet value
                if bet_type == "straight":
                    bet_val = int(bet_value)
                    if bet_val < 0 or bet_val > 36:
                        await ctx.send("Number must be between 0 and 36")
                        return
                elif bet_type in ["dozen", "column"]:
                    bet_val = int(bet_value)
                    if bet_val not in [1, 2, 3]:
                        await ctx.send("Dozen/Column must be 1, 2, or 3")
                        return
                else:
                    bet_val = None
                
                # Parse amount
                bet_amount_str = amount
            else:
                # Types that don't need a value (red, black, odd, even, low, high)
                if bet_type not in ["red", "black", "odd", "even", "low", "high"]:
                    await ctx.send("Invalid bet type. Use: straight, red, black, odd, even, low, high, dozen, column")
                    return
                
                bet_val = None
                bet_amount_str = bet_value  # Second param is the amount
                
                if not bet_amount_str:
                    await ctx.send(f"Usage: `groulette {bet_type} <amount>`")
                    return

            # Get user balance
            data = await get_user_data(ctx.author.id)
            mora = data.get("mora", 0)

            # Parse bet amount
            if bet_amount_str.lower() == "all":
                if mora <= 0:
                    await ctx.send("You don't have any Mora.")
                    return
                bet_amount = mora
                if bet_amount < MIN_BET:
                    await ctx.send(f"Min bet: {MIN_BET:,} <:mora:1437958309255577681>")
                    return
            else:
                bet_amount = int(bet_amount_str.replace(",", ""))
                
                if bet_amount < MIN_BET:
                    await ctx.send(f"Min bet: {MIN_BET:,} <:mora:1437958309255577681>")
                    return
                if bet_amount > mora:
                    await ctx.send("Not enough Mora.")
                    return

        except ValueError:
            await ctx.send("Invalid number or amount.")
            return

        # Spin the wheel
        winning_number = random.randint(0, 36)
        emoji, color = self.get_number_color(winning_number)
        
        # Update recent spins
        if ctx.author.id not in self.recent_spins:
            self.recent_spins[ctx.author.id] = []
        self.recent_spins[ctx.author.id].append(winning_number)
        if len(self.recent_spins[ctx.author.id]) > 5:
            self.recent_spins[ctx.author.id].pop(0)

        # Check if bet won
        multiplier = self.check_win(winning_number, bet_type, bet_val)
        
        if multiplier > 0:
            # Win
            payout = bet_amount * multiplier
            profit = payout  # Net profit
            
            # Check for Double Down Card (must be activated first)
            from utils.database import has_active_item, consume_active_item, consume_inventory_item
            has_double = await has_active_item(ctx.author.id, "double_down")
            double_active = False
            if has_double > 0:
                payout *= 2  # Double the entire payout
                profit *= 2
                await consume_active_item(ctx.author.id, "double_down")
                await consume_inventory_item(ctx.author.id, "double_down")
                double_active = True
            
            new_mora = mora + profit
            await update_user_data(ctx.author.id, mora=new_mora)
            
            # Track stats
            try:
                await track_game_stat(ctx.author.id, "roulette_wins")
                await track_game_stat(ctx.author.id, "roulette_plays")
                await check_and_award_game_achievements(ctx.author.id, self.bot, ctx)
                
                # Award XP
                exp_reward = 70
                leveled_up, new_level, old_level = await add_account_exp(ctx.author.id, exp_reward)
            except Exception:
                exp_reward = 0
                leveled_up = False
            
            embed = discord.Embed(
                title="🎰 Roulette",
                description=f"**{emoji} {winning_number} {color}**",
                color=0x2ECC71
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embed.add_field(name="Result", value="Winner!" + (" 💳 **DOUBLE DOWN!**" if double_active else ""), inline=True)
            embed.add_field(name="Payout", value=f"{payout:,} <:mora:1437958309255577681> ({multiplier}:1{'x2' if double_active else ''})", inline=True)
            embed.add_field(name="Profit", value=f"+{profit:,} <:mora:1437958309255577681>", inline=True)
            
            if exp_reward > 0:
                embed.add_field(name="XP", value=f"+{exp_reward} XP", inline=True)
            
            if leveled_up:
                embed.add_field(name="Level Up!", value=f"You reached level {new_level}!", inline=False)
        else:
            # Loss
            new_mora = mora - bet_amount
            
            # Check for Hot Streak Card (50% refund on loss)
            from utils.database import has_active_item, consume_active_item
            has_hot = await has_active_item(ctx.author.id, "streak")
            hot_refund = 0
            if has_hot > 0:
                hot_refund = int(bet_amount * 0.5)
                await consume_active_item(ctx.author.id, "streak")
                new_mora += hot_refund
            
            await update_user_data(ctx.author.id, mora=new_mora)
            
            # Apply golden card cashback (10%)
            bank_cog = self.bot.get_cog('Bank')
            cashback = 0
            if bank_cog:
                cashback = await bank_cog.apply_golden_cashback(ctx.author.id, bet_amount)
            
            # Track play stat
            try:
                await track_game_stat(ctx.author.id, "roulette_plays")
            except Exception:
                pass
            
            # Add loss to global bank
            try:
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE global_bank SET balance = balance + ? WHERE id = 1",
                        (bet_amount,)
                    )
                    await db.commit()
            except Exception:
                pass
            
            embed = discord.Embed(
                title="🎰 Roulette",
                description=f"**{emoji} {winning_number} {color}**",
                color=0xE74C3C
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embed.add_field(name="Result", value="Loss", inline=True)
            
            loss_value = f"-{bet_amount:,} <:mora:1437958309255577681>"
            if hot_refund > 0:
                loss_value += f"\n+{hot_refund:,} Hot Streak refund"
            if cashback > 0:
                loss_value += f"\n+{cashback:,} cashback <a:gold:1457409675963138205>"
            embed.add_field(name="Lost", value=loss_value, inline=True)

        # Show recent spins
        recent = " ".join([f"{n}" for n in self.recent_spins[ctx.author.id]])
        embed.set_footer(text=f"Recent spins: {recent}")
        
        await send_embed(ctx, embed)


async def setup(bot):
    await bot.add_cog(Roulette(bot))
