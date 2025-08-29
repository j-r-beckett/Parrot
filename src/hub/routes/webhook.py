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


@post("/webhook/sms-proxy/received")
async def handle_sms_proxy_received(
    request: Request, state: State, data: SmsReceived
) -> str:
    """Handle SMS received webhooks from sms-proxy."""
    request.logger.info(f"SMS received: {data}")

    # Create partial functions with httpx clients bound
    geocode = partial(nominatim_client.geocode, state.nominatim_httpx_client)
    get_directions = partial(valhalla_client.directions, state.valhalla_httpx_client)

    # Set up tools
    tools = [
        forecast_tool(state.weather_httpx_client, geocode, request.logger),
        datetime_tool(geocode),
        navigation_tool(get_directions, geocode),
    ]

    # Set up initial messages with system prompt
    messages = [Messages.System(settings.prompts.assistant).model_dump()]

    # Process the incoming SMS and generate a response
    response, _ = await state.assistant.step(messages, tools, data.payload.message)

    # Send response back via sms-proxy
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
