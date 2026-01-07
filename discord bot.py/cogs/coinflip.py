import random
import discord
from discord.ext import commands
import aiosqlite
from config import DB_PATH
from utils.database import get_user_data, update_user_data, require_enrollment, track_game_stat, check_and_award_game_achievements, add_account_exp
from utils.embed import send_embed


class CoinFlip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="flip", aliases=["coin", "cf"])
    async def flip(self, ctx, choice: str, amount: str):
        """Flip a coin and bet Mora. You must pick 'heads' or 'tails'.
        If your pick matches the flip result you win your bet (net +bet), otherwise you lose it.
        Usage: gflip heads 1000 or gflip tails all
        Min bet: 1,000 | Max bet: 200,000
        """
        if not await require_enrollment(ctx):
            return
        try:
            # Check if user has unlimited betting
            from utils.database import has_unlimited_game
            unlimited = await has_unlimited_game(ctx.author.id, "flip")
            
            MIN_BET = 1_000
            # Check premium status for higher bet limit
            premium_cog = self.bot.get_cog('Premium')
            is_premium = False
            if premium_cog:
                is_premium = await premium_cog.is_premium(ctx.author.id)
            
            # Premium: 1M, Normal: 200K, Unlimited: No limit
            MAX_BET = 1_000_000 if is_premium else 200_000
            if unlimited:
                MAX_BET = float('inf')

            choice = choice.lower()
            # accept a few shorthand forms
            if choice in ("h", "head"):
                choice = "heads"
            elif choice in ("t", "tail"):
                choice = "tails"

            if choice not in ("heads", "tails"):
                await ctx.send("Usage: `gflip heads/tails <amount>`\nExample: `gflip heads 5000`")
                return

            # allow 'all' to bet entire balance
            data = await get_user_data(ctx.author.id)
            mora = data.get("mora", 0)

            if isinstance(amount, str) and amount.lower() == "all":
                if mora <= 0:
                    await ctx.send("<a:X_:1437951830393884788> You don't have any Mora.")
                    return
                if unlimited:
                    bet = mora  # No cap for unlimited users
                else:
                    bet = min(mora, 200_000)  # Cap at max bet for normal users
                if bet < MIN_BET:
                    await ctx.send(f"<a:X_:1437951830393884788> Min bet: {MIN_BET:,} <:mora:1437958309255577681>")
                    return
            else:
                # try parsing integer amount (allow commas)
                try:
                    bet = int(str(amount).replace(",", ""))
                except Exception:
                    await ctx.send("Invalid amount. Use a number or `all`.")
                    return

                if bet < MIN_BET:
                    await ctx.send(f"<a:X_:1437951830393884788> Min bet: {MIN_BET:,} <:mora:1437958309255577681>")
                    return
                if not unlimited and bet > 200_000:
                    await ctx.send(f"<a:X_:1437951830393884788> Max bet: {200_000:,} <:mora:1437958309255577681>")
                    return
                if bet > mora:
                    await ctx.send("<a:X_:1437951830393884788> Not enough Mora.")
                    return

            # flip result
            flip_result = random.choice(["heads", "tails"])
            
            # Check premium status for slight advantage
            premium_cog = self.bot.get_cog('Premium')
            is_premium = False
            if premium_cog:
                is_premium = await premium_cog.is_premium(ctx.author.id)
            
            # Premium users get +8% win chance
            if is_premium and flip_result != choice and random.random() < 0.08:
                flip_result = choice  # Premium luck override
            
            # Check for Lucky Dice (adds +5% win chance)
            from utils.database import has_active_item, consume_active_item
            has_lucky = await has_active_item(ctx.author.id, "lucky_dice")
            
            if has_lucky > 0:
                # 5% chance to override loss into win
                if flip_result != choice and random.random() < 0.05:
                    flip_result = choice  # Lucky override!
                    await consume_active_item(ctx.author.id, "lucky_dice")
            
            won = flip_result == choice

            if won:
                # Check for Golden Chip bonus (must be activated first)
                from utils.database import has_active_item, consume_active_item, consume_inventory_item
                has_chip = await has_active_item(ctx.author.id, "golden_chip")
                
                chip_bonus = 0
                if has_chip > 0:
                    chip_bonus = int(bet * 0.3)
                    bet += chip_bonus
                    await consume_active_item(ctx.author.id, "golden_chip")
                    await consume_inventory_item(ctx.author.id, "golden_chip")
                
                # Check for Double Down Card (must be activated first)
                has_double = await has_active_item(ctx.author.id, "double_down")
                double_bonus = 0
                if has_double > 0:
                    double_bonus = bet  # Double the winnings
                    bet += double_bonus
                    await consume_active_item(ctx.author.id, "double_down")
                    await consume_inventory_item(ctx.author.id, "double_down")
                
                # win: user gains amount (net +bet)
                new_mora = mora + bet
                await update_user_data(ctx.author.id, mora=new_mora)
                
                # Track stats and check achievements
                try:
                    await track_game_stat(ctx.author.id, "coinflip_wins")
                    await track_game_stat(ctx.author.id, "coinflip_plays")
                    await check_and_award_game_achievements(ctx.author.id, self.bot, ctx)
                except Exception:
                    pass
                
                # Award XP (60 XP for coinflip win)
                exp_reward = 60
                leveled_up = False
                new_level = 0
                try:
                    from utils.database import has_xp_booster
                    if await has_xp_booster(ctx.author.id):
                        exp_reward = int(exp_reward * 1.5)
                    leveled_up, new_level, old_level = await add_account_exp(ctx.author.id, exp_reward)
                except Exception:
                    exp_reward = 0
                
                result_msg = f"<a:Check:1437951818452832318> **{flip_result}** - Won {bet:,} <:mora:1437958309255577681>!"
                if chip_bonus > 0:
                    result_msg += f" <:goldenchip:1457964285207646264> +{chip_bonus:,} bonus!"
                if double_bonus > 0:
                    result_msg += f" 💳 **DOUBLE DOWN!** +{double_bonus:,} bonus!"
                if has_lucky > 0:
                    result_msg += f" <:dice:1457965149137670186> Lucky! ({has_lucky-1} uses left)"
                if exp_reward > 0:
                    result_msg += f" (+{exp_reward} XP)"
                if leveled_up:
                    result_msg += f"\n<a:arrow:1437968863026479258> **Level Up!** You reached level {new_level}!"
                
                await ctx.send(result_msg)
            else:
                # Check for Hot Streak Card (50% refund on loss)
                has_hot = await has_active_item(ctx.author.id, "streak")
                refund = 0
                
                if has_hot > 0:
                    refund = int(bet * 0.5)
                    await consume_active_item(ctx.author.id, "streak")
                    new_mora = mora - bet + refund
                else:
                    new_mora = mora - bet
                    
                await update_user_data(ctx.author.id, mora=new_mora)
                
                # Apply golden card cashback (10%)
                bank_cog = self.bot.get_cog('Bank')
                cashback = 0
                if bank_cog:
                    cashback = await bank_cog.apply_golden_cashback(ctx.author.id, bet)
                
                # Track play stat (not a win)
                try:
                    await track_game_stat(ctx.author.id, "coinflip_plays")
                except Exception:
                    pass
                
                # Add loss to global bank (only non-refunded amount)
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE global_bank SET balance = balance + ? WHERE id = 1",
                        (bet - refund,)
                    )
                    await db.commit()
                
                loss_msg = f"💥 **{flip_result}** - Lost {bet:,} <:mora:1437958309255577681>"
                if refund > 0:
                    loss_msg += f" <:streak:1457966635838214247> Hot Streak refunded {refund:,}! ({has_hot-1} uses left)"
                if cashback > 0:
                    loss_msg += f" +{cashback:,} cashback <a:gold:1457409675963138205>"
                await ctx.send(loss_msg)
        except Exception as e:
            print(f"Error in flip command: {e}")
            await ctx.send("<a:X_:1437951830393884788> Error processing flip.")


async def setup(bot):
    await bot.add_cog(CoinFlip(bot))
