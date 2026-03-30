import logging
import httpx
from typing import List, Dict, Any, Optional
from functools import reduce
from app.core.config import settings
from app.core.fp_core import Ok, Err, Result
from app.core.domain import DisasterEvent

logger = logging.getLogger(__name__)


# declarative url builder — accumulates only non-None params via reduce
def build_eonet_url(base_url: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    params = reduce(
        lambda acc, pair: {**acc, pair[0]: pair[1]} if pair[1] else acc,
        [("start", start_date), ("end", end_date)],
        {}
    )
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base_url}?{query}" if query else base_url


# wrap raw dicts in opaque domain type, freezing each on entry
def extract_events(data: Dict[str, Any]) -> List[DisasterEvent]:
    return [DisasterEvent.from_dict(e) for e in data.get("events", [])]


# io boundary: fetch raw json, convert http errors to Err
async def get_raw_data(client: httpx.AsyncClient, url: str) -> Result:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return Ok(response.json())
    except Exception as exc:
        logger.error("nasa eonet fetch failed: %s", exc)
        return Err(str(exc))


# io boundary: compose url → fetch → extract, threading Result via map
async def fetch_nasa_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Result:
    url = build_eonet_url(base_url or settings.NASA_EONET_API, start_date, end_date)
    async with httpx.AsyncClient(timeout=15) as client:
        result = await get_raw_data(client, url)
    # map lifts extract_events over Ok, passes Err through unchanged
    return result.map(extract_events)
