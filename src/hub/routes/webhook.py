from litestar import post, Request
from litestar.datastructures import State
from schemas.sms import SmsReceived, SmsDelivered
from integrations.sms_proxy import send_sms as send_sms_sms_proxy
from assistant.agent import create_assistant
from assistant.dependencies import create_assistant_dependencies
from config import settings
from database.manager import load_recent_messages, save_conversation


@post("/webhook/sms-proxy/received")
async def handle_sms_proxy_received(
    request: Request, state: State, data: SmsReceived
) -> str:
    """Handle SMS received webhooks from sms-proxy."""
    request.logger.info(f"SMS received: {data}")

    # Create assistant dependencies
    deps = create_assistant_dependencies(state, request.logger)

    # Create assistant
    assistant = create_assistant()

    # Load recent messages based on memory_depth setting
    message_history = await load_recent_messages(
        state.db_pool, data.payload.phone_number, settings.memory_depth
    )
    message = data.payload.message

    # Run assistant
    result = await assistant.run(message, deps=deps, message_history=message_history)

    # Save conversation using PydanticAI's built-in JSON serialization
    await save_conversation(
        state.db_pool,
        data.payload.phone_number,
        result.new_messages_json().decode("utf-8"),
    )

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
