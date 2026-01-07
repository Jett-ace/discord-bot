import discord
from discord.ext import commands
import aiosqlite
import asyncio
import random
from datetime import datetime
from config import DB_PATH
from utils.embed import send_embed


class EndlessCashOutView(discord.ui.View):
    """Cash out button for endless mode"""
    
    def __init__(self, user_id, cog):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.cog = cog
    
    @discord.ui.button(label="💰 Cash Out", style=discord.ButtonStyle.success)
    async def cash_out(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ This isn't your game!", ephemeral=True)
        
        await interaction.response.defer()
        await self.cog.endless_cash_out(self.user_id, interaction.channel)
        
        # Disable button
        button.disabled = True
        await interaction.message.edit(view=self)


# Word lists by difficulty (200 words each)
WORD_LISTS = {
    "easy": [
        "TEAM", "RACE", "JUMP", "CAKE", "PARK", "BIRD", "FISH", "STAR", "MOON", "TREE",
        "BOAT", "DOOR", "FIRE", "GOLD", "HOME", "KING", "LION", "RAIN", "WIND", "SNOW",
        "COIN", "DECK", "FROG", "GIFT", "HAND", "IRON", "JADE", "KITE", "LAMP", "MASK",
        "NOTE", "OVER", "PEAK", "RING", "SHIP", "TIDE", "UNIT", "VASE", "WAVE", "ZONE",
        "BELL", "CARD", "DIAL", "EPIC", "FLAG", "GAME", "HERO", "ISLE", "JOKE", "KEYS",
        "LUCK", "MAZE", "NEWS", "OPEN", "PAGE", "QUIZ", "RUST", "SAFE", "TIME", "UNDO",
        "ARCH", "BARN", "CLAW", "DAWN", "EDGE", "FARM", "GATE", "HILL", "INCH", "JAIL",
        "KEEP", "LEAF", "MIST", "NEST", "OATH", "PATH", "QUIT", "ROBE", "SAIL", "TAIL",
        "UGLY", "VINE", "WISE", "YARN", "ZOOM", "APEX", "BOLT", "CAVE", "DUCK", "EAST",
        "FANG", "GULF", "HAWK", "ICON", "JUNK", "KIWI", "LAVA", "MINT", "NOON", "OPAL",
        "PEAR", "REEF", "SALT", "TENT", "VEIL", "WAND", "YELL", "ZERO", "AREA", "BEAM",
        "COAT", "DEER", "EXAM", "FOIL", "GLOW", "HIVE", "IRIS", "JADE", "KNEE", "LENS",
        "MOLD", "NAIL", "OVEN", "PAWS", "RICE", "SAGE", "TOMB", "URGE", "VIEW", "WOLF",
        "YAWN", "ABLE", "BEAM", "COIL", "DUSK", "EARN", "FLAP", "GAZE", "HORN", "IDOL",
        "JUMP", "KIND", "LOUD", "MILD", "NAVY", "ONLY", "PLUG", "RAMP", "SILK", "TOAD",
        "UNIT", "VICE", "WAIT", "YOLK", "ZEAL", "ACNE", "BASH", "COZY", "DROP", "EVEN",
        "FOAM", "GRIP", "HOUR", "IDEA", "JUST", "KALE", "LURE", "MUTE", "NUMB", "OVAL",
        "PACT", "RASH", "SLAP", "TRIM", "UNDO", "VOWS", "WASP", "YANK", "ZEST", "ACME",
        "BUFF", "CRIB", "DUEL", "EMIT", "FOLD", "GRAM", "HUGE", "ITCH", "JOLT", "KELP",
        "LOOP", "MOTH", "NEON", "ODDS", "PALM", "RUSE", "SODA", "TAXI", "UNIT", "VERB"
    ],
    "medium": [
        "APPLE", "PHONE", "MUSIC", "MONEY", "WATER", "HOUSE", "CHAIR", "TABLE", "CLOCK", "LIGHT",
        "PAPER", "SHIRT", "PANTS", "SHOES", "WATCH", "BREAD", "LUNCH", "DRINK", "SMILE", "HEART",
        "BEACH", "CLOUD", "STORM", "GRASS", "PLANT", "STONE", "RIVER", "OCEAN", "WORLD", "SPEED",
        "PIZZA", "SWEET", "SPICY", "FRESH", "CLEAN", "QUICK", "SLEEP", "DREAM", "PARTY", "DANCE",
        "POWER", "MAGIC", "BRAVE", "SMART", "HAPPY", "PEACE", "TRUST", "VOICE", "MOVIE", "SIGHT",
        "PLACE", "SPACE", "TRAIN", "PLANE", "DRIVE", "FIGHT", "WRITE", "LEARN", "TEACH", "COUNT",
        "ABOUT", "AFTER", "ANGLE", "ARROW", "BADGE", "BAKER", "BENCH", "BLEND", "BLOCK", "BOARD",
        "BRAIN", "BRAKE", "BRAND", "BRICK", "BUNCH", "BURST", "CABIN", "CANAL", "CANDY", "CARGO",
        "CATCH", "CHAIN", "CHARM", "CHEAP", "CHEST", "CHIEF", "CHINA", "CLAIM", "CLASS", "COACH",
        "COAST", "CORAL", "COUCH", "COURT", "COVER", "CRACK", "CRASH", "CRAZY", "CREAM", "CROWN",
        "CURVE", "DAILY", "DAIRY", "DEPTH", "DIRTY", "DOUBT", "DRAFT", "DRAIN", "DRAWN", "DROWN",
        "EAGLE", "EARLY", "EARTH", "EMPTY", "ENEMY", "ENJOY", "EQUAL", "ERROR", "EXACT", "EXTRA",
        "FANCY", "FAULT", "FEVER", "FIELD", "FINAL", "FLAME", "FLASH", "FLEET", "FLOOD", "FLOUR",
        "FLUID", "FORGE", "FORTH", "FRAME", "FRANK", "FRAUD", "FROST", "FRUIT", "GAUGE", "GHOST",
        "GIANT", "GLORY", "GLOVE", "GRACE", "GRADE", "GRAIN", "GRAND", "GRANT", "GREET", "GRIEF",
        "GRILL", "GRIND", "GROSS", "GROUP", "GROVE", "GUARD", "GUESS", "GUEST", "GUIDE", "GUILT",
        "HARSH", "HASTE", "HEART", "HOBBY", "HONEY", "HONOR", "HORSE", "HOTEL", "HUMAN", "HUMOR",
        "IDEAL", "IMAGE", "INDEX", "INNER", "INPUT", "ISSUE", "IVORY", "JOKER", "JOINT", "JUICE",
        "KNIFE", "LABEL", "LABOR", "LASER", "LAYER", "LEGAL", "LEMON", "LEVEL", "LIMIT", "LOCAL",
        "LOOSE", "LOWER", "LOYAL", "LUCKY", "LUNAR", "MAJOR", "MAPLE", "MARCH", "MATCH", "MAYOR"
    ],
    "hard": [
        "KITCHEN", "BROTHER", "WEATHER", "HOLIDAY", "PICTURE", "CHICKEN", "WEEKEND", "WELCOME",
        "MORNING", "EVENING", "RAINBOW", "THUNDER", "BLANKET", "BEDROOM", "TEACHER", "STUDENT",
        "COMPUTER", "BIRTHDAY", "SHOPPING", "LIBRARY", "HISTORY", "SCIENCE", "ENGLISH", "MYSTERY",
        "FREEDOM", "BALANCE", "BENEFIT", "CONTROL", "CULTURE", "FASHION", "NETWORK", "PROBLEM",
        "QUALITY", "SUCCESS", "TRAFFIC", "VITAMIN", "WEATHER", "ACCOUNT", "CONTEST", "PRESENT",
        "SERVICE", "MESSAGE", "FORWARD", "CHAPTER", "COMPASS", "HEALTHY", "REGULAR", "SECTION",
        "BROTHER", "DISPLAY", "EVENING", "FIFTEEN", "GENERAL", "HIMSELF", "IMPROVE", "JUSTICE",
        "ADVANCE", "ANCIENT", "ANOTHER", "ANXIETY", "ANYBODY", "ARRIVAL", "ARTICLE", "ATTEMPT",
        "AVERAGE", "AWESOME", "BATTERY", "BENEATH", "BESIDES", "BETWEEN", "BILLION", "BLANKET",
        "BOULDER", "BOUNCE", "BRACKET", "BREATHE", "BRIDGE", "BURNING", "CABINET", "CALCIUM",
        "CAPABLE", "CAPTAIN", "CAPTURE", "CAREFUL", "CENTURY", "CERTAIN", "CHAMBER", "CHANNEL",
        "CHAPTER", "CHARITY", "CHARTER", "CHICKEN", "CIRCUIT", "CITIZEN", "CLASSIC", "CLIMATE",
        "CLOTHES", "COCONUT", "COLLEGE", "COMBINE", "COMMAND", "COMMENT", "COMPANY", "COMPARE",
        "COMPASS", "COMPLEX", "CONCEPT", "CONCERN", "CONDUCT", "CONFIRM", "CONNECT", "CONSENT",
        "CONTAIN", "CONTENT", "CONTEST", "CONTEXT", "CONTROL", "CONVERT", "CONVICT", "CORRECT",
        "COUNCIL", "COUNTER", "COUNTRY", "COURAGE", "CRYSTAL", "CULTURE", "CURRENT", "CUSTOMS",
        "CUTTING", "DECLINE", "DEFAULT", "DEFENSE", "DELIVER", "DENSITY", "DEPOSIT", "DESCEND",
        "DESERVE", "DESKTOP", "DESPITE", "DESTROY", "DEVELOP", "DIAMOND", "DIGITAL", "DISCUSS",
        "DISEASE", "DISMISS", "DISPLAY", "DISPUTE", "DISTANT", "DIVERSE", "DOLPHIN", "DRAWING",
        "ECONOMY", "EDITION", "ELDERLY", "ELEMENT", "EMPEROR", "ENDLESS", "ENFORCE", "ENGINEER",
        "ENHANCE", "EPISODE", "ESSENCE", "EVENING", "EVIDENT", "EXACTLY", "EXAMINE", "EXAMPLE",
        "EXCLAIM", "EXCLUDE", "EXECUTE", "EXPENSE", "EXPLAIN", "EXPLORE", "EXPRESS", "EXTREME",
        "FACTORY", "FACULTY", "FAILURE", "FANTASY", "FASHION", "FEATURE", "FEDERAL", "FIFTEEN",
        "FIGHTER", "FINANCE", "FORTUNE", "FORWARD", "FOUNDER", "FREEDOM", "FREQUENT", "FRIENDS",
        "FUNERAL", "GALLERY", "GARBAGE", "GATEWAY", "GENERAL", "GENETIC", "GESTURE", "GLIMPSE"
    ],
    "expert": [
        "CHOCOLATE", "TELEPHONE", "YESTERDAY", "BEAUTIFUL", "IMPORTANT", "SOMETHING", "DIFFERENT",
        "SOMEWHERE", "EVERYBODY", "SOMETHING", "COMMUNITY", "EDUCATION", "CHRISTMAS", "WEDNESDAY",
        "SEPTEMBER", "HAMBURGER", "VALENTINE", "PINEAPPLE", "BUTTERFLY", "FANTASTIC", "CELEBRATE",
        "ADVENTURE", "BREAKFAST", "UNDERSTAND", "APARTMENT", "NEWSPAPER", "WEDNESDAY", "SPAGHETTI",
        "EMERGENCY", "DANGEROUS", "CHARACTER", "MARKETING", "AFTERNOON", "RECOMMEND", "STRUCTURE",
        "KNOWLEDGE", "CHALLENGE", "ATTENTION", "INTERVIEW", "OPERATION", "PERMANENT", "PRINCIPAL",
        "BEAUTIFUL", "NECESSARY", "CONFIDENT", "EQUIPMENT", "LANDSCAPE", "MESSENGER", "SCIENTIST",
        "RECOGNIZE", "TECHNIQUE", "YESTERDAY", "NIGHTMARE", "WONDERFUL", "CROCODILE", "ORGANIZED",
        "ABANDONED", "ABILITIES", "ABSORBING", "ABUNDANCE", "ACADEMIC", "ACCESSORY", "ACCOMPANY",
        "ACCORDION", "ACCORDING", "ACCUSTOM", "ACHIEVING", "ACOUSTIC", "ACQUAINT", "ACTIVATED",
        "ADDICTION", "ADJUSTING", "ADMISSION", "ADMITTING", "ADVANCING", "ADVENTURE", "ADVERTISE",
        "AESTHETIC", "AFFECTION", "AFTERMATH", "AFTERNOON", "AGREEABLE", "AGREEMENT", "ALGORITHM",
        "ALIGNMENT", "ALONGSIDE", "ALPHABETS", "ALTERNATE", "AMAZEMENT", "AMBITIOUS", "AMBULANCE",
        "AMENDMENT", "AMPLIFIER", "AMUSEMENT", "ANALYZING", "ANCESTORS", "ANCHORING", "ANIMATION",
        "ANNOUNCED", "ANSWERING", "ANXIOUSLY", "APARTMENT", "APOLOGIZE", "APPARATUS", "APPEARING",
        "APPETIZER", "APPLIANCE", "APPOINTED", "APPRAISAL", "ARCHITECT", "ARGUMENTS", "ARMADILLO",
        "AROMATICS", "ARRANGING", "ARTIFACTS", "ARTILLERY", "ASCENDING", "ASPARAGUS", "ASPERSION",
        "ASSESSING", "ASSIGNING", "ASSISTANT", "ASSOCIATE", "ASSURANCE", "ASTRONOMY", "ATHLETICS",
        "ATTACKING", "ATTAINING", "ATTEMPTED", "ATTENDING", "ATTENTION", "ATTITUDES", "ATTRACTED",
        "ATTRIBUTE", "AUCTIONED", "AUDACIOUS", "AUDIENCES", "AUTHENTIC", "AUTHORITY", "AUTOMATED",
        "AUTOMATIC", "AUTUMN", "AVAILABLE", "AVERAGING", "AWAKENING", "AWARENESS", "BACKBOARD",
        "BACKLIGHT", "BACKSPACE", "BACKWARDS", "BACTERIAL", "BALANCING", "BALLPOINT", "BANDWIDTH",
        "BANKRUPTCY", "BARBECUE", "BAREFOOT", "BARGAINED", "BAROMETER", "BARRICADE", "BASICALLY",
        "BASKETBALL", "BATTERIES", "BEAUTIFUL", "BEGINNERS", "BEGINNING", "BEHAVIOUR", "BELIEVERS",
        "BELONGING", "BENCHMARK", "BENEFICIAL", "BETRAYING", "BEVERAGES", "BIOGRAPHY", "BIOLOGIST",
        "BIRTHDAYS", "BLACKJACK", "BLACKMAIL", "BLACKNESS", "BLESSINGS", "BLINDNESS", "BLOODSHOT"
    ]
}

DIFFICULTY_MULTIPLIERS = {
    "easy": 1.5,
    "medium": 2.0,
    "hard": 3.0,
    "expert": 5.0
}

DIFFICULTY_TIME_LIMITS = {
    "easy": 60,
    "medium": 60,
    "hard": 60,
    "expert": 60
}

class Scramble(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # user_id: game_data
        self.endless_games = {}  # user_id: endless game data

    def scramble_word(self, word):
        """Scramble a word ensuring it's different from original"""
        chars = list(word)
        scrambled = chars.copy()
        
        # Keep scrambling until it's different
        max_attempts = 50
        for _ in range(max_attempts):
            random.shuffle(scrambled)
            if ''.join(scrambled) != word:
                break
        
        return ''.join(scrambled)

    @commands.command(name="scramble", aliases=["wordscramble", "ws"])
    async def scramble(self, ctx, bet: str = None, difficulty: str = None):
        """Play word scramble game
        
        Usage: 
        gscramble <bet> [difficulty]
        gscramble 1000
        gscramble 1000 hard
        gscramble stats
        """
        # Allow DM play without betting
        if isinstance(ctx.channel, discord.DMChannel):
            if bet and bet.lower() != "stats":
                return await ctx.send(
                    "❌ You can only play scramble for fun in DMs (no betting)!\n"
                    "Use `gscramble` without a bet amount to play."
                )
            if bet and bet.lower() == "stats":
                return await ctx.send("❌ Stats are only available in servers!")
            # Set defaults for DM play
            bet = "0"
            difficulty = difficulty or "medium"
        
        # Check for stats
        if bet == "stats":
            return await self.show_stats(ctx)
        
        # Check if user already has active game
        if ctx.author.id in self.active_games:
            return await ctx.send("❌ You already have an active scramble game! Answer it first or wait for it to expire.")
        
        if ctx.author.id in self.endless_games:
            return await ctx.send("❌ You have an active endless scramble game! Finish or cash out first.")
        
        # Validate bet
        if bet is None:
            embed = discord.Embed(
                title="Word Scramble",
                description=(
                    "Unscramble words to win mora!\n\n"
                    "**Usage:**\n"
                    "`gscramble <bet>` - Random difficulty\n"
                    "`gscramble <bet> <difficulty>` - Choose difficulty\n"
                    "`gscramble stats` - View your stats\n\n"
                    "**Difficulties:**\n"
                    "• Easy (3-4 letters): 1.5x - 60s\n"
                    "• Medium (5-6 letters): 3.0x - 60s\n"
                    "• Hard (7-8 letters): 5.0x - 60s\n"
                    "• Expert (9-10 letters): 10.0x - 60s\n\n"
                    "**Bonuses:**\n"
                    "• Speed Bonus: +50% if solved under 10s\n"
                    "• Hint: `ghint` reveals 1 letter (costs 20% of bet, -0.5x multiplier, once per game)"
                ),
                color=0x3498DB
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            return await send_embed(ctx, embed)
        
        try:
            bet_amount = int(bet)
        except ValueError:
            return await ctx.send("❌ Invalid bet amount! Use a number.")
        
        # Skip balance checks for DM play (bet_amount is 0)
        if bet_amount > 0:
            if bet_amount < 100:
                return await ctx.send("❌ Minimum bet is 100 mora!")
            
            if bet_amount > 100000:
                return await ctx.send("❌ Maximum bet is 100,000 mora!")
            
            # Get user balance
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (ctx.author.id,))
                row = await cursor.fetchone()
                
                if not row:
                    return await ctx.send("❌ You need to enroll first! Use `gstart`")
                
                balance = row[0]
                
                if balance < bet_amount:
                    return await ctx.send(f"❌ You don't have enough mora! Balance: {balance:,} <:mora:1437958309255577681>")
        else:
            # DM play - no balance check needed
            balance = 0
            
            # Deduct bet
            await db.execute("UPDATE users SET mora = mora - ? WHERE user_id = ?", (bet_amount, ctx.author.id))
            await db.commit()
        
        # Determine difficulty
        if difficulty and difficulty.lower() in WORD_LISTS:
            diff = difficulty.lower()
        else:
            # Random difficulty based on bet amount
            if bet_amount < 1000:
                diff = "easy"
            elif bet_amount < 5000:
                diff = random.choice(["easy", "medium"])
            elif bet_amount < 10000:
                diff = random.choice(["medium", "hard"])
            else:
                diff = random.choice(["medium", "hard", "expert"])
        
        # Select random word
        word = random.choice(WORD_LISTS[diff])
        scrambled = self.scramble_word(word)
        
        # Store game data
        time_limit = DIFFICULTY_TIME_LIMITS[diff]
        self.active_games[ctx.author.id] = {
            "word": word,
            "scrambled": scrambled,
            "difficulty": diff,
            "bet": bet_amount,
            "multiplier": DIFFICULTY_MULTIPLIERS[diff],
            "start_time": datetime.now(),
            "time_limit": time_limit,
            "hint_used": False,
            "revealed_letters": set(),
            "channel_id": ctx.channel.id,
            "message_id": None  # Will store game message ID
        }
        
        # Create difficulty stars
        diff_stars = {
            "easy": "⭐",
            "medium": "⭐⭐⭐",
            "hard": "⭐⭐⭐⭐⭐",
            "expert": "⭐⭐⭐⭐⭐⭐⭐"
        }
        
        potential_win = int(bet_amount * DIFFICULTY_MULTIPLIERS[diff])
        
        embed = discord.Embed(
            title="WORD SCRAMBLE",
            description=(
                f"**Unscramble this word:**\n\n"
                f"# {' '.join(scrambled)}\n\n"
                f"**Difficulty:** {diff_stars[diff]} {diff.title()}\n"
                f"**Time Limit:** ⏱️ {time_limit} seconds\n"
                f"**Potential Win:** {potential_win:,} <:mora:1437958309255577681>\n\n"
                f"Type your answer in chat!\n"
                f"💡 Hint available: `ghint` (costs 20% of bet, once per game)"
            ),
            color=0x3498DB
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.set_footer(text=f"Bet: {bet_amount:,} mora | Speed bonus if under 10s!")
        
        game_msg = await ctx.send(embed=embed)
        self.active_games[ctx.author.id]["message_id"] = game_msg.id
        
        # Start timeout checker and countdown updater
        asyncio.create_task(self.game_timeout(ctx.author.id, time_limit))
        asyncio.create_task(self.update_countdown(ctx.author.id, game_msg, ctx.channel))

    async def game_timeout(self, user_id, time_limit):
        """Handle game timeout"""
        try:
            await asyncio.sleep(time_limit)
            
            if user_id in self.active_games:
                game = self.active_games[user_id]
                
                # Update stats
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("""
                        INSERT INTO game_stats (user_id, scramble_games, scramble_losses)
                        VALUES (?, 1, 1)
                        ON CONFLICT(user_id) DO UPDATE SET
                            scramble_games = scramble_games + 1,
                            scramble_losses = scramble_losses + 1,
                            scramble_streak = 0
                    """, (user_id,))
                    await db.commit()
                
                # Send timeout message to the channel where game was started
                channel = self.bot.get_channel(game['channel_id'])
                if channel:
                    user = self.bot.get_user(user_id)
                    embed = discord.Embed(
                        title="⏱️ TIME'S UP!",
                        description=(
                            f"{user.mention}\n\n"
                            f"**Correct answer:** {game['word']}\n\n"
                            f"⏱️ Time expired!\n"
                            f"💸 Lost: {game['bet']:,} <:mora:1437958309255577681>\n\n"
                            f"Better luck next time!"
                        ),
                        color=0xE74C3C
                    )
                    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
                    try:
                        await channel.send(embed=embed)
                    except:
                        pass
                
                del self.active_games[user_id]
        except asyncio.CancelledError:
            # Task was cancelled (game finished before timeout)
            pass
        except Exception as e:
            print(f"Error in game_timeout: {e}")

    async def update_countdown(self, user_id, message, channel):
        """Update the game embed with countdown timer"""
        try:
            while user_id in self.active_games:
                game = self.active_games[user_id]
                elapsed = (datetime.now() - game['start_time']).total_seconds()
                remaining = max(0, game['time_limit'] - int(elapsed))
                
                if remaining <= 0:
                    break
                
                # Create difficulty stars
                diff_stars = {
                    "easy": "⭐",
                    "medium": "⭐⭐⭐",
                    "hard": "⭐⭐⭐⭐⭐",
                    "expert": "⭐⭐⭐⭐⭐⭐⭐"
                }
                
                diff = game['difficulty']
                potential_win = int(game['bet'] * game['multiplier'])
                
                embed = discord.Embed(
                    title="WORD SCRAMBLE",
                    description=(
                        f"**Unscramble this word:**\n\n"
                        f"# {' '.join(game['scrambled'])}\n\n"
                        f"**Difficulty:** {diff_stars[diff]} {diff.title()}\n"
                        f"**Time Remaining:** ⏱️ **{remaining}s**\n"
                        f"**Potential Win:** {potential_win:,} <:mora:1437958309255577681>\n\n"
                        f"Type your answer in chat!\n"
                        f"💡 Hint available: `ghint` (costs 20% of bet, once per game)"
                    ),
                    color=0x3498DB if remaining > 10 else 0xE67E22 if remaining > 5 else 0xE74C3C
                )
                
                # Get user for display
                user = self.bot.get_user(user_id)
                if user:
                    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
                
                embed.set_footer(text=f"Bet: {game['bet']:,} mora | Speed bonus if under 10s!")
                
                try:
                    await message.edit(embed=embed)
                except:
                    break  # Message was deleted or can't be edited
                
                await asyncio.sleep(1)  # Update every second
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in update_countdown: {e}")

    @commands.command(name="hint")
    async def hint(self, ctx):
        """Get a hint for active scramble game (costs 20% of bet)"""
        if ctx.author.id not in self.active_games:
            return await ctx.send("❌ You don't have an active scramble game!")
        
        game = self.active_games[ctx.author.id]
        
        if game["hint_used"]:
            return await ctx.send("❌ You already used your hint for this game!")
        
        hint_cost = int(game["bet"] * 0.2)
        
        # Get user balance
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (ctx.author.id,))
            row = await cursor.fetchone()
            
            if not row or row[0] < hint_cost:
                return await ctx.send(f"❌ You need {hint_cost:,} mora for a hint!")
            
            # Deduct hint cost
            await db.execute("UPDATE users SET mora = mora - ? WHERE user_id = ?", (hint_cost, ctx.author.id))
            await db.commit()
        
        # Mark hint as used and reduce multiplier
        game["hint_used"] = True
        game["multiplier"] -= 0.5
        
        # Reveal a random letter that hasn't been revealed
        word = game["word"]
        unrevealed = [i for i in range(len(word)) if i not in game["revealed_letters"]]
        
        if unrevealed:
            reveal_idx = random.choice(unrevealed)
            game["revealed_letters"].add(reveal_idx)
            
            # Create hint string with revealed letter positioned correctly
            hint_word = ""
            for i, char in enumerate(word):
                if i in game["revealed_letters"] or i == reveal_idx:
                    hint_word += char + " "
                else:
                    hint_word += "\\_ "
            
            embed = discord.Embed(
                title="💡 HINT",
                description=(
                    f"**Word pattern:** `{hint_word.strip()}`\n\n"
                    f"💸 Cost: {hint_cost:,} mora\n"
                    f"📉 Multiplier reduced to: {game['multiplier']:.1f}x\n\n"
                    f"Scrambled: {' '.join(game['scrambled'])}"
                ),
                color=0xF39C12
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            await send_embed(ctx, embed)

    @commands.command(name="scrambleendless", aliases=["endlessscramble", "se"])
    async def scramble_endless(self, ctx, bet: str = None, difficulty: str = None):
        """Play endless scramble mode - keep going until you lose or cash out!
        
        Usage: gscrambleendless <bet> <difficulty>
        """
        # Check if user already has active game
        if ctx.author.id in self.endless_games:
            return await ctx.send("❌ You already have an active endless scramble game!")
        
        if ctx.author.id in self.active_games:
            return await ctx.send("❌ You have an active regular scramble game! Finish it first.")
        
        # Show help
        if bet is None:
            embed = discord.Embed(
                title="🔥 Endless Scramble Mode",
                description=(
                    "Keep guessing words to increase your multiplier!\n\n"
                    "**How it works:**\n"
                    "• Choose difficulty and starting bet\n"
                    "• First word: 1x (break even)\n"
                    "• Each correct: +0.5x multiplier\n"
                    "• Cash out anytime to claim winnings\n"
                    "• One mistake = lose everything!\n"
                    "• Max 15 rounds or 10x multiplier\n\n"
                    "**Usage:** `gscrambleendless <bet> <difficulty>`\n\n"
                    "**Difficulties:** easy, medium, hard, expert\n"
                    "**Bet Range:** 100 - 50,000"
                ),
                color=0xF39C12
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            return await send_embed(ctx, embed)
        
        # Validate difficulty
        if not difficulty or difficulty.lower() not in WORD_LISTS:
            return await ctx.send("❌ Choose difficulty: `easy`, `medium`, `hard`, or `expert`")
        
        diff = difficulty.lower()
        
        # Parse bet
        try:
            bet_amount = int(bet.replace(',', ''))
        except ValueError:
            return await ctx.send("❌ Invalid bet amount!")
        
        if bet_amount < 100:
            return await ctx.send("❌ Minimum bet is 100 mora!")
        
        if bet_amount > 50000:
            return await ctx.send("❌ Maximum bet is 50,000 mora!")
        
        # Get user balance
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (ctx.author.id,))
            row = await cursor.fetchone()
            
            if not row:
                return await ctx.send("❌ You need to enroll first! Use `!start`")
            
            balance = row[0]
            
            if balance < bet_amount:
                return await ctx.send(f"❌ Not enough mora! Balance: {balance:,} <:mora:1437958309255577681>")
            
            # Deduct bet
            await db.execute("UPDATE users SET mora = mora - ? WHERE user_id = ?", (bet_amount, ctx.author.id))
            await db.commit()
        
        # Starting multiplier - first word gives 1x (break even)
        start_mult = 1.0
        
        # Start first round
        word = random.choice(WORD_LISTS[diff])
        scrambled = self.scramble_word(word)
        
        self.endless_games[ctx.author.id] = {
            "word": word,
            "scrambled": scrambled,
            "difficulty": diff,
            "bet": bet_amount,
            "round": 1,
            "multiplier": start_mult,
            "start_time": datetime.now(),
            "channel_id": ctx.channel.id,
            "message_id": None  # Will store message ID for reply checking
        }
        
        await self.show_endless_word(ctx)

    async def show_endless_word(self, ctx):
        """Display current endless word"""
        game = self.endless_games[ctx.author.id]
        
        current_win = int(game["bet"] * game["multiplier"])
        next_mult = min(game["multiplier"] + 0.5, 10.0)
        next_win = int(game["bet"] * next_mult)
        
        embed = discord.Embed(
            title="🔥 ENDLESS SCRAMBLE 🔥",
            description=(
                f"**Round {game['round']}/15**\n\n"
                f"# {' '.join(game['scrambled'])}\n\n"
                f"**{game['difficulty'].title()}** | **{game['multiplier']:.1f}x**\n"
                f"**Current:** {current_win:,} <:mora:1437958309255577681>\n"
                f"**Next:** {next_mult:.1f}x = {next_win:,} <:mora:1437958309255577681>\n\n"
                f"Type answer or **Cash Out**!"
            ),
            color=0xF39C12
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.set_footer(text=f"Bet: {game['bet']:,} | Wrong answer = lose all!")
        
        view = EndlessCashOutView(ctx.author.id, self)
        msg = await ctx.send(embed=embed, view=view)
        game['message_id'] = msg.id
        game['message'] = msg

    async def endless_cash_out(self, user_id, channel, auto=False):
        """Cash out from endless mode"""
        if user_id not in self.endless_games:
            return
        
        game = self.endless_games[user_id]
        winnings = int(game["bet"] * game["multiplier"])
        
        # Give winnings
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET mora = mora + ? WHERE user_id = ?", (winnings, user_id))
            await db.commit()
        
        profit = winnings - game["bet"]
        
        embed = discord.Embed(
            title="💰 CASHED OUT!" if not auto else "🏆 MAX REACHED!",
            description=(
                f"<@{user_id}>\n\n"
                f"**Rounds Completed:** {game['round'] - (0 if auto else 1)}\n"
                f"**Final Multiplier:** {game['multiplier']:.1f}x\n"
                f"**Total Won:** {winnings:,} <:mora:1437958309255577681>\n"
                f"**Profit:** +{profit:,} <:mora:1437958309255577681>"
            ),
            color=0x2ECC71
        )
        embed.set_author(name=channel.guild.get_member(user_id).display_name, icon_url=channel.guild.get_member(user_id).display_avatar.url)
        
        await channel.send(embed=embed)
        del self.endless_games[user_id]

    async def endless_lose(self, user_id, channel):
        """Lose in endless mode"""
        if user_id not in self.endless_games:
            return
        
        game = self.endless_games[user_id]
        
        embed = discord.Embed(
            title="💥 WRONG ANSWER!",
            description=(
                f"<@{user_id}>\n\n"
                f"**Correct answer:** {game['word']}\n\n"
                f"**Rounds:** {game['round']}\n"
                f"**Lost:** {game['bet']:,} <:mora:1437958309255577681>\n\n"
                f"You were at {game['multiplier']:.1f}x!"
            ),
            color=0xE74C3C
        )
        embed.set_author(name=channel.guild.get_member(user_id).display_name, icon_url=channel.guild.get_member(user_id).display_avatar.url)
        
        await channel.send(embed=embed)
        del self.endless_games[user_id]

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for answers to active games"""
        if message.author.bot:
            return
        
        # Check endless game first
        if message.author.id in self.endless_games:
            game = self.endless_games[message.author.id]
            
            # Only respond if user replied to the game message
            if not message.reference or message.reference.message_id != game.get("message_id"):
                return
            
            if message.content.startswith('g'):
                return
            
            user_answer = message.content.strip().upper()
            
            if user_answer == game["word"]:
                # Correct!
                await message.add_reaction("✅")
                
                game["round"] += 1
                game["multiplier"] = min(game["multiplier"] + 0.5, 10.0)
                
                # Check max
                if game["round"] > 15 or game["multiplier"] >= 10.0:
                    await self.endless_cash_out(message.author.id, message.channel, auto=True)
                    return
                
                # Next word immediately
                word = random.choice(WORD_LISTS[game["difficulty"]])
                scrambled = self.scramble_word(word)
                game["word"] = word
                game["scrambled"] = scrambled
                game["start_time"] = datetime.now()
                
                # Show next word in same channel
                ctx = await self.bot.get_context(message)
                await self.show_endless_word(ctx)
            else:
                # Wrong - lose all
                await message.add_reaction("❌")
                await self.endless_lose(message.author.id, message.channel)
            
            return
        
        # Regular game
        if message.author.id not in self.active_games:
            return
        
        game = self.active_games[message.author.id]
        
        # Only respond if user replied to the game message
        if not message.reference or message.reference.message_id != game.get("message_id"):
            return
        
        # Check if it's a command
        if message.content.startswith('g'):
            return
        
        user_answer = message.content.strip().upper()
        
        # Calculate time taken
        time_taken = (datetime.now() - game["start_time"]).total_seconds()
        
        if time_taken > game["time_limit"]:
            return  # Timeout will handle it
        
        # Check answer
        if user_answer == game["word"]:
            # Correct!
            base_win = int(game["bet"] * game["multiplier"])
            
            # Speed bonus
            speed_bonus = 0
            if time_taken < 10:
                speed_bonus = int(base_win * 0.5)
            
            total_win = base_win + speed_bonus
            
            # Update balance
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET mora = mora + ? WHERE user_id = ?", (total_win, message.author.id))
                
                # Get current streak
                cursor = await db.execute("SELECT scramble_streak FROM game_stats WHERE user_id = ?", (message.author.id,))
                row = await cursor.fetchone()
                current_streak = row[0] if row else 0
                new_streak = current_streak + 1
                
                # Update stats
                await db.execute("""
                    INSERT INTO game_stats (user_id, scramble_games, scramble_wins, scramble_streak, scramble_best_time)
                    VALUES (?, 1, 1, 1, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        scramble_games = scramble_games + 1,
                        scramble_wins = scramble_wins + 1,
                        scramble_streak = scramble_streak + 1,
                        scramble_best_time = MIN(scramble_best_time, ?)
                """, (message.author.id, time_taken, time_taken))
                
                # Get updated balance
                cursor = await db.execute("SELECT mora FROM users WHERE user_id = ?", (message.author.id,))
                balance = (await cursor.fetchone())[0]
                
                await db.commit()
            
            # Create success embed
            embed = discord.Embed(
                title="<a:Trophy:1438199339586424925> CORRECT!",
                description=(
                    f"**The word was:** {game['word']}\n\n"
                    f"⏱️ **Solved in:** {time_taken:.1f} seconds\n"
                    f"**Base Win:** {base_win:,} <:mora:1437958309255577681>\n"
                    f"**Difficulty:** {game['difficulty'].title()} ({game['multiplier']:.1f}x)\n"
                ),
                color=0x2ECC71
            )
            embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
            
            if speed_bonus > 0:
                embed.add_field(name="⚡ Speed Bonus", value=f"+{speed_bonus:,} mora", inline=False)
            
            if new_streak > 1:
                embed.add_field(name="🔥 Streak", value=f"{new_streak} in a row!", inline=False)
            
            embed.add_field(name="Total Won", value=f"**{total_win:,}** <:mora:1437958309255577681>", inline=False)
            embed.set_footer(text=f"New Balance: {balance:,} mora")
            
            await send_embed(message.channel, embed)
            
            # Remove game
            del self.active_games[message.author.id]
            
        elif len(user_answer) >= 3:  # Only respond to serious attempts
            # Wrong answer
            embed = discord.Embed(
                title="❌ Wrong Answer",
                description=f"**{user_answer}** is not correct. Keep trying!",
                color=0xE74C3C
            )
            embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
            time_left = game["time_limit"] - time_taken
            embed.set_footer(text=f"Time left: {int(time_left)}s | Hint available: ghint")
            await send_embed(message.channel, embed)

    async def show_stats(self, ctx):
        """Show user's scramble statistics"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT scramble_games, scramble_wins, scramble_losses, scramble_streak, scramble_best_time
                FROM game_stats WHERE user_id = ?
            """, (ctx.author.id,))
            row = await cursor.fetchone()
        
        if not row or row[0] == 0:
            return await ctx.send("❌ You haven't played any scramble games yet!")
        
        games, wins, losses, streak, best_time = row
        win_rate = (wins / games * 100) if games > 0 else 0
        avg_time = best_time if best_time else 0
        
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Scramble Stats",
            color=0x3498DB
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="Games Played", value=f"{games}", inline=True)
        embed.add_field(name="✅ Wins", value=f"{wins}", inline=True)
        embed.add_field(name="❌ Losses", value=f"{losses}", inline=True)
        embed.add_field(name="📈 Win Rate", value=f"{win_rate:.1f}%", inline=True)
        embed.add_field(name="🔥 Current Streak", value=f"{streak}", inline=True)
        embed.add_field(name="⚡ Best Time", value=f"{avg_time:.1f}s" if avg_time > 0 else "N/A", inline=True)
        
        await send_embed(ctx, embed)

async def setup(bot):
    await bot.add_cog(Scramble(bot))
