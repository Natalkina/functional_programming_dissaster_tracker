from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List
from functools import reduce
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import CalendarEvent, User
from app.services.calendar_service import get_disaster_warnings_for_events
from app.services.functional_streams import calculate_hotspots
from app.services import nasa_client
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

router = APIRouter(prefix="/calendar", tags=["calendar"])

class CalendarEventCreate(BaseModel):
    title: str
    location: str
    date: str
    user_id: int

class DisasterWarning(BaseModel):
    event_title: str
    event_location: str
    event_date: str
    disaster_type: str
    distance_km: float
    warning_level: str

@router.post("/events")
async def add_event(event: CalendarEventCreate, db: Session = Depends(get_db)):
    new_event = CalendarEvent(
        user_id=event.user_id,
        title=event.title,
        location=event.location,
        date=event.date
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return {"message": "Event added", "event_id": new_event.id}

@router.get("/events")
async def get_events(user_id: int = Query(...), date: str = Query(None), db: Session = Depends(get_db)):
    query = db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id)
    if date:
        query = query.filter(CalendarEvent.date == date)
    events = query.all()
    return {"events": [{"id": e.id, "title": e.title, "location": e.location, "date": e.date} for e in events], "count": len(events)}

@router.get("/check-disasters", response_model=List[DisasterWarning])
async def check_disasters_for_events(user_id: int, start_date: str, end_date: str = None, db: Session = Depends(get_db)):
    events = db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id).all()
    user_events = [{"title": e.title, "location": e.location, "date": e.date} for e in events]
    warnings = await get_disaster_warnings_for_events(user_events, start_date, end_date)
    return warnings

@router.post("/notify-warnings")
async def send_warnings(user_id: int, start_date: str, end_date: str = None, db: Session = Depends(get_db)):
    warnings = await check_disasters_for_events(user_id, start_date, end_date, db)
    
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
