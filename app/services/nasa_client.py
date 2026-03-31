import logging
import httpx
from typing import List, Dict, Any, Optional, Tuple
from functools import reduce
from cachetools import TTLCache
from app.core.config import settings
from app.core.fp_core import Ok, Err, Result
from app.core.domain import DisasterEvent

logger = logging.getLogger(__name__)


# returns str: URLs are strings — httpx, logging, and redirects all consume str directly.
# a typed wrapper would need unwrapping at every call site with no added safety,
# since urls have no domain invariants worth enforcing at the type level.
# declarative url builder — accumulates only non-None params via reduce
def build_eonet_url(base_url: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    params = reduce(
        lambda acc, pair: {**acc, pair[0]: pair[1]} if pair[1] else acc,
        [("start", start_date), ("end", end_date)],
        {}
    )
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base_url}?{query}" if query else base_url

# wrap raw dicts in opaque domain type, freezing each on entry.
# data["events"] is a mutable list from the raw api response — we don't control it,
# but we consume it immediately via a generator, so mutability doesn't escape.
def extract_events(data: Dict[str, Any]) -> Tuple[DisasterEvent, ...]:
    return tuple(DisasterEvent.from_dict(e) for e in data.get("events", []))


# io boundary: fetch raw json, convert http errors to Err
def get_raw_data(client: httpx.Client, url: str) -> Result:
    try:
        resp = client.get(url)
    except Exception as exc:
        logger.error("nasa eonet fetch failed: %s", exc)
        return Err(str(exc))
    if not resp.is_success:
        logger.error("nasa eonet fetch failed: HTTP %s", resp.status_code)
        return Err(f"HTTP {resp.status_code}")
    return Ok(resp.json())


# keyed on (start_date, end_date); base_url excluded — always None in production.
# only Ok results are stored: transient network failures must not poison the cache.
# ttl=300 balances freshness vs. redundant nasa api calls across endpoints.
_events_cache: TTLCache = TTLCache(maxsize=32, ttl=300)


def fetch_nasa_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Result:
    """
    io boundary: build url → check cache → fetch → extract, threading Result via map.
    returns Ok(tuple[DisasterEvent, ...]) on success, Err(str) on network or http failure.
    cache hit short-circuits before any io; only Ok results are stored — transient
    failures fall through every time so the caller always gets a fresh retry on error.
    base_url is injectable for testing; defaults to NASA_EONET_API from config.
    """
    key = (start_date, end_date)
    if key in _events_cache:
        return _events_cache[key]
    url = build_eonet_url(base_url or settings.NASA_EONET_API, start_date, end_date)
    with httpx.Client(timeout=15) as client:
        result = get_raw_data(client, url)
    result = result.map(extract_events)
    if isinstance(result, Ok):
        _events_cache[key] = result
    return result
