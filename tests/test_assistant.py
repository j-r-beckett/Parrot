import pytest
from dynaconf.utils.boxing import DynaBox

from assistant import Assistant


@pytest.mark.asyncio
async def test_haiku_says_hello():
    """Test that Haiku 3.5 responds with 'hello' when prompted."""
    # This will use the real API key from environment
    from config import settings

    llm_config = DynaBox(
        {
            "model": "claude-3-5-haiku",
            "max_tokens": 100,
            "api_key": settings.llm.api_key,
        }
    )

    assistant = Assistant(llm_config)

    messages = []
    tools = []

    response_text, updated_messages = await assistant.step(
        messages=messages, tools=tools, query='Say "hello"'
    )

    assert "hello" in response_text.lower()

    assert len(updated_messages) == 2  # User message + Assistant response
    assert all(isinstance(m, str) and m for m in updated_messages)


@pytest.mark.asyncio
async def test_haiku_tool_call():
    """Test that Haiku 3.5 can call tools and get the magic number."""
    from config import settings

    llm_config = DynaBox(
        {
            "model": "claude-3-5-haiku",
            "max_tokens": 200,
            "api_key": settings.llm.api_key,
        }
    )

    assistant = Assistant(llm_config)

    # Define the magic_number tool
    async def magic_number() -> int:
        """Get the magic number."""
        return 58

    messages = []
    tools = [magic_number]

    response_text, updated_messages = await assistant.step(
        messages=messages,
        tools=tools,
        query="What is the magic number?"
    )

    # Verify the response contains 58
    assert "58" in response_text

    # Verify there are 4 messages:
    # 1. User query
    # 2. Assistant with tool call
    # 3. Tool result
    # 4. Assistant final response
    assert len(updated_messages) == 4
    assert all(isinstance(m, str) and m for m in updated_messages)
