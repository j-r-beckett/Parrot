from litestar import get, Request


@get(path="/health")
async def health(request: Request) -> str:
    return "healthy"