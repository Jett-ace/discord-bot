import random
import discord
import asyncio
from discord.ext import commands
from typing import Optional
from utils.database import add_chest, add_chest_with_type, get_user_data, update_user_data
from utils.chest_config import RPS as RPS_CHEST_CONFIG
from utils.embed import send_embed
from collections import defaultdict
from datetime import datetime, timedelta


class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # track active connect4 games per channel to avoid duplicates
        self.active_connect4 = {}
        # RPS cooldown tracking: {user_id: [timestamp1, timestamp2, ...]}
        self.rps_plays = defaultdict(list)

    @commands.command()
    async def rps(self, ctx, user_choice: str):
        """Play rock-paper-scissors. Winners get Mora and 50% chance for a <:random:1437977751520018452> random chest. Limited to 5 plays per 5 minutes."""
        # Check cooldown (5 plays per 5 minutes)
        user_id = ctx.author.id
        now = datetime.now()
        cutoff = now - timedelta(minutes=5)
        
        # Remove plays older than 5 minutes
        self.rps_plays[user_id] = [t for t in self.rps_plays[user_id] if t > cutoff]
        
        # Check if user has played 5 times in the last 5 minutes
        if len(self.rps_plays[user_id]) >= 5:
            # Find when the oldest play will expire
            oldest = self.rps_plays[user_id][0]
            wait_time = (oldest + timedelta(minutes=5)) - now
            minutes = int(wait_time.total_seconds() // 60)
            seconds = int(wait_time.total_seconds() % 60)
            await ctx.send(f"⏳ You've played 5 times already! Wait {minutes}m {seconds}s before playing again.")
            return
        
        user_choice = user_choice.lower()
        rpsgame = ['rock', 'paper', 'scissors']
        if user_choice not in rpsgame:
            await ctx.send('Use: !rps rock | paper | scissors')
            return

        # Record this play
        self.rps_plays[user_id].append(now)

        bot_choice = random.choice(rpsgame)

        # Choice icons
        choice_icons = {
            'rock': '🪨',
            'paper': '📜',
            'scissors': '✂️'
        }

        # determine result
        if user_choice == bot_choice:
            color = 0xFFA500  # Orange for tie
            result = "It's a tie! 🤝"
        elif (user_choice == 'rock' and bot_choice == 'scissors') or \
             (user_choice == 'paper' and bot_choice == 'rock') or \
             (user_choice == 'scissors' and bot_choice == 'paper'):
            color = 0x9B59B6  # Dark Purple for win
            
            # Award Mora (500-900)
            mora_reward = random.randint(500, 900)
            try:
                data = await get_user_data(ctx.author.id)
                data['mora'] += mora_reward
                await update_user_data(ctx.author.id, mora=data['mora'])
            except Exception:
                mora_reward = 0
            
            # 50% chance to get 1 random chest
            chest_awarded = None
            if random.random() < 0.50:
                # Random chest type
                chest_types = ['common', 'exquisite', 'precious', 'luxurious']
                chest_type = random.choice(chest_types)
                try:
                    await add_chest_with_type(ctx.author.id, chest_type, 1)
                    chest_awarded = chest_type
                except Exception:
                    chest_awarded = None
            
            # Chest icons
            chest_icons = {
                'common': '<:cajitadelexplorador:1437473147833286676>',
                'exquisite': '<:cajitaplatino:1437473086571286699>',
                'precious': '<:cajitapremium:1437473125095837779>',
                'luxurious': '<:cajitadiamante:1437473169475764406>'
            }
            
            # Build result message
            reward_parts = []
            if mora_reward > 0:
                reward_parts.append(f"{mora_reward:,} <:mora:1437958309255577681>")
            if chest_awarded:
                icon = chest_icons.get(chest_awarded, '')
                reward_parts.append(f"{icon} 1x {chest_awarded} chest")
            
            reward_msg = ", ".join(reward_parts) if reward_parts else "nothing this time"
            result = f"You won! 👑\nYou received: {reward_msg}."
        else:
            color = 0xDC143C  # Crimson for loss
            result = "I won!"

        embed = discord.Embed(title="Rock Paper Scissors 🎲", color=color)
        embed.add_field(name="Your Choice", value=f"{choice_icons[user_choice]} {user_choice.capitalize()}", inline=True)
        embed.add_field(name="Bot Choice", value=f"{choice_icons[bot_choice]} {bot_choice.capitalize()}", inline=True)
        embed.add_field(name="Result", value=result, inline=False)
        
        # Show remaining plays
        plays_left = 5 - len(self.rps_plays[user_id])
        embed.set_footer(text=f"Plays remaining: {plays_left}/5")
        
        await send_embed(ctx, embed)

    @commands.command()
    async def ping(self, ctx):
        """Simple ping command to check bot responsiveness."""
        await ctx.send("pong")

    @commands.command(name="connect4", aliases=["c4"])
    async def connect4(self, ctx, opponent: Optional[discord.Member] = None):
        """Start a Connect 4 game. Usage: !connect4 @opponent
        If no opponent is provided, this will start a local game vs the bot.
        The board is displayed as a visual grid - click buttons to drop your piece.
        """
        import traceback
        try:
            # prevent multiple games per channel
            if ctx.channel.id in self.active_connect4:
                await ctx.send("A Connect4 game is already running in this channel. Finish it before starting another.")
                return

            if opponent is None or opponent.bot:
                # play vs bot (bot user)
                players = [ctx.author, self.bot.user]
            else:
                if opponent.id == ctx.author.id:
                    await ctx.send("You can't play against yourself. Mention someone else.")
                    return
                players = [ctx.author, opponent]

            board = Connect4Board()
            view = Connect4View(board, players, ctx.author, ctx)
            self.active_connect4[ctx.channel.id] = view

            embed = discord.Embed(
                title=f"Connect 4: {players[0].display_name} vs {players[1].display_name}",
                description=board.render(),
                color=0xff0000
            )
            embed.set_footer(text=f"{players[0].display_name}'s turn (🔴)")
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            
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

    @commands.command(name="flip", aliases=["coin", "cf"]) 
    async def flip(self, ctx, choice: str, amount: str):
        """Flip a coin and bet Mora. You must pick 'heads' or 'tails'.
        If your pick matches the flip result you win your bet (net +bet), otherwise you lose it.
        Usage: !flip heads 1000 or !flip tails all
        Min bet: 1,000 | Max bet: 200,000
        """
        try:
            MIN_BET = 1_000
            MAX_BET = 200_000
            
            choice = choice.lower()
            # accept a few shorthand forms
            if choice in ('h', 'head'):
                choice = 'heads'
            elif choice in ('t', 'tail'):
                choice = 'tails'

            if choice not in ('heads', 'tails'):
                await ctx.send("Use: `!flip heads <amount>` or `!flip tails <amount>`")
                return

            # allow 'all' to bet entire balance
            data = await get_user_data(ctx.author.id)
            mora = data.get('mora', 0)

            if isinstance(amount, str) and amount.lower() == 'all':
                if mora <= 0:
                    await ctx.send("You don't have any Mora to bet.")
                    return
                bet = min(mora, MAX_BET)  # Cap at max bet
                if bet < MIN_BET:
                    await ctx.send(f"You need at least {MIN_BET:,} <:mora:1437958309255577681> to play.")
                    return
            else:
                # try parsing integer amount (allow commas)
                try:
                    bet = int(str(amount).replace(',', ''))
                except Exception:
                    await ctx.send("Please specify a valid number to bet, or use `all` to bet everything.")
                    return

                if bet < MIN_BET:
                    await ctx.send(f"Minimum bet is {MIN_BET:,} <:mora:1437958309255577681>.")
                    return
                if bet > MAX_BET:
                    await ctx.send(f"Maximum bet is {MAX_BET:,} <:mora:1437958309255577681>.")
                    return
                if bet > mora:
                    await ctx.send(f"You dont have enough mora.")
                    return

            # flip result
            flip_result = random.choice(['heads', 'tails'])
            won = (flip_result == choice)

            if won:
                # win: user gains amount (net +bet)
                new_mora = mora + bet
                await update_user_data(ctx.author.id, mora=new_mora)
                await ctx.send(f"You chose **{choice}**. The coin landed **{flip_result}** - You won {bet:,} <:mora:1437958309255577681>!")
            else:
                new_mora = mora - bet
                await update_user_data(ctx.author.id, mora=new_mora)
                await ctx.send(f"You chose **{choice}**. The coin landed **{flip_result}** - You lost {bet:,} <:mora:1437958309255577681>. Better luck next time.")
        except Exception as e:
            print(f"Error in flip command: {e}")
            await ctx.send("There was an error processing your coin flip.")

    @commands.command(name="mines")
    async def mines(self, ctx, bet: str):
        """Start a 4x4 mines game. Usage: `!mines <bet>` or `!mines all`
        Each non-bomb box is a money box (<:mora:1437958309255577681>). There are 3 bombs by default.
        Bet may be an integer (commas allowed) or the literal `all` to bet your full balance.
        Cash out anytime with the Finish button.
        Min bet: 1,000 | Max bet: 200,000
        """
        try:
            # validate bet
            MIN_BET = 1_000
            MAX_BET = 200_000
            
            # parse bet: allow 'all' or integer strings (commas allowed)
            data = await get_user_data(ctx.author.id)
            mora = data.get('mora', 0)
            
            if isinstance(bet, str) and bet.lower() == 'all':
                bet_amount = min(mora, MAX_BET)  # Cap at max bet
                if bet_amount < MIN_BET:
                    await ctx.send(f"You need at least {MIN_BET:,} <:mora:1437958309255577681> to play.")
                    return
            else:
                try:
                    bet_amount = int(str(bet).replace(',', ''))
                except Exception:
                    await ctx.send("Please specify a valid integer bet or use `all` to bet your full balance.")
                    return

            if bet_amount < MIN_BET:
                await ctx.send(f"Minimum bet is {MIN_BET:,} <:mora:1437958309255577681>.")
                return
            if bet_amount > MAX_BET:
                await ctx.send(f"Maximum bet is {MAX_BET:,} <:mora:1437958309255577681>.")
                return
            if mora < bet_amount:
                await ctx.send("You don't have enough Mora to place that bet.")
                return

            # deduct bet up-front (escrow)
            await update_user_data(ctx.author.id, mora=mora - bet_amount)

            # settle callback: credit payout (amount) back to user if won cashout, or zero on loss
            async def settle_cb(user, amount: int, won: bool):
                try:
                    # credit amount to user's mora
                    if amount and amount > 0:
                        ud = await get_user_data(user.id)
                        await update_user_data(user.id, mora=ud.get('mora', 0) + int(amount))
                    # (no DM) result notification is intentionally suppressed to avoid sending users DMs
                except Exception as e:
                    print(f"Error in mines settle_cb: {e}")

            # create game and view
            from typing import Optional
            game = MinesGame(ctx.author, bet_amount, bombs=3, size=4, settle_cb=settle_cb)
            view = MinesView(game)
            embed = view.make_embed()
            await send_embed(ctx, embed, view=view)
        except Exception as e:
            print(f"Error starting mines: {e}")
            await ctx.send("Failed to start Mines.")

    @commands.command(name="slots", aliases=["slot", "slotmachine"])
    async def slots(self, ctx, bet: str):
        """Play the slot machine! Match 3 symbols to win big. Usage: `!slots <bet>` or `!slots all`
        Min bet: 1,000 | Max bet: 200,000
        
        Payouts:
        🍒🍒🍒 - 2x
        🍋🍋🍋 - 3x
        🍊🍊🍊 - 5x
        🍇🍇🍇 - 10x
        💎💎💎 - 20x
        7️⃣7️⃣7️⃣ - 50x (JACKPOT!)
        """
        try:
            MIN_BET = 1_000
            MAX_BET = 200_000
            
            # Parse bet
            data = await get_user_data(ctx.author.id)
            mora = data.get('mora', 0)
            
            if isinstance(bet, str) and bet.lower() == 'all':
                bet_amount = min(mora, MAX_BET)  # Cap at max bet
                if bet_amount < MIN_BET:
                    await ctx.send(f"You need at least {MIN_BET:,} <:mora:1437958309255577681> to play.")
                    return
            else:
                try:
                    bet_amount = int(str(bet).replace(',', ''))
                except Exception:
                    await ctx.send("Please specify a valid integer bet or use `all`.")
                    return

            if bet_amount < MIN_BET:
                await ctx.send(f"Minimum bet is {MIN_BET:,} <:mora:1437958309255577681>.")
                return
            if bet_amount > MAX_BET:
                await ctx.send(f"Maximum bet is {MAX_BET:,} <:mora:1437958309255577681>.")
                return
            if mora < bet_amount:
                await ctx.send("You don't have enough Mora for that bet.")
                return

            # Slot symbols with weighted probabilities (no luck bonus)
            symbols = {
                '🍒': 40,  # 40% chance per reel
                '🍋': 30,  # 30% chance
                '🍊': 15,  # 15% chance
                '🍇': 8,   # 8% chance
                '💎': 5,   # 5% chance
                '7️⃣': 2   # 2% chance (jackpot)
            }
            
            # Create weighted list
            symbol_pool = []
            for symbol, weight in symbols.items():
                symbol_pool.extend([symbol] * weight)
            
            # Spin the slots
            reel1 = random.choice(symbol_pool)
            reel2 = random.choice(symbol_pool)
            reel3 = random.choice(symbol_pool)
            
            # Check for win
            payout_multipliers = {
                '🍒': 2,
                '🍋': 3,
                '🍊': 5,
                '🍇': 10,
                '💎': 20,
                '7️⃣': 50
            }
            
            if reel1 == reel2 == reel3:
                # Win!
                multiplier = payout_multipliers.get(reel1, 2)
                payout = bet_amount * multiplier
                new_mora = mora - bet_amount + payout
                await update_user_data(ctx.author.id, mora=new_mora)
                
                embed = discord.Embed(title="🎰 Slot Machine", color=0xFFD700)
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
                embed.description = f"**[ {reel1} | {reel2} | {reel3} ]**"
                
                if reel1 == '7️⃣':
                    embed.add_field(name="🎉 JACKPOT!", value=f"Won {payout:,} <:mora:1437958309255577681> ({multiplier}x)", inline=False)
                else:
                    embed.add_field(name="🎉 Winner!", value=f"Won {payout:,} <:mora:1437958309255577681> ({multiplier}x)", inline=False)
                
                embed.add_field(name="Net Profit", value=f"+{payout - bet_amount:,} <:mora:1437958309255577681>", inline=True)
            else:
                # Loss
                new_mora = mora - bet_amount
                await update_user_data(ctx.author.id, mora=new_mora)
                
                embed = discord.Embed(title="🎰 Slot Machine", color=0x95a5a6)
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
                embed.description = f"**[ {reel1} | {reel2} | {reel3} ]**"
                embed.add_field(name="No match", value=f"Lost {bet_amount:,} <:mora:1437958309255577681>", inline=False)
            
            await send_embed(ctx, embed)
            
        except Exception as e:
            print(f"Error in slots command: {e}")
            await ctx.send("There was an error with the slot machine.")

    @commands.command(name="wheel", aliases=["spin"])
    async def wheel_of_fortune(self, ctx, bet: str = None):
        """Spin the wheel of fortune!
        Usage: `!wheel <bet>` or `!wheel all`
        min bet: 1,000 | max bet: 200,000

        prizes: 
        💸 Bankrupt - Lose bet
        🎯 0.5x - Half back
        💰 1x - Money back
        💎 2x - Double
        💵 5x - 5x win
        🌟 10x - 10x win
        👑 JACKPOT - 50x win!
        """
        try:
            MIN_BET = 1_000
            MAX_BET = 200_000

            # Show help embed if no bet provided
            if bet is None:
                embed = discord.Embed(
                    title="🎡 Wheel of Fortune",
                    description="Spin the wheel and test your luck!",
                    color=0xf1c40f
                )
                embed.add_field(
                    name="📋 How to Play",
                    value=f"Use `!wheel <amount>` or `!wheel all`\n"
                          f"**Min bet:** {MIN_BET:,} <:mora:1437958309255577681>\n"
                          f"**Max bet:** {MAX_BET:,} <:mora:1437958309255577681>",
                    inline=False
                )
                embed.add_field(
                    name="🎯 Possible Outcomes",
                    value="💸 **Bankrupt** (15%) - Lose everything\n"
                          "🎯 **0.5x** (30%) - Get half back\n"
                          "💰 **1x** (25%) - Break even\n"
                          "💎 **2x** (15%) - Double your bet\n"
                          "💵 **5x** (10%) - 5x profit\n"
                          "🌟 **10x** (4%) - 10x profit\n"
                          "👑 **JACKPOT 50x** (1%) - Massive win!",
                    inline=False
                )
                embed.add_field(
                    name="💡 Examples",
                    value="`!wheel 5000` - Bet 5,000 Mora\n"
                          "`!wheel all` - Bet your max (up to 200k)",
                    inline=False
                )
                embed.set_footer(text="Good luck!")
                return await ctx.send(embed=embed)

            data = await get_user_data(ctx.author.id)
            mora = data.get('mora', 0)

            if isinstance(bet, str) and bet.lower() == 'all':
                bet_amount = min(mora, MAX_BET)
                if bet_amount < MIN_BET:
                    await ctx.send(f"You need at least {MIN_BET:,} <:mora:1437958309255577681> to play.")
                    return 
            
            else:
                try:
                    bet_amount = int(str(bet).replace(',', ''))
                except Exception:
                    await ctx.send("Please specify a valid integer bet or use `all`.")
                    return

            if bet_amount < MIN_BET:
                await ctx.send(f"Minimum bet is {MIN_BET:,} <:mora:1437958309255577681>.")
                return
            if bet_amount > MAX_BET:
                await ctx.send(f"Maximum bet is {MAX_BET:,} <:mora:1437958309255577681>.")
                return
            if mora < bet_amount:
                await ctx.send("You don't have enough Mora for that bet.")
                return
            
            await update_user_data(ctx.author.id, mora=mora - bet_amount)

            segments = [
                ("💸 Bankrupt", 0, 15),
                ("🎯 0.5x", 0.5, 30),
                ("💰 1x", 1, 25),
                ("💎 2x", 2, 15),
                ("💵 5x", 5, 10),
                ("🌟 10x", 10, 4),
                ("👑 JACKPOT", 50, 1)
            ]

            wheel_pool = []
            for segment, multiplier, weight in segments:
                wheel_pool.extend([(segment, multiplier)] * weight)

            spin_msg = await ctx.send("**Spinning the wheel...** 🎡")
            await asyncio.sleep(1)

            for i in range(3):
                random_seg = random.choice(wheel_pool)
                await spin_msg.edit(content=f"🎡 **Spinning the wheel...** {random_seg[0]}")
                await asyncio.sleep(0.5)

            result_segment, multiplier = random.choice(wheel_pool)

            if multiplier == 0:
                payout = 0
                color = 0x95a5a6
                result_text = f"You landed on {result_segment} and lost your bet of {bet_amount:,} <:mora:1437958309255577681>."
            elif multiplier < 1:
                payout = int(bet_amount * multiplier)
                color = 0xe67e22
                result_text = f"You landed on {result_segment} and got back {payout:,} <:mora:1437958309255577681>."
            elif multiplier == 1:
                payout = bet_amount
                color = 0x3498db
                result_text = f"You landed on {result_segment} and got your bet of {bet_amount:,} <:mora:1437958309255577681> back."
            elif multiplier == 50:
                payout = int(bet_amount * multiplier)
                color = 0xf1c40f
                result_text = f"🎉 **{result_segment}!!!** 🎉\nYou won {payout:,} <:mora:1437958309255577681>!\nNet profit: +{payout - bet_amount:,} <:mora:1437958309255577681>"
            else:
                payout = int(bet_amount * multiplier)
                color = 0x2ecc71
                result_text = f"You landed on {result_segment} and won {payout:,} <:mora:1437958309255577681>!\nNet profit: +{payout - bet_amount:,} <:mora:1437958309255577681>"

            if payout > 0:
                data = await get_user_data(ctx.author.id)
                await update_user_data(ctx.author.id, mora=data.get('mora', 0) + payout)

            embed = discord.Embed(
                title="🎡 Wheel of Fortune",
                description=result_text,
                color=color
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)  
            embed.add_field(name="Bet", value=f"{bet_amount:,} <:mora:1437958309255577681>", inline=True)
            embed.add_field(name="Multiplier", value=f"{multiplier}x", inline=True)

            embed.set_footer(text="Outcomes: Bankrupt (15%) | 0.5x (30%) | 1x (25%) | 2x (15%) | 5x (10%) | 10x (4%) | JACKPOT (1%)")

            await spin_msg.edit(content=None, embed=embed)

        except Exception as e:
            print(f"Error in wheel command: {e}")
            await ctx.send("There was an error with the Wheel of Fortune.")


async def setup(bot):
    if bot.get_cog("Games") is None:
        await bot.add_cog(Games(bot))
    else:
        print("Games cog already loaded; skipping add_cog")


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
        emoji = {0: '⬜', 1: '🔴', 2: '🟡'}
        lines = []
        for r in range(self.ROWS - 1, -1, -1):
            line = ''.join(emoji[self.board[r][c]] + ' ' for c in range(self.COLS))
            lines.append(line)
        # add emoji column numbers
        number_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣']
        lines.append(' '.join(number_emojis))
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
            if 0 <= rr < self.ROWS and 0 <= cc < self.COLS and self.board[rr][cc] == player:
                cnt += 1
            else:
                break
        return cnt >= 4


class Connect4View(discord.ui.View):
    def __init__(self, board: Connect4Board, players, starter, ctx, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.board = board
        # players: [discord.Member, discord.Member]
        self.players = players
        # map 1 -> players[0], 2 -> players[1]
        self.turn = 1
        self.message = None
        self.starter = starter
        self.ctx = ctx
        # create buttons for each column (using box emojis for the board display)
        number_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣']
        for col in range(self.board.COLS):
            row_index = 0 if col < 5 else 1
            btn = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji=number_emojis[col], row=row_index)
            btn.callback = self._make_callback(col)
            self.add_item(btn)

    def _make_callback(self, col):
        async def callback(interaction: discord.Interaction):
            # find which player clicked
            user = interaction.user
            expected = self.players[self.turn - 1]
            if user.id != expected.id:
                await interaction.response.send_message("It's not your turn.", ephemeral=True)
                return
            # place disc in the column (drop to lowest empty slot)
            pos = self.board.place(col, self.turn)
            if pos is None:
                await interaction.response.send_message("That column is full.", ephemeral=True)
                return

            # update embed with visual grid
            desc = self.board.render()
            embed = discord.Embed(title=f"Connect 4: {self.players[0].display_name} vs {self.players[1].display_name}", description=desc)
            embed.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)

            # check win
            if self.board.check_win(self.turn):
                winner = self.players[self.turn - 1]
                embed.color = 0x2ecc71 if self.turn == 1 else 0xDC143C
                embed.set_footer(text=f"{winner.display_name} wins!")
                # award a chest to the winner if they're a human (not the bot)
                if not getattr(winner, 'bot', False):
                    try:
                        await add_chest_with_type(winner.id, 'common', 1)
                        embed.add_field(name="Reward", value="Winner received <:cajitadelexplorador:1437473147833286676> 1 Common Chest!", inline=False)
                    except Exception as e:
                        print(f"Failed to award chest to winner: {e}")
                # disable all buttons
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(embed=embed, view=self)
                self.stop()
                return

            # check draw
            if self.board.is_full():
                embed.color = 0x95a5a6
                embed.set_footer(text="It's a draw!")
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(embed=embed, view=self)
                self.stop()
                return

            # next turn
            self.turn = 2 if self.turn == 1 else 1
            next_player = self.players[self.turn - 1]
            # update footer to show whose turn and color
            color = 0xff0000 if self.turn == 1 else 0xffd700
            foot = f"{next_player.display_name}'s turn ({'🔴' if self.turn==1 else '🟡'})"
            embed.color = color
            embed.set_footer(text=foot)

            # disable buttons for full columns
            for idx, item in enumerate(self.children):
                try:
                    item.disabled = (self.board.board[self.board.ROWS - 1][idx] != 0)
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
            if getattr(next_player, 'bot', False):
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
                    avail = [c for c in range(self.board.COLS) if self.board.board[self.board.ROWS - 1][c] == 0]
                    if not avail:
                        return None
                    return random.choice(avail)

                bot_col = choose_bot_col()
                if bot_col is not None:
                    bot_pos = self.board.place(bot_col, 2)
                    # update embed after bot move
                    desc2 = self.board.render()
                    embed2 = discord.Embed(title=f"Connect 4: {self.players[0].display_name} vs {self.players[1].display_name}", description=desc2)
                    embed2.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)

                    # check bot win
                    if self.board.check_win(2):
                        embed2.color = 0xDC143C
                        winner = self.players[1]
                        embed2.set_footer(text=f"{winner.display_name} (bot) wins!")
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
                        embed2.color = 0x95a5a6
                        embed2.set_footer(text="It's a draw!")
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
                    color = 0xff0000 if self.turn == 1 else 0xffd700
                    foot = f"{next_player.display_name}'s turn ({'🔴' if self.turn==1 else '🟡'})"
                    embed2.color = color
                    embed2.set_footer(text=foot)
                    # disable buttons for full columns
                    for idx, item in enumerate(self.children):
                        try:
                            item.disabled = (self.board.board[self.board.ROWS - 1][idx] != 0)
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
                embed = self.message.embeds[0] if self.message.embeds else discord.Embed(title="Connect 4", description=self.board.render())
                embed.set_footer(text="Game timed out.")
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


