from litestar import Litestar, get, Request, Response, post
from litestar.datastructures import State
from litestar.di import Provide
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE
from config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sms_gateway_client import SmsGatewayClient
from schemas import SmsDelivered, HourlyForecast, TwelveHourForecast
from mirascope.core.base import Messages
from weather_client import WeatherClient
from weather_tools import forecast_tool
from assistant import Assistant
from nominatim_client import NominatimClient


async def get_sms_gateway_client(state: State) -> SmsGatewayClient:
    return state.sms_gateway_client


async def get_weather_client(state: State) -> WeatherClient:
    return state.weather_client


async def get_nominatim_client(state: State) -> NominatimClient:
    return state.nominatim_client


@get(
    path="/health",
    dependencies={
        "sms_gateway_client": Provide(get_sms_gateway_client),
    },
)
async def health(request: Request, sms_gateway_client: SmsGatewayClient) -> Response:
    gateway_health, gateway_health_info = await sms_gateway_client.gateway_health()
    webhook_health, webhook_health_info = await sms_gateway_client.webhook_health()

    is_healthy = gateway_health and webhook_health

    return Response(
        content={
            "status": "healthy" if is_healthy else "unhealthy",
            "sms_gateway_info": str(gateway_health_info),
            "webhook_health_info": str(webhook_health_info),
        },
        status_code=HTTP_200_OK if is_healthy else HTTP_503_SERVICE_UNAVAILABLE,
    )


@get("/testsms", dependencies={"sms_gateway_client": Provide(get_sms_gateway_client)})
async def test_sms(request: Request, sms_gateway_client: SmsGatewayClient) -> Response:
    await sms_gateway_client.send_sms("hello there 2", "5123662653", request.logger)

    return Response(content="sent sms", status_code=HTTP_200_OK)


@post("/webhooks/delivered")
async def webhook(request: Request, data: SmsDelivered) -> Response:
    request.logger.info("received webhook: %s", data)
    return Response(content="", status_code=HTTP_200_OK)


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
    return await weather_client.TwelveHour_forecast(request.logger, lat, lon)


@get("/testagent", dependencies={"weather_client": Provide(get_weather_client)})
async def test_agent(request: Request, weather_client: WeatherClient, q: str) -> str:
    assistant = Assistant([forecast_tool(weather_client)])
    return assistant.step(q)


@get("/testgeocoding", dependencies={"nominatim_client": Provide(get_nominatim_client)})
async def test_geocoding(
    request: Request, nominatim_client: NominatimClient, text: str
) -> tuple[float, float]:
    return await nominatim_client.geocode(text)


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    async with (
        SmsGatewayClient(
            settings, {"sms:delivered": "/webhooks/delivered"}
        ) as sms_gateway_client,
        WeatherClient(settings) as weather_client,
        NominatimClient(settings) as nominatim_client,
    ):
        app.state.sms_gateway_client = sms_gateway_client
        app.state.weather_client = weather_client
        app.state.nominatim_client = nominatim_client
        yield


app = Litestar(
    route_handlers=[
        health,
        test_sms,
        webhook,
        test_weather_hourly,
        test_weather_12hour,
        test_agent,
        test_geocoding,
    ],
    lifespan=[lifespan],
    debug=settings.debug,
)
