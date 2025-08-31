from contextvars import ContextVar
import uuid
import logging
from litestar.middleware.base import ASGIMiddleware
from litestar.types import ASGIApp, Scope, Receive, Send, Message
from litestar.datastructures import MutableScopeHeaders


class CorrelationFormatter(logging.Formatter):
    """Formatter that safely handles missing correlation_id fields."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Ensure correlation_id exists, fallback to 'system' if not set
        if not hasattr(record, 'correlation_id'):
            record.correlation_id = 'system'
        return super().format(record)


class CorrelationFilter(logging.Filter):
    """Logging filter that adds correlation ID to log records at creation time."""
    
    def __init__(self, contextvar: ContextVar[str]):
        super().__init__()
        self.contextvar = contextvar
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Add correlation_id when record is created (in request thread)
        record.correlation_id = self.contextvar.get('system')
        return True



class CorrelationMiddleware(ASGIMiddleware):
    """Middleware that adds correlation ID to requests and responses."""

    def __init__(self, contextvar: ContextVar[str]):
        super().__init__()
        self.contextvar = contextvar

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
            return

        # Get or generate correlation ID
        headers = dict(scope.get("headers", []))
        correlation_id: str | None = None

        # Look for existing X-Correlation-ID header
        for name, value in headers.items():
            if name.lower() == b"x-correlation-id":
                correlation_id = value.decode("utf-8")
                break

        # Generate new ID if not provided
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Set in context
        self.contextvar.set(correlation_id)

        # Add to response headers
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableScopeHeaders.from_message(message=message)
                response_headers["X-Correlation-ID"] = str(correlation_id)
            await send(message)

        await next_app(scope, receive, send_wrapper)
