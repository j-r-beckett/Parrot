from litestar import post, Request
from litestar.datastructures import State
from functools import partial
import asyncio
from schemas.sms import SmsReceived, SmsDelivered
from clients.sms_proxy import send_sms as send_sms_sms_proxy
from assistant.tools.weather import forecast_tool
from assistant.tools.datetime import datetime_tool
from assistant.tools.navigation import navigation_tool
import clients.nominatim as nominatim_client
import clients.valhalla as valhalla_client
from mirascope import Messages
from config import settings
from database.manager import load_last_conversation, save_conversation


@post("/webhook/sms-proxy/received")
async def handle_sms_proxy_received(
    request: Request, state: State, data: SmsReceived
) -> str:
    """Handle SMS received webhooks from sms-proxy."""
    request.logger.info(f"SMS received: {data}")

    # Check if this should continue existing conversation (starts with "! ")
    conversation_id = None
    if data.payload.message.startswith("! "):
        # Load existing conversation and strip the "! " prefix
        messages, conversation_id = await load_last_conversation(state.db_pool, data.payload.phone_number)
        if conversation_id is None:
            messages = [Messages.System(settings.prompts.assistant).model_dump()]
        # Remove the "! " prefix from the message
        actual_message = data.payload.message[2:]
    else:
        # Start new conversation
        messages = [Messages.System(settings.prompts.assistant).model_dump()]
        actual_message = data.payload.message

    # Create partial functions with httpx clients bound
    geocode = partial(nominatim_client.geocode, state.nominatim_httpx_client)
    get_directions = partial(valhalla_client.directions, state.valhalla_httpx_client)

    # Set up tools
    tools = [
        forecast_tool(state.weather_httpx_client, geocode, request.logger),
        datetime_tool(geocode),
        navigation_tool(get_directions, geocode),
    ]

    # Remember the original message count
    original_message_count = len(messages)

    # Process the incoming SMS and generate a response
    response, all_messages = await state.assistant.step(
        messages, tools, actual_message
    )

    # Save only the new messages to database
    new_messages = all_messages[original_message_count:]
    await save_conversation(state.db_pool, data.payload.phone_number, new_messages, conversation_id)

    # If we're running locally w/ no sms-proxy, just return
    if settings.ring == "local":
        return response

    # If we're not running locally, send response back via sms-proxy
    await send_sms_sms_proxy(
        state.sms_proxy_client,
        response,
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
