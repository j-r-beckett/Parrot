from litestar import Litestar, get, Response, Request
from litestar.datastructures import State
from litestar.di import Provide
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE
from config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sms_gateway_client import SmsGatewayClient


async def get_sms_gateway_client(state: State) -> SmsGatewayClient:
    return state.sms_gateway_client


@get(
    path="/health", dependencies={"sms_gateway_client": Provide(get_sms_gateway_client)}
)
async def health(request: Request, sms_gateway_client: SmsGatewayClient) -> Response:
    sms_is_healthy, sms_health_info = await sms_gateway_client.health()

    is_healthy = sms_is_healthy

    return Response(
        content={
            "status": "healthy" if is_healthy else "unhealthy",
            "sms_gateway_info": str(sms_health_info),
        },
        status_code=HTTP_200_OK if is_healthy else HTTP_503_SERVICE_UNAVAILABLE,
    )


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    async with SmsGatewayClient(settings) as sms_gateway_client:
        app.state.sms_gateway_client = sms_gateway_client
        yield


app = Litestar(
    route_handlers=[health],
    lifespan=[lifespan],
    debug=settings.debug,
)
