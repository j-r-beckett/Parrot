import aiosqlite
from aiosqlitepool import SQLiteConnectionPool


async def init_database(db_pool: SQLiteConnectionPool) -> None:
    async with db_pool.connection() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_id 
            ON messages(conversation_id)
        """)
        await db.commit()


async def create_db_pool() -> SQLiteConnectionPool:
    async def sqlite_connection() -> aiosqlite.Connection:
        return await aiosqlite.connect("conversations.db")
    
    db_pool = SQLiteConnectionPool(connection_factory=sqlite_connection)
    await init_database(db_pool)
    return db_pool