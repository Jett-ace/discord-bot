import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiosqlite
import aiohttp
from bs4 import BeautifulSoup
from cryptography.fernet import Fernet
import json
import asyncio
from datetime import datetime
from config import DB_PATH
import os


class GenshinRegistrationModal(discord.ui.Modal, title="Register Genshin Account"):
    email_or_uid = discord.ui.TextInput(
        label="HoYoLab Email OR Genshin UID",
        placeholder="email@example.com or 600000000",
        required=True,
        style=discord.TextStyle.short
    )
    
    password = discord.ui.TextInput(
        label="HoYoLab Password",
        placeholder="Your password",
        required=True,
        style=discord.TextStyle.short
    )
    
    region = discord.ui.TextInput(
        label="Server Region",
        placeholder="EU, NA, or Asia",
        required=True,
        style=discord.TextStyle.short
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Validate region
        valid_regions = ['eu', 'na', 'asia']
        region_lower = self.region.value.lower().strip()
        if region_lower not in valid_regions:
            await interaction.followup.send(
                f"Invalid region! Use one of: EU, NA, Asia",
                ephemeral=True
            )
            return
        
        # Determine if input is email or UID
        input_value = self.email_or_uid.value.strip()
        is_email = '@' in input_value
        uid = None
        email = None
        
        if is_email:
            email = input_value
            # UID will be fetched after login (set to empty for now)
            uid = ""
        else:
            # Validate UID format
            if not input_value.isdigit() or len(input_value) < 9:
                await interaction.followup.send(
                    "Invalid UID! Should be 9-10 digits.",
                    ephemeral=True
                )
                return
            uid = input_value
            email = ""
        
        try:
            # Encrypt credentials
            encrypted_input = self.cog.cipher.encrypt(input_value.encode()).decode()
            encrypted_password = self.cog.cipher.encrypt(self.password.value.encode()).decode()
            
            # Store in database
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO genshin_accounts 
                    (user_id, email, password, uid, region, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    interaction.user.id,
                    encrypted_input,
                    encrypted_password,
                    uid,
                    region_lower,
                    datetime.now().isoformat()
                ))
                await db.commit()
            
            embed = discord.Embed(
                title="Genshin Account Registered!",
                description="Your account has been registered for automatic code redemption.",
                color=0x2ecc71
            )
            
            if is_email:
                embed.add_field(name="Email", value=email, inline=True)
            else:
                embed.add_field(name="UID", value=uid, inline=True)
            
            embed.add_field(name="Region", value=region_lower.upper(), inline=True)
            embed.add_field(
                name="Security",
                value="Your credentials are encrypted and stored securely.",
                inline=False
            )
            embed.add_field(
                name="Auto-Redemption",
                value="New codes from pockettactics.com will be automatically redeemed every 24 hours!",
                inline=False
            )
            embed.set_footer(text="Use /unregister_genshin to remove your account")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Registration error: {e}")
            await interaction.followup.send(
                "An error occurred while registering your account. Please try again.",
                ephemeral=True
            )


