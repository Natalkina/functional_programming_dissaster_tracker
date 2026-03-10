from fastapi import APIRouter, HTTPException, Query
from app.services import nasa_client
from app.services.functional_streams import process_disaster_stream, calculate_hotspots
from app.core.config import settings

router = APIRouter(prefix="/disasters", tags=["disasters"])

@router.get("/events")
async def get_all_disasters():
    try:
        events = await nasa_client.fetch_nasa_events()
        return {"nasa": events}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/events/by-date")
async def get_disasters_by_date(
    start_date: str = Query(...),
    end_date: str = Query(None)
):
    try:
        events = await nasa_client.fetch_nasa_events_by_date(start_date, end_date)
        return {"events": events, "count": len(events)}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/events/by-location")
async def get_disasters_near_location(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = Query(100)
):
    try:
        events = await process_disaster_stream(
            settings.NASA_EONET_API,
            user_location=(lat, lon),
            radius_km=radius_km
        )
        return {"events": events, "count": len(events)}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/hotspots")
async def get_disaster_hotspots(limit: int = Query(10)):
    try:
        events = await nasa_client.fetch_nasa_events()
        hotspots = await calculate_hotspots(events, grid_size=1.0)
        return {"hotspots": hotspots[:limit]}
    except Exception as e:
        raise HTTPException(500, str(e))