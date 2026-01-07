"""Central registry of achievement definitions.

Small convenience helpers to look up titles/descriptions by key. This file is
meant to centralize achievement metadata so cogs can refer to keys safely.
"""

# Achievement categories with emojis
ACHIEVEMENT_CATEGORIES = {
    "minigames": {"name": "🎮 Minigame Master", "emoji": "🎮"},
    "social": {"name": "👥 Social Player", "emoji": "👥"},
    "economy": {"name": "💰 Economy", "emoji": "💰"},
    "dedication": {"name": "🎯 Dedication", "emoji": "🎯"},
    "special": {"name": "⭐ Special", "emoji": "⭐"},
}

ACHIEVEMENTS = {
    # Daily Streak Achievements - 50k Mora each
    "daily_streak_10": {
        "title": "Dedicated Week+",
        "description": "Claimed daily rewards for 10 days in a row!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "dedication",
    },
    "daily_streak_20": {
        "title": "Three Week Warrior",
        "description": "Claimed daily rewards for 20 days in a row!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "dedication",
    },
    "daily_streak_30": {
        "title": "Monthly Master",
        "description": "Claimed daily rewards for 30 days in a row!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "dedication",
    },
    "daily_streak_50": {
        "title": "Dedicated Player",
        "description": "Claimed daily rewards for 50 days in a row!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "dedication",
    },
    "daily_streak_100": {
        "title": "Centennial Champion",
        "description": "Claimed daily rewards for 100 days in a row!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "dedication",
    },
    
    # RPS Achievements
    "rps_win_10": {
        "title": "RPS Novice",
        "description": "Win 10 games of Rock Paper Scissors!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    "rps_win_50": {
        "title": "RPS Expert",
        "description": "Win 50 games of Rock Paper Scissors!",
        "reward": "100,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    "rps_win_100": {
        "title": "RPS Master",
        "description": "Win 100 games of Rock Paper Scissors!",
        "reward": "250,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    
    # Multiplayer Achievements
    "play_multiplayer_50": {
        "title": "Social Butterfly",
        "description": "Play 50 games against other players!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "social",
    },
    "play_multiplayer_100": {
        "title": "Community Favorite",
        "description": "Play 100 games against other players!",
        "reward": "100,000 <:mora:1437958309255577681>",
        "category": "social",
    },
    "play_multiplayer_250": {
        "title": "Tournament Regular",
        "description": "Play 250 games against other players!",
        "reward": "200,000 <:mora:1437958309255577681>",
        "category": "social",
    },
    
    # Connect4 Achievements
    "connect4_win_10": {
        "title": "Connect4 Starter",
        "description": "Win 10 games of Connect4!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    "connect4_win_25": {
        "title": "Connect4 Pro",
        "description": "Win 25 games of Connect4!",
        "reward": "75,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    
    # TicTacToe Achievements
    "tictactoe_win_10": {
        "title": "Tic-Tac-Toe Rookie",
        "description": "Win 10 games of Tic-Tac-Toe!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    "tictactoe_win_25": {
        "title": "Tic-Tac-Toe Champion",
        "description": "Win 25 games of Tic-Tac-Toe!",
        "reward": "75,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    
    # Blackjack Achievements
    "blackjack_win_10": {
        "title": "Blackjack Beginner",
        "description": "Win 10 games of Blackjack!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    "blackjack_win_50": {
        "title": "Card Shark",
        "description": "Win 50 games of Blackjack!",
        "reward": "100,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    "blackjack_natural_10": {
        "title": "Natural 21",
        "description": "Get 10 natural blackjacks!",
        "reward": "75,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    
    # Slots Achievements
    "slots_jackpot_1": {
        "title": "First Jackpot",
        "description": "Hit your first jackpot on slots!",
        "reward": "100,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    "slots_play_100": {
        "title": "Slot Enthusiast",
        "description": "Play 100 games of slots!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    
    # Coinflip Achievements
    "coinflip_win_10": {
        "title": "Lucky Flipper",
        "description": "Win 10 coinflips!",
        "reward": "25,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    "coinflip_streak_5": {
        "title": "Flip Streak",
        "description": "Win 5 coinflips in a row!",
        "reward": "100,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    
    # Mines Achievements
    "mines_cash_100k": {
        "title": "Mine Survivor",
        "description": "Cash out with 100k+ profit in Mines!",
        "reward": "75,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    "mines_reveal_15": {
        "title": "Risk Taker",
        "description": "Reveal 15 safe tiles in one Mines game!",
        "reward": "150,000 <:mora:1437958309255577681>",
        "category": "minigames",
    },
    
    # Economy Achievements
    "earn_1m": {
        "title": "Millionaire",
        "description": "Earn 1,000,000 Mora total!",
        "reward": "100,000 <:mora:1437958309255577681>",
        "category": "economy",
    },
    "earn_10m": {
        "title": "Multi-Millionaire",
        "description": "Earn 10,000,000 Mora total!",
        "reward": "500,000 <:mora:1437958309255577681>",
        "category": "economy",
    },
    "wallet_500k": {
        "title": "Big Spender",
        "description": "Have 500,000 Mora in your wallet at once!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "economy",
    },
    "bank_deposit_1m": {
        "title": "Smart Saver",
        "description": "Deposit 1,000,000 Mora in the bank!",
        "reward": "75,000 <:mora:1437958309255577681>",
        "category": "economy",
    },
    
    # Rob Achievements
    "rob_success_10": {
        "title": "Petty Thief",
        "description": "Successfully rob 10 players!",
        "reward": "50,000 <:mora:1437958309255577681>",
        "category": "economy",
    },
    "rob_success_50": {
        "title": "Master Thief",
        "description": "Successfully rob 50 players!",
        "reward": "150,000 <:mora:1437958309255577681>",
        "category": "economy",
    },
    "rob_steal_100k": {
        "title": "Big Heist",
        "description": "Steal 100k+ Mora in a single robbery!",
        "reward": "100,000 <:mora:1437958309255577681>",
        "category": "economy",
    },
    
    # Special Achievements
    "first_game": {
        "title": "First Steps",
        "description": "Play your first minigame!",
        "reward": "10,000 <:mora:1437958309255577681>",
        "category": "special",
    },
    "play_all_games": {
        "title": "Game Connoisseur",
        "description": "Play every minigame at least once!",
        "reward": "200,000 <:mora:1437958309255577681>",
        "category": "special",
    },
}


def get_category_emoji(category: str) -> str:
    """Get emoji for achievement category."""
    return ACHIEVEMENT_CATEGORIES.get(category, {}).get("emoji", "🏆")


def get_achievements_by_category():
    """Return achievements organized by category."""
    categorized = {cat: [] for cat in ACHIEVEMENT_CATEGORIES.keys()}
    categorized["uncategorized"] = []

    for key, meta in ACHIEVEMENTS.items():
        category = meta.get("category", "uncategorized")
        categorized[category].append((key, meta))

    return categorized


def get_achievement_meta(key: str):
    return ACHIEVEMENTS.get(key, {"title": key, "description": ""})


async def send_achievement_notification(user, ach_key: str, ctx=None):
    """Send a fancy achievement unlock notification."""
    import discord

    from utils.embed import send_embed

    meta = get_achievement_meta(ach_key)
    title = meta.get("title", ach_key)
    desc = meta.get("description", "")
    reward = meta.get("reward", "")
    category = meta.get("category", "special")
    cat_emoji = get_category_emoji(category)

    embed = discord.Embed(
        title="🎉 Achievement Unlocked!",
        description=f"{cat_emoji} **{title}**",
        color=0xF39C12,
    )

    if desc:
        embed.add_field(name="Description", value=desc, inline=False)

    if reward:
        embed.add_field(name="🎁 Reward", value=reward, inline=False)

    embed.set_thumbnail(url="https://i.imgur.com/D3pQiHu.png")  # Trophy image
    embed.set_footer(text="Check gachievements to see all your unlocked achievements!")

    # Only send in channel context, no DMs
    try:
        if ctx:
            await send_embed(ctx, embed)
    except Exception:
        pass
