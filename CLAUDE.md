# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ludd is a Python web application built with the Litestar ASGI framework, with Android device integration capabilities. The project uses Python 3.13 and the UV package manager.

## Development Commands

```bash
# Install/update dependencies
uv sync

# Run development server with auto-reload
uv run uvicorn app:app --reload

# Alternative: Run with Litestar CLI
uv run litestar run --reload

# Run the application
uv run python -m app
```

## Architecture

### Core Components

1. **`app.py`**: Main application entry point with Litestar app instance. Currently implements a simple "Hello, world!" endpoint.

2. **Android Integration**: The project includes Android-specific functionality:
   - `android/server_mode.sh`: Boot script for rooted Android devices that configures power management settings
   - README contains device connection information (IP addresses, ADB/SSH access)

### Tech Stack

- **Framework**: Litestar 2.16.0+ (ASGI web framework)
- **Server**: Uvicorn 0.35.0+ (ASGI server)
- **Python**: 3.13
- **Package Manager**: UV (not pip)
- **Virtual Environment**: Uses `.venv` directory

## Important Context

### Android Server Mode
The `android/server_mode.sh` script is designed to run on rooted Android devices via Magisk. It:
- Disables Doze mode to prevent the device from sleeping
- Keeps WiFi active when screen is off
- Logs all actions to `/data/local/tmp/server_mode.log`

### CLI Design Goals
According to `notes.md`, the project aims to implement a conversational CLI with shortcuts and user-friendly commands like `!remember`, `!shortcut`, `!weather`, etc.

## Project Status

Early development stage - basic Litestar application structure is in place with plans for expanded CLI functionality and Android device management features.