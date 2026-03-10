from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List
from functools import reduce
from app.services.calendar_service import get_disaster_warnings_for_events
from app.services.functional_streams import calculate_hotspots
from app.services import nasa_client
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

router = APIRouter(prefix="/calendar", tags=["calendar"])

user_events = []

class CalendarEvent(BaseModel):
    title: str
    location: str
    date: str

class DisasterWarning(BaseModel):
    event_title: str
    event_location: str
    event_date: str
    disaster_type: str
    distance_km: float
    warning_level: str

@router.post("/events")
async def add_event(event: CalendarEvent):
    user_events.append(event.dict())
    return {"message": "Event added", "event": event}

@router.get("/events")
async def get_events(date: str = Query(None)):
    if date:
        filtered = [e for e in user_events if e["date"] == date]
        return {"events": filtered, "count": len(filtered)}
    return {"events": user_events, "count": len(user_events)}

@router.get("/check-disasters", response_model=List[DisasterWarning])
async def check_disasters_for_events(start_date: str, end_date: str = None):
    warnings = await get_disaster_warnings_for_events(user_events, start_date, end_date)
    return warnings

@router.post("/notify-warnings")
async def send_warnings(start_date: str, end_date: str = None):
    warnings = await check_disasters_for_events(start_date, end_date)
    
    if not warnings:
        return {"message": "Безпечно! Катастроф не знайдено", "warnings": []}

    count_by_level = reduce(
        lambda acc, w: {**acc, w.warning_level: acc.get(w.warning_level, 0) + 1},
        warnings,
        {}
    )
    
    return {
        "message": f"УВАГА! Знайдено {len(warnings)} попереджень",
        "high_risk": count_by_level.get("HIGH", 0),
        "medium_risk": count_by_level.get("MEDIUM", 0),
        "warnings": [w.dict() for w in warnings]
    }

@router.get("/hotspot-warnings")
async def check_hotspot_warnings(location: str):
    events = await nasa_client.fetch_nasa_events()
    hotspots = await calculate_hotspots(events, grid_size=5.0)
    
    geolocator = Nominatim(user_agent="disaster_tracker")
    geo = geolocator.geocode(location)
    
    if not geo:
        raise HTTPException(400, "Location not found")

    for hotspot in hotspots[:20]:
        distance = geodesic((geo.latitude, geo.longitude), (hotspot["lat"], hotspot["lon"])).km
        
        if distance < 200:
            return {
                "warning": True,
                "message": f"⚠️ УВАГА! {location} знаходиться в небезпечній зоні!",
                "hotspot": hotspot,
                "distance_km": round(distance, 2),
                "recommendation": "Це місце може бути небезпечним. Розгляньте інший напрямок подорожі."
            }
    
    return {
        "warning": False,
        "message": f"✅ {location} виглядає безпечно",
        "recommendation": "Приємної подорожі!"
    }
