import json
import pytest
import httpx
from pathlib import Path

import src.clients.weather as weather_client


@pytest.fixture
def fixture_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def points_response(fixture_dir):
    with open(fixture_dir / "points_response.json") as f:
        return json.load(f)


@pytest.fixture
def hourly_forecast_response(fixture_dir):
    with open(fixture_dir / "hourly_forecast_response.json") as f:
        return json.load(f)


@pytest.fixture
def twelve_hour_forecast_response(fixture_dir):
    with open(fixture_dir / "twelve_hour_forecast_response.json") as f:
        return json.load(f)


class MockLogger:
    def info(self, *args, **kwargs):
        pass


@pytest.mark.asyncio
async def test_hourly_forecast_happy_path(points_response, hourly_forecast_response):
    """Test hourly forecast with successful API responses"""
    
    # Create a mock transport that returns our fixture data
    def mock_handler(request: httpx.Request):
        if "/points/40.7128,-74.006" in str(request.url):
            return httpx.Response(200, json=points_response)
        elif "/gridpoints/OKX/33,35/forecast/hourly" in str(request.url):
            return httpx.Response(200, json=hourly_forecast_response)
        else:
            return httpx.Response(404)
    
    # Create httpx client with mock transport
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.weather.gov"
    ) as client:
        # Call the function
        logger = MockLogger()
        result = await weather_client.hourly_forecast(client, logger, 40.7128, -74.0060)
        
        # Verify the result structure
        assert result is not None
        assert hasattr(result, 'forecasts')
        assert len(result.forecasts) > 0
        
        # Check first forecast entry
        first_forecast = result.forecasts[0]
        assert hasattr(first_forecast, 'time')
        assert hasattr(first_forecast, 'temperature')
        assert hasattr(first_forecast, 'precipitation_probability')
        assert hasattr(first_forecast, 'description')
        
        # Verify data transformation
        assert first_forecast.temperature.endswith('F')
        assert first_forecast.precipitation_probability.endswith('%')


@pytest.mark.asyncio
async def test_hourly_forecast_exact_transformation():
    """Test hourly forecast with minimal hardcoded JSON to verify exact transformations"""
    
    # Minimal JSON responses with only required fields
    points_json = {
        "properties": {
            "gridId": "TEST",
            "gridX": 10,
            "gridY": 20
        }
    }
    
    hourly_json = {
        "properties": {
            "periods": [
                {
                    "startTime": "2025-08-20T14:00:00-04:00",
                    "temperature": 72,
                    "temperatureUnit": "F",
                    "probabilityOfPrecipitation": {
                        "unitCode": "wmoUnit:percent",
                        "value": 30
                    },
                    "shortForecast": "Partly Cloudy"
                },
                {
                    "startTime": "2025-08-20T15:00:00-04:00",
                    "temperature": 75,
                    "temperatureUnit": "F",
                    "probabilityOfPrecipitation": {
                        "unitCode": "wmoUnit:percent",
                        "value": 0
                    },
                    "shortForecast": "Sunny"
                }
            ]
        }
    }
    
    def mock_handler(request: httpx.Request):
        if "/points/" in str(request.url):
            return httpx.Response(200, json=points_json)
        elif "/gridpoints/TEST/10,20/forecast/hourly" in str(request.url):
            return httpx.Response(200, json=hourly_json)
        else:
            return httpx.Response(404)
    
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.weather.gov"
    ) as client:
        logger = MockLogger()
        result = await weather_client.hourly_forecast(client, logger, 40.0, -74.0)
        
        # Verify exact transformation results
        assert len(result.forecasts) == 2
        
        # First forecast - 30% precipitation
        assert result.forecasts[0].time == "Wednesday Aug 20, 2:00 PM"
        assert result.forecasts[0].temperature == "72F"
        assert result.forecasts[0].precipitation_probability == "30%"
        assert result.forecasts[0].description == "Partly Cloudy"
        
        # Second forecast - 0% precipitation
        assert result.forecasts[1].time == "Wednesday Aug 20, 3:00 PM"
        assert result.forecasts[1].temperature == "75F"
        assert result.forecasts[1].precipitation_probability == "0%"
        assert result.forecasts[1].description == "Sunny"


