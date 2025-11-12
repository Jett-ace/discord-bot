# Character Pool
characters = [
    # 5★ characters (expanded)
    {"name": "Diluc", "rarity": "5★", "element": "Pyro", "hp": 1200, "atk": 300},
    {"name": "Keqing", "rarity": "5★", "element": "Electro", "hp": 1150, "atk": 310},
    {"name": "Mona", "rarity": "5★", "element": "Hydro", "hp": 1100, "atk": 295},
    {"name": "Traveler", "rarity": "5★", "element": "Anemo", "hp": 1225, "atk": 295},
    {"name": "Qiqi", "rarity": "5★", "element": "Cryo", "hp": 1250, "atk": 280},
    {"name": "Venti", "rarity": "5★", "element": "Anemo", "hp": 1120, "atk": 270},
    {"name": "Zhongli", "rarity": "5★", "element": "Geo", "hp": 1400, "atk": 260},
    {"name": "Ganyu", "rarity": "5★", "element": "Cryo", "hp": 1300, "atk": 320},
    {"name": "Hu Tao", "rarity": "5★", "element": "Pyro", "hp": 1050, "atk": 340},
    {"name": "Xiao", "rarity": "5★", "element": "Anemo", "hp": 1180, "atk": 330},
    {"name": "Klee", "rarity": "5★", "element": "Pyro", "hp": 980, "atk": 350},
    {"name": "Ayaka", "rarity": "5★", "element": "Cryo", "hp": 1080, "atk": 310},
    {"name": "Tartaglia", "rarity": "5★", "element": "Hydro", "hp": 1220, "atk": 325},
    {"name": "Albedo", "rarity": "5★", "element": "Geo", "hp": 1160, "atk": 285},
    {"name": "Jean", "rarity": "5★", "element": "Anemo", "hp": 1190, "atk": 300},
    {"name": "Eula", "rarity": "5★", "element": "Cryo", "hp": 1280, "atk": 340},
    {"name": "Gorou", "rarity": "3★", "element": "Geo", "hp": 990, "atk": 210},
    # 4★ characters (expanded)
    {"name": "Fischl", "rarity": "4★", "element": "Electro", "hp": 950, "atk": 200},
    {"name": "Sucrose", "rarity": "4★", "element": "Anemo", "hp": 970, "atk": 210},
    {"name": "Noelle", "rarity": "4★", "element": "Geo", "hp": 1020, "atk": 220},
    {"name": "Beidou", "rarity": "4★", "element": "Electro", "hp": 980, "atk": 215},
    {"name": "Xingqiu", "rarity": "4★", "element": "Hydro", "hp": 940, "atk": 205},
    {"name": "Razor", "rarity": "4★", "element": "Electro", "hp": 970, "atk": 225},
    {"name": "Barbara", "rarity": "4★", "element": "Hydro", "hp": 930, "atk": 190},
    {"name": "Bennett", "rarity": "4★", "element": "Pyro", "hp": 900, "atk": 195},
    {"name": "Ningguang", "rarity": "4★", "element": "Geo", "hp": 980, "atk": 210},
    {"name": "Chongyun", "rarity": "4★", "element": "Cryo", "hp": 920, "atk": 205},
    # 3★ characters (expanded)
    {"name": "Amber", "rarity": "3★", "element": "Pyro", "hp": 730, "atk": 110},
    {"name": "Kaeya", "rarity": "3★", "element": "Cryo", "hp": 800, "atk": 120},
    {"name": "Lisa", "rarity": "3★", "element": "Electro", "hp": 780, "atk": 115},
    {"name": "Xiangling", "rarity": "3★", "element": "Pyro", "hp": 780, "atk": 120},
    {"name": "Diona", "rarity": "3★", "element": "Cryo", "hp": 740, "atk": 95},
    {"name": "Xinyan", "rarity": "3★", "element": "Pyro", "hp": 740, "atk": 100},

    # Additional 5★ additions
    {"name": "Raiden Shogun", "rarity": "5★", "element": "Electro", "hp": 1180, "atk": 305},
    {"name": "Kazuha", "rarity": "5★", "element": "Anemo", "hp": 1100, "atk": 290},
    {"name": "Tighnari", "rarity": "5★", "element": "Dendro", "hp": 1120, "atk": 315},
    {"name": "Alhaitham", "rarity": "5★", "element": "Dendro", "hp": 1090, "atk": 320},

    # Additional 4★ additions
    {"name": "Thoma", "rarity": "4★", "element": "Pyro", "hp": 960, "atk": 205},
    {"name": "Kokomi", "rarity": "5★", "element": "Hydro", "hp": 1890, "atk": 200},
    {"name": "Sayu", "rarity": "3★", "element": "Anemo", "hp": 930, "atk": 190},
    {"name": "Kirara", "rarity": "3★", "element": "Electro", "hp": 940, "atk": 195},

    # Additional 3★ additions
    {"name": "Lyney", "rarity": "5★", "element": "Anemo", "hp": 1150, "atk": 280},
    {"name": "wanderer", "rarity": "4★", "element": "Hydro", "hp": 710, "atk": 95},
]

rarity_weights = {"5★": 0.01, "4★": 0.14, "3★": 0.85}

city_lookup = {
    "Diluc": "Mondstadt", "Amber": "Mondstadt", "Kaeya": "Mondstadt",
    "Lisa": "Mondstadt", "Barbara": "Mondstadt", "Venti": "Mondstadt",
    "Qiqi": "Liyue", "Keqing": "Liyue", "Mona": "Mondstadt",
    "Zhongli": "Liyue", "Razor": "Mondstadt", "Xiangling": "Liyue",
    "Diona": "Mondstadt", "Xinyan": "Liyue", "Traveler": "Unknown",
    "Ganyu": "Liyue", "Hu Tao": "Liyue", "Xiao": "Liyue", "Klee": "Mondstadt",
    "Ayaka": "Inazuma", "Tartaglia": "Snezhnaya", "Albedo": "Mondstadt", "Jean": "Mondstadt",
    "Eula": "Mondstadt", "Bennett": "Mondstadt", "Ningguang": "Liyue", "Chongyun": "Liyue"
}

filtered_words = ["nigger", "bitch", "cunt", "faggot"]

# Regions / map for exploration dispatches
regions = {
    # key: canonical lower-case name -> display name and level
    # Levels represent region difficulty tiers — these correspond to unlock levels in the account progression system
    "mondstadt": {"name": "Mondstadt", "level": 0},
    "liyue": {"name": "Liyue", "level": 5},
    "inazuma": {"name": "Inazuma", "level": 10},
    "sumeru": {"name": "Sumeru", "level": 25},
    "fontaine": {"name": "Fontaine", "level": 35},
    "natlan": {"name": "Natlan", "level": 45},
    "snezhnaya": {"name": "Snezhnaya", "level": 50},
}

# Optional local path for the map image used by `!map`.
# Place your map image at this path (relative to the bot project root) to have it shown in the embed.
MAP_IMAGE_PATH = "assets/teyvat_map.png"

# Gameplay tuning constants (change these to balance progression)
EXP_TUNING = {
    # EXP awarded per single wish
    "wish": 50,
    # EXP per region level when claiming a dispatch (dispatch_exp = region_level * value)
    "dispatch_per_region_level": 10,
    # EXP awarded when opening chests (kept here for central tuning)
    "chest_common": 10,
    "chest_exquisite": 25,
    "chest_precious": 50,
    "chest_luxurious": 100,
}

# Minimum account level required to use fishing
FISHING_MIN_LEVEL = 5

# Fish pool with 3 rarities: Common, Rare, Mythic
fish_pool = [
    # Common fish (5 total) - 80% chance
    {"name": "Medaka", "rarity": "Common", "icon": "🐟"},
    {"name": "Dawncatcher", "rarity": "Common", "icon": "🐟"},
    {"name": "Glaze Medaka", "rarity": "Common", "icon": "🐟"},
    {"name": "Sweet-Flower Medaka", "rarity": "Common", "icon": "🐟"},
    {"name": "Aizen Medaka", "rarity": "Common", "icon": "🐟"},
    
    # Rare fish (7 total) - 18% chance
    {"name": "Betta", "rarity": "Rare", "icon": "🐠"},
    {"name": "Venomspine Fish", "rarity": "Rare", "icon": "🐠"},
    {"name": "Golden Koi", "rarity": "Rare", "icon": "🐠"},
    {"name": "Rusty Koi", "rarity": "Rare", "icon": "🐠"},
    {"name": "Crystalfish", "rarity": "Rare", "icon": "🐠"},
    {"name": "Lunged Stickleback", "rarity": "Rare", "icon": "🐠"},
    {"name": "Akai Maou", "rarity": "Rare", "icon": "🐠"},
    
    # Mythic fish (3 total) - 2% chance
    {"name": "Raimei Angelfish", "rarity": "Mythic", "icon": "🐡"},
    {"name": "Peach of the Deep Waves", "rarity": "Mythic", "icon": "🐡"},
    {"name": "Abiding Angelfish", "rarity": "Mythic", "icon": "🐡"},
]

fish_rarity_weights = {"Common": 0.80, "Rare": 0.18, "Mythic": 0.02}