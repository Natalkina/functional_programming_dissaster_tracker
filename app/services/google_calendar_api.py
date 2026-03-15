"""
Google Calendar API client — functional style.

IO functions return Result[T, str].
Pure transforms are plain functions over dicts / lists.
"""
from __future__ import annotations

from typing import Any, Callable, Awaitable

from app.services.fp_core import Result, Ok, Err

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"

DEFAULT_CALENDAR_ID = "primary"

# ---------------------------------------------------------------------------
# IO  —  fetch raw events from Google Calendar
# ---------------------------------------------------------------------------

async def fetch_calendar_events_raw(
    http_get: Callable[[str, dict[str, str]], Awaitable[dict]],
    access_token: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    time_min_iso: str | None = None,
    time_max_iso: str | None = None,
    sync_token: str | None = None,
    max_results: int = 250,
) -> Result[dict[str, Any], str]:
    """
    Fetch a page of events from Google Calendar API.
    Returns full JSON body wrapped in Result.

    *http_get* signature: async (url, headers) -> dict
    """
    url = f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events"

    params: list[str] = [
        f"maxResults={max_results}",
        "singleEvents=true",
        "orderBy=startTime",
    ]

    if sync_token:
        params.append(f"syncToken={sync_token}")
    else:
        if time_min_iso:
            params.append(f"timeMin={time_min_iso}")
        if time_max_iso:
            params.append(f"timeMax={time_max_iso}")

    full_url = f"{url}?{'&'.join(params)}"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        body = await http_get(full_url, headers)
        return Ok(body)
    except Exception as exc:
        return Err(f"Google Calendar fetch failed: {exc}")


# ---------------------------------------------------------------------------
# Pure  —  normalize a single Google event dict
# ---------------------------------------------------------------------------

def normalize_google_event(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Transform a raw Google Calendar event into a flat domain dict.
    Pure function — no side effects.
    """
    start_block = raw.get("start", {})
    end_block = raw.get("end", {})

    return {
        "id": raw.get("id", ""),
        "title": raw.get("summary", "(no title)"),
        "location": raw.get("location", ""),
        "description": raw.get("description", ""),
        "start_date": start_block.get("date") or start_block.get("dateTime", ""),
        "end_date": end_block.get("date") or end_block.get("dateTime", ""),
        "status": raw.get("status", "confirmed"),
        "html_link": raw.get("htmlLink", ""),
    }


# ---------------------------------------------------------------------------
# Pure  —  normalize a list of events (functor-style map)
# ---------------------------------------------------------------------------

def normalize_google_events(raw_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map normalize_google_event over a list (functor over list)."""
    return list(map(normalize_google_event, raw_events))


# ---------------------------------------------------------------------------
# Pure  —  extract items + next sync token from raw body
# ---------------------------------------------------------------------------

def extract_items_and_sync_token(
    body: dict[str, Any],
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Extract (items, nextSyncToken) from the raw Google response.
    Pure function.
    """
    items = body.get("items", [])
    next_sync_token = body.get("nextSyncToken")
    return items, next_sync_token


# ---------------------------------------------------------------------------
# Pure  —  filter events that have a location string
# ---------------------------------------------------------------------------

def keep_events_with_location(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only keep events where 'location' is non-empty."""
    return list(filter(lambda e: bool(e.get("location")), events))


# ---------------------------------------------------------------------------
# Pure  —  filter events by date range
# ---------------------------------------------------------------------------

def filter_events_by_date(
    events: list[dict[str, Any]],
    start_date: str,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Keep events whose start_date falls within [start_date .. end_date]."""
    effective_end = end_date or start_date
    return list(filter(
        lambda e: start_date <= (e.get("start_date", "") or "")[:10] <= effective_end,
        events,
    ))


# ---------------------------------------------------------------------------
# Composed pipeline  —  raw body -> normalized events with location
# ---------------------------------------------------------------------------

def process_calendar_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Pure pipeline: extract items → normalize → keep with location.
    Composition of three pure functions.
    """
    items, _ = extract_items_and_sync_token(body)
    normalized = normalize_google_events(items)
    with_location = keep_events_with_location(normalized)
    return with_location

