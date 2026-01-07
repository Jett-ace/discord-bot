"""Migration script to remove all Genshin characters from database and keep only Fate Servants"""
import sqlite3
import sys
import os

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import DB_PATH
from utils.constants import characters

# Get list of valid Fate Servant names
VALID_SERVANTS = {char['name'] for char in characters}

def migrate_database():
    """Remove all Genshin character pulls from database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all unique character names in database
    cursor.execute("SELECT DISTINCT character_name FROM pulls")
    db_characters = [row[0] for row in cursor.fetchall()]
    
    print(f"Found {len(db_characters)} unique characters in database")
    print(f"Valid Fate Servants: {len(VALID_SERVANTS)}")
    
    # Find Genshin characters to remove
    genshin_chars = [name for name in db_characters if name not in VALID_SERVANTS]
    
    if not genshin_chars:
        print("\n✓ No Genshin characters found! Database is clean.")
        conn.close()
        return
    
    print(f"\n⚠ Found {len(genshin_chars)} Genshin characters to remove:")
    for char in sorted(genshin_chars):
        print(f"  - {char}")
    
    # Count total pulls to be deleted
    placeholders = ','.join('?' * len(genshin_chars))
    cursor.execute(f"SELECT COUNT(*) FROM pulls WHERE character_name IN ({placeholders})", genshin_chars)
    total_pulls = cursor.fetchone()[0]
    
    print(f"\nThis will delete {total_pulls} pull records.")
    
    response = input("\nProceed with deletion? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Migration cancelled.")
        conn.close()
        return
    
    # Delete Genshin character pulls
    cursor.execute(f"DELETE FROM pulls WHERE character_name IN ({placeholders})", genshin_chars)
    conn.commit()
    
    print(f"\n✓ Successfully deleted {cursor.rowcount} Genshin character records!")
    
    # Show remaining characters
    cursor.execute("SELECT DISTINCT character_name FROM pulls ORDER BY character_name")
    remaining = [row[0] for row in cursor.fetchall()]
    
    if remaining:
        print(f"\n✓ Remaining Fate Servants in database ({len(remaining)}):")
        for char in remaining:
            print(f"  - {char}")
    else:
        print("\n⚠ Database is now empty (no character pulls)")
    
    conn.close()
    print("\n✓ Migration complete!")

if __name__ == "__main__":
    print("=" * 60)
    print("FATE SERIES MIGRATION")
    print("=" * 60)
    print("\nThis script will remove ALL Genshin Impact characters")
    print("from your database, keeping only Fate Servants.\n")
    
    migrate_database()
