from litestar import Litestar, get, Request, Response, post
from litestar.datastructures import State
from litestar.di import Provide
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE
from config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sms_gateway_client import SmsGatewayClient
from schemas import SmsDelivered
from anthropic import AsyncAnthropic


async def get_sms_gateway_client(state: State) -> SmsGatewayClient:
    return state.sms_gateway_client


async def get_anthropic_client(state: State) -> AsyncAnthropic:
    return state.anthropic_client


@get(
    path="/health", dependencies={"sms_gateway_client": Provide(get_sms_gateway_client)}
)
async def health(sms_gateway_client: SmsGatewayClient) -> Response:
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


@get("/testanthropic", dependencies={"anthropic_client": Provide(get_anthropic_client)})
async def test_anthropic(anthropic_client: AsyncAnthropic) -> Response:
    response = await anthropic_client.messages.create(
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello there"}],
        model="claude-sonnet-4-20250514",
    )
    text = " ".join(block.text for block in response.content if block.type == "text")
    return Response(content=text, status_code=HTTP_200_OK)


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    app.state.anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    async with SmsGatewayClient(
        settings, {"sms:delivered": "/webhooks/delivered"}
    ) as sms_gateway_client:
        app.state.sms_gateway_client = sms_gateway_client
        yield


app = Litestar(
    route_handlers=[health, test_sms, webhook, test_anthropic],
    lifespan=[lifespan],
    debug=settings.debug,
)
