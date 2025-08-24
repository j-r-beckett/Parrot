from litestar import get, Request, Response
from litestar.datastructures import State
from litestar.di import Provide
from litestar.status_codes import HTTP_200_OK
import httpx
from config import settings
from clients.smsgap import send_sms
from dependencies import get_settler_smsgap_client


@get("/testsms", dependencies={"smsgap_client": Provide(get_settler_smsgap_client)})
async def test_sms(request: Request, smsgap_client: httpx.AsyncClient) -> Response:
    await send_sms(
        smsgap_client, "hello there 3", [settings.sms.settler.number], request.logger
    )

    return Response(content="sent sms", status_code=HTTP_200_OK)