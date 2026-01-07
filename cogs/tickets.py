import discord
from discord.ext import commands
import aiosqlite
import asyncio
from datetime import datetime
from config import DB_PATH


class TicketControlView(discord.ui.View):
    """Control buttons for ticket management"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.primary, emoji="✋", custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is staff (has manage channels permission or is admin)
        if not interaction.user.guild_permissions.manage_channels:
            # Check if user has mod/admin role from settings
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT mod_role_id, admin_role_id FROM ticket_settings WHERE guild_id = ?",
                    (interaction.guild.id,)
                ) as cursor:
                    result = await cursor.fetchone()
            
            if result:
                mod_role_id, admin_role_id = result
                has_role = False
                if mod_role_id and interaction.guild.get_role(mod_role_id) in interaction.user.roles:
                    has_role = True
                if admin_role_id and interaction.guild.get_role(admin_role_id) in interaction.user.roles:
                    has_role = True
                
                if not has_role:
                    return await interaction.response.send_message(
                        "<a:X_:1437951830393884788> Only staff members can claim tickets!",
                        ephemeral=True
                    )
            else:
                return await interaction.response.send_message(
                    "<a:X_:1437951830393884788> Only staff members can claim tickets!",
                    ephemeral=True
                )
        
        # Update the embed to show who claimed it
        embed = interaction.message.embeds[0]
        embed.color = 0xF39C12  # Orange color
        embed.add_field(
            name="📌 Claimed By",
            value=f"{interaction.user.mention}",
            inline=False
        )
        
        # Disable the claim button
        button.disabled = True
        button.style = discord.ButtonStyle.secondary
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Send a message in the channel
        await interaction.channel.send(
            f"✅ {interaction.user.mention} has claimed this ticket and will assist you."
        )
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_button")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get ticket creator from database
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id FROM tickets WHERE channel_id = ? AND status = 'open'",
                (interaction.channel.id,)
            ) as cursor:
                ticket_data = await cursor.fetchone()
        
        if not ticket_data:
            return await interaction.response.send_message(
                "<a:X_:1437951830393884788> This ticket is not found or already closed!",
                ephemeral=True
            )
        
        ticket_creator_id = ticket_data[0]
        
        # Check permissions
        is_creator = interaction.user.id == ticket_creator_id
        has_manage = interaction.user.guild_permissions.manage_channels
        
        if not is_creator and not has_manage:
            # Check if user has mod/admin role from settings
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT mod_role_id, admin_role_id FROM ticket_settings WHERE guild_id = ?",
                    (interaction.guild.id,)
                ) as cursor:
                    result = await cursor.fetchone()
            
            if result:
                mod_role_id, admin_role_id = result
                has_role = False
                if mod_role_id and interaction.guild.get_role(mod_role_id) in interaction.user.roles:
                    has_role = True
                if admin_role_id and interaction.guild.get_role(admin_role_id) in interaction.user.roles:
                    has_role = True
                
                if not has_role:
                    return await interaction.response.send_message(
                        "<a:X_:1437951830393884788> Only staff members or the ticket creator can close this ticket!",
                        ephemeral=True
                    )
            else:
                return await interaction.response.send_message(
                    "<a:X_:1437951830393884788> Only staff members or the ticket creator can close this ticket!",
                    ephemeral=True
                )
        
        # Close the ticket
        await interaction.response.defer()
        
        # Update database
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                UPDATE tickets 
                SET status = 'closed', closed_at = ?
                WHERE channel_id = ?
            """, (datetime.utcnow(), interaction.channel.id))
            await db.commit()
        
        # Send closing message
        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=f"**Closed by:** {interaction.user.mention}\n\nThis channel will be deleted in 10 seconds...",
            color=0xE74C3C,
            timestamp=datetime.utcnow()
        )
        
        await interaction.channel.send(embed=embed)
        
        # Wait and delete channel
        await asyncio.sleep(10)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except:
            pass


