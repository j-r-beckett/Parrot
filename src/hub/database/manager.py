import aiosqlite
from aiosqlitepool import SQLiteConnectionPool
import os
import json
import uuid
from typing import List, Optional, Tuple, cast
from litestar.types.protocols import Logger
from aiosqlitepool.protocols import Connection as PoolConnection
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from config import settings


async def init_database(db_pool: SQLiteConnectionPool) -> None:
    async with db_pool.connection() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                user_phone_number TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_id 
            ON messages(conversation_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_phone_number 
            ON messages(user_phone_number)
        """)
        await db.commit()  # type: ignore


async def load_recent_messages(
    db_pool: SQLiteConnectionPool, phone_number: str, memory_depth: int
) -> List[ModelMessage]:
    """Load the last memory_depth interactions for a phone number. Returns messages list."""
    async with db_pool.connection() as db:
        # Get the last memory_depth interactions for this user
        cursor = await db.execute(
            "SELECT message FROM messages WHERE user_phone_number = ? ORDER BY id DESC LIMIT ?",
            (phone_number, memory_depth),
        )
        rows = await cursor.fetchall()
        
        # Reverse the order to get chronological order and collect messages
        messages = []
        for row in reversed(rows):
            parsed = json.loads(row[0])
            messages.extend(ModelMessagesTypeAdapter.validate_python(parsed))

        return messages


async def save_conversation(
    db_pool: SQLiteConnectionPool,
    phone_number: str,
    messages_json: str,
    conversation_id: Optional[str] = None,
) -> None:
    """Save new messages to the conversation for a phone number."""
    if conversation_id is None:
        conversation_id = str(uuid.uuid4())

    async with db_pool.connection() as db:
        await db.execute(
            "INSERT INTO messages (conversation_id, user_phone_number, message) VALUES (?, ?, ?)",
            (conversation_id, phone_number, messages_json),
        )

        await db.commit()  # type: ignore


async def create_db_pool(db_path: str, logger: Logger) -> SQLiteConnectionPool:
    def sqlite_connection() -> aiosqlite.Connection:
        if settings.ring == "local":
            logger.info("Creating in-memory database connection")
            return aiosqlite.connect("file::memory:?cache=shared", uri=True)

        logger.info("Creating connection to database at %s", db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return aiosqlite.connect(db_path)

    db_pool = SQLiteConnectionPool(connection_factory=sqlite_connection)  # type: ignore
    await init_database(db_pool)
    logger.info("Database initialized")
    return db_pool
