import asyncio
import random
from typing import Optional

import discord
from discord.ext import commands

from utils.database import track_game_stat, check_and_award_game_achievements, add_account_exp
from utils.embed import send_embed


class Connect4Board:
    ROWS = 6
    COLS = 7

    def __init__(self):
        # board[row][col], row 0 is bottom
        self.board = [[0 for _ in range(self.COLS)] for _ in range(self.ROWS)]

    def place(self, col, player):
        """Place a disc for player (1 or 2) in column col. Returns (row,col) or None if column full."""
        if col < 0 or col >= self.COLS:
            return None
        for r in range(self.ROWS):
            if self.board[r][col] == 0:
                self.board[r][col] = player
                return (r, col)
        return None

    def is_full(self):
        return all(self.board[self.ROWS - 1][c] != 0 for c in range(self.COLS))

    def render(self):
        # render top-down with buttons
        emoji = {0: "⬜", 1: "🔴", 2: "🟡"}
        lines = []
        for r in range(self.ROWS - 1, -1, -1):
            line = "".join(emoji[self.board[r][c]] + " " for c in range(self.COLS))
            lines.append(line)
        # add emoji column numbers
        number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]
        lines.append(" ".join(number_emojis))
        return "\n".join(lines)

    def check_win(self, player):
        # check horizontal
        for r in range(self.ROWS):
            count = 0
            for c in range(self.COLS):
                count = count + 1 if self.board[r][c] == player else 0
                if count >= 4:
                    return True
        # check vertical
        for c in range(self.COLS):
            count = 0
            for r in range(self.ROWS):
                count = count + 1 if self.board[r][c] == player else 0
                if count >= 4:
                    return True
        # diagonal checks
        for r in range(self.ROWS):
            for c in range(self.COLS):
                if self._check_direction(r, c, 1, 1, player):
                    return True
                if self._check_direction(r, c, 1, -1, player):
                    return True
        return False

    def _check_direction(self, r, c, dr, dc, player):
        cnt = 0
        for i in range(4):
            rr = r + dr * i
            cc = c + dc * i
            if (
                0 <= rr < self.ROWS
                and 0 <= cc < self.COLS
                and self.board[rr][cc] == player
            ):
                cnt += 1
            else:
                break
        return cnt >= 4


