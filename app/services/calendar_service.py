from geopy.geocoders import Nominatim
from app.services import nasa_client
from app.services.functional_streams import enrich_event_with_distance
from app.core.config import settings
from pydantic import BaseModel

geolocator = Nominatim(user_agent="disaster_tracker")

async def get_disaster_warnings_for_events(user_events, start_date, end_date=None):
    warnings = []
    disasters = await nasa_client.fetch_nasa_events_by_date(start_date, end_date)

    for event in user_events:
        if not (start_date <= event["date"] <= (end_date or start_date)):
            continue

        try:
            geo = geolocator.geocode(event["location"])
            if not geo:
                continue

            event_coords = (geo.latitude, geo.longitude)

            for disaster in disasters:
                enriched = enrich_event_with_distance(disaster, event_coords)

                if enriched.get("distance_km") and enriched["distance_km"] <= settings.DISASTER_RADIUS_KM:
                    warnings.append({
                        "event_title": event["title"],
                        "event_location": event["location"],
                        "event_date": event["date"],
                        "disaster_type": disaster.get("title", "Unknown"),
                        "distance_km": enriched["distance_km"],
                        "warning_level": enriched["warning_level"]
                    })
        except Exception as e:
            print(f"Error: {e}")
            continue

    class DisasterWarning(BaseModel):
        event_title: str
        event_location: str
        event_date: str
        disaster_type: str
        distance_km: float
        warning_level: str
    
    return [DisasterWarning(**w) for w in warnings]