# --- Minesweeper-style mini-game (4x4, 3 bombs) ---
BOMB = "💣"
MONEY = "💰"


class MinesGame:
    def __init__(self, user: discord.User, bet: int, bombs: int = 3, size: int = 4, settle_cb=None):
        self.user = user
        self.bet = int(bet)
        self.bombs = int(bombs)
        self.size = size
        self.total_cells = size * size
        bomb_positions = set(random.sample(range(self.total_cells), self.bombs))
        self.grid = [BOMB if i in bomb_positions else MONEY for i in range(self.total_cells)]
        self.revealed = set()
        self.finished = False
        self.settle_cb = settle_cb

    @property
    def found_money_count(self):
        return sum(1 for i in self.revealed if self.grid[i] == MONEY)

    @property
    def potential_payout(self):
        # multiplier increases per found money box: 1.0 + 0.2 per box
        multiplier = 1.0 + 0.2 * self.found_money_count
        return int(self.bet * multiplier)

    def reveal_index(self, idx: int):
        if self.finished:
            return None, False
        if idx in self.revealed:
            return self.grid[idx], False
        self.revealed.add(idx)
        if self.grid[idx] == BOMB:
            self.finished = True
            return BOMB, True
        return MONEY, False

    def reveal_all_bombs(self):
        return [i for i, v in enumerate(self.grid) if v == BOMB]