class Connect4View(discord.ui.View):
    def __init__(
        self, board: Connect4Board, players, starter, ctx, cog, timeout: float = 300.0
    ):
        super().__init__(timeout=timeout)
        self.board = board
        # players: [discord.Member, discord.Member]
        self.players = players
        # map 1 -> players[0], 2 -> players[1]
        self.turn = 1
        self.message = None
        self.starter = starter
        self.ctx = ctx
        self.cog = cog
        # create buttons for each column (using box emojis for the board display)
        number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]
        for col in range(self.board.COLS):
            row_index = 0 if col < 5 else 1
            btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=number_emojis[col],
                row=row_index,
            )
            btn.callback = self._make_callback(col)
            self.add_item(btn)

    def _make_callback(self, col):
        async def callback(interaction: discord.Interaction):
            # find which player clicked
            user = interaction.user
            expected = self.players[self.turn - 1]
            if user.id != expected.id:
                await interaction.response.send_message(
                    "It's not your turn.", ephemeral=True
                )
                return
            # place disc in the column (drop to lowest empty slot)
            pos = self.board.place(col, self.turn)
            if pos is None:
                await interaction.response.send_message(
                    "That column is full.", ephemeral=True
                )
                return

            # update embed with visual grid
            desc = self.board.render()
            embed = discord.Embed(
                title=f"Connect 4: {self.players[0].display_name} vs {self.players[1].display_name}",
                description=desc,
            )
            embed.set_author(
                name=self.ctx.author.display_name,
                icon_url=self.ctx.author.display_avatar.url,
            )

            # check win
            if self.board.check_win(self.turn):
                winner = self.players[self.turn - 1]
                loser = self.players[0 if self.turn == 2 else 1]
                embed.color = 0x2ECC71 if self.turn == 1 else 0xDC143C
                
                exp_reward = 0
                leveled_up = False
                new_level = 0
                
                # award XP and track stats for the winner if they're a human (not the bot)
                if not getattr(winner, "bot", False):
                    try:
                        # Track stats
                        await track_game_stat(winner.id, "connect4_wins")
                        await track_game_stat(winner.id, "connect4_plays")
                        await track_game_stat(loser.id, "connect4_plays")
                        
                        # Track multiplayer games if vs player
                        if not getattr(loser, "bot", False):
                            await track_game_stat(winner.id, "multiplayer_games")
                            await track_game_stat(loser.id, "multiplayer_games")
                        
                        await check_and_award_game_achievements(winner.id, self.cog.bot, self.ctx)
                        
                        # Award XP (100 XP for multiplayer win, 60 XP for bot win)
                        exp_reward = 100 if not getattr(loser, "bot", False) else 60
                        leveled_up, new_level, old_level = await add_account_exp(winner.id, exp_reward)
                        
                        if exp_reward > 0:
                            embed.add_field(
                                name="Reward",
                                value=f"Winner received +{exp_reward} XP!",
                                inline=False,
                            )
                        
                        if leveled_up:
                            embed.add_field(
                                name="Level Up!",
                                value=f"<a:arrow:1437968863026479258> You reached level {new_level}!",
                                inline=False,
                            )
                    except Exception as e:
                        print(f"Failed to award XP to winner: {e}")
                
                embed.set_footer(text=f"{winner.display_name} wins!")
                # disable all buttons
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(embed=embed, view=self)
                self.stop()
                return

            # check draw
            if self.board.is_full():
                embed.color = 0x95A5A6
                embed.set_footer(text="It's a draw!")
                
                # Track play stats for both players on draw
                try:
                    await track_game_stat(self.players[0].id, "connect4_plays")
                    await track_game_stat(self.players[1].id, "connect4_plays")
                    if not getattr(self.players[0], "bot", False) and not getattr(self.players[1], "bot", False):
                        await track_game_stat(self.players[0].id, "multiplayer_games")
                        await track_game_stat(self.players[1].id, "multiplayer_games")
                except Exception:
                    pass
                
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(embed=embed, view=self)
                self.stop()
                return

            # next turn
            self.turn = 2 if self.turn == 1 else 1
            next_player = self.players[self.turn - 1]
            # update footer to show whose turn and color
            color = 0xFF0000 if self.turn == 1 else 0xFFD700
            foot = f"{next_player.display_name}'s turn ({'🔴' if self.turn == 1 else '🟡'})"
            embed.color = color
            embed.set_footer(text=foot)

            # disable buttons for full columns
            for idx, item in enumerate(self.children):
                try:
                    item.disabled = self.board.board[self.board.ROWS - 1][idx] != 0
                except Exception:
                    pass

            # first edit to show the player's move
            try:
                await interaction.response.edit_message(embed=embed, view=self)
            except Exception:
                # fallback to editing the message directly if response already used
                if self.message:
                    try:
                        await self.message.edit(embed=embed, view=self)
                    except Exception:
                        pass

            # if it's the bot's turn, make an automated AI move
            if getattr(next_player, "bot", False):
                # small delay to simulate thinking
                await asyncio.sleep(0.6)

                def choose_bot_col():
                    # prefer immediate winning move for bot (player 2)
                    for c in range(self.board.COLS):
                        pos = self.board.place(c, 2)
                        if pos:
                            won = self.board.check_win(2)
                            self.board.board[pos[0]][pos[1]] = 0
                            if won:
                                return c
                    # block player's immediate win
                    for c in range(self.board.COLS):
                        pos = self.board.place(c, 1)
                        if pos:
                            will_win = self.board.check_win(1)
                            self.board.board[pos[0]][pos[1]] = 0
                            if will_win:
                                return c
                    # prefer center column
                    center = self.board.COLS // 2
                    if self.board.board[self.board.ROWS - 1][center] == 0:
                        return center
                    # fallback: random available column
                    avail = [
                        c
                        for c in range(self.board.COLS)
                        if self.board.board[self.board.ROWS - 1][c] == 0
                    ]
                    if not avail:
                        return None
                    return random.choice(avail)

                bot_col = choose_bot_col()
                if bot_col is not None:
                    self.board.place(bot_col, 2)
                    # update embed after bot move
                    desc2 = self.board.render()
                    embed2 = discord.Embed(
                        title=f"Connect 4: {self.players[0].display_name} vs {self.players[1].display_name}",
                        description=desc2,
                    )
                    embed2.set_author(
                        name=self.ctx.author.display_name,
                        icon_url=self.ctx.author.display_avatar.url,
                    )

                    # check bot win
                    if self.board.check_win(2):
                        embed2.color = 0xDC143C
                        winner = self.players[1]
                        embed2.set_footer(text=f"{winner.display_name} (bot) wins!")
                        
                        # Track player's play stat on loss to bot
                        try:
                            await track_game_stat(self.players[0].id, "connect4_plays")
                        except Exception:
                            pass
                        
                        # disable buttons
                        for item in self.children:
                            item.disabled = True
                        # edit message and stop
                        if self.message:
                            try:
                                await self.message.edit(embed=embed2, view=self)
                            except Exception:
                                pass
                        self.stop()
                        return

                    # check draw
                    if self.board.is_full():
                        embed2.color = 0x95A5A6
                        embed2.set_footer(text="It's a draw!")
                        
                        # Track play stats for both players on draw
                        try:
                            await track_game_stat(self.players[0].id, "connect4_plays")
                            await track_game_stat(self.players[1].id, "connect4_plays")
                        except Exception:
                            pass
                        
                        for item in self.children:
                            item.disabled = True
                        if self.message:
                            try:
                                await self.message.edit(embed=embed2, view=self)
                            except Exception:
                                pass
                        self.stop()
                        return

                    # otherwise switch back to human
                    self.turn = 1
                    next_player = self.players[self.turn - 1]
                    color = 0xFF0000 if self.turn == 1 else 0xFFD700
                    foot = f"{next_player.display_name}'s turn ({'🔴' if self.turn == 1 else '🟡'})"
                    embed2.color = color
                    embed2.set_footer(text=foot)
                    # disable buttons for full columns
                    for idx, item in enumerate(self.children):
                        try:
                            item.disabled = (
                                self.board.board[self.board.ROWS - 1][idx] != 0
                            )
                        except Exception:
                            pass
                    if self.message:
                        try:
                            await self.message.edit(embed=embed2, view=self)
                        except Exception:
                            pass

        return callback

    async def on_timeout(self):
        # disable buttons on timeout
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                embed = (
                    self.message.embeds[0]
                    if self.message.embeds
                    else discord.Embed(
                        title="Connect 4", description=self.board.render()
                    )
                )
                embed.set_footer(text="Game timed out.")
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


