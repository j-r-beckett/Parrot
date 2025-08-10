from litestar import Litestar, get
from config import settings


@get("/")
async def index() -> str:
    return f"SMS gateway addr: {settings.sms_gateway_addr}"


app = Litestar([index], debug=settings.debug)