class MinesButton(discord.ui.Button):
    def __init__(self, index: int, view: "MinesView", row: int):
        label = str(index + 1)
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=row)
        self.index = index
        self.mines_view = view

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.mines_view
        game = view.game

        if interaction.user.id != game.user.id:
            await interaction.response.send_message("This is not your game.", ephemeral=True)
            return

        if game.finished:
            await interaction.response.send_message("This game has finished.", ephemeral=True)
            return

        value, lost = game.reveal_index(self.index)

        self.disabled = True
        self.label = value
        
        # Red for bomb, green for money, gray for empty
        if value == BOMB:
            self.style = discord.ButtonStyle.danger  # Red
        elif value == MONEY:
            self.style = discord.ButtonStyle.success  # Green
        else:
            self.style = discord.ButtonStyle.secondary  # Gray

        if lost:
            # Reveal all boxes
            for item in view.children:
                if isinstance(item, MinesButton):
                    val = game.grid[item.index]
                    item.label = val
                    # Red for bombs, green for money
                    if val == BOMB:
                        item.style = discord.ButtonStyle.danger
                    elif val == MONEY:
                        item.style = discord.ButtonStyle.success
                    else:
                        item.style = discord.ButtonStyle.secondary
                    item.disabled = True
            game.finished = True

            embed = view.make_embed(title="Boom! You hit a bomb 💥", finished=True)
            await interaction.response.edit_message(embed=embed, view=view)
            if game.settle_cb:
                try:
                    await game.settle_cb(game.user, 0, False)
                except Exception:
                    pass
            return

        embed = view.make_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class FinishButton(discord.ui.Button):
    def __init__(self, view: "MinesView", row: int):
        super().__init__(label="Finish", style=discord.ButtonStyle.secondary, row=row)
        self.mines_view = view

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.mines_view
        game = view.game

        if interaction.user.id != game.user.id:
            await interaction.response.send_message("This is not your game.", ephemeral=True)
            return

        if game.finished:
            await interaction.response.send_message("This game has already ended.", ephemeral=True)
            return

        payout = game.potential_payout
        game.finished = True

        # Reveal all boxes
        for item in view.children:
            if isinstance(item, MinesButton):
                val = game.grid[item.index]
                item.label = val
                # Red for bombs, green for money
                if val == BOMB:
                    item.style = discord.ButtonStyle.danger
                elif val == MONEY:
                    item.style = discord.ButtonStyle.success
                else:
                    item.style = discord.ButtonStyle.secondary
                item.disabled = True
            elif isinstance(item, FinishButton):
                item.disabled = True

        embed = view.make_embed(title="Cashed out <a:Check:1437951818452832318>", finished=True)
        await interaction.response.edit_message(embed=embed, view=view)

        if game.settle_cb:
            try:
                await game.settle_cb(game.user, payout, True)
            except Exception:
                pass


