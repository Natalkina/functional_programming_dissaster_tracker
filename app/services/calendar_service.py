import itertools
from typing import List, Optional, Tuple
from pydantic import BaseModel
from geopy.geocoders import Nominatim

from app.services import nasa_client
from app.services.functional_streams import enrich_event_with_distance
from app.core.config import settings


# --- Чисті трансформатори (Pure Transformers) ---

def is_event_in_range(event: dict, start: str, end: Optional[str]) -> bool:
    return start <= event["date"] <= (end or start)


def try_get_coords(event: dict, geolocator: Nominatim) -> dict:
    """Збагачує подію координатами, якщо це можливо."""
    try:
        geo = geolocator.geocode(event["location"])
        coords = (geo.latitude, geo.longitude) if geo else None
        return {**event, "coords": coords}
    except Exception:
        return {**event, "coords": None}


def build_warning_dto(pair: Tuple[dict, dict]) -> Optional[dict]:
    """Спроба створити попередження з пари (подія_користувача, катастрофа)."""
    user_event, disaster = pair

    if not user_event["coords"]:
        return None

    enriched = enrich_event_with_distance(disaster, user_event["coords"])

    # Фільтрація за радіусом прямо всередині мапера
    if not enriched.get("distance_km") or enriched["distance_km"] > settings.DISASTER_RADIUS_KM:
        return None

    return {
        "event_title": user_event["title"],
        "event_location": user_event["location"],
        "event_date": user_event["date"],
        "disaster_type": disaster.get("title", "Unknown"),
        "distance_km": enriched["distance_km"],
        "warning_level": enriched["warning_level"]
    }


# --- Основний сервіс ---

async def get_disaster_warnings_for_events(user_events, start_date, end_date=None):
    geolocator = Nominatim(user_agent="disaster_tracker")

    # 1. Отримуємо дані через функціональний клієнт
    disasters = await nasa_client.fetch_nasa_events(start_date, end_date)

    # 2. Pipeline: Фільтруємо за датою та додаємо координати
    valid_user_events = [
        try_get_coords(e, geolocator)
        for e in user_events
        if is_event_in_range(e, start_date, end_date)
    ]

    # 3. Створюємо декартовий добуток (кожна подія з кожною катастрофою)
    # Це замінює вкладений цикл for event in events: for disaster in disasters
    pairs = itertools.product(valid_user_events, disasters)

    # 4. Трансформуємо пари в DTO та відфільтровуємо None (ті, що не пройшли по радіусу або гео)
    raw_warnings = filter(None, map(build_warning_dto, pairs))

    # 5. Валідація через Pydantic
    class DisasterWarning(BaseModel):
        event_title: str
        event_location: str
        event_date: str
        disaster_type: str
        distance_km: float
        warning_level: str

    return [DisasterWarning(**w) for w in raw_warnings]
