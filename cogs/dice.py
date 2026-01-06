import discord
import random
from discord.ext import commands
from utils.embed import send_embed

class dice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="roll", aliases=["dice"])
    async def roll_dice(self, ctx, sides: int = 6):
        """Roll a dice with specified sides (default 6).
        Usage: groll or groll 20"""

        if sides < 2:
            await ctx.send("Dice must have at least 2 sides!")
            return
        if sides > 100:
            await ctx.send("Dice cannot have more than 100 sides!")
            return
        result = random.randint(1, sides) 

        embed = discord.Embed(
            title=f"🎲 Dice Roll (d{sides})",
            description=f"{ctx.author.mention} rolled a **{result}**!",
            color=0x3498db
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        await send_embed(ctx, embed)

async def setup(bot):
    await bot.add_cog(dice(bot))