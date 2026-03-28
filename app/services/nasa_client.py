import httpx
from typing import List, Dict, Any, Optional
from functools import reduce
from app.core.config import settings
from app.services.fp_core import Ok, Err


# declarative URL builder
def build_eonet_url(base_url: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    params = reduce(
        lambda acc, pair: {**acc, pair[0]: pair[1]} if pair[1] else acc,
        [("start", start_date), ("end", end_date)],
        {}
    )
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base_url}?{query}" if query else base_url


# extract events from raw response
def extract_events(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return data.get("events", [])


# fetch raw data, returns result
async def get_raw_data(client: httpx.AsyncClient, url: str):
    try:
        response = await client.get(url)
        response.raise_for_status()
        return Ok(response.json())
    except Exception as e:
        return Err(str(e))


# сomposition pipeline
async def fetch_nasa_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    base_url: str = None,
) -> List[Dict[str, Any]]:
    url = build_eonet_url(base_url or settings.NASA_EONET_API, start_date, end_date)
    async with httpx.AsyncClient(timeout=15) as client:
        result = await get_raw_data(client, url)
    match result:
        case Ok(value=data):
            return extract_events(data)
        case Err():
            return []
