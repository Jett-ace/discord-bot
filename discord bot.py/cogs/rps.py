import random
from collections import defaultdict
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from utils.database import get_user_data, update_user_data, track_game_stat, check_and_award_game_achievements, add_account_exp
from utils.embed import send_embed


class RPS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # RPS cooldown tracking: {user_id: [timestamp1, timestamp2, ...]}
        self.rps_plays = defaultdict(list)

    @commands.command()
    async def rps(self, ctx, user_choice: str):
        """Play rock-paper-scissors. Winners get Mora and 50% chance for a <:random:1437977751520018452> random chest. Limited to 5 plays per 5 minutes (unlimited for premium)."""
        # Check premium status for unlimited plays
        is_premium = False
        try:
            premium_cog = self.bot.get_cog('Premium')
            if premium_cog:
                is_premium = await premium_cog.is_premium(ctx.author.id)
        except:
            pass
        
        # Check cooldown (5 plays per 5 minutes) - skip for premium
        if not is_premium:
            user_id = ctx.author.id
            now = datetime.now()
            cutoff = now - timedelta(minutes=5)

            # Remove plays older than 5 minutes
            self.rps_plays[user_id] = [t for t in self.rps_plays[user_id] if t > cutoff]

            # Check if user has played 5 times in the last 5 minutes
            if len(self.rps_plays[user_id]) >= 5:
                # Find when the oldest play will expire
                oldest = self.rps_plays[user_id][0]
                wait_time = (oldest + timedelta(minutes=5)) - now
                minutes = int(wait_time.total_seconds() // 60)
                seconds = int(wait_time.total_seconds() % 60)
                await ctx.send(
                    f"⏳ You've played 5 times already! Wait {minutes}m {seconds}s before playing again.\n💡 Get Premium for unlimited plays!"
                )
                return

        user_choice = user_choice.lower()
        rpsgame = ["rock", "paper", "scissors"]
        if user_choice not in rpsgame:
            await ctx.send("Use: grps rock | paper | scissors")
            return

        # Record this play (only for non-premium)
        user_id = ctx.author.id
        if not is_premium:
            now = datetime.now()
            self.rps_plays[user_id].append(now)

        # Premium users get slight advantage (15% chance bot picks a losing choice)
        if is_premium and random.random() < 0.15:
            # Bot intentionally picks losing choice
            losing_choices = {
                "rock": "scissors",
                "paper": "rock",
                "scissors": "paper"
            }
            bot_choice = losing_choices[user_choice]
        else:
            # Check for lucky dice (+3% win chance)
            from utils.database import has_active_item, consume_active_item, consume_inventory_item
            has_dice = await has_active_item(ctx.author.id, "lucky_dice")
            
            if has_dice > 0 and random.random() < 0.03:
                # Lucky dice triggered - force a win
                losing_choices = {
                    "rock": "scissors",
                    "paper": "rock",
                    "scissors": "paper"
                }
                bot_choice = losing_choices[user_choice]
                await consume_active_item(ctx.author.id, "lucky_dice")
            else:
                bot_choice = random.choice(rpsgame)

        # Choice icons
        choice_icons = {"rock": "🪨", "paper": "📜", "scissors": "✂️"}

        # determine result
        if user_choice == bot_choice:
            color = 0xFFA500  # Orange for tie
            result = "It's a tie! 🤝"
        elif (
            (user_choice == "rock" and bot_choice == "scissors")
            or (user_choice == "paper" and bot_choice == "rock")
            or (user_choice == "scissors" and bot_choice == "paper")
        ):
            color = 0x9B59B6  # Dark Purple for win

            # Award Mora (500-900)
            mora_reward = random.randint(500, 900)
            
            # Check for Double Down Card (must be activated first)
            from utils.database import has_active_item, consume_active_item, consume_inventory_item
            has_double = await has_active_item(ctx.author.id, "double_down")
            double_bonus = 0
            if has_double > 0:
                double_bonus = mora_reward  # Double the reward
                mora_reward += double_bonus
                await consume_active_item(ctx.author.id, "double_down")
                await consume_inventory_item(ctx.author.id, "double_down")
            
            try:
                data = await get_user_data(ctx.author.id)
                data["mora"] += mora_reward
                await update_user_data(ctx.author.id, mora=data["mora"])
            except Exception:
                mora_reward = 0

            # Track game stat and check achievements
            try:
                await track_game_stat(ctx.author.id, "rps_wins")
                await track_game_stat(ctx.author.id, "rps_plays")
                await check_and_award_game_achievements(ctx.author.id, self.bot, ctx)
            except Exception:
                pass

            # Award XP (50 XP for solo win)
            exp_reward = 50
            leveled_up = False
            new_level = 0
            try:
                leveled_up, new_level, old_level = await add_account_exp(ctx.author.id, exp_reward)
            except Exception:
                exp_reward = 0

            # Build result message
            reward_parts = []
            if mora_reward > 0:
                reward_parts.append(f"{mora_reward:,} <:mora:1437958309255577681>")
                if double_bonus > 0:
                    reward_parts.append("💳 **DOUBLE DOWN!**")
            if exp_reward > 0:
                reward_parts.append(f"+{exp_reward} XP")

            reward_msg = (
                ", ".join(reward_parts) if reward_parts else "nothing this time"
            )
            result = f"<a:Trophy:1438199339586424925> You won!\nYou received: {reward_msg}."
            
            # Add level up message
            if leveled_up:
                result += f"\n\n<a:arrow:1437968863026479258> **Level Up!** You reached level {new_level}!"
        else:
            color = 0xDC143C  # Crimson for loss
            result = "I won!"
            
            # Track play stat (not a win)
            try:
                await track_game_stat(ctx.author.id, "rps_plays")
            except Exception:
                pass

        embed = discord.Embed(title="✊ Rock Paper Scissors", color=color)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(
            name="Your Choice",
            value=f"{choice_icons[user_choice]} **{user_choice.capitalize()}**",
            inline=True,
        )
        embed.add_field(
            name="Bot Choice",
            value=f"{choice_icons[bot_choice]} **{bot_choice.capitalize()}**",
            inline=True,
        )
        embed.add_field(name="Result", value=result, inline=False)

        # Show remaining plays
        plays_left = 5 - len(self.rps_plays[user_id])
        embed.set_footer(text=f"Plays remaining: {plays_left}/5")

        await send_embed(ctx, embed)


async def setup(bot):
    await bot.add_cog(RPS(bot))