@pytest.mark.asyncio
async def test_twelve_hour_forecast_happy_path(points_response, twelve_hour_forecast_response):
    """Test 12-hour forecast with successful API responses"""
    
    # Create a mock transport that returns our fixture data
    def mock_handler(request: httpx.Request):
        if "/points/40.7128,-74.006" in str(request.url):
            return httpx.Response(200, json=points_response)
        elif "/gridpoints/OKX/33,35/forecast" in str(request.url):
            return httpx.Response(200, json=twelve_hour_forecast_response)
        else:
            return httpx.Response(404)
    
    # Create httpx client with mock transport
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.weather.gov"
    ) as client:
        # Call the function
        logger = MockLogger()
        result = await weather_client.twelve_hour_forecast(client, logger, 40.7128, -74.0060)
        
        # Verify the result structure
        assert result is not None
        assert hasattr(result, 'forecasts')
        assert len(result.forecasts) > 0
        
        # Check first forecast entry
        first_forecast = result.forecasts[0]
        assert hasattr(first_forecast, 'time')
        assert hasattr(first_forecast, 'temperature')
        assert hasattr(first_forecast, 'precipitation_probability')
        assert hasattr(first_forecast, 'description')
        
        # Verify data transformation
        assert first_forecast.temperature.endswith('F')
        assert first_forecast.precipitation_probability.endswith('%')
        assert len(first_forecast.description) > 0


@pytest.mark.asyncio
async def test_twelve_hour_forecast_exact_transformation():
    """Test 12-hour forecast with minimal hardcoded JSON to verify exact transformations"""
    
    # Minimal JSON responses with only required fields
    points_json = {
        "properties": {
            "gridId": "TEST",
            "gridX": 10,
            "gridY": 20
        }
    }
    
    twelve_hour_json = {
        "properties": {
            "periods": [
                {
                    "name": "Tonight",
                    "startTime": "2025-08-20T18:00:00-04:00",
                    "temperature": 65,
                    "temperatureUnit": "F",
                    "probabilityOfPrecipitation": {
                        "unitCode": "wmoUnit:percent",
                        "value": 70
                    },
                    "detailedForecast": "Rain likely with thunderstorms possible. Low around 65."
                },
                {
                    "name": "Thursday",
                    "startTime": "2025-08-21T06:00:00-04:00",
                    "temperature": 78,
                    "temperatureUnit": "F",
                    "probabilityOfPrecipitation": {
                        "unitCode": "wmoUnit:percent",
                        "value": 20
                    },
                    "detailedForecast": "Mostly sunny with a slight chance of showers. High near 78."
                }
            ]
        }
    }
    
    def mock_handler(request: httpx.Request):
        if "/points/" in str(request.url):
            return httpx.Response(200, json=points_json)
        elif "/gridpoints/TEST/10,20/forecast" in str(request.url):
            return httpx.Response(200, json=twelve_hour_json)
        else:
            return httpx.Response(404)
    
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.weather.gov"
    ) as client:
        logger = MockLogger()
        result = await weather_client.twelve_hour_forecast(client, logger, 40.0, -74.0)
        
        # Verify exact transformation results
        assert len(result.forecasts) == 2
        
        # First forecast - Tonight with rain
        assert result.forecasts[0].time == "Aug 20, Tonight"
        assert result.forecasts[0].temperature == "65F"
        assert result.forecasts[0].precipitation_probability == "70%"
        assert result.forecasts[0].description == "Rain likely with thunderstorms possible. Low around 65."
        
        # Second forecast - Thursday daytime
        assert result.forecasts[1].time == "Aug 21, Thursday"
        assert result.forecasts[1].temperature == "78F"
        assert result.forecasts[1].precipitation_probability == "20%"
        assert result.forecasts[1].description == "Mostly sunny with a slight chance of showers. High near 78."