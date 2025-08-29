import pytest
import httpx
import json
from pathlib import Path
from unittest.mock import Mock
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from assistant.dependencies import AssistantDependencies
from assistant.tools.weather import register_weather_tool


class MockLogger:
    def info(self, *args, **kwargs):
        pass


async def mock_geocode(location: str) -> tuple[float, float]:
    """Mock geocoding function that returns NYC coordinates"""
    return (40.7128, -74.0060)


def load_fixture(filename: str):
    """Load test fixture JSON file."""
    fixture_path = Path(__file__).parent / "fixtures" / filename
    with open(fixture_path) as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_weather_tool_happy_path():
    """Test weather tool with successful API responses."""
    
    # Load test fixtures
    points_response = load_fixture("points_response.json")
    forecast_response = load_fixture("twelve_hour_forecast_response.json")
    
    # Mock NWS API responses
    def weather_mock_handler(request: httpx.Request):
        if "/points/40.7128,-74.006" in str(request.url):
            return httpx.Response(200, json=points_response)
        elif "/gridpoints/OKX/33,35/forecast" in str(request.url):
            return httpx.Response(200, json=forecast_response)
        return httpx.Response(404)
    
    # Create agent with weather tool
    agent = Agent("test", deps_type=AssistantDependencies)
    register_weather_tool(agent)
    
    # Create mock weather client
    weather_client = httpx.AsyncClient(
        transport=httpx.MockTransport(weather_mock_handler),
        base_url="https://api.weather.gov"
    )
    
    deps = AssistantDependencies(
        weather_client=weather_client,
        nominatim_client=httpx.AsyncClient(),  # Won't be used
        valhalla_client=httpx.AsyncClient(),   # Won't be used
        geocode=mock_geocode,
        logger=MockLogger(),
    )
    
    try:
        # Use TestModel to trigger tool call
        with agent.override(model=TestModel()):
            result = await agent.run("What's the weather in NYC?", deps=deps)
        
        # Verify tool was called and returned weather data
        assert "forecast" in result.output.lower()
        # Should contain weather data from the fixture - check for period names from twelve_hour_forecast_response.json
        period_names = [period["name"] for period in forecast_response["properties"]["periods"]]
        assert any(period_name in result.output for period_name in period_names[:3])  # Check first few periods
        
    finally:
        await weather_client.aclose()

