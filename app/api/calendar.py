from fastapi import APIRouter, Query, Depends
from dataclasses import dataclass
from functools import reduce
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import CalendarEvent
from app.services.calendar_service import get_disaster_warnings_for_events
from app.core.domain import Coord, DisasterWarning
from app.core.functional_streams import calculate_hotspots, calculate_distance
from app.services import nasa_client
from geopy.geocoders import Nominatim

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
)
from app.repositories.token_repo import (
    save_user_tokens,
    get_user_tokens,
)
from app.core.fp_core import Ok, Err
import httpx
from fastapi.responses import RedirectResponse, JSONResponse


# pure: split scopes string into immutable sequence
_parse_scopes: callable = lambda s: tuple(s.split())


# io boundary: GET request returning Result; callers chain via map/flat_map
def _http_get_json(url: str, headers: dict[str, str]) -> Ok | Err:
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, headers=headers)
    except Exception as exc:
        return Err(f"network error: {exc}")
    if not resp.is_success:
        return Err(f"HTTP {resp.status_code}")
    return Ok(resp.json())


# io boundary: query user calendar events, project ORM objects to plain dicts.
# SQLAlchemy .all() returns a mutable list — converted to tuple here so
# downstream pure functions receive an immutable sequence.
def _fetch_user_events(db: Session, user_id: int) -> tuple[dict, ...]:
    return tuple(
        {"title": e.title, "location": e.location, "date": e.date}
        for e in db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id).all()
    )


router = APIRouter(prefix="/calendar", tags=["calendar"])

