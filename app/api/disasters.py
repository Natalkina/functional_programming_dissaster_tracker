from fastapi import APIRouter, HTTPException, Query

from app.services import nasa_client
from app.services.functional_streams import process_disaster_stream, calculate_hotspots, get_city
from app.core.config import settings

router = APIRouter(prefix="/disasters", tags=["disasters"])


# helpers

def make_events_response(events: list) -> dict:
    return {"events": events, "count": len(events)}


def enrich_with_city(hotspot: dict) -> dict:
    city, country = get_city(hotspot["lat"], hotspot["lon"])
    return {**hotspot, "city": city, "country": country}


# routes

@router.get("/events")
async def get_all_disasters():
    events = await nasa_client.fetch_nasa_events()
    return make_events_response(events)


@router.get("/events/by-date")
async def get_disasters_by_date(
    start_date: str = Query(...),
    end_date: str = Query(None),
):
    events = await nasa_client.fetch_nasa_events(start_date=start_date, end_date=end_date)
    return make_events_response(events)


@router.get("/events/by-location")
async def get_disasters_near_location(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = Query(100),
):
    events = await process_disaster_stream(
        api_url=settings.NASA_EONET_API,
        user_location=(lat, lon),
        radius_km=radius_km,
    )
    return make_events_response(events)


@router.get("/hotspots")
async def get_disaster_hotspots(limit: int = Query(10)):
    events = await nasa_client.fetch_nasa_events()
    top_hotspots = calculate_hotspots(events, grid_size=1.0)[:limit]
    enriched = list(map(enrich_with_city, top_hotspots))
    return {"hotspots": enriched}
