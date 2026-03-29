from __future__ import annotations

from typing import Any, Callable, Awaitable

from app.services.fp_core import Result, Ok, Err
from app.services.domain import CalendarEvent

GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
DEFAULT_CALENDAR_ID = "primary"

async def fetch_calendar_events_raw(
    http_get: Callable[[str, dict[str, str]], Awaitable[dict]],
    access_token: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    time_min_iso: str | None = None,
    time_max_iso: str | None = None,
    sync_token: str | None = None,
    max_results: int = 250,
) -> Result[dict[str, Any], str]:
    """io boundary: fetch raw calendar body, returns Result"""
    url = f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events"

    params: tuple[str, ...] = (
        f"maxResults={max_results}",
        "singleEvents=true",
        "orderBy=startTime",
    )

    if sync_token:
        params += (f"syncToken={sync_token}",)
    else:
        if time_min_iso:
            params += (f"timeMin={time_min_iso}",)
        if time_max_iso:
            params += (f"timeMax={time_max_iso}",)

    full_url = f"{url}?{'&'.join(params)}"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        body = await http_get(full_url, headers)
        return Ok(body)
    except Exception as exc:
        return Err(f"Google Calendar fetch failed: {exc}")


# ---------------------------------------------------------------------------
# Pure  —  normalize a single raw Google event into CalendarEvent
# ---------------------------------------------------------------------------

def normalize_google_event(raw: dict[str, Any]) -> CalendarEvent:
    """pure: raw google event dict -> typed CalendarEvent"""
    start_block = raw.get("start", {})
    end_block = raw.get("end", {})
    return CalendarEvent(
        id=raw.get("id", ""),
        title=raw.get("summary", "(no title)"),
        location=raw.get("location", ""),
        description=raw.get("description", ""),
        start_date=start_block.get("date") or start_block.get("dateTime", ""),
        end_date=end_block.get("date") or end_block.get("dateTime", ""),
        status=raw.get("status", "confirmed"),
        html_link=raw.get("htmlLink", ""),
    )


# ---------------------------------------------------------------------------
# Pure  —  normalize a sequence of raw events (functor over tuple)
# ---------------------------------------------------------------------------

def normalize_google_events(raw_events: tuple[dict[str, Any], ...]) -> tuple[CalendarEvent, ...]:
    """pure: map normalize_google_event over a sequence"""
    return tuple(map(normalize_google_event, raw_events))


# ---------------------------------------------------------------------------
# Pure  —  extract items + next sync token from raw body
# ---------------------------------------------------------------------------

def extract_items_and_sync_token(
    body: dict[str, Any],
) -> tuple[tuple[dict[str, Any], ...], str | None]:
    """pure: extract (items, nextSyncToken) from raw google response"""
    return tuple(body.get("items", [])), body.get("nextSyncToken")


# ---------------------------------------------------------------------------
# Pure  —  filter events that have a location string
# ---------------------------------------------------------------------------

def keep_events_with_location(xs: tuple[CalendarEvent, ...]) -> tuple[CalendarEvent, ...]:
    """pure: drop events without a location"""
    return tuple(filter(lambda e: bool(e.location), xs))


# ---------------------------------------------------------------------------
# Pure  —  filter events by date range
# ---------------------------------------------------------------------------

def filter_events_by_date(
    xs: tuple[CalendarEvent, ...],
    start_date: str,
    end_date: str | None = None,
) -> tuple[CalendarEvent, ...]:
    """pure: keep events whose start_date falls within [start_date, end_date]"""
    effective_end = end_date or start_date
    return tuple(filter(
        lambda e: start_date <= e.start_date[:10] <= effective_end,
        xs,
    ))


# ---------------------------------------------------------------------------
# Composed pipeline  —  raw body -> normalized CalendarEvents with location
# ---------------------------------------------------------------------------

def process_calendar_body(body: dict[str, Any]) -> tuple[CalendarEvent, ...]:
    """pure pipeline: extract items -> normalize -> keep with location"""
    items, _ = extract_items_and_sync_token(body)
    return keep_events_with_location(normalize_google_events(items))

