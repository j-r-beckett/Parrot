import os
import logging
from contextvars import ContextVar

# Disable Anthropic and OpenAI SDK deferred schema building. Prevents errors during message serialization
os.environ["DEFER_PYDANTIC_BUILD"] = "false"

from litestar import Litestar
from litestar.logging import LoggingConfig
from lifespan import lifespan
from routes.health import health
from routes.webhook import handle_sms_proxy_received, handle_sms_proxy_delivered
from logging_middleware import CorrelationFilter, CorrelationFormatter, CorrelationMiddleware

# Create correlation ID contextvar
correlation_id_contextvar = ContextVar('correlation_id')

logging_config = LoggingConfig(
    root={
        "level": "INFO",
        "handlers": ["queue_listener"],
        "filters": ["correlation"]
    },
    formatters={
        "standard": {
            "()": CorrelationFormatter,
            "format": "%(asctime)s - %(correlation_id)s - %(levelname)s - %(message)s"
        }
    },
    filters={
        "correlation": {
            "()": CorrelationFilter,
            "contextvar": correlation_id_contextvar
        }
    },
    loggers={
        # Ensure specific loggers also get the correlation filter
        "httpx": {
            "level": "INFO",
            "filters": ["correlation"],
            "propagate": True
        },
        "uvicorn": {
            "level": "INFO", 
            "filters": ["correlation"],
            "propagate": True
        },
        "litestar": {
            "level": "INFO",
            "filters": ["correlation"],
            "propagate": True
        }
    },
    log_exceptions="always",
)

app = Litestar(
    route_handlers=[
        health,
        handle_sms_proxy_received,
        handle_sms_proxy_delivered,
    ],
    lifespan=[lifespan],
    logging_config=logging_config,
    middleware=[CorrelationMiddleware(correlation_id_contextvar)],
)
