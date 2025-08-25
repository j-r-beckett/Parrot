import aiosqlite
from aiosqlitepool import SQLiteConnectionPool
import os
from logging import Logger


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


async def create_db_pool(db_path: str, logger: Logger) -> SQLiteConnectionPool:
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    async def sqlite_connection() -> aiosqlite.Connection:
        return await aiosqlite.connect(db_path)

    db_pool = SQLiteConnectionPool(connection_factory=sqlite_connection)
    await init_database(db_pool)
    logger.info("Database initialized")
    return db_pool