class Connect4(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # track active connect4 games per channel to avoid duplicates
        self.active_connect4 = {}

    @commands.command(name="connect4", aliases=["c4"])
    async def connect4(self, ctx, opponent: Optional[discord.Member] = None):
        """Start a Connect 4 game. Usage: gconnect4 @opponent
        If no opponent is provided, this will start a local game vs the bot.
        The board is displayed as a visual grid - click buttons to drop your piece.
        """
        import traceback

        try:
            # prevent multiple games per channel
            if ctx.channel.id in self.active_connect4:
                await ctx.send(
                    "⏳ A Connect4 game is already running in this channel. Finish it before starting another."
                )
                return

            if opponent is None or opponent.bot:
                # play vs bot (bot user)
                players = [ctx.author, self.bot.user]
            else:
                if opponent.id == ctx.author.id:
                    await ctx.send(
                        "You can't play against yourself. Mention someone else."
                    )
                    return
                players = [ctx.author, opponent]

            board = Connect4Board()
            view = Connect4View(board, players, ctx.author, ctx, self)
            self.active_connect4[ctx.channel.id] = view

            embed = discord.Embed(
                title=f"Connect 4: {players[0].display_name} vs {players[1].display_name}",
                description=board.render(),
                color=0xFF0000,
            )
            embed.set_footer(text=f"{players[0].display_name}'s turn (Red)")
            embed.set_author(
                name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url
            )

            message = await send_embed(ctx, embed, view=view)
            view.message = message

            # wait for view to finish (timeout or win)
            await view.wait()
            # cleanup
            if ctx.channel.id in self.active_connect4:
                del self.active_connect4[ctx.channel.id]
        except Exception as e:
            tb = traceback.format_exc()
            # send a short error message back to the channel to help debugging
            short = str(e)
            try:
                await ctx.send(f"Error running connect4 command: {short}")
                # also send first 1500 chars of traceback if available
                await ctx.send(f"```\n{tb[:1500]}\n```")
            except Exception:
                # fall back to printing
                print("Error sending traceback to channel")
                print(tb)


async def setup(bot):
    await bot.add_cog(Connect4(bot))
