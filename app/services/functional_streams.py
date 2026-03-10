from aiostream import stream
from geopy.distance import geodesic
import httpx


def extract_coordinates(event):
    return [(g["coordinates"][1], g["coordinates"][0]) 
            for g in event.get("geometry", []) 
            if len(g.get("coordinates", [])) >= 2]

def calculate_distance(point1, point2):
    return geodesic(point1, point2).km

def classify_warning_level(distance):
    if distance < 50: return "HIGH"
    elif distance < 100: return "MEDIUM"
    return "LOW"

def enrich_event_with_distance(event, user_location):
    coords = extract_coordinates(event)
    if not coords:
        return {**event, "distance_km": None, "warning_level": None}
    
    distances = [calculate_distance(user_location, coord) for coord in coords]
    min_distance = min(distances)
    
    return {
        **event,
        "distance_km": round(min_distance, 2),
        "warning_level": classify_warning_level(min_distance)
    }

def filter_by_distance(radius):
    return lambda event: event.get("distance_km") is not None and event["distance_km"] <= radius

# Обробка потоків
async def process_disaster_stream(api_url, user_location=None, radius_km=100):
    xs = stream.iterate([])
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, timeout=10)
            if response.status_code == 200:
                events = response.json().get("events", [])
                xs = stream.iterate(events)
    except Exception as e:
        print(f"Error: {e}")
        return []
    
    if user_location:
        xs = stream.map(xs, lambda e: enrich_event_with_distance(e, user_location))
        xs = stream.filter(xs, filter_by_distance(radius_km))
    
    return await stream.list(xs)

async def calculate_hotspots(events, grid_size=1.0):
    def round_coord(coord, precision):
        return round(coord / precision) * precision
    
    grid_counts = {}
    for event in events:
        coords = extract_coordinates(event)
        for lat, lon in coords:
            key = f"{round_coord(lat, grid_size)},{round_coord(lon, grid_size)}"
            grid_counts[key] = grid_counts.get(key, 0) + 1
    
    return [
        {
            "location": key,
            "lat": float(key.split(",")[0]),
            "lon": float(key.split(",")[1]),
            "count": count
        }
        for key, count in sorted(grid_counts.items(), key=lambda x: x[1], reverse=True)
    ]
