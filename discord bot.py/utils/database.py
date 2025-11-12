import datetime
import asyncio
import aiosqlite
from config import DB_PATH, RESET_TIME

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Users
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            mora INTEGER DEFAULT 0,
            dust INTEGER DEFAULT 0,
            fates INTEGER DEFAULT 0
        )""")
        # Pulls
        await db.execute("""
        CREATE TABLE IF NOT EXISTS pulls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            character_name TEXT,
            rarity TEXT,
            count INTEGER DEFAULT 1,
            relics INTEGER DEFAULT 0,
            element TEXT,
            hp INTEGER,
            atk INTEGER
        )""")
        # Persistent wish + pity
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_wishes (
            user_id INTEGER PRIMARY KEY,
            count INTEGER DEFAULT 0,
            reset TIMESTAMP,
            pity INTEGER DEFAULT 0
        )""")
        # Crates inventory
        await db.execute("""
        CREATE TABLE IF NOT EXISTS chests (
            user_id INTEGER PRIMARY KEY,
            count INTEGER DEFAULT 0
        )""")
        # Detailed chest inventory by rarity/type
        await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_inventory (
            user_id INTEGER PRIMARY KEY,
            common INTEGER DEFAULT 0,
            exquisite INTEGER DEFAULT 0,
            precious INTEGER DEFAULT 0,
            luxurious INTEGER DEFAULT 0
        )""")
        # Ensure the canonical 'luxurious' column exists in chest_inventory.
        # This keeps the schema stable for typed chest storage.
        try:
            async with db.execute("PRAGMA table_info('chest_inventory')") as cursor:
                cols = await cursor.fetchall()
                col_names = [c[1] for c in cols]
                if 'luxurious' not in col_names:
                    await db.execute("ALTER TABLE chest_inventory ADD COLUMN luxurious INTEGER DEFAULT 0")
                    await db.commit()
        except Exception:
            # Best-effort migration; on failure, continue without raising so bot can still start.
            pass
        # Exploration dispatches
        await db.execute("""
        CREATE TABLE IF NOT EXISTS dispatches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            character_name TEXT,
            region TEXT,
            rarity TEXT,
            start TIMESTAMP,
            end TIMESTAMP,
            mora_reward INTEGER DEFAULT 0,
            dust_reward INTEGER DEFAULT 0,
            fates_reward INTEGER DEFAULT 0,
            chest_award INTEGER DEFAULT 0,
            claimed INTEGER DEFAULT 0
        )""")
        # Shop purchases: track daily purchases per user
        await db.execute("""
        CREATE TABLE IF NOT EXISTS shop_purchases (
            user_id INTEGER,
            date TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )""")
        # Per-item shop purchases (track purchases per item per day)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS shop_item_purchases (
            user_id INTEGER,
            date TEXT,
            item_key TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date, item_key)
        )""")
        # Account progression: EXP and level
        await db.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            user_id INTEGER PRIMARY KEY,
            exp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0
        )""")
        # Track which level rewards a user has claimed (prevents double-granting)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS level_claims (
            user_id INTEGER,
            level INTEGER,
            claimed INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, level)
        )""")
        # Simple badges table for stage completion and other honors
        await db.execute("""
        CREATE TABLE IF NOT EXISTS badges (
            user_id INTEGER,
            badge_key TEXT,
            awarded_at TIMESTAMP,
            PRIMARY KEY (user_id, badge_key)
        )""")
        # Achievements table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            user_id INTEGER,
            ach_key TEXT,
            title TEXT,
            description TEXT,
            awarded_at TIMESTAMP,
            PRIMARY KEY (user_id, ach_key)
        )""")
        # Per-user consumable / misc item storage (e.g., exp bottles)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_items (
            user_id INTEGER,
            item_key TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, item_key)
        )""")
        # Fish caught tracking (for achievements and collections)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS fish_caught (
            user_id INTEGER,
            fish_name TEXT,
            count INTEGER DEFAULT 0,
            first_caught TIMESTAMP,
            PRIMARY KEY (user_id, fish_name)
        )""")
        # Fish pets system (each caught fish becomes a pet that can be leveled)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS fish_pets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            fish_name TEXT,
            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,
            caught_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.commit()

async def ensure_user_db(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            if not user:
                await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
                await db.commit()
        async with db.execute("SELECT * FROM user_wishes WHERE user_id=?", (user_id,)) as cursor:
            wish = await cursor.fetchone()
            if not wish:
                now = datetime.datetime.now()
                await db.execute("INSERT INTO user_wishes (user_id, count, reset, pity) VALUES (?, ?, ?, ?)",
                                 (user_id, 0, now + RESET_TIME, 0))
                await db.commit()
        async with db.execute("SELECT * FROM chests WHERE user_id=?", (user_id,)) as cursor:
            chest = await cursor.fetchone()
            if not chest:
                await db.execute("INSERT INTO chests (user_id, count) VALUES (?, ?)", (user_id, 0))
                await db.commit()
        async with db.execute("SELECT * FROM chest_inventory WHERE user_id=?", (user_id,)) as cursor:
            inv = await cursor.fetchone()
            if not inv:
                await db.execute("INSERT INTO chest_inventory (user_id, common, exquisite, precious, luxurious) VALUES (?, ?, ?, ?, ?)", (user_id, 0, 0, 0, 0))
                await db.commit()
        # ensure account row exists
        async with db.execute("SELECT * FROM accounts WHERE user_id=?", (user_id,)) as cursor:
            acc = await cursor.fetchone()
            if not acc:
                await db.execute("INSERT INTO accounts (user_id, exp, level) VALUES (?, ?, ?)", (user_id, 0, 0))
                await db.commit()

async def get_user_data(user_id):
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT mora, dust, fates FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return {"mora": row[0], "dust": row[1], "fates": row[2]}

async def update_user_data(user_id, mora=None, dust=None, fates=None):
    await ensure_user_db(user_id)
    # SQLite can raise 'database is locked' when concurrent writers contend.
    # Retry a few times with a small backoff to reduce transient lock failures.
    attempts = 5
    for attempt in range(attempts):
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                if mora is not None:
                    await db.execute("UPDATE users SET mora=? WHERE user_id=?", (mora, user_id))
                if dust is not None:
                    await db.execute("UPDATE users SET dust=? WHERE user_id=?", (dust, user_id))
                if fates is not None:
                    await db.execute("UPDATE users SET fates=? WHERE user_id=?", (fates, user_id))
                await db.commit()
            break
        except aiosqlite.OperationalError as e:
            if 'locked' in str(e).lower() and attempt < attempts - 1:
                await asyncio.sleep(0.05 * (attempt + 1))
                continue
            raise

async def save_pull(user_id: int, username: str, char: dict):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await init_db()
            # Normalize character name for comparisons
            char_name = (char.get("name") or "").strip()
            async with db.execute(
                "SELECT relics, count FROM pulls WHERE user_id=? AND LOWER(character_name)=LOWER(?)",
                (user_id, char_name)
            ) as cursor:
                existing = await cursor.fetchone()

            if existing:
                relics, count = existing
                new_relics = (relics or 0) + 1
                await db.execute(
                    "UPDATE pulls SET relics = ? WHERE user_id=? AND LOWER(character_name)=LOWER(?)",
                    (new_relics, user_id, char_name)
                )
                await db.commit()
                # Duplicate: convert to a relic (do not insert another card row)
                # Return a short message with the character name and rarity at the start per user request
                rarity = char.get('rarity') or ""
                name_with_rarity = f"{char_name} ({rarity})" if rarity else char_name
                return f"{name_with_rarity} - Obtained 1x {char_name.lower()} relic."
            else:
                # New card: insert into pulls with count=1 and relics=0
                await db.execute("""
                    INSERT INTO pulls (user_id, username, character_name, rarity, count, relics, element, hp, atk)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, username, char_name, char.get("rarity"), 1, 0,
                      char.get("element"), char.get("hp"), char.get("atk")))
                await db.commit()
                return f"{char_name} ({char.get('rarity')}) - Obtained new card."
    except Exception as e:
        print(f"Error in save_pull: {e}")
        return "An internal error occurred saving that pull."

