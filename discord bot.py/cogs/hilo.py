import discord
from discord.ext import commands
import aiosqlite
import random
from config import DB_PATH
from utils.embed import send_embed
from utils.database import require_enrollment

# Card values
CARD_RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
CARD_SUITS = ['♠', '♥', '♦', '♣']
CARD_VALUES = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
}

# Multiplier progression (lowered)
MULTIPLIERS = {
    1: 1.3,
    2: 1.6,
    3: 2.0,
    4: 2.4,
    5: 3.0,
    6: 3.8,
    7: 5.0,
    8: 7.0
}

class HiLoView(discord.ui.View):
    def __init__(self, game_data, cog):
        super().__init__(timeout=120)
        self.game_data = game_data
        self.cog = cog
        self.message = None
    
    async def on_timeout(self):
        """Handle timeout by auto-cashing out"""
        if self.game_data['user_id'] in self.cog.active_games:
            await self.auto_cashout()
    
    async def auto_cashout(self):
        """Auto cash out on timeout"""
        user_id = self.game_data['user_id']
        if user_id not in self.cog.active_games:
            return
        
        game = self.cog.active_games[user_id]
        streak = game['streak']
        multiplier = MULTIPLIERS.get(streak, 10.0)
        winnings = int(game['bet'] * multiplier)
        
        # Update balance
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET mora = mora + ? WHERE user_id = ?", (winnings, user_id))
            
            # Update stats
            await db.execute("""
                INSERT INTO game_stats (user_id, hilo_games, hilo_cashouts, hilo_best_streak)
                VALUES (?, 1, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    hilo_games = hilo_games + 1,
                    hilo_cashouts = hilo_cashouts + 1,
                    hilo_best_streak = MAX(hilo_best_streak, ?)
            """, (user_id, streak, streak))
            
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (user_id,))
            balance = (await cursor.fetchone())[0]
            await db.commit()
        
        profit = winnings - game['bet']
        
        embed = discord.Embed(
            title="⏱️ AUTO CASHED OUT",
            description=(
                f"**Final Card:** {game['current_card']}\n"
                f"**Streak:** {streak} correct guesses\n"
                f"**Multiplier:** {multiplier:.1f}x\n\n"
                f"**Bet:** {game['bet']:,} <:mora:1437958309255577681>\n"
                f"**Won:** {winnings:,} <:mora:1437958309255577681>\n"
                f"**Profit:** {profit:+,} <:mora:1437958309255577681>\n\n"
                f"New Balance: {balance:,} <:mora:1437958309255577681>"
            ),
            color=0xF39C12
        )
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        if self.message:
            await self.message.edit(embed=embed, view=self)
        
        del self.cog.active_games[user_id]
    
    @discord.ui.button(label="Higher", style=discord.ButtonStyle.primary, emoji="🔼")
    async def higher_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game_data['user_id']:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        await self.cog.process_guess(interaction, "higher", self)
    
    @discord.ui.button(label="Lower", style=discord.ButtonStyle.primary, emoji="🔽")
    async def lower_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game_data['user_id']:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        await self.cog.process_guess(interaction, "lower", self)
    
    @discord.ui.button(label="Cash Out", style=discord.ButtonStyle.success)
    async def cashout_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game_data['user_id']:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        await self.cog.cash_out(interaction, self)

