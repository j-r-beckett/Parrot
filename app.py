from litestar import Litestar, get, Request, Response, post
from litestar.datastructures import State
from litestar.di import Provide
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE
from config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Literal
import httpx
from sms_gateway import create_sms_gateway_client, send_sms, init_webhooks
from schemas import SmsDelivered, HourlyForecast, TwelveHourForecast, Directions
from weather_client import WeatherClient
from weather_tools import forecast_tool
from datetime_tools import datetime_tool
from navigation_tools import navigation_tool
from assistant import Assistant
from nominatim_client import NominatimClient
from valhalla_client import ValhallaClient


async def get_sms_gateway_client(state: State) -> httpx.AsyncClient:
    return state.sms_gateway_client


async def get_webhook_events(state: State) -> dict:
    return state.webhook_events


async def get_weather_client(state: State) -> WeatherClient:
    return state.weather_client


async def get_nominatim_client(state: State) -> NominatimClient:
    return state.nominatim_client


async def get_valhalla_client(state: State) -> ValhallaClient:
    return state.valhalla_client


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
    "/testweather/hourly", dependencies={"weather_client": Provide(get_weather_client)}
)
async def test_weather_hourly(
    request: Request, weather_client: WeatherClient, lat: float, lon: float
) -> HourlyForecast:
    return await weather_client.hourly_forecast(request.logger, lat, lon)


@get(
    "/testweather/12hour",
    dependencies={"weather_client": Provide(get_weather_client)},
)
async def test_weather_12hour(
    request: Request, weather_client: WeatherClient, lat: float, lon: float
) -> TwelveHourForecast:
    return await weather_client.twelveHour_forecast(request.logger, lat, lon)


@get(
    "/testagent",
    dependencies={
        "weather_client": Provide(get_weather_client),
        "nominatim_client": Provide(get_nominatim_client),
        "valhalla_client": Provide(get_valhalla_client),
    },
)
async def test_agent(
    request: Request,
    weather_client: WeatherClient,
    nominatim_client: NominatimClient,
    valhalla_client: ValhallaClient,
    q: str,
) -> str:
    assistant = Assistant(
        [
            forecast_tool(weather_client, nominatim_client, request.logger),
            datetime_tool(nominatim_client),
            navigation_tool(valhalla_client, nominatim_client),
        ],
        request.logger,
        settings.llm,
    )
    return await assistant.step(q)


@get("/testgeocoding", dependencies={"nominatim_client": Provide(get_nominatim_client)})
async def test_geocoding(
    request: Request, nominatim_client: NominatimClient, text: str
) -> tuple[float, float]:
    return await nominatim_client.geocode(text)


@get(
    "/testnav",
    dependencies={
        "valhalla_client": Provide(get_valhalla_client),
        "nominatim_client": Provide(get_nominatim_client),
    },
)
async def test_nav(
    request: Request,
    valhalla_client: ValhallaClient,
    nominatim_client: NominatimClient,
    start: str,
    end: str,
    mode: Literal["drive", "walk", "bike", "transit"] = "drive",
) -> Directions:
    # Geocode the start and end locations
    start_coords = await nominatim_client.geocode(start)
    end_coords = await nominatim_client.geocode(end)

    return await valhalla_client.directions(
        start=start_coords,
        end=end_coords,
        mode=mode,
    )


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    async def on_delivered(data: SmsDelivered) -> None:
        app.logger.info("SMS delivered webhook received: %s", data)

    async with (
        create_sms_gateway_client(settings.sms.settler) as sms_gateway_client,
        WeatherClient(settings.nws) as weather_client,
        NominatimClient(settings.nominatim) as nominatim_client,
        ValhallaClient() as valhalla_client,
    ):
        await init_webhooks(
            gateway_client=sms_gateway_client,
            registrar=app.register,
            route_prefix="/webhooks/settler",
            webhook_target_url=settings.sms.settler.webhook_target_url,
            on_delivered=on_delivered,
        )

        app.state.sms_gateway_client = sms_gateway_client
        app.state.weather_client = weather_client
        app.state.nominatim_client = nominatim_client
        app.state.valhalla_client = valhalla_client
        yield


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
