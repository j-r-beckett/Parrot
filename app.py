from litestar import Litestar, get, Request, Response, post
from litestar.datastructures import State
from litestar.di import Provide
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE
from config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sms_gateway_client import SmsGatewayClient
from schemas import SmsDelivered
from llm_client import LlmClient
from mirascope.core.base import Messages
from weather_client import WeatherClient


async def get_sms_gateway_client(state: State) -> SmsGatewayClient:
    return state.sms_gateway_client


async def get_llm_client(state: State) -> LlmClient:
    return state.llm_client


async def get_weather_client(state: State) -> WeatherClient:
    return state.weather_client


@get(
    path="/health",
    dependencies={
        "sms_gateway_client": Provide(get_sms_gateway_client),
        "llm_client": Provide(get_llm_client),
    },
)
async def health(
    request: Request, sms_gateway_client: SmsGatewayClient, llm_client: LlmClient
) -> Response:
    gateway_health, gateway_health_info = await sms_gateway_client.gateway_health()
    webhook_health, webhook_health_info = await sms_gateway_client.webhook_health()
    llm_health, llm_health_info = await llm_client.health(request.logger)

    is_healthy = gateway_health and webhook_health and llm_health

    return Response(
        content={
            "status": "healthy" if is_healthy else "unhealthy",
            "sms_gateway_info": str(gateway_health_info),
            "webhook_health_info": str(webhook_health_info),
            "llm_health_info": str(llm_health_info),
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


@get("/testllm", dependencies={"llm_client": Provide(get_llm_client)})
async def test_llm(request: Request, llm_client: LlmClient) -> Response:
    text = await llm_client.send_message(
        messages=[Messages.User("Hello there")], logger=request.logger
    )
    return Response(content=text, status_code=HTTP_200_OK)


@get("/testweather", dependencies={"weather_client": Provide(get_weather_client)})
async def test_weather(
    request: Request, weather_client: WeatherClient, lat: float, lon: float
) -> Response:
    temperature = await weather_client.get_temperature(request.logger, lat, lon)
    return Response(
        content={"temperature": temperature, "lat": lat, "lon": lon},
        status_code=HTTP_200_OK,
    )


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    app.state.llm_client = LlmClient(settings.llm_config)
    async with (
        SmsGatewayClient(
            settings, {"sms:delivered": "/webhooks/delivered"}
        ) as sms_gateway_client,
        WeatherClient(settings) as weather_client,
    ):
        app.state.sms_gateway_client = sms_gateway_client
        app.state.weather_client = weather_client
        yield


app = Litestar(
    route_handlers=[health, test_sms, webhook, test_llm, test_weather],
    lifespan=[lifespan],
    debug=settings.debug,
)
