import sqlite3

# Connect to the database
conn = sqlite3.connect('../data/gacha.db')
cursor = conn.cursor()

try:
    # Add the missing daily_checkin column
    cursor.execute("ALTER TABLE genshin_accounts ADD COLUMN daily_checkin INTEGER DEFAULT 0")
    conn.commit()
    print("✅ Successfully added daily_checkin column to genshin_accounts table!")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("ℹ️ Column daily_checkin already exists!")
    else:
        print(f"❌ Error: {e}")
finally:
    conn.close()
