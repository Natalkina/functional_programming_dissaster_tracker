import httpx
from app.core.config import settings

async def fetch_nasa_events():
    async with httpx.AsyncClient() as client:
        response = await client.get(settings.NASA_EONET_API)
        response.raise_for_status()
        return response.json().get("events", [])

async def fetch_nasa_events_by_date(start_date: str, end_date: str = None):
    url = f"{settings.NASA_EONET_API}?start={start_date}"
    if end_date:
        url += f"&end={end_date}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json().get("events", [])