"""Admin commands with permission system"""
import discord
from discord.ext import commands
from datetime import timedelta, datetime
import aiosqlite
from config import DB_PATH, OWNER_ID
from utils.permissions import (
    has_permission, add_permission, remove_permission, get_command_permissions, 
    init_permissions_db, disable_command_in_channel, enable_command_in_channel,
    is_command_disabled, get_disabled_commands_in_channel
)
from utils.embed import send_embed


class Admin(commands.Cog):
    """Admin commands with custom permission system"""
    
    def __init__(self, bot):
        self.bot = bot
        self.sybau_cooldowns = {}  # Track cooldowns for sybau command
    
    async def cog_load(self):
        """Initialize permissions database"""
        await init_permissions_db()
    
    async def check_admin_permission(self, ctx, command_name: str):
        """Check if user has permission for a command"""
        if not await has_permission(ctx.author, command_name):
            await ctx.send(f"❌ You don't have permission to use `{command_name}`! Ask an admin to grant access with `gap @role {command_name}`")
            return False
        return True
    
    @commands.command(name="ap", aliases=["addperm", "addpermission"])
    async def add_perm(self, ctx, target: discord.Role | discord.Member, command_name: str):
        """Add permission for a role or user to use an admin command
        
        Usage: !ap @role <command>
               !ap @user <command>
        Example: !ap @Admin steal
        """
        # Only owner can manage permissions
        if ctx.author.id != OWNER_ID:
            return await ctx.send("❌ Only the bot owner can manage permissions!")
        
        if isinstance(target, discord.Role):
            await add_permission(ctx.guild.id, command_name, role_id=target.id)
            await ctx.send(f"✅ Role {target.mention} can now use `g{command_name}`")
        else:
            await add_permission(ctx.guild.id, command_name, user_id=target.id)
            await ctx.send(f"✅ User {target.mention} can now use `g{command_name}`")
    
    @commands.command(name="rp", aliases=["removeperm", "removepermission"])
    async def remove_perm(self, ctx, target: discord.Role | discord.Member, command_name: str):
        """Remove permission for a role or user to use an admin command
        
        Usage: grp @role <command>
               !rp @user <command>
        """
        # Only owner can manage permissions
        if ctx.author.id != OWNER_ID:
            return await ctx.send("❌ Only the bot owner can manage permissions!")
        
        if isinstance(target, discord.Role):
            await remove_permission(ctx.guild.id, command_name, role_id=target.id)
            await ctx.send(f"\u2705 Removed `g{command_name}` permission from {target.mention}")
        else:
            await remove_permission(ctx.guild.id, command_name, user_id=target.id)
            await ctx.send(f"\u2705 Removed `g{command_name}` permission from {target.mention}")
    
    @commands.command(name="listperms", aliases=["lp", "permissions"])
    async def list_perms(self, ctx, command_name: str = None):
        """List all permissions for a command or all commands
        
        Usage: glistperms [command]
        """
        if ctx.author.id != OWNER_ID:
            return await ctx.send("❌ Only the bot owner can view permissions!")
        
        if command_name:
            perms = await get_command_permissions(ctx.guild.id, command_name)
            if not perms:
                return await ctx.send(f"No permissions set for `g{command_name}`")
            
            embed = discord.Embed(
                title=f"Permissions for !{command_name}",
                color=0x3498DB
            )
            
            roles = []
            users = []
            for role_id, user_id in perms:
                if role_id:
                    role = ctx.guild.get_role(role_id)
                    if role:
                        roles.append(role.mention)
                elif user_id:
                    user = ctx.guild.get_member(user_id)
                    if user:
                        users.append(user.mention)
            
            if roles:
                embed.add_field(name="Authorized Roles", value="\n".join(roles), inline=False)
            if users:
                embed.add_field(name="Authorized Users", value="\n".join(users), inline=False)
            
            await send_embed(ctx, embed)
        else:
            # List all commands with permissions
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute("""
                    SELECT DISTINCT command_name FROM command_permissions WHERE guild_id = ?
                """, (ctx.guild.id,))
                commands_list = await cursor.fetchall()
            
            if not commands_list:
                return await ctx.send("No command permissions set up yet!")
            
            embed = discord.Embed(
                title="All Command Permissions",
                description=f"Use `glistperms <command>` for details",
                color=0x3498DB
            )
            
            cmds = [f"`g{cmd[0]}`" for cmd in commands_list]
            embed.add_field(name="Commands", value=", ".join(cmds), inline=False)
            
            await send_embed(ctx, embed)
    
    @commands.command(name="ban")
    async def ban_member(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Ban a member from the server
        
        Usage: gban @member [reason]
        """
        if not await self.check_admin_permission(ctx, "ban"):
            return
        
        if member.id == OWNER_ID:
            return await ctx.send("❌ Cannot ban the bot owner!")
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != OWNER_ID:
            return await ctx.send("❌ You cannot ban someone with equal or higher role!")
        
        try:
            await member.ban(reason=f"{reason} | Banned by {ctx.author}")
            
            embed = discord.Embed(
                title="🔨 Member Banned",
                description=f"{member.mention} has been banned",
                color=0xE74C3C
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"Banned by {ctx.author}")
            
            await send_embed(ctx, embed)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to ban this member!")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    
    @commands.command(name="kick")
    async def kick_member(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Kick a member from the server
        
        Usage: gkick @member [reason]
        """
        if not await self.check_admin_permission(ctx, "kick"):
            return
        
        if member.id == OWNER_ID:
            return await ctx.send("❌ Cannot kick the bot owner!")
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != OWNER_ID:
            return await ctx.send("❌ You cannot kick someone with equal or higher role!")
        
        try:
            await member.kick(reason=f"{reason} | Kicked by {ctx.author}")
            
            embed = discord.Embed(
                title="👢 Member Kicked",
                description=f"{member.mention} has been kicked",
                color=0xE67E22
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"Kicked by {ctx.author}")
            
            await send_embed(ctx, embed)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to kick this member!")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    
    @commands.command(name="mute", aliases=["timeout"])
    async def mute_member(self, ctx, member: discord.Member, duration: str = "10m", *, reason: str = "No reason provided"):
        """Mute/timeout a member
        
        Usage: !mute @member [duration] [reason]
        Duration: 10s, 5m, 1h, 1d (seconds/minutes/hours/days)
        Example: !mute @user 30m Spamming
        """
        if not await self.check_admin_permission(ctx, "mute"):
            return
        
        if member.id == OWNER_ID:
            return await ctx.send("❌ Cannot mute the bot owner!")
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != OWNER_ID:
            return await ctx.send("❌ You cannot mute someone with equal or higher role!")
        
        # Parse duration
        try:
            time_unit = duration[-1].lower()
            time_value = int(duration[:-1])
            
            if time_unit == 's':
                delta = timedelta(seconds=time_value)
            elif time_unit == 'm':
                delta = timedelta(minutes=time_value)
            elif time_unit == 'h':
                delta = timedelta(hours=time_value)
            elif time_unit == 'd':
                delta = timedelta(days=time_value)
            else:
                return await ctx.send("❌ Invalid duration! Use format like: 10s, 5m, 1h, 1d")
            
            if delta.total_seconds() > 2419200:  # 28 days max
                return await ctx.send("❌ Maximum timeout duration is 28 days!")
            
        except (ValueError, IndexError):
            return await ctx.send("❌ Invalid duration format! Use: 10s, 5m, 1h, 1d")
        
        try:
            await member.timeout(delta, reason=f"{reason} | Muted by {ctx.author}")
            
            embed = discord.Embed(
                title="🔇 Member Muted",
                description=f"{member.mention} has been muted",
                color=0x95A5A6
            )
            embed.add_field(name="Duration", value=duration, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"Muted by {ctx.author}")
            
            await send_embed(ctx, embed)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to timeout this member!")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    
    @commands.command(name="unmute")
    async def unmute_member(self, ctx, member: discord.Member):
        """Unmute/remove timeout from a member
        
        Usage: gunmute @member
        """
        if not await self.check_admin_permission(ctx, "mute"):
            return
        
        try:
            await member.timeout(None, reason=f"Unmuted by {ctx.author}")
            await ctx.send(f"✅ {member.mention} has been unmuted")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to remove timeout from this member!")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    
    @commands.command(name="setsybau")
    async def set_sybau_gif(self, ctx, gif_url: str):
        """Set your custom sybau GIF (Booster only)
        
        Usage: gsetsybau <gif_url>
        """
        # Check if user is a server booster or owner
        if not ctx.author.premium_since and ctx.author.id != OWNER_ID:
            return await ctx.send("❌ This command is only available to server boosters! 💎")
        
        # Validate it's a URL
        if not (gif_url.startswith("http://") or gif_url.startswith("https://")):
            return await ctx.send("❌ Please provide a valid URL starting with http:// or https://")
        
        # Handle Tenor URLs - extract GIF URL if needed
        import aiohttp
        import re
        final_url = gif_url
        
        if "tenor.com" in gif_url and not gif_url.endswith(('.gif', '.png', '.jpg')):
            try:
                # If it's a media.tenor.com link, use directly
                if "media.tenor.com" in gif_url:
                    final_url = gif_url
                else:
                    # Extract from page
                    async with aiohttp.ClientSession() as session:
                        async with session.get(gif_url) as response:
                            html = await response.text()
                            # Try multiple patterns
                            patterns = [
                                r'"url":"(https://media\.tenor\.com/[^"]+\.gif)"',
                                r'<meta property="og:image" content="([^"]+)"',
                                r'<meta name="twitter:image" content="([^"]+)"',
                                r'"contentUrl":"(https://media\.tenor\.com/[^"]+\.gif)"'
                            ]
                            for pattern in patterns:
                                match = re.search(pattern, html)
                                if match:
                                    final_url = match.group(1)
                                    break
            except Exception as e:
                return await ctx.send(f"❌ Failed to extract GIF from Tenor URL! Try using the direct media link.\nError: {str(e)}")
        
        # Save to database
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sybau_gifs (
                    user_id INTEGER PRIMARY KEY,
                    gif_url TEXT NOT NULL
                )
            """)
            await db.execute("""
                INSERT OR REPLACE INTO sybau_gifs (user_id, gif_url)
                VALUES (?, ?)
            """, (ctx.author.id, final_url))
            await db.commit()
        
        embed = discord.Embed(
            title="✅ Sybau GIF Set!",
            description="Your custom GIF has been saved!",
            color=0xF47FFF
        )
        embed.set_image(url=final_url)
        embed.set_footer(text=f"Booster {ctx.author.display_name}")
        
        await send_embed(ctx, embed)
    
    @commands.command(name="sybau")
    async def booster_mute(self, ctx, member: discord.Member):
        """Booster-only: Temporarily mute someone for 20 seconds (fun command)
        
        Usage: gsybau @member
        """
        # Check if user is a server booster or owner
        if not ctx.author.premium_since and ctx.author.id != OWNER_ID:
            return await ctx.send("❌ This command is only available to server boosters! 💎")
        
        # Check cooldown (15 minutes)
        cooldown_key = f"{ctx.guild.id}_{ctx.author.id}"
        if cooldown_key in self.sybau_cooldowns:
            last_used = self.sybau_cooldowns[cooldown_key]
            time_passed = (datetime.now() - last_used).total_seconds()
            cooldown_seconds = 15 * 60  # 15 minutes
            
            if time_passed < cooldown_seconds:
                remaining = int(cooldown_seconds - time_passed)
                minutes = remaining // 60
                seconds = remaining % 60
                return await ctx.send(f"⏰ Cooldown active! Wait **{minutes}m {seconds}s** before using sybau again!")
        
        if member.bot:
            return await ctx.send("❌ You can't mute bots!")
        
        try:
            await member.timeout(timedelta(seconds=20), reason=f"Booster temp mute by {ctx.author}")
            
            # Set cooldown
            cooldown_key = f"{ctx.guild.id}_{ctx.author.id}"
            self.sybau_cooldowns[cooldown_key] = datetime.now()
            
            # Get custom GIF if set
            custom_gif = None
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT gif_url FROM sybau_gifs WHERE user_id = ?",
                    (ctx.author.id,)
                )
                row = await cursor.fetchone()
                if row:
                    custom_gif = row[0]
            
            embed = discord.Embed(
                title="🔇 Sybau!",
                description=f"{member.mention} has been silenced for 20 seconds!",
                color=0xF47FFF
            )
            
            if custom_gif:
                embed.set_image(url=custom_gif)
            
            embed.set_footer(text=f"Used by booster {ctx.author.display_name}")
            
            await send_embed(ctx, embed)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to timeout this member!")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    
    @commands.command(name="warn")
    async def warn_member(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Warn a member (sends them a DM)
        
        Usage: gwarn @member [reason]
        """
        if not await self.check_admin_permission(ctx, "warn"):
            return
        
        if member.id == OWNER_ID:
            return await ctx.send("❌ Cannot warn the bot owner!")
        
        # Store warning in database
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    warned_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                INSERT INTO warnings (guild_id, user_id, moderator_id, reason)
                VALUES (?, ?, ?, ?)
            """, (ctx.guild.id, member.id, ctx.author.id, reason))
            await db.commit()
            
            # Get total warnings
            cursor = await db.execute("""
                SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?
            """, (ctx.guild.id, member.id))
            total_warnings = (await cursor.fetchone())[0]
        
        embed = discord.Embed(
            title="⚠️ Member Warned",
            description=f"{member.mention} has been warned",
            color=0xF39C12
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Total Warnings", value=f"{total_warnings}", inline=False)
        embed.set_footer(text=f"Warned by {ctx.author}")
        
        await send_embed(ctx, embed)
    
    @commands.command(name="warnings", aliases=["warns"])
    async def view_warnings(self, ctx, member: discord.Member = None):
        """View warnings for a member
        
        Usage: gwarnings [@member]
        """
        if not await self.check_admin_permission(ctx, "warn"):
            return
        
        target = member or ctx.author
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT reason, moderator_id, warned_at FROM warnings 
                WHERE guild_id = ? AND user_id = ?
                ORDER BY warned_at DESC
            """, (ctx.guild.id, target.id))
            warnings = await cursor.fetchall()
        
        if not warnings:
            return await ctx.send(f"{target.mention} has no warnings!")
        
        embed = discord.Embed(
            title=f"⚠️ Warnings for {target.display_name}",
            description=f"Total: {len(warnings)} warning(s)",
            color=0xF39C12
        )
        
        for idx, (reason, mod_id, warned_at) in enumerate(warnings[:10], 1):
            moderator = ctx.guild.get_member(mod_id)
            mod_name = moderator.display_name if moderator else f"Unknown#{mod_id}"
            
            embed.add_field(
                name=f"Warning #{idx}",
                value=f"**Reason:** {reason}\n**By:** {mod_name}\n**Date:** {warned_at[:10]}",
                inline=False
            )
        
        if len(warnings) > 10:
            embed.set_footer(text=f"Showing 10 of {len(warnings)} warnings")
        
        await send_embed(ctx, embed)
    
    @commands.command(name="cc", aliases=["createchannel"])
    async def create_channel(self, ctx, name: str, visibility: str = "public"):
        """Create a text channel
        
        Usage: !cc <name> <public/private>
        - public: Everyone can see
        - private: Admin only
        
        Example: !cc announcements public
        """
        if not await self.check_admin_permission(ctx, "cc"):
            return
        
        visibility = visibility.lower()
        if visibility not in ["public", "private"]:
            return await ctx.send("❌ Visibility must be 'public' or 'private'!")
        
        try:
            overwrites = {}
            
            if visibility == "private":
                # Private: Only admins can see
                overwrites[ctx.guild.default_role] = discord.PermissionOverwrite(read_messages=False)
                # Give permission to admin roles (those with manage_guild permission)
                for role in ctx.guild.roles:
                    if role.permissions.manage_guild:
                        overwrites[role] = discord.PermissionOverwrite(read_messages=True)
            
            channel = await ctx.guild.create_text_channel(
                name=name,
                overwrites=overwrites if overwrites else None,
                reason=f"Created by {ctx.author}"
            )
            
            visibility_emoji = "🔒" if visibility == "private" else "🌐"
            await ctx.send(f"✅ {visibility_emoji} Channel created: {channel.mention}")
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to create channels!")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    
    @commands.command(name="nick", aliases=["nickname", "rename"])
    async def change_nickname(self, ctx, member: discord.Member, *, new_name: str):
        """Change a member's nickname
        
        Usage: gnick @member <new name>
        Example: gnick @user NewName
        """
        if not await self.check_admin_permission(ctx, "nick"):
            return
        
        if member.id == ctx.guild.owner_id:
            return await ctx.send("❌ Cannot change the server owner's nickname!")
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != OWNER_ID:
            return await ctx.send("❌ You cannot change the nickname of someone with equal or higher role!")
        
        try:
            old_name = member.display_name
            await member.edit(nick=new_name, reason=f"Changed by {ctx.author}")
            await ctx.send(f"✅ Changed {member.mention}'s nickname from **{old_name}** to **{new_name}**")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to change this member's nickname!")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    
    @commands.command(name="disable", aliases=["disablecmd"])
    @commands.has_permissions(manage_guild=True)
    async def disable_command(self, ctx, command_name: str, channel: discord.TextChannel = None):
        """Disable a command in a specific channel (Requires Manage Server)
        
        Usage: g disable <command> [#channel]
        If no channel specified, uses current channel
        Example: g disable slots #general
        """
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server!")
        
        target_channel = channel or ctx.channel
        
        await disable_command_in_channel(ctx.guild.id, target_channel.id, command_name)
        await ctx.send(f"✅ Command `g{command_name}` has been disabled in {target_channel.mention}")
    
    @commands.command(name="enable", aliases=["enablecmd"])
    @commands.has_permissions(manage_guild=True)
    async def enable_command(self, ctx, command_name: str, channel: discord.TextChannel = None):
        """Re-enable a command in a specific channel (Requires Manage Server)
        
        Usage: g enable <command> [#channel]
        If no channel specified, uses current channel
        Example: g enable slots #general
        """
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server!")
        
        target_channel = channel or ctx.channel
        
        await enable_command_in_channel(ctx.guild.id, target_channel.id, command_name)
        await ctx.send(f"✅ Command `g{command_name}` has been re-enabled in {target_channel.mention}")
    
    @commands.command(name="disabledcmds", aliases=["listdisabled"])
    @commands.has_permissions(manage_guild=True)
    async def list_disabled(self, ctx, channel: discord.TextChannel = None):
        """List all disabled commands in a channel (Requires Manage Server)
        
        Usage: g disabledcmds [#channel]
        """
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server!")
        
        target_channel = channel or ctx.channel
        
        disabled_cmds = await get_disabled_commands_in_channel(ctx.guild.id, target_channel.id)
        
        if not disabled_cmds:
            return await ctx.send(f"No commands are disabled in {target_channel.mention}")
        
        embed = discord.Embed(
            title=f"🚫 Disabled Commands in {target_channel.name}",
            description=", ".join([f"`g{cmd}`" for cmd in disabled_cmds]),
            color=0xE74C3C
        )
        
        await send_embed(ctx, embed)
    
    @commands.command(name="setupmessage", aliases=["sendmessage", "say"])
    @commands.has_permissions(administrator=True)
    async def setup_message(self, ctx, channel: discord.TextChannel, *, message: str):
        """Make the bot send a message to a specific channel
        
        Usage: g setupmessage #channel Your message here
        
        This is useful for sending rules, announcements, or information messages.
        
        Example: g setupmessage #rules Please read and follow all server rules!
        """
        try:
            # Create an embed for the message
            embed = discord.Embed(
                description=message,
                color=0x3498DB,
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"Sent by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            
            await channel.send(embed=embed)
            
            # Confirm to the admin
            await ctx.send(f"<a:Check:1437951818452832318> Message sent to {channel.mention}!")
            
            # Delete the command message to keep the channel clean
            try:
                await ctx.message.delete()
            except:
                pass
                
        except discord.Forbidden:
            await ctx.send(f"<a:X_:1437951830393884788> I don't have permission to send messages in {channel.mention}!")
        except Exception as e:
            await ctx.send(f"<a:X_:1437951830393884788> Failed to send message: {str(e)}")


async def setup(bot):
    await bot.add_cog(Admin(bot))
