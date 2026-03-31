"""
opaque domain types — is represented as frozen, slotted dataclass

consumers interact through typed accessors, never through
raw dict keys. Internal dict is wrapped in MappingProxyType
to guarantee true immutability (frozen only prevents field
reassignment, not mutation of mutable containers inside).
serialization happens at the io boundary via to_dict()

I personally don't like these commentaries at the top, yet, they are not suitable
for any of the dataclass docstring;
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple
from types import MappingProxyType
from typing import Optional, Tuple


@dataclass(frozen=True, slots=True)
class Coord:
    """a geographic point, also used as dict key in hotspot aggregation"""
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class DisasterEvent:
    """wraps raw nasa eonet event — MappingProxyType prevents mutation"""
    _raw: MappingProxyType

    @classmethod
    def from_dict(cls, d: dict) -> DisasterEvent:
        """construct from mutable dict, freezing it on entry"""
        return cls(_raw=MappingProxyType(d))

    @property
    def id(self) -> str:
        return self._raw.get("id", "")

    @property
    def title(self) -> str:
        return self._raw.get("title", "")

    @property
    def description(self) -> Optional[str]:
        return self._raw.get("description")

    @property
    def link(self) -> str:
        return self._raw.get("link", "")

    @property
    def closed(self) -> Optional[str]:
        return self._raw.get("closed")

    # return tuples, not lists — callers cannot mutate the contents
    @property
    def categories(self) -> tuple:
        return tuple(self._raw.get("categories", []))

    @property
    def sources(self) -> tuple:
        return tuple(self._raw.get("sources", []))

    @property
    def geometry(self) -> tuple:
        return tuple(self._raw.get("geometry", []))

    # extract typed coordinates from geometry entries
    def coordinates(self) -> Tuple[Coord, ...]:
        return tuple(
            Coord(lat=g["coordinates"][1], lon=g["coordinates"][0])
            for g in self._raw.get("geometry", [])
            if len(g.get("coordinates", [])) >= 2
        )

    # return a copy — caller gets their own mutable dict, our data stays safe
    def to_dict(self) -> dict:
        return dict(self._raw)


@dataclass(frozen=True, slots=True)
class ProximityEvent:
    """disaster event enriched with distance and warning level"""
    event: DisasterEvent
    distance_km: Optional[float] = None
    warning_level: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            **self.event.to_dict(),
            "distance_km": self.distance_km,
            "warning_level": self.warning_level,
        }


@dataclass(frozen=True, slots=True)
class Hotspot:
    """grid-aggregated disaster concentration point"""
    coord: Coord
    count: int
    city: str = "Unknown"
    country: str = "Unknown"

    def to_dict(self) -> dict:
        return {
            "location": f"{self.coord.lat},{self.coord.lon}",
            "lat": self.coord.lat,
            "lon": self.coord.lon,
            "count": self.count,
            "city": self.city,
            "country": self.country,
        }


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """normalized google calendar event — all scalar fields, fully immutable"""
    id: str
    title: str
    location: str
    description: str
    start_date: str
    end_date: str
    status: str
    html_link: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "location": self.location,
            "description": self.description,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "status": self.status,
            "html_link": self.html_link,
        }


@dataclass(frozen=True, slots=True)
class DisasterWarning:
    """proximity alert pairing a user calendar event with a nearby disaster"""
    event_title: str
    event_location: str
    event_date: str
    disaster_type: str
    distance_km: float
    warning_level: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event_title": self.event_title,
            "event_location": self.event_location,
            "event_date": self.event_date,
            "disaster_type": self.disaster_type,
            "distance_km": self.distance_km,
            "warning_level": self.warning_level,
        }


# auth responses — NamedTuples are naturally immutable and unpackable
class RegisterResponse(NamedTuple):
    message: str
    user_id: int

class LoginResponse(NamedTuple):
    message: str
    email: str
    user_id: int
