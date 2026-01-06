"""Memory Match Game - PVP Memory Matching"""
import discord
from discord.ext import commands
import random
import asyncio
import aiosqlite
from datetime import datetime
from typing import Union
from config import DB_PATH
from utils.database import get_user_data, update_user_data, ensure_user_db, require_enrollment
from utils.embed import send_embed


class ChallengeView(discord.ui.View):
    """Accept/Decline challenge buttons"""
    
    def __init__(self, challenger_id, opponent_id, bet):
        super().__init__(timeout=60)
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.bet = bet
        self.accepted = False
    
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent_id:
            return await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
        
        self.accepted = True
        self.stop()
        
        await interaction.response.edit_message(
            content=f"✅ <@{self.opponent_id}> accepted the challenge!",
            view=None
        )
    
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent_id:
            return await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
        
        self.stop()
        
        await interaction.response.edit_message(
            content=f"❌ <@{self.opponent_id}> declined the challenge.",
            view=None
        )


class SoloMemoryMatchView(discord.ui.View):
    """Button grid for solo memory match game"""
    
    def __init__(self, game_data, cog):
        super().__init__(timeout=120)
        self.game_data = game_data
        self.cog = cog
        self.message = None
        
        # Create buttons for all cards (4x4 grid = 16 cards)
        for i in range(16):
            button = discord.ui.Button(
                label="?",
                style=discord.ButtonStyle.primary,
                custom_id=f"card_{i}",
                row=i // 4
            )
            button.callback = self.create_callback(i)
            self.add_item(button)
    
    def create_callback(self, index):
        async def button_callback(interaction: discord.Interaction):
            await self.handle_card_flip(interaction, index)
        return button_callback
    
    async def handle_card_flip(self, interaction: discord.Interaction, card_index: int):
        """Handle card flip"""
        game = self.game_data
        
        # Check if it's the player
        if interaction.user.id != game['player_id']:
            return await interaction.response.send_message("❌ This isn't your game!", ephemeral=True)
        
        # Check if card is already revealed
        if card_index in game['revealed']:
            return await interaction.response.send_message("❌ This card is already matched!", ephemeral=True)
        
        # Check if already flipped 2 cards
        if len(game['flipped']) >= 2:
            return await interaction.response.send_message("❌ Wait for cards to flip back!", ephemeral=True)
        
        # Flip the card
        game['flipped'].append(card_index)
        game['moves'] += 1
        
        # Update the display
        await self.update_display(interaction)
        
        # If 2 cards flipped, check for match
        if len(game['flipped']) == 2:
            card1_idx = game['flipped'][0]
            card2_idx = game['flipped'][1]
            card1 = game['cards'][card1_idx]
            card2 = game['cards'][card2_idx]
            
            if card1 == card2:
                # Match found!
                game['revealed'].add(card1_idx)
                game['revealed'].add(card2_idx)
                game['matches'] += 1
                game['flipped'] = []
                
                # Check if game won
                if len(game['revealed']) == 16:
                    await self.game_won(interaction)
                else:
                    await self.update_display(interaction, match=True)
            else:
                # No match - show cards then flip back
                await asyncio.sleep(2)
                game['flipped'] = []
                
                # Check if still in game
                if game['player_id'] in self.cog.active_games:
                    await self.update_display(interaction, mismatch=True)
    
    async def update_display(self, interaction: discord.Interaction, match=False, mismatch=False):
        """Update the game display"""
        game = self.game_data
        
        # Update button states
        for i, item in enumerate(self.children):
            if i in game['revealed']:
                # Permanently revealed (matched)
                item.label = game['cards'][i]
                item.style = discord.ButtonStyle.success
                item.disabled = True
            elif i in game['flipped']:
                # Currently flipped
                item.label = game['cards'][i]
                item.style = discord.ButtonStyle.secondary
                item.disabled = False
            else:
                # Hidden
                item.label = "?"
                item.style = discord.ButtonStyle.primary
                item.disabled = False
        
        # Calculate time elapsed
        time_elapsed = (datetime.now() - game['start_time']).total_seconds()
        time_left = max(0, game['time_limit'] - time_elapsed)
        
        embed = discord.Embed(
            title="🎴 Memory Match - Solo",
            description=f"Find all 8 pairs!",
            color=0xE91E63
        )
        
        embed.add_field(name="⏱️ Time Left", value=f"{int(time_left)}s", inline=True)
        embed.add_field(name="🎯 Matches", value=f"{game['matches']}/8", inline=True)
        embed.add_field(name="🔄 Moves", value=f"{game['moves']}", inline=True)
        
        if match:
            embed.set_footer(text="✅ Match found!")
        elif mismatch:
            embed.set_footer(text="❌ No match! Cards flipped back.")
        else:
            embed.set_footer(text="Click two cards to find a match!")
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except:
            if self.message:
                await self.message.edit(embed=embed, view=self)
    
    async def game_won(self, interaction: discord.Interaction):
        """Handle game win"""
        game = self.game_data
        
        # Calculate performance
        time_taken = (datetime.now() - game['start_time']).total_seconds()
        perfect_moves = 8  # Minimum possible moves
        
        # Base multiplier (lowered)
        multiplier = 1.2
        
        # Bonus for efficiency
        if game['moves'] == perfect_moves:
            multiplier = 2.0  # Perfect game!
        elif game['moves'] <= perfect_moves + 2:
            multiplier = 1.8  # Excellent
        elif game['moves'] <= perfect_moves + 4:
            multiplier = 1.5  # Great
        
        # Time bonus
        if time_taken < 40:
            multiplier += 0.3
        elif time_taken < 60:
            multiplier += 0.2
        
        winnings = int(game['bet'] * multiplier)
        
        # Update balance
        user_data = await get_user_data(game['player_id'])
        new_balance = user_data['mora'] + winnings
        await update_user_data(game['player_id'], mora=new_balance)
        
        # Update stats
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO game_stats (user_id, memory_games, memory_wins)
                VALUES (?, 1, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    memory_games = memory_games + 1,
                    memory_wins = memory_wins + 1
            """, (game['player_id'],))
            await db.commit()
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        embed = discord.Embed(
            title="✅ Memory Match Complete!",
            description=f"You found all pairs!",
            color=0x2ECC71
        )
        
        embed.add_field(name="⏱️ Time", value=f"{time_taken:.1f}s", inline=True)
        embed.add_field(name="🔄 Moves", value=f"{game['moves']}", inline=True)
        embed.add_field(name="🎯 Perfect", value=f"{perfect_moves}", inline=True)
        
        performance = "Perfect! 🌟" if game['moves'] == perfect_moves else "Excellent!" if game['moves'] <= perfect_moves + 2 else "Great!" if game['moves'] <= perfect_moves + 4 else "Good!"
        embed.add_field(name="Performance", value=performance, inline=False)
        
        embed.add_field(name="💰 Bet", value=f"{game['bet']:,} <:mora:1437958309255577681>", inline=True)
        embed.add_field(name="Multiplier", value=f"{multiplier:.1f}x", inline=True)
        embed.add_field(name="🎉 Won", value=f"**{winnings:,}** <:mora:1437958309255577681>", inline=True)
        
        embed.set_footer(text=f"New Balance: {new_balance:,} mora")
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except:
            if self.message:
                await self.message.edit(embed=embed, view=self)
        
        # Remove from active games
        if game['player_id'] in self.cog.active_games:
            del self.cog.active_games[game['player_id']]
    
    async def on_timeout(self):
        """Handle timeout"""
        game = self.game_data
        
        # Update stats
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO game_stats (user_id, memory_games, memory_losses)
                VALUES (?, 1, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    memory_games = memory_games + 1,
                    memory_losses = memory_losses + 1
            """, (game['player_id'],))
            await db.commit()
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        embed = discord.Embed(
            title="⏱️ Time's Up!",
            description=f"You ran out of time!",
            color=0xE74C3C
        )
        
        embed.add_field(name="🎯 Matches Found", value=f"{game['matches']}/8", inline=True)
        embed.add_field(name="💸 Lost", value=f"{game['bet']:,} <:mora:1437958309255577681>", inline=True)
        
        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except:
                pass
        
        # Remove from active games
        if game['player_id'] in self.cog.active_games:
            del self.cog.active_games[game['player_id']]


