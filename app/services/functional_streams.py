import reverse_geocode
from aiostream import stream
from geopy.distance import geodesic
from itertools import chain
from collections import Counter
from typing import List, Tuple, Optional, Dict
from app.services import nasa_client


# helpers

def extract_coordinates(event: Dict) -> List[Tuple[float, float]]:
    return [
        (g["coordinates"][1], g["coordinates"][0])
        for g in event.get("geometry", [])
        if len(g.get("coordinates", [])) >= 2
    ]


def calculate_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return geodesic(p1, p2).km


# declarative mapping
_WARNING_THRESHOLDS = ((50, "HIGH"), (100, "MEDIUM"))

def classify_warning_level(distance: float) -> str:
    return next(
        (level for threshold, level in _WARNING_THRESHOLDS if distance < threshold),
        "LOW"
    )


def enrich_event_with_distance(event: Dict, user_location: Tuple[float, float]) -> Dict:
    coords = extract_coordinates(event)
    min_dist = min((calculate_distance(user_location, c) for c in coords), default=None)

    return {
        **event,
        "distance_km": round(min_dist, 2) if min_dist is not None else None,
        "warning_level": classify_warning_level(min_dist) if min_dist is not None else None,
    }


def snap_to_grid(lat: float, lon: float, grid_size: float) -> Tuple[float, float]:
    return (round(lat / grid_size) * grid_size, round(lon / grid_size) * grid_size)


def get_city(lat: float, lon: float, _geolocator=None) -> Tuple[str, str]:
    result = reverse_geocode.search([(lat, lon)])[0]
    return result.get("city", "Unknown"), result.get("country", "Unknown")


# stream pipeline

async def process_disaster_stream(
    api_url: str,
    user_location: Optional[Tuple[float, float]] = None,
    radius_km: float = 100,
) -> List[Dict]:
    events = await nasa_client.fetch_nasa_events(base_url=api_url)
    xs = stream.iterate(events)

    if user_location:
        enriched = stream.map(xs, lambda e: enrich_event_with_distance(e, user_location))
        filtered = stream.filter(enriched, lambda e: e["distance_km"] is not None and e["distance_km"] <= radius_km)
        return await stream.list(filtered)

    return await stream.list(xs)


# aggregation

def calculate_hotspots(events: List[Dict], grid_size: float = 1.0) -> List[Dict]:
    all_points = chain.from_iterable(extract_coordinates(e) for e in events)

    counts = Counter(snap_to_grid(lat, lon, grid_size) for lat, lon in all_points)

    return sorted(
        [
            {"location": f"{lat},{lon}", "lat": lat, "lon": lon, "count": count}
            for (lat, lon), count in counts.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )
