"""Permission system for admin commands"""
import aiosqlite
from config import DB_PATH, OWNER_ID


async def init_permissions_db():
    """Initialize the permissions database table"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS command_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                role_id INTEGER,
                user_id INTEGER,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, command_name, role_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS disabled_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                disabled_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, channel_id, command_name)
            )
        """)
        await db.commit()


async def add_permission(guild_id: int, command_name: str, role_id: int = None, user_id: int = None):
    """Add permission for a role or user to use a command"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO command_permissions (guild_id, command_name, role_id, user_id)
            VALUES (?, ?, ?, ?)
        """, (guild_id, command_name.lower(), role_id, user_id))
        await db.commit()


async def remove_permission(guild_id: int, command_name: str, role_id: int = None, user_id: int = None):
    """Remove permission for a role or user to use a command"""
    async with aiosqlite.connect(DB_PATH) as db:
        if role_id:
            await db.execute("""
                DELETE FROM command_permissions 
                WHERE guild_id = ? AND command_name = ? AND role_id = ?
            """, (guild_id, command_name.lower(), role_id))
        elif user_id:
            await db.execute("""
                DELETE FROM command_permissions 
                WHERE guild_id = ? AND command_name = ? AND user_id = ?
            """, (guild_id, command_name.lower(), user_id))
        await db.commit()


async def has_permission(member, command_name: str):
    """Check if a member has permission to use a command"""
    # Owner always has permission
    if member.id == OWNER_ID:
        return True
    
    if not member.guild:
        return False
    
    guild_id = member.guild.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Check user-specific permission
        cursor = await db.execute("""
            SELECT 1 FROM command_permissions 
            WHERE guild_id = ? AND command_name = ? AND user_id = ?
        """, (guild_id, command_name.lower(), member.id))
        if await cursor.fetchone():
            return True
        
        # Check role permissions
        role_ids = [role.id for role in member.roles]
        if role_ids:
            placeholders = ','.join('?' * len(role_ids))
            cursor = await db.execute(f"""
                SELECT 1 FROM command_permissions 
                WHERE guild_id = ? AND command_name = ? AND role_id IN ({placeholders})
            """, (guild_id, command_name.lower(), *role_ids))
            if await cursor.fetchone():
                return True
    
    return False


async def get_command_permissions(guild_id: int, command_name: str):
    """Get all permissions for a command in a guild"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT role_id, user_id FROM command_permissions 
            WHERE guild_id = ? AND command_name = ?
        """, (guild_id, command_name.lower()))
        return await cursor.fetchall()


async def disable_command_in_channel(guild_id: int, channel_id: int, command_name: str):
    """Disable a command in a specific channel"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO disabled_channels (guild_id, channel_id, command_name)
            VALUES (?, ?, ?)
        """, (guild_id, channel_id, command_name.lower()))
        await db.commit()


async def enable_command_in_channel(guild_id: int, channel_id: int, command_name: str):
    """Re-enable a command in a specific channel"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            DELETE FROM disabled_channels 
            WHERE guild_id = ? AND channel_id = ? AND command_name = ?
        """, (guild_id, channel_id, command_name.lower()))
        await db.commit()


async def is_command_disabled(channel_id: int, guild_id: int, command_name: str):
    """Check if a command is disabled in a channel (or if channel is blacklisted)"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if channel is blacklisted (wildcard '*') or specific command is disabled
        cursor = await db.execute("""
            SELECT 1 FROM disabled_channels 
            WHERE guild_id = ? AND channel_id = ? AND (command_name = ? OR command_name = '*')
        """, (guild_id, channel_id, command_name.lower()))
        return await cursor.fetchone() is not None


async def get_disabled_commands_in_channel(guild_id: int, channel_id: int):
    """Get all disabled commands in a channel"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT command_name FROM disabled_channels 
            WHERE guild_id = ? AND channel_id = ?
        """, (guild_id, channel_id))
        return [row[0] for row in await cursor.fetchall()]