class MinesView(discord.ui.View):
    def __init__(self, game: MinesGame):
        super().__init__(timeout=None)
        self.game = game
        size = game.size

        for i in range(size):
            for j in range(size):
                idx = i * size + j
                if idx in game.revealed:
                    val = game.grid[idx]
                    style = discord.ButtonStyle.success if val == MONEY else discord.ButtonStyle.danger
                    btn = MinesButton(index=idx, view=self, row=i)
                    btn.label = val
                    btn.disabled = True
                    btn.style = style
                else:
                    btn = MinesButton(index=idx, view=self, row=i)
                self.add_item(btn)

        finish_row = size
        finish_btn = FinishButton(view=self, row=finish_row)
        self.add_item(finish_btn)

    def make_embed(self, title: str = None, finished: bool = False) -> discord.Embed:
        game = self.game
        title = title or "Mines - Avoid Bombs"
        embed = discord.Embed(title=title, color=0x2ecc71 if not finished else 0x3498db)
        embed.set_author(name=game.user.display_name, icon_url=game.user.display_avatar.url)
        embed.add_field(name="Bet", value=f"{game.bet:,}", inline=True)
        multiplier = 1.0 + 0.2 * game.found_money_count
        embed.add_field(name="Multiplier", value=f"{multiplier:.1f}x", inline=True)
        embed.add_field(name="Potential Payout", value=f"{game.potential_payout:,}", inline=True)
        if finished:
            if any(game.grid[i] == BOMB for i in game.revealed):
                embed.description = "You hit a bomb. Better luck next time!"
            else:
                embed.description = f"You cashed out {game.potential_payout:,} <:mora:1437958309255577681>."
        else:
            embed.description = "Click boxes to reveal. Cash out anytime using the Finish button. If you hit a bomb you lose everything."
        return embed