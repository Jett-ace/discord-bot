import discord
from discord.ext import commands
import aiosqlite
import asyncio
import random
from datetime import datetime
from config import DB_PATH
from utils.database import get_user_data, update_user_data, require_enrollment
from utils.embed import send_embed

# Easy trivia questions database with math
TRIVIA_QUESTIONS = [
    # Math Questions (40 questions)
    {"question": "What is 5 + 3?", "answer": "8"},
    {"question": "What is 10 - 4?", "answer": "6"},
    {"question": "What is 2 x 5?", "answer": "10"},
    {"question": "What is 15 + 5?", "answer": "20"},
    {"question": "What is 7 + 8?", "answer": "15"},
    {"question": "What is 20 - 10?", "answer": "10"},
    {"question": "What is 3 x 4?", "answer": "12"},
    {"question": "What is 12 + 8?", "answer": "20"},
    {"question": "What is 25 - 5?", "answer": "20"},
    {"question": "What is 6 x 2?", "answer": "12"},
    {"question": "What is 9 + 9?", "answer": "18"},
    {"question": "What is 30 - 15?", "answer": "15"},
    {"question": "What is 5 x 5?", "answer": "25"},
    {"question": "What is 100 - 50?", "answer": "50"},
    {"question": "What is 8 + 7?", "answer": "15"},
    {"question": "What is 4 x 3?", "answer": "12"},
    {"question": "What is 13 + 7?", "answer": "20"},
    {"question": "What is 40 - 20?", "answer": "20"},
    {"question": "What is 7 x 2?", "answer": "14"},
    {"question": "What is 11 + 9?", "answer": "20"},
    {"question": "What is 50 - 25?", "answer": "25"},
    {"question": "What is 10 x 2?", "answer": "20"},
    {"question": "What is 6 + 6?", "answer": "12"},
    {"question": "What is 18 - 9?", "answer": "9"},
    {"question": "What is 3 x 3?", "answer": "9"},
    {"question": "What is 14 + 6?", "answer": "20"},
    {"question": "What is 35 - 15?", "answer": "20"},
    {"question": "What is 8 x 2?", "answer": "16"},
    {"question": "What is 17 + 3?", "answer": "20"},
    {"question": "What is 60 - 30?", "answer": "30"},
    {"question": "What is 9 x 2?", "answer": "18"},
    {"question": "What is 12 + 12?", "answer": "24"},
    {"question": "What is 45 - 20?", "answer": "25"},
    {"question": "What is 6 x 3?", "answer": "18"},
    {"question": "What is 19 + 1?", "answer": "20"},
    {"question": "What is 70 - 40?", "answer": "30"},
    {"question": "What is 4 x 5?", "answer": "20"},
    {"question": "What is 16 + 4?", "answer": "20"},
    {"question": "What is 80 - 50?", "answer": "30"},
    {"question": "What is 11 x 2?", "answer": "22"},
    
    # Easy General Knowledge (30 questions)
    {"question": "What color is the sky?", "answer": "BLUE"},
    {"question": "What color is grass?", "answer": "GREEN"},
    {"question": "How many days in a week?", "answer": "7"},
    {"question": "What animal says meow?", "answer": "CAT"},
    {"question": "What animal says woof?", "answer": "DOG"},
    {"question": "What do bees make?", "answer": "HONEY"},
    {"question": "What is frozen water?", "answer": "ICE"},
    {"question": "What color is a banana?", "answer": "YELLOW"},
    {"question": "How many legs does a cat have?", "answer": "4"},
    {"question": "What is the opposite of hot?", "answer": "COLD"},
    {"question": "What color is snow?", "answer": "WHITE"},
    {"question": "What do cows give us to drink?", "answer": "MILK"},
    {"question": "How many fingers on one hand?", "answer": "5"},
    {"question": "What animal has a trunk?", "answer": "ELEPHANT"},
    {"question": "What color is an apple?", "answer": "RED"},
    {"question": "How many eyes do you have?", "answer": "2"},
    {"question": "What do birds use to fly?", "answer": "WINGS"},
    {"question": "What season comes after winter?", "answer": "SPRING"},
    {"question": "How many wheels on a car?", "answer": "4"},
    {"question": "What animal has 8 legs?", "answer": "SPIDER"},
    {"question": "What do fish live in?", "answer": "WATER"},
    {"question": "What color is the sun?", "answer": "YELLOW"},
    {"question": "How many months in a year?", "answer": "12"},
    {"question": "What animal is king of the jungle?", "answer": "LION"},
    {"question": "What do you use to write?", "answer": "PEN"},
    {"question": "How many legs does a spider have?", "answer": "8"},
    {"question": "What do chickens lay?", "answer": "EGGS"},
    {"question": "What shape is a ball?", "answer": "CIRCLE"},
    {"question": "How many corners on a square?", "answer": "4"},
    {"question": "What animal says moo?", "answer": "COW"},


    {"question": "What city hosted the 2012 Olympics?", "answer": "LONDON"},
    {"question": "Who invented the telephone?", "answer": "BELL"},
    {"question": "What is the largest continent?", "answer": "ASIA"},
    {"question": "What river runs through Egypt?", "answer": "NILE"},
    {"question": "Who was known as the Iron Lady?", "answer": "THATCHER"},
    {"question": "What is the capital of Spain?", "answer": "MADRID"},
    {"question": "What country gifted the Statue of Liberty to the US?", "answer": "FRANCE"},

    # Entertainment & Pop Culture (25 questions)
    {"question": "What is the name of the fairy in Peter Pan?", "answer": "TINKERBELL"},
    {"question": "What is Superman's weakness?", "answer": "KRYPTONITE"},
    {"question": "What is the fastest car brand?", "answer": "BUGATTI"},
    {"question": "What company created the iPhone?", "answer": "APPLE"},
    {"question": "What Disney movie features a magic carpet?", "answer": "ALADDIN"},
    {"question": "What is Mario's brother's name?", "answer": "LUIGI"},
    {"question": "What color is Sonic the Hedgehog?", "answer": "BLUE"},
    {"question": "What is the most popular search engine?", "answer": "GOOGLE"},
    {"question": "What animal is Pikachu?", "answer": "MOUSE"},
    {"question": "What is the name of Harry Potter's owl?", "answer": "HEDWIG"},
    {"question": "What is Batman's real name?", "answer": "BRUCE"},
    {"question": "What company makes PlayStation?", "answer": "SONY"},
    {"question": "What is the most viewed video on YouTube?", "answer": "BABYSHARK"},
    {"question": "What movie features Jack and Rose on a ship?", "answer": "TITANIC"},
    {"question": "What is the name of Thor's hammer?", "answer": "MJOLNIR"},
    {"question": "What is the currency in Fortnite?", "answer": "VBUCKS"},
    {"question": "What game involves building with blocks?", "answer": "MINECRAFT"},
    {"question": "What is Iron Man's real name?", "answer": "TONYSTARK"},
    {"question": "What is the most streamed song on Spotify?", "answer": "BLINDINGLIGHTS"},
    {"question": "What princess has very long hair?", "answer": "RAPUNZEL"},
    {"question": "What color is the Facebook logo?", "answer": "BLUE"},
    {"question": "What game has a battle royale mode?", "answer": "FORTNITE"},
    {"question": "What is Link's fairy companion called in Zelda?", "answer": "NAVI"},
    {"question": "What animal is Tom in Tom and Jerry?", "answer": "CAT"},
    {"question": "What superhero can shrink and grow?", "answer": "ANTMAN"},

    # Food & Miscellaneous (20 questions)
    {"question": "What is the main ingredient in bread?", "answer": "FLOUR"},
    {"question": "What fruit is red and often mistaken for a vegetable?", "answer": "TOMATO"},
    {"question": "What is the most popular pizza topping?", "answer": "PEPPERONI"},
    {"question": "What beverage contains caffeine?", "answer": "COFFEE"},
    {"question": "What is sushi traditionally wrapped in?", "answer": "SEAWEED"},
    {"question": "What nut is used to make marzipan?", "answer": "ALMOND"},
    {"question": "What is the main ingredient in guacamole?", "answer": "AVOCADO"},
    {"question": "What type of pasta is shaped like a tube?", "answer": "PENNE"},
    {"question": "What is the hottest chili pepper?", "answer": "CAROLINAREAPER"},
    {"question": "What do you call a person who doesn't eat meat?", "answer": "VEGETARIAN"},
    {"question": "What is the main ingredient in hummus?", "answer": "CHICKPEAS"},
    {"question": "What drink is made from fermented grapes?", "answer": "WINE"},
    {"question": "What is the most expensive spice?", "answer": "SAFFRON"},
    {"question": "What country is famous for maple syrup?", "answer": "CANADA"},
    {"question": "What is a baby kangaroo called?", "answer": "JOEY"},
    {"question": "What color is a giraffe's tongue?", "answer": "PURPLE"},
    {"question": "What is the fear of spiders called?", "answer": "ARACHNOPHOBIA"},
    {"question": "What is the world's most popular sport?", "answer": "SOCCER"},
    {"question": "What is the largest bird in the world?", "answer": "OSTRICH"},
    {"question": "What is the fear of heights called?", "answer": "ACROPHOBIA"},
]


