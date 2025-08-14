import httpx
from config import AppSettings


class NominatimClient:
    def __init__(self, settings: AppSettings):
        self.client = None
        self.settings = settings

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url="https://nominatim.openstreetmap.org",
            headers={"User-Agent": "Clanker/1.0"},
            timeout=10.0,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def geocode(self, text: str) -> tuple[float, float]:
        """Geocode a text address to get coordinates"""
        response = await self.client.get(
            "/search",
            params={
                "q": text,
                "format": "json",
                "limit": 1,
            },
        )

        response.raise_for_status()

        result = response.json()[0]

        return float(result["lat"]), float(result["lon"])
