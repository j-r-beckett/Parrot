from litestar import Litestar
from litestar.logging import LoggingConfig
from lifespan import lifespan
from routes.health import health
from routes.webhook import handle_sms_proxy_received, handle_sms_proxy_delivered
from routes.assistant import assist


logging_config = LoggingConfig(log_exceptions="always")

app = Litestar(
    route_handlers=[
        health,
        handle_sms_proxy_received,
        handle_sms_proxy_delivered,
        assist,
    ],
    lifespan=[lifespan],
    logging_config=logging_config,
)
