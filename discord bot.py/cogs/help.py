import discord
from discord.ext import commands
from utils.embed import send_embed

class SimpleHelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        # Group commands by category
        commands_by_cog = {}
        for cmd in sorted(self.bot.commands, key=lambda c: (c.cog_name or "other", c.name)):
            if cmd.hidden:
                continue
            
            # Skip these commands (help system and admin commands)
            if cmd.name in ["reload", "help", "resetdaily"]:
                continue
            
            cog_name = cmd.cog_name or "other"
            lower = cog_name.lower()
            
            # Hide admin commands, help cog, and shinanigans
            if lower in ["moderation", "simplehelp", "shinanigans"]:
                continue
            
            # Group game cogs together
            if "game" in lower or lower in ["blackjack", "tictactoe", "dice"]:
                cog_name = "games"
            
            commands_by_cog.setdefault(cog_name, []).append(cmd.name)

        # Build embed
        embed = discord.Embed(title="Commands", color=0x3498db)
        for cog, cmds in sorted(commands_by_cog.items()):
            cmds_list = ", ".join(f"`{name}`" for name in sorted(set(cmds))) + "."
            if len(cmds_list) > 1020:
                cmds_list = cmds_list[:1017] + "..."
            embed.add_field(name=f"{cog.lower()}:", value=cmds_list, inline=False)

        await send_embed(ctx, embed)

async def setup(bot):
    await bot.add_cog(SimpleHelp(bot))

