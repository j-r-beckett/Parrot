import pytest
from dynaconf.utils.boxing import DynaBox

from assistant import create_llm_call, step


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

    llm_call = create_llm_call(llm_config)

    messages = []
    tools = []

    response_text, updated_messages = await step(
        llm_call=llm_call, messages=messages, tools=tools, query='Say "hello"'
    )

    assert "hello" in response_text.lower()

    assert len(updated_messages) == 2  # User message + Assistant response
    assert all(isinstance(m, str) and m for m in updated_messages)