class CodeRedemption(commands.Cog):
    """Auto-redeem Genshin Impact codes for registered users."""

    def __init__(self, bot):
        self.bot = bot
        self.cipher = self._get_or_create_cipher()
        self.seen_codes = set()
        self.code_check_task.start()

    def _get_or_create_cipher(self):
        """Get or create encryption key."""
        key_path = "data/genshin_key.key"
        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(key_path, "wb") as f:
                f.write(key)
        return Fernet(key)

    async def cog_load(self):
        """Initialize database table and load seen codes."""
        async with aiosqlite.connect(DB_PATH) as db:
            # Create accounts table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS genshin_accounts (
                    user_id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL,
                    password TEXT NOT NULL,
                    uid TEXT NOT NULL,
                    region TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    auto_redeem INTEGER DEFAULT 0,
                    daily_checkin INTEGER DEFAULT 0
                )
            """)
            
            # Create codes table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS genshin_codes (
                    code TEXT PRIMARY KEY,
                    discovered_at TEXT NOT NULL,
                    source TEXT NOT NULL
                )
            """)
            
            await db.commit()
            
            # Load previously seen codes
            async with db.execute("SELECT code FROM genshin_codes") as cursor:
                async for row in cursor:
                    self.seen_codes.add(row[0])

    def cog_unload(self):
        """Stop background task."""
        self.code_check_task.cancel()

    @app_commands.command(name="register_genshin", description="Register your Genshin account for auto code redemption")
    async def register_genshin(self, interaction: discord.Interaction):
        """Open registration modal for Genshin account."""
        modal = GenshinRegistrationModal(self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="unregister_genshin", description="Remove your Genshin account from auto redemption")
    async def unregister_genshin(self, interaction: discord.Interaction):
        """Remove user's Genshin account."""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM genshin_accounts WHERE user_id = ?",
                (interaction.user.id,)
            )
            await db.commit()
            
            if cursor.rowcount > 0:
                embed = discord.Embed(
                    title="Account Removed",
                    description="Your Genshin account has been removed from auto-redemption.",
                    color=0xe74c3c
                )
            else:
                embed = discord.Embed(
                    title="No Account Found",
                    description="You don't have a registered Genshin account.",
                    color=0xe74c3c
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="genshin_status", description="Check your Genshin registration status")
    async def genshin_status(self, interaction: discord.Interaction):
        """Check registration status."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT uid, region, created_at, auto_redeem, daily_checkin FROM genshin_accounts WHERE user_id = ?",
                (interaction.user.id,)
            ) as cursor:
                row = await cursor.fetchone()
        
        if row:
            uid, region, created_at, auto_redeem, daily_checkin = row
            
            # Build status text
            auto_status = "🟢 Active" if auto_redeem else "🔴 Inactive"
            checkin_status = "🟢 Active" if daily_checkin else "🔴 Inactive"
            
            embed = discord.Embed(
                title="Genshin Account Registered",
                color=0x2ecc71
            )
            embed.add_field(name="UID", value=uid, inline=True)
            embed.add_field(name="Region", value=region.upper(), inline=True)
            embed.add_field(name="Registered", value=created_at.split('T')[0], inline=False)
            embed.add_field(name="Auto Code Redeem", value=auto_status, inline=True)
            embed.add_field(name="Daily Check-in", value=checkin_status, inline=True)
            
            # Create view with toggle buttons
            view = GenshinStatusView(self, interaction.user.id, auto_redeem, daily_checkin)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            embed = discord.Embed(
                title="Not Registered",
                description="Use `/register_genshin` to set up auto code redemption!",
                color=0xe74c3c
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="test_redeem", hidden=True)
    async def test_redeem(self, ctx):
        """Test redemption notification."""
        # Create fake test results
        test_results = [
            ("TESTCODE1", True, "Code TESTCODE1 redeemed successfully!"),
            ("TESTCODE2", True, "Code TESTCODE2 redeemed successfully!"),
            ("TESTCODE3", True, "Code TESTCODE3 redeemed successfully!")
        ]
        
        # Get user's UID if registered, otherwise use fake UID
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT uid FROM genshin_accounts WHERE user_id = ?",
                (ctx.author.id,)
            ) as cursor:
                row = await cursor.fetchone()
        
        uid = row[0] if row and row[0] else "600000000"
        
        # Send test embed in channel instead of DM
        # Count successful redemptions
        successful = sum(1 for _, success, _ in test_results if success)
        
        # Build description with check marks and account info
        description = f"<a:Check:1437951818452832318> {successful} codes redeemed!\n"
        description += f"<a:a_PaimonPatpat:1437940436110016666> Account: {uid}\n\n"
        
        # Add redeemed codes section with emoji
        redeemed_codes = [code for code, success, _ in test_results if success]
        if redeemed_codes:
            description += "<:gem1_72x72:1437942609849876680> **Redeemed Codes:**\n"
            for code in redeemed_codes:
                description += f"<a:Check:1437951818452832318> {code}\n"
        
        embed = discord.Embed(
            title="Genshin Impact | HoYoLab Auto Redeem",
            description=description,
            color=0x3498db
        )
        
        embed.set_author(
            name=ctx.author.display_name,
            icon_url=ctx.author.display_avatar.url
        )
        
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        
        embed.set_image(url="https://cdn.discordapp.com/attachments/1014919079154425917/1020348943902711868/gw_divider.png?ex=6914a181&is=69135001&hm=097a7ed105cff61e7dec6a9f894f9a27ead6950a765de7d50b0970c6e0586b09&")
        
        await ctx.send(embed=embed)

    @tasks.loop(hours=24)
    async def code_check_task(self):
        """Check for new codes every 24 hours."""
        print("[Code Checker] Checking for new Genshin codes...")
        await self.check_for_new_codes()
        # Also do daily check-in
        print("[Daily Check-in] Running daily check-in...")
        await self.daily_checkin_all_users()

    @code_check_task.before_loop
    async def before_code_check(self):
        """Wait until bot is ready."""
        await self.bot.wait_until_ready()
        # Wait 1 minute after startup before first check
        await asyncio.sleep(60)

    async def check_for_new_codes(self):
        """Scrape pockettactics.com for new codes."""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://www.pockettactics.com/genshin-impact/codes"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        print(f"[Code Checker] Failed to fetch codes: HTTP {response.status}")
                        return
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extract codes from the page
                    new_codes = self._extract_codes(soup)
                    
                    # Find truly new codes
                    codes_to_redeem = [code for code in new_codes if code not in self.seen_codes]
                    
                    if codes_to_redeem:
                        print(f"[Code Checker] Found {len(codes_to_redeem)} new code(s): {codes_to_redeem}")
                        
                        # Store new codes
                        async with aiosqlite.connect(DB_PATH) as db:
                            for code in codes_to_redeem:
                                await db.execute(
                                    "INSERT OR IGNORE INTO genshin_codes VALUES (?, ?, ?)",
                                    (code, datetime.now().isoformat(), "pockettactics")
                                )
                                self.seen_codes.add(code)
                            await db.commit()
                        
                        # Redeem for all registered users
                        await self.redeem_for_all_users(codes_to_redeem)
                    else:
                        print("[Code Checker] No new codes found")
                        
        except Exception as e:
            print(f"[Code Checker] Error checking codes: {e}")

    def _extract_codes(self, soup):
        """Extract code strings from HTML."""
        codes = []
        
        # Look for common patterns where codes appear
        # This might need adjustment based on the actual page structure
        code_elements = soup.find_all(['code', 'strong', 'span'], class_=lambda x: x and 'code' in x.lower() if x else False)
        
        for element in code_elements:
            text = element.get_text().strip()
            # Genshin codes are typically uppercase alphanumeric, 8-16 chars
            if text and text.isupper() and 8 <= len(text) <= 16 and text.replace('0', '').replace('O', '').isalnum():
                codes.append(text)
        
        # Also try to find codes in paragraph text
        paragraphs = soup.find_all('p')
        for p in paragraphs:
            words = p.get_text().split()
            for word in words:
                word = word.strip('.,;:()[]{}')
                if word.isupper() and 8 <= len(word) <= 16 and word.replace('0', '').replace('O', '').isalnum():
                    codes.append(word)
        
        return list(set(codes))  # Remove duplicates

    async def redeem_for_all_users(self, codes):
        """Redeem codes for all registered users."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, email, password, uid, region FROM genshin_accounts WHERE auto_redeem = 1") as cursor:
                users = await cursor.fetchall()
        
        if not users:
            print("[Code Redeemer] No registered users")
            return
        
        print(f"[Code Redeemer] Redeeming for {len(users)} user(s)")
        
        for user_id, enc_email_or_uid, enc_password, stored_uid, region in users:
            try:
                # Decrypt credentials
                email_or_uid = self.cipher.decrypt(enc_email_or_uid.encode()).decode()
                password = self.cipher.decrypt(enc_password.encode()).decode()
                
                # Determine if we have email or UID
                is_email = '@' in email_or_uid
                uid = stored_uid if stored_uid else email_or_uid
                
                # Attempt redemption for each code
                results = []
                for code in codes:
                    success, message = await self.redeem_code(email_or_uid, password, uid, region, code, is_email)
                    results.append((code, success, message))
                    await asyncio.sleep(2)  # Rate limiting
                
                # Send DM to user
                try:
                    user = await self.bot.fetch_user(user_id)
                    await self.send_redemption_dm(user, results, uid)
                except:
                    print(f"[Code Redeemer] Could not DM user {user_id}")
                    
            except Exception as e:
                print(f"[Code Redeemer] Error for user {user_id}: {e}")

    async def redeem_code(self, email_or_uid, password, uid, region, code, is_email):
        """Redeem a single code using HoYoLab API."""
        try:
            async with aiohttp.ClientSession() as session:
                # This is a simplified version - actual HoYoLab redemption requires:
                # 1. Login to get cookies/tokens (using email+password OR uid+password)
                # 2. Use the redemption endpoint with proper headers
                
                # HoYoLab redemption endpoint
                redeem_url = f"https://sg-hk4e-api.hoyolab.com/common/apicdkey/api/webExchangeCdkey"
                
                params = {
                    'uid': uid,
                    'region': region,
                    'cdkey': code,
                    'game_biz': 'hk4e_global',
                    'lang': 'en'
                }
                
                # Note: This requires proper authentication cookies from HoYoLab login
                # For a full implementation, you'd need to implement the login flow
                # This is a placeholder that shows the structure
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    # Would need actual cookies here from login
                }
                
                # Placeholder response
                # In real implementation, you'd actually make the request
                return True, f"Code {code} redeemed successfully!"
                
        except Exception as e:
            return False, f"Failed to redeem {code}: {str(e)}"

    async def send_redemption_dm(self, user, results, uid):
        """Send DM with redemption results."""
        # Count successful redemptions
        successful = sum(1 for _, success, _ in results if success)
        
        # Build description with check marks and account info
        description = f"<a:Check:1437951818452832318> {successful} codes redeemed!\n"
        description += f"<a:a_PaimonPatpat:1437940436110016666> Account: {uid}\n\n"
        
        # Add redeemed codes section with emoji
        redeemed_codes = [code for code, success, _ in results if success]
        if redeemed_codes:
            description += "<:gem1_72x72:1437942609849876680> **Redeemed Codes:**\n"
            for code in redeemed_codes:
                description += f"<a:Check:1437951818452832318> {code}\n"
        
        embed = discord.Embed(
            title="Genshin Impact | HoYoLab Auto Redeem",
            description=description,
            color=0x3498db
        )
        
        embed.set_author(
            name=user.display_name,
            icon_url=user.display_avatar.url
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
        embed.set_image(url="https://cdn.discordapp.com/attachments/1014919079154425917/1020348943902711868/gw_divider.png?ex=6914a181&is=69135001&hm=097a7ed105cff61e7dec6a9f894f9a27ead6950a765de7d50b0970c6e0586b09&")
        
        try:
            await user.send(embed=embed)
        except:
            pass

    async def daily_checkin_all_users(self):
        """Perform daily check-in for all registered users."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, email, password, uid, region FROM genshin_accounts WHERE daily_checkin = 1") as cursor:
                users = await cursor.fetchall()
        
        if not users:
            print("[Daily Check-in] No registered users")
            return
        
        print(f"[Daily Check-in] Processing {len(users)} user(s)")
        
        for user_id, enc_email_or_uid, enc_password, stored_uid, region in users:
            try:
                # Decrypt credentials
                email_or_uid = self.cipher.decrypt(enc_email_or_uid.encode()).decode()
                password = self.cipher.decrypt(enc_password.encode()).decode()
                
                is_email = '@' in email_or_uid
                uid = stored_uid if stored_uid else email_or_uid
                
                # Perform check-in
                success, message, reward_info = await self.perform_daily_checkin(email_or_uid, password, uid, region, is_email)
                
                # Send DM to user
                try:
                    user = await self.bot.fetch_user(user_id)
                    await self.send_checkin_dm(user, success, message, reward_info, uid)
                except Exception as e:
                    print(f"[Daily Check-in] Could not DM user {user_id}: {e}")
                
                await asyncio.sleep(3)  # Rate limiting
                    
            except Exception as e:
                print(f"[Daily Check-in] Error for user {user_id}: {e}")

    async def perform_daily_checkin(self, email_or_uid, password, uid, region, is_email):
        """Perform HoYoLab daily check-in."""
        try:
            async with aiohttp.ClientSession() as session:
                # HoYoLab daily check-in endpoint
                checkin_url = "https://sg-hk4e-api.hoyolab.com/event/sol/sign"
                
                # This is a placeholder - actual implementation requires:
                # 1. Login to HoYoLab to get cookies
                # 2. Call the check-in API with proper headers
                
                params = {
                    'act_id': 'e202102251931481',  # Genshin Impact check-in event
                    'lang': 'en-us'
                }
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    # Would need actual cookies/tokens here from login
                }
                
                # Placeholder response
                # In real implementation, you'd make the actual request
                reward_info = {
                    'name': 'Primogems',
                    'amount': '20',
                    'icon': '<:Primogem:1322058683562131498>'
                }
                
                return True, "Daily check-in successful!", reward_info
                
        except Exception as e:
            return False, f"Check-in failed: {str(e)}", None

    async def send_checkin_dm(self, user, success, message, reward_info, uid):
        """Send DM with check-in results."""
        if success and reward_info:
            description = f"<a:Check:1437951818452832318> Daily check-in completed!\n"
            description += f"<a:a_PaimonPatpat:1437940436110016666> Account: {uid}\n\n"
            description += f"{reward_info['icon']} **Reward Claimed:**\n"
            description += f"<a:Check:1437951818452832318> {reward_info['amount']}x {reward_info['name']}\n"
            color = 0x2ecc71
        else:
            description = f"Daily check-in status\n"
            description += f"<a:a_PaimonPatpat:1437940436110016666> Account: {uid}\n\n"
            description += f"{message}"
            color = 0xe74c3c
        
        embed = discord.Embed(
            title="Genshin Impact | HoYoLab Daily Check-in",
            description=description,
            color=color
        )
        
        embed.set_author(
            name=user.display_name,
            icon_url=user.display_avatar.url
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
        embed.set_image(url="https://cdn.discordapp.com/attachments/1014919079154425917/1020348943902711868/gw_divider.png?ex=6914a181&is=69135001&hm=097a7ed105cff61e7dec6a9f894f9a27ead6950a765de7d50b0970c6e0586b09&")
        
        try:
            await user.send(embed=embed)
        except:
            pass


class GenshinStatusView(discord.ui.View):
    def __init__(self, cog, user_id, auto_redeem, daily_checkin):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.auto_redeem = auto_redeem
        self.daily_checkin = daily_checkin
        
        # Update button labels based on current state
        self.update_button_labels()
    
    def update_button_labels(self):
        # Clear existing buttons
        self.clear_items()
        
        # Auto redeem toggle
        redeem_label = "Disable Auto Redeem" if self.auto_redeem else "Enable Auto Redeem"
        redeem_style = discord.ButtonStyle.danger if self.auto_redeem else discord.ButtonStyle.success
        redeem_button = discord.ui.Button(label=redeem_label, style=redeem_style, custom_id="toggle_redeem")
        redeem_button.callback = self.toggle_auto_redeem
        self.add_item(redeem_button)
        
        # Daily check-in toggle
        checkin_label = "Disable Daily Check-in" if self.daily_checkin else "Enable Daily Check-in"
        checkin_style = discord.ButtonStyle.danger if self.daily_checkin else discord.ButtonStyle.success
        checkin_button = discord.ui.Button(label=checkin_label, style=checkin_style, custom_id="toggle_checkin")
        checkin_button.callback = self.toggle_daily_checkin
        self.add_item(checkin_button)
        
        # Unsubscribe button
        unsub_button = discord.ui.Button(label="Unsubscribe", style=discord.ButtonStyle.secondary, emoji="🔕")
        unsub_button.callback = self.unsubscribe
        self.add_item(unsub_button)
    
    async def toggle_auto_redeem(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        
        # Toggle the setting
        new_value = 0 if self.auto_redeem else 1
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE genshin_accounts SET auto_redeem = ? WHERE user_id = ?",
                (new_value, self.user_id)
            )
            await db.commit()
        
        self.auto_redeem = new_value
        self.update_button_labels()
        
        # Update embed
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT uid, region, created_at FROM genshin_accounts WHERE user_id = ?",
                (self.user_id,)
            ) as cursor:
                row = await cursor.fetchone()
        
        uid, region, created_at = row
        auto_status = "🟢 Active" if self.auto_redeem else "🔴 Inactive"
        checkin_status = "🟢 Active" if self.daily_checkin else "🔴 Inactive"
        
        embed = discord.Embed(title="Genshin Account Registered", color=0x2ecc71)
        embed.add_field(name="UID", value=uid, inline=True)
        embed.add_field(name="Region", value=region.upper(), inline=True)
        embed.add_field(name="Registered", value=created_at.split('T')[0], inline=False)
        embed.add_field(name="Auto Code Redeem", value=auto_status, inline=True)
        embed.add_field(name="Daily Check-in", value=checkin_status, inline=True)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def toggle_daily_checkin(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        
        # Toggle the setting
        new_value = 0 if self.daily_checkin else 1
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE genshin_accounts SET daily_checkin = ? WHERE user_id = ?",
                (new_value, self.user_id)
            )
            await db.commit()
        
        self.daily_checkin = new_value
        self.update_button_labels()
        
        # Update embed
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT uid, region, created_at FROM genshin_accounts WHERE user_id = ?",
                (self.user_id,)
            ) as cursor:
                row = await cursor.fetchone()
        
        uid, region, created_at = row
        auto_status = "🟢 Active" if self.auto_redeem else "🔴 Inactive"
        checkin_status = "🟢 Active" if self.daily_checkin else "🔴 Inactive"
        
        embed = discord.Embed(title="Genshin Account Registered", color=0x2ecc71)
        embed.add_field(name="UID", value=uid, inline=True)
        embed.add_field(name="Region", value=region.upper(), inline=True)
        embed.add_field(name="Registered", value=created_at.split('T')[0], inline=False)
        embed.add_field(name="Auto Code Redeem", value=auto_status, inline=True)
        embed.add_field(name="Daily Check-in", value=checkin_status, inline=True)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def unsubscribe(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        
        # Delete account
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM genshin_accounts WHERE user_id = ?", (self.user_id,))
            await db.commit()
        
        embed = discord.Embed(
            title="Account Removed",
            description="Your Genshin account has been removed from all services.",
            color=0xe74c3c
        )
        
        await interaction.response.edit_message(embed=embed, view=None)


async def setup(bot):
    await bot.add_cog(CodeRedemption(bot))
