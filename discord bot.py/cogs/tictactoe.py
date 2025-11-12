import random
import discord
from discord.ext import commands
from utils.database import get_user_data, update_user_data
from utils.embed import send_embed


def check_winner(board):
    # board is list of 9 elements: None, 'X', or 'O'
    lines = (
        (0, 1, 2),
        (3, 4, 5),
        (6, 7, 8),
        (0, 3, 6),
        (1, 4, 7),
        (2, 5, 8),
        (0, 4, 8),
        (2, 4, 6),
    )
    for a, b, c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(x is not None for x in board):
        return "draw"
    return None


class BoxButton(discord.ui.Button):
    def __init__(self, index: int, view: "TicTacToeView", row: int):
        # gray boxes without numbers
        super().__init__(label='\u200b', style=discord.ButtonStyle.secondary, row=row)
        self.index = index
        self.ttt_view = view

    async def callback(self, interaction: discord.Interaction):
        view: TicTacToeView = self.ttt_view
        if interaction.user.id not in (view.player_x, view.player_o):
            return await interaction.response.send_message("This is not your game.", ephemeral=True)

        if view.finished:
            return await interaction.response.defer()

        # enforce turn
        current_id = view.player_x if view.turn == 'X' else view.player_o
        if interaction.user.id != current_id:
            return await interaction.response.send_message("Not your turn.", ephemeral=True)

        # mark the box
        if view.board[self.index] is not None:
            return await interaction.response.send_message("Box already taken.", ephemeral=True)

        mark = view.turn
        view.board[self.index] = mark
        # update visual label to show X or O
        self.label = '❌' if mark == 'X' else '⭕'
        self.disabled = True
        self.style = discord.ButtonStyle.success if mark == 'X' else discord.ButtonStyle.danger

        # check for win/draw
        winner = check_winner(view.board)
        if winner:
            view.finished = True
            # disable all remaining buttons and show results
            for item in view.children:
                if isinstance(item, BoxButton):
                    item.disabled = True
                    if view.board[item.index] is not None:
                        item.label = '❌' if view.board[item.index] == 'X' else '⭕'
                        item.style = discord.ButtonStyle.success if view.board[item.index] == 'X' else discord.ButtonStyle.danger

            if winner == 'draw':
                title = "TicTacToe - Draw"
                desc = "It's a draw!"
                color = 0x95a5a6
            else:
                winner_id = view.player_x if winner == 'X' else view.player_o
                member = view.ctx.guild.get_member(winner_id) if view.ctx.guild else None
                winner_name = member.display_name if member else 'Player'
                # award Mora to the winner (if not the bot)
                reward = random.randint(200, 600)
                if winner_id != view.cog.bot.user.id:
                    try:
                        data = await get_user_data(winner_id)
                        data['mora'] = data.get('mora', 0) + reward
                        await update_user_data(winner_id, mora=data['mora'])
                    except Exception as e:
                        print(f"Error awarding tic tac toe reward: {e}")

                # check if bot won against player
                if view.vs_bot and winner_id == view.cog.bot.user.id:
                    title = "TicTacToe - You Lose"
                    desc = "You lose. Better luck next time."
                    color = 0xDC143C  # Crimson red
                else:
                    title = f"TicTacToe - {winner_name} wins!"
                    desc = f"{winner_name} wins! Awarded {reward:,} 💰."
                    color = 0x2ecc71
            embed = discord.Embed(title=title, description=desc, color=color)
            embed.set_author(name=view.ctx.author.display_name, icon_url=view.ctx.author.display_avatar.url)
            try:
                await interaction.response.edit_message(embed=embed, view=view)
            except Exception:
                pass
            # clear active game
            view.cog.active_games.discard(view.game_key)
            return

        # swap turn
        view.turn = 'O' if view.turn == 'X' else 'X'

        # update embed
        embed = view.embed()
        await interaction.response.edit_message(embed=embed, view=view)

        # if playing vs bot and it's bot's turn, make a move
        if view.vs_bot and view.turn == view.bot_mark and not view.finished:
            await view.bot_move()


