import json
import pytest
import httpx
from pathlib import Path

import clients.valhalla as valhalla_client


@pytest.fixture
def fixture_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def walk_response(fixture_dir):
    with open(fixture_dir / "valhalla_walk_response.json") as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_directions_happy_path(walk_response):
    """Test directions with successful API response from fixture"""

    # Create a mock transport that returns our fixture data
    def mock_handler(request: httpx.Request):
        if "/route" in str(request.url):
            return httpx.Response(200, json=walk_response)
        else:
            return httpx.Response(404)

    # Create httpx client with mock transport
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://valhalla1.openstreetmap.de"
    ) as client:
        # Call the function
        result = await valhalla_client.directions(
            client,
            start=(40.7580, -73.9855),  # Times Square
            end=(40.7829, -73.9654),  # Central Park
            mode="walk",
        )

        # Verify the result structure
        assert result is not None
        assert hasattr(result, "steps")
        assert hasattr(result, "total_time")
        assert hasattr(result, "total_distance")

        # Check that we have steps
        assert len(result.steps) > 0
        assert isinstance(result.steps[0], str)

        # Check formatting
        assert "mile" in result.total_distance.lower()
        assert "hour" in result.total_time or "minute" in result.total_time


@pytest.mark.asyncio
async def test_directions_exact_transformation():
    """Test directions with minimal hardcoded JSON to verify exact transformations"""

    # Minimal JSON response with only required fields
    directions_json = {
        "trip": {
            "summary": {
                "time": 2700,  # 45 minutes
                "length": 2.3034,  # miles
            },
            "legs": [
                {
                    "maneuvers": [
                        {
                            "instruction": "Walk north on Broadway.",
                            "verbal_post_transition_instruction": "Continue for 80 feet.",
                        },
                        {
                            "instruction": "Turn right onto West 47th Street.",
                            "verbal_post_transition_instruction": None,
                        },
                        {"instruction": "You have arrived at your destination."},
                    ]
                }
            ],
        }
    }

    def mock_handler(request: httpx.Request):
        if "/route" in str(request.url):
            return httpx.Response(200, json=directions_json)
        else:
            return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://valhalla1.openstreetmap.de"
    ) as client:
        result = await valhalla_client.directions(
            client, start=(40.7580, -73.9855), end=(40.7829, -73.9654), mode="walk"
        )

        # Verify exact transformation results
        assert result.total_time == "45 minutes"
        assert result.total_distance == "2.3034 miles"

        assert len(result.steps) == 3
        assert result.steps[0] == "Walk north on Broadway. Continue for 80 feet."
        assert result.steps[1] == "Turn right onto West 47th Street."
        assert result.steps[2] == "You have arrived at your destination."


@pytest.mark.asyncio
async def test_directions_different_modes():
    """Test that different travel modes map to correct costing models"""

    captured_payloads = []

    def mock_handler(request: httpx.Request):
        # Capture the request payload
        if request.content:
            payload = json.loads(request.content)
            captured_payloads.append(payload)

        # Return a minimal valid response
        return httpx.Response(
            200,
            json={
                "trip": {
                    "summary": {"time": 600, "length": 5.0},
                    "legs": [{"maneuvers": [{"instruction": "Test"}]}],
                }
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://valhalla1.openstreetmap.de"
    ) as client:
        # Test each mode
        modes_to_costing = {
            "drive": "auto",
            "walk": "pedestrian",
            "bike": "bicycle",
            "transit": "multimodal",
        }

        for mode, expected_costing in modes_to_costing.items():
            captured_payloads.clear()

            await valhalla_client.directions(
                client, start=(40.7580, -73.9855), end=(40.7829, -73.9654), mode=mode
            )

            # Verify the correct costing model was used
            assert len(captured_payloads) == 1
            assert captured_payloads[0]["costing"] == expected_costing
            assert captured_payloads[0]["units"] == "miles"


@pytest.mark.asyncio
async def test_directions_time_formatting():
    """Test various time formatting scenarios"""

    test_cases = [
        (30, "0 minutes"),  # Less than a minute rounds to 0
        (90, "1 minutes"),  # 1.5 minutes truncates to 1
        (150, "2 minutes"),  # 2.5 minutes truncates to 2
        (3600, "1 hours"),  # Exactly 1 hour (no minutes)
        (3660, "1 hours, 1 minutes"),  # 1 hour and 1 minute
        (7320, "2 hours, 2 minutes"),  # Multiple hours and minutes
        (59, "0 minutes"),  # Just under a minute rounds to 0
        (61, "1 minutes"),  # Just over a minute
    ]

    for seconds, expected_time in test_cases:
        directions_json = {
            "trip": {
                "summary": {"time": seconds, "length": 1.0},
                "legs": [{"maneuvers": [{"instruction": "Test"}]}],
            }
        }

        def mock_handler(request: httpx.Request):
            return httpx.Response(200, json=directions_json)

        transport = httpx.MockTransport(mock_handler)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://valhalla1.openstreetmap.de"
        ) as client:
            result = await valhalla_client.directions(
                client, start=(0, 0), end=(1, 1), mode="drive"
            )

            assert result.total_time == expected_time, f"Failed for {seconds} seconds"
