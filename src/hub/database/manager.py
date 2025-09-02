import aiosqlite
from aiosqlitepool import SQLiteConnectionPool
import os
import json
import uuid
from typing import Optional
from litestar.types.protocols import Logger
from config import settings


async def init_database(db_pool: SQLiteConnectionPool) -> None:
    """Initialize the interactions database table."""
    async with db_pool.connection() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id TEXT PRIMARY KEY,
                user_phone_number TEXT NOT NULL,
                user_prompt TEXT NOT NULL,
                llm_response TEXT NOT NULL,
                messages TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_phone_created 
            ON interactions(user_phone_number, created_at)
        """)
        await db.commit()  # type: ignore


async def load_recent_interactions(
    db_pool: SQLiteConnectionPool, phone_number: str, memory_depth: int
) -> str:
    """Load the last memory_depth interactions for a phone number as JSON string."""
    async with db_pool.connection() as db:
        cursor = await db.execute(
            """SELECT user_prompt, llm_response, created_at 
               FROM interactions 
               WHERE user_phone_number = ? 
               ORDER BY created_at DESC LIMIT ?""",
            (phone_number, memory_depth),
        )
        rows = await cursor.fetchall()
        
        # Build list of interaction dicts in chronological order
        interactions = []
        for row in reversed(rows):
            interactions.append({
                "user_prompt": row[0],
                "llm_response": row[1],
                "timestamp": row[2]
            })
        
        return json.dumps(interactions)


async def save_interaction(
    db_pool: SQLiteConnectionPool,
    phone_number: str,
    user_prompt: str,
    llm_response: str,
    messages_json: str,
) -> str:
    """Save a new interaction and return the interaction ID (UUID)."""
    interaction_id = str(uuid.uuid4())
    async with db_pool.connection() as db:
        await db.execute(
            """INSERT INTO interactions (id, user_phone_number, user_prompt, llm_response, messages) 
               VALUES (?, ?, ?, ?, ?)""",
            (interaction_id, phone_number, user_prompt, llm_response, messages_json),
        )
        await db.commit()  # type: ignore
        return interaction_id




async def create_db_pool(db_path: str, logger: Logger) -> SQLiteConnectionPool:
    # Clear database file when running locally
    if settings.ring == "local" and os.path.exists(db_path):
        logger.warning("Removing existing database file: %s", db_path)
        os.remove(db_path)
    
    def sqlite_connection() -> aiosqlite.Connection:
        logger.info("Creating connection to database at %s", db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return aiosqlite.connect(db_path)

    db_pool = SQLiteConnectionPool(connection_factory=sqlite_connection)  # type: ignore
    await init_database(db_pool)
    logger.info("Database initialized")
    return db_pool
