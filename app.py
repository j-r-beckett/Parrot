from litestar import Litestar, get, Request, Response, post
from litestar.datastructures import State
from litestar.di import Provide
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE
from config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Literal, Callable
from functools import partial
import httpx
from sms_gateway import create_sms_gateway_client, send_sms, init_webhooks
from schemas import (
    SmsDelivered,
    SmsReceived,
    HourlyForecast,
    TwelveHourForecast,
    Directions,
)
import weather_client
from weather_tools import forecast_tool
from datetime_tools import datetime_tool
from navigation_tools import navigation_tool
from assistant import create_llm_call, step
from mirascope import Messages
import nominatim_client
import valhalla_client


async def get_sms_gateway_client(state: State) -> httpx.AsyncClient:
    return state.sms_gateway_client


async def get_webhook_events(state: State) -> dict:
    return state.webhook_events


async def get_weather_httpx_client(state: State) -> httpx.AsyncClient:
    return state.weather_httpx_client


async def get_nominatim_httpx_client(state: State) -> httpx.AsyncClient:
    return state.nominatim_httpx_client


async def get_valhalla_httpx_client(state: State) -> httpx.AsyncClient:
    return state.valhalla_httpx_client


async def get_llm_call(state: State) -> Callable:
    return state.llm_call


@get(path="/health")
async def health(request: Request) -> str:
    return "healthy"


@get("/testsms", dependencies={"sms_gateway_client": Provide(get_sms_gateway_client)})
async def test_sms(request: Request, sms_gateway_client: httpx.AsyncClient) -> Response:
    await send_sms(
        sms_gateway_client, "hello there 3", settings.sms.settler.number, request.logger
    )

    return Response(content="sent sms", status_code=HTTP_200_OK)


@get(
    "/testweather/hourly", dependencies={"weather_httpx_client": Provide(get_weather_httpx_client)}
)
async def test_weather_hourly(
    request: Request, weather_httpx_client: httpx.AsyncClient, lat: float, lon: float
) -> HourlyForecast:
    return await weather_client.hourly_forecast(weather_httpx_client, request.logger, lat, lon)


@get(
    "/testweather/12hour",
    dependencies={"weather_httpx_client": Provide(get_weather_httpx_client)},
)
async def test_weather_12hour(
    request: Request, weather_httpx_client: httpx.AsyncClient, lat: float, lon: float
) -> TwelveHourForecast:
    return await weather_client.twelve_hour_forecast(weather_httpx_client, request.logger, lat, lon)


@get(
    "/testagent",
    dependencies={
        "weather_httpx_client": Provide(get_weather_httpx_client),
        "nominatim_httpx_client": Provide(get_nominatim_httpx_client),
        "valhalla_httpx_client": Provide(get_valhalla_httpx_client),
        "llm_call": Provide(get_llm_call),
    },
)
async def test_agent(
    request: Request,
    weather_httpx_client: httpx.AsyncClient,
    nominatim_httpx_client: httpx.AsyncClient,
    valhalla_httpx_client: httpx.AsyncClient,
    llm_call: Callable,
    q: str,
) -> str:
    # Create partial functions with httpx clients bound
    geocode = partial(nominatim_client.geocode, nominatim_httpx_client)
    get_directions = partial(valhalla_client.directions, valhalla_httpx_client)
    
    # Set up tools
    tools = [
        forecast_tool(weather_httpx_client, geocode, request.logger),
        datetime_tool(geocode),
        navigation_tool(get_directions, geocode),
    ]
    
    # Set up initial messages with system prompt
    messages = [Messages.System(settings.prompts.assistant)]
    
    # Call step function
    response, _ = await step(llm_call, messages, tools, q)
    return response


@get("/testgeocoding", dependencies={"nominatim_httpx_client": Provide(get_nominatim_httpx_client)})
async def test_geocoding(
    request: Request, nominatim_httpx_client: httpx.AsyncClient, text: str
) -> tuple[float, float]:
    return await nominatim_client.geocode(nominatim_httpx_client, text)


