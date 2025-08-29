import os

# Disable Anthropic and OpenAI SDK deferred schema building. Prevents errors during message serialization
os.environ["DEFER_PYDANTIC_BUILD"] = "false"

from litestar import Litestar
from litestar.logging import LoggingConfig
from lifespan import lifespan
from routes.health import health
from routes.webhook import handle_sms_proxy_received, handle_sms_proxy_delivered


logging_config = LoggingConfig(log_exceptions="always")

app = Litestar(
    route_handlers=[
        health,
        handle_sms_proxy_received,
        handle_sms_proxy_delivered,
    ],
    lifespan=[lifespan],
    logging_config=logging_config,
)
