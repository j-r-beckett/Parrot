import pytest
import httpx
from datetime import datetime, timezone, timedelta
import asyncio

from integrations.citi_bike import CitiBikeClient, Station
from tests.utils import MockLogger


@pytest.mark.asyncio
async def test_citi_bike_client_happy_path():
    """Test CitiBikeClient startup, get results, and shutdown with synthetic data"""

    # Create synthetic API responses with recent timestamps to avoid long waits
    now_timestamp = int(datetime.now(timezone.utc).timestamp())

    system_info_response = {
        "data": {"timezone": "America/Los_Angeles"},
        "version": "2.3",
        "last_updated": now_timestamp,
        "ttl": 1,
    }

    station_info_response = {
        "data": {
            "stations": [
                {"station_id": "station_1", "lat": 37.7749, "lon": -122.4194},
                {"station_id": "station_2", "lat": 37.7849, "lon": -122.4294},
            ]
        },
        "last_updated": now_timestamp,
        "ttl": 1,
    }

    station_status_response = {
        "data": {
            "stations": [
                {
                    "station_id": "station_1",
                    "vehicle_types_available": [
                        {"vehicle_type_id": "1", "count": 5},  # regular bikes
                        {"vehicle_type_id": "2", "count": 3},  # ebikes
                    ],
                },
                {
                    "station_id": "station_2",
                    "vehicle_types_available": [
                        {"vehicle_type_id": "1", "count": 2},
                        {"vehicle_type_id": "2", "count": 4},
                    ],
                },
            ]
        },
        "last_updated": now_timestamp,
        "ttl": 1,
    }

    # Create mock handler
    def mock_handler(request: httpx.Request):
        if "/system_information.json" in str(request.url):
            return httpx.Response(200, json=system_info_response)
        elif "/station_information.json" in str(request.url):
            return httpx.Response(200, json=station_info_response)
        elif "/station_status.json" in str(request.url):
            return httpx.Response(200, json=station_status_response)
        else:
            return httpx.Response(404)

    # Create httpx client with mock transport
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as httpx_client:
        logger = MockLogger()

        # Test the client
        async with CitiBikeClient(httpx_client, logger) as client:
            # Set fast error recovery for tests
            client._error_wait_seconds = 0.01

            # Let the background tasks start (they should run once immediately)
            await asyncio.sleep(0.1)

            # Get stations and verify results
            stations = await client.get_stations()

            # Should have 2 stations with expected data
            assert len(stations) == 2

            # Find stations by lat to verify data (since order might vary)
            station_1 = next(s for s in stations if s.lat == 37.7749)
            station_2 = next(s for s in stations if s.lat == 37.7849)

            # Verify station_1 data
            assert station_1.lat == 37.7749
            assert station_1.lon == -122.4194
            assert station_1.num_bikes == 5
            assert station_1.num_ebikes == 3

            # Verify station_2 data
            assert station_2.lat == 37.7849
            assert station_2.lon == -122.4294
            assert station_2.num_bikes == 2
            assert station_2.num_ebikes == 4


@pytest.mark.asyncio
async def test_sync_loop_debug():
    """Debug what's happening in the sync loop"""

    now_timestamp = int(datetime.now(timezone.utc).timestamp())
    call_count = {"count": 0}

    def mock_handler(request: httpx.Request):
        if "/system_information.json" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": {"timezone": "America/Los_Angeles"},
                    "version": "2.3",
                    "last_updated": now_timestamp,
                    "ttl": 1,
                },
            )
        elif "/station_information.json" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": {"stations": []},
                    "last_updated": now_timestamp,
                    "ttl": 1,
                },
            )
        elif "/station_status.json" in str(request.url):
            call_count["count"] += 1
            print(f"Mock handler called {call_count['count']} times")
            return httpx.Response(
                200,
                json={
                    "data": {"stations": []},
                    "last_updated": now_timestamp,
                    "ttl": 1,
                },
            )
        else:
            return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as httpx_client:
        logger = MockLogger()

        # Test a minimal sync scenario with timeout
        try:
            async with asyncio.timeout(2):  # 2 second timeout
                async with CitiBikeClient(httpx_client, logger) as client:
                    client._error_wait_seconds = 0.01
                    print("Client started, waiting...")
                    await asyncio.sleep(0.5)
                    print("Done waiting")
        except asyncio.TimeoutError:
            print("Sync loop timed out - this tells us it's hanging")
            # This is expected if sync is hanging
            pass

        print(f"Total API calls made: {call_count['count']}")