class MemoryMatchView(discord.ui.View):
    """Button grid for memory match game"""
    
    def __init__(self, game_data, cog):
        super().__init__(timeout=180)
        self.game_data = game_data
        self.cog = cog
        self.message = None
        
        # Create buttons for all cards (4x4 grid = 16 cards)
        for i in range(16):
            button = discord.ui.Button(
                label="?",
                style=discord.ButtonStyle.primary,
                custom_id=f"card_{i}",
                row=i // 4  # 4 cards per row
            )
            button.callback = self.create_callback(i)
            self.add_item(button)
    
    def create_callback(self, index):
        async def button_callback(interaction: discord.Interaction):
            await self.handle_card_flip(interaction, index)
        return button_callback
    
    async def handle_card_flip(self, interaction: discord.Interaction, card_index: int):
        """Handle card flip"""
        game = self.game_data
        
        # Check if it's the player's turn
        current_player = game['player1_id'] if game['current_turn'] == 1 else game['player2_id']
        if interaction.user.id != current_player:
            return await interaction.response.send_message("❌ It's not your turn!", ephemeral=True)
        
        # Check if card is already revealed
        if card_index in game['revealed']:
            return await interaction.response.send_message("❌ This card is already matched!", ephemeral=True)
        
        # Check if already flipped 2 cards this turn
        if len(game['flipped']) >= 2:
            return await interaction.response.send_message("❌ Wait for cards to flip back!", ephemeral=True)
        
        # Flip the card
        game['flipped'].append(card_index)
        
        # Update the display
        await self.update_display(interaction)
        
        # If 2 cards flipped, check for match
        if len(game['flipped']) == 2:
            card1_idx = game['flipped'][0]
            card2_idx = game['flipped'][1]
            card1 = game['cards'][card1_idx]
            card2 = game['cards'][card2_idx]
            
            if card1 == card2:
                # Match found! Player continues
                game['revealed'].add(card1_idx)
                game['revealed'].add(card2_idx)
                
                if game['current_turn'] == 1:
                    game['player1_score'] += 1
                else:
                    game['player2_score'] += 1
                
                game['flipped'] = []
                
                # Check if game won
                if len(game['revealed']) == 16:
                    await self.game_won(interaction)
                else:
                    await self.update_display(interaction, match=True)
            else:
                # No match - show cards then flip back and switch turns
                await asyncio.sleep(2)
                game['flipped'] = []
                
                # Switch turns
                game['current_turn'] = 2 if game['current_turn'] == 1 else 1
                
                # Check if still in game (not timed out)
                game_key = f"{game['player1_id']}_{game['player2_id']}"
                if game_key in self.cog.active_games:
                    await self.update_display(interaction, mismatch=True)
    
    async def update_display(self, interaction: discord.Interaction, match=False, mismatch=False):
        """Update the game display"""
        game = self.game_data
        
        # Update button states
        for i, item in enumerate(self.children):
            if i in game['revealed']:
                # Permanently revealed (matched)
                item.label = game['cards'][i]
                item.style = discord.ButtonStyle.success
                item.disabled = True
            elif i in game['flipped']:
                # Currently flipped
                item.label = game['cards'][i]
                item.style = discord.ButtonStyle.secondary
                item.disabled = False
            else:
                # Hidden
                item.label = "?"
                item.style = discord.ButtonStyle.primary
                item.disabled = False
        
        current_player = game['player1_id'] if game['current_turn'] == 1 else game['player2_id']
        
        embed = discord.Embed(
            title="🎴 Memory Match PVP",
            description=f"<@{current_player}>'s turn!",
            color=0xE91E63
        )
        
        embed.add_field(
            name=f"<@{game['player1_id']}>",
            value=f"**{game['player1_score']}** pairs",
            inline=True
        )
        embed.add_field(
            name="VS",
            value="⚔️",
            inline=True
        )
        embed.add_field(
            name=f"<@{game['player2_id']}>",
            value=f"**{game['player2_score']}** pairs",
            inline=True
        )
        
        embed.add_field(name="💰 Bet", value=f"{game['bet']:,} <:mora:1437958309255577681>", inline=True)
        embed.add_field(name="🎯 Total Pairs", value="8 pairs", inline=True)
        embed.add_field(name="✅ Found", value=f"{game['player1_score'] + game['player2_score']}/8", inline=True)
        
        if match:
            embed.set_footer(text="✅ Match! You get another turn!")
        elif mismatch:
            embed.set_footer(text="❌ No match! Cards flipped back. Turn switched!")
        else:
            embed.set_footer(text="Click two cards to find a match!")
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except:
            # If response already sent, use followup
            if self.message:
                await self.message.edit(embed=embed, view=self)
    
    async def game_won(self, interaction: discord.Interaction):
        """Handle game end"""
        game = self.game_data
        
        # Determine winner
        if game['player1_score'] > game['player2_score']:
            winner_id = game['player1_id']
            loser_id = game['player2_id']
            winner_score = game['player1_score']
            loser_score = game['player2_score']
        elif game['player2_score'] > game['player1_score']:
            winner_id = game['player2_id']
            loser_id = game['player1_id']
            winner_score = game['player2_score']
            loser_score = game['player1_score']
        else:
            # Tie - return bets
            p1_data = await get_user_data(game['player1_id'])
            p2_data = await get_user_data(game['player2_id'])
            
            await update_user_data(game['player1_id'], mora=p1_data['mora'] + game['bet'])
            await update_user_data(game['player2_id'], mora=p2_data['mora'] + game['bet'])
            
            embed = discord.Embed(
                title="🤝 It's a Tie!",
                description=f"Both players found 4 pairs!",
                color=0x95A5A6
            )
            
            embed.add_field(name=f"<@{game['player1_id']}>", value=f"{game['player1_score']} pairs", inline=True)
            embed.add_field(name=f"<@{game['player2_id']}>", value=f"{game['player2_score']} pairs", inline=True)
            embed.add_field(name="💰 Result", value="Bets returned!", inline=False)
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            try:
                await interaction.response.edit_message(embed=embed, view=self)
            except:
                if self.message:
                    await self.message.edit(embed=embed, view=self)
            
            game_key = f"{game['player1_id']}_{game['player2_id']}"
            if game_key in self.cog.active_games:
                del self.cog.active_games[game_key]
            return
        
        # Transfer winnings
        winner_data = await get_user_data(winner_id)
        new_balance = winner_data['mora'] + (game['bet'] * 2)
        await update_user_data(winner_id, mora=new_balance)
        
        # Update stats
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO game_stats (user_id, memory_games, memory_wins)
                VALUES (?, 1, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    memory_games = memory_games + 1,
                    memory_wins = memory_wins + 1
            """, (winner_id,))
            
            await db.execute("""
                INSERT INTO game_stats (user_id, memory_games, memory_losses)
                VALUES (?, 1, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    memory_games = memory_games + 1,
                    memory_losses = memory_losses + 1
            """, (loser_id,))
            
            await db.commit()
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        embed = discord.Embed(
            title="<a:Trophy:1438199339586424925> Game Over!",
            description=f"<@{winner_id}> wins!",
            color=0xFFD700
        )
        
        embed.add_field(name="Winner", value=f"<@{winner_id}>", inline=True)
        embed.add_field(name="Score", value=f"{winner_score} - {loser_score}", inline=True)
        embed.add_field(name="Won", value=f"**{game['bet'] * 2:,}** <:mora:1437958309255577681>", inline=True)
        
        embed.set_footer(text=f"New Balance: {new_balance:,} mora")
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except:
            if self.message:
                await self.message.edit(embed=embed, view=self)
        
        # Remove from active games
        game_key = f"{game['player1_id']}_{game['player2_id']}"
        if game_key in self.cog.active_games:
            del self.cog.active_games[game_key]
    
    async def on_timeout(self):
        """Handle timeout"""
        game = self.game_data
        
        # Return bets to both players
        p1_data = await get_user_data(game['player1_id'])
        p2_data = await get_user_data(game['player2_id'])
        
        await update_user_data(game['player1_id'], mora=p1_data['mora'] + game['bet'])
        await update_user_data(game['player2_id'], mora=p2_data['mora'] + game['bet'])
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        embed = discord.Embed(
            title="⏱️ Game Timeout!",
            description=f"Game took too long. Bets returned.",
            color=0xE74C3C
        )
        
        embed.add_field(name=f"<@{game['player1_id']}>", value=f"{game['player1_score']} pairs", inline=True)
        embed.add_field(name=f"<@{game['player2_id']}>", value=f"{game['player2_score']} pairs", inline=True)
        
        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except:
                pass
        
        # Remove from active games
        game_key = f"{game['player1_id']}_{game['player2_id']}"
        if game_key in self.cog.active_games:
            del self.cog.active_games[game_key]


class MemoryMatch(commands.Cog):
    """Memory Match PVP minigame"""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}
    
    async def cog_load(self):
        """Add memory match columns to database"""
        async with aiosqlite.connect(DB_PATH) as db:
            try:
                await db.execute("ALTER TABLE game_stats ADD COLUMN memory_games INTEGER DEFAULT 0")
                await db.commit()
            except:
                pass
            
            try:
                await db.execute("ALTER TABLE game_stats ADD COLUMN memory_wins INTEGER DEFAULT 0")
                await db.commit()
            except:
                pass
            
            try:
                await db.execute("ALTER TABLE game_stats ADD COLUMN memory_losses INTEGER DEFAULT 0")
                await db.commit()
            except:
                pass
    
    @commands.command(name="memory", aliases=["memorymatch", "match"])
    async def memory_match(self, ctx, opponent_or_bet: Union[discord.Member, str] = None, bet: str = None):
        """Play Memory Match solo or challenge someone to PVP
        
        Solo: Find all pairs before time runs out!
        PVP: Take turns finding pairs. Most pairs wins!
        
        Usage: 
        - Solo: gmemory <bet>
        - PVP: gmemory @player <bet>
        
        Example: gmemory 1000 OR gmemory @user 1000
        """
        if not await require_enrollment(ctx):
            return
        
        await ensure_user_db(ctx.author.id)
        
        if not opponent_or_bet:
            return await ctx.send("Usage: `gmemory <bet>` OR `gmemory @player <bet>`\nExample: `gmemory 1000` or `gmemory @user 1000`")
        
        # Check if it's solo or PVP
        if isinstance(opponent_or_bet, discord.Member):
            # PVP MODE
            opponent = opponent_or_bet
            
            if not bet:
                return await ctx.send("Usage: `gmemory @player <bet>`\nExample: `gmemory @user 1000`")
            
            if opponent.bot:
                return await ctx.send("❌ You can't play against bots!")
            
            if opponent.id == ctx.author.id:
                return await ctx.send("❌ Use `gmemory <bet>` to play solo!")
            
            await ensure_user_db(opponent.id)
            
            await self.start_pvp_game(ctx, opponent, bet)
        else:
            # SOLO MODE
            bet = str(opponent_or_bet)
            await self.start_solo_game(ctx, bet)
    
    async def start_solo_game(self, ctx, bet: str):
        """Start a solo memory match game"""
        # Check if already in a game
        if ctx.author.id in self.active_games:
            return await ctx.send("❌ You already have an active memory match game!")
        
        # Parse bet
        user_data = await get_user_data(ctx.author.id)
        user_mora = user_data['mora']
        
        # Convert bet to string if it isn't already
        bet = str(bet)
        
        if bet.lower() == 'all':
            bet_amount = user_mora
        else:
            try:
                bet_amount = int(bet.replace(',', ''))
            except Exception as e:
                return await ctx.send(f"❌ Invalid bet amount! Please enter a number.\nExample: `gmemory 1000`")
        
        if bet_amount < 100:
            return await ctx.send("❌ Minimum bet is 100 <:mora:1437958309255577681>!")
        
        if bet_amount > 1000000:
            return await ctx.send("❌ Maximum bet is 1,000,000 <:mora:1437958309255577681>!")
        
        if bet_amount > user_mora:
            return await ctx.send(f"❌ You only have {user_mora:,} <:mora:1437958309255577681>!")
        
        # Deduct bet
        await update_user_data(ctx.author.id, mora=user_mora - bet_amount)
        
        # Setup game - 16 cards (8 pairs)
        card_emojis = ["🍎", "🍊", "🍋", "🍇", "🍓", "🍒", "🍑", "🍈"]
        cards = card_emojis * 2
        random.shuffle(cards)
        
        # Create game data for solo
        game_data = {
            'player_id': ctx.author.id,
            'cards': cards,
            'revealed': set(),
            'flipped': [],
            'matches': 0,
            'moves': 0,
            'bet': bet_amount,
            'start_time': datetime.now(),
            'time_limit': 90,
            'solo': True
        }
        
        self.active_games[ctx.author.id] = game_data
        
        # Start game directly (no preview)
        view = SoloMemoryMatchView(game_data, self)
        
        embed = discord.Embed(
            title="🎴 Memory Match - Solo",
            description=f"Find all 8 pairs!",
            color=0xE91E63
        )
        
        embed.add_field(name="⏱️ Time Limit", value="90s", inline=True)
        embed.add_field(name="🎯 Matches", value="0/8", inline=True)
        embed.add_field(name="💰 Bet", value=f"{bet_amount:,} <:mora:1437958309255577681>", inline=True)
        
        embed.set_footer(text="Click two cards to find a match!")
        
        game_msg = await send_embed(ctx, embed, view=view)
        view.message = game_msg
    
    async def start_pvp_game(self, ctx, opponent: discord.Member, bet: str):
        """Start a PVP memory match game"""
        
    async def start_pvp_game(self, ctx, opponent: discord.Member, bet: str):
        """Start a PVP memory match game"""
        # Check if either player is already in a game
        game_key1 = f"{ctx.author.id}_{opponent.id}"
        game_key2 = f"{opponent.id}_{ctx.author.id}"
        
        if game_key1 in self.active_games or game_key2 in self.active_games:
            return await ctx.send("❌ One of you is already in a game!")
        
        if ctx.author.id in self.active_games or opponent.id in self.active_games:
            return await ctx.send("❌ One of you is already in a game!")
        
        # Parse bet
        user_data = await get_user_data(ctx.author.id)
        user_mora = user_data['mora']
        
        if bet.lower() == 'all':
            bet_amount = user_mora
        else:
            try:
                bet_amount = int(bet.replace(',', ''))
            except:
                return await ctx.send("❌ Invalid bet amount!")
        
        if bet_amount < 100:
            return await ctx.send("❌ Minimum bet is 100 <:mora:1437958309255577681>!")
        
        if bet_amount > 1000000:
            return await ctx.send("❌ Maximum bet is 1,000,000 <:mora:1437958309255577681>!")
        
        if bet_amount > user_mora:
            return await ctx.send(f"❌ You only have {user_mora:,} <:mora:1437958309255577681>!")
        
        # Check opponent balance
        opp_data = await get_user_data(opponent.id)
        if bet_amount > opp_data['mora']:
            return await ctx.send(f"❌ {opponent.mention} only has {opp_data['mora']:,} <:mora:1437958309255577681>!")
        
        # Send challenge
        challenge_view = ChallengeView(ctx.author.id, opponent.id, bet_amount)
        
        challenge_embed = discord.Embed(
            title="🎴 Memory Match Challenge!",
            description=f"{ctx.author.mention} challenges {opponent.mention} to Memory Match!",
            color=0xE91E63
        )
        challenge_embed.add_field(name="💰 Bet", value=f"{bet_amount:,} <:mora:1437958309255577681>", inline=True)
        challenge_embed.add_field(name="Rules", value="Take turns finding pairs. Match = another turn!\nMost pairs wins!", inline=False)
        
        challenge_msg = await send_embed(ctx, challenge_embed, view=challenge_view)
        
        # Wait for response
        await challenge_view.wait()
        
        if not challenge_view.accepted:
            return
        
        # Deduct bets from both players
        await update_user_data(ctx.author.id, mora=user_mora - bet_amount)
        await update_user_data(opponent.id, mora=opp_data['mora'] - bet_amount)
        
        # Setup game - 16 cards (8 pairs)
        card_emojis = ["🍎", "🍊", "🍋", "🍇", "🍓", "🍒", "🍑", "🍈"]
        cards = card_emojis * 2  # Create pairs
        random.shuffle(cards)
        
        # Create game data
        game_data = {
            'player1_id': ctx.author.id,
            'player2_id': opponent.id,
            'cards': cards,
            'revealed': set(),
            'flipped': [],
            'player1_score': 0,
            'player2_score': 0,
            'current_turn': 1,  # Player 1 starts
            'bet': bet_amount
        }
        
        game_key = f"{ctx.author.id}_{opponent.id}"
        self.active_games[game_key] = game_data
        
        # Start game directly (no preview)
        view = MemoryMatchView(game_data, self)
        
        embed = discord.Embed(
            title="🎴 Memory Match PVP",
            description=f"<@{ctx.author.id}>'s turn!",
            color=0xE91E63
        )
        
        embed.add_field(
            name=f"{ctx.author.display_name}",
            value=f"**0** pairs",
            inline=True
        )
        embed.add_field(
            name="VS",
            value="⚔️",
            inline=True
        )
        embed.add_field(
            name=f"{opponent.display_name}",
            value=f"**0** pairs",
            inline=True
        )
        
        embed.add_field(name="💰 Bet", value=f"{bet_amount:,} <:mora:1437958309255577681>", inline=True)
        embed.add_field(name="🎯 Total Pairs", value="8 pairs", inline=True)
        embed.add_field(name="✅ Found", value="0/8", inline=True)
        
        embed.set_footer(text="Click two cards to find a match!")
        
        # Start the game
        game_msg = await send_embed(ctx, embed, view=view)
        view.message = game_msg


async def setup(bot):
    await bot.add_cog(MemoryMatch(bot))