class TriviaGame:
    """Represents an active trivia PvP game"""
    def __init__(self, player1_id, player2_id, total_questions, bet, player1_channel_id=None, player2_channel_id=None, original_channel_id=None):
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.total_questions = total_questions
        self.bet = bet
        
        # Track each player's progress separately
        self.player1_current = 0  # Current question index for player 1
        self.player2_current = 0  # Current question index for player 2
        self.player1_correct = 0  # Questions answered correctly by player 1
        self.player2_correct = 0  # Questions answered correctly by player 2
        
        # Generate question list for this game
        self.questions = random.sample(TRIVIA_QUESTIONS, min(total_questions, len(TRIVIA_QUESTIONS)))
        
        self.game_active = True
        self.winner = None
        self.start_time = None
        self.player1_channel_id = player1_channel_id  # Separate channel for player 1
        self.player2_channel_id = player2_channel_id  # Separate channel for player 2
        self.original_channel_id = original_channel_id  # Original channel where command was run
        
        # Track when each player started their current question
        self.player1_question_start = None
        self.player2_question_start = None
        
        # Track finish times
        self.player1_finish_time = None
        self.player2_finish_time = None
        
        # Skip and hint counters for each player
        self.player1_skips = 3
        self.player2_skips = 3
        self.player1_hints = 3
        self.player2_hints = 3
        self.player1_revealed_letters = set()  # Track revealed letters for current question
        self.player2_revealed_letters = set()  # Track revealed letters for current question


