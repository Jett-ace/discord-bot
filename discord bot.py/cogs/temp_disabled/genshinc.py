"""Genshin Impact Auto-Claim & Redemption System (Standalone Module)

This is a completely separate system from the main bot's minigames and economy.
It operates independently with its own database, commands, and help system.

Features:
- HoYoLab account verification via in-game signature
- Automatic daily check-in rewards
- Real-time code tracking from pockettactics.com
- Auto-redemption of new codes
- Secure credential storage with encryption

Note: This module does NOT interact with bot economy, items, or game systems.
"""
from __future__ import annotations

import os
import asyncio
from datetime import datetime
from typing import List

import aiohttp
import aiosqlite
import discord
from discord.ext import commands, tasks
from cryptography.fernet import Fernet
from bs4 import BeautifulSoup

# Separate database for Genshin system (isolated from main bot)
DB_PATH = "data/genshin.db"
CODES_URL = "https://www.pockettactics.com/genshin-impact/codes"


class GenshinRegistrationView(discord.ui.View):
    """Interactive registration menu with button-based flow."""
    
    def __init__(self, cog, user: discord.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.uid = None  # Track UID during registration
        self.region = None
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the command author can use buttons."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "<a:X_:1437951830393884788> This registration menu isn't for you!",
                ephemeral=True
            )
            return False
        return True
    
    async def on_timeout(self):
        """Disable all buttons on timeout."""
        for item in self.children:
            item.disabled = True
        
    @discord.ui.button(label="🔗 Link UID", style=discord.ButtonStyle.primary, row=0)
    async def link_uid_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start UID verification flow."""
        await interaction.response.defer(ephemeral=True)
        
        # Send DM to start UID verification
        try:
            dm_embed = discord.Embed(
                title="🔗 UID Verification",
                description=(
                    "Let's link your Genshin Impact account!\n\n"
                    "**Step 1:** Please reply with your **9-digit UID**\n"
                    "You can find it in-game under Settings → Account → UID"
                ),
                color=0x9d7cd8
            )
            dm_embed.set_thumbnail(url="https://i.imgur.com/8wLQKgs.png")
            await self.user.send(embed=dm_embed)
            
            await interaction.followup.send(
                "<a:Check:1437951818452832318> Check your DMs to continue!",
                ephemeral=True
            )
            
            # Wait for UID input
            def check(m):
                return m.author.id == self.user.id and isinstance(m.channel, discord.DMChannel)
            
            msg = await self.cog.bot.wait_for('message', check=check, timeout=180)
            uid = msg.content.strip()
            
            # Validate UID
            if not uid.isdigit() or len(uid) != 9:
                error_embed = discord.Embed(
                    title="<a:X_:1437951830393884788> Invalid UID",
                    description="UID must be exactly 9 digits. Please try again.",
                    color=0xe74c3c
                )
                await self.user.send(embed=error_embed)
                return
            
            # Detect region from UID
            first_digit = int(uid[0])
            region_map = {6: 'os_usa', 7: 'os_euro', 8: 'os_asia', 9: 'os_cht'}
            region = region_map.get(first_digit, 'os_asia')
            
            self.uid = uid
            self.region = region
            
            # Generate verification code
            verification_code = f"CopilotBot_{self.user.id}"
            
            # Send signature verification instructions
            verify_embed = discord.Embed(
                title="🔒 Verify Ownership",
                description=(
                    f"**Step 2:** Set your in-game signature to:\n"
                    f"```{verification_code}```\n\n"
                    "**How to set signature:**\n"
                    "1. Open Genshin Impact\n"
                    "2. Go to Profile (top left)\n"
                    "3. Edit > Signature\n"
                    "4. Paste the code above\n"
                    "5. Save and reply with `done`\n\n"
                    "⏳ This helps verify you own this account!"
                ),
                color=0x9d7cd8
            )
            await self.user.send(embed=verify_embed)
            
            # Wait for confirmation
            confirm_msg = await self.cog.bot.wait_for('message', check=check, timeout=300)
            
            if confirm_msg.content.strip().lower() != 'done':
                await self.user.send("<a:X_:1437951830393884788> Verification cancelled.")
                return
            
            # Check signature via Enka Network API
            checking_embed = discord.Embed(
                title="⏳ Verifying Signature...",
                description="Please wait while we check your profile...",
                color=0x3498db
            )
            await self.user.send(embed=checking_embed)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://enka.network/api/uid/{uid}/") as resp:
                    if resp.status != 200:
                        error_embed = discord.Embed(
                            title="<a:X_:1437951830393884788> Verification Failed",
                            description=(
                                "Could not fetch your profile. Make sure:\n"
                                "- Your UID is correct\n"
                                "- Your profile is public (Settings → Other → Show Character Details)"
                            ),
                            color=0xe74c3c
                        )
                        await self.user.send(embed=error_embed)
                        return
                    
                    data = await resp.json()
                    signature = data.get("playerInfo", {}).get("signature", "")
                    
                    if verification_code not in signature:
                        error_embed = discord.Embed(
                            title="<a:X_:1437951830393884788> Signature Mismatch",
                            description=(
                                f"Your signature doesn't match!\n\n"
                                f"**Expected:** `{verification_code}`\n"
                                f"**Found:** `{signature or '(empty)'}`\n\n"
                                "Please set it correctly and try again."
                            ),
                            color=0xe74c3c
                        )
                        await self.user.send(embed=error_embed)
                        return
            
            # UID verified! Now need HoYoLab cookies
            success_embed = discord.Embed(
                title="<a:Check:1437951818452832318> UID Verified!",
                description=(
                    f"Successfully verified UID: `{uid}` (Region: {region})\n\n"
                    "**Next Step:** Click the **🍪 HoYoLab** button to link your cookies for automation!"
                ),
                color=0x2ecc71
            )
            await self.user.send(embed=success_embed)
            
            # Enable HoYoLab button
            for item in self.children:
                if isinstance(item, discord.ui.Button) and "HoYoLab" in item.label:
                    item.disabled = False
            
        except asyncio.TimeoutError:
            timeout_embed = discord.Embed(
                title="⏰ Registration Timed Out",
                description="You took too long to respond. Please start again.",
                color=0x95a5a6
            )
            await self.user.send(embed=timeout_embed)
        except discord.Forbidden:
            await interaction.followup.send(
                "<a:X_:1437951830393884788> I can't DM you! Please enable DMs from server members.",
                ephemeral=True
            )
    
    @discord.ui.button(label="🍪 HoYoLab", style=discord.ButtonStyle.primary, row=0, disabled=True)
    async def hoyolab_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Link HoYoLab cookies for automation."""
        await interaction.response.defer(ephemeral=True)
        
        if not self.uid:
            await interaction.followup.send(
                "<a:X_:1437951830393884788> Please verify your UID first!",
                ephemeral=True
            )
            return
        
        try:
            # Send HoYoLab cookie instructions
            cookie_embed = discord.Embed(
                title="🍪 HoYoLab Cookie Setup",
                description=(
                    "To enable automatic features, I need your HoYoLab cookies.\n\n"
                    "**How to get cookies:**\n"
                    "1. Go to [HoYoLab](https://www.hoyolab.com/)\n"
                    "2. Log in to your account\n"
                    "3. Press `F12` (Developer Tools)\n"
                    "4. Go to **Console** tab\n"
                    "5. Paste this code:\n"
                    "```javascript\n"
                    "copy(document.cookie)\n"
                    "```\n"
                    "6. Press Enter\n"
                    "7. Reply here with the copied cookies\n\n"
                    "🔒 Your cookies are encrypted and never shared!"
                ),
                color=0x9d7cd8
            )
            cookie_embed.set_footer(text="Cookies enable auto check-in and code redemption")
            await self.user.send(embed=cookie_embed)
            
            await interaction.followup.send(
                "<a:Check:1437951818452832318> Check your DMs!",
                ephemeral=True
            )
            
            # Wait for cookie input
            def check(m):
                return m.author.id == self.user.id and isinstance(m.channel, discord.DMChannel)
            
            msg = await self.cog.bot.wait_for('message', check=check, timeout=300)
            cookie_string = msg.content.strip()
            
            # Parse cookies
            ltuid = None
            ltoken = None
            
            # Try to extract from full cookie string
            for cookie in cookie_string.split(';'):
                cookie = cookie.strip()
                if cookie.startswith('ltuid=') or cookie.startswith('ltuid_v2='):
                    ltuid = cookie.split('=', 1)[1]
                elif cookie.startswith('ltoken=') or cookie.startswith('ltoken_v2='):
                    ltoken = cookie.split('=', 1)[1]
            
            if not ltuid or not ltoken:
                error_embed = discord.Embed(
                    title="<a:X_:1437951830393884788> Invalid Cookies",
                    description=(
                        "Could not find `ltuid` and `ltoken` in your cookies.\n\n"
                        "Make sure you copied the full cookie string from the console!"
                    ),
                    color=0xe74c3c
                )
                await self.user.send(embed=error_embed)
                return
            
            # Validate cookies by making test API call
            headers = {
                'Cookie': f'ltuid={ltuid}; ltoken={ltoken}'
            }
            
            async with aiohttp.ClientSession() as session:
                url = f"https://bbs-api-os.hoyolab.com/game_record/genshin/api/index?role_id={self.uid}&server={self.region}"
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        error_embed = discord.Embed(
                            title="<a:X_:1437951830393884788> Cookie Validation Failed",
                            description="The cookies you provided are invalid or expired. Please try again.",
                            color=0xe74c3c
                        )
                        await self.user.send(embed=error_embed)
                        return
            
            # Encrypt and store in database
            encrypted_ltuid = self.cog.cipher.encrypt(ltuid.encode()).decode()
            encrypted_ltoken = self.cog.cipher.encrypt(ltoken.encode()).decode()
            
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO genshin_accounts 
                    (user_id, uid, region, ltuid, ltoken, verified, auto_redeem, daily_checkin)
                    VALUES (?, ?, ?, ?, ?, 1, 1, 1)
                """, (self.user.id, self.uid, self.region, encrypted_ltuid, encrypted_ltoken))
                await db.commit()
            
            # Registration complete!
            complete_embed = discord.Embed(
                title="<a:Check:1437951818452832318> Registration Complete!",
                description=(
                    f"**Account Linked Successfully!**\n\n"
                    f"**UID:** `{self.uid}`\n"
                    f"**Region:** `{self.region}`\n\n"
                    "**Features Enabled:**\n"
                    "- 📅 Daily HoYoLab check-in\n"
                    "- 🎁 Automatic code redemption\n"
                    "- 📬 DM notifications\n\n"
                    "You can manage settings with `ggenshin_status`!"
                ),
                color=0x2ecc71
            )
            complete_embed.set_thumbnail(url="https://i.imgur.com/8wLQKgs.png")
            await self.user.send(embed=complete_embed)
            
            # Disable all buttons (registration complete)
            for item in self.children:
                item.disabled = True
            
            await interaction.message.edit(view=self)
            
        except asyncio.TimeoutError:
            timeout_embed = discord.Embed(
                title="⏰ Cookie Setup Timed Out",
                description="You took too long to respond. Please click the button again to retry.",
                color=0x95a5a6
            )
            await self.user.send(embed=timeout_embed)
        except discord.Forbidden:
            await interaction.followup.send(
                "<a:X_:1437951830393884788> I can't DM you! Please enable DMs from server members.",
                ephemeral=True
            )
    
    @discord.ui.button(label="📊 Wish History", style=discord.ButtonStyle.secondary, row=0, disabled=True)
    async def wish_history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Import wish history (future feature)."""
        await interaction.response.send_message(
            "📊 Wish history import coming soon! This will let you track your gacha pulls and pity counts.",
            ephemeral=True
        )
    
    @discord.ui.button(label="◀️ Go Back", style=discord.ButtonStyle.secondary, row=1)
    async def go_back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel registration."""
        cancel_embed = discord.Embed(
            title="Registration Cancelled",
            description="You can start again anytime with `gregister_genshin`!",
            color=0x95a5a6
        )
        await interaction.response.send_message(embed=cancel_embed, ephemeral=True)
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.message.edit(view=self)


class CodeRedemptionView(discord.ui.View):
    """View with buttons for redeeming codes."""
    
    def __init__(self, cog, user_id: int, codes: List[str]):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.codes = codes


class GenshinCog(commands.Cog, name="Genshin System"):
    """Standalone Genshin Impact HoYoLab integration - completely separate from bot minigames."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cipher = self.get_or_create_cipher()
        self.known_codes: set = set()
        self.code_scanner.start()
        self.daily_checkin.start()

    def get_or_create_cipher(self) -> Fernet:
        """Create or load encryption key for credentials."""
        key_path = "data/genshin_key.key"
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(key_path, "wb") as f:
                f.write(key)
        return Fernet(key)

    async def cog_load(self):
        """Set up database tables and load existing codes."""
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        async with aiosqlite.connect(DB_PATH) as db:
            # Create tables
            await db.execute("""
                CREATE TABLE IF NOT EXISTS genshin_accounts (
                    user_id INTEGER PRIMARY KEY,
                    ltuid TEXT,
                    ltoken TEXT,
                    uid TEXT,
                    region TEXT,
                    created_at TEXT,
                    verified INTEGER DEFAULT 0,
                    auto_redeem INTEGER DEFAULT 1,
                    daily_checkin INTEGER DEFAULT 1
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS genshin_codes (
                    code TEXT PRIMARY KEY,
                    discovered_at TEXT,
                    active INTEGER DEFAULT 1
                )
            """)
            
            await db.commit()
            
            # Load known codes
            cursor = await db.execute("SELECT code FROM genshin_codes WHERE active = 1")
            rows = await cursor.fetchall()
            self.known_codes = {row[0] for row in rows}
        
        print(f"[Genshin] Loaded {len(self.known_codes)} known codes")

    def cog_unload(self):
        """Cancel background tasks."""
        self.code_scanner.cancel()
        self.daily_checkin.cancel()

    # ==================== REGISTRATION ====================

    @commands.command(name="register_genshin", hidden=True)
    async def register_genshin(self, ctx):
        """Complete registration with interactive UI."""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT verified FROM genshin_accounts WHERE user_id = ?",
                (ctx.author.id,)
            )
            row = await cursor.fetchone()
        
        if row and row[0] == 1:
            await ctx.send("<a:Check:1437951818452832318> You're already registered! Use `!genshin_status` to view settings.")
            return

        embed = discord.Embed(
            title="🎮 Genshin Account Registration",
            description=(
                "Connect your Genshin Impact account to unlock automated features!\n\n"
                "**What you'll get:**\n"
                "- Daily HoYoLab check-in rewards\n"
                "- Automatic code redemption\n"
                "- Real-time notifications via DM\n\n"
                "Choose your registration method below:"
            ),
            color=0x9d7cd8
        )
        embed.set_thumbnail(url="https://i.imgur.com/8wLQKgs.png")
        
        view = GenshinRegistrationView(self, ctx.author)
        await ctx.send(embed=embed, view=view)

    # ==================== CODE SCANNING ====================

    @tasks.loop(hours=2)
    async def code_scanner(self):
        """Automatically scan for new codes."""
        await self.bot.wait_until_ready()
        print("[Genshin] Scanning for new codes...")
        
        new_codes = await self.scrape_codes()
        
        if new_codes:
            print(f"[Genshin] Found {len(new_codes)} new code(s): {new_codes}")
            await self.redeem_for_all_users(new_codes)
        else:
            print("[Genshin] No new codes found")

    async def scrape_codes(self):
        """Scrape codes from website."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {'User-Agent': 'Mozilla/5.0'}
                async with session.get(CODES_URL, headers=headers, timeout=15) as resp:
                    if resp.status != 200:
                        return []
                    
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    codes = set()
                    for tag in soup.find_all(['strong', 'code']):
                        text = tag.get_text().strip().upper()
                        if self.is_valid_code(text):
                            codes.add(text)
                    
                    # Filter new codes
                    new_codes = [code for code in codes if code not in self.known_codes]
                    
                    # Save to database
                    if new_codes:
                        async with aiosqlite.connect(DB_PATH) as db:
                            for code in new_codes:
                                await db.execute(
                                    "INSERT OR IGNORE INTO genshin_codes (code, discovered_at) VALUES (?, ?)",
                                    (code, datetime.utcnow().isoformat())
                                )
                                self.known_codes.add(code)
                            await db.commit()
                    
                    return new_codes
        except Exception as e:
            print(f"[Genshin] Scraping error: {e}")
            return []

    def is_valid_code(self, code):
        """Validate code format."""
        if not code or len(code) < 8 or len(code) > 16:
            return False
        if not code.isalnum() or not code.isupper():
            return False
        if any(word in code for word in ['HTTP', 'HTML', 'GENSHIN', 'IMPACT']):
            return False
        return True

    async def redeem_for_all_users(self, codes):
        """Redeem codes for all users with auto-redeem enabled."""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id, ltuid, ltoken, uid, region FROM genshin_accounts WHERE verified = 1 AND auto_redeem = 1"
            )
            users = await cursor.fetchall()
        
        if not users:
            return
        
        for user_id, enc_ltuid, enc_ltoken, uid, region in users:
            try:
                ltuid = self.cipher.decrypt(enc_ltuid.encode()).decode()
                ltoken = self.cipher.decrypt(enc_ltoken.encode()).decode()
                
                results = []
                for code in codes:
                    success, message = await self.redeem_single_code(ltuid, ltoken, uid, region, code)
                    results.append((code, success, message))
                    await asyncio.sleep(2)
                
                user = await self.bot.fetch_user(user_id)
                await self.send_redemption_dm(user, results, uid)
            except Exception as e:
                print(f"[Genshin] Error for user {user_id}: {e}")

    async def redeem_single_code(self, ltuid, ltoken, uid, region, code):
        """Redeem single code via HoYoLab API."""
        try:
            url = "https://sg-hk4e-api.hoyolab.com/common/apicdkey/api/webExchangeCdkey"
            
            params = {'uid': uid, 'region': region, 'cdkey': code, 'game_biz': 'hk4e_global', 'lang': 'en'}
            cookies = {'ltuid': ltuid, 'ltoken': ltoken}
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, cookies=cookies, headers=headers, timeout=10) as resp:
                    data = await resp.json()
                    
                    if data.get('retcode') == 0:
                        return True, "Redeemed successfully"
                    elif data.get('retcode') == -2017:
                        return False, "Already claimed"
                    elif data.get('retcode') == -2003:
                        return False, "Invalid/expired"
                    else:
                        return False, data.get('message', 'Unknown error')
        except Exception as e:
            return False, str(e)

    async def send_redemption_dm(self, user, results, uid):
        """Send redemption results via DM."""
        successful = sum(1 for _, success, _ in results if success)
        
        description = f"**Account:** `{uid}`\n\n"
        for code, success, message in results:
            emoji = "<a:Check:1437951818452832318>" if success else "<a:X_:1437951830393884788>"
            description += f"{emoji} `{code}` - {message}\n"
        
        embed = discord.Embed(
            title="🎁 Genshin Code Redemption",
            description=description,
            color=0x2ecc71 if successful > 0 else 0xe74c3c,
            timestamp=datetime.utcnow()
        )
        
        try:
            await user.send(embed=embed)
        except Exception:
            pass

    # ==================== DAILY CHECK-IN ====================

    @tasks.loop(hours=24)
    async def daily_checkin(self):
        """Run daily HoYoLab check-in."""
        await self.bot.wait_until_ready()
        print("[Genshin] Running daily check-in...")
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id, ltuid, ltoken, uid, region FROM genshin_accounts WHERE verified = 1 AND daily_checkin = 1"
            )
            users = await cursor.fetchall()
        
        if not users:
            return
        
        for user_id, enc_ltuid, enc_ltoken, uid, region in users:
            try:
                ltuid = self.cipher.decrypt(enc_ltuid.encode()).decode()
                ltoken = self.cipher.decrypt(enc_ltoken.encode()).decode()
                
                success, message = await self.perform_checkin(ltuid, ltoken, region)
                
                user = await self.bot.fetch_user(user_id)
                await self.send_checkin_dm(user, success, message, uid)
                await asyncio.sleep(3)
            except Exception as e:
                print(f"[Genshin] Check-in error for {user_id}: {e}")

    async def perform_checkin(self, ltuid, ltoken, region):
        """Perform HoYoLab daily check-in."""
        try:
            url = "https://sg-hk4e-api.hoyolab.com/event/sol/sign"
            params = {'act_id': 'e202102251931481', 'lang': 'en-us'}
            cookies = {'ltuid': ltuid, 'ltoken': ltoken}
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, cookies=cookies, headers=headers, timeout=10) as resp:
                    data = await resp.json()
                    
                    if data.get('retcode') == 0:
                        return True, "Daily reward claimed!"
                    elif data.get('retcode') == -5003:
                        return False, "Already claimed today"
                    else:
                        return False, data.get('message', 'Unknown error')
        except Exception as e:
            return False, str(e)

    async def send_checkin_dm(self, user, success, message, uid):
        """Send check-in result via DM."""
        embed = discord.Embed(
            title="📅 Daily HoYoLab Check-in",
            description=f"**Account:** `{uid}`\n\n{message}",
            color=0x2ecc71 if success else 0x95a5a6,
            timestamp=datetime.utcnow()
        )
        
        try:
            await user.send(embed=embed)
        except Exception:
            pass

    # ==================== USER COMMANDS ====================

    @commands.command(name="genshin_status", hidden=True)
    async def genshin_status(self, ctx):
        """Check Genshin account status."""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT uid, region, verified, auto_redeem, daily_checkin FROM genshin_accounts WHERE user_id = ?",
                (ctx.author.id,)
            )
            row = await cursor.fetchone()
        
        if not row:
            await ctx.send("❌ Not registered. Use `!register_genshin`!")
            return
        
        uid, region, verified, auto_redeem, daily_checkin = row
        
        embed = discord.Embed(title="🎮 Genshin Account Status", color=0x2ecc71)
        embed.add_field(name="UID", value=uid, inline=True)
        embed.add_field(name="Region", value=region.upper(), inline=True)
        embed.add_field(name="Auto Redeem", value="🟢" if auto_redeem else "🔴", inline=True)
        embed.add_field(name="Daily Check-in", value="🟢" if daily_checkin else "🔴", inline=True)
        
        await ctx.send(embed=embed)

    @commands.command(name="toggle_redeem", hidden=True)
    async def toggle_redeem(self, ctx):
        """Toggle automatic code redemption."""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT auto_redeem FROM genshin_accounts WHERE user_id = ?",
                (ctx.author.id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                await ctx.send("❌ Not registered!")
                return
            
            new_value = 0 if row[0] else 1
            await db.execute(
                "UPDATE genshin_accounts SET auto_redeem = ? WHERE user_id = ?",
                (new_value, ctx.author.id)
            )
            await db.commit()
        
        await ctx.send(f"✅ Auto redemption {'enabled' if new_value else 'disabled'}!")

    @commands.command(name="toggle_checkin", hidden=True)
    async def toggle_checkin(self, ctx):
        """Toggle daily check-in."""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT daily_checkin FROM genshin_accounts WHERE user_id = ?",
                (ctx.author.id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                await ctx.send("❌ Not registered!")
                return
            
            new_value = 0 if row[0] else 1
            await db.execute(
                "UPDATE genshin_accounts SET daily_checkin = ? WHERE user_id = ?",
                (new_value, ctx.author.id)
            )
            await db.commit()
        
        await ctx.send(f"✅ Daily check-in {'enabled' if new_value else 'disabled'}!")


async def setup(bot: commands.Bot) -> None:
    """Load the Genshin cog."""
    await bot.add_cog(GenshinCog(bot))
    print("[Genshin] Cog loaded successfully")
