from litestar import Request, post
import httpx
from typing import Callable, Optional, Any, Awaitable
from schemas import SmsDelivered


async def init_webhooks(
    client: httpx.AsyncClient,
    registrar: Callable[[Any], None],
    route_prefix: str,
    webhook_target_url: str,
    on_delivered: Optional[Callable[[SmsDelivered], Awaitable[None]]],
) -> None:
    # get active webhooks
    get_webhooks_response = await client.get("/webhooks")
    get_webhooks_response.raise_for_status()
    active_webhooks = [hook["id"] for hook in get_webhooks_response.json()]

    # delete active webhooks
    for webhook_id in active_webhooks:
        delete_webhook_response = await client.delete(f"/webhooks/{webhook_id}")
        delete_webhook_response.raise_for_status()

    # add new webhooks
    events = []

    if on_delivered:
        events.append(("sms:delivered", f"{route_prefix}/delivered"))

        @post(f"{route_prefix}/delivered")
        async def hook(request: Request, data: SmsDelivered) -> str:
            await on_delivered(data)
            return ""

        registrar(hook)

    for event, route in events:
        create_webhook_response = await client.post(
            "/webhooks", json={"url": f"{webhook_target_url}{route}", "event": event}
        )
        create_webhook_response.raise_for_status()
