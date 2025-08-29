from dataclasses import dataclass
from typing import Callable, Awaitable
from litestar.types.protocols import Logger
import httpx
from functools import partial
from litestar.datastructures import State
import clients.nominatim as nominatim_client


@dataclass
class AssistantDependencies:
    """Dependencies for the assistant agent."""
    weather_client: httpx.AsyncClient
    nominatim_client: httpx.AsyncClient  
    valhalla_client: httpx.AsyncClient
    geocode: Callable[[str], Awaitable[tuple[float, float]]]
    logger: Logger


def create_assistant_dependencies(state: State, logger: Logger) -> AssistantDependencies:
    """Create assistant dependencies from Litestar state."""
    # Create partial function with httpx client bound
    geocode = partial(nominatim_client.geocode, state.nominatim_httpx_client)
    
    return AssistantDependencies(
        weather_client=state.weather_httpx_client,
        nominatim_client=state.nominatim_httpx_client,
        valhalla_client=state.valhalla_httpx_client,
        geocode=geocode,
        logger=logger,
    )