@get(
    "/testnav",
    dependencies={
        "valhalla_httpx_client": Provide(get_valhalla_httpx_client),
        "nominatim_httpx_client": Provide(get_nominatim_httpx_client),
    },
)
async def test_nav(
    request: Request,
    valhalla_httpx_client: httpx.AsyncClient,
    nominatim_httpx_client: httpx.AsyncClient,
    start: str,
    end: str,
    mode: Literal["drive", "walk", "bike", "transit"] = "drive",
) -> Directions:
    # Geocode the start and end locations
    start_coords = await nominatim_client.geocode(nominatim_httpx_client, start)
    end_coords = await nominatim_client.geocode(nominatim_httpx_client, end)

    return await valhalla_client.directions(
        valhalla_httpx_client,
        start=start_coords,
        end=end_coords,
        mode=mode,
    )


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    async def on_delivered(data: SmsDelivered) -> None:
        app.logger.info("SMS delivered: %s", data)

    async def on_received(data: SmsReceived) -> None:
        app.logger.info("SMS received: %s", data)

        # Create partial functions with httpx clients bound
        geocode = partial(nominatim_client.geocode, app.state.nominatim_httpx_client)
        get_directions = partial(valhalla_client.directions, app.state.valhalla_httpx_client)
        
        # Set up tools
        tools = [
            forecast_tool(
                app.state.weather_httpx_client, geocode, app.logger
            ),
            datetime_tool(geocode),
            navigation_tool(get_directions, geocode),
        ]
        
        # Set up initial messages with system prompt
        messages = [Messages.System(settings.prompts.assistant)]
        
        # Process the incoming SMS and generate a response
        response, _ = await step(app.state.llm_call, messages, tools, data.payload.message)

        # Send the response back via SMS
        await send_sms(
            app.state.sms_gateway_client,
            response,
            data.payload.phone_number,
            app.logger,
        )

    weather_httpx_client = httpx.AsyncClient(
        base_url=settings.nws.api_url,
        headers={"User-Agent": settings.nws.user_agent},
        timeout=10.0,
        follow_redirects=True,
    )
    
    nominatim_httpx_client = httpx.AsyncClient(
        base_url=settings.nominatim.api_url,
        headers={"User-Agent": settings.nominatim.user_agent},
        timeout=10.0,
        follow_redirects=True,
    )
    
    valhalla_httpx_client = httpx.AsyncClient(
        base_url="https://valhalla1.openstreetmap.de",
        timeout=10.0,
        follow_redirects=True,
    )
    
    # Create the LLM call function
    llm_call = create_llm_call(settings.llm)
    
    async with (
        create_sms_gateway_client(settings.sms.settler) as settler_sms_client,
        create_sms_gateway_client(settings.sms.nomad) as nomad_sms_client,
    ):
        await init_webhooks(
            gateway_client=settler_sms_client,
            registrar=app.register,
            route_prefix="/webhooks/settler",
            webhook_target_url=settings.sms.settler.webhook_target_url,
            on_delivered=on_delivered,
            on_received=on_received,
        )

        app.state.sms_gateway_client = settler_sms_client
        app.state.weather_httpx_client = weather_httpx_client
        app.state.nominatim_httpx_client = nominatim_httpx_client
        app.state.valhalla_httpx_client = valhalla_httpx_client
        app.state.llm_call = llm_call
        try:
            yield
        finally:
            await weather_httpx_client.aclose()
            await nominatim_httpx_client.aclose()
            await valhalla_httpx_client.aclose()


app = Litestar(
    route_handlers=[
        health,
        test_sms,
        test_weather_hourly,
        test_weather_12hour,
        test_agent,
        test_geocoding,
        test_nav,
    ],
    lifespan=[lifespan],
    debug=settings.debug,
)
