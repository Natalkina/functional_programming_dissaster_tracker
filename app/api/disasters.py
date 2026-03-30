import logging
import reverse_geocode
from functools import partial
from fastapi import APIRouter, HTTPException, Query

from app.services import nasa_client
from app.services.fp_core import Ok, Err
from app.services.domain import Coord
from app.services.functional_streams import (
    process_disaster_stream,
    calculate_hotspots,
    enrich_hotspot_city,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/disasters", tags=["disasters"])


# serialize event list — called at response boundary
def make_events_response(xs: list) -> dict:
    return {"events": [e.to_dict() for e in xs], "count": len(xs)}


# unwrap Result or raise 502 — centralizes the io→http error translation
def unwrap_or_502(result, context: str):
    match result:
        case Err(error=err):
            logger.error("%s: %s", context, err)
            raise HTTPException(status_code=502, detail=err)
        case Ok(value=v):
            return v


@router.get("/events")
async def get_all_disasters():
    result = await nasa_client.fetch_nasa_events()
    xs = unwrap_or_502(result, "fetch disasters failed")
    return make_events_response(xs)


@router.get("/events/by-date", description="Dates must be in ISO format, e.g. 2026-04-01. end_date is optional.")
async def get_disasters_by_date(
    start_date: str = Query(..., description="ISO date, e.g. 2026-04-01"),
    end_date: str = Query(None, description="ISO date, e.g. 2026-05-01"),
):
    result = await nasa_client.fetch_nasa_events(start_date=start_date, end_date=end_date)
    xs = unwrap_or_502(result, "fetch by date failed")
    return make_events_response(xs)


@router.get("/events/by-location")
async def get_disasters_near_location(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = Query(100),
):
    result = await nasa_client.fetch_nasa_events()
    xs = unwrap_or_502(result, "fetch for location filter failed")
    # aiostream pipeline: enrich + filter by proximity
    nearby = await process_disaster_stream(xs, user_loc=Coord(lat=lat, lon=lon), radius_km=radius_km)
    return make_events_response(nearby)


@router.get("/hotspots")
async def get_disaster_hotspots(limit: int = Query(10)):
    result = await nasa_client.fetch_nasa_events()
    xs = unwrap_or_502(result, "fetch for hotspots failed")
    top = calculate_hotspots(xs, grid_size=1.0)[:limit]
    # io boundary: geocode enrichment via partial application
    enriched = list(map(partial(enrich_hotspot_city, geocode_fn=reverse_geocode.search), top))
    return {"hotspots": [h.to_dict() for h in enriched]}
