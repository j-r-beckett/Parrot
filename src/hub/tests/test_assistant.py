import pytest
import tempfile
import os
import uuid
from unittest.mock import AsyncMock, Mock
from litestar.datastructures import State

import routes.webhook
from routes.webhook import handle_sms_proxy_received
from schemas.sms import SmsReceived, SmsReceivedPayload
from database.manager import create_db_pool, save_conversation, load_last_conversation
from pydantic_ai.messages import UserPromptPart, ModelRequest, ModelResponse, TextPart, SystemPromptPart, ModelMessagesTypeAdapter


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
    
    return db_path, db_pool, mock_assistant, (original_create_assistant, original_create_dependencies)


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
async def test_new_conversation_first_time():
    """Test starting a new conversation when user has no previous conversations."""
    db_path, db_pool, mock_assistant, originals = await _setup_test_db_and_mocks()
    
    try:
        # Mock assistant.run for first-time user
        mock_result = Mock()
        mock_result.output = "Hello! How can I help you?"
        mock_messages = [
            ModelRequest(parts=[
                SystemPromptPart(content="You are a helpful assistant."),
                UserPromptPart(content="Hello")
            ]),
            ModelResponse(parts=[TextPart(content="Hello! How can I help you?")])
        ]
        mock_result.new_messages_json.return_value = ModelMessagesTypeAdapter.dump_json(mock_messages).decode('utf-8')
        mock_assistant.run = AsyncMock(return_value=mock_result)
        
        # Create state and SMS payload
        state = Mock(spec=State)
        state.db_pool = db_pool
        
        sms_data = SmsReceived(
            device_id="test-device",
            id="test-webhook-123", 
            payload=SmsReceivedPayload(
                phone_number="+15551234567",
                message="Hello",
                received_at="2025-08-29T06:20:00Z",
                message_id="msg-123"
            )
        )
        
        # Call webhook handler
        result = await handle_sms_proxy_received.fn(request=MockRequest(), state=state, data=sms_data)
        
        # Verify response
        assert result == "Hello! How can I help you?"
        
        # Verify assistant.run was called with empty history
        mock_assistant.run.assert_called_once()
        call_args = mock_assistant.run.call_args
        assert call_args[0][0] == "Hello"
        assert call_args[1]['message_history'] == []
        
        # Verify conversation was saved to database
        messages, conversation_id = await load_last_conversation(db_pool, "+15551234567")
        assert len(messages) == 2  # Request + response
        assert conversation_id is not None
        
        # Verify message content
        assert isinstance(messages[0], ModelRequest)
        assert len(messages[0].parts) == 2  # System + user
        assert messages[0].parts[0].content == "You are a helpful assistant."
        assert messages[0].parts[1].content == "Hello"
        
        assert isinstance(messages[1], ModelResponse)
        assert messages[1].parts[0].content == "Hello! How can I help you?"
        
    finally:
        await _cleanup_test_db_and_mocks(db_path, db_pool, originals)


