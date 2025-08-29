import aiosqlite
from aiosqlitepool import SQLiteConnectionPool
import os
import json
import uuid
from typing import List, Optional, Dict, Any, Tuple
from logging import Logger


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
        await db.commit()


async def load_last_conversation(db_pool: SQLiteConnectionPool, phone_number: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Load the last conversation for a phone number. Returns (messages, conversation_id) or ([], None)."""
    async with db_pool.connection() as db:
        # First, find the most recent conversation_id for this user
        cursor = await db.execute(
            "SELECT conversation_id FROM messages WHERE user_phone_number = ? ORDER BY id DESC LIMIT 1",
            (phone_number,),
        )
        row = await cursor.fetchone()
        if not row:
            return ([], None)
        
        conversation_id = row[0]
        
        # Then, get all messages in that conversation
        cursor = await db.execute(
            "SELECT message FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        messages = [json.loads(row[0]) for row in rows]
        
        return (messages, conversation_id)


async def save_conversation(db_pool: SQLiteConnectionPool, phone_number: str, messages: List[Dict[str, Any]], conversation_id: Optional[str] = None) -> None:
    """Save new messages to the conversation for a phone number."""
    if conversation_id is None:
        conversation_id = str(uuid.uuid4())
    
    async with db_pool.connection() as db:
        for msg in messages:
            await db.execute(
                "INSERT INTO messages (conversation_id, user_phone_number, message) VALUES (?, ?, ?)",
                (conversation_id, phone_number, json.dumps(msg)),
            )
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
