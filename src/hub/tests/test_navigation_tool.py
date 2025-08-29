import pytest
import httpx
import json
from pathlib import Path
from unittest.mock import Mock
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from assistant.dependencies import AssistantDependencies
from assistant.tools.navigation import register_navigation_tool


class MockLogger:
    def info(self, *args, **kwargs):
        pass


async def mock_geocode(location: str) -> tuple[float, float]:
    """Mock geocoding function that returns NYC coordinates"""
    if "times square" in location.lower():
        return (40.7580, -73.9855)  # Times Square
    elif "central park" in location.lower():
        return (40.7829, -73.9654)  # Central Park
    return (40.7128, -74.0060)  # Default NYC


def load_fixture(filename: str):
    """Load test fixture JSON file."""
    fixture_path = Path(__file__).parent / "fixtures" / filename
    with open(fixture_path) as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_navigation_tool_happy_path():
    """Test navigation tool with successful Valhalla API responses."""
    
    # Load test fixture
    valhalla_response = load_fixture("valhalla_walk_response.json")
    
    # Mock Valhalla API responses
    def navigation_mock_handler(request: httpx.Request):
        if "valhalla1.openstreetmap.de/route" in str(request.url):
            return httpx.Response(200, json=valhalla_response)
        return httpx.Response(404)
    
    # Create agent with navigation tool
    agent = Agent("test", deps_type=AssistantDependencies)
    register_navigation_tool(agent)
    
    # Create mock valhalla client
    valhalla_client = httpx.AsyncClient(
        transport=httpx.MockTransport(navigation_mock_handler),
        base_url="https://valhalla1.openstreetmap.de"
    )
    
    deps = AssistantDependencies(
        weather_client=httpx.AsyncClient(),      # Won't be used
        nominatim_client=httpx.AsyncClient(),    # Won't be used
        valhalla_client=valhalla_client,
        geocode=mock_geocode,
        logger=MockLogger(),
    )
    
    try:
        # Use TestModel to trigger tool call
        with agent.override(model=TestModel()):
            result = await agent.run("How do I walk from Times Square to Central Park?", deps=deps)
        
        # Verify tool was called and returned navigation data
        assert "navigate" in result.output.lower()
        
        # Should contain typical navigation words in the response
        output_lower = result.output.lower()
        assert "left" in output_lower
        assert "right" in output_lower
        assert "continue" in output_lower
        
    finally:
        await deps.weather_client.aclose()
        await deps.nominatim_client.aclose()
        await valhalla_client.aclose()