@pytest.mark.asyncio
async def test_new_conversation_after_previous():
    """Test starting a new conversation when user has had previous conversations."""
    db_path, db_pool, mock_assistant, originals = await _setup_test_db_and_mocks()
    
    try:
        # Pre-populate database with old conversation (different ID)
        old_conversation_id = str(uuid.uuid4())
        old_messages = [
            ModelRequest(parts=[
                SystemPromptPart(content="You are a helpful assistant."),
                UserPromptPart(content="Old question")
            ]),
            ModelResponse(parts=[TextPart(content="Old answer")])
        ]
        old_messages_json = ModelMessagesTypeAdapter.dump_json(old_messages).decode('utf-8')
        await save_conversation(db_pool, "+15551234567", old_messages_json, old_conversation_id)
        
        # Mock assistant.run for new conversation (without ! prefix)
        mock_result = Mock()
        mock_result.output = "Hello again! How can I help?"
        mock_messages = [
            ModelRequest(parts=[
                SystemPromptPart(content="You are a helpful assistant."),
                UserPromptPart(content="New question")
            ]),
            ModelResponse(parts=[TextPart(content="Hello again! How can I help?")])
        ]
        mock_result.new_messages_json.return_value = ModelMessagesTypeAdapter.dump_json(mock_messages).decode('utf-8')
        mock_assistant.run = AsyncMock(return_value=mock_result)
        
        # Create state and SMS payload (no ! prefix)
        state = Mock(spec=State)
        state.db_pool = db_pool
        
        sms_data = SmsReceived(
            device_id="test-device",
            id="test-webhook-new",
            payload=SmsReceivedPayload(
                phone_number="+15551234567", 
                message="New question",
                received_at="2025-08-29T06:22:00Z",
                message_id="msg-new"
            )
        )
        
        # Call webhook handler
        result = await handle_sms_proxy_received.fn(request=MockRequest(), state=state, data=sms_data)
        
        # Verify response
        assert result == "Hello again! How can I help?"
        
        # Verify assistant.run was called with empty history (new conversation)
        mock_assistant.run.assert_called_once()
        call_args = mock_assistant.run.call_args
        assert call_args[0][0] == "New question"
        assert call_args[1]['message_history'] == []  # Should be empty for new conversation
        
        # Verify new conversation was saved to database
        messages, conversation_id = await load_last_conversation(db_pool, "+15551234567")
        assert len(messages) == 2  # Should have new conversation (request + response)
        assert conversation_id != old_conversation_id  # Should be different conversation
        
        # Verify new conversation content
        assert isinstance(messages[0], ModelRequest)
        assert len(messages[0].parts) == 2  # System + user
        assert messages[0].parts[1].content == "New question"
        
        assert isinstance(messages[1], ModelResponse)  
        assert messages[1].parts[0].content == "Hello again! How can I help?"
        
    finally:
        await _cleanup_test_db_and_mocks(db_path, db_pool, originals)


@pytest.mark.asyncio
async def test_continue_conversation_no_history():
    """Test attempting to continue a conversation when user has no previous conversations."""
    db_path, db_pool, mock_assistant, originals = await _setup_test_db_and_mocks()
    
    try:
        # Mock assistant.run - when no history is found, should start new conversation
        mock_result = Mock()
        mock_result.output = "I don't have previous context, but let me help!"
        mock_messages = [
            ModelRequest(parts=[
                SystemPromptPart(content="You are a helpful assistant."),
                UserPromptPart(content="Continue from before")
            ]),
            ModelResponse(parts=[TextPart(content="I don't have previous context, but let me help!")])
        ]
        mock_result.new_messages_json.return_value = ModelMessagesTypeAdapter.dump_json(mock_messages).decode('utf-8')
        mock_assistant.run = AsyncMock(return_value=mock_result)
        
        # Create state and SMS payload with ! prefix but no history
        state = Mock(spec=State)
        state.db_pool = db_pool
        
        sms_data = SmsReceived(
            device_id="test-device",
            id="test-webhook-continue-no-hist",
            payload=SmsReceivedPayload(
                phone_number="+15551234567",
                message="! Continue from before",
                received_at="2025-08-29T06:23:00Z",
                message_id="msg-continue-no-hist"
            )
        )
        
        # Call webhook handler
        result = await handle_sms_proxy_received.fn(request=MockRequest(), state=state, data=sms_data)
        
        # Verify response
        assert result == "I don't have previous context, but let me help!"
        
        # Verify assistant.run was called with empty history (no previous conversation found)
        mock_assistant.run.assert_called_once()
        call_args = mock_assistant.run.call_args
        assert call_args[0][0] == "Continue from before"  # ! prefix stripped
        assert call_args[1]['message_history'] == []  # Should be empty when no history found
        
        # Verify conversation was saved
        messages, conversation_id = await load_last_conversation(db_pool, "+15551234567")
        assert len(messages) == 2  # New conversation created
        assert conversation_id is not None
        
    finally:
        await _cleanup_test_db_and_mocks(db_path, db_pool, originals)


