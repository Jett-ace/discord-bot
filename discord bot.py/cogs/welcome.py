import discord
from discord.ext import commands
import aiosqlite
from config import DB_PATH


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Ensure table exists when cog loads"""
        await self.ensure_table()
    
    async def ensure_table(self):
        """Create welcome settings table if it doesn't exist"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS welcome_settings (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    message TEXT,
                    gif_url TEXT
                )
            """)
            await db.commit()
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Send welcome message when member joins"""
        if member.bot:
            return
        
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT channel_id, message, gif_url FROM welcome_settings WHERE guild_id = ?",
                (member.guild.id,)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result:
            return
        
        channel_id, message, gif_url = result
        
        if not channel_id or not message:
            return
        
        channel = member.guild.get_channel(channel_id)
        if not channel:
            return
        
        # Replace placeholders in message
        welcome_text = message.replace("{user}", member.mention)
        welcome_text = welcome_text.replace("{username}", member.name)
        welcome_text = welcome_text.replace("{server}", member.guild.name)
        welcome_text = welcome_text.replace("{membercount}", str(member.guild.member_count))
        
        # Create embed
        embed = discord.Embed(
            title=f"Welcome to {member.guild.name}!",
            description=welcome_text,
            color=0x2ECC71
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        if gif_url:
            embed.set_image(url=gif_url)
        
        embed.set_footer(text=f"Member #{member.guild.member_count}")
        
        try:
            await channel.send(content=member.mention, embed=embed)
        except discord.Forbidden:
            pass
    
    @commands.command(name="setupwelcome")
    @commands.has_permissions(administrator=True)
    async def setup_welcome(self, ctx, channel: discord.TextChannel, *, message: str):
        """Setup welcome message for new members
        
        Usage: g setupwelcome #channel Your welcome message here
        
        Available placeholders:
        - {user} - Mentions the user
        - {username} - User's name
        - {server} - Server name
        - {membercount} - Current member count
        
        Example: g setupwelcome #welcome Welcome {user} to {server}! You are member #{membercount}
        """
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO welcome_settings (guild_id, channel_id, message)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message = excluded.message
            """, (ctx.guild.id, channel.id, message))
            await db.commit()
        
        embed = discord.Embed(
            title="<a:Check:1437951818452832318> Welcome System Configured!",
            description=f"**Channel:** {channel.mention}\n**Message:** {message}",
            color=0x2ECC71
        )
        embed.add_field(
            name="Available Placeholders",
            value="`{user}` `{username}` `{server}` `{membercount}`",
            inline=False
        )
        embed.set_footer(text="Use 'g setupgif <url>' to add a GIF to the welcome message")
        await ctx.send(embed=embed)
    
    @commands.command(name="setupgif")
    @commands.has_permissions(administrator=True)
    async def setup_gif(self, ctx, gif_url: str):
        """Setup GIF for welcome message embed
        
        Usage: g setupgif <gif_url>
        
        Example: g setupgif https://media.giphy.com/media/example/giphy.gif
        """
        # Check if welcome is configured
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT channel_id FROM welcome_settings WHERE guild_id = ?",
                (ctx.guild.id,)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result or not result[0]:
            return await ctx.send(
                "<a:X_:1437951830393884788> Please setup welcome message first with `g setupwelcome`!"
            )
        
        # Validate URL
        if not (gif_url.startswith("http://") or gif_url.startswith("https://")):
            return await ctx.send(
                "<a:X_:1437951830393884788> Please provide a valid URL starting with http:// or https://"
            )
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE welcome_settings SET gif_url = ? WHERE guild_id = ?",
                (gif_url, ctx.guild.id)
            )
            await db.commit()
        
        embed = discord.Embed(
            title="<a:Check:1437951818452832318> Welcome GIF Configured!",
            description="GIF will be displayed in welcome messages",
            color=0x2ECC71
        )
        embed.set_image(url=gif_url)
        await ctx.send(embed=embed)
    
    @commands.command(name="removegif")
    @commands.has_permissions(administrator=True)
    async def remove_gif(self, ctx):
        """Remove GIF from welcome message"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE welcome_settings SET gif_url = NULL WHERE guild_id = ?",
                (ctx.guild.id,)
            )
            await db.commit()
        
        await ctx.send("<a:Check:1437951818452832318> Welcome GIF removed!")
    
    @commands.command(name="testwelcome")
    @commands.has_permissions(administrator=True)
    async def test_welcome(self, ctx):
        """Test the welcome message (Admin only)
        
        Usage: g testwelcome
        
        This will simulate a member join and send the welcome message
        """
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT channel_id, message, gif_url FROM welcome_settings WHERE guild_id = ?",
                (ctx.guild.id,)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result:
            return await ctx.send(
                "<a:X_:1437951830393884788> Welcome system is not configured!\n"
                "Use `g setupwelcome #channel <message>` to set it up."
            )
        
        channel_id, message, gif_url = result
        
        if not channel_id or not message:
            return await ctx.send(
                "<a:X_:1437951830393884788> Welcome message or channel not configured!"
            )
        
        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            return await ctx.send(
                "<a:X_:1437951830393884788> Welcome channel not found! Please reconfigure with `g setupwelcome`"
            )
        
        # Use command author as test member
        member = ctx.author
        
        # Replace placeholders in message
        welcome_text = message.replace("{user}", member.mention)
        welcome_text = welcome_text.replace("{username}", member.name)
        welcome_text = welcome_text.replace("{server}", ctx.guild.name)
        welcome_text = welcome_text.replace("{membercount}", str(ctx.guild.member_count))
        
        # Create embed
        embed = discord.Embed(
            title=f"Welcome to {ctx.guild.name}! [TEST]",
            description=welcome_text,
            color=0xF39C12
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        if gif_url:
            embed.set_image(url=gif_url)
        
        embed.set_footer(text=f"Test Message • Member #{ctx.guild.member_count}")
        
        try:
            await channel.send(embed=embed)
            await ctx.send(
                f"<a:Check:1437951818452832318> Test welcome message sent to {channel.mention}!"
            )
        except discord.Forbidden:
            await ctx.send(
                f"<a:X_:1437951830393884788> I don't have permission to send messages in {channel.mention}!"
            )
    
    @commands.command(name="welcomeinfo")
    @commands.has_permissions(administrator=True)
    async def welcome_info(self, ctx):
        """View current welcome message configuration"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT channel_id, message, gif_url FROM welcome_settings WHERE guild_id = ?",
                (ctx.guild.id,)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result:
            return await ctx.send(
                "<a:X_:1437951830393884788> Welcome system is not configured!\n"
                "Use `g setupwelcome #channel <message>` to set it up."
            )
        
        channel_id, message, gif_url = result
        
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        channel_text = channel.mention if channel else "*Not set*"
        message_text = message if message else "*Not set*"
        gif_text = "✅ Configured" if gif_url else "❌ Not set"
        
        embed = discord.Embed(
            title="Welcome System Configuration",
            color=0x3498DB
        )
        embed.add_field(name="Channel", value=channel_text, inline=False)
        embed.add_field(name="Message", value=message_text, inline=False)
        embed.add_field(name="GIF", value=gif_text, inline=False)
        embed.set_footer(text="Use 'g testwelcome' to test the welcome message")
        await ctx.send(embed=embed)
    
    @commands.command(name="disablewelcome")
    @commands.has_permissions(administrator=True)
    async def disable_welcome(self, ctx):
        """Disable welcome messages"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM welcome_settings WHERE guild_id = ?",
                (ctx.guild.id,)
            )
            await db.commit()
        
        await ctx.send("<a:Check:1437951818452832318> Welcome system disabled!")


async def setup(bot):
    await bot.add_cog(Welcome(bot))