@pytest.mark.asyncio
async def test_background_sync_updates():
    """Test that background sync picks up modified data"""

    now_timestamp = int(datetime.now(timezone.utc).timestamp())

    # Mutable data that we can modify during the test
    station_data = {"num_bikes": 5, "num_ebikes": 3}

    def mock_handler(request: httpx.Request):
        if "/system_information.json" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": {"timezone": "America/Los_Angeles"},
                    "version": "2.3",
                    "last_updated": now_timestamp,
                    "ttl": 60,
                },
            )
        elif "/station_information.json" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "stations": [
                            {
                                "station_id": "test_station",
                                "lat": 37.7749,
                                "lon": -122.4194,
                            }
                        ]
                    },
                    "last_updated": now_timestamp,
                    "ttl": 60,
                },
            )
        elif "/station_status.json" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "stations": [
                            {
                                "station_id": "test_station",
                                "vehicle_types_available": [
                                    {
                                        "vehicle_type_id": "1",
                                        "count": station_data["num_bikes"],
                                    },
                                    {
                                        "vehicle_type_id": "2",
                                        "count": station_data["num_ebikes"],
                                    },
                                ],
                            }
                        ]
                    },
                    "last_updated": now_timestamp
                    - 10,  # In the past so sync triggers quickly
                    "ttl": 1,  # Very short TTL
                },
            )
        else:
            return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as httpx_client:
        logger = MockLogger()

        async with CitiBikeClient(httpx_client, logger) as client:
            client._error_wait_seconds = 0.01

            # Get initial data
            stations = await client.get_stations()
            assert len(stations) == 1
            assert stations[0].num_bikes == 5
            assert stations[0].num_ebikes == 3

            # Modify the mock data
            station_data["num_bikes"] = 8
            station_data["num_ebikes"] = 1

            # Wait for background sync to pick up the changes
            await asyncio.sleep(0.5)

            # Get updated data - should reflect the modified values
            stations = await client.get_stations()
            assert len(stations) == 1
            assert stations[0].num_bikes == 8  # Should be updated by background sync
            assert stations[0].num_ebikes == 1  # Should be updated by background sync


@pytest.mark.asyncio
async def test_update_station_info():
    """Test _update_station_info method directly"""

    now_timestamp = int(datetime.now(timezone.utc).timestamp())

    station_info_response = {
        "data": {
            "stations": [
                {"station_id": "test_station", "lat": 37.7749, "lon": -122.4194}
            ]
        },
        "last_updated": now_timestamp,
        "ttl": 300,
    }

    def mock_handler(request: httpx.Request):
        if "/system_information.json" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": {"timezone": "America/Los_Angeles"},
                    "version": "2.3",
                    "last_updated": now_timestamp,
                    "ttl": 60,
                },
            )
        elif "/station_information.json" in str(request.url):
            return httpx.Response(200, json=station_info_response)
        else:
            return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as httpx_client:
        logger = MockLogger()
        client = CitiBikeClient(httpx_client, logger)

        # Initialize timezone
        client.timezone, _ = await client._get_system_info()

        # Test the update method directly
        wait_time = await client._update_station_info()

        # Verify wait time calculation (should be ttl/2 = 300/2 = 150 seconds)
        assert isinstance(wait_time, timedelta)
        assert wait_time.total_seconds() == 150.0

        # Verify data was stored in client
        assert len(client.station_info) == 1
        assert client.station_info[0].station_id == "test_station"
        assert client.station_info[0].lat == 37.7749
        assert client.station_info[0].lon == -122.4194


