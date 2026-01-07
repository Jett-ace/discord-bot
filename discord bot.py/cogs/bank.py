"""Bank System - Loans, penalties, and global bank tracking"""
import discord
from discord.ext import commands, tasks
import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH
from utils.database import get_user_data, update_user_data, get_account_level, ensure_user_db, require_enrollment
from utils.embed import send_embed
from utils.transaction_logger import log_transaction


class LoanConfirmationView(discord.ui.View):
    """View for accepting or declining loan requests"""
    
    def __init__(self, lender: discord.Member, borrower: discord.Member, amount: int):
        super().__init__(timeout=60)
        self.lender = lender
        self.borrower = borrower
        self.amount = amount
        self.message = None
    
    async def on_timeout(self):
        """Called when the view times out"""
        if self.message:
            embed = discord.Embed(
                title="⏰ Loan Request Expired",
                description=f"{self.borrower.mention} did not respond in time.",
                color=0x95A5A6
            )
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(embed=embed, view=self)
            except:
                pass
    
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Accept the loan"""
        if interaction.user.id != self.borrower.id:
            return await interaction.response.send_message("❌ Only the loan recipient can accept!", ephemeral=True)
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        
        # Check if lender still has enough money
        lender_data = await get_user_data(self.lender.id)
        lender_balance = lender_data.get('mora', 0)
        
        if self.amount > lender_balance:
            embed = discord.Embed(
                title="❌ Loan Failed",
                description=f"{self.lender.mention} no longer has enough <:mora:1437958309255577681>!",
                color=0xE74C3C
            )
            await interaction.response.edit_message(embed=embed, view=self)
            return
        
        # Check if borrower already has an active loan
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id FROM p2p_loans WHERE borrower_id = ? AND status = 'active'",
                (self.borrower.id,)
            )
            if await cursor.fetchone():
                embed = discord.Embed(
                    title="❌ Loan Failed",
                    description=f"{self.borrower.mention} already has an active P2P loan!",
                    color=0xE74C3C
                )
                await interaction.response.edit_message(embed=embed, view=self)
                return
            
            # Create loan
            now = datetime.now()
            due = now + timedelta(hours=12)
            
            await db.execute(
                """INSERT INTO p2p_loans (lender_id, borrower_id, amount, interest_rate, due_date, created_at, status)
                   VALUES (?, ?, ?, 5.0, ?, ?, 'active')""",
                (self.lender.id, self.borrower.id, self.amount, due.isoformat(), now.isoformat())
            )
            await db.commit()
        
        # Transfer money
        await update_user_data(self.lender.id, mora=lender_balance - self.amount)
        
        await ensure_user_db(self.borrower.id)
        borrower_data = await get_user_data(self.borrower.id)
        borrower_balance = borrower_data.get('mora', 0)
        await update_user_data(self.borrower.id, mora=borrower_balance + self.amount)
        
        # Calculate expected return
        interest = int(self.amount * 0.05)
        total_return = self.amount + interest
        
        embed = discord.Embed(
            title="✅ Loan Accepted!",
            description=f"{self.lender.mention} loaned {self.borrower.mention} `{self.amount:,}` <:mora:1437958309255577681>",
            color=0x2ECC71
        )
        embed.add_field(
            name="Expected Return",
            value=f"`{total_return:,}` <:mora:1437958309255577681> (+5% interest)",
            inline=False
        )
        embed.add_field(
            name="Due in",
            value="12 hours",
            inline=True
        )
        embed.set_footer(text=f"{self.borrower.display_name} must repay within 12 hours!")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Decline the loan"""
        if interaction.user.id != self.borrower.id:
            return await interaction.response.send_message("❌ Only the loan recipient can decline!", ephemeral=True)
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        
        embed = discord.Embed(
            title="❌ Loan Declined",
            description=f"{self.borrower.mention} declined the loan request.",
            color=0xE74C3C
        )
        await interaction.response.edit_message(embed=embed, view=self)