@router.get("/google/oauth/login")
def google_oauth_login(user_id: str = Query("anonymous")):
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
def google_oauth_callback(code: str = Query(...), state: str = Query(...)):
    """
    Google redirects here after user consent.
    Exchange code → tokens, store them, redirect to UI.
    """
    # 1. Validate state (CSRF)
    validation = validate_oauth_state(state, settings.OAUTH_STATE_SECRET)
    if not validation["ok"]:
        return JSONResponse(status_code=400, content={"detail": f"Invalid OAuth state: {validation['reason']}"})

    user_id = validation["user_id"]

    # 2. Exchange code for tokens (IO boundary).
    # flat_map chain inside exchange_code_for_tokens: post → normalize; Err propagates.
    token_result = exchange_code_for_tokens(
        http_post_form=post_form_httpx,
        code=code,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    if isinstance(token_result, Err):
        return JSONResponse(status_code=502, content={"detail": f"Token exchange failed: {token_result.error}"})
    tokens = token_result.value

    # 3. Store tokens (mutable boundary, isolated in repo)
    store_result = save_user_tokens(user_id, tokens)
    if isinstance(store_result, Err):
        return JSONResponse(status_code=500, content={"detail": store_result.error})

    # 4. Redirect back to frontend with success indicator
    return RedirectResponse(f"/?google_auth=ok&user_id={user_id}")


@router.get("/google/events")
def get_google_calendar_events(
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
        return JSONResponse(status_code=401, content={"detail": f"Not authenticated: {token_result.error}. Please connect Google Calendar first."})

    tokens = token_result.value

    # 2. Refresh if expired (IO boundary)
    if is_access_token_expired(tokens):
        refresh_tok = tokens.get("refresh_token")
        if not refresh_tok:
            return JSONResponse(status_code=401, content={"detail": "Access token expired and no refresh token available. Re-authenticate."})
        # flat_map chain: post → normalize → preserve refresh_token; Err propagates
        refresh_result = refresh_access_token(
            http_post_form=post_form_httpx,
            refresh_token=refresh_tok,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
        if isinstance(refresh_result, Err):
            return JSONResponse(status_code=502, content={"detail": f"Token refresh failed: {refresh_result.error}"})
        tokens = refresh_result.value
        save_user_tokens(user_id, tokens)

    # pure: convert date strings to RFC 3339 for Google API
    time_min_iso = f"{time_min}T00:00:00Z" if time_min else None
    time_max_iso = f"{time_max}T23:59:59Z" if time_max else None

    # 3. Fetch raw calendar data (IO boundary).
    # _http_get_json returns Result; fetch_calendar_events_raw passes it through.
    raw_result = fetch_calendar_events_raw(
        http_get=_http_get_json,
        access_token=tokens["access_token"],
        time_min_iso=time_min_iso,
        time_max_iso=time_max_iso,
    )
    if isinstance(raw_result, Err):
        return JSONResponse(status_code=502, content={"detail": raw_result.error})

    # 4. Pure pipeline: raw body → normalized CalendarEvents with location
    events = process_calendar_body(raw_result.value)
    return {"events": [e.to_dict() for e in events], "count": len(events), "user_id": user_id}


@router.get("/google/status")
def google_auth_status(user_id: str = Query("anonymous")):
    """Check whether a user has connected Google Calendar."""
    token_result = get_user_tokens(user_id)
    connected = isinstance(token_result, Ok)
    return {"connected": connected, "user_id": user_id}


@dataclass(frozen=True, slots=True)
class CalendarEventCreate:
    title: str
    location: str
    date: str
    user_id: int


@router.post("/events")
def add_event(event: CalendarEventCreate, db: Session = Depends(get_db)) -> dict[str, object]:
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


# db.query(...).all() returns a mutable list of ORM objects; immediately
# projected to immutable plain dicts at this io boundary — no further change needed.
@router.get("/events")
def get_events(user_id: int = Query(...), date: str = Query(None), db: Session = Depends(get_db)) -> dict[str, object]:
    query = db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id)
    if date:
        query = query.filter(CalendarEvent.date == date)
    events = query.all()
    return {"events": tuple({"id": e.id, "title": e.title, "location": e.location, "date": e.date} for e in events), "count": len(events)}


@router.get("/check-disasters", response_model=list[DisasterWarning])
def check_disasters_for_events(user_id: int, start_date: str, end_date: str = None, db: Session = Depends(get_db)):
    return get_disaster_warnings_for_events(_fetch_user_events(db, user_id), start_date, end_date)


@router.post("/notify-warnings")
def send_warnings(user_id: int, start_date: str, end_date: str = None, db: Session = Depends(get_db)) -> dict[str, object]:
    warnings = get_disaster_warnings_for_events(_fetch_user_events(db, user_id), start_date, end_date)

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
        "warnings": [w.to_dict() for w in warnings],
    }

@router.get("/hotspot-warnings")
def check_hotspot_warnings(location: str):
    result = nasa_client.fetch_nasa_events()
    if isinstance(result, Err):
        return JSONResponse(status_code=502, content={"detail": f"Failed to fetch disasters: {result.error}"})
    hotspots = calculate_hotspots(result.value, grid_size=1.0)

    geolocator = Nominatim(user_agent="disaster_tracker")
    geo = geolocator.geocode(location)
    if not geo:
        return JSONResponse(status_code=400, content={"detail": "Location not found"})

    user_loc = Coord(lat=geo.latitude, lon=geo.longitude)

    # compute distance once per hotspot via lazy generator; next() short-circuits
    candidates = (
        {"hotspot": h.to_dict(), "distance_km": round(calculate_distance(user_loc, h.coord), 2)}
        for h in hotspots[:20]
    )
    nearby = next((c for c in candidates if c["distance_km"] < 200), None)

    if nearby:
        return {
            "warning": True,
            "message": f"УВАГА! {location} знаходиться в небезпечній зоні!",
            "hotspot": nearby["hotspot"],
            "distance_km": nearby["distance_km"],
            "recommendation": "Це місце може бути небезпечним. Розгляньте інший напрямок подорожі.",
        }

    return {
        "warning": False,
        "message": f"{location} виглядає безпечно",
        "recommendation": "Приємної подорожі!",
    }