@pytest.mark.asyncio
async def test_update_station_status():
    """Test _update_station_status method directly"""

    now_timestamp = int(datetime.now(timezone.utc).timestamp())

    station_status_response = {
        "data": {
            "stations": [
                {
                    "station_id": "test_station",
                    "vehicle_types_available": [
                        {"vehicle_type_id": "1", "count": 7},  # regular bikes
                        {"vehicle_type_id": "2", "count": 4},  # ebikes
                        {
                            "vehicle_type_id": "3",
                            "count": 2,
                        },  # scooters (should be ignored)
                    ],
                }
            ]
        },
        "last_updated": now_timestamp,
        "ttl": 60,
    }

    def mock_handler(request: httpx.Request):
        if "/system_information.json" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": {"timezone": "America/Los_Angeles"},
                    "version": "2.3",
                    "last_updated": now_timestamp,
                    "ttl": 60,
                },
            )
        elif "/station_status.json" in str(request.url):
            return httpx.Response(200, json=station_status_response)
        else:
            return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as httpx_client:
        logger = MockLogger()
        client = CitiBikeClient(httpx_client, logger)

        # Initialize timezone
        client.timezone, _ = await client._get_system_info()

        # Test the update method directly
        wait_time = await client._update_station_status()

        # Verify wait time calculation (should be ttl/2 = 60/2 = 30 seconds)
        assert isinstance(wait_time, timedelta)
        assert wait_time.total_seconds() == 30.0

        # Verify data was stored in client
        assert len(client.station_status) == 1
        assert client.station_status[0].station_id == "test_station"
        assert client.station_status[0].num_bikes == 7  # Only vehicle_type_id="1"
        assert client.station_status[0].num_ebikes == 4  # Only vehicle_type_id="2"


@pytest.mark.asyncio
async def test_get_system_info():
    """Test _get_system_info method directly"""

    now_timestamp = int(datetime.now(timezone.utc).timestamp())

    system_info_response = {
        "data": {"timezone": "America/New_York"},
        "version": "2.3",
        "last_updated": now_timestamp,
        "ttl": 60,
    }

    def mock_handler(request: httpx.Request):
        if "/system_information.json" in str(request.url):
            return httpx.Response(200, json=system_info_response)
        else:
            return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as httpx_client:
        logger = MockLogger()
        client = CitiBikeClient(httpx_client, logger)

        # Test the method
        timezone_info, version = await client._get_system_info()

        # Verify results
        assert str(timezone_info) == "America/New_York"
        assert version == 2.3


@pytest.mark.asyncio
async def test_citi_bike_client_with_fixtures():
    """Test CitiBikeClient with real fixture data"""
    import json
    from pathlib import Path

    # Load fixture files
    fixture_dir = Path(__file__).parent / "fixtures"

    with open(fixture_dir / "system_information.json") as f:
        system_info = json.load(f)

    with open(fixture_dir / "station_information.json") as f:
        station_info = json.load(f)

    with open(fixture_dir / "station_status.json") as f:
        station_status = json.load(f)

    def mock_handler(request: httpx.Request):
        if "/system_information.json" in str(request.url):
            return httpx.Response(200, json=system_info)
        elif "/station_information.json" in str(request.url):
            return httpx.Response(200, json=station_info)
        elif "/station_status.json" in str(request.url):
            return httpx.Response(200, json=station_status)
        else:
            return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as httpx_client:
        logger = MockLogger()

        async with CitiBikeClient(httpx_client, logger) as client:
            client._error_wait_seconds = 0.01

            # Get stations using real fixture data
            stations = await client.get_stations()

            # Verify we got a reasonable number of stations
            assert len(stations) > 0
            print(f"Found {len(stations)} stations from fixture data")

            # Verify all stations have proper structure and NYC coordinates
            for i, station in enumerate(stations):
                assert hasattr(station, "lat"), f"Station {i} missing lat"
                assert hasattr(station, "lon"), f"Station {i} missing lon"
                assert hasattr(station, "num_bikes"), f"Station {i} missing num_bikes"
                assert hasattr(station, "num_ebikes"), f"Station {i} missing num_ebikes"

                # Verify coordinates are in NYC range
                assert 40.0 < station.lat < 41.0, (
                    f"Station {i} lat {station.lat} not in NYC range"
                )
                assert -75.0 < station.lon < -73.0, (
                    f"Station {i} lon {station.lon} not in NYC range"
                )

                # Verify bike counts are non-negative
                assert station.num_bikes >= 0, (
                    f"Station {i} has negative bikes: {station.num_bikes}"
                )
                assert station.num_ebikes >= 0, (
                    f"Station {i} has negative ebikes: {station.num_ebikes}"
                )
