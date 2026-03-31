import logging
from aiostream import stream
from geopy.distance import geodesic
from itertools import chain
from collections import Counter
from typing import List, Tuple


from app.core.fp_core import Ok, Err, Result
from app.core.domain import Coord, DisasterEvent, ProximityEvent, Hotspot

logger = logging.getLogger(__name__)


# total function: catches ValueError from malformed coords so callers never see an exception
def calculate_distance(a: Coord, b: Coord) -> Result:
    """
    lat ∈ [-90, 90]; lon ∈ [-180, 180]
    """
    # i've understood that we can actually catch exception, but we can't raise them
    # it is better to use pattern matching tho
    try:
        return Ok(geodesic((a.lat, a.lon), (b.lat, b.lon)).km)
    except ValueError as exc:
        return Err(str(exc))


# declarative threshold mapping — evaluated top-down, first match wins
_WARNING_THRESHOLDS = ((50, "HIGH"), (100, "MEDIUM"))


def classify_warning_level(distance: float) -> str:
    """
    because warning thresholds are constant, this one is pure!
    """
    return next(
        (level for threshold, level in _WARNING_THRESHOLDS if distance < threshold),
        "LOW"
    )


# find the closest disaster coordinate to the user and wrap as ProximityEvent
# calculate_distance returns Result; filter Ok values, discard Err (bad coords)
def enrich_distance(event: DisasterEvent, user_loc: Coord) -> ProximityEvent:
    xs = event.coordinates()
    ok_distances = tuple(r.value for r in (calculate_distance(user_loc, c) for c in xs) if isinstance(r, Ok))
    min_d = min(ok_distances, default=None)
    d = round(min_d, 2) if min_d is not None else None
    return ProximityEvent(event=event, distance_km=d)


# attach warning level based on distance — returns new ProximityEvent (immutable)
def enrich_warning(pe: ProximityEvent) -> ProximityEvent:
    lvl = classify_warning_level(pe.distance_km) if pe.distance_km is not None else None
    return ProximityEvent(event=pe.event, distance_km=pe.distance_km, warning_level=lvl)


# snap coordinate to grid cell for aggregation
def snap_to_grid(c: Coord, grid_size: float) -> Coord:
    return Coord(
        lat=round(c.lat / grid_size) * grid_size,
        lon=round(c.lon / grid_size) * grid_size,
    )


# io boundary: reverse geocode a point — caller must inject geocode_fn explicitly
def get_city(c: Coord, geocode_fn) -> Tuple[str, str]:
    result = geocode_fn([(c.lat, c.lon)])[0]
    return result.get("city", "Unknown"), result.get("country", "Unknown")

# io-dependent: calls get_city which performs disk/network io via geocode_fn
def enrich_hotspot_city(h: Hotspot, geocode_fn) -> Hotspot:
    city, country = get_city(h.coord, geocode_fn=geocode_fn)
    return Hotspot(coord=h.coord, count=h.count, city=city, country=country)


async def process_disaster_stream(
    xs: List[DisasterEvent],
    user_loc: Coord,
    radius_km: float = 100,
) -> Tuple[ProximityEvent, ...]:
    """
    async because aiostream pipeline terminators (stream.list) return coroutines — must be awaited.
    other functions are sync pure transforms; this one owns the aiostream execution boundary.
    pipeline: enrich events with distance/warning, keep only those within radius
    """
    s = stream.iterate(xs)
    enriched = stream.map(s, lambda e: enrich_distance(e, user_loc))
    with_warning = stream.map(enriched, enrich_warning)
    filtered = stream.filter(
        with_warning,
        lambda pe: pe.distance_km is not None and pe.distance_km <= radius_km
    )
    # stream.list materializes the aiostream pipeline into a list; wrap in tuple for immutability
    return tuple(await stream.list(filtered))

# aggregate all event coordinates into grid cells, count per cell
def calculate_hotspots(xs: List[DisasterEvent], grid_size: float = 1.0) -> Tuple[Hotspot, ...]:
    all_points = chain.from_iterable(e.coordinates() for e in xs)
    counts = Counter(snap_to_grid(c, grid_size) for c in all_points)
    return tuple(sorted(
        [Hotspot(coord=c, count=n) for c, n in counts.items()],
        key=lambda h: h.count,
        reverse=True,
    ))
