import pytest
import httpx
import re
from datetime import datetime
from unittest.mock import Mock
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
import pytz
from timezonefinder import TimezoneFinder

from assistant.dependencies import AssistantDependencies
from assistant.tools.datetime import register_datetime_tool
from tests.utils import MockLogger


async def mock_geocode(location: str) -> tuple[float, float]:
    """Mock geocoding function that returns NYC coordinates"""
    return (40.7128, -74.0060)


@pytest.mark.asyncio
async def test_datetime_tool_happy_path():
    """Test datetime tool returns accurate current time for location."""

    # Create agent with datetime tool
    agent = Agent("test", deps_type=AssistantDependencies)
    register_datetime_tool(agent)

    deps = AssistantDependencies(
        weather_client=httpx.AsyncClient(),
        nominatim_client=httpx.AsyncClient(),
        valhalla_client=httpx.AsyncClient(),
        citi_bike_client=Mock(),  # type: ignore
        geocode=mock_geocode,
        logger=MockLogger(),
    )

    try:
        # Get expected time for NYC
        tf = TimezoneFinder()
        tz = pytz.timezone(tf.timezone_at(lat=40.7128, lng=-74.0060))
        expected_time = datetime.now(tz)

        # Use TestModel to trigger tool call
        with agent.override(model=TestModel()):
            result = await agent.run("What time is it in New York?", deps=deps)

        # Extract datetime from result
        datetime_match = re.search(
            r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", result.output
        )
        assert datetime_match, f"No datetime found in output: {result.output}"

        returned_time = tz.localize(
            datetime.strptime(datetime_match.group(), "%Y-%m-%d %H:%M:%S")
        )

        # Should be within 1 second
        time_diff = abs((returned_time - expected_time).total_seconds())
        assert time_diff <= 1, f"Time difference {time_diff} seconds too large"

    finally:
        await deps.weather_client.aclose()
        await deps.nominatim_client.aclose()
        await deps.valhalla_client.aclose()
