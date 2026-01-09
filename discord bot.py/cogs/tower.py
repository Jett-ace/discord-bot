import discord
from discord.ext import commands
import aiosqlite
import random
from config import DB_PATH
from utils.embed import send_embed
from utils.database import require_enrollment

# Floor multipliers
FLOOR_MULTIPLIERS = {
    1: 1.3,
    2: 1.6,
    3: 2.0,
    4: 2.5,
    5: 3.0,
    6: 3.5,
    7: 4.5,
    8: 6.0,
    9: 8.0,
    10: 10.0
}

class TowerView(discord.ui.View):
    def __init__(self, game_data, cog):
        super().__init__(timeout=120)
        self.game_data = game_data
        self.cog = cog
        self.message = None
        
        # Set up tile buttons
        self.setup_buttons()
    
    def setup_buttons(self):
        """Setup the tile and cash out buttons"""
        # Clear existing buttons
        self.clear_items()
        
        # Add 3 tile buttons
        for i in range(1, 4):
            button = discord.ui.Button(
                label=f"Tile {i}",
                style=discord.ButtonStyle.primary,
                custom_id=f"tile_{i}"
            )
            button.callback = self.create_tile_callback(i)
            self.add_item(button)
        
        # Add cash out button
        cashout = discord.ui.Button(
            label="Cash Out",
            style=discord.ButtonStyle.success,
            custom_id="cashout"
        )
        cashout.callback = self.cashout_callback
        self.add_item(cashout)
    
    def create_tile_callback(self, tile_num):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.game_data['user_id']:
                return await interaction.response.send_message("This isn't your game!", ephemeral=True)
            await self.cog.process_tile_choice(interaction, tile_num, self)
        return callback
    
    async def cashout_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game_data['user_id']:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        await self.cog.cash_out(interaction, self)
    
    async def on_timeout(self):
        """Auto cash out on timeout"""
        if self.game_data['user_id'] in self.cog.active_games:
            await self.auto_cashout()
    
    async def auto_cashout(self):
        """Auto cash out when timeout"""
        user_id = self.game_data['user_id']
        if user_id not in self.cog.active_games:
            return
        
        game = self.cog.active_games[user_id]
        floor = game['floor']
        
        # Can't cash out on floor 0
        if floor == 0:
            del self.cog.active_games[user_id]
            return
        
        multiplier = FLOOR_MULTIPLIERS[floor]
        winnings = int(game['bet'] * multiplier)
        
        # Update balance
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET mora = mora + ? WHERE user_id = ?", (winnings, user_id))
            
            # Update stats
            await db.execute("""
                INSERT INTO game_stats (user_id, tower_games, tower_cashouts, tower_highest_floor)
                VALUES (?, 1, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    tower_games = tower_games + 1,
                    tower_cashouts = tower_cashouts + 1,
                    tower_highest_floor = MAX(tower_highest_floor, ?)
            """, (user_id, floor, floor))
            
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (user_id,))
            balance = (await cursor.fetchone())[0]
            await db.commit()
        
        profit = winnings - game['bet']
        
        embed = discord.Embed(
            title="⏱️ AUTO CASHED OUT",
            description=(
                f"**Final Floor:** {floor} / 10\n"
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

class Tower(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}
    
    @commands.command(name="tower", aliases=["climb"])
    async def tower(self, ctx, bet: str = None):
        """Climb the tower by choosing safe tiles
        
        Usage:
        gtower <bet>
        gtower stats
        """
        if bet == "stats":
            return await self.show_stats(ctx)
        
        if not await require_enrollment(ctx):
            return
        
        if ctx.author.id in self.active_games:
            return await ctx.send("❌ You already have an active Tower game!")
        
        if bet is None:
            embed = discord.Embed(
                title="🗼 Tower Game",
                description=(
                    "Climb the tower by choosing safe tiles!\n\n"
                    "**Usage:** `gtower <bet>`\n\n"
                    "**How to Play:**\n"
                    "• Each floor has 3 tiles: 2 safe, 1 trap\n"
                    "• Choose a safe tile to climb higher\n"
                    "• Cash out anytime to keep winnings\n"
                    "• Hit a trap = lose everything\n\n"
                    "**Multipliers:**\n"
                    "Floor 1: 1.3x | 2: 1.6x | 3: 2.0x\n"
                    "Floor 4: 2.5x | 5: 3.0x | 6: 3.5x\n"
                    "Floor 7: 4.5x | 8: 6.0x | 9: 8.0x\n"
                    "Floor 10: 10.0x (auto cash out)\n\n"
                    "33% chance to fail each floor"
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
        
        # Check premium status for higher bet limit
        premium_cog = self.bot.get_cog('Premium')
        is_premium = False
        if premium_cog:
            try:
                is_premium = await premium_cog.is_premium(ctx.author.id)
                print(f"[TOWER] User {ctx.author.id} premium status: {is_premium}")
            except Exception:
                is_premium = False
        
        max_bet = 1_000_000 if is_premium else 100_000
        print(f"[TOWER] User {ctx.author.id} max_bet set to: {max_bet:,}")
        
        if bet_amount > max_bet:
            return await ctx.send(f"❌ Maximum bet is {max_bet:,} mora!")
        
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
        game_data = {
            "user_id": ctx.author.id,
            "bet": bet_amount,
            "floor": 0,
            "history": []  # Track which tiles were traps
        }
        
        self.active_games[ctx.author.id] = game_data
        
        # Start climbing
        await self.show_floor(ctx, game_data)
    
    async def show_floor(self, ctx, game_data, interaction=None):
        """Display current floor"""
        game_data['floor'] += 1
        floor = game_data['floor']
        
        # Generate trap position (1, 2, or 3)
        trap_tile = random.randint(1, 3)
        game_data['trap_tile'] = trap_tile
        
        multiplier = FLOOR_MULTIPLIERS[floor]
        current_win = int(game_data['bet'] * multiplier)
        
        # Get next floor info if not max
        if floor < 10:
            next_multiplier = FLOOR_MULTIPLIERS[floor + 1]
            next_win = int(game_data['bet'] * next_multiplier)
            next_info = f"**Next Floor:** {next_win:,} <:mora:1437958309255577681> ({next_multiplier:.1f}x)\n\n"
        else:
            next_info = "\n"
        
        embed = discord.Embed(
            title="🗼 TOWER CLIMB",
            description=(
                f"**Floor:** {floor} / 10\n"
                f"**Current Win:** {current_win:,} <:mora:1437958309255577681> ({multiplier:.1f}x)\n"
                f"{next_info}"
                f"Choose a tile to climb:\n"
                f"[🟦] [🟦] [🟦]\n\n"
                f"2 safe tiles, 1 trap"
            ),
            color=0x3498DB
        )
        embed.set_author(name=ctx.author.display_name if ctx else interaction.user.display_name, icon_url=(ctx.author.display_avatar.url if ctx else interaction.user.display_avatar.url))
        embed.set_footer(text=f"Bet: {game_data['bet']:,} mora | Wrong choice = lose everything")
        
        view = TowerView(game_data, self)
        
        if interaction:
            view.message = await interaction.message.edit(embed=embed, view=view)
        else:
            view.message = await send_embed(ctx, embed, view=view)
    
    async def process_tile_choice(self, interaction: discord.Interaction, tile_num: int, view: TowerView):
        """Process a tile choice"""
        user_id = interaction.user.id
        
        if user_id not in self.active_games:
            return await interaction.response.send_message("❌ Game not found!", ephemeral=True)
        
        game = self.active_games[user_id]
        floor = game['floor']
        trap_tile = game['trap_tile']
        
        # Check if hit trap
        hit_trap = tile_num == trap_tile
        
        # Check for lucky dice (+5% chance to avoid trap)
        from utils.database import has_active_item, consume_active_item
        has_dice = await has_active_item(user_id, "lucky_dice")
        
        if hit_trap and has_dice > 0 and random.random() < 0.03:
            # Lucky dice triggered - convert trap to safe tile
            hit_trap = False
            await consume_active_item(user_id, "lucky_dice")
        
        if hit_trap:
            # Hit trap - lose
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO game_stats (user_id, tower_games, tower_traps, tower_highest_floor)
                    VALUES (?, 1, 1, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        tower_games = tower_games + 1,
                        tower_traps = tower_traps + 1,
                        tower_highest_floor = MAX(tower_highest_floor, ?)
                """, (user_id, floor - 1, floor - 1))
                await db.commit()
            
            # Apply golden card cashback (10%)
            bank_cog = interaction.client.get_cog('Bank')
            cashback = 0
            if bank_cog:
                cashback = await bank_cog.apply_golden_cashback(user_id, game['bet'])
            
            # Show which tiles were safe/trap
            tiles = []
            for i in range(1, 4):
                if i == trap_tile:
                    tiles.append("❌")
                else:
                    tiles.append("✅")
            
            loss_text = f"**Lost:** {game['bet']:,} <:mora:1437958309255577681>"
            if cashback > 0:
                loss_text += f"\n+{cashback:,} cashback <a:gold:1457409675963138205>"
            
            embed = discord.Embed(
                title="❌ TRAP!",
                description=(
                    f"You hit a trap on Floor {floor}!\n\n"
                    f"Tiles: [{tiles[0]}] [{tiles[1]}] [{tiles[2]}]\n\n"
                    f"{loss_text}\n\n"
                    f"Should've cashed out! Better luck next time."
                ),
                color=0xE74C3C
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            
            # Disable buttons
            for item in view.children:
                item.disabled = True
            
            await interaction.response.edit_message(embed=embed, view=view)
            del self.active_games[user_id]
        else:
            # Safe tile!
            game['history'].append({
                'floor': floor,
                'trap': trap_tile,
                'chosen': tile_num
            })
            
            # Check if reached max floor
            if floor >= 10:
                return await self.force_cashout(interaction, view)
            
            # Show safe tile message and continue
            tiles = []
            for i in range(1, 4):
                if i == trap_tile:
                    tiles.append("❌")
                elif i == tile_num:
                    tiles.append("✅")
                else:
                    tiles.append("🟦")
            
            multiplier = FLOOR_MULTIPLIERS[floor]
            current_win = int(game['bet'] * multiplier)
            next_multiplier = FLOOR_MULTIPLIERS[floor + 1]
            next_win = int(game['bet'] * next_multiplier)
            
            embed = discord.Embed(
                title="✅ SAFE TILE!",
                description=(
                    f"**Floor:** {floor} / 10\n"
                    f"**Current Win:** {current_win:,} <:mora:1437958309255577681> ({multiplier:.1f}x)\n"
                    f"**Next Floor:** {next_win:,} <:mora:1437958309255577681> ({next_multiplier:.1f}x)\n\n"
                    f"Choose next tile:\n"
                    f"[🟦] [🟦] [🟦]"
                ),
                color=0x2ECC71
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            
            await interaction.response.edit_message(embed=embed, view=view)
            
            # Move to next floor
            await self.show_floor(None, game, interaction)
    
    async def cash_out(self, interaction: discord.Interaction, view: TowerView):
        """Cash out current winnings"""
        user_id = interaction.user.id
        
        if user_id not in self.active_games:
            return await interaction.response.send_message("❌ Game not found!", ephemeral=True)
        
        game = self.active_games[user_id]
        floor = game['floor']
        
        # Can't cash out before climbing
        if floor == 0:
            return await interaction.response.send_message("❌ You need to climb at least 1 floor to cash out!", ephemeral=True)
        
        multiplier = FLOOR_MULTIPLIERS[floor]
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
                INSERT INTO game_stats (user_id, tower_games, tower_cashouts, tower_highest_floor)
                VALUES (?, 1, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    tower_games = tower_games + 1,
                    tower_cashouts = tower_cashouts + 1,
                    tower_highest_floor = MAX(tower_highest_floor, ?)
            """, (user_id, floor, floor))
            
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (user_id,))
            balance = (await cursor.fetchone())[0]
            await db.commit()
        
        embed = discord.Embed(
            title="✅ CASHED OUT!" + (" 💳 **DOUBLE DOWN!**" if double_bonus > 0 else ""),
            description=(
                f"**Final Floor:** {floor} / 10\n"
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
    
    async def force_cashout(self, interaction: discord.Interaction, view: TowerView):
        """Force cash out at max floor"""
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
                INSERT INTO game_stats (user_id, tower_games, tower_cashouts, tower_highest_floor, tower_perfect)
                VALUES (?, 1, 1, 10, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    tower_games = tower_games + 1,
                    tower_cashouts = tower_cashouts + 1,
                    tower_highest_floor = 10,
                    tower_perfect = tower_perfect + 1
            """, (user_id,))
            
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (user_id,))
            balance = (await cursor.fetchone())[0]
            await db.commit()
        
        embed = discord.Embed(
            title="🏆 TOWER COMPLETE!" + (" 💳 **DOUBLE DOWN!**" if double_bonus > 0 else ""),
            description=(
                f"You reached the top!\n\n"
                f"**Floor:** 10 / 10\n"
                f"**Multiplier:** 10.0x\n\n"
                f"**Bet:** {game['bet']:,} <:mora:1437958309255577681>\n"
                f"**Won:** {winnings:,} <:mora:1437958309255577681>\n"
                f"**Profit:** {profit:+,} <:mora:1437958309255577681>\n\n"
                f"New Balance: {balance:,} <:mora:1437958309255577681>\n\n"
                f"Perfect climb! 🎯"
            ),
            color=0xFFD700
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        for item in view.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=view)
        del self.active_games[user_id]
    
    async def show_stats(self, ctx):
        """Show user's Tower statistics"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT tower_games, tower_cashouts, tower_traps, tower_highest_floor, tower_perfect
                FROM game_stats WHERE user_id = ?
            """, (ctx.author.id,))
            row = await cursor.fetchone()
        
        if not row or row[0] == 0:
            return await ctx.send("❌ You haven't played any Tower games yet!")
        
        games, cashouts, traps, highest, perfect = row
        cashout_rate = (cashouts / games * 100) if games > 0 else 0
        
        embed = discord.Embed(
            title=f"🗼 {ctx.author.display_name}'s Tower Stats",
            color=0x3498DB
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="Games Played", value=f"{games}", inline=True)
        embed.add_field(name="Cashed Out", value=f"{cashouts}", inline=True)
        embed.add_field(name="Hit Traps", value=f"{traps}", inline=True)
        embed.add_field(name="Cash Out Rate", value=f"{cashout_rate:.1f}%", inline=True)
        embed.add_field(name="Highest Floor", value=f"{highest or 0}", inline=True)
        embed.add_field(name="Perfect Climbs", value=f"{perfect or 0}", inline=True)
        
        await send_embed(ctx, embed)

async def setup(bot):
    await bot.add_cog(Tower(bot))