class TicTacToeView(discord.ui.View):
    def __init__(self, ctx, player_x: int, player_o: int, vs_bot: bool, cog):
        super().__init__(timeout=None)  # No timeout during active gameplay
        self.ctx = ctx
        self.player_x = player_x
        self.player_o = player_o
        self.vs_bot = vs_bot
        self.cog = cog
        self.board = [None] * 9
        self.turn = 'X'
        self.finished = False
        self.bot_mark = 'O' if player_o == cog.bot.user.id else 'X'
        self.message = None
        # game key used for locking active games (frozenset of player ids)
        self.game_key = frozenset({player_x, player_o})

        # add 9 numbered box buttons in a 3x3 grid
        for i in range(9):
            row = i // 3
            self.add_item(BoxButton(i, self, row))

    def embed(self):
        # determine which member's turn it is (if in a guild)
        turn_member = None
        if self.ctx.guild:
            if self.turn == 'X':
                turn_member = self.ctx.guild.get_member(self.player_x)
            else:
                turn_member = self.ctx.guild.get_member(self.player_o)

        emb = discord.Embed(title="TicTacToe", description="Click on the boxes to play", color=0x3498db)
        emb.set_footer(text=f"Turn: {self.turn} - {turn_member.display_name if turn_member else 'Player'}")
        # Set author's profile picture to keep it persistent
        emb.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)
        return emb

    async def bot_move(self):
        # simple bot: pick random empty cell
        empties = [i for i, v in enumerate(self.board) if v is None]
        if not empties:
            return
        choice = random.choice(empties)
        # set board and update button state
        self.board[choice] = self.bot_mark
        for item in self.children:
            if isinstance(item, BoxButton) and item.index == choice:
                item.label = '❌' if self.bot_mark == 'X' else '⭕'
                item.disabled = True
                item.style = discord.ButtonStyle.success if self.bot_mark == 'X' else discord.ButtonStyle.danger
                break

        winner = check_winner(self.board)
        if winner:
            self.finished = True
            # disable all buttons and show final state
            for item in self.children:
                if isinstance(item, BoxButton):
                    item.disabled = True
                    if self.board[item.index] is not None:
                        item.label = '❌' if self.board[item.index] == 'X' else '⭕'
                        item.style = discord.ButtonStyle.success if self.board[item.index] == 'X' else discord.ButtonStyle.danger

            if winner == 'draw':
                title = "TicTacToe - Draw"
                desc = "It's a draw!"
                color = 0x95a5a6
            else:
                winner_id = self.player_x if winner == 'X' else self.player_o
                member = self.ctx.guild.get_member(winner_id) if self.ctx.guild else None
                winner_name = member.display_name if member else 'Player'
                # award Mora to the winner (if not the bot)
                reward = random.randint(200, 600)
                if winner_id != self.cog.bot.user.id:
                    try:
                        data = await get_user_data(winner_id)
                        data['mora'] = data.get('mora', 0) + reward
                        await update_user_data(winner_id, mora=data['mora'])
                    except Exception as e:
                        print(f"Error awarding tic tac toe reward: {e}")

                # check if bot won against player
                if self.vs_bot and winner_id == self.cog.bot.user.id:
                    title = "TicTacToe - You Lose"
                    desc = "You lose. Better luck next time."
                    color = 0xDC143C  # Crimson red
                else:
                    title = f"TicTacToe - {winner_name} wins!"
                    desc = f"{winner_name} wins! Awarded {reward:,} 💰."
                    color = 0x2ecc71
            embed = discord.Embed(title=title, description=desc, color=color)
            embed.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)
            try:
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass
            self.cog.active_games.discard(self.game_key)
            return

        # swap turn back to player
        self.turn = 'O' if self.turn == 'X' else 'X'
        # update the message to show new board state
        try:
            embed = self.embed()
            await self.message.edit(embed=embed, view=self)
        except Exception:
            pass


class ChallengeView(discord.ui.View):
    def __init__(self, ctx, challenger_id: int, opponent_id: int, cog, game_key):
        super().__init__(timeout=120)  # 2 minutes for accepting/declining challenge
        self.ctx = ctx
        self.challenger = challenger_id
        self.opponent = opponent_id
        self.cog = cog
        self.game_key = game_key

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent:
            return await interaction.response.send_message("Only the challenged player may accept.", ephemeral=True)

        # remove pending
        try:
            self.cog.pending_challenges.discard(self.game_key)
        except Exception:
            pass

        # create and start the actual game
        try:
            view = TicTacToeView(self.ctx, self.challenger, self.opponent, False, self.cog)
            view.game_key = self.game_key
            self.cog.active_games.add(self.game_key)
            embed = view.embed()
            # edit the original challenge message to become the game board
            await interaction.response.edit_message(content=None, embed=embed, view=view)
            # interaction.message is the original message object; use it as the view message
            view.message = interaction.message
        except Exception as e:
            print(f"Error starting TicTacToe PvP game: {e}")
            await interaction.response.edit_message(content="Failed to start game.", embed=None, view=None)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent:
            return await interaction.response.send_message("Only the challenged player may decline.", ephemeral=True)
        try:
            self.cog.pending_challenges.discard(self.game_key)
        except Exception:
            pass
        try:
            await interaction.response.edit_message(content=f"{interaction.user.display_name} declined the challenge.", embed=None, view=None)
        except Exception:
            pass

    async def on_timeout(self):
        try:
            self.cog.pending_challenges.discard(self.game_key)
            await self.ctx.send("Challenge timed out.")
        except Exception:
            pass
        


class TicTacToe(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = set()
        self.pending_challenges = set()

    @commands.command(name="tictactoe", aliases=["tt","ttt"])
    async def tictactoe(self, ctx, opponent: discord.Member = None):
        """Start a 3x3 TicTacToe. Usage: !tictactoe [@opponent]
        If no opponent is provided, you play vs the bot.
        Click the gray boxes to play.
        """
        player_x = ctx.author.id
        if opponent and opponent.bot:
            # if opponent is the bot, treat as vs bot
            opponent = None

        if opponent:
            player_o = opponent.id
        else:
            player_o = self.bot.user.id

        game_key = frozenset({player_x, player_o})

        # if playing vs bot, start immediately
        if player_o == self.bot.user.id:
            if game_key in self.active_games:
                await ctx.send("A game between these players is already active in another channel.")
                return
            self.active_games.add(game_key)
            vs_bot = True
            view = TicTacToeView(ctx, player_x, player_o, vs_bot, self)
            view.game_key = game_key
            embed = view.embed()
            message = await send_embed(ctx, embed, view=view)
            view.message = message
            return

        # PvP: send challenge and await accept/decline
        if game_key in self.active_games or game_key in self.pending_challenges:
            await ctx.send("A game or challenge between these players is already active.")
            return

        # create a pending challenge and send accept/decline buttons
        self.pending_challenges.add(game_key)
        chall_embed = discord.Embed(title="TicTacToe Challenge", description=f"{ctx.author.display_name} has challenged {opponent.display_name} to TicTacToe.\n{opponent.mention}, accept?", color=0x3498db)
        view = ChallengeView(ctx, player_x, player_o, self, game_key)
        msg = await send_embed(ctx, chall_embed, view=view)
        view.message = msg


async def setup(bot):
    if bot.get_cog("TicTacToe") is None:
        await bot.add_cog(TicTacToe(bot))
    else:
        print("TicTacToe cog already loaded; skipping add_cog")
