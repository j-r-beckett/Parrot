import pytest
import tempfile
import os
import uuid
from unittest.mock import AsyncMock, Mock
from litestar.datastructures import State

import routes.webhook
from routes.webhook import handle_sms_proxy_received
from schemas.sms import SmsReceived, SmsReceivedPayload
from database.manager import create_db_pool, save_conversation, load_recent_messages
from pydantic_ai.messages import (
    UserPromptPart,
    ModelRequest,
    ModelResponse,
    TextPart,
    SystemPromptPart,
    ModelMessagesTypeAdapter,
)
from typing import List, Union


class MockRequest:
    def __init__(self):
        self.logger = Mock()
        self.logger.info = Mock()


async def _setup_test_db_and_mocks():
    """Helper to set up common test infrastructure."""
    # Create temporary database
    with tempfile.NamedTemporaryFile(delete=False) as tmp_db:
        db_path = tmp_db.name

    # Create database pool
    logger = Mock()
    db_pool = await create_db_pool(db_path, logger)

    # Store original functions for restoration
    original_create_assistant = routes.webhook.create_assistant
    original_create_dependencies = routes.webhook.create_assistant_dependencies

    # Create mock assistant
    mock_assistant = Mock()
    routes.webhook.create_assistant = Mock(return_value=mock_assistant)
    routes.webhook.create_assistant_dependencies = Mock(return_value=Mock())

    return (
        db_path,
        db_pool,
        mock_assistant,
        (original_create_assistant, original_create_dependencies),
    )


async def _cleanup_test_db_and_mocks(db_path, db_pool, originals):
    """Helper to clean up test infrastructure."""
    original_create_assistant, original_create_dependencies = originals

    # Restore original functions
    routes.webhook.create_assistant = original_create_assistant
    routes.webhook.create_assistant_dependencies = original_create_dependencies

    # Clean up database
    if db_pool:
        await db_pool.close()
    os.unlink(db_path)


@pytest.mark.asyncio
async def test_memory_depth_limit():
    """Test that memory_depth=2 only remembers the most recent 2 interactions."""
    db_path, db_pool, mock_assistant, originals = await _setup_test_db_and_mocks()

    try:
        # Mock settings.memory_depth for this test
        import routes.webhook
        original_settings = routes.webhook.settings
        mock_settings = Mock()
        mock_settings.memory_depth = 2
        mock_settings.ring = "local"
        routes.webhook.settings = mock_settings

        state = Mock(spec=State)
        state.db_pool = db_pool

        # First interaction
        mock_result1 = Mock()
        mock_result1.output = "Response A"
        mock_result1.new_messages_json.return_value = ModelMessagesTypeAdapter.dump_json([
            ModelRequest(parts=[UserPromptPart(content="Message A")]),
            ModelResponse(parts=[TextPart(content="Response A")]),
        ])
        mock_result1.all_messages_json.return_value = ModelMessagesTypeAdapter.dump_json([
            ModelRequest(parts=[UserPromptPart(content="Message A")]),
            ModelResponse(parts=[TextPart(content="Response A")]),
        ])
        mock_assistant.run = AsyncMock(return_value=mock_result1)

        sms_data1 = SmsReceived(
            device_id="test-device",
            id="test-1", 
            payload=SmsReceivedPayload(
                phone_number="+15551234567",
                message="Message A",
                received_at="2025-08-29T06:20:00Z",
                message_id="msg-1",
            ),
        )

        await handle_sms_proxy_received.fn(request=MockRequest(), state=state, data=sms_data1)

        # Verify first interaction is in database
        messages = await load_recent_messages(db_pool, "+15551234567", 2)
        assert len(messages) == 2
        assert messages[0].parts[0].content == "Message A"  # type: ignore
        assert messages[1].parts[0].content == "Response A"  # type: ignore

        # Second interaction
        mock_result2 = Mock()
        mock_result2.output = "Response B"
        mock_result2.new_messages_json.return_value = ModelMessagesTypeAdapter.dump_json([
            ModelRequest(parts=[UserPromptPart(content="Message B")]),
            ModelResponse(parts=[TextPart(content="Response B")]),
        ])
        mock_result2.all_messages_json.return_value = ModelMessagesTypeAdapter.dump_json([
            ModelRequest(parts=[UserPromptPart(content="Message B")]),
            ModelResponse(parts=[TextPart(content="Response B")]),
        ])
        mock_assistant.run = AsyncMock(return_value=mock_result2)

        sms_data2 = SmsReceived(
            device_id="test-device",
            id="test-2",
            payload=SmsReceivedPayload(
                phone_number="+15551234567", 
                message="Message B",
                received_at="2025-08-29T06:21:00Z",
                message_id="msg-2",
            ),
        )

        await handle_sms_proxy_received.fn(request=MockRequest(), state=state, data=sms_data2)
        
        # Verify both interactions are returned (memory_depth=2)
        messages = await load_recent_messages(db_pool, "+15551234567", 2)
        assert len(messages) == 4  # 2 interactions * 2 messages each
        assert messages[0].parts[0].content == "Message A"  # type: ignore
        assert messages[1].parts[0].content == "Response A"  # type: ignore
        assert messages[2].parts[0].content == "Message B"  # type: ignore
        assert messages[3].parts[0].content == "Response B"  # type: ignore

        # Third interaction
        mock_result3 = Mock()
        mock_result3.output = "Response C"
        mock_result3.new_messages_json.return_value = ModelMessagesTypeAdapter.dump_json([
            ModelRequest(parts=[UserPromptPart(content="Message C")]),
            ModelResponse(parts=[TextPart(content="Response C")]),
        ])
        mock_result3.all_messages_json.return_value = ModelMessagesTypeAdapter.dump_json([
            ModelRequest(parts=[UserPromptPart(content="Message C")]),
            ModelResponse(parts=[TextPart(content="Response C")]),
        ])
        mock_assistant.run = AsyncMock(return_value=mock_result3)

        sms_data3 = SmsReceived(
            device_id="test-device",
            id="test-3",
            payload=SmsReceivedPayload(
                phone_number="+15551234567", 
                message="Message C",
                received_at="2025-08-29T06:22:00Z",
                message_id="msg-3",
            ),
        )

        await handle_sms_proxy_received.fn(request=MockRequest(), state=state, data=sms_data3)
        
        # Verify only last 2 interactions are returned (memory_depth=2)
        messages = await load_recent_messages(db_pool, "+15551234567", 2)
        assert len(messages) == 4  # 2 interactions * 2 messages each
        assert messages[0].parts[0].content == "Message B"  # type: ignore
        assert messages[1].parts[0].content == "Response B"  # type: ignore
        assert messages[2].parts[0].content == "Message C"  # type: ignore
        assert messages[3].parts[0].content == "Response C"  # type: ignore
        # First interaction should not be returned
        assert not any("Message A" in str(msg) for msg in messages)
        assert not any("Response A" in str(msg) for msg in messages)

    finally:
        # Restore original settings
        routes.webhook.settings = original_settings
        await _cleanup_test_db_and_mocks(db_path, db_pool, originals)