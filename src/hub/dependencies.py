from litestar.datastructures import State
import httpx
from aiosqlitepool import SQLiteConnectionPool
from assistant.llm import Assistant


async def get_sms_proxy_client(state: State) -> httpx.AsyncClient:
    return state.sms_proxy_client


async def get_weather_httpx_client(state: State) -> httpx.AsyncClient:
    return state.weather_httpx_client


async def get_nominatim_httpx_client(state: State) -> httpx.AsyncClient:
    return state.nominatim_httpx_client


async def get_valhalla_httpx_client(state: State) -> httpx.AsyncClient:
    return state.valhalla_httpx_client


async def get_assistant(state: State) -> Assistant:
    return state.assistant


async def get_db_pool(state: State) -> SQLiteConnectionPool:
    return state.db_pool
