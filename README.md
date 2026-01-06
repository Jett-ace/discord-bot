# Discord Bot - Fate Series Edition

## 📁 Folder Organization

```
discord bot.py/
├── bot.py              # Main bot entry point
├── config.py           # Bot configuration settings
├── requirements.txt    # Python dependencies
│
├── cogs/              # Bot commands organized by category
│   ├── achievements.py   # Achievement tracking
│   ├── battle.py         # Command Card PvP battles
│   ├── blackjack.py      # Card game
│   ├── cardlevel.py      # Servant leveling system
│   ├── explore.py        # Exploration
│   ├── fishing.py        # Fishing minigame
│   ├── gacha.py          # Servant summoning
│   ├── games.py          # Mini-games
│   ├── help.py           # Command list
│   ├── inventory.py      # Item/Servant management
│   ├── moderation.py     # Server moderation
│   └── tictactoe.py      # Tic-tac-toe
│
├── utils/             # Helper utilities
│   ├── achievements.py   # Achievement logic
│   ├── chest_config.py   # Chest rewards
│   ├── constants.py      # Servants, passives, classes
│   ├── database.py       # SQLite operations
│   ├── db_validator.py   # Database integrity
│   ├── embed.py          # Discord embeds
│   ├── emoji.py          # Custom emojis
│   └── logger.py         # Logging system
│
├── data/              # Database and data files
│   ├── gacha.db          # Main database
│   └── gacha.db.bak      # Database backup
│
├── logs/              # Daily log files
│   └── bot_YYYY-MM-DD.log
│
├── scripts/           # Utility scripts
│   └── fix_database.py
│
└── tests/             # Unit tests
    ├── test_achievements.py
    └── test_blackjack_sim.py
```

## 🚀 Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure `.env` file with your bot token

3. Run the bot:
   ```bash
   python bot.py
   ```

## 📝 Key Features

### ⚔️ Fate/Grand Order Mechanics
- **Servant Summoning**: Gacha system with 30+ Servants (SSR/SR/R rarities)
- **Command Card System**: Strategic turn-based combat with Buster/Arts/Quick cards
- **Servant Classes**: 8 classes with unique advantages (Saber, Archer, Lancer, Rider, Caster, Assassin, Berserker, Ruler)
- **Noble Phantasms**: Ultimate abilities charged through Arts cards
- **Passive Abilities**: 30+ unique passive skills per Servant
- **Card Leveling**: Individual Servant progression with stat growth
- **NP Gauge System**: Build NP through Arts/Quick cards, unleash devastating attacks

### 🎮 Game Systems
- **PvP Battles**: Interactive Command Card battles with NP mechanics
- **Mini-Games**: Blackjack, Slots, Mines, Connect4, RPS
- **Fishing System**: Catch fish and collect pets
- **Achievement System**: Track player milestones
- **Card Progression**: Level up Servants with EXP bottles (200 EXP each)
- **Account Leveling**: Gain EXP from summoning (20 per roll) and battles (500 per win)

### 🛠️ Additional Features
- **Moderation Tools**: Message logging, purge, filtering
- **Database Validation**: Auto-checks on startup
- **Logging System**: Daily rotating logs for debugging
- **Chest Rewards**: Random loot from battles and exploration

## 🔧 Configuration

Edit `config.py` to customize:
- Max wishes limit
- Reset timers
- Database path
- Owner ID

## 📊 Minigame Bet Limits

All gambling games have standardized limits:
- **Minimum bet**: 1,000 Mora
- **Maximum bet**: 200,000 Mora

## 🗂️ Message Logging

Configure with `glogfilter` to toggle logging for:
- 🤖 Bot messages
- 👥 Regular members
- 🛡️ Moderators

Log channel names: `logs`, `mod-logs`, `message-logs`, `deleted-messages`
