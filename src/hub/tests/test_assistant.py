import pytest
import tempfile
import os
import json
from unittest.mock import AsyncMock, Mock
from litestar.datastructures import State

import routes.webhook
from routes.webhook import handle_sms_proxy_received
from schemas.sms import SmsReceived, SmsReceivedPayload
from database.manager import create_db_pool, save_interaction, load_recent_interactions


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
        mock_settings.llm = Mock()
        mock_settings.llm.model = "test-model"
        routes.webhook.settings = mock_settings

        state = Mock(spec=State)
        state.db_pool = db_pool

        # First interaction
        mock_result1 = Mock()
        mock_result1.output = "Response A"
        mock_result1.new_messages_json.return_value = b'[{"type":"user","content":"Message A"},{"type":"assistant","content":"Response A"}]'
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

        await handle_sms_proxy_received.fn(
            request=MockRequest(), state=state, data=sms_data1
        )

        # Verify first interaction is in database
        interactions_json = await load_recent_interactions(db_pool, "+15551234567", 2)
        interactions = json.loads(interactions_json)
        assert len(interactions) == 1
        assert interactions[0]["user_prompt"] == "Message A"
        assert interactions[0]["llm_response"] == "Response A"

        # Second interaction
        mock_result2 = Mock()
        mock_result2.output = "Response B"
        mock_result2.new_messages_json.return_value = b'[{"type":"user","content":"Message B"},{"type":"assistant","content":"Response B"}]'
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

        await handle_sms_proxy_received.fn(
            request=MockRequest(), state=state, data=sms_data2
        )

        # Verify both interactions are returned (memory_depth=2)
        interactions_json = await load_recent_interactions(db_pool, "+15551234567", 2)
        interactions = json.loads(interactions_json)
        assert len(interactions) == 2
        assert interactions[0]["user_prompt"] == "Message A"
        assert interactions[0]["llm_response"] == "Response A"
        assert interactions[1]["user_prompt"] == "Message B"
        assert interactions[1]["llm_response"] == "Response B"

        # Third interaction
        mock_result3 = Mock()
        mock_result3.output = "Response C"
        mock_result3.new_messages_json.return_value = b'[{"type":"user","content":"Message C"},{"type":"assistant","content":"Response C"}]'
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

        await handle_sms_proxy_received.fn(
            request=MockRequest(), state=state, data=sms_data3
        )

        # Verify only last 2 interactions are returned (memory_depth=2)
        interactions_json = await load_recent_interactions(db_pool, "+15551234567", 2)
        interactions = json.loads(interactions_json)
        assert len(interactions) == 2
        assert interactions[0]["user_prompt"] == "Message B"
        assert interactions[0]["llm_response"] == "Response B"
        assert interactions[1]["user_prompt"] == "Message C"
        assert interactions[1]["llm_response"] == "Response C"
        # First interaction should not be returned
        assert not any(
            interaction["user_prompt"] == "Message A" for interaction in interactions
        )
        assert not any(
            interaction["llm_response"] == "Response A" for interaction in interactions
        )

    finally:
        # Restore original settings
        routes.webhook.settings = original_settings
        await _cleanup_test_db_and_mocks(db_path, db_pool, originals)


@pytest.mark.asyncio
async def test_empty_interactions():
    """Test that empty interactions return '[]'."""
    db_path, db_pool, mock_assistant, originals = await _setup_test_db_and_mocks()

    try:
        # Test empty interactions
        interactions_json = await load_recent_interactions(db_pool, "+15551234567", 5)
        assert interactions_json == "[]"

    finally:
        await _cleanup_test_db_and_mocks(db_path, db_pool, originals)


@pytest.mark.asyncio
async def test_save_and_load_interaction():
    """Test saving and loading individual interactions."""
    db_path, db_pool, mock_assistant, originals = await _setup_test_db_and_mocks()

    try:
        # Save an interaction
        interaction_id = await save_interaction(
            db_pool,
            "+15551234567",
            "Test prompt",
            "Test response",
            '{"messages": "test"}',
        )

        # Verify it's a UUID
        assert len(interaction_id) == 36  # UUID format
        assert "-" in interaction_id

        # Load the interaction
        interactions_json = await load_recent_interactions(db_pool, "+15551234567", 5)
        interactions = json.loads(interactions_json)
        assert len(interactions) == 1
        assert interactions[0]["user_prompt"] == "Test prompt"
        assert interactions[0]["llm_response"] == "Test response"
        assert "timestamp" in interactions[0]

    finally:
        await _cleanup_test_db_and_mocks(db_path, db_pool, originals)
