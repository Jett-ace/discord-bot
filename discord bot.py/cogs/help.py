import discord
from discord.ext import commands
from utils.embed import send_embed

class SimpleHelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        """Display all available minigame commands"""
        
        embed = discord.Embed(
            title="🎮 Bot Commands",
            description="Quick reference for main commands",
            color=0xFF6B9D
        )
        
        embed.add_field(
            name="Games",
            value="`slots` `roulette` `wheel` `blackjack` `coinflip` `mines` `rps` `dice` `scramble` `hilo` `tower` `memory`",
            inline=False
        )
        
        embed.add_field(
            name="Economy",
            value="`gstart` `gbal` `gdaily` `gbank` `gdeposit` `gwithdraw` `gbankcard` `gloan` `grepay` `grob`",
            inline=False
        )
        
        embed.add_field(            name="Fishing 🎣",
            value="`gfish <area>` `gaqua` `gequipfish` `gunequipfish` `gcraftrod` `gupgraderod` `grepairrod` `gupgradefish`",
            inline=False
        )
        
        embed.add_field(            name="Black Market",
            value="`gbm` - View shop (global stock)\n`gpm` - Player market listings\n`gbuy <item>` - Buy from shop\n`gsell <price> <item>` - List item\n`gbl <id>` - Buy from listing\n`gi` - View inventory\n`gitems` - View all items\n`guse <item>` - Use item\n`gopen <type>` - Open chest",
            inline=False
        )
        
        embed.add_field(
            name="Profile",
            value="`gprofile` `gachievements` `gleaderboard`",
            inline=False
        )
        
        embed.add_field(
            name="Moderation",
            value="`gban` `gkick` `gmute` `gunmute` `gwarn` `gwarnings` `gnick` `gcc` `gsteal`",
            inline=False
        )
        
        embed.add_field(
            name="Admin",
            value="`gap` `grp` `glistperms` `gsetprefix` `gdisable` `genable` `gdisabledcmds`",
            inline=False
        )
        
        embed.add_field(
            name="Utility",
            value="`gtranslate` `glanguages` `gping`",
            inline=False
        )
        
        embed.set_footer(text="Prefix: g | Example: gslots, gbm, gi")
        
        await send_embed(ctx, embed)
    
    @commands.command(name="ping")
    async def ping_command(self, ctx):
        """Check the bot's latency"""
        latency = round(self.bot.latency * 1000)  # Convert to milliseconds
        await ctx.send(f"Ping: **{latency}ms**")


async def setup(bot):
    await bot.add_cog(SimpleHelp(bot))

