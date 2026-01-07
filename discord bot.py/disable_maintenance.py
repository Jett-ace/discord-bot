import sqlite3
import os

db_path = 'data/gacha.db'

# Check if database exists
if not os.path.exists(db_path):
    print(f"❌ Database not found at {db_path}")
    print("Current directory:", os.getcwd())
else:
    # Connect to database and disable maintenance
    conn = sqlite3.connect(db_path)
    
    # Check current value
    cursor = conn.execute("SELECT value FROM bot_settings WHERE key = 'maintenance_mode'")
    row = cursor.fetchone()
    if row:
        print(f"Current maintenance mode: {row[0]}")
    else:
        print("No maintenance mode setting found")
    
    # Delete or set to 0
    conn.execute("DELETE FROM bot_settings WHERE key = 'maintenance_mode'")
    conn.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('maintenance_mode', '0')")
    conn.commit()
    
    # Verify
    cursor = conn.execute("SELECT value FROM bot_settings WHERE key = 'maintenance_mode'")
    row = cursor.fetchone()
    print(f"New maintenance mode: {row[0] if row else 'deleted'}")
    
    conn.close()
    
    print("\n✅ Maintenance mode has been DISABLED!")
    print("You can now restart the bot and it should work.")
