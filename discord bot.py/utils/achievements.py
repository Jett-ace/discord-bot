"""Central registry of achievement definitions.

Small convenience helpers to look up titles/descriptions by key. This file is
meant to centralize achievement metadata so cogs can refer to keys safely.
"""
ACHIEVEMENTS = {
    "first_fish": {
        "title": "First Cast",
        "description": "You fished for the first time."
    },
    "first_chest": {
        "title": "Opened a Chest",
        "description": "You opened your first chest."
    },
    "first_5star": {
        "title": "First 5★",
        "description": "You pulled your first 5★ character!"
    },
    "level_10": {
        "title": "Reached Level 10",
        "description": "You achieved account level 10."
    },
    "level_20": {
        "title": "Bronze Adventurer",
        "description": "Reached level 20!"
    },
    "level_50": {
        "title": "Silver Traveler",
        "description": "Reached level 50!"
    },
    "level_100": {
        "title": "Golden Legend",
        "description": "Reached level 100!"
    },
    # Fishing achievements
    "first_fish_caught": {
        "title": "Angler",
        "description": "You caught your first fish!",
        "reward": "3 <:essence:1437463601479942385> Hydro Essence"
    },
    "first_mythic": {
        "title": "Mythic Catch",
        "description": "You caught your first mythic fish!",
        "reward": "5 <:essence:1437463601479942385> Hydro Essence"
    },
    "all_common_fish": {
        "title": "Common Collector",
        "description": "Caught all 5 common fish species!",
        "reward": "10 <:essence:1437463601479942385> Hydro Essence"
    },
    "all_rare_fish": {
        "title": "Rare Hunter",
        "description": "Caught all 7 rare fish species!",
        "reward": "3 <:crystal:1437458982989205624> Hydro Crystal"
    },
    "all_mythic_fish": {
        "title": "Mythic Master",
        "description": "Caught all 3 mythic fish species!",
        "reward": "5 <:crystal:1437458982989205624> Hydro Crystal"
    },
    "fish_10": {
        "title": "Novice Angler",
        "description": "Caught 10 fish total.",
        "reward": "5 <:essence:1437463601479942385> Hydro Essence"
    },
    "fish_50": {
        "title": "Experienced Angler",
        "description": "Caught 50 fish total.",
        "reward": "2 <:crystal:1437458982989205624> Hydro Crystal"
    },
    "fish_100": {
        "title": "Master Angler",
        "description": "Caught 100 fish total.",
        "reward": "5 <:crystal:1437458982989205624> Hydro Crystal"
    },
    "fish_master": {
        "title": "Fish Encyclopedia",
        "description": "Caught every single fish in Teyvat!",
        "reward": "10 <:crystal:1437458982989205624> Hydro Crystal"
    },
    "daily_streak_50": {
        "title": "Dedicated Daily",
        "description": "Reached a 50-day streak!",
        "reward": "5 <:random:1437977751520018452> random chests"
    },
    "daily_streak_100": {
        "title": "Committed Adventurer",
        "description": "Reached a 100-day streak!",
        "reward": "5 <:random:1437977751520018452> random chests"
    },
    "daily_streak_200": {
        "title": "Loyal Traveler",
        "description": "Reached a 200-day streak!",
        "reward": "5 <:random:1437977751520018452> random chests"
    },
    "daily_streak_365": {
        "title": "Year-Long Journey",
        "description": "Reached a 365-day streak!",
        "reward": "5 <:random:1437977751520018452> random chests"
    },
    "daily_streak_500": {
        "title": "Unwavering Spirit",
        "description": "Reached a 500-day streak!",
        "reward": "5 <:random:1437977751520018452> random chests"
    },
    "daily_streak_1000": {
        "title": "Eternal Dedication",
        "description": "Reached a 1000-day streak!",
        "reward": "5 <:random:1437977751520018452> random chests"
    },
}


def get_achievement_meta(key: str):
    return ACHIEVEMENTS.get(key, {"title": key, "description": ""})
