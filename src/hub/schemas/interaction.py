from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Interaction:
    """Represents a user-LLM interaction for context management."""

    id: str  # UUID
    user_phone_number: str
    user_prompt: str
    llm_response: str
    messages: str  # Full new_messages_json() for debugging
    created_at: Optional[datetime] = None