class HiLo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}
    
    def draw_card(self):
        """Draw a random card or joker (0.2% chance)"""
        if random.random() < 0.002:  # 0.2% chance
            return "🃏"
        rank = random.choice(CARD_RANKS)
        suit = random.choice(CARD_SUITS)
        return f"{rank}{suit}"
    
    def get_card_value(self, card):
        """Get numeric value of card"""
        if card == "🃏":
            return -1  # Special joker value
        rank = card[:-1]  # Remove suit
        return CARD_VALUES[rank]
    
    @commands.command(name="hilo", aliases=["highlow", "hl"])
    async def hilo(self, ctx, bet: str = None):
        """Play Hi-Lo card game
        
        Usage:
        ghilo <bet>
        ghilo stats
        """
        if bet == "stats":
            return await self.show_stats(ctx)
        
        if not await require_enrollment(ctx):
            return
        
        if ctx.author.id in self.active_games:
            return await ctx.send("❌ You already have an active Hi-Lo game!")
        
        if bet is None:
            embed = discord.Embed(
                title="🎴 Hi-Lo Game",
                description=(
                    "Guess if the next card will be higher or lower!\n\n"
                    "**Usage:** `ghilo <bet>`\n\n"
                    "**How to Play:**\n"
                    "• Guess if next card is higher or lower\n"
                    "• Each correct guess increases your multiplier\n"
                    "• Cash out anytime to keep your winnings\n"
                    "• Wrong guess = lose everything\n\n"
                    "**Multipliers:**\n"
                    "1 streak: 1.5x | 2: 2.0x | 3: 2.5x\n"
                    "4: 3.0x | 5: 4.0x | 6: 5.0x\n"
                    "7: 7.0x | 8+: 10.0x\n\n"
                    "**Special:**\n"
                    "• Joker (0.2%): Instant 50x win!\n"
                    "• Same card: Continue with no penalty\n"
                    "• Aces count as high (14)\n"
                    "• Max 10 streak (auto cash out)"
                ),
                color=0x3498DB
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            return await send_embed(ctx, embed)
        
        try:
            bet_amount = int(bet)
        except ValueError:
            return await ctx.send("❌ Invalid bet amount!")
        
        if bet_amount < 100:
            return await ctx.send("❌ Minimum bet is 100 mora!")
        
        if bet_amount > 100000:
            return await ctx.send("❌ Maximum bet is 100,000 mora!")
        
        # Check balance
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (ctx.author.id,))
            row = await cursor.fetchone()
            
            if not row or row[0] < bet_amount:
                return await ctx.send(f"❌ You don't have enough mora! Balance: {row[0] if row else 0:,} <:mora:1437958309255577681>")
            
            # Deduct bet
            await db.execute("UPDATE users SET mora = mora - ? WHERE user_id = ?", (bet_amount, ctx.author.id))
            await db.commit()
        
        # Start game
        current_card = self.draw_card()
        
        # Handle starting with joker (rare)
        if current_card == "🃏":
            return await self.handle_joker(ctx, bet_amount)
        
        game_data = {
            "user_id": ctx.author.id,
            "bet": bet_amount,
            "current_card": current_card,
            "streak": 0,
            "used_cards": [current_card]
        }
        
        self.active_games[ctx.author.id] = game_data
        
        multiplier = MULTIPLIERS.get(0, 1.0)
        potential = int(bet_amount * MULTIPLIERS.get(1, 1.5))
        
        embed = discord.Embed(
            title="🎴 HI-LO GAME",
            description=(
                f"**Current Card:** {current_card}\n\n"
                f"**Bet:** {bet_amount:,} <:mora:1437958309255577681>\n"
                f"**Next Win:** {potential:,} <:mora:1437958309255577681> (1.5x)\n\n"
                f"Will the next card be **Higher** or **Lower**?"
            ),
            color=0x3498DB
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        view = HiLoView(game_data, self)
        view.message = await send_embed(ctx, embed, view=view)
    
    async def process_guess(self, interaction: discord.Interaction, guess: str, view: HiLoView):
        """Process a higher/lower guess"""
        user_id = interaction.user.id
        
        if user_id not in self.active_games:
            return await interaction.response.send_message("❌ Game not found!", ephemeral=True)
        
        game = self.active_games[user_id]
        previous_card = game['current_card']
        previous_value = self.get_card_value(previous_card)
        
        # Draw new card
        new_card = self.draw_card()
        
        # Handle joker
        if new_card == "🃏":
            return await self.handle_joker_mid_game(interaction, view, previous_card)
        
        new_value = self.get_card_value(new_card)
        
        # Check if same card (push)
        if new_value == previous_value:
            game['current_card'] = new_card
            game['used_cards'].append(new_card)
            
            multiplier = MULTIPLIERS.get(game['streak'] + 1, 10.0)
            potential = int(game['bet'] * multiplier)
            
            embed = discord.Embed(
                title="🎴 SAME CARD - PUSH",
                description=(
                    f"**Current Card:** {new_card}\n\n"
                    f"**Streak:** {game['streak']}\n"
                    f"**Next Win:** {potential:,} <:mora:1437958309255577681> ({multiplier:.1f}x)\n\n"
                    f"Will the next card be **Higher** or **Lower**?"
                ),
                color=0xF39C12
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            
            await interaction.response.edit_message(embed=embed, view=view)
            return
        
        # Check if guess is correct
        correct = (guess == "higher" and new_value > previous_value) or (guess == "lower" and new_value < previous_value)
        
        if correct:
            game['streak'] += 1
            game['current_card'] = new_card
            game['used_cards'].append(new_card)
            
            # Check for max streak (auto cash out)
            if game['streak'] >= 10:
                return await self.force_cashout(interaction, view)
            
            multiplier = MULTIPLIERS.get(game['streak'], 10.0)
            next_multiplier = MULTIPLIERS.get(game['streak'] + 1, 10.0)
            current_win = int(game['bet'] * multiplier)
            next_win = int(game['bet'] * next_multiplier)
            
            embed = discord.Embed(
                title="<a:Trophy:1438199339586424925> CORRECT!",
                description=(
                    f"**Current Card:** {new_card}\n\n"
                    f"**Streak:** {game['streak']}\n"
                    f"**Current Win:** {current_win:,} <:mora:1437958309255577681> ({multiplier:.1f}x)\n"
                    f"**Next Win:** {next_win:,} <:mora:1437958309255577681> ({next_multiplier:.1f}x)\n\n"
                    f"Will the next card be **Higher** or **Lower**?"
                ),
                color=0x2ECC71
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            # Wrong guess - lose
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO game_stats (user_id, hilo_games, hilo_busts, hilo_best_streak)
                    VALUES (?, 1, 1, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        hilo_games = hilo_games + 1,
                        hilo_busts = hilo_busts + 1,
                        hilo_best_streak = MAX(hilo_best_streak, ?)
                """, (user_id, game['streak'], game['streak']))
                await db.commit()
            
            # Check for Hot Streak Card (50% refund on loss)
            from utils.database import has_active_item, consume_active_item, get_user_data, update_user_data
            has_hot = await has_active_item(user_id, "streak")
            hot_refund = 0
            if has_hot > 0:
                hot_refund = int(game['bet'] * 0.5)
                await consume_active_item(user_id, "streak")
                data = await get_user_data(user_id)
                data['mora'] += hot_refund
                await update_user_data(user_id, mora=data['mora'])
            
            # Apply golden card cashback (10%)
            bank_cog = interaction.client.get_cog('Bank')
            cashback = 0
            if bank_cog:
                cashback = await bank_cog.apply_golden_cashback(user_id, game['bet'])
            
            loss_text = f"**Lost:** {game['bet']:,} <:mora:1437958309255577681>"
            if hot_refund > 0:
                loss_text += f"\n+{hot_refund:,} Hot Streak refund"
            if cashback > 0:
                loss_text += f"\n+{cashback:,} cashback <a:gold:1457409675963138205>"
            
            embed = discord.Embed(
                title="❌ WRONG!",
                description=(
                    f"**You guessed:** {guess.title()}\n"
                    f"**Your card:** {previous_card} → **New card:** {new_card}\n\n"
                    f"You were on a **{game['streak']}** streak!\n"
                    f"{loss_text}\n\n"
                    f"Better luck next time!"
                ),
                color=0xE74C3C
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            
            # Disable buttons
            for item in view.children:
                item.disabled = True
            
            await interaction.response.edit_message(embed=embed, view=view)
            del self.active_games[user_id]
    
    async def cash_out(self, interaction: discord.Interaction, view: HiLoView):
        """Cash out current winnings"""
        user_id = interaction.user.id
        
        if user_id not in self.active_games:
            return await interaction.response.send_message("❌ Game not found!", ephemeral=True)
        
        game = self.active_games[user_id]
        
        if game['streak'] == 0:
            return await interaction.response.send_message("❌ You need at least 1 correct guess to cash out!", ephemeral=True)
        
        multiplier = MULTIPLIERS.get(game['streak'], 10.0)
        winnings = int(game['bet'] * multiplier)
        profit = winnings - game['bet']
        
        # Check for Double Down Card (must be activated first)
        from utils.database import has_active_item, consume_active_item, consume_inventory_item
        has_double = await has_active_item(user_id, "double_down")
        double_bonus = 0
        if has_double > 0:
            double_bonus = profit  # Double the profit
            winnings += double_bonus
            await consume_active_item(user_id, "double_down")
            await consume_inventory_item(user_id, "double_down")
        
        # Update balance
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET mora = mora + ? WHERE user_id = ?", (winnings, user_id))
            
            await db.execute("""
                INSERT INTO game_stats (user_id, hilo_games, hilo_cashouts, hilo_best_streak)
                VALUES (?, 1, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    hilo_games = hilo_games + 1,
                    hilo_cashouts = hilo_cashouts + 1,
                    hilo_best_streak = MAX(hilo_best_streak, ?)
            """, (user_id, game['streak'], game['streak']))
            
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (user_id,))
            balance = (await cursor.fetchone())[0]
            await db.commit()
        
        embed = discord.Embed(
            title="✅ CASHED OUT!" + (" 💳 **DOUBLE DOWN!**" if double_bonus > 0 else ""),
            description=(
                f"**Final Card:** {game['current_card']}\n"
                f"**Streak:** {game['streak']} correct guesses\n"
                f"**Multiplier:** {multiplier:.1f}x\n\n"
                f"**Bet:** {game['bet']:,} <:mora:1437958309255577681>\n"
                f"**Won:** {winnings:,} <:mora:1437958309255577681>\n"
                f"**Profit:** {profit:+,} <:mora:1437958309255577681>\n\n"
                f"New Balance: {balance:,} <:mora:1437958309255577681>"
            ),
            color=0x2ECC71
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        # Disable buttons
        for item in view.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=view)
        del self.active_games[user_id]
    
    async def force_cashout(self, interaction: discord.Interaction, view: HiLoView):
        """Force cash out at max streak"""
        user_id = interaction.user.id
        game = self.active_games[user_id]
        
        multiplier = 10.0
        winnings = int(game['bet'] * multiplier)
        profit = winnings - game['bet']
        
        # Check for Double Down Card (must be activated first)
        from utils.database import has_active_item, consume_active_item, consume_inventory_item
        has_double = await has_active_item(user_id, "double_down")
        double_bonus = 0
        if has_double > 0:
            double_bonus = profit  # Double the profit
            winnings += double_bonus
            await consume_active_item(user_id, "double_down")
            await consume_inventory_item(user_id, "double_down")
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET mora = mora + ? WHERE user_id = ?", (winnings, user_id))
            
            await db.execute("""
                INSERT INTO game_stats (user_id, hilo_games, hilo_cashouts, hilo_best_streak)
                VALUES (?, 1, 1, 10)
                ON CONFLICT(user_id) DO UPDATE SET
                    hilo_games = hilo_games + 1,
                    hilo_cashouts = hilo_cashouts + 1,
                    hilo_best_streak = MAX(hilo_best_streak, 10)
            """, (user_id,))
            
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (user_id,))
            balance = (await cursor.fetchone())[0]
            await db.commit()
        
        embed = discord.Embed(
            title="🏆 MAX STREAK - AUTO CASHOUT!" + (" 💳 **DOUBLE DOWN!**" if double_bonus > 0 else ""),
            description=(
                f"**Final Card:** {game['current_card']}\n"
                f"**Streak:** 10 (MAX)\n"
                f"**Multiplier:** 10.0x\n\n"
                f"**Bet:** {game['bet']:,} <:mora:1437958309255577681>\n"
                f"**Won:** {winnings:,} <:mora:1437958309255577681>\n"
                f"**Profit:** {profit:+,} <:mora:1437958309255577681>\n\n"
                f"New Balance: {balance:,} <:mora:1437958309255577681>\n\n"
                f"Maximum streak reached!"
            ),
            color=0xFFD700
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        for item in view.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=view)
        del self.active_games[user_id]
    
    async def handle_joker(self, ctx, bet_amount):
        """Handle joker drawn at start"""
        winnings = int(bet_amount * 50)
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET mora = mora + ? WHERE user_id = ?", (winnings, ctx.author.id))
            
            await db.execute("""
                INSERT INTO game_stats (user_id, hilo_games, hilo_jokers)
                VALUES (?, 1, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    hilo_games = hilo_games + 1,
                    hilo_jokers = hilo_jokers + 1
            """, (ctx.author.id,))
            
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (ctx.author.id,))
            balance = (await cursor.fetchone())[0]
            await db.commit()
        
        embed = discord.Embed(
            title="🃏 JOKER - JACKPOT! 🃏",
            description=(
                f"You drew the legendary Joker!\n\n"
                f"**Bet:** {bet_amount:,} <:mora:1437958309255577681>\n"
                f"**Won:** {winnings:,} <:mora:1437958309255577681>\n"
                f"**Multiplier:** 50.0x\n\n"
                f"New Balance: {balance:,} <:mora:1437958309255577681>\n\n"
                f"Incredible luck! (0.2% chance)"
            ),
            color=0xFFD700
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        await send_embed(ctx, embed)
    
    async def handle_joker_mid_game(self, interaction: discord.Interaction, view: HiLoView, previous_card):
        """Handle joker drawn mid-game"""
        user_id = interaction.user.id
        game = self.active_games[user_id]
        
        winnings = int(game['bet'] * 50)
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET mora = mora + ? WHERE user_id = ?", (winnings, user_id))
            
            await db.execute("""
                INSERT INTO game_stats (user_id, hilo_games, hilo_jokers, hilo_best_streak)
                VALUES (?, 1, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    hilo_games = hilo_games + 1,
                    hilo_jokers = hilo_jokers + 1,
                    hilo_best_streak = MAX(hilo_best_streak, ?)
            """, (user_id, game['streak'], game['streak']))
            
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (user_id,))
            balance = (await cursor.fetchone())[0]
            await db.commit()
        
        embed = discord.Embed(
            title="🃏 JOKER - JACKPOT! 🃏",
            description=(
                f"**Previous:** {previous_card} → **Joker:** 🃏\n\n"
                f"You drew the legendary Joker!\n\n"
                f"**Streak before Joker:** {game['streak']}\n"
                f"**Bet:** {game['bet']:,} <:mora:1437958309255577681>\n"
                f"**Won:** {winnings:,} <:mora:1437958309255577681>\n"
                f"**Multiplier:** 50.0x\n\n"
                f"New Balance: {balance:,} <:mora:1437958309255577681>\n\n"
                f"Incredible luck! (0.2% chance)"
            ),
            color=0xFFD700
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        for item in view.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=view)
        del self.active_games[user_id]
    
    async def show_stats(self, ctx):
        """Show user's Hi-Lo statistics"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT hilo_games, hilo_cashouts, hilo_busts, hilo_best_streak, hilo_jokers
                FROM game_stats WHERE user_id = ?
            """, (ctx.author.id,))
            row = await cursor.fetchone()
        
        if not row or row[0] == 0:
            return await ctx.send("❌ You haven't played any Hi-Lo games yet!")
        
        games, cashouts, busts, best_streak, jokers = row
        cashout_rate = (cashouts / games * 100) if games > 0 else 0
        
        embed = discord.Embed(
            title=f"🎴 {ctx.author.display_name}'s Hi-Lo Stats",
            color=0x3498DB
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="Games Played", value=f"{games}", inline=True)
        embed.add_field(name="Cashed Out", value=f"{cashouts}", inline=True)
        embed.add_field(name="Busted", value=f"{busts}", inline=True)
        embed.add_field(name="Cash Out Rate", value=f"{cashout_rate:.1f}%", inline=True)
        embed.add_field(name="Best Streak", value=f"{best_streak}", inline=True)
        embed.add_field(name="Jokers Hit", value=f"{jokers or 0}", inline=True)
        
        await send_embed(ctx, embed)

async def setup(bot):
    await bot.add_cog(HiLo(bot))
