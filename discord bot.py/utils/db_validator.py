"""Database validation utility to check schema integrity on startup."""
import aiosqlite
from config import DB_PATH
from utils.logger import setup_logger

logger = setup_logger("DatabaseValidator")

# Required tables and their critical columns
REQUIRED_SCHEMA = {
    "users": ["user_id", "mora", "dust", "fates"],
    "pulls": ["id", "user_id", "username", "character_name", "rarity"],
    "user_wishes": ["user_id", "count", "reset", "pity"],
    "chests": ["user_id", "count"],
    "chest_inventory": ["user_id", "common", "exquisite", "precious", "luxurious"],
    "dispatches": ["id", "user_id", "character_name", "region", "rarity", "start", "end", "claimed"],
    "shop_purchases": ["user_id", "date", "count"],
    "shop_item_purchases": ["user_id", "date", "item_key", "count"],
    "accounts": ["user_id", "exp", "level"],
    "level_claims": ["user_id", "level", "claimed"],
    "badges": ["user_id", "badge_key"],
    "achievements": ["user_id", "ach_key", "title", "description", "awarded_at"],
    "user_items": ["user_id", "item_key", "count"],
    "fish_caught": ["user_id", "fish_name", "count", "first_caught"],
    "fish_pets": ["id", "user_id", "fish_name", "level", "exp"],
    "daily_claims": ["user_id", "last_claim", "streak"],
    "genshin_accounts": ["user_id", "email", "password", "uid", "region", "auto_redeem", "daily_checkin"]
}

async def validate_database():
    """Validate that all required tables and columns exist.
    
    Returns:
        tuple: (success: bool, issues: list[str])
    """
    issues = []
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Get all tables
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
                tables = await cursor.fetchall()
                existing_tables = {table[0] for table in tables}
            
            # Check each required table
            for table_name, required_columns in REQUIRED_SCHEMA.items():
                if table_name not in existing_tables:
                    issues.append(f"Missing table: {table_name}")
                    continue
                
                # Get columns for this table
                async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
                    columns = await cursor.fetchall()
                    existing_columns = {col[1] for col in columns}  # col[1] is column name
                
                # Check required columns
                for col_name in required_columns:
                    if col_name not in existing_columns:
                        issues.append(f"Missing column: {table_name}.{col_name}")
            
            if issues:
                logger.warning(f"Database validation found {len(issues)} issue(s):")
                for issue in issues:
                    logger.warning(f"  - {issue}")
                return False, issues
            else:
                logger.info("Database validation passed: all required tables and columns exist.")
                return True, []
                
    except Exception as e:
        logger.error(f"Database validation failed with error: {e}")
        return False, [f"Validation error: {e}"]

async def repair_database():
    """Attempt to repair missing columns by running init_db.
    
    This will create missing tables and add missing columns where possible.
    """
    try:
        from utils.database import init_db
        logger.info("Attempting to repair database schema...")
        await init_db()
        
        # Re-validate
        success, issues = await validate_database()
        if success:
            logger.info("Database repair successful!")
        else:
            logger.warning("Database repair completed but some issues remain:")
            for issue in issues:
                logger.warning(f"  - {issue}")
        
        return success
    except Exception as e:
        logger.error(f"Database repair failed: {e}")
        return False
