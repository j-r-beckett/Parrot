# Parrot Hub Service

The **hub** is a Litestar-based Python service that acts as an intelligent SMS assistant with AI-powered conversational capabilities. It receives SMS messages via webhooks from the sms-proxy service and responds with helpful information using various external APIs.

## Architecture

The hub service is built on:
- **Litestar** - Fast ASGI web framework
- **Pydantic AI** - LLM integration library with Anthropic Claude support
- **SQLite** - Conversation persistence with connection pooling
- **httpx** - Async HTTP client for external API calls

## Core Features

### AI Assistant
- **Models**: Supports Claude Sonnet 4 (with thinking mode) and Claude 3.5 Haiku
- **Conversation Memory**: Persistent conversations stored in SQLite database
- **Tool Integration**: Weather, navigation, and datetime tools
- **Terse Responses**: Configured for brief, efficient replies optimized for SMS

### SMS Integration
- Receives SMS via webhooks from sms-proxy service
- Conversation continuation with `! ` prefix
- Auto-registration with sms-proxy for webhook delivery
- Delivery confirmation handling

### Available Tools
1. **Weather** - National Weather Service forecasts via coordinates
2. **Navigation** - Turn-by-turn directions via Valhalla routing service  
3. **DateTime** - Current time for any location with timezone handling
4. **Geocoding** - Location lookup via Nominatim/OpenStreetMap
5. **Web Search** - PydanticAI builtin WebSearchTool for current information
6. **Code Execution** - PydanticAI builtin CodeExecutionTool (Anthropic's tool lets the model run Python3)

## Key Components

### Application Structure
```
app.py              # Main Litestar application setup
lifespan.py         # Service lifecycle management (clients, DB, registration)
config.py           # Dynaconf-based configuration loading
dependencies.py     # Dependency injection for HTTP clients and services
```

### Routes
```
routes/
├── health.py       # Health check endpoint
└── webhook.py      # SMS webhook handlers (received/delivered)
```

### Assistant System
```
assistant/
├── agent.py        # Pydantic AI agent factory and tool registration
├── dependencies.py # Dependency injection for assistant tools
└── tools/          # Tool implementations
    ├── weather.py    # NWS weather forecasts
    ├── navigation.py # Valhalla routing directions
    └── datetime.py   # Timezone-aware datetime lookup
```

### External Clients
```
clients/
├── sms_proxy.py    # SMS sending and registration management
├── weather.py      # National Weather Service API client
├── nominatim.py    # OpenStreetMap geocoding client
└── valhalla.py     # Valhalla routing service client
```

### Data Management
```
database/
├── manager.py      # SQLite connection pooling and conversation storage
└── models.py       # Database models (currently minimal)

schemas/
├── sms.py          # SMS webhook payload schemas
├── weather.py      # Weather forecast response schemas
├── navigation.py   # Navigation directions schemas
└── conversation.py # Conversation data schemas
```

## Configuration

### Environment Variables
- `ANTHROPIC_API_KEY` - Claude API access
- `SMS_PROXY_URL` - sms-proxy service URL
- `HOST_URL` - This service's public URL for webhook registration
- `RING` - Deployment environment (local/ppe/prod)

### Settings Files
- `settings.json` - Service configuration including API URLs and LLM settings
- `prompts.json` - System prompt for the assistant (emphasizes terseness)

## Development

### Local Development
```bash
# Start the service with hot reload
uv run litestar run --reload

# Run tests
uv run python -m pytest

# Alternative port if 8000 is taken
uv run litestar run --host 0.0.0.0 --port 8001 --reload
```

### Testing
- **Comprehensive test suite** in `tests/` directory with JSON fixtures for external API responses
- **Webhook handler tests** - Test SMS conversation flows, message history, and database persistence
- **Tool integration tests** - Test weather, navigation, and datetime tools using Pydantic AI's TestModel
- **Client unit tests** - Test HTTP API integrations and data transformations
- **Test patterns**: Uses httpx MockTransport for API mocking and TestModel for tool testing

## Deployment

### Docker
- Multi-stage Dockerfile using Python 3.13-slim
- uv for dependency management
- Exposes port 8000

### Production Deployment
```bash
# Deploy to production/ppe
./deploy.sh prod  # or ppe
```

- Builds Docker image and pushes to private registry
- Uses docker-compose template with environment substitution
- Automatic service restart with new version
- Production deployment requires confirmation prompt

### Environment Rings
- **local** - Development mode, no SMS sending
- **ppe** - Pre-production environment  
- **prod** - Production environment

## External Dependencies

### APIs Used
- **Anthropic Claude** - AI assistant capabilities
- **National Weather Service** - Weather forecasts (US only)
- **Nominatim/OpenStreetMap** - Geocoding services
- **Valhalla** - Routing and navigation directions
- **SMS-Proxy** - SMS sending and webhook management

### Service Registration
The hub automatically registers with sms-proxy on startup to receive:
- SMS received webhooks (`/webhook/sms-proxy/received`)
- SMS delivered webhooks (`/webhook/sms-proxy/delivered`)

## Conversation Flow

1. SMS received via webhook from sms-proxy
2. Check for conversation continuation (`! ` prefix)
3. Load existing conversation or start new one
4. Process message through Pydantic AI agent with available tools
5. Save conversation to database
6. Send response via sms-proxy (unless running locally)

## Key Architectural Decisions

- **Async-first**: All I/O operations are async for better performance
- **Connection pooling**: SQLite connection pooling for database efficiency  
- **Tool-based AI**: Pydantic AI agents use structured tools with type-safe dependency injection
- **Persistent conversations**: Full conversation history maintained per phone number
- **Environment-aware**: Different behavior based on deployment ring
- **Resource cleanup**: Proper lifecycle management for HTTP clients and database connections

## Monitoring

- Health check endpoint at `/health`
- Structured logging throughout the application
- Automatic sms-proxy re-registration every 45 seconds
- Database initialization on startup

## Common Issues and Solutions

### MockValSer Serialization Error
**Error**: `TypeError: 'MockValSer' object cannot be converted to 'SchemaSerializer'`

**Cause**: Anthropic and OpenAI SDKs use deferred Pydantic schema building (`defer_build=True`) which creates MockValSer placeholders instead of real schema serializers. This breaks serialization of message objects containing web search results or other complex tool outputs.

**Solution**: Set `DEFER_PYDANTIC_BUILD=false` environment variable to disable deferred schema building. This is handled in:
- `app.py` - Sets the environment variable at startup before any imports
- `.envrc` - Sets the variable for development/testing environments
- Use PydanticAI's `new_messages_json()` method for proper message serialization