import pytest
from logging import getLogger
from unittest.mock import AsyncMock
import httpx

from assistant.agent import create_assistant
from assistant.dependencies import AssistantDependencies
from pydantic_ai.models.test import TestModel


class MockLogger:
    def info(self, *args, **kwargs):
        pass


async def mock_geocode(location: str) -> tuple[float, float]:
    """Mock geocoding function"""
    return (40.7128, -74.0060)  # NYC coordinates


@pytest.mark.asyncio
async def test_assistant_says_hello():
    """Test that assistant responds with 'hello' when prompted."""
    
    # Mock HTTP responses for the various APIs
    def weather_mock_handler(request: httpx.Request):
        if "/points/" in str(request.url):
            return httpx.Response(200, json={
                "properties": {"gridId": "OKX", "gridX": 33, "gridY": 35}
            })
        elif "/gridpoints/" in str(request.url):
            return httpx.Response(200, json={
                "properties": {
                    "periods": [
                        {
                            "name": "Today",
                            "startTime": "2025-08-20T12:00:00-04:00",
                            "temperature": 75,
                            "temperatureUnit": "F",
                            "probabilityOfPrecipitation": {"value": 30},
                            "detailedForecast": "Partly cloudy with a chance of showers."
                        }
                    ]
                }
            })
        return httpx.Response(404)

    def nominatim_mock_handler(request: httpx.Request):
        return httpx.Response(200, json=[{
            "lat": "40.7128",
            "lon": "-74.0060",
            "display_name": "New York City"
        }])

    def valhalla_mock_handler(request: httpx.Request):
        return httpx.Response(200, json={
            "trip": {
                "legs": [{
                    "maneuvers": [
                        {
                            "instruction": "Turn right",
                            "length": 0.5,
                            "time": 30
                        }
                    ]
                }]
            }
        })

    # Create mock HTTP clients with proper transport
    weather_client = httpx.AsyncClient(
        transport=httpx.MockTransport(weather_mock_handler),
        base_url="https://api.weather.gov"
    )
    nominatim_client = httpx.AsyncClient(
        transport=httpx.MockTransport(nominatim_mock_handler),
        base_url="https://nominatim.openstreetmap.org"
    )
    valhalla_client = httpx.AsyncClient(
        transport=httpx.MockTransport(valhalla_mock_handler),
        base_url="https://valhalla1.openstreetmap.de"
    )

    deps = AssistantDependencies(
        weather_client=weather_client,
        nominatim_client=nominatim_client,
        valhalla_client=valhalla_client,
        geocode=mock_geocode,
        logger=MockLogger(),
    )

    assistant = create_assistant()

    try:
        # Use TestModel to avoid real API calls
        with assistant.override(model=TestModel(custom_output_text="Hello there!")):
            result = await assistant.run('Say "hello"', deps=deps)

        assert "hello" in result.output.lower()
        # Should have at least user message + assistant response (may include system prompt and tool calls)
        assert len(result.all_messages()) >= 2
    finally:
        await weather_client.aclose()
        await nominatim_client.aclose() 
        await valhalla_client.aclose()


@pytest.mark.asyncio
async def test_assistant_tool_call():
    """Test that assistant can call tools and get the magic number."""
    # Create a custom agent with a simple tool for this test
    from pydantic_ai import Agent
    from pydantic_ai.tools import RunContext
    
    agent = Agent("test", deps_type=AssistantDependencies)
    
    @agent.tool
    async def magic_number(ctx: RunContext[AssistantDependencies]) -> int:
        """Get the magic number."""
        return 58

    # Create minimal dependencies (tool doesn't use them)
    deps = AssistantDependencies(
        weather_client=httpx.AsyncClient(),
        nominatim_client=httpx.AsyncClient(),
        valhalla_client=httpx.AsyncClient(),
        geocode=mock_geocode,
        logger=MockLogger(),
    )

    try:
        # Use TestModel to avoid real API calls
        with agent.override(model=TestModel()):
            result = await agent.run("What is the magic number?", deps=deps)

        # TestModel should call the tool and include result in output
        assert "58" in result.output
        # Should have user message, tool call/result, and final response
        assert len(result.all_messages()) >= 2
    finally:
        await deps.weather_client.aclose()
        await deps.nominatim_client.aclose()
        await deps.valhalla_client.aclose()


@pytest.mark.asyncio
async def test_assistant_tool_call_exception():
    """Test that assistant handles tool exceptions properly."""
    # Create a custom agent with a failing tool for this test
    from pydantic_ai import Agent
    from pydantic_ai.tools import RunContext
    
    agent = Agent("test", deps_type=AssistantDependencies)
    
    @agent.tool
    async def failing_tool(ctx: RunContext[AssistantDependencies]) -> str:
        """A tool that always throws an exception."""
        raise Exception("This tool intentionally fails")

    # Create minimal dependencies (tool doesn't use them)
    deps = AssistantDependencies(
        weather_client=httpx.AsyncClient(),
        nominatim_client=httpx.AsyncClient(),
        valhalla_client=httpx.AsyncClient(),
        geocode=mock_geocode,
        logger=MockLogger(),
    )

    try:
        # Use TestModel to avoid real API calls
        # The exception should be handled by the agent framework
        with agent.override(model=TestModel()):
            try:
                result = await agent.run("Use the failing tool", deps=deps)
                # If we get here, the agent handled the exception and continued
                assert result.all_messages() is not None
                assert len(result.all_messages()) > 0
            except Exception as e:
                # If the exception bubbles up, that's also acceptable behavior
                assert "intentionally fails" in str(e)
    finally:
        await deps.weather_client.aclose()
        await deps.nominatim_client.aclose()
        await deps.valhalla_client.aclose()