class Bank(commands.Cog):
    """Bank system for loans and penalties"""
    
    def __init__(self, bot):
        self.bot = bot
        self.daily_tasks.start()  # Start background tasks
    
    def cog_unload(self):
        self.daily_tasks.cancel()
    
    @tasks.loop(hours=1)  # Check every hour
    async def daily_tasks(self):
        """Background task for daily interest and loan deadlines"""
        try:
            await self.distribute_daily_interest()
            await self.check_loan_deadlines()
        except Exception as e:
            print(f"Error in daily tasks: {e}")
    
    @daily_tasks.before_loop
    async def before_daily_tasks(self):
        await self.bot.wait_until_ready()
    
    async def cog_load(self):
        """Initialize database tables"""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Global bank balance
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS global_bank (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        balance INTEGER DEFAULT 0,
                        total_loans_given INTEGER DEFAULT 0,
                        total_penalties_collected INTEGER DEFAULT 0
                    )
                """)
                
                # User loans
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS user_loans (
                        user_id INTEGER PRIMARY KEY,
                        loan_amount INTEGER DEFAULT 0,
                        penalty_amount INTEGER DEFAULT 0,
                        due_date TEXT,
                        penalty_applied INTEGER DEFAULT 0,
                        last_loan_date TEXT,
                        daily_loan_count INTEGER DEFAULT 0,
                        loan_count_date TEXT,
                        loan_ban_until TEXT
                    )
                """)
                
                # P2P loans between players
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS p2p_loans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        lender_id INTEGER NOT NULL,
                        borrower_id INTEGER NOT NULL,
                        amount INTEGER NOT NULL,
                        interest_rate REAL DEFAULT 5.0,
                        due_date TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        status TEXT DEFAULT 'active'
                    )
                """)
                
                # Migrations: Add new columns if they don't exist
                try:
                    await db.execute("ALTER TABLE user_loans ADD COLUMN daily_loan_count INTEGER DEFAULT 0")
                    await db.commit()
                except:
                    pass  # Column already exists
                
                try:
                    await db.execute("ALTER TABLE user_loans ADD COLUMN loan_count_date TEXT")
                    await db.commit()
                except:
                    pass  # Column already exists
                
                try:
                    await db.execute("ALTER TABLE user_loans ADD COLUMN loan_ban_until TEXT")
                    await db.commit()
                except:
                    pass  # Column already exists
                
                try:
                    await db.execute("ALTER TABLE user_bank_deposits ADD COLUMN last_interest_date TEXT")
                    await db.commit()
                except:
                    pass
                
                # User bank deposits
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS user_bank_deposits (
                        user_id INTEGER PRIMARY KEY,
                        deposited_amount INTEGER DEFAULT 0,
                        interest_earned INTEGER DEFAULT 0
                    )
                """)
                
                # Bank cards system
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS bank_cards (
                        user_id INTEGER PRIMARY KEY,
                        card_tier INTEGER DEFAULT 0,
                        purchased_at TEXT
                    )
                """)
                
                # Initialize global bank if not exists (starts with 1 million)
                await db.execute("""
                    INSERT INTO global_bank (id, balance) 
                    VALUES (1, 1000000) 
                    ON CONFLICT(id) DO NOTHING
                """)
                
                await db.commit()
        except Exception as e:
            print(f"Error loading Bank cog: {e}")
    
    async def add_to_bank(self, amount: int):
        """Add money to the global bank"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE global_bank SET balance = balance + ? WHERE id = 1",
                (amount,)
            )
            await db.commit()
    
    async def get_bank_balance(self) -> int:
        """Get current global bank balance"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT balance FROM global_bank WHERE id = 1")
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    async def get_user_card_tier(self, user_id: int) -> int:
        """Get user's bank card tier (0-5)"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT card_tier FROM bank_cards WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    def get_card_limit(self, tier: int, is_premium: bool) -> int:
        """Get deposit limit for a card tier"""
        if is_premium:
            return 999_999_999_999  # Effectively unlimited
        
        limits = {
            0: 5_000_000,      # No card: 5M
            1: 50_000_000,     # Platinum: 50M
            2: 150_000_000     # Gold: 150M (max tier)
        }
        return limits.get(tier, 5_000_000)
    
    async def apply_golden_cashback(self, user_id: int, loss_amount: int) -> int:
        """Apply 10% cashback for golden card holders. Returns cashback amount."""
        card_tier = await self.get_user_card_tier(user_id)
        if card_tier == 2:  # Golden card
            cashback = int(loss_amount * 0.10)
            if cashback > 0:
                from utils.database import get_user_data, update_user_data
                user_data = await get_user_data(user_id)
                new_mora = user_data.get('mora', 0) + cashback
                await update_user_data(user_id, mora=new_mora)
                return cashback
        return 0
    
    async def get_user_loan(self, user_id: int):
        """Get user's current loan information"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT loan_amount, penalty_amount, due_date, penalty_applied, last_loan_date FROM user_loans WHERE user_id = ?",
                (user_id,)
            )
            return await cursor.fetchone()
    
    async def check_and_apply_penalty(self, user_id: int):
        """Check if loan is overdue and apply penalty"""
        loan_data = await self.get_user_loan(user_id)
        if not loan_data or loan_data[0] == 0:
            return False
        
        loan_amount, penalty_amount, due_date_str, penalty_applied, _ = loan_data
        
        # Already has penalty
        if penalty_applied:
            return False
        
        # Check if overdue (12 hours past loan time)
        due_date = datetime.fromisoformat(due_date_str)
        now = datetime.now()
        
        if now > due_date:
            # Apply 20% penalty (0.2x the original amount)
            penalty = int(loan_amount * 0.2)
            total_owed = loan_amount + penalty
            
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """UPDATE user_loans 
                       SET penalty_amount = ?, penalty_applied = 1 
                       WHERE user_id = ?""",
                    (penalty, user_id)
                )
                await db.execute(
                    "UPDATE global_bank SET total_penalties_collected = total_penalties_collected + ? WHERE id = 1",
                    (penalty,)
                )
                await db.commit()
            
            return True
        
        return False
    
    async def distribute_daily_interest(self):
        """Distribute 3% daily interest to all depositors (except those with active loans)"""
        async with aiosqlite.connect(DB_PATH) as db:
            # Get all depositors
            cursor = await db.execute(
                "SELECT user_id, deposited_amount, last_interest_date FROM user_bank_deposits WHERE deposited_amount > 0"
            )
            depositors = await cursor.fetchall()
            
            today = datetime.now().date().isoformat()
            
            for user_id, amount, last_date in depositors:
                # Check if already got interest today
                if last_date == today:
                    continue
                
                # Check if user has an active loan - no interest if they do
                loan_cursor = await db.execute(
                    "SELECT loan_amount FROM user_loans WHERE user_id = ? AND loan_amount > 0",
                    (user_id,)
                )
                loan_row = await loan_cursor.fetchone()
                if loan_row:
                    # User has active loan, skip interest
                    continue
                
                # Calculate 3% interest
                interest = int(amount * 0.03)
                
                # Add interest
                await db.execute(
                    """UPDATE user_bank_deposits 
                       SET interest_earned = interest_earned + ?, last_interest_date = ?
                       WHERE user_id = ?""",
                    (interest, today, user_id)
                )
            
            await db.commit()
    
    async def check_loan_deadlines(self):
        """Check all loans for first (12h) and second (24h) deadlines"""
        now = datetime.now()
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id, loan_amount, penalty_amount, due_date, penalty_applied FROM user_loans WHERE loan_amount > 0"
            )
            loans = await cursor.fetchall()
            
            for user_id, loan_amt, penalty_amt, due_date_str, penalty_applied in loans:
                due_date = datetime.fromisoformat(due_date_str)
                time_passed = now - due_date
                
                # Second deadline (24h): Auto-deduct + ban
                if time_passed.total_seconds() >= 86400:  # 24 hours
                    if penalty_applied < 2:  # Haven't applied second penalty yet
                        # Apply second 20% penalty
                        second_penalty = int(loan_amt * 0.2)
                        total_owed = loan_amt + penalty_amt + second_penalty
                        
                        # Get user balance
                        user_data = await get_user_data(user_id)
                        user_mora = user_data.get('mora', 0)
                        
                        # Deduct what we can
                        deducted = min(user_mora, total_owed)
                        remaining_loan = max(0, total_owed - deducted)
                        
                        # Update user balance
                        await update_user_data(user_id, mora=user_mora - deducted)
                        
                        # Add deducted amount back to bank
                        await db.execute(
                            "UPDATE global_bank SET balance = balance + ? WHERE id = 1",
                            (deducted,)
                        )
                        
                        # Set 1-week ban
                        ban_until = (now + timedelta(days=7)).isoformat()
                        
                        # Update loan record
                        await db.execute(
                            """UPDATE user_loans 
                               SET loan_amount = ?, penalty_amount = 0, penalty_applied = 2, loan_ban_until = ?
                               WHERE user_id = ?""",
                            (remaining_loan, ban_until, user_id)
                        )
                
                # First deadline (12h): Apply first 20% penalty
                elif time_passed.total_seconds() >= 43200 and penalty_applied == 0:  # 12 hours
                    first_penalty = int(loan_amt * 0.2)
                    await db.execute(
                        """UPDATE user_loans 
                           SET penalty_amount = penalty_amount + ?, penalty_applied = 1
                           WHERE user_id = ?""",
                        (first_penalty, user_id)
                    )
            
            await db.commit()
    
    @commands.command(name="bal", aliases=["balance", "wallet"])
    async def balance(self, ctx):
        """Check your wallet balance and bank deposits"""
        if not await require_enrollment(ctx):
            return
        
        try:
            # Get wallet balance
            data = await get_user_data(ctx.author.id)
            mora = data.get("mora", 0)
            
            # Get bank deposit
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT deposited_amount, interest_earned FROM user_bank_deposits WHERE user_id = ?",
                    (ctx.author.id,)
                )
                deposit_row = await cursor.fetchone()
                deposited = deposit_row[0] if deposit_row else 0
                interest = deposit_row[1] if deposit_row else 0
            
            # Check premium status
            premium_cog = self.bot.get_cog('Premium')
            custom_badge = ""
            if premium_cog:
                is_premium = await premium_cog.is_premium(ctx.author.id)
                if is_premium:
                    badge = await premium_cog.get_custom_badge(ctx.author.id)
                    if badge:
                        custom_badge = f" {badge}"
            
            embed = discord.Embed(
                title=f"{ctx.author.display_name}{custom_badge}'s Balance",
                color=0xF1C40F
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            
            embed.add_field(
                name="Mora <:mora:1437958309255577681>",
                value=f"{mora:,}",
                inline=True
            )
            embed.add_field(
                name="Bank Deposit <:mora:1437958309255577681>",
                value=f"{deposited:,}",
                inline=True
            )
            
            if interest > 0:
                embed.add_field(
                    name="Interest Earned",
                    value=f"{interest:,} <:mora:1437958309255577681>",
                    inline=False
                )
            
            await send_embed(ctx, embed)
        except Exception as e:
            print(f"Error in balance command: {e}")
            await ctx.send("<a:X_:1437951830393884788> Error retrieving balance.")
    
    @commands.command(name="bank")
    async def bank_info(self, ctx):
        """View the global bank status and your deposits"""
        if not await require_enrollment(ctx):
            return
        
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Get global bank info
                cursor = await db.execute(
                    "SELECT balance, total_loans_given, total_penalties_collected FROM global_bank WHERE id = 1"
                )
                row = await cursor.fetchone()
                balance, total_loans, total_penalties = row if row else (0, 0, 0)
                
                # Get user's deposit
                cursor = await db.execute(
                    "SELECT deposited_amount, interest_earned FROM user_bank_deposits WHERE user_id = ?",
                    (ctx.author.id,)
                )
                user_row = await cursor.fetchone()
                user_deposit = user_row[0] if user_row else 0
                user_interest = user_row[1] if user_row else 0
                
                # Get total deposits from all users
                cursor = await db.execute("SELECT SUM(deposited_amount), SUM(interest_earned) FROM user_bank_deposits")
                deposit_row = await cursor.fetchone()
                total_deposits, total_interest = deposit_row if deposit_row else (0, 0)
                total_deposits = total_deposits or 0
                total_interest = total_interest or 0
                
                # Get rob items for defense calculation
                cursor = await db.execute(
                    "SELECT shotgun, mask, night_vision, lockpicker, guard_dog, guard_dog_expires, spiky_fence, lock FROM rob_items WHERE user_id = ?",
                    (ctx.author.id,)
                )
                rob_row = await cursor.fetchone()
            
            # Calculate robbery stats
            offense_bonus = 0
            defense_bonus = 0
            
            if rob_row:
                shotgun, mask, night_vision, lockpicker, guard_dog, guard_dog_expires, spiky_fence, lock_item = rob_row
                
                # Offense
                if shotgun:
                    offense_bonus += 20
                if mask and night_vision and lockpicker:
                    offense_bonus += 25
                
                # Defense
                if guard_dog and guard_dog_expires:
                    from datetime import datetime
                    expiry = datetime.fromisoformat(guard_dog_expires)
                    if datetime.now() < expiry:
                        defense_bonus += 25
                if spiky_fence:
                    defense_bonus += 5
            
            rob_success_rate = 20 + offense_bonus
            rob_defense_rate = defense_bonus
            
            embed = discord.Embed(
                title="🏦 Global Bank Status",
                description="Community bank - deposit money to earn interest!",
                color=0x2ECC71
            )
            
            # Global stats
            embed.add_field(
                name="💰 Bank Balance",
                value=f"`{balance:,}` <:mora:1437958309255577681>",
                inline=True
            )
            embed.add_field(
                name="💵 Total Deposits",
                value=f"`{total_deposits:,}` <:mora:1437958309255577681>",
                inline=True
            )
            embed.add_field(
                name="Stats",
                value=f"Loans: `{total_loans:,}`\nPenalties: `{total_penalties:,}`",
                inline=True
            )
            
            # User's deposits
            if user_deposit > 0 or user_interest > 0:
                embed.add_field(
                    name=f"Your Deposits",
                    value=(
                        f"Deposited: `{user_deposit:,}` <:mora:1437958309255577681>\n"
                        f"Interest Earned: `{user_interest:,}` <:mora:1437958309255577681>"
                    ),
                    inline=False
                )
            
            embed.add_field(
                name="How It Works",
                value=(
                    "<a:arrow:1437968863026479258> `gdeposit <amount>` - Deposit to earn interest\n"
                    "<a:arrow:1437968863026479258> `gwithdraw <amount>` - Withdraw anytime\n"
                    "<a:arrow:1437968863026479258> Earn 5% from each loan distributed to depositors"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💳 Bank Cards",
                value=(
                    "Upgrade your card to increase deposit limits:\n"
                    "<:platinum:1457410519534403635> **Platinum**: 50M limit (10M mora)\n"
                    "<a:gold:1457409675963138205> **Gold**: 150M limit (50M mora)\n\n"
                    "Use `gbankcard` to view cards\n"
                    "Use `gbankcard buy` to purchase/upgrade"
                ),
                inline=False
            )
            
            # Add robbery stats
            embed.add_field(
                name="⚔️ Robbery Stats",
                value=(
                    f"Rob Success Rate: **{rob_success_rate}%**\n"
                    f"Defense Rate: **{rob_defense_rate}%**"
                ),
                inline=False
            )
            
            await send_embed(ctx, embed)
        except Exception as e:
            print(f"Error in bank command: {e}")
            await ctx.send("<a:X_:1437951830393884788> Error retrieving bank info.")
    
    @commands.command(name="deposit", aliases=["bankdeposit", "dep", "d"])
    async def deposit_money(self, ctx, amount: str = None):
        """Deposit Mora into the bank to earn interest from loans
        
        Usage: gdeposit <amount> or gdeposit all
        
        How it works:
        - Deposit your Mora safely in the bank
        - Earn 5% interest whenever someone takes a loan
        - Interest distributed proportionally based on your deposit
        - Free users: Max 5M deposit | Premium: Unlimited
        - Withdraw anytime with no fees
        
        Example: gdeposit 100000
        """
        if not await require_enrollment(ctx):
            return
        await ensure_user_db(ctx.author.id)
        
        if amount is None:
            # Show deposit info
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT deposited_amount, interest_earned FROM user_bank_deposits WHERE user_id = ?",
                    (ctx.author.id,)
                )
                row = await cursor.fetchone()
                deposited, interest = row if row else (0, 0)
                
                # Get total deposits
                cursor = await db.execute("SELECT SUM(deposited_amount) FROM user_bank_deposits")
                total_row = await cursor.fetchone()
                total_deposits = total_row[0] if total_row and total_row[0] else 0
                
                # Check for bank_capacity bonus from banker's keys
                cursor = await db.execute(
                    "SELECT bank_capacity FROM users WHERE user_id = ?",
                    (ctx.author.id,)
                )
                capacity_row = await cursor.fetchone()
                bank_capacity_bonus = capacity_row[0] if capacity_row and capacity_row[0] else 0
            
            # Check premium status and card tier
            premium_cog = self.bot.get_cog("Premium")
            is_premium = premium_cog and await premium_cog.is_premium(ctx.author.id)
            card_tier = await self.get_user_card_tier(ctx.author.id)
            base_deposit_limit = self.get_card_limit(card_tier, is_premium)
            deposit_limit = base_deposit_limit + bank_capacity_bonus
            
            card_names = ["No Card", "<:platinum:1457410519534403635> Platinum", "<a:gold:1457409675963138205> Gold"]
            card_name = card_names[card_tier]
            limit_text = "Unlimited ⭐" if is_premium else f"{deposit_limit:,}"
            
            embed = discord.Embed(
                title="🏦 Bank Deposits",
                description="Keep your Mora safe and earn interest!",
                color=0x3498DB
            )
            embed.add_field(
                name="💰 Your Deposit",
                value=f"`{deposited:,}` <:mora:1437958309255577681>",
                inline=True
            )
            embed.add_field(
                name="📈 Interest Earned",
                value=f"`{interest:,}` <:mora:1437958309255577681>",
                inline=True
            )
            
            card_benefits = card_name
            if card_tier == 2:  # Golden card
                card_benefits += "\n<a:arrow:1437968863026479258> 10% cashback on losses\n<a:arrow:1437968863026479258> 2 loans per day (750K max)"
            elif card_tier == 1:  # Platinum card
                card_benefits += "\n<a:arrow:1437968863026479258> Higher deposit limit"
            
            embed.add_field(
                name="💳 Bank Card",
                value=card_benefits,
                inline=True
            )
            
            limit_display = limit_text
            if bank_capacity_bonus > 0 and not is_premium:
                limit_display = f"`{limit_text}` <:mora:1437958309255577681>\n<a:bankerskey:1457962936076075049> +{bank_capacity_bonus:,} bonus"
            
            embed.add_field(
                name="Deposit Limit",
                value=limit_display,
                inline=True
            )
            
            # Check if user has active loan
            loan_data = await self.get_user_loan(ctx.author.id)
            has_loan = loan_data and loan_data[0] > 0
            
            interest_info = "<a:arrow:1437968863026479258> Earn 3% daily interest on deposits\n<a:arrow:1437968863026479258> Earn 5% from each loan distributed to depositors"
            if has_loan:
                interest_info = "<a:arrow:1437968863026479258> ⚠️ **No interest while you have an active loan**\n<a:arrow:1437968863026479258> Repay your loan to resume earning interest"
            
            embed.add_field(
                name="How it Works",
                value=(
                    f"<a:arrow:1437968863026479258> `gdeposit <amount>` - Deposit to bank\n"
                    f"<a:arrow:1437968863026479258> `gwithdraw <amount>` - Withdraw anytime\n"
                    f"{interest_info}"
                ),
                inline=False
            )
            if not is_premium:
                embed.set_footer(text="Premium members get unlimited deposits!")
            return await send_embed(ctx, embed)
        
        # Parse amount
        user_data = await get_user_data(ctx.author.id)
        user_mora = user_data['mora']
        
        if amount.lower() == 'all':
            deposit_amount = user_mora
        else:
            try:
                deposit_amount = int(amount.replace(',', ''))
            except:
                return await ctx.send("❌ Invalid amount! Use a number or `all`")
        
        if deposit_amount <= 0:
            return await ctx.send("❌ Deposit amount must be positive!")
        
        if deposit_amount > user_mora:
            return await ctx.send(f"❌ You only have `{user_mora:,}` <:mora:1437958309255577681>!")
        
        # Check current deposits and limit
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT deposited_amount FROM user_bank_deposits WHERE user_id = ?",
                (ctx.author.id,)
            )
            row = await cursor.fetchone()
            current_deposit = row[0] if row else 0
            
            # Check for bank_capacity bonus from banker's keys
            cursor = await db.execute(
                "SELECT bank_capacity FROM users WHERE user_id = ?",
                (ctx.author.id,)
            )
            row = await cursor.fetchone()
            bank_capacity_bonus = row[0] if row and row[0] else 0
        
        # Check premium status and card tier for deposit limit
        premium_cog = self.bot.get_cog("Premium")
        is_premium = premium_cog and await premium_cog.is_premium(ctx.author.id)
        card_tier = await self.get_user_card_tier(ctx.author.id)
        base_deposit_limit = self.get_card_limit(card_tier, is_premium)
        
        # Add bank_capacity bonus from banker's keys
        deposit_limit = base_deposit_limit + bank_capacity_bonus
        
        if not is_premium:
            # Check against card tier limit + bonuses
            new_total = current_deposit + deposit_amount
            if new_total > deposit_limit:
                remaining = deposit_limit - current_deposit
                card_names = ["No Card", "<:platinum:1457410519534403635> Platinum", "<a:gold:1457409675963138205> Gold"]
                card_name = card_names[card_tier]
                embed = discord.Embed(
                    title="❌ Deposit Limit Reached",
                    description=f"Your current limit: **{deposit_limit:,}** <:mora:1437958309255577681>",
                    color=0xE74C3C
                )
                embed.add_field(
                    name="💳 Current Card",
                    value=card_name,
                    inline=True
                )
                if bank_capacity_bonus > 0:
                    embed.add_field(
                        name="<a:bankerskey:1457962936076075049> Bonus Capacity",
                        value=f"+{bank_capacity_bonus:,} <:mora:1437958309255577681>",
                        inline=True
                    )
                embed.add_field(
                    name="Current Deposit",
                    value=f"`{current_deposit:,}` <:mora:1437958309255577681>",
                    inline=True
                )
                embed.add_field(
                    name="Remaining Space",
                    value=f"`{remaining:,}` <:mora:1437958309255577681>",
                    inline=True
                )
                if card_tier < 2:
                    embed.add_field(
                        name="💳 Upgrade Your Card!",
                        value=f"Use `gbankcard` to upgrade and increase your limit!\nOr get Premium for unlimited deposits: `gpremium`",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="💎 Go Premium!",
                        value="Premium members get **unlimited** deposits!\nUse `gpremium` to learn more.",
                        inline=False
                    )
                return await send_embed(ctx, embed)
        
        # Make deposit
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO user_bank_deposits (user_id, deposited_amount, interest_earned)
                   VALUES (?, ?, 0)
                   ON CONFLICT(user_id) DO UPDATE SET
                   deposited_amount = deposited_amount + ?""",
                (ctx.author.id, deposit_amount, deposit_amount)
            )
            await db.commit()
        
        # Take money from user
        await update_user_data(ctx.author.id, mora=user_mora - deposit_amount)
        
        new_total = current_deposit + deposit_amount
        
        # Log transaction
        await log_transaction(ctx.author.id, "deposit", deposit_amount, f"New bank balance: {new_total:,}")
        
        embed = discord.Embed(
            title="✅ Deposit Successful!",
            description=f"You deposited `{deposit_amount:,}` <:mora:1437958309255577681> into the bank.",
            color=0x2ECC71
        )
        embed.add_field(
            name="💰 Total in Bank",
            value=f"`{new_total:,}` <:mora:1437958309255577681>",
            inline=True
        )
        embed.add_field(
            name="📈 Earning Interest",
            value="5% of every loan taken!",
            inline=True
        )
        if not is_premium:
            remaining = deposit_limit - new_total
            if remaining < deposit_limit * 0.2:  # Warn when at 80% capacity
                embed.set_footer(text=f"You can deposit {remaining:,} more Mora | Upgrade card: gbankcard")
        await send_embed(ctx, embed)
    
    @commands.command(name="withdraw", aliases=["bankwithdraw", "with", "wd", "w"])
    async def withdraw_money(self, ctx, amount: str = None):
        """Withdraw your deposited Mora from the bank
        
        Usage: gwithdraw <amount> or gwithdraw all
        Example: gwithdraw 50000
        """
        if not await require_enrollment(ctx):
            return
        await ensure_user_db(ctx.author.id)
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT deposited_amount, interest_earned FROM user_bank_deposits WHERE user_id = ?",
                (ctx.author.id,)
            )
            row = await cursor.fetchone()
        
        if not row or row[0] == 0:
            return await ctx.send("❌ You don't have any money deposited in the bank!")
        
        deposited, interest = row
        total_available = deposited + interest
        
        if amount is None:
            embed = discord.Embed(
                title="💰 Withdraw Funds",
                description="Take your money out of the bank",
                color=0x3498DB
            )
            embed.add_field(
                name="💵 Available",
                value=f"`{total_available:,}` <:mora:1437958309255577681>",
                inline=True
            )
            embed.add_field(
                name="📈 Interest",
                value=f"`{interest:,}` <:mora:1437958309255577681>",
                inline=True
            )
            return await send_embed(ctx, embed)
        
        # Parse amount
        if amount.lower() == 'all':
            withdraw_amount = total_available
        else:
            try:
                withdraw_amount = int(amount.replace(',', ''))
            except:
                return await ctx.send("❌ Invalid amount! Use a number or `all`")
        
        if withdraw_amount <= 0:
            return await ctx.send("❌ Withdrawal amount must be positive!")
        
        if withdraw_amount > total_available:
            return await ctx.send(f"❌ You only have `{total_available:,}` <:mora:1437958309255577681> available!")
        
        # Calculate what to deduct from deposit vs interest
        interest_withdrawn = min(withdraw_amount, interest)
        deposit_withdrawn = withdraw_amount - interest_withdrawn
        
        new_interest = interest - interest_withdrawn
        new_deposit = deposited - deposit_withdrawn
        
        # Update database
        async with aiosqlite.connect(DB_PATH) as db:
            if new_deposit <= 0 and new_interest <= 0:
                await db.execute("DELETE FROM user_bank_deposits WHERE user_id = ?", (ctx.author.id,))
            else:
                await db.execute(
                    "UPDATE user_bank_deposits SET deposited_amount = ?, interest_earned = ? WHERE user_id = ?",
                    (new_deposit, new_interest, ctx.author.id)
                )
            await db.commit()
        
        # Give money to user
        user_data = await get_user_data(ctx.author.id)
        await update_user_data(ctx.author.id, mora=user_data['mora'] + withdraw_amount)
        
        # Log transaction
        await log_transaction(ctx.author.id, "withdraw", withdraw_amount, f"Remaining in bank: {new_deposit:,}")
        
        embed = discord.Embed(
            title="✅ Withdrawal Successful!",
            description=f"You withdrew `{withdraw_amount:,}` <:mora:1437958309255577681> from the bank.",
            color=0x2ECC71
        )
        if new_deposit > 0 or new_interest > 0:
            embed.add_field(
                name="💰 Remaining Balance",
                value=f"`{new_deposit + new_interest:,}` <:mora:1437958309255577681>",
                inline=False
            )
        await send_embed(ctx, embed)
    
    @commands.command(name="loan")
    async def take_loan(self, ctx, amount: str = None):
        """Take out a loan from the bank
        
        Usage: gloan <amount>
        Example: gloan 100000
        
        Requirements:
        - No active loan
        
        Free Users:
        - Max 500k Mora per loan
        - 1 loan per day
        
        Premium Users:
        - Max 1M Mora per loan
        - 3 loans per day
        
        Warning: You have 12 hours to repay. After that, a 20% penalty is added!
        """
        if not await require_enrollment(ctx):
            return
        await ensure_user_db(ctx.author.id)
        
        if amount is None:
            # Check premium status
            premium_cog = self.bot.get_cog("Premium")
            is_premium = premium_cog and await premium_cog.is_premium(ctx.author.id)
            
            # Check golden card
            card_tier = await self.get_user_card_tier(ctx.author.id)
            has_golden_card = card_tier == 2
            
            if is_premium:
                max_loan = "1,000,000"
                daily_loans = "3"
                tier = "Premium"
            elif has_golden_card:
                max_loan = "750,000"
                daily_loans = "2"
                tier = "<a:gold:1457409675963138205> Golden Card"
            else:
                max_loan = "500,000"
                daily_loans = "1"
                tier = "Free"
            
            # Show loan info
            embed = discord.Embed(
                title="🏦 Bank Loans",
                description=(
                    "Take out a loan from the community bank!\n\n"
                    f"**Your Tier: {tier}**\n"
                    f"<a:arrow:1437968863026479258> Max loan: **{max_loan}** Mora\n"
                    f"<a:arrow:1437968863026479258> Loans per day: **{daily_loans}**\n"
                ),
                color=0x3498DB
            )
            
            if has_golden_card:
                embed.description += "\n<a:arrow:1437968863026479258> **10% cashback on all game losses** <a:gold:1457409675963138205>\n"
            
            embed.description += (
                "\n**Requirements:**\n"
                "<a:arrow:1437968863026479258> No active loan\n\n"
                "**Terms:**\n"
                "<a:arrow:1437968863026479258> Repay within 12 hours\n"
                "<a:arrow:1437968863026479258> After 12 hours: +20% penalty\n"
                "<a:arrow:1437968863026479258> Use `grepay <amount>` to pay back"
            )
            embed.add_field(
                name="Usage",
                value="`gloan <amount>`\nExample: `gloan 100000`",
                inline=False
            )
            if not is_premium:
                embed.set_footer(text="Premium users get 1M max loans & 3 loans per day!")
            return await send_embed(ctx, embed)
        
        # Check if user is banned from loans
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT loan_ban_until FROM user_loans WHERE user_id = ?",
                (ctx.author.id,)
            )
            ban_row = await cursor.fetchone()
            
            if ban_row and ban_row[0]:
                ban_until = datetime.fromisoformat(ban_row[0])
                if datetime.now() < ban_until:
                    time_left = ban_until - datetime.now()
                    days = time_left.days
                    hours = time_left.seconds // 3600
                    
                    embed = discord.Embed(
                        title="🚫 Loan Suspended",
                        description=f"You are suspended from taking loans due to missing the 24h deadline.",
                        color=0xE74C3C
                    )
                    embed.add_field(
                        name="⏰ Time Remaining",
                        value=f"{days} days, {hours} hours",
                        inline=False
                    )
                    embed.set_footer(text="Suspension will be lifted automatically")
                    return await send_embed(ctx, embed)
        
        # Check for active loan
        loan_data = await self.get_user_loan(ctx.author.id)
        if loan_data and loan_data[0] > 0:
            loan_amount, penalty_amount, due_date_str, penalty_applied, _ = loan_data
            total_owed = loan_amount + penalty_amount
            
            due_date = datetime.fromisoformat(due_date_str)
            time_left = due_date - datetime.now()
            
            if time_left.total_seconds() > 0 and not penalty_applied:
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                time_str = f"{hours}h {minutes}m"
            else:
                time_str = "OVERDUE"
            
            embed = discord.Embed(
                title="❌ Active Loan",
                description=f"You already have an active loan!",
                color=0xE74C3C
            )
            embed.add_field(
                name="💰 Amount Owed",
                value=f"`{total_owed:,}` <:mora:1437958309255577681>",
                inline=True
            )
            embed.add_field(
                name="⏰ Time Left",
                value=time_str,
                inline=True
            )
            if penalty_applied:
                embed.add_field(
                    name="⚠️ Penalty Applied",
                    value=f"+`{penalty_amount:,}` <:mora:1437958309255577681> (20%)",
                    inline=False
                )
            return await send_embed(ctx, embed)
        
        # Check premium status
        premium_cog = self.bot.get_cog("Premium")
        is_premium = premium_cog and await premium_cog.is_premium(ctx.author.id)
        
        # Check golden card
        card_tier = await self.get_user_card_tier(ctx.author.id)
        has_golden_card = card_tier == 2
        
        if is_premium:
            max_loan_amount = 1_000_000
            daily_loan_limit = 3
        elif has_golden_card:
            max_loan_amount = 750_000
            daily_loan_limit = 2
        else:
            max_loan_amount = 500_000
            daily_loan_limit = 1
        
        # Check daily loan count
        async with aiosqlite.connect(DB_PATH) as db:
            # Get current daily loan count
            cursor = await db.execute(
                "SELECT daily_loan_count, loan_count_date FROM user_loans WHERE user_id = ?",
                (ctx.author.id,)
            )
            count_row = await cursor.fetchone()
            
            today = datetime.now().date()
            loans_today = 0
            
            if count_row and count_row[1]:
                count_date = datetime.fromisoformat(count_row[1]).date()
                if count_date == today:
                    loans_today = count_row[0] or 0
            
            # Check if limit reached
            if loans_today >= daily_loan_limit:
                tier_name = "Premium" if is_premium else "Free"
                embed = discord.Embed(
                    title="❌ Daily Loan Limit Reached",
                    description=f"You've taken **{loans_today}/{daily_loan_limit}** loans today ({tier_name} tier)",
                    color=0xE74C3C
                )
                if not is_premium:
                    embed.add_field(
                        name="💎 Upgrade to Premium!",
                        value="Premium users can take **3 loans per day** with **1M max**!\nUse `gpremium` to learn more.",
                        inline=False
                    )
                else:
                    embed.set_footer(text="Limit resets at midnight")
                return await send_embed(ctx, embed)
        
        # Parse amount
        try:
            loan_amount = int(amount.replace(',', ''))
        except:
            return await ctx.send("❌ Invalid amount! Use a number like `100000`")
        
        if loan_amount <= 0:
            return await ctx.send("❌ Loan amount must be positive!")
        
        if loan_amount > max_loan_amount:
            tier_text = "Premium" if is_premium else "Free"
            embed = discord.Embed(
                title="❌ Loan Limit Exceeded",
                description=f"Maximum loan for {tier_text} tier is `{max_loan_amount:,}` <:mora:1437958309255577681>",
                color=0xE74C3C
            )
            if not is_premium:
                embed.add_field(
                    name="💎 Upgrade to Premium!",
                    value="Premium users get:\\n<a:arrow:1437968863026479258> **1M max loans**\\n<a:arrow:1437968863026479258> **3 loans per day**",
                    inline=False
                )
            return await send_embed(ctx, embed)
        
        # Check bank has enough
        bank_balance = await self.get_bank_balance()
        if bank_balance < loan_amount:
            embed = discord.Embed(
                title="❌ Insufficient Bank Funds",
                description=f"The bank only has `{bank_balance:,}` <:mora:1437958309255577681> available.",
                color=0xE74C3C
            )
            return await send_embed(ctx, embed)
        
        # Calculate 5% interest for depositors
        interest_amount = int(loan_amount * 0.05)
        
        # Give loan
        now = datetime.now()
        due_date = now + timedelta(hours=12)
        
        async with aiosqlite.connect(DB_PATH) as db:
            # Get current daily loan count
            cursor = await db.execute(
                "SELECT daily_loan_count, loan_count_date FROM user_loans WHERE user_id = ?",
                (ctx.author.id,)
            )
            count_row = await cursor.fetchone()
            
            today = now.date()
            if count_row and count_row[1]:
                count_date = datetime.fromisoformat(count_row[1]).date()
                if count_date == today:
                    new_count = (count_row[0] or 0) + 1
                else:
                    new_count = 1  # Reset count for new day
            else:
                new_count = 1
            
            # Update user loan with daily count
            await db.execute(
                """INSERT INTO user_loans (user_id, loan_amount, penalty_amount, due_date, penalty_applied, last_loan_date, daily_loan_count, loan_count_date)
                   VALUES (?, ?, 0, ?, 0, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                   loan_amount = ?, penalty_amount = 0, due_date = ?, penalty_applied = 0, last_loan_date = ?, daily_loan_count = ?, loan_count_date = ?""",
                (ctx.author.id, loan_amount, due_date.isoformat(), now.isoformat(), new_count, now.isoformat(),
                 loan_amount, due_date.isoformat(), now.isoformat(), new_count, now.isoformat())
            )
            
            # Distribute 5% interest to depositors
            # Get total deposits
            cursor = await db.execute("SELECT SUM(deposited_amount) FROM user_bank_deposits")
            total_row = await cursor.fetchone()
            total_deposits = total_row[0] if total_row and total_row[0] else 0
            
            if total_deposits > 0:
                # Get all depositors
                cursor = await db.execute("SELECT user_id, deposited_amount FROM user_bank_deposits WHERE deposited_amount > 0")
                depositors = await cursor.fetchall()
                
                # Distribute interest proportionally
                for depositor_id, deposit_amount in depositors:
                    # Calculate this user's share of the interest
                    share = (deposit_amount / total_deposits) * interest_amount
                    share = int(share)
                    
                    await db.execute(
                        "UPDATE user_bank_deposits SET interest_earned = interest_earned + ? WHERE user_id = ?",
                        (share, depositor_id)
                    )
            
            # Update bank (deduct loan + interest paid to depositors)
            await db.execute(
                """UPDATE global_bank 
                   SET balance = balance - ? - ?, 
                       total_loans_given = total_loans_given + ?
                   WHERE id = 1""",
                (loan_amount, interest_amount, loan_amount)
            )
            
            await db.commit()
        
        # Give user the money
        user_data = await get_user_data(ctx.author.id)
        await update_user_data(ctx.author.id, mora=user_data['mora'] + loan_amount)
        
        # Calculate total repayment amount
        total_repay = loan_amount + interest_amount
        
        # Log transaction
        await log_transaction(
            ctx.author.id,
            "loan_taken",
            loan_amount,
            f"Interest: {interest_amount:,}, Total due: {total_repay:,}"
        )
        
        embed = discord.Embed(
            title="✅ Loan Approved!",
            description=f"You received `{loan_amount:,}` <:mora:1437958309255577681> from the bank.",
            color=0x2ECC71
        )
        embed.add_field(
            name="💰 Amount to Repay",
            value=f"`{loan_amount:,}` <:mora:1437958309255577681>",
            inline=True
        )
        embed.add_field(
            name="Due in",
            value="12 hours",
            inline=True
        )
        embed.add_field(
            name="Interest Paid",
            value=f"`{interest_amount:,}` <:mora:1437958309255577681> (5%) to depositors",
            inline=False
        )
        embed.add_field(
            name="⚠️ Warning",
            value="After 12 hours, a **20% penalty** will be added to your loan!",
            inline=False
        )
        await send_embed(ctx, embed)
    
    @commands.command(name="repay")
    async def repay_loan(self, ctx, amount: str = None):
        """Repay your loan
        
        Usage: grepay <amount> or grepay all
        Example: grepay 50000
        """
        if not await require_enrollment(ctx):
            return
        await ensure_user_db(ctx.author.id)
        
        # Check for penalty first
        await self.check_and_apply_penalty(ctx.author.id)
        
        # Get loan info
        loan_data = await self.get_user_loan(ctx.author.id)
        if not loan_data or loan_data[0] == 0:
            return await ctx.send("❌ You don't have an active loan!")
        
        loan_amount, penalty_amount, _, penalty_applied, _ = loan_data
        total_owed = loan_amount + penalty_amount
        
        if amount is None:
            embed = discord.Embed(
                title="💳 Loan Repayment",
                description="Pay back your loan to the bank",
                color=0x3498DB
            )
            embed.add_field(
                name="💰 Total Owed",
                value=f"`{total_owed:,}` <:mora:1437958309255577681>",
                inline=True
            )
            if penalty_applied:
                embed.add_field(
                    name="⚠️ Penalty",
                    value=f"`{penalty_amount:,}` <:mora:1437958309255577681>",
                    inline=True
                )
            embed.add_field(
                name="Usage",
                value="`grepay <amount>` or `grepay all`",
                inline=False
            )
            return await send_embed(ctx, embed)
        
        # Parse amount
        user_data = await get_user_data(ctx.author.id)
        user_mora = user_data['mora']
        
        # Add 1% tax to total owed
        tax_amount = int(loan_amount * 0.01)
        total_with_tax = total_owed + tax_amount
        
        if amount.lower() == 'all':
            repay_amount = min(user_mora, total_with_tax)
        else:
            try:
                repay_amount = int(amount.replace(',', ''))
            except:
                return await ctx.send("❌ Invalid amount! Use a number or `all`")
        
        if repay_amount <= 0:
            return await ctx.send("❌ Repayment amount must be positive!")
        
        if repay_amount > user_mora:
            return await ctx.send(f"❌ You only have `{user_mora:,}` <:mora:1437958309255577681>!")
        
        # Can't repay more than owed (including tax)
        if repay_amount > total_with_tax:
            repay_amount = total_with_tax
        
        # Calculate how much goes to tax, penalty, and loan
        remaining = repay_amount
        
        # First pay tax
        tax_paid = min(remaining, tax_amount)
        remaining -= tax_paid
        
        # Then pay penalty
        penalty_paid = min(remaining, penalty_amount)
        remaining -= penalty_paid
        
        # Rest goes to loan
        loan_paid = remaining
        
        new_penalty = penalty_amount - penalty_paid
        new_loan = loan_amount - loan_paid
        new_tax = tax_amount - tax_paid
        
        # Update database
        async with aiosqlite.connect(DB_PATH) as db:
            if new_loan <= 0 and new_penalty <= 0:
                # Loan fully repaid - don't delete row, keep daily count
                await db.execute(
                    "UPDATE user_loans SET loan_amount = 0, penalty_amount = 0, penalty_applied = 0 WHERE user_id = ?",
                    (ctx.author.id,)
                )
            else:
                await db.execute(
                    "UPDATE user_loans SET loan_amount = ?, penalty_amount = ? WHERE user_id = ?",
                    (new_loan, new_penalty, ctx.author.id)
                )
            
            # Add money back to bank
            await db.execute(
                "UPDATE global_bank SET balance = balance + ? WHERE id = 1",
                (repay_amount,)
            )
            
            await db.commit()
        
        # Take money from user
        await update_user_data(ctx.author.id, mora=user_mora - repay_amount)
        
        # Log transaction
        await log_transaction(
            ctx.author.id,
            "loan_repaid",
            repay_amount,
            f"Tax: {tax_paid:,}, Penalty: {penalty_paid:,}, Principal: {loan_paid:,}, Remaining: {new_loan + new_penalty:,}"
        )
        
        if new_loan <= 0 and new_penalty <= 0:
            embed = discord.Embed(
                title="✅ Loan Fully Repaid!",
                description=f"You paid `{repay_amount:,}` <:mora:1437958309255577681> and cleared your loan!",
                color=0x2ECC71
            )
            if tax_paid > 0:
                embed.add_field(
                    name="💵 Tax Paid",
                    value=f"`{tax_paid:,}` <:mora:1437958309255577681> (1% processing fee)",
                    inline=False
                )
        else:
            embed = discord.Embed(
                title="💳 Loan Payment Made",
                description=f"You paid `{repay_amount:,}` <:mora:1437958309255577681>",
                color=0x3498DB
            )
            remaining = new_loan + new_penalty + new_tax
            embed.add_field(
                name="💰 Remaining Balance",
                value=f"`{remaining:,}` <:mora:1437958309255577681>",
                inline=False
            )
            if new_tax > 0:
                embed.add_field(
                    name="💵 Tax Remaining",
                    value=f"`{new_tax:,}` <:mora:1437958309255577681> (1%)",
                    inline=True
                )
            if new_penalty > 0:
                embed.add_field(
                    name="⚠️ Penalty Remaining",
                    value=f"`{new_penalty:,}` <:mora:1437958309255577681>",
                    inline=False
                )
        
        await send_embed(ctx, embed)
    
    @commands.command(name="myloan", aliases=["loanstatus"])
    async def my_loan(self, ctx):
        """Check your current loan status"""
        if not await require_enrollment(ctx):
            return
        await ensure_user_db(ctx.author.id)
        
        # Check for penalty
        penalty_just_applied = await self.check_and_apply_penalty(ctx.author.id)
        
        loan_data = await self.get_user_loan(ctx.author.id)
        if not loan_data or loan_data[0] == 0:
            embed = discord.Embed(
                title="🏦 No Active Loan",
                description="You don't have any active loans.\n\nUse `gloan <amount>` to take out a loan!",
                color=0x95A5A6
            )
            return await send_embed(ctx, embed)
        
        loan_amount, penalty_amount, due_date_str, penalty_applied, last_loan_date = loan_data
        total_owed = loan_amount + penalty_amount
        
        due_date = datetime.fromisoformat(due_date_str)
        time_left = due_date - datetime.now()
        
        if time_left.total_seconds() > 0 and not penalty_applied:
            hours = int(time_left.total_seconds() // 3600)
            minutes = int((time_left.total_seconds() % 3600) // 60)
            time_str = f"{hours}h {minutes}m"
            color = 0x3498DB
            status = "⏰ Active"
        else:
            time_str = "OVERDUE"
            color = 0xE74C3C
            status = "⚠️ Overdue"
        
        embed = discord.Embed(
            title="🏦 Your Loan Status",
            description=status,
            color=color
        )
        embed.add_field(
            name="💰 Original Loan",
            value=f"`{loan_amount:,}` <:mora:1437958309255577681>",
            inline=True
        )
        embed.add_field(
            name="⏰ Time Left",
            value=time_str,
            inline=True
        )
        
        if penalty_applied:
            embed.add_field(
                name="⚠️ Penalty Applied",
                value=f"+`{penalty_amount:,}` <:mora:1437958309255577681> (20%)",
                inline=False
            )
            if penalty_just_applied:
                embed.add_field(
                    name="🚨 Just Applied",
                    value="Your loan is now overdue! Penalty has been added.",
                    inline=False
                )
        
        embed.add_field(
            name="📋 Total Owed",
            value=f"`{total_owed:,}` <:mora:1437958309255577681>",
            inline=False
        )
        
        await send_embed(ctx, embed)
    
    @commands.command(name="setbank")
    async def set_bank_balance(self, ctx, action: str = None, amount: str = None):
        """Owner only - Control the global bank balance
        
        Usage: 
        gsetbank set <amount> - Set bank balance to exact amount
        gsetbank add <amount> - Add to bank balance
        gsetbank remove <amount> - Remove from bank balance
        
        Example: gsetbank set 5000000
        """
        # Owner only check
        if ctx.author.id != 873464016217968640:
            return await ctx.send("nice try bozo.")
        
        if action is None or amount is None:
            embed = discord.Embed(
                title="🏦 Bank Control",
                description="Control the global bank balance",
                color=0x3498DB
            )
            embed.add_field(
                name="Commands",
                value=(
                    "`gsetbank set <amount>` - Set exact balance\n"
                    "`gsetbank add <amount>` - Add to balance\n"
                    "`gsetbank remove <amount>` - Remove from balance"
                ),
                inline=False
            )
            
            # Show current balance
            current_balance = await self.get_bank_balance()
            embed.add_field(
                name="Current Balance",
                value=f"`{current_balance:,}` <:mora:1437958309255577681>",
                inline=False
            )
            return await send_embed(ctx, embed)
        
        # Parse amount
        try:
            change_amount = int(amount.replace(',', ''))
        except:
            return await ctx.send("❌ Invalid amount! Use a number like `1000000`")
        
        if change_amount < 0:
            return await ctx.send("❌ Amount must be positive!")
        
        current_balance = await self.get_bank_balance()
        
        async with aiosqlite.connect(DB_PATH) as db:
            if action.lower() in ['set', 's']:
                # Set exact balance
                await db.execute(
                    "UPDATE global_bank SET balance = ? WHERE id = 1",
                    (change_amount,)
                )
                new_balance = change_amount
                action_text = "set to"
                
            elif action.lower() in ['add', 'a', '+']:
                # Add to balance
                await db.execute(
                    "UPDATE global_bank SET balance = balance + ? WHERE id = 1",
                    (change_amount,)
                )
                new_balance = current_balance + change_amount
                action_text = "increased by"
                
            elif action.lower() in ['remove', 'r', '-', 'subtract']:
                # Remove from balance
                if change_amount > current_balance:
                    return await ctx.send(f"❌ Cannot remove `{change_amount:,}` <:mora:1437958309255577681>! Bank only has `{current_balance:,}` <:mora:1437958309255577681>")
                
                await db.execute(
                    "UPDATE global_bank SET balance = balance - ? WHERE id = 1",
                    (change_amount,)
                )
                new_balance = current_balance - change_amount
                action_text = "decreased by"
                
            else:
                return await ctx.send("❌ Invalid action! Use `set`, `add`, or `remove`")
            
            await db.commit()
        
        embed = discord.Embed(
            title="✅ Bank Balance Updated",
            description=f"Bank balance {action_text} `{change_amount:,}` <:mora:1437958309255577681>",
            color=0x2ECC71
        )
        embed.add_field(
            name="Previous Balance",
            value=f"`{current_balance:,}` <:mora:1437958309255577681>",
            inline=True
        )
        embed.add_field(
            name="New Balance",
            value=f"`{new_balance:,}` <:mora:1437958309255577681>",
            inline=True
        )
        await send_embed(ctx, embed)
    
    @commands.command(name="pay")
    async def pay_user(self, ctx, member: discord.Member = None, amount: str = None):
        """Send Mora to another user
        
        Usage: gpay @user <amount>
        Example: gpay @Friend 1000
        """
        if not await require_enrollment(ctx):
            return
        
        if member is None or amount is None:
            embed = discord.Embed(
                title="💸 Pay User",
                description="Transfer Mora to another user",
                color=0x3498DB
            )
            embed.add_field(
                name="Usage",
                value="`gpay @user <amount>`",
                inline=False
            )
            embed.add_field(
                name="Example",
                value="`gpay @Friend 5000`",
                inline=False
            )
            return await send_embed(ctx, embed)
        
        # Can't pay yourself
        if member.id == ctx.author.id:
            return await ctx.send("❌ You can't pay yourself!")
        
        # Can't pay bots
        if member.bot:
            return await ctx.send("❌ You can't pay bots!")
        
        # Parse amount
        try:
            pay_amount = int(amount.replace(',', ''))
        except:
            return await ctx.send("❌ Invalid amount! Use a number like `1000`")
        
        if pay_amount <= 0:
            return await ctx.send("❌ Amount must be positive!")
        
        # Get sender's balance
        sender_data = await get_user_data(ctx.author.id)
        sender_balance = sender_data.get('mora', 0)
        
        if pay_amount > sender_balance:
            return await ctx.send(f"❌ You don't have enough Mora! You have `{sender_balance:,}` <:mora:1437958309255577681>")
        
        # Ensure receiver is in database
        await ensure_user_db(member.id)
        
        # Transfer money
        await update_user_data(ctx.author.id, mora=sender_balance - pay_amount)
        
        receiver_data = await get_user_data(member.id)
        receiver_balance = receiver_data.get('mora', 0)
        await update_user_data(member.id, mora=receiver_balance + pay_amount)
        
        # Success message
        embed = discord.Embed(
            title="💸 Payment Sent",
            description=f"{ctx.author.mention} paid {member.mention}",
            color=0x2ECC71
        )
        embed.add_field(
            name="Amount",
            value=f"`{pay_amount:,}` <:mora:1437958309255577681>",
            inline=False
        )
        embed.add_field(
            name="Your Balance",
            value=f"`{sender_balance - pay_amount:,}` <:mora:1437958309255577681>",
            inline=True
        )
        embed.add_field(
            name=f"{member.display_name}'s Balance",
            value=f"`{receiver_balance + pay_amount:,}` <:mora:1437958309255577681>",
            inline=True
        )
        await send_embed(ctx, embed)
    
    @commands.command(name="loanplayer", aliases=["lendmoney"])
    async def loan_player(self, ctx, member: discord.Member = None, amount: str = None):
        """Loan money to another player with 5% interest
        
        Usage: gloanplayer @user <amount>
        - They have 12 hours to repay
        - After 12h: +20% penalty
        - After 24h: +20% MORE penalty + auto-deduct + ban
        - You get 5% interest profit
        """
        if not await require_enrollment(ctx):
            return
        
        if member is None or amount is None:
            embed = discord.Embed(
                title="💸 Player-to-Player Loans",
                description="Loan money to other players and earn 5% interest!",
                color=0x3498DB
            )
            embed.add_field(
                name="Usage",
                value="`gloanplayer @user <amount>`",
                inline=False
            )
            embed.add_field(
                name="Terms",
                value=(
                    "• 12h repayment deadline\n"
                    "• 5% interest profit for you\n"
                    "• Same penalty system as bank loans\n"
                    "• They must `grepayplayer @you <amount>`"
                ),
                inline=False
            )
            return await send_embed(ctx, embed)
        
        # Can't loan yourself
        if member.id == ctx.author.id:
            return await ctx.send("❌ You can't loan yourself!")
        
        # Can't loan bots
        if member.bot:
            return await ctx.send("❌ You can't loan bots!")
        
        # Parse amount
        try:
            loan_amt = int(amount.replace(',', ''))
        except:
            return await ctx.send("❌ Invalid amount!")
        
        if loan_amt <= 0:
            return await ctx.send("❌ Amount must be positive!")
        
        # Check if lender has enough
        lender_data = await get_user_data(ctx.author.id)
        lender_balance = lender_data.get('mora', 0)
        
        if loan_amt > lender_balance:
            return await ctx.send(f"❌ You only have `{lender_balance:,}` <:mora:1437958309255577681>!")
        
        # Check if borrower already has a P2P loan
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id FROM p2p_loans WHERE borrower_id = ? AND status = 'active'",
                (member.id,)
            )
            if await cursor.fetchone():
                return await ctx.send(f"❌ {member.display_name} already has an active P2P loan!")
        
        # Send loan request with confirmation
        interest = int(loan_amt * 0.05)
        total_repay = loan_amt + interest
        
        embed = discord.Embed(
            title="💸 Loan Request",
            description=f"{ctx.author.mention} wants to loan you `{loan_amt:,}` <:mora:1437958309255577681>",
            color=0x3498DB
        )
        embed.add_field(
            name="Repayment Amount",
            value=f"`{total_repay:,}` <:mora:1437958309255577681> (+5% interest)",
            inline=False
        )
        embed.add_field(
            name="Due in",
            value="12 hours",
            inline=True
        )
        embed.set_footer(text="Accept or decline within 60 seconds")
        
        view = LoanConfirmationView(ctx.author, member, loan_amt)
        msg = await ctx.send(member.mention, embed=embed, view=view)
        view.message = msg
    
    @commands.command(name="repayplayer", aliases=["paybackplayer"])
    async def repay_player(self, ctx, member: discord.Member = None, amount: str = None):
        """Repay a P2P loan
        
        Usage: grepayplayer @lender <amount>
        """
        if not await require_enrollment(ctx):
            return
        
        if member is None:
            # Show active P2P loans
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT lender_id, amount, interest_rate, due_date FROM p2p_loans WHERE borrower_id = ? AND status = 'active'",
                    (ctx.author.id,)
                )
                loans = await cursor.fetchall()
            
            if not loans:
                return await ctx.send("You don't have any active P2P loans!")
            
            embed = discord.Embed(
                title="Your Active P2P Loans",
                color=0xE74C3C
            )
            
            for lender_id, amt, rate, due in loans:
                lender = ctx.guild.get_member(lender_id)
                lender_name = lender.display_name if lender else f"User#{lender_id}"
                interest = int(amt * (rate / 100))
                total = amt + interest
                
                due_date = datetime.fromisoformat(due)
                time_left = due_date - datetime.now()
                
                if time_left.total_seconds() > 0:
                    hours = int(time_left.total_seconds() // 3600)
                    minutes = int((time_left.total_seconds() % 3600) // 60)
                    time_str = f"{hours}h {minutes}m"
                else:
                    time_str = "OVERDUE"
                
                embed.add_field(
                    name=f"Loan from {lender_name}",
                    value=f"Amount: `{total:,}` <:mora:1437958309255577681>\nTime left: {time_str}",
                    inline=False
                )
            
            embed.set_footer(text="Use grepayplayer @lender <amount> to repay")
            return await send_embed(ctx, embed)
        
        if amount is None:
            return await ctx.send("Usage: `grepayplayer @lender <amount>`")
        
        # Get loan details
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, amount, interest_rate FROM p2p_loans WHERE lender_id = ? AND borrower_id = ? AND status = 'active'",
                (member.id, ctx.author.id)
            )
            loan = await cursor.fetchone()
        
        if not loan:
            return await ctx.send(f"❌ You don't have an active loan from {member.display_name}!")
        
        loan_id, loan_amt, interest_rate = loan
        interest = int(loan_amt * (interest_rate / 100))
        total_owed = loan_amt + interest
        
        # Parse repayment amount
        borrower_data = await get_user_data(ctx.author.id)
        borrower_balance = borrower_data.get('mora', 0)
        
        if amount.lower() == 'all':
            repay_amt = min(borrower_balance, total_owed)
        else:
            try:
                repay_amt = int(amount.replace(',', ''))
            except:
                return await ctx.send("❌ Invalid amount!")
        
        if repay_amt <= 0:
            return await ctx.send("❌ Amount must be positive!")
        
        if repay_amt > borrower_balance:
            return await ctx.send(f"❌ You only have `{borrower_balance:,}` <:mora:1437958309255577681>!")
        
        if repay_amt > total_owed:
            repay_amt = total_owed
        
        # Transfer money
        await update_user_data(ctx.author.id, mora=borrower_balance - repay_amt)
        
        lender_data = await get_user_data(member.id)
        lender_balance = lender_data.get('mora', 0)
        await update_user_data(member.id, mora=lender_balance + repay_amt)
        
        # Update loan status
        async with aiosqlite.connect(DB_PATH) as db:
            if repay_amt >= total_owed:
                # Fully repaid
                await db.execute(
                    "UPDATE p2p_loans SET status = 'repaid' WHERE id = ?",
                    (loan_id,)
                )
            else:
                # Partial payment - reduce principal
                new_principal = loan_amt - repay_amt
                await db.execute(
                    "UPDATE p2p_loans SET amount = ? WHERE id = ?",
                    (new_principal, loan_id)
                )
            await db.commit()
        
        embed = discord.Embed(
            title="✅ P2P Loan Payment",
            description=f"You paid {member.mention} `{repay_amt:,}` <:mora:1437958309255577681>",
            color=0x2ECC71
        )
        
        if repay_amt >= total_owed:
            embed.add_field(
                name="Status",
                value="Loan fully repaid!",
                inline=False
            )
        else:
            remaining = total_owed - repay_amt
            embed.add_field(
                name="Remaining",
                value=f"`{remaining:,}` <:mora:1437958309255577681>",
                inline=False
            )
        
        await send_embed(ctx, embed)

    @commands.command(name="bankcard", aliases=["card", "upgradecard"])
    async def bank_card(self, ctx, action: str = None):
        """Buy or upgrade your bank card to increase deposit limits
        
        Card Tiers:
        - Platinum 💳: 50M limit (10M mora)
        - Gold 🌟: 150M limit (50M mora)
        
        Usage: gbankcard [buy/upgrade]
        """
        if not await require_enrollment(ctx):
            return
        await ensure_user_db(ctx.author.id)
        
        # Card information
        card_info = {
            0: {"name": "No Card", "limit": 5_000_000, "icon": "🏦", "cost": 0, "next": 1},
            1: {"name": "Platinum", "limit": 50_000_000, "icon": "<:platinum:1457410519534403635>", "cost": 10_000_000, "next": 2},
            2: {"name": "Gold", "limit": 150_000_000, "icon": "<a:gold:1457409675963138205>", "cost": 50_000_000, "next": None}
        }
        
        # Get current card tier
        current_tier = await self.get_user_card_tier(ctx.author.id)
        
        if action is None:
            # Show card info (default behavior - show how to buy)
            current_card = card_info[current_tier]
            
            embed = discord.Embed(
                title="🏦 Bank Card System",
                description="Upgrade your bank card to increase your deposit limit!",
                color=0xF39C12
            )
            
            embed.add_field(
                name="💳 Current Card",
                value=f"{current_card['icon']} **{current_card['name']}**\nLimit: `{current_card['limit']:,}` <:mora:1437958309255577681>",
                inline=False
            )
            
            # Show all card tiers
            tiers_text = []
            for tier, info in card_info.items():
                if tier == 0:
                    continue
                status = "✅ Owned" if tier <= current_tier else f"{info['cost']:,} mora"
                tiers_text.append(
                    f"{info['icon']} **{info['name']}**\n"
                    f"Limit: `{info['limit']:,}` | Cost: {status}"
                )
            
            embed.add_field(
                name="📋 Available Cards",
                value="\n\n".join(tiers_text),
                inline=False
            )
            
            # Add instructions
            if current_tier < 2:
                next_card = card_info[current_tier + 1]
                embed.add_field(
                    name="💡 How to Buy",
                    value=f"Use `gbankcard buy` to purchase {next_card['icon']} **{next_card['name']}** for `{next_card['cost']:,}` <:mora:1437958309255577681>",
                    inline=False
                )
            else:
                embed.set_footer(text="You own the maximum tier card!")
            
            return await send_embed(ctx, embed)
        
        elif action.lower() in ["buy", "upgrade"]:
            # Buy/upgrade card
            if current_tier >= 2:
                return await ctx.send("✅ You already have the maximum tier card (Gold <a:gold:1457409675963138205>)!")
            
            next_tier = current_tier + 1
            next_card = card_info[next_tier]
            
            # Check if trying to buy gold without platinum
            if next_tier == 2 and current_tier == 0:
                return await ctx.send("❌ You must buy <:platinum:1457410519534403635> **Platinum** card first before upgrading to <a:gold:1457409675963138205> **Gold**!")
            
            cost = next_card['cost']
            
            # Check if user has enough mora
            user_data = await get_user_data(ctx.author.id)
            user_mora = user_data.get('mora', 0)
            
            if user_mora < cost:
                embed = discord.Embed(
                    title="❌ Insufficient Funds",
                    description=f"You need `{cost:,}` <:mora:1437958309255577681> to buy {next_card['icon']} **{next_card['name']}**",
                    color=0xE74C3C
                )
                embed.add_field(
                    name="Your Balance",
                    value=f"`{user_mora:,}` <:mora:1437958309255577681>",
                    inline=True
                )
                embed.add_field(
                    name="Still Need",
                    value=f"`{cost - user_mora:,}` <:mora:1437958309255577681>",
                    inline=True
                )
                return await send_embed(ctx, embed)
            
            # Process purchase
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO bank_cards (user_id, card_tier, purchased_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        card_tier = ?,
                        purchased_at = ?
                """, (ctx.author.id, next_tier, datetime.now().isoformat(), next_tier, datetime.now().isoformat()))
                await db.commit()
            
            # Deduct mora
            await update_user_data(ctx.author.id, mora=user_mora - cost)
            
            # Log transaction
            await log_transaction(ctx.author.id, "bank_card_purchase", -cost, f"Upgraded to {next_card['name']}")
            
            embed = discord.Embed(
                title="✅ Card Upgraded!",
                description=f"You purchased {next_card['icon']} **{next_card['name']}**!",
                color=0x2ECC71
            )
            embed.add_field(
                name="💳 New Deposit Limit",
                value=f"`{next_card['limit']:,}` <:mora:1437958309255577681>",
                inline=True
            )
            embed.add_field(
                name="💰 Cost",
                value=f"`{cost:,}` <:mora:1437958309255577681>",
                inline=True
            )
            embed.add_field(
                name="New Balance",
                value=f"`{user_mora - cost:,}` <:mora:1437958309255577681>",
                inline=True
            )
            
            if next_tier < 2:
                next_next = card_info[next_tier + 1]
                embed.set_footer(text=f"Next tier: {next_next['name']} - {next_next['cost']:,} mora")
            else:
                embed.set_footer(text="You've reached the maximum card tier!")
            
            await send_embed(ctx, embed)
        
        else:
            await ctx.send("Invalid action! Use: `gbankcard` or `gbankcard buy`")


async def setup(bot):
    await bot.add_cog(Bank(bot))
