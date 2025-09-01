import httpx


async def geocode(client: httpx.AsyncClient, text: str) -> tuple[float, float]:
    """Geocode a text address to get coordinates"""
    response = await client.get(
        "/search",
        params={
            "q": text,
            "format": "json",
            "limit": 1,
        },
    )

    response.raise_for_status()

    results = response.json()

    if not results:
        raise ValueError(f"No geocoding results found for: {text}")

    result = results[0]

    return float(result["lat"]), float(result["lon"])
