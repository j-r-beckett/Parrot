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


async def reverse_geocode(client: httpx.AsyncClient, lat: float, lon: float) -> str:
    """Reverse geocode coordinates to get a human-readable address"""
    response = await client.get(
        "/reverse",
        params={
            "lat": lat,
            "lon": lon,
            "format": "json",
            "addressdetails": 1,
        },
    )

    response.raise_for_status()

    result = response.json()

    if not result:
        raise ValueError(f"No reverse geocoding results found for: {lat}, {lon}")

    return result.get("display_name", f"{lat}, {lon}")