@pytest.mark.asyncio
async def test_continue_conversation_with_history():
    """Test continuing a conversation when user has previous conversation history."""
    db_path, db_pool, mock_assistant, originals = await _setup_test_db_and_mocks()
    
    try:
        # Pre-populate database with first exchange
        conversation_id = str(uuid.uuid4())
        initial_messages = [
            ModelRequest(parts=[
                SystemPromptPart(content="You are a helpful assistant."),
                UserPromptPart(content="What's 2+2?")
            ]),
            ModelResponse(parts=[TextPart(content="2+2 equals 4.")])
        ]
        initial_messages_json = ModelMessagesTypeAdapter.dump_json(initial_messages).decode('utf-8')
        await save_conversation(db_pool, "+15551234567", initial_messages_json, conversation_id)
        
        # Mock assistant.run for continuation (no system prompt in new messages)
        mock_result = Mock()
        mock_result.output = "3+3 equals 6."
        mock_messages = [
            ModelRequest(parts=[UserPromptPart(content="What about 3+3?")]),
            ModelResponse(parts=[TextPart(content="3+3 equals 6.")])
        ]
        mock_result.new_messages_json.return_value = ModelMessagesTypeAdapter.dump_json(mock_messages).decode('utf-8')
        mock_assistant.run = AsyncMock(return_value=mock_result)
        
        # Create state and SMS payload with ! prefix
        state = Mock(spec=State)
        state.db_pool = db_pool
        
        sms_data = SmsReceived(
            device_id="test-device",
            id="test-webhook-continue",
            payload=SmsReceivedPayload(
                phone_number="+15551234567",
                message="! What about 3+3?",
                received_at="2025-08-29T06:24:00Z",
                message_id="msg-continue"
            )
        )
        
        # Call webhook handler
        result = await handle_sms_proxy_received.fn(request=MockRequest(), state=state, data=sms_data)
        
        # Verify response
        assert result == "3+3 equals 6."
        
        # Verify assistant.run was called with existing history
        mock_assistant.run.assert_called_once()
        call_args = mock_assistant.run.call_args
        assert call_args[0][0] == "What about 3+3?"  # ! prefix stripped
        
        # Verify the EXACT history content was loaded, not just the count
        loaded_history = call_args[1]['message_history']
        assert len(loaded_history) == 2
        assert loaded_history[0].parts[0].content == "You are a helpful assistant."
        assert loaded_history[0].parts[1].content == "What's 2+2?"
        assert loaded_history[1].parts[0].content == "2+2 equals 4."
        
        # Verify database contains complete conversation (4 messages total)
        messages, loaded_conversation_id = await load_last_conversation(db_pool, "+15551234567")
        assert loaded_conversation_id == conversation_id  # Same conversation
        assert len(messages) == 4  # Initial 2 + new 2
        
        # Check first exchange (unchanged)
        assert isinstance(messages[0], ModelRequest)
        assert len(messages[0].parts) == 2  # System + user
        assert messages[0].parts[0].content == "You are a helpful assistant."
        assert messages[0].parts[1].content == "What's 2+2?"
        
        assert isinstance(messages[1], ModelResponse)
        assert messages[1].parts[0].content == "2+2 equals 4."
        
        # Check second exchange (no system prompt)
        assert isinstance(messages[2], ModelRequest)
        assert len(messages[2].parts) == 1  # Only user prompt
        assert messages[2].parts[0].content == "What about 3+3?"
        
        assert isinstance(messages[3], ModelResponse)
        assert messages[3].parts[0].content == "3+3 equals 6."
        
    finally:
        await _cleanup_test_db_and_mocks(db_path, db_pool, originals)

