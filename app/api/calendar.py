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

# ── Google OAuth + Calendar events (functional pipeline) ─────────────
from app.core.config import settings
from app.api.calendar_oauth import (
    make_oauth_state,
    validate_oauth_state,
    build_google_oauth_url,
    exchange_code_for_tokens,
    refresh_access_token,
    is_access_token_expired,
    post_form_httpx,
)
from app.services.google_calendar_api import (
    fetch_calendar_events_raw,
    process_calendar_body,
    extract_items_and_sync_token,
)
from app.repositories.token_repo import (
    save_user_tokens,
    get_user_tokens,
)
from app.services.fp_core import Ok, Err
import httpx
from fastapi.responses import RedirectResponse


# ── Pure: split scopes string into list ──────────────────────────────
_parse_scopes = lambda s: s.split()


# ── IO boundary: httpx GET returning dict ────────────────────────────
async def _http_get_json(url: str, headers: dict[str, str]) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


router = APIRouter(prefix="/calendar", tags=["calendar"])

@router.get("/google/oauth/login")
async def google_oauth_login(user_id: str = Query("anonymous")):
    """
    Redirect the browser to Google's consent screen.
    """
    state = make_oauth_state(user_id, settings.OAUTH_STATE_SECRET)
    scopes = _parse_scopes(settings.GOOGLE_SCOPES)
    url = build_google_oauth_url(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        state=state,
        scopes=scopes,
    )
    return RedirectResponse(url)
@router.get("/google/oauth/callback")
async def google_oauth_callback(code: str = Query(...), state: str = Query(...)):
    """
    Google redirects here after user consent.
    Exchange code → tokens, store them, redirect to UI.
    """
    # 1. Validate state (CSRF)
    validation = validate_oauth_state(state, settings.OAUTH_STATE_SECRET)
    if not validation["ok"]:
        raise HTTPException(400, f"Invalid OAuth state: {validation['reason']}")

    user_id = validation["user_id"]

    # 2. Exchange code for tokens (IO boundary)
    try:
        tokens = await exchange_code_for_tokens(
            http_post_form=post_form_httpx,
            code=code,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
        )
    except Exception as exc:
        raise HTTPException(502, f"Token exchange failed: {exc}")

    # 3. Store tokens (mutable boundary, isolated in repo)
    result = save_user_tokens(user_id, tokens)
    if isinstance(result, Err):
        raise HTTPException(500, result.error)

    # 4. Redirect back to frontend with success indicator
    return RedirectResponse(f"/?google_auth=ok&user_id={user_id}")


@router.get("/google/events")
async def get_google_calendar_events(
    user_id: str = Query("anonymous"),
    time_min: str = Query(None, description="ISO date, e.g. 2026-03-15"),
    time_max: str = Query(None, description="ISO date, e.g. 2026-04-15"),
):
    """
    Fetch Google Calendar events for an authenticated user.
    Functional pipeline: get tokens → refresh if expired → fetch → process.
    """
    # 1. Retrieve stored tokens
    token_result = get_user_tokens(user_id)
    if isinstance(token_result, Err):
        raise HTTPException(401, f"Not authenticated: {token_result.error}. Please connect Google Calendar first.")

    tokens = token_result.value

    # 2. Refresh if expired (IO boundary)
    if is_access_token_expired(tokens):
        refresh_tok = tokens.get("refresh_token")
        if not refresh_tok:
            raise HTTPException(401, "Access token expired and no refresh token available. Re-authenticate.")
        try:
            tokens = await refresh_access_token(
                http_post_form=post_form_httpx,
                refresh_token=refresh_tok,
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
            )
            save_user_tokens(user_id, tokens)
        except Exception as exc:
            raise HTTPException(502, f"Token refresh failed: {exc}")

    # Pure: convert date strings to RFC 3339 for Google API
    time_min_iso = f"{time_min}T00:00:00Z" if time_min else None
    time_max_iso = f"{time_max}T23:59:59Z" if time_max else None

    # 3. Fetch raw calendar data (IO boundary)
    raw_result = await fetch_calendar_events_raw(
        http_get=_http_get_json,
        access_token=tokens["access_token"],
        time_min_iso=time_min_iso,
        time_max_iso=time_max_iso,
    )

    if isinstance(raw_result, Err):
        raise HTTPException(502, raw_result.error)

    # 4. Pure pipeline: raw body → normalized events with location
    events = process_calendar_body(raw_result.value)

    return {"events": events, "count": len(events), "user_id": user_id}



@router.get("/google/status")
async def google_auth_status(user_id: str = Query("anonymous")):
    """Check whether a user has connected Google Calendar."""
    token_result = get_user_tokens(user_id)
    connected = isinstance(token_result, Ok)
    return {"connected": connected, "user_id": user_id}

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
