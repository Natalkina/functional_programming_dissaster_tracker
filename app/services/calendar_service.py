import itertools
from typing import Optional, Tuple
from geopy.geocoders import Nominatim

from app.services import nasa_client
from app.core.fp_core import Err
from app.core.domain import Coord, DisasterEvent, DisasterWarning
from app.core.functional_streams import enrich_distance, enrich_warning


# pure: check if event falls within date range
def is_event_in_range(event: dict, start: str, end: Optional[str]) -> bool:
    return start <= event["date"] <= (end or start)


# pure: pair user event with disaster, compute proximity warning
def build_warning(pair: Tuple[dict, DisasterEvent], radius_km: float) -> Optional[DisasterWarning]:
    user_event, disaster = pair

    if not user_event.get("coords"):
        return None

    pe = enrich_warning(enrich_distance(disaster, user_event["coords"]))

    if pe.distance_km is None or pe.distance_km > radius_km:
        return None

    return DisasterWarning(
        event_title=user_event["title"],
        event_location=user_event["location"],
        event_date=user_event["date"],
        disaster_type=disaster.title or "Unknown",
        distance_km=pe.distance_km,
        warning_level=pe.warning_level,
    )


# io boundary: forward geocoding (text → coords)
def geocode_event(event: dict, geolocator: Nominatim) -> dict:
    try:
        geo = geolocator.geocode(event["location"])
        coords = Coord(lat=geo.latitude, lon=geo.longitude) if geo else None
    except Exception:
        coords = None
    return {**event, "coords": coords}


# io boundary: fetch disasters → geocode events → compute proximity warnings
def get_disaster_warnings_for_events(
    user_events: tuple[dict, ...],
    start_date: str,
    end_date: Optional[str] = None,
    radius_km: float = 100.0,
) -> tuple[DisasterWarning, ...]:
    geolocator = Nominatim(user_agent="disaster_tracker")
    result = nasa_client.fetch_nasa_events(start_date, end_date)
    if isinstance(result, Err):
        return ()
    disasters = result.value

    # geocoding is an io side-effect; isolated here at the pipeline boundary
    valid_events = tuple(map(
        lambda e: geocode_event(e, geolocator),
        filter(lambda e: is_event_in_range(e, start_date, end_date), user_events),
    ))

    pairs = itertools.product(valid_events, disasters)
    return tuple(filter(None, map(lambda p: build_warning(p, radius_km), pairs)))
