import json
import pytest
import httpx
from pathlib import Path

import clients.nominatim as nominatim_client


@pytest.fixture
def fixture_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def nyc_response(fixture_dir):
    with open(fixture_dir / "nominatim_nyc_response.json") as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_geocode_happy_path(nyc_response):
    """Test geocoding with successful API response from fixture"""
    
    # Create a mock transport that returns our fixture data
    def mock_handler(request: httpx.Request):
        if "/search" in str(request.url) and "New+York+City" in str(request.url):
            return httpx.Response(200, json=nyc_response)
        else:
            return httpx.Response(404)
    
    # Create httpx client with mock transport
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://nominatim.openstreetmap.org"
    ) as client:
        # Call the function
        result = await nominatim_client.geocode(client, "New York City")
        
        # Verify the result
        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 2
        
        lat, lon = result
        assert isinstance(lat, float)
        assert isinstance(lon, float)
        
        # NYC coordinates should be around 40.7, -74.0
        assert 40 < lat < 41
        assert -75 < lon < -73


@pytest.mark.asyncio
async def test_geocode_exact_transformation():
    """Test geocoding with minimal hardcoded JSON to verify exact transformations"""
    
    # Minimal JSON response with only required fields
    geocode_json = [
        {
            "lat": "40.7127281",
            "lon": "-74.0060152",
            "display_name": "New York City, New York, United States",
            "importance": 0.99
        }
    ]
    
    def mock_handler(request: httpx.Request):
        if "/search" in str(request.url):
            return httpx.Response(200, json=geocode_json)
        else:
            return httpx.Response(404)
    
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://nominatim.openstreetmap.org"
    ) as client:
        result = await nominatim_client.geocode(client, "New York City")
        
        # Verify exact transformation results
        assert result == (40.7127281, -74.0060152)


@pytest.mark.asyncio
async def test_geocode_no_results():
    """Test geocoding when no results are found"""
    
    # Empty results array
    empty_json = []
    
    def mock_handler(request: httpx.Request):
        if "/search" in str(request.url):
            return httpx.Response(200, json=empty_json)
        else:
            return httpx.Response(404)
    
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://nominatim.openstreetmap.org"
    ) as client:
        # Should raise ValueError for no results
        with pytest.raises(ValueError, match="No geocoding results found"):
            await nominatim_client.geocode(client, "Nonexistent Place XYZ123")


@pytest.mark.asyncio
async def test_geocode_multiple_results():
    """Test that geocoding returns only the first result when multiple are available"""
    
    # Multiple results, should return the first one
    multiple_json = [
        {
            "lat": "51.5074",
            "lon": "-0.1278",
            "display_name": "London, England, United Kingdom",
        },
        {
            "lat": "42.9834",
            "lon": "-81.2497",
            "display_name": "London, Ontario, Canada",
        }
    ]
    
    def mock_handler(request: httpx.Request):
        if "/search" in str(request.url):
            return httpx.Response(200, json=multiple_json)
        else:
            return httpx.Response(404)
    
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://nominatim.openstreetmap.org"
    ) as client:
        result = await nominatim_client.geocode(client, "London")
        
        # Should return coordinates of the first result (London, UK)
        assert result == (51.5074, -0.1278)