async def get_user_pulls(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        async with db.execute(
            "SELECT character_name, rarity, count, relics, element, hp, atk FROM pulls WHERE user_id=?",
            (user_id,)
        ) as cursor:
            return await cursor.fetchall()

async def purge_inventory_db(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pulls WHERE user_id=?", (user_id,))
        await db.execute("UPDATE chests SET count=0 WHERE user_id=?", (user_id,))
        await db.execute("UPDATE chest_inventory SET common=0, exquisite=0, precious=0, luxurious=0 WHERE user_id=?", (user_id,))
        await db.commit()


async def get_shop_purchases_today(user_id: int):
    """Return how many shop purchases the user has made today."""
    await ensure_user_db(user_id)
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT count FROM shop_purchases WHERE user_id=? AND date=?", (user_id, today)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def increment_shop_purchases(user_id: int, delta: int = 1):
    """Increment the shop purchase counter for today by delta."""
    await ensure_user_db(user_id)
    today = datetime.date.today().isoformat()
    attempts = 5
    for attempt in range(attempts):
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Use INSERT ... ON CONFLICT to upsert the daily count
                await db.execute(
                    "INSERT INTO shop_purchases (user_id, date, count) VALUES (?, ?, ?) ON CONFLICT(user_id, date) DO UPDATE SET count = shop_purchases.count + ?",
                    (user_id, today, delta, delta)
                )
                await db.commit()
            break
        except aiosqlite.OperationalError as e:
            if 'locked' in str(e).lower() and attempt < attempts - 1:
                await asyncio.sleep(0.05 * (attempt + 1))
                continue
            raise


async def get_shop_item_purchases_today(user_id: int, item_key: str):
    """Return how many of `item_key` the user has purchased today."""
    await ensure_user_db(user_id)
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT count FROM shop_item_purchases WHERE user_id=? AND date=? AND item_key=?", (user_id, today, item_key)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def increment_shop_item_purchases(user_id: int, item_key: str, delta: int = 1):
    """Increment the per-item shop purchase counter for today by delta."""
    await ensure_user_db(user_id)
    today = datetime.date.today().isoformat()
    attempts = 5
    for attempt in range(attempts):
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT INTO shop_item_purchases (user_id, date, item_key, count) VALUES (?, ?, ?, ?) ON CONFLICT(user_id, date, item_key) DO UPDATE SET count = shop_item_purchases.count + ?",
                    (user_id, today, item_key, delta, delta)
                )
                await db.commit()
            break
        except aiosqlite.OperationalError as e:
            if 'locked' in str(e).lower() and attempt < attempts - 1:
                await asyncio.sleep(0.05 * (attempt + 1))
                continue
            raise

async def add_chest(user_id, amount=1):
    # Backwards-compatible wrapper: increments generic chest count only
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE chests SET count=count+? WHERE user_id=?", (amount, user_id))
        await db.commit()


async def add_chest_with_type(user_id, chest_type: str = 'common', amount: int = 1):
    """Add chest(s) of a specific type to a user's inventory.

    chest_type should be one of: 'common', 'exquisite', 'precious', 'luxurious'.
    This function also updates the legacy `chests.count` for compatibility.
    """
    await ensure_user_db(user_id)
    col = None
    chest_type = (chest_type or 'common').strip().lower()
    # accept public name 'luxurious' and map to DB column 'luxurious'
    if chest_type == 'common':
        col = 'common'
    elif chest_type == 'exquisite':
        col = 'exquisite'
    elif chest_type == 'precious':
        col = 'precious'
    elif chest_type == 'luxurious':
        col = 'luxurious'
    else:
        col = 'common'

    async with aiosqlite.connect(DB_PATH) as db:
        # ensure a row exists (race-safe)
        await db.execute("INSERT OR IGNORE INTO chest_inventory (user_id, common, exquisite, precious, luxurious) VALUES (?, ?, ?, ?, ?)", (user_id, 0, 0, 0, 0))
        # update detailed inventory
        await db.execute(f"UPDATE chest_inventory SET {col}={col}+? WHERE user_id= ?", (amount, user_id))
        # update legacy counter too
        await db.execute("INSERT OR IGNORE INTO chests (user_id, count) VALUES (?, 0)", (user_id,))
        await db.execute("UPDATE chests SET count=count+? WHERE user_id=?", (amount, user_id))
        await db.commit()

async def get_chest_count(user_id):
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT count FROM chests WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_chest_inventory(user_id):
    """Return a dict with counts for each chest type for the user."""
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT common, exquisite, precious, luxurious FROM chest_inventory WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                # return public-facing keys
                return {"common": 0, "exquisite": 0, "precious": 0, "luxurious": 0}
            return {"common": row[0] or 0, "exquisite": row[1] or 0, "precious": row[2] or 0, "luxurious": row[3] or 0}


async def get_user_item_count(user_id: int, item_key: str):
    """Return how many of `item_key` the user currently has."""
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT count FROM user_items WHERE user_id=? AND item_key=?", (user_id, item_key)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def add_user_item(user_id: int, item_key: str, amount: int = 1):
    """Add (or subtract if amount negative) `amount` of item_key for user. Does not allow negative results.

    Returns the new count.
    """
    await ensure_user_db(user_id)
    item = (item_key or '').strip().lower()
    if amount == 0:
        return await get_user_item_count(user_id, item)
    attempts = 5
    for attempt in range(attempts):
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Ensure row exists
                await db.execute("INSERT OR IGNORE INTO user_items (user_id, item_key, count) VALUES (?, ?, ?)", (user_id, item, 0))
                # Attempt conditional update so count never goes negative
                cur = await db.execute("UPDATE user_items SET count = count + ? WHERE user_id=? AND item_key=? AND (count + ?) >= 0", (amount, user_id, item, amount))
                await db.commit()
                if cur.rowcount == 0:
                    # fetch current for better error
                    async with db.execute("SELECT count FROM user_items WHERE user_id=? AND item_key=?", (user_id, item)) as cur2:
                        r = await cur2.fetchone()
                    current = r[0] if r and r[0] is not None else 0
                    raise ValueError(f"Not enough {item} (have={current}, want_delta={amount})")
                async with db.execute("SELECT count FROM user_items WHERE user_id=? AND item_key=?", (user_id, item)) as cur3:
                    newr = await cur3.fetchone()
                return newr[0] if newr and newr[0] is not None else 0
        except aiosqlite.OperationalError as e:
            if 'locked' in str(e).lower() and attempt < attempts - 1:
                await asyncio.sleep(0.05 * (attempt + 1))
                continue
            raise


async def change_chest_type_count(user_id, chest_type: str, delta: int):
    """Atomically add (or subtract if delta negative) chest_type count and update legacy total count.

    Returns the new count for the chest_type. Raises ValueError if the operation would result
    in a negative count.
    """
    await ensure_user_db(user_id)
    col = (chest_type or '').strip().lower()
    # accept variants and map to DB column 'luxurious'
    if col == 'luxurious':
        db_col = 'luxurious'
    else:
        db_col = col if col in ("common", "exquisite", "precious") else 'common'

    async with aiosqlite.connect(DB_PATH) as db:
        # ensure row exists
        await db.execute("INSERT OR IGNORE INTO chest_inventory (user_id, common, exquisite, precious, luxurious) VALUES (?, ?, ?, ?, ?)", (user_id, 0, 0, 0, 0))
        # Try to atomically update the typed chest column only if it won't go negative.
        # Use a conditional UPDATE: only apply when current + delta >= 0.
        cur = await db.execute(
            f"UPDATE chest_inventory SET {db_col} = {db_col} + ? WHERE user_id=? AND ({db_col} + ?) >= 0",
            (delta, user_id, delta)
        )
        await db.commit()
        # If no rows were affected, the decrement would have gone negative
        if cur.rowcount == 0:
            # read current to provide a helpful error
            async with db.execute(f"SELECT {db_col} FROM chest_inventory WHERE user_id=?", (user_id,)) as cur2:
                row = await cur2.fetchone()
            current = row[0] if row and row[0] is not None else 0
            raise ValueError(f"Not enough {db_col} chests (have={current}, want_delta={delta})")

        # fetch the new value
        async with db.execute(f"SELECT {db_col} FROM chest_inventory WHERE user_id=?", (user_id,)) as cur3:
            new_row = await cur3.fetchone()
        new = new_row[0] if new_row and new_row[0] is not None else 0

        # also update legacy total (keep it >= 0)
        await db.execute("INSERT OR IGNORE INTO chests (user_id, count) VALUES (?, 0)", (user_id,))
        async with db.execute("SELECT count FROM chests WHERE user_id=?", (user_id,)) as cur4:
            crow = await cur4.fetchone()
        legacy = crow[0] if crow and crow[0] is not None else 0
        legacy_new = legacy + int(delta)
        if legacy_new < 0:
            legacy_new = 0
        await db.execute("UPDATE chests SET count = ? WHERE user_id=?", (legacy_new, user_id))
        await db.commit()
        return new


async def insert_dispatch(user_id: int, character_name: str, region: str, rarity: str,
                          start_iso: str, end_iso: str, mora: int, dust: int, fates: int, chest: int):
    """Insert a new dispatch record and return its id."""
    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        # Try a few times to compute and insert a compact id. If a race causes a
        # PRIMARY KEY conflict, retry. If retries fail, fall back to letting SQLite
        # assign the id automatically.
        for attempt in range(3):
            async with db.execute("SELECT id FROM dispatches ORDER BY id ASC") as cursor:
                rows = await cursor.fetchall()
                used_ids = [r[0] for r in rows]

            next_id = 1
            for uid in used_ids:
                if uid == next_id:
                    next_id += 1
                elif uid > next_id:
                    break

            try:
                cur = await db.execute(
                    """INSERT INTO dispatches (id, user_id, character_name, region, rarity, start, end, mora_reward, dust_reward, fates_reward, chest_award, claimed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (next_id, user_id, character_name, region, rarity, start_iso, end_iso, mora, dust, fates, chest)
                )
                await db.commit()
                return next_id
            except aiosqlite.IntegrityError:
                # Likely a PRIMARY KEY conflict due to a concurrent insert; retry
                await asyncio.sleep(0.05)
                continue

        # Fallback: insert without specifying id and return the autoincremented id
        cur = await db.execute(
            """INSERT INTO dispatches (user_id, character_name, region, rarity, start, end, mora_reward, dust_reward, fates_reward, chest_award, claimed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (user_id, character_name, region, rarity, start_iso, end_iso, mora, dust, fates, chest)
        )
        await db.commit()
        return cur.lastrowid


async def get_user_active_dispatches(user_id: int):
    """Return active (not yet ended) dispatches for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        now = datetime.datetime.now().isoformat()
        async with db.execute(
            "SELECT id, character_name, region, rarity, start, end, mora_reward, dust_reward, fates_reward, chest_award FROM dispatches WHERE user_id=? AND claimed=0 AND end> ?",
            (user_id, now)
        ) as cursor:
            return await cursor.fetchall()


async def get_user_ready_dispatches(user_id: int):
    """Return finished-but-unclaimed dispatches for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        now = datetime.datetime.now().isoformat()
        async with db.execute(
            "SELECT id, character_name, region, rarity, start, end, mora_reward, dust_reward, fates_reward, chest_award FROM dispatches WHERE user_id=? AND claimed=0 AND end<= ?",
            (user_id, now)
        ) as cursor:
            return await cursor.fetchall()


async def get_dispatch_by_id(dispatch_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        async with db.execute("SELECT id, user_id, character_name, region, rarity, start, end, mora_reward, dust_reward, fates_reward, chest_award, claimed FROM dispatches WHERE id=?", (dispatch_id,)) as cursor:
            return await cursor.fetchone()


async def mark_dispatch_claimed(dispatch_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        await db.execute("UPDATE dispatches SET claimed=1 WHERE id=?", (dispatch_id,))
        await db.commit()

async def load_user_wish(user_id):
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT count, reset, pity FROM user_wishes WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return {"count": row[0], "reset": datetime.datetime.fromisoformat(row[1]), "pity": row[2]}

async def save_user_wish(user_id, count, reset, pity):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_wishes (user_id, count, reset, pity) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET count=excluded.count, reset=excluded.reset, pity=excluded.pity",
            (user_id, count, reset.isoformat(), pity)
        )
        await db.commit()

async def reset_wishes(user_id):
    now = datetime.datetime.now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE user_wishes SET count=0, reset=? WHERE user_id=?",
                         (now + RESET_TIME, user_id))
        await db.commit()

async def update_chest_count(user_id, count):
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE chests SET count=? WHERE user_id=?", (count, user_id))
        await db.commit()


async def _exp_required_for_level(level: int) -> int:
    """Return EXP required to reach the next level from `level`.

    Formula: base 1000 EXP + linear scaling (200 * level). Keep baseline 1000 as requested.
    """
    base = 1000
    step = 200
    return int(base + step * max(0, int(level)))


async def get_account_level(user_id: int):
    """Return a tuple (level, exp) for the user's account."""
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT level, exp FROM accounts WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return 0, 0, await _exp_required_for_level(0)
            level = int(row[0] or 0)
            exp = int(row[1] or 0)
            needed = await _exp_required_for_level(level)
            return level, exp, needed


async def grant_level_rewards(user_id: int, level: int):
    """Idempotently grant level-up rewards for the given level.

    This function will check `level_claims` to avoid double-granting. Rewards are intentionally
    conservative: 1 common chest per level, and on every 10th level give 5,000 Mora and 1 exquisite chest.
    Achievements are awarded at levels 20, 50, and 100. Badges are awarded based on ranks (1-6).
    """
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if already claimed
        async with db.execute("SELECT claimed FROM level_claims WHERE user_id=? AND level=?", (user_id, level)) as cur:
            row = await cur.fetchone()
            if row and row[0]:
                return False

        # Mark as claimed (insert or update)
        await db.execute("INSERT OR REPLACE INTO level_claims (user_id, level, claimed) VALUES (?, ?, 1)", (user_id, level))


        # Basic reward: 1 common chest
        try:
            await add_chest_with_type(user_id, 'common', 1)
        except Exception:
            pass

        # Per-level Mora scaled by stage: stage = (level//20) + 1
        try:
            stage = (int(level) // 20) + 1
            per_level_mora = 1000 * stage
            async with db.execute("SELECT mora FROM users WHERE user_id=?", (user_id,)) as cur2:
                r = await cur2.fetchone()
                current = int(r[0] or 0) if r else 0
            await db.execute("UPDATE users SET mora=? WHERE user_id=?", (current + per_level_mora, user_id))
        except Exception:
            pass

        # Every 10 levels: extra Mora and exquisite chest (scaled by stage)
        if level % 10 == 0:
            try:
                extra_mora = 5000 * stage
                async with db.execute("SELECT mora FROM users WHERE user_id=?", (user_id,)) as cur3:
                    r2 = await cur3.fetchone()
                    cur_now = int(r2[0] or 0) if r2 else 0
                await db.execute("UPDATE users SET mora=? WHERE user_id=?", (cur_now + extra_mora, user_id))
            except Exception:
                pass
            try:
                await add_chest_with_type(user_id, 'exquisite', 1)
            except Exception:
                pass
        
        # Sync tier badges based on current rank (3 tiers: Bronze 1-2, Silver 3-4, Gold 5-6)
        rank = max(0, stage - 1)
        
        # Define all possible tier badges
        all_tier_badges = {
            "<a:Medal3:1438198826799468604> Bronze Adventurer": (rank >= 1),
            "<a:Medal2:1438198813851652117> Silver Traveler": (rank >= 3),
            "<a:Medal:1438198856910241842> Golden Legend": (rank >= 5)
        }
        
        try:
            # Remove badges user no longer qualifies for
            for badge_key, qualifies in all_tier_badges.items():
                if not qualifies:
                    await db.execute("DELETE FROM badges WHERE user_id=? AND badge_key=?", (user_id, badge_key))
            
            # Add badges user now qualifies for
            for badge_key, qualifies in all_tier_badges.items():
                if qualifies:
                    async with db.execute("SELECT 1 FROM badges WHERE user_id=? AND badge_key=?", (user_id, badge_key)) as cur:
                        has_badge = await cur.fetchone()
                    if not has_badge:
                        await db.execute("INSERT OR IGNORE INTO badges (user_id, badge_key, awarded_at) VALUES (?, ?, ?)",
                            (user_id, badge_key, datetime.datetime.now().isoformat()))
        except Exception:
            pass

        await db.commit()
        return True


async def add_account_exp(user_id: int, amount: int, source: str = 'unknown'):
    """Add EXP to a user's account and handle level ups.

    Returns: dict with keys: 'old_level','new_level','old_exp','new_exp','levels_gained'
    """
    if amount is None or amount <= 0:
        return {"old_level": None, "new_level": None, "old_exp": None, "new_exp": None, "levels_gained": 0}

    await ensure_user_db(user_id)
    levels_gained = 0
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT level, exp FROM accounts WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                level = 0
                exp = 0
            else:
                level = int(row[0] or 0)
                exp = int(row[1] or 0)

        old_level = level
        old_exp = exp
        exp += int(amount)

        # level up loop
        while True:
            req = await _exp_required_for_level(level)
            if exp >= req:
                exp -= req
                level += 1
                levels_gained += 1
                # grant level rewards (idempotent)
                try:
                    await grant_level_rewards(user_id, level)
                except Exception:
                    pass
                # continue to see if next level also reached
                continue
            break

        # persist new values
        await db.execute("UPDATE accounts SET level=?, exp=? WHERE user_id=?", (level, exp, user_id))
        await db.commit()

    return {"old_level": old_level, "new_level": level, "old_exp": old_exp, "new_exp": exp, "levels_gained": levels_gained}


async def award_achievement(user_id: int, ach_key: str, title: str, description: str = None):
    """Idempotently award an achievement to a user."""
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT OR IGNORE INTO achievements (user_id, ach_key, title, description, awarded_at) VALUES (?, ?, ?, ?, ?)",
                             (user_id, ach_key, title, description or '', datetime.datetime.now().isoformat()))
            await db.commit()
            return True
        except Exception:
            return False


async def get_user_achievements(user_id: int):
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT ach_key, title, description, awarded_at FROM achievements WHERE user_id=?", (user_id,)) as cur:
            rows = await cur.fetchall()
            return [dict(key=r[0], title=r[1], description=r[2], awarded_at=r[3]) for r in rows]


async def check_and_award_level_achievements(user_id: int):
    """Check user's current level and award any missing level achievements. Also checks and awards rank badges."""
    level, _, _ = await get_account_level(user_id)
    stage = (level // 20) + 1
    rank = max(0, stage - 1)
    
    # Level achievement milestones (no badges, just achievements)
    level_milestones = [
        (20, 'level_20', 'Bronze Adventurer', 'Reached level 20!'),
        (50, 'level_50', 'Silver Traveler', 'Reached level 50!'),
        (100, 'level_100', 'Golden Legend', 'Reached level 100!')
    ]
    
    # Define all possible tier badges with qualification requirements
    all_tier_badges = {
        "<a:Medal3:1438198826799468604> Bronze Adventurer": (rank >= 1),
        "<a:Medal2:1438198813851652117> Silver Traveler": (rank >= 3),
        "<a:Medal:1438198856910241842> Golden Legend": (rank >= 5)
    }
    
    awarded_count = 0
    async with aiosqlite.connect(DB_PATH) as db:
        # Check level achievements
        for level_req, ach_key, title, desc in level_milestones:
            if level >= level_req:
                async with db.execute("SELECT 1 FROM achievements WHERE user_id=? AND ach_key=?", (user_id, ach_key)) as cur:
                    has_ach = await cur.fetchone()
                
                if not has_ach:
                    await db.execute("INSERT OR IGNORE INTO achievements (user_id, ach_key, title, description, awarded_at) VALUES (?, ?, ?, ?, ?)",
                        (user_id, ach_key, title, desc, datetime.datetime.now().isoformat()))
                    awarded_count += 1
        
        # Sync tier badges based on current qualifications
        for badge_key, qualifies in all_tier_badges.items():
            if qualifies:
                # User qualifies - ensure they have the badge
                async with db.execute("SELECT 1 FROM badges WHERE user_id=? AND badge_key=?", (user_id, badge_key)) as cur:
                    has_badge = await cur.fetchone()
                
                if not has_badge:
                    await db.execute("INSERT OR IGNORE INTO badges (user_id, badge_key, awarded_at) VALUES (?, ?, ?)",
                        (user_id, badge_key, datetime.datetime.now().isoformat()))
                    awarded_count += 1
            else:
                # User doesn't qualify - remove the badge if they have it
                result = await db.execute("DELETE FROM badges WHERE user_id=? AND badge_key=?", (user_id, badge_key))
                if result.rowcount > 0:
                    awarded_count += 1  # Count removals too
        
        await db.commit()
    
    return awarded_count


async def add_fish_caught(user_id: int, fish_name: str, count: int = 1):
    """Track a fish caught by a user. Increments count and sets first_caught timestamp if new."""
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT count FROM fish_caught WHERE user_id=? AND fish_name=?", (user_id, fish_name)) as cur:
            row = await cur.fetchone()
        if row:
            # already caught, increment count
            new_count = row[0] + count
            await db.execute("UPDATE fish_caught SET count=? WHERE user_id=? AND fish_name=?", (new_count, user_id, fish_name))
        else:
            # first time catching this fish
            await db.execute("INSERT INTO fish_caught (user_id, fish_name, count, first_caught) VALUES (?, ?, ?, ?)",
                           (user_id, fish_name, count, datetime.datetime.now().isoformat()))
        await db.commit()


async def get_user_fish_caught(user_id: int):
    """Return list of all fish caught by user with counts."""
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT fish_name, count, first_caught FROM fish_caught WHERE user_id=?", (user_id,)) as cur:
            rows = await cur.fetchall()
            return [dict(fish_name=r[0], count=r[1], first_caught=r[2]) for r in rows]


async def get_fish_count_by_rarity(user_id: int, rarity: str):
    """Count how many unique fish of a given rarity the user has caught."""
    from utils.constants import fish_pool
    caught = await get_user_fish_caught(user_id)
    caught_names = {f['fish_name'] for f in caught}
    matching = [f for f in fish_pool if f['rarity'] == rarity and f['name'] in caught_names]
    return len(matching)


async def get_total_fish_caught(user_id: int):
    """Return total number of fish caught (sum of all counts)."""
    caught = await get_user_fish_caught(user_id)
    return sum(f['count'] for f in caught)


# ===== Fish Pet System =====

async def add_fish_pet(user_id: int, fish_name: str):
    """Add a new fish pet when caught."""
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO fish_pets (user_id, fish_name, level, exp) VALUES (?, ?, ?, ?)",
                        (user_id, fish_name, 1, 0))
        await db.commit()


async def get_user_fish_pets(user_id: int):
    """Return all fish pets owned by a user."""
    await ensure_user_db(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, fish_name, level, exp, caught_at FROM fish_pets WHERE user_id=? ORDER BY caught_at DESC", (user_id,)) as cur:
            rows = await cur.fetchall()
            return [dict(id=r[0], fish_name=r[1], level=r[2], exp=r[3], caught_at=r[4]) for r in rows]


async def level_up_fish_pet(user_id: int, pet_id: int, crystals_needed: int):
    """Level up a fish pet by consuming hydro crystals. Returns True if successful."""
    await ensure_user_db(user_id)
    # Check if user has enough crystals
    crystal_count = await get_user_item_count(user_id, 'hydro_crystal')
    if crystal_count < crystals_needed:
        return False
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Verify pet belongs to user
        async with db.execute("SELECT level FROM fish_pets WHERE id=? AND user_id=?", (pet_id, user_id)) as cur:
            row = await cur.fetchone()
            if not row:
                return False
        
        # Consume crystals
        await add_user_item(user_id, 'hydro_crystal', -crystals_needed)
        
        # Level up pet
        await db.execute("UPDATE fish_pets SET level = level + 1 WHERE id=?", (pet_id,))
        await db.commit()
        return True
