import discord
from discord.ext import commands


class Shinanigans(commands.Cog):
    """Small misc commands (lightweight shenanigans)."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="cofi")
    async def cofi(self, ctx):
        """A tiny fun command requested by the user."""
        await ctx.send("Yes cofi is a nigger")
    
    @commands.command(name="nerd")
    async def nerd(self, ctx):
        """Another fun command."""
        await ctx.send("fuck you nigga.")
    


async def setup(bot):
    if bot.get_cog("Shinanigans") is None:
        await bot.add_cog(Shinanigans(bot))
    else:
        print("Shinanigans cog already loaded; skipping add_cog")
