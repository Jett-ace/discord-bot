"""Transaction Logger - Track major economy events"""
import aiosqlite
from datetime import datetime
from config import DB_PATH


async def init_transaction_logs():
    """Initialize transaction logs table"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transaction_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                amount INTEGER,
                details TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        await db.commit()


async def log_transaction(user_id: int, event_type: str, amount: int = None, details: str = None):
    """Log a transaction event
    
    Args:
        user_id: Discord user ID
        event_type: Type of event (loan, deposit, withdrawal, big_win, rob, etc.)
        amount: Mora amount involved (can be negative for losses)
        details: Additional details about the transaction
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await init_transaction_logs()
        await db.execute(
            """INSERT INTO transaction_logs (user_id, event_type, amount, details, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, event_type, amount, details, datetime.now().isoformat())
        )
        await db.commit()


async def get_user_transactions(user_id: int, limit: int = 20):
    """Get recent transactions for a user"""
    async with aiosqlite.connect(DB_PATH) as db:
        await init_transaction_logs()
        cursor = await db.execute(
            """SELECT event_type, amount, details, timestamp 
               FROM transaction_logs 
               WHERE user_id = ? 
               ORDER BY id DESC 
               LIMIT ?""",
            (user_id, limit)
        )
        rows = await cursor.fetchall()
        return rows


async def get_recent_transactions(limit: int = 50):
    """Get recent transactions across all users"""
    async with aiosqlite.connect(DB_PATH) as db:
        await init_transaction_logs()
        cursor = await db.execute(
            """SELECT user_id, event_type, amount, details, timestamp 
               FROM transaction_logs 
               ORDER BY id DESC 
               LIMIT ?""",
            (limit,)
        )
        rows = await cursor.fetchall()
        return rows


async def get_transactions_by_type(event_type: str, limit: int = 20):
    """Get recent transactions of a specific type"""
    async with aiosqlite.connect(DB_PATH) as db:
        await init_transaction_logs()
        cursor = await db.execute(
            """SELECT user_id, amount, details, timestamp 
               FROM transaction_logs 
               WHERE event_type = ? 
               ORDER BY id DESC 
               LIMIT ?""",
            (event_type, limit)
        )
        rows = await cursor.fetchall()
        return rows