class TicketButton(discord.ui.View):
    """Persistent button for creating tickets"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.green, emoji="🎫", custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Check if user already has an open ticket
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT channel_id FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'",
                (interaction.guild.id, interaction.user.id)
            ) as cursor:
                existing = await cursor.fetchone()
        
        if existing:
            channel = interaction.guild.get_channel(existing[0])
            if channel:
                return await interaction.followup.send(
                    f"<a:X_:1437951830393884788> You already have an open ticket: {channel.mention}",
                    ephemeral=True
                )
        
        # Get ticket settings
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT mod_role_id, admin_role_id, category_id FROM ticket_settings WHERE guild_id = ?",
                (interaction.guild.id,)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result:
            return await interaction.followup.send(
                "<a:X_:1437951830393884788> Ticket system is not configured!",
                ephemeral=True
            )
        
        mod_role_id, admin_role_id, category_id = result
        
        # Create ticket channel
        category = interaction.guild.get_channel(category_id) if category_id else None
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        # Add mod role permissions
        if mod_role_id:
            mod_role = interaction.guild.get_role(mod_role_id)
            if mod_role:
                overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        # Add admin role permissions
        if admin_role_id:
            admin_role = interaction.guild.get_role(admin_role_id)
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        try:
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket by {interaction.user.name} | ID: {interaction.user.id}"
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                "<a:X_:1437951830393884788> I don't have permission to create channels!",
                ephemeral=True
            )
        
        # Save ticket to database
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO tickets (guild_id, channel_id, user_id, created_at, status)
                VALUES (?, ?, ?, ?, 'open')
            """, (interaction.guild.id, channel.id, interaction.user.id, datetime.utcnow()))
            await db.commit()
        
        # Build mention string
        mentions = []
        if mod_role_id:
            mod_role = interaction.guild.get_role(mod_role_id)
            if mod_role:
                mentions.append(mod_role.mention)
        if admin_role_id:
            admin_role = interaction.guild.get_role(admin_role_id)
            if admin_role:
                mentions.append(admin_role.mention)
        
        # Send initial message in ticket with control buttons
        embed = discord.Embed(
            title="🎫 Support Ticket",
            description=f"{interaction.user.mention} created this ticket.\n\nPlease wait patiently until one of the admins reply.",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"User ID: {interaction.user.id}")
        
        mention_text = " ".join(mentions) if mentions else ""
        await channel.send(
            mention_text,
            embed=embed,
            view=TicketControlView()
        )
        
        # Confirm to user
        await interaction.followup.send(
            f"<a:Check:1437951818452832318> Ticket created! {channel.mention}",
            ephemeral=True
        )


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Ensure table exists and register persistent views"""
        await self.ensure_table()
        # Register persistent views
        self.bot.add_view(TicketButton())
        self.bot.add_view(TicketControlView())
    
    async def ensure_table(self):
        """Create tickets table if it doesn't exist"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_settings (
                    guild_id INTEGER PRIMARY KEY,
                    mod_role_id INTEGER,
                    admin_role_id INTEGER,
                    category_id INTEGER,
                    setup_channel_id INTEGER,
                    message_id INTEGER
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    user_id INTEGER,
                    created_at TIMESTAMP,
                    closed_at TIMESTAMP,
                    status TEXT DEFAULT 'open'
                )
            """)
            await db.commit()
    
    @commands.command(name="setupticket")
    @commands.has_permissions(administrator=True)
    async def setup_ticket(self, ctx, channel: discord.TextChannel, mod_role: discord.Role = None, admin_role: discord.Role = None, category: discord.CategoryChannel = None):
        """Setup the ticket system with an interactive button
        
        Usage: g setupticket #channel [@ModRole] [@AdminRole] [category]
        
        This will send an embed with a button in the specified channel.
        Users can click the button to create support tickets.
        
        Example: g setupticket #tickets @Moderator @Admin Support
        """
        # Create embed for ticket panel
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description=(
                "Need help? Create a ticket and our staff team will assist you!\n\n"
                "**How it works:**\n"
                "<a:arrow:1437968863026479258> Click the button below to open a ticket\n"
                "<a:arrow:1437968863026479258> A private channel will be created for you\n"
                "<a:arrow:1437968863026479258> Explain your issue and wait for staff to respond\n"
                "<a:arrow:1437968863026479258> Staff will help resolve your problem\n\n"
                "**Common reasons to open a ticket:**\n"
                "<a:arrow:1437968863026479258> Report bugs or issues\n"
                "<a:arrow:1437968863026479258> Ask questions about the server\n"
                "<a:arrow:1437968863026479258> Request help with bot features\n"
                "<a:arrow:1437968863026479258> Report rule violations\n"
                "<a:arrow:1437968863026479258> Appeal punishments"
            ),
            color=0x2ECC71
        )
        embed.set_footer(text="Click the button below to open a ticket")
        
        # Send the message with button
        try:
            message = await channel.send(embed=embed, view=TicketButton())
        except discord.Forbidden:
            return await ctx.send(
                f"<a:X_:1437951830393884788> I don't have permission to send messages in {channel.mention}!"
            )
        
        # Save settings to database
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO ticket_settings (guild_id, mod_role_id, admin_role_id, category_id, setup_channel_id, message_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    mod_role_id = excluded.mod_role_id,
                    admin_role_id = excluded.admin_role_id,
                    category_id = excluded.category_id,
                    setup_channel_id = excluded.setup_channel_id,
                    message_id = excluded.message_id
            """, (ctx.guild.id, mod_role.id if mod_role else None, admin_role.id if admin_role else None, category.id if category else None, channel.id, message.id))
            await db.commit()
        
        # Confirm setup
        confirm_embed = discord.Embed(
            title="<a:Check:1437951818452832318> Ticket System Configured!",
            description=f"**Setup Channel:** {channel.mention}",
            color=0x2ECC71
        )
        
        if mod_role:
            confirm_embed.add_field(name="Mod Role", value=mod_role.mention, inline=True)
        if admin_role:
            confirm_embed.add_field(name="Admin Role", value=admin_role.mention, inline=True)
        if category:
            confirm_embed.add_field(name="Category", value=category.name, inline=True)
        
        confirm_embed.add_field(
            name="Next Steps",
            value=f"Users can now click the button in {channel.mention} to create tickets!",
            inline=False
        )
        
        await ctx.send(embed=confirm_embed)
    
    @commands.command(name="close", aliases=["closeticket"])
    async def close_ticket(self, ctx, *, reason: str = None):
        """Close the current ticket
        
        Usage: g close [reason]
        
        Only works in ticket channels. Moderators and the ticket creator can close tickets.
        
        Example: g close Issue resolved
        """
        # Check if this is a ticket channel
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, ticket_id FROM tickets WHERE channel_id = ? AND status = 'open'",
                (ctx.channel.id,)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result:
            return await ctx.send(
                "<a:X_:1437951830393884788> This is not an open ticket channel!"
            )
        
        ticket_user_id, ticket_id = result
        
        # Check if user has permission to close
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT mod_role_id FROM ticket_settings WHERE guild_id = ?",
                (ctx.guild.id,)
            ) as cursor:
                settings = await cursor.fetchone()
        
        is_mod = False
        if settings and settings[0]:
            mod_role = ctx.guild.get_role(settings[0])
            if mod_role and mod_role in ctx.author.roles:
                is_mod = True
        
        if ctx.author.id != ticket_user_id and not is_mod and not ctx.author.guild_permissions.administrator:
            return await ctx.send(
                "<a:X_:1437951830393884788> You don't have permission to close this ticket!"
            )
        
        # Close ticket
        close_reason = reason or "No reason provided"
        
        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=f"**Closed by:** {ctx.author.mention}\n**Reason:** {close_reason}",
            color=0xE74C3C,
            timestamp=datetime.utcnow()
        )
        embed.add_field(
            name="Channel Deletion",
            value="This channel will be deleted in 10 seconds...",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
        # Update database
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                UPDATE tickets 
                SET status = 'closed', closed_at = ?
                WHERE ticket_id = ?
            """, (datetime.utcnow(), ticket_id))
            await db.commit()
        
        # Wait and delete channel
        await asyncio.sleep(10)
        try:
            await ctx.channel.delete(reason=f"Ticket closed by {ctx.author}")
        except:
            pass
    
    @commands.command(name="ticketstats")
    @commands.has_permissions(manage_guild=True)
    async def ticket_stats(self, ctx):
        """View ticket statistics for this server"""
        async with aiosqlite.connect(DB_PATH) as db:
            # Get total tickets
            async with db.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ?",
                (ctx.guild.id,)
            ) as cursor:
                total = (await cursor.fetchone())[0]
            
            # Get open tickets
            async with db.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'open'",
                (ctx.guild.id,)
            ) as cursor:
                open_tickets = (await cursor.fetchone())[0]
            
            # Get closed tickets
            async with db.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'closed'",
                (ctx.guild.id,)
            ) as cursor:
                closed_tickets = (await cursor.fetchone())[0]
        
        embed = discord.Embed(
            title="🎫 Ticket Statistics",
            color=0x3498DB
        )
        embed.add_field(name="Total Tickets", value=f"{total}", inline=True)
        embed.add_field(name="Open", value=f"{open_tickets}", inline=True)
        embed.add_field(name="Closed", value=f"{closed_tickets}", inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command(name="ticketadd")
    @commands.has_permissions(manage_channels=True)
    async def ticket_add(self, ctx, member: discord.Member):
        """Add a user to the current ticket
        
        Usage: g ticketadd @user
        """
        # Check if this is a ticket channel
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id FROM tickets WHERE channel_id = ? AND status = 'open'",
                (ctx.channel.id,)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result:
            return await ctx.send(
                "<a:X_:1437951830393884788> This is not a ticket channel!"
            )
        
        try:
            await ctx.channel.set_permissions(
                member,
                read_messages=True,
                send_messages=True
            )
            await ctx.send(f"<a:Check:1437951818452832318> Added {member.mention} to this ticket!")
        except discord.Forbidden:
            await ctx.send("<a:X_:1437951830393884788> I don't have permission to modify channel permissions!")
    
    @commands.command(name="ticketremove")
    @commands.has_permissions(manage_channels=True)
    async def ticket_remove(self, ctx, member: discord.Member):
        """Remove a user from the current ticket
        
        Usage: g ticketremove @user
        """
        # Check if this is a ticket channel
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id FROM tickets WHERE channel_id = ? AND status = 'open'",
                (ctx.channel.id,)
            ) as cursor:
                result = await cursor.fetchone()
        
        if not result:
            return await ctx.send(
                "<a:X_:1437951830393884788> This is not a ticket channel!"
            )
        
        if member.id == result[0]:
            return await ctx.send(
                "<a:X_:1437951830393884788> You cannot remove the ticket creator!"
            )
        
        try:
            await ctx.channel.set_permissions(member, overwrite=None)
            await ctx.send(f"<a:Check:1437951818452832318> Removed {member.mention} from this ticket!")
        except discord.Forbidden:
            await ctx.send("<a:X_:1437951830393884788> I don't have permission to modify channel permissions!")


async def setup(bot):
    await bot.add_cog(Tickets(bot))
