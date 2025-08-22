from litestar import get, Request, Response
from litestar.datastructures import State
from litestar.di import Provide
from litestar.status_codes import HTTP_200_OK
import httpx
from src.config import settings
from src.clients.sms_gateway import send_sms


async def get_sms_gateway_client(state: State) -> httpx.AsyncClient:
    return state.sms_gateway_client


@get("/testsms", dependencies={"sms_gateway_client": Provide(get_sms_gateway_client)})
async def test_sms(request: Request, sms_gateway_client: httpx.AsyncClient) -> Response:
    await send_sms(
        sms_gateway_client, "hello there 3", settings.sms.settler.number, request.logger
    )

    return Response(content="sent sms", status_code=HTTP_200_OK)