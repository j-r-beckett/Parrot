import asyncio
import httpx
from pydantic import BaseModel
from typing import List, Callable, Awaitable, Tuple, Self
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


class Station(BaseModel):
    lat: float
    lon: float
    num_bikes: int
    num_ebikes: int


class StationStatusResponse(BaseModel):
    ...
    last_updated: datetime
    ttl: timedelta


class StationInfoResponse(BaseModel):
    ...
    last_updated: datetime
    ttl: timedelta


class CitiBikeClient:
    api_version = 2.3

    def __init__(self, httpx_client: httpx.AsyncClient, system_logger):
        self.httpx_client = httpx_client
        self.system_logger = system_logger
        self._station_status: StationStatusResponse
        self._station_info: StationInfoResponse

    @staticmethod
    def create_httpx_client():
        return httpx.AsyncClient(
            base_url=f"https://gbfs.lyft.com/gbfs/{CitiBikeClient.api_version}/bay/en",
            timeout=10.0,
            follow_redirects=True,
        )

    async def __aenter__(self) -> Self:
        self.timezone, version = await self._get_system_info()

        # If version != CitiBikeClient.api_version, raise an error

        # Use timezone when deserializing unix timestamps in citi bike responses to the utc datetimes we use internally

        self._station_status = await self._update_station_status()
        self._station_info = await self._update_station_info()

        self.status_sync_task = asyncio.create_task(
            self._sync(self._update_station_status)
        )
        self.info_sync_task = asyncio.create_task(self._sync(self._update_station_info))

        return self

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
        updater: Callable[[], Awaitable[StationInfoResponse | StationStatusResponse]],
    ) -> None:
        while True:
            updated = await updater()
            next_update_time = updated.last_updated + updated.ttl
            wait_for = next_update_time - datetime.now(timezone.utc)
            # TODO: emit a log message saying we updated
            if wait_for > timedelta():
                await asyncio.sleep(wait_for.total_seconds())

    async def _update_station_info(self) -> StationInfoResponse:
        # 1. Make get request to https://gbfs.lyft.com/gbfs/2.3/bay/en/station_information.json
        # 2. Deserialize
        # 3. Acquire info_rw_lock writer lock
        # 4. Update self._station_info
        # 5. Release lock
        pass

    async def _update_station_status(self) -> StationStatusResponse:
        # 1. Make get request to https://gbfs.lyft.com/gbfs/2.3/bay/en/station_status.json
        # 2. Deserialize
        # 3. Acquire status_rw_lock writer lock
        # 4. Update self._station_status
        # 5. Release lock
        pass

    async def get_stations(self) -> List[Station]:
        # 1. Acquire status_rw_lock reader lock
        # 2. Create a dict mapping station_id to (num_bikes, num_ebikes). Call this status_dict
        # 3. Release status_rw_lock
        # 4. Acquire info_rw_lock reader lock
        # 5. Create a dict mapping station_id to (lat, lon). Call this info_dict
        # 6. Release info_rw_lock
        # 7. For each station_id in info_dict, creating a Station and appending to a result list. If station_id is not found in status_dict, log an error with system_logger and carry on
        # 8. Return result list
        pass

    async def _get_system_info(self) -> Tuple[ZoneInfo, float]:
        # 1. Make a get request to https://gbfs.lyft.com/gbfs/2.3/bay/en/system_information.json
        # 2. Deserialize
        # 3. Extract response["data"]["timezone"], convert to ZoneInfo
        # 4. Extract response["version"], convert to float
        # 5. Return
        pass
