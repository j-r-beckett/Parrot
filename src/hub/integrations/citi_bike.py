import asyncio
import httpx
from pydantic import BaseModel
from typing import List, Callable, Awaitable, Tuple, Self, Literal
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dataclasses import dataclass

from rw_lock import RWLock


class Station(BaseModel):
    lat: float
    lon: float
    num_bikes: int  # non-ebikes
    num_ebikes: int


@dataclass
class StationInfo:
    station_id: str
    lat: float
    lon: float


@dataclass
class StationStatus:
    station_id: str
    num_bikes: int
    num_ebikes: int


class CitiBikeClient:
    api_version = 2.3

    def __init__(self, httpx_client: httpx.AsyncClient, system_logger):
        self.httpx_client = httpx_client
        self.system_logger = system_logger
        self.station_status: List[StationStatus]
        self.station_info: List[StationInfo]
        self.status_rw_lock = RWLock()
        self.info_rw_lock = RWLock()
        self._error_wait_seconds = 60

    @staticmethod
    def create_httpx_client(region: Literal["bkn", "bay"] = "bkn"):
        return httpx.AsyncClient(
            base_url=f"https://gbfs.lyft.com/gbfs/{CitiBikeClient.api_version}/{region}/en",
            timeout=10.0,
            follow_redirects=True,
        )

    async def __aenter__(self) -> Self:
        self.timezone, version = await self._get_system_info()

        if version != CitiBikeClient.api_version:
            raise ValueError(
                f"API version mismatch: expected {CitiBikeClient.api_version}, got {version}"
            )

        self.station_status, _ = await self._update_station_status()
        self.station_info, _ = await self._update_station_info()

        self.status_sync_task = asyncio.create_task(
            self._sync(self._update_station_status)
        )
        self.info_sync_task = asyncio.create_task(self._sync(self._update_station_info))

        return self

    def _next_update_time(self, last_updated: int, ttl: int) -> datetime:
        """Convert unix timestamp and ttl to next update time in UTC"""
        last_updated_dt = datetime.fromtimestamp(
            last_updated, tz=self.timezone
        ).astimezone(timezone.utc)
        return last_updated_dt + timedelta(seconds=ttl)

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.status_sync_task.cancel()
        try:
            await self.status_sync_task
        except asyncio.CancelledError:
            pass

        self.info_sync_task.cancel()
        try:
            await self.info_sync_task
        except asyncio.CancelledError:
            pass

    async def _sync(
        self,
        updater: Callable[
            [], Awaitable[Tuple[List[StationInfo] | List[StationStatus], datetime]]
        ],
    ) -> None:
        while True:
            try:
                _, next_update_time = await updater()
                wait_for = next_update_time - datetime.now(timezone.utc)
                # TODO: emit a log message saying we updated
                if wait_for > timedelta():
                    await asyncio.sleep(wait_for.total_seconds())
                else:
                    # Next update time is in the past - something is wrong
                    self.system_logger.error(
                        f"Next update time is in the past by {abs(wait_for.total_seconds())} seconds"
                    )
                    await asyncio.sleep(self._error_wait_seconds)
            except asyncio.CancelledError:
                # Task was cancelled, exit the loop
                break
            except Exception as e:
                self.system_logger.error(f"Sync failed: {e}")
                try:
                    await asyncio.sleep(self._error_wait_seconds)
                except asyncio.CancelledError:
                    break

    async def _update_station_info(self) -> Tuple[List[StationInfo], datetime]:
        response = await self.httpx_client.get("/station_information.json")
        response.raise_for_status()
        data = response.json()

        stations = [
            StationInfo(
                station_id=station["station_id"], lat=station["lat"], lon=station["lon"]
            )
            for station in data["data"]["stations"]
        ]

        next_update_time = self._next_update_time(data["last_updated"], data["ttl"])

        async with self.info_rw_lock.w_locked():
            self.station_info = stations

        return stations, next_update_time

    async def _update_station_status(self) -> Tuple[List[StationStatus], datetime]:
        response = await self.httpx_client.get("/station_status.json")
        response.raise_for_status()
        data = response.json()

        stations = []
        for station_data in data["data"]["stations"]:
            # Extract bike counts from vehicle_types_available
            num_bikes = 0  # regular bikes (vehicle_type_id="1")
            num_ebikes = 0  # ebikes (vehicle_type_id="2")

            for vehicle in station_data.get("vehicle_types_available", []):
                if vehicle["vehicle_type_id"] == "1":
                    num_bikes = vehicle["count"]
                elif vehicle["vehicle_type_id"] == "2":
                    num_ebikes = vehicle["count"]

            stations.append(
                StationStatus(
                    station_id=station_data["station_id"],
                    num_bikes=num_bikes,
                    num_ebikes=num_ebikes,
                )
            )

        next_update_time = self._next_update_time(data["last_updated"], data["ttl"])

        async with self.status_rw_lock.w_locked():
            self.station_status = stations

        return stations, next_update_time

    async def get_stations(self) -> List[Station]:
        # Acquire status_rw_lock reader lock and create status dict
        async with self.status_rw_lock.r_locked():
            status_dict = {
                status.station_id: (status.num_bikes, status.num_ebikes)
                for status in self.station_status
            }

        # Acquire info_rw_lock reader lock and create info dict
        async with self.info_rw_lock.r_locked():
            info_dict = {
                info.station_id: (info.lat, info.lon) for info in self.station_info
            }

        # Create Station objects by combining info and status data
        result = []
        for station_id, (lat, lon) in info_dict.items():
            if station_id in status_dict:
                num_bikes, num_ebikes = status_dict[station_id]
                result.append(
                    Station(
                        lat=lat, lon=lon, num_bikes=num_bikes, num_ebikes=num_ebikes
                    )
                )
            else:
                self.system_logger.error(
                    f"Station {station_id} found in info but not in status"
                )

        return result

    async def _get_system_info(self) -> Tuple[ZoneInfo, float]:
        response = await self.httpx_client.get("/system_information.json")
        response.raise_for_status()
        data = response.json()

        timezone_str = data["data"]["timezone"]
        timezone_info = ZoneInfo(timezone_str)
        version = float(data["version"])

        return timezone_info, version
