import logging
import reverse_geocode
from functools import partial
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.services import nasa_client
from app.core.fp_core import Err
from app.core.domain import Coord
from app.core.functional_streams import (
    process_disaster_stream,
    calculate_hotspots,
    enrich_hotspot_city,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/disasters", tags=["disasters"])


# serialize event list — called at response boundary
def make_events_response(xs) -> JSONResponse:
    return JSONResponse(content={"events": [e.to_dict() for e in xs], "count": len(xs)})


# TODO: add memoization and lazy evaluation (return by batches of 10 maybe?)
@router.get("/events")
def get_all_disasters() -> JSONResponse:
    result = nasa_client.fetch_nasa_events()
    if isinstance(result, Err):
        logger.error("fetch disasters failed: %s", result.error)
        return JSONResponse(status_code=502, content={"detail": result.error})
    return make_events_response(result.value)


@router.get("/events/by-date", description="Dates must be in ISO format, e.g. 2026-04-01. end_date is optional.")
def get_disasters_by_date(
    start_date: str = Query(..., description="ISO date, e.g. 2026-04-01"),
    end_date: str = Query(None, description="ISO date, e.g. 2026-05-01"),
) -> JSONResponse:
    result = nasa_client.fetch_nasa_events(start_date=start_date, end_date=end_date)
    if isinstance(result, Err):
        logger.error("fetch by date failed: %s", result.error)
        return JSONResponse(status_code=502, content={"detail": result.error})
    return make_events_response(result.value)


@router.get("/events/by-location")
def get_disasters_near_location(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = Query(100),
) -> JSONResponse:
    result = nasa_client.fetch_nasa_events()
    if isinstance(result, Err):
        logger.error("fetch for location filter failed: %s", result.error)
        return JSONResponse(status_code=502, content={"detail": result.error})
    nearby = process_disaster_stream(result.value, user_loc=Coord(lat=lat, lon=lon), radius_km=radius_km)
    return make_events_response(nearby)


@router.get("/hotspots")
def get_disaster_hotspots(limit: int = Query(10)) -> JSONResponse:
    result = nasa_client.fetch_nasa_events()
    if isinstance(result, Err):
        logger.error("fetch for hotspots failed: %s", result.error)
        return JSONResponse(status_code=502, content={"detail": result.error})
    top = calculate_hotspots(result.value, grid_size=1.0)[:limit]
    # io boundary: geocode enrichment via partial application
    enriched = tuple(map(partial(enrich_hotspot_city, geocode_fn=reverse_geocode.search), top))
    return JSONResponse(content={"hotspots": [h.to_dict() for h in enriched]})