class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # channel_id: TriviaGame
        self.pending_challenges = {}  # user_id: challenge_data

    @commands.command(name="trivia", aliases=["tpvp", "triviaduel"])
    async def trivia(self, ctx, opponent: discord.Member = None, rounds: int = None, bet: int = None):
        """Challenge someone to a trivia duel!
        
        First to answer wins the round. Most rounds won = winner!
        
        Usage: gtrivia @opponent <rounds> <bet>
        Example: gtrivia @User 5 1000
        
        Rounds: 1-35 (max)
        Bet: 100 minimum per player
        """
        if not await require_enrollment(ctx):
            return
        
        # Show help or validate opponent
        if opponent is None:
            embed = discord.Embed(
                title="Trivia PVP",
                description=(
                    "Challenge someone to a trivia battle!\n\n"
                    "**How to Play:**\n"
                    "<a:arrow:1437968863026479258> Challenge an opponent with a bet\n"
                    "<a:arrow:1437968863026479258> Both players answer trivia questions\n"
                    "<a:arrow:1437968863026479258> First to finish all questions wins!\n"
                    "<a:arrow:1437968863026479258> Winner takes the pot!\n\n"
                    "**Usage:**\n"
                    "`gtrivia @opponent <rounds> <bet>`\n\n"
                    "**Example:**\n"
                    "`gtrivia @Friend 10 5000`\n\n"
                    "**Rules:**\n"
                    "<a:arrow:1437968863026479258> Max 35 rounds\n"
                    "<a:arrow:1437968863026479258> Min bet: 100 mora per player\n"
                    "<a:arrow:1437968863026479258> No repeated questions\n"
                    "<a:arrow:1437968863026479258> Winner takes all!"
                ),
                color=0x9B59B6
            )
            embed.set_footer(text="70 easy questions available (40 math, 30 general)")
            return await ctx.send(embed=embed)
        
        if opponent.bot:
            return await ctx.send("❌ You can't challenge a bot!")
        
        if opponent.id == ctx.author.id:
            return await ctx.send("❌ You can't challenge yourself!")
        
        # Validate rounds
        if rounds is None:
            return await ctx.send("❌ Specify number of rounds! Example: `gtrivia @user 5 1000`")
        
        if rounds < 1 or rounds > 35:
            return await ctx.send("❌ Rounds must be between 1 and 35!")
        
        # Validate bet
        if bet is None:
            return await ctx.send("❌ Specify bet amount! Example: `gtrivia @user 5 1000`")
        
        if bet < 100:
            return await ctx.send("❌ Minimum bet is 100 mora!")
        
        # Check if channel already has a game
        if ctx.channel.id in self.active_games:
            return await ctx.send("❌ There's already a trivia game in this channel!")
        
        # Check if either player already has a pending challenge
        if ctx.author.id in self.pending_challenges:
            return await ctx.send("❌ You already have a pending challenge! Wait for it to be accepted or declined.")
        
        if opponent.id in self.pending_challenges:
            return await ctx.send(f"❌ {opponent.mention} already has a pending challenge!")
        
        # Check balances
        challenger_data = await get_user_data(ctx.author.id)
        opponent_data = await get_user_data(opponent.id)
        
        if not opponent_data:
            return await ctx.send(f"❌ {opponent.mention} needs to `gstart` first!")
        
        if challenger_data["mora"] < bet:
            return await ctx.send(f"❌ You don't have enough mora! Need: {bet:,} <:mora:1437958309255577681>")
        
        if opponent_data["mora"] < bet:
            return await ctx.send(f"❌ {opponent.mention} doesn't have enough mora!")
        
        # Create challenge
        self.pending_challenges[opponent.id] = {
            "challenger_id": ctx.author.id,
            "rounds": rounds,
            "bet": bet,
            "channel_id": ctx.channel.id,
            "message": None
        }
        
        # Create accept/decline view
        view = TriviaAcceptView(self, opponent.id)
        
        total_pot = bet * 2
        embed = discord.Embed(
            title="TRIVIA CHALLENGE",
            description=(
                f"{opponent.mention}, you've been challenged by {ctx.author.mention}!\n\n"
                f"**Rounds:** {rounds}\n"
                f"**Bet:** {bet:,} <:mora:1437958309255577681> per player\n"
                f"**Total Pot:** {total_pot:,} <:mora:1437958309255577681>\n\n"
                f"First to finish all questions wins!\n"
                f"Winner takes all!"
            ),
            color=0x9B59B6
        )
        embed.set_footer(text="Challenge expires in 60 seconds")
        
        msg = await ctx.send(embed=embed, view=view)
        self.pending_challenges[opponent.id]["message"] = msg
        
        # Auto-decline after 60 seconds
        await asyncio.sleep(60)
        if opponent.id in self.pending_challenges:
            del self.pending_challenges[opponent.id]
            embed.description += "\n\n❌ **Challenge expired!**"
            embed.color = 0x95A5A6
            try:
                await msg.edit(embed=embed, view=None)
            except:
                pass

    async def start_trivia_game(self, player1_id, player2_id, rounds, bet, original_channel):
        """Start the trivia game"""
        # Deduct bets from both players
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET mora = mora - ? WHERE user_id = ?", (bet, player1_id))
            await db.execute("UPDATE users SET mora = mora - ? WHERE user_id = ?", (bet, player2_id))
            await db.commit()
        
        # Get players
        player1 = self.bot.get_user(player1_id)
        player2 = self.bot.get_user(player2_id)
        guild = original_channel.guild
        category = original_channel.category
        
        # Set up permissions for each player's channel
        # Add moderator roles
        mod_overwrites = {}
        for role in guild.roles:
            if role.permissions.manage_channels or role.permissions.administrator:
                mod_overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=False)
        
        # Get bot owner as guild member (hardcoded owner ID: 873464016217968640)
        bot_owner_id = 873464016217968640
        bot_owner_member = None
        try:
            bot_owner_member = await guild.fetch_member(bot_owner_id)
        except:
            pass
        
        # Create two separate channels - one for each player
        try:
            # Player 1's channel
            p1_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                player1: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                **mod_overwrites
            }
            # Add bot owner if exists in this guild
            if bot_owner_member:
                p1_overwrites[bot_owner_member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            player1_channel = await guild.create_text_channel(
                name="trivia",
                category=category,
                overwrites=p1_overwrites,
                topic=f"{player1.name}'s trivia channel | {rounds} rounds | Prize: {bet*2:,} mora"
            )
            
            # Player 2's channel
            p2_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                player2: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                **mod_overwrites
            }
            # Add bot owner if exists in this guild
            if bot_owner_member:
                p2_overwrites[bot_owner_member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            player2_channel = await guild.create_text_channel(
                name="trivia",
                category=category,
                overwrites=p2_overwrites,
                topic=f"{player2.name}'s trivia channel | {rounds} rounds | Prize: {bet*2:,} mora"
            )
        except discord.Forbidden:
            await original_channel.send("❌ Bot doesn't have permission to create channels!")
            # Refund players
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET mora = mora + ? WHERE user_id = ?", (bet, player1_id))
                await db.execute("UPDATE users SET mora = mora + ? WHERE user_id = ?", (bet, player2_id))
                await db.commit()
            return
        
        # Create game with both channel IDs
        game = TriviaGame(player1_id, player2_id, rounds, bet, player1_channel.id, player2_channel.id, original_channel.id)
        self.active_games[player1_channel.id] = game
        self.active_games[player2_channel.id] = game
        
        # Send welcome message to each player's channel
        # Send ping first (outside embed) so players get notified
        await player1_channel.send(f"{player1.mention} Your trivia battle is ready!")
        await player2_channel.send(f"{player2.mention} Your trivia battle is ready!")
        
        welcome_p1 = discord.Embed(
            title="TRIVIA SPEED RACE",
            description=(
                f"**{player1.mention} vs {player2.mention}**\n\n"
                f"🔄 **3 Skips** - Type `gskip` to skip a question\n"
                f"💡 **3 Hints** - Type `gtriviahint` to reveal letters\n\n"
                f"**Rules:**\n"
                f"<a:arrow:1437968863026479258> Both players answer the SAME questions\n"
                f"<a:arrow:1437968863026479258> First to correctly answer ALL **{rounds} questions** wins!\n"
                f"<a:arrow:1437968863026479258> Answer your current question to get the next one\n"
                f"<a:arrow:1437968863026479258> Type your answers in chat\n"
                f"<a:arrow:1437968863026479258> No cheating - mods are watching!\n\n"
                f"**Pot:** {bet*2:,} <:mora:1437958309255577681>\n"
                f"Winner takes all!\n\n"
                f"**You have 15 seconds to prepare...**"
            ),
            color=0x9B59B6
        )
        
        welcome_p2 = discord.Embed(
            title="TRIVIA SPEED RACE",
            description=(
                f"**{player2.mention} vs {player1.mention}**\n\n"
                f"🔄 **3 Skips** - Type `gskip` to skip a question\n"
                f"💡 **3 Hints** - Type `gtriviahint` to reveal letters\n\n"
                f"**Rules:**\n"
                f"<a:arrow:1437968863026479258> Both players answer the SAME questions\n"
                f"<a:arrow:1437968863026479258> First to correctly answer ALL **{rounds} questions** wins!\n"
                f"<a:arrow:1437968863026479258> Answer your current question to get the next one\n"
                f"<a:arrow:1437968863026479258> Type your answers in chat\n"
                f"<a:arrow:1437968863026479258> No cheating - mods are watching!\n\n"
                f"**Pot:** {bet*2:,} <:mora:1437958309255577681>\n"
                f"Winner takes all!\n\n"
                f"**You have 15 seconds to prepare...**"
            ),
            color=0x9B59B6
        )
        
        await player1_channel.send(embed=welcome_p1)
        await player2_channel.send(embed=welcome_p2)
        
        # Give players 15 seconds to find the channel and prepare
        for i in range(15, 0, -5):
            await asyncio.sleep(5)
            if i > 5:
                await player1_channel.send(f"Game starting in **{i-5}** seconds...")
                await player2_channel.send(f"Game starting in **{i-5}** seconds...")
        
        # Final countdown
        await player1_channel.send("**Get ready... GO!**")
        await player2_channel.send("**Get ready... GO!**")
        await asyncio.sleep(1)
        
        game.start_time = datetime.now()
        
        # Send first question to both players in their respective channels
        await self.send_question_to_player(player1_channel, game, game.player1_id)
        await self.send_question_to_player(player2_channel, game, game.player2_id)

    async def send_question_to_player(self, channel, game, player_id):
        """Send the current question to a specific player"""
        if not game.game_active:
            return
        
        player = self.bot.get_user(player_id)
        
        # Determine which question this player is on
        if player_id == game.player1_id:
            question_num = game.player1_current
            correct_count = game.player1_correct
            game.player1_question_start = datetime.now()
        else:
            question_num = game.player2_current
            correct_count = game.player2_correct
            game.player2_question_start = datetime.now()
        
        # Check if player finished all questions
        if question_num >= game.total_questions:
            return
        
        question = game.questions[question_num]
        
        # Get skip and hint counts for this player
        if player_id == game.player1_id:
            skips_left = game.player1_skips
            hints_left = game.player1_hints
        else:
            skips_left = game.player2_skips
            hints_left = game.player2_hints
        
        embed = discord.Embed(
            title=f"Question {question_num + 1}/{game.total_questions}",
            description=(
                f"**{player.mention}**\n\n"
                f"# {question['question']}\n\n"
                f"Type your answer in chat!\n"
                f"🔄 Skips: **{skips_left}** | 💡 Hints: **{hints_left}**"
            ),
            color=0x9B59B6
        )
        embed.set_footer(text=f"Progress: {correct_count}/{game.total_questions} correct | Use gskip or gtriviahint")
        
        await channel.send(embed=embed)

    async def end_game(self, channel, winner_id):
        """End the game and award winner"""
        game = self.active_games.get(channel.id)
        if not game:
            return
        
        # Prevent double-ending if already processed
        if game.winner is not None:
            return
        
        game.game_active = False
        game.winner = winner_id
        
        player1 = self.bot.get_user(game.player1_id)
        player2 = self.bot.get_user(game.player2_id)
        winner = self.bot.get_user(winner_id)
        
        # Get both channels
        player1_channel = self.bot.get_channel(game.player1_channel_id)
        player2_channel = self.bot.get_channel(game.player2_channel_id)
        
        # Calculate time taken
        time_taken = (datetime.now() - game.start_time).total_seconds()
        
        # Give pot to winner
        total_pot = game.bet * 2
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET mora = mora + ? WHERE user_id = ?", (total_pot, winner_id))
            await db.commit()
        
        profit = total_pot - game.bet
        
        # Get final progress
        p1_progress = game.player1_correct
        p2_progress = game.player2_correct
        
        embed = discord.Embed(
            title="<a:Trophy:1438199339586424925> GAME OVER",
            description=(
                f"**{winner.mention} WINS!**\n\n"
                f"Finished all {game.total_questions} questions first!\n\n"
                f"**Final Progress:**\n"
                f"{player1.mention}: {p1_progress}/{game.total_questions}\n"
                f"{player2.mention}: {p2_progress}/{game.total_questions}\n\n"
                f"**Time:** {time_taken:.1f} seconds\n"
                f"**Total Pot:** {total_pot:,} <:mora:1437958309255577681>\n"
                f"**Profit:** +{profit:,} <:mora:1437958309255577681>\n\n"
                f"Channel will be deleted in 10 seconds..."
            ),
            color=0x2ECC71
        )
        embed.set_footer(text=f"Winner: {winner.display_name}")
        
        # Send to both channels
        if player1_channel:
            await player1_channel.send(embed=embed)
        if player2_channel:
            await player2_channel.send(embed=embed)
        
        # Post results to original channel
        original_channel = self.bot.get_channel(game.original_channel_id)
        if original_channel:
            public_embed = discord.Embed(
                title="<a:Trophy:1438199339586424925> TRIVIA GAME FINISHED",
                description=(
                    f"**{winner.mention} WINS!**\n\n"
                    f"**Players:** {player1.mention} vs {player2.mention}\n"
                    f"**Questions:** {game.total_questions}\n"
                    f"**Final Scores:**\n"
                    f"{player1.mention}: {p1_progress}/{game.total_questions}\n"
                    f"{player2.mention}: {p2_progress}/{game.total_questions}\n\n"
                    f"**Time:** {time_taken:.1f} seconds\n"
                    f"**Prize Won:** {total_pot:,} <:mora:1437958309255577681>\n"
                    f"**Profit:** +{profit:,} <:mora:1437958309255577681>"
                ),
                color=0x2ECC71
            )
            public_embed.set_footer(text=f"Winner: {winner.display_name}")
            await original_channel.send(embed=public_embed)
        
        # Remove from active games
        if game.player1_channel_id in self.active_games:
            del self.active_games[game.player1_channel_id]
        if game.player2_channel_id in self.active_games:
            del self.active_games[game.player2_channel_id]
        
        # Delete both channels after delay
        await asyncio.sleep(10)
        try:
            if player1_channel:
                await player1_channel.delete(reason=f"Trivia game ended - {winner.name} won")
        except:
            pass
        try:
            if player2_channel:
                await player2_channel.delete(reason=f"Trivia game ended - {winner.name} won")
        except:
            pass

    @commands.command(name="skip")
    async def skip_question(self, ctx):
        """Skip the current trivia question"""
        game = self.active_games.get(ctx.channel.id)
        if not game or not game.game_active:
            return await ctx.send("❌ No active trivia game in this channel!")
        
        # Only players can skip
        if ctx.author.id not in [game.player1_id, game.player2_id]:
            return await ctx.send("❌ You're not in this trivia game!")
        
        is_player1 = ctx.author.id == game.player1_id
        
        # Check if player has skips left
        if is_player1:
            if game.player1_skips <= 0:
                return await ctx.send("❌ You have no skips remaining!")
            if game.player1_current >= game.total_questions:
                return await ctx.send("❌ You've already finished all questions!")
            
            game.player1_skips -= 1
            game.player1_current += 1
            game.player1_revealed_letters.clear()
            skips_left = game.player1_skips
        else:
            if game.player2_skips <= 0:
                return await ctx.send("❌ You have no skips remaining!")
            if game.player2_current >= game.total_questions:
                return await ctx.send("❌ You've already finished all questions!")
            
            game.player2_skips -= 1
            game.player2_current += 1
            game.player2_revealed_letters.clear()
            skips_left = game.player2_skips
        
        await ctx.send(f"🔄 Question skipped! **{skips_left}** skips remaining.")
        
        # Send next question
        await self.send_question_to_player(ctx.channel, game, ctx.author.id)

    @commands.command(name="triviahint", aliases=["thint"])
    async def get_hint(self, ctx):
        """Get a hint for the current trivia question"""
        game = self.active_games.get(ctx.channel.id)
        if not game or not game.game_active:
            return await ctx.send("❌ No active trivia game in this channel!")
        
        # Only players can get hints
        if ctx.author.id not in [game.player1_id, game.player2_id]:
            return await ctx.send("❌ You're not in this trivia game!")
        
        is_player1 = ctx.author.id == game.player1_id
        
        # Check if player has hints left
        if is_player1:
            if game.player1_hints <= 0:
                return await ctx.send("❌ You have no hints remaining!")
            if game.player1_current >= game.total_questions:
                return await ctx.send("❌ You've already finished all questions!")
            
            current_question = game.questions[game.player1_current]
            game.player1_hints -= 1
            revealed_letters = game.player1_revealed_letters
            hints_left = game.player1_hints
        else:
            if game.player2_hints <= 0:
                return await ctx.send("❌ You have no hints remaining!")
            if game.player2_current >= game.total_questions:
                return await ctx.send("❌ You've already finished all questions!")
            
            current_question = game.questions[game.player2_current]
            game.player2_hints -= 1
            revealed_letters = game.player2_revealed_letters
            hints_left = game.player2_hints
        
        # Reveal a random letter from the answer
        answer = current_question['answer']
        available_positions = [i for i, char in enumerate(answer) if i not in revealed_letters and char.isalnum()]
        
        if not available_positions:
            return await ctx.send("❌ All letters already revealed!")
        
        # Reveal a random position
        reveal_pos = random.choice(available_positions)
        revealed_letters.add(reveal_pos)
        
        # Build hint string
        hint_string = ""
        for i, char in enumerate(answer):
            if i in revealed_letters:
                hint_string += char
            elif char.isalnum():
                hint_string += "_"
            else:
                hint_string += char
        
        await ctx.send(f"💡 **Hint:** `{hint_string}`\n**{hints_left}** hints remaining.")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for trivia answers"""
        if message.author.bot:
            return
        
        if message.content.startswith('g'):
            return
        
        game = self.active_games.get(message.channel.id)
        if not game or not game.game_active:
            return
        
        # Only players can answer
        if message.author.id not in [game.player1_id, game.player2_id]:
            return
        
        # Determine which player answered
        is_player1 = message.author.id == game.player1_id
        
        # Get current question for this player
        if is_player1:
            if game.player1_current >= game.total_questions:
                return  # Player already finished
            current_question = game.questions[game.player1_current]
            question_start = game.player1_question_start
        else:
            if game.player2_current >= game.total_questions:
                return  # Player already finished
            current_question = game.questions[game.player2_current]
            question_start = game.player2_question_start
        
        # Check answer (case insensitive, remove spaces/special chars)
        user_answer = ''.join(c.upper() for c in message.content if c.isalnum())
        correct_answer = ''.join(c.upper() for c in current_question['answer'] if c.isalnum())
        
        # Accept exact match OR if one contains the other (for partial name answers like TONY vs TONYSTARK)
        is_correct = (user_answer == correct_answer or 
                     (len(user_answer) >= 4 and user_answer in correct_answer) or
                     (len(correct_answer) >= 4 and correct_answer in user_answer))
        
        if is_correct:
            # Correct answer!
            await message.add_reaction("✅")
            
            # Calculate time for this question
            time_taken = (datetime.now() - question_start).total_seconds()
            
            # Update player's progress
            if is_player1:
                game.player1_correct += 1
                game.player1_current += 1
                game.player1_revealed_letters.clear()  # Clear hints for next question
                
                # Check if player 1 finished all questions
                if game.player1_correct >= game.total_questions:
                    # Record finish time
                    game.player1_finish_time = datetime.now()
                    
                    # Check if game already ended (other player finished first)
                    if game.winner is not None:
                        return
                    
                    # Determine winner based on finish time
                    if game.player2_finish_time is not None:
                        # Both finished, compare times
                        if game.player1_finish_time < game.player2_finish_time:
                            await self.end_game(message.channel, game.player1_id)
                        else:
                            await self.end_game(message.channel, game.player2_id)
                    else:
                        # Player 1 finished first
                        await self.end_game(message.channel, game.player1_id)
                    return
                
                # Send next question
                await asyncio.sleep(1)
                await self.send_question_to_player(message.channel, game, game.player1_id)
            else:
                game.player2_correct += 1
                game.player2_current += 1
                game.player2_revealed_letters.clear()  # Clear hints for next question
                
                # Check if player 2 finished all questions
                if game.player2_correct >= game.total_questions:
                    # Record finish time
                    game.player2_finish_time = datetime.now()
                    
                    # Check if game already ended (other player finished first)
                    if game.winner is not None:
                        return
                    
                    # Determine winner based on finish time
                    if game.player1_finish_time is not None:
                        # Both finished, compare times
                        if game.player2_finish_time < game.player1_finish_time:
                            await self.end_game(message.channel, game.player2_id)
                        else:
                            await self.end_game(message.channel, game.player1_id)
                    else:
                        # Player 2 finished first
                        await self.end_game(message.channel, game.player2_id)
                    return
                
                # Send next question
                await asyncio.sleep(1)
                await self.send_question_to_player(message.channel, game, game.player2_id)
        else:
            # Wrong answer - just react, don't give next question
            await message.add_reaction("❌")


class TriviaAcceptView(discord.ui.View):
    """Accept/Decline buttons for trivia challenge"""
    
    def __init__(self, cog, opponent_id):
        super().__init__(timeout=60)
        self.cog = cog
        self.opponent_id = opponent_id
    
    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent_id:
            return await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
        
        if self.opponent_id not in self.cog.pending_challenges:
            return await interaction.response.send_message("❌ Challenge expired!", ephemeral=True)
        
        challenge = self.cog.pending_challenges[self.opponent_id]
        del self.cog.pending_challenges[self.opponent_id]
        
        await interaction.response.send_message("✅ Challenge accepted! Starting game...", ephemeral=True)
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        
        # Start game
        await self.cog.start_trivia_game(
            challenge["challenger_id"],
            self.opponent_id,
            challenge["rounds"],
            challenge["bet"],
            interaction.channel
        )
    
    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent_id:
            return await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
        
        if self.opponent_id not in self.cog.pending_challenges:
            return await interaction.response.send_message("❌ Challenge expired!", ephemeral=True)
        
        del self.cog.pending_challenges[self.opponent_id]
        
        await interaction.response.send_message("❌ Challenge declined.", ephemeral=True)
        
        # Update message
        embed = interaction.message.embeds[0]
        embed.description += "\n\n❌ **Challenge declined!**"
        embed.color = 0xE74C3C
        
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(embed=embed, view=self)


async def setup(bot):
    await bot.add_cog(Trivia(bot))
