import random
import datetime
import discord
from discord.ext import commands
from config import MAX_WISHES, RESET_TIME
from utils.constants import characters, rarity_weights, rarity_emojis
from utils.database import (
    get_user_data, update_user_data, save_pull,
    load_user_wish, save_user_wish, reset_wishes,
    add_account_exp, award_achievement, require_enrollment
)
from utils.embed import send_embed

WISH_ACCOUNT_EXP = 20  # Account EXP per pull

class Gacha(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def can_wish(self, user_id, amount):
        user_data = await load_user_wish(user_id)
        now = datetime.datetime.now()

        # Reset if time passed
        if now >= user_data["reset"]:
            user_data["count"] = 0
            user_data["reset"] = now + RESET_TIME

        remaining = MAX_WISHES - user_data["count"]
        actual = min(amount, remaining)

        # Check if limit reached
        if actual <= 0:
            time_left = user_data["reset"] - now
            mins = time_left.seconds // 60
            secs = time_left.seconds % 60
            return False, mins, secs, 0, user_data

        user_data["count"] += actual
        return True, None, None, actual, user_data

    def pull_character(self, pity):
        # Pull rarity
        rarity = random.choices(list(rarity_weights.keys()), weights=list(rarity_weights.values()))[0]
        
        # Guaranteed 5 star at pity 99+
        if pity >= 99:
            rarity = "5★"
        
        # Get character from pool
        pool = [c for c in characters if c["rarity"] == rarity]
        char = random.choice(pool) if pool else random.choice(characters)
        return char

    async def perform_wish(self, ctx, amount):
        allowed, mins, secs, actual, user_data = await self.can_wish(ctx.author.id, amount)
        
        if not allowed:
            await ctx.send(f"you've reached the limit of wishes you can do. try again in {mins}m {secs}s")
            return

        pull_results = []
        
        # Do pulls
        for _ in range(actual):
            char = self.pull_character(user_data["pity"])
            user_data["pity"] += 1
            
            # Reset pity at 100
            if user_data["pity"] >= 100:
                user_data["pity"] = 0
            
            res = await save_pull(ctx.author.id, str(ctx.author), char)
            pull_results.append((char, res))
            
            # Award first 5 star achievement
            if char.get('rarity') == '5★':
                try:
                    await award_achievement(ctx.author.id, 'first_5star', 'First 5★', 'You pulled your first 5★ character!')
                except:
                    pass
        
        # Save data
        await save_user_wish(ctx.author.id, user_data["count"], user_data["reset"], user_data["pity"])
        
        # Award account EXP for pulling
        try:
            await add_account_exp(ctx.author.id, actual * WISH_ACCOUNT_EXP, source='wish')
        except:
            pass
        
        # Update quest progress
        try:
            quests_cog = self.bot.get_cog('Quests')
            if quests_cog:
                await quests_cog.update_quest_progress(ctx.author.id, 'wish', actual)
        except:
            pass

        # Build embed with numbered list
        results_lines = []
        for idx, (char, res_text) in enumerate(pull_results, 1):
            char_name = char.get('name', 'Unknown')
            rarity = char.get('rarity', '')
            servant_class = char.get('class', 'Unknown')
            
            # Get custom emoji for rarity
            rarity_emoji = rarity_emojis.get(rarity, rarity)
            
            # Check if it was a duplicate (has "relic" in result text)
            if "relic" in res_text.lower():
                detail_text = f"1x {char_name} Relic"
            else:
                detail_text = f"New!"
            
            results_lines.append(f"**{idx}.** {rarity_emoji} **{char_name}**\n{detail_text}")
        
        pity_count = user_data['pity']
        description = "\n\n".join(results_lines)
        description += f"\n\nPulls until guaranteed SSR: **{pity_count}/100**"
        
        if len(description) > 4000:
            description = description[:4000] + "\n...and more!"

        servant_word = "Servant" if actual == 1 else "Servants"
        title = f"{ctx.author.display_name} summoned {actual} {servant_word}"
        embed = discord.Embed(title=title, description=description)
        await send_embed(ctx, embed)

    @commands.command(name="wish", aliases=["w"])
    async def wish(self, ctx, *args):
        if not await require_enrollment(ctx):
            return
        if args:
            await ctx.send("You can only do a single wish using gwish.")
            return
        await self.perform_wish(ctx, 1)

    @commands.command(name="multiwish", aliases=["mw"])
    async def multiwish(self, ctx, amount: int = 10):
        if amount < 1:
            await ctx.send("You must wish at least 1 time.")
            return
        await self.perform_wish(ctx, amount)

    @commands.command(name="intertwined fate", aliases=["ifate"])
    async def usefate(self, ctx):
        data = await get_user_data(ctx.author.id)
        
        if data['fates'] < 1:
            embed = discord.Embed(
                title="No Fates Available <a:X_:1437951830393884788>",
                description="You don't have any Intertwined Fates.",
                color=0xff0000
            )
            await send_embed(ctx, embed)
            return
        
        # Use fate and reset cooldown
        data['fates'] -= 1
        await update_user_data(ctx.author.id, fates=data['fates'])
        await reset_wishes(ctx.author.id)
        await ctx.send("intertwined fate used. your wish cooldown has been reset.")

async def setup(bot):
    await bot.add_cog(Gacha(bot))
