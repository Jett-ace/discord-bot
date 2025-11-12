# Discord Bot - Project Structure

## 📁 Folder Organization

```
discord bot.py/
├── bot.py              # Main bot entry point
├── config.py           # Bot configuration settings
├── requirements.txt    # Python dependencies
│
├── cogs/              # Bot commands organized by category
│   ├── achievements.py
│   ├── blackjack.py
│   ├── explore.py
│   ├── fishing.py
│   ├── gacha.py
│   ├── games.py
│   ├── genshinc.py
│   ├── help.py
│   ├── inventory.py
│   ├── moderation.py
│   ├── shinanigans.py
│   └── tictactoe.py
│
├── utils/             # Helper utilities
│   ├── achievements.py
│   ├── chest_config.py
│   ├── constants.py
│   ├── database.py
│   ├── db_validator.py
│   ├── embed.py
│   ├── emoji.py
│   └── logger.py
│
├── data/              # Database and data files
│   ├── gacha.db          # Main database
│   ├── gacha.db.bak      # Database backup
│   └── genshin_key.key   # Encryption key
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

- **Game System**: Gacha, Blackjack, Slots, Mines, Connect4, RPS
- **Fishing System**: Catch fish and collect pets
- **Achievement System**: Track player milestones
- **Moderation Tools**: Message logging, purge, filtering
- **Genshin Integration**: Daily check-in, redemption codes
- **Database Validation**: Auto-checks on startup
- **Logging System**: Daily rotating logs for debugging

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

Configure with `!logfilter` to toggle logging for:
- 🤖 Bot messages
- 👥 Regular members
- 🛡️ Moderators

Log channel names: `logs`, `mod-logs`, `message-logs`, `deleted-messages`
