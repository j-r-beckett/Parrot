# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Clanker is a Python web application built with the Litestar ASGI framework, focused on SMS gateway integration with Android device management capabilities. The project uses Python 3.13 and the UV package manager.

## Development Commands

```bash
# Install/update dependencies
uv sync

# Run development server with auto-reload (default port 8000)
uv run litestar run --reload

# Run on a different port (e.g., for testing with logs access)
uv run litestar run --reload --port 8003

# Alternative: Run with uvicorn
uv run uvicorn app:app --reload

# Run the application directly
uv run python -m app
```

### Running the App Notes

- Use `uv run litestar run --reload` to run the app
- If there's an instance already running, Claude can assume it's running in reload mode
- If Claude doesn't need access to app logs, Claude can send requests to the running app
- If Claude needs to start their own server instance:
  1. First try to start on port 8000
  2. If there's already one running on port 8000, shut it down first
  3. Start the new instance on port 8000
  4. Remember to shut it down when done

## Architecture

### Core Components

1. **`app.py`**: Main application entry point with Litestar app instance
   - Defines health check endpoint (`/health`)
   - Test SMS endpoint (`/testsms`)
   - Test LLM endpoint (`/testllm`)
   - Webhook handler for SMS delivery notifications (`/webhooks/delivered`)
   - Manages SMS and LLM client lifecycle via Litestar lifespan events

2. **`sms_gateway_client.py`**: HTTPX-based SMS gateway client
   - Async context manager implementation
   - HTTP Basic Authentication
   - UUID-based message tracking
   - Health check capabilities
   - 5-second timeout configuration
   - Webhook management (registration and cleanup)

3. **`llm_client.py`**: Mirascope-based LLM client for Claude Sonnet 4
   - Async message sending with cost tracking
   - Health check with gauge pattern using `_last_result`
   - The health check reports on the most recent API call status
   - If no recent call exists or last call failed >15 seconds ago, makes a minimal API call
   - This acts as a gauge - health status reflects the last known state

4. **`config.py`**: Pydantic Settings-based configuration
   - Environment variable management
   - `.env` file support
   - SMS gateway configuration (URL, auth credentials)
   - LLM configuration (Anthropic API key, model selection)

### Dependency Injection Pattern

The application uses Litestar's DI system:
- SMS and LLM clients initialized during app lifespan
- Injected into route handlers via `Provide` dependency
- Accessed through `State` object

### SMS Message Flow

1. Client requests endpoint → 2. Handler receives injected SMS client → 3. Client sends request to SMS gateway → 4. UUID tracking for message → 5. Response returned

### Tech Stack

- **Framework**: Litestar 2.16.0+ (ASGI web framework)
- **Server**: Uvicorn 0.35.0+ (ASGI server)
- **HTTP Client**: HTTPX 0.28.1+ (async)
- **LLM Integration**: Mirascope 1.0.0+ with Anthropic
- **Configuration**: Pydantic 2.11.7+ with Settings
- **Python**: 3.13
- **Package Manager**: UV (not pip)

## Android Integration

The project includes Android device management tools:
- `android/server_mode.sh`: Magisk boot script for rooted devices
  - Disables Doze mode
  - Keeps WiFi active
  - Logs to `/data/local/tmp/server_mode.log`

Device connection (from README):
- Pixel 2 IP: 192.168.0.21
- ADB: `adb connect 192.168.0.16:5555`
- SSH: `ssh -p 8022 u0_a192@192.168.0.16`

## Environment Configuration

The application expects a `.env` file with:
- `SMS_GATEWAY_URL`: SMS gateway API endpoint
- `SMS_GATEWAY_USERNAME`: Basic auth username
- `SMS_GATEWAY_PASSWORD`: Basic auth password
- `ANTHROPIC_API_KEY`: API key for Claude LLM access
- `DEBUG`: Enable debug mode (optional, defaults to False)
- `ACTIVE_LLM`: LLM selection (optional, defaults to "claude-sonnet-4")

## Future Implementation Notes

According to `notes.md`, planned features include:
- Conversational CLI with shortcuts
- User commands: `!remember`, `!shortcut`, `!weather`, etc.
- Extended Android device management

## Project Status

Early development - functional SMS gateway integration complete, ready for feature expansion.
- Run tests with `uv run python -m pytest`