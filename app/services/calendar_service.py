import itertools
from typing import List, Optional, Tuple
from geopy.geocoders import Nominatim

from app.services import nasa_client
from app.services.functional_streams import enrich_event_with_distance


# transformers

def is_event_in_range(event: dict, start: str, end: Optional[str]) -> bool:
    return start <= event["date"] <= (end or start)


def build_warning(pair: Tuple[dict, dict], radius_km: float) -> Optional[dict]:
    user_event, disaster = pair

    if not user_event.get("coords"):
        return None

    enriched = enrich_event_with_distance(disaster, user_event["coords"])

    if not enriched.get("distance_km") or enriched["distance_km"] > radius_km:
        return None

    return {
        "event_title": user_event["title"],
        "event_location": user_event["location"],
        "event_date": user_event["date"],
        "disaster_type": disaster.get("title", "Unknown"),
        "distance_km": enriched["distance_km"],
        "warning_level": enriched["warning_level"],
    }


# forward geocoding (text → coords)

def geocode_event(event: dict, geolocator: Nominatim) -> dict:
    try:
        geo = geolocator.geocode(event["location"])
        coords = (geo.latitude, geo.longitude) if geo else None
    except Exception:
        coords = None
    return {**event, "coords": coords}


# pipeline

async def get_disaster_warnings_for_events(
    user_events: List[dict],
    start_date: str,
    end_date: Optional[str] = None,
    radius_km: float = 100.0,
) -> List[dict]:
    geolocator = Nominatim(user_agent="disaster_tracker")
    disasters = await nasa_client.fetch_nasa_events(start_date, end_date)

    valid_events = list(map(
        lambda e: geocode_event(e, geolocator),
        filter(lambda e: is_event_in_range(e, start_date, end_date), user_events),
    ))

    pairs = itertools.product(valid_events, disasters)
    return list(filter(None, map(lambda p: build_warning(p, radius_km), pairs)))
