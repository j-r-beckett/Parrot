from litestar import post, Request
from litestar.datastructures import State
from schemas.sms import SmsReceived, SmsDelivered
from integrations.sms_proxy import send_sms as send_sms_sms_proxy
from assistant.agent import create_assistant
from assistant.dependencies import create_assistant_dependencies
from config import settings
from database.manager import load_recent_interactions, save_interaction
import system_prompt


@post("/webhook/sms-proxy/received")
async def handle_sms_proxy_received(
    request: Request, state: State, data: SmsReceived
) -> str:
    """Handle SMS received webhooks from sms-proxy."""
    request.logger.info(f"SMS received: {data}")

    # Load recent interactions for context
    interactions_json = await load_recent_interactions(
        state.db_pool, 
        data.payload.phone_number, 
        settings.memory_depth
    )
    
    # Build dynamic system prompt
    dynamic_prompt = system_prompt.prompt(settings.llm.model, interactions_json)
    
    # Create assistant with dynamic prompt
    deps = create_assistant_dependencies(state, request.logger)
    assistant = create_assistant(dynamic_prompt)
    
    # Run assistant (no message_history parameter)
    message = data.payload.message
    result = await assistant.run(message, deps=deps)
    
    # Save the interaction with full messages for debugging
    interaction_id = await save_interaction(
        state.db_pool,
        data.payload.phone_number,
        message,
        result.output,
        result.new_messages_json().decode("utf-8")
    )
    
    # Log only the interaction ID
    request.logger.info(f"Created interaction {interaction_id} for {data.payload.phone_number}")

    # If we're running locally w/ no sms-proxy, just return
    if settings.ring == "local":
        return result.output

    # If we're not running locally, send response back via sms-proxy
    await send_sms_sms_proxy(
        state.sms_proxy_client,
        result.output,
        [data.payload.phone_number],
        request.logger,
    )

    return ""


@post("/webhook/sms-proxy/delivered")
async def handle_sms_proxy_delivered(
    request: Request, state: State, data: SmsDelivered
) -> str:
    """Handle SMS delivered webhooks from sms-proxy."""
    request.logger.info(f"SMS delivered: {data}")
    return ""
