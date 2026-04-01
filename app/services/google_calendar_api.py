from __future__ import annotations

from typing import Any, Callable

from app.core.fp_core import Result
from app.core.domain import CalendarEvent

GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
DEFAULT_CALENDAR_ID = "primary"

def fetch_calendar_events_raw(
    http_get: Callable[[str, dict[str, str]], Result],
    access_token: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    time_min_iso: str | None = None,
    time_max_iso: str | None = None,
    sync_token: str | None = None,
    max_results: int = 250,
) -> Result:
    """io: fetch raw calendar body; delegates error handling to http_get Result"""
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

    return http_get(full_url, headers)


# pure: `raw` is a mutable dict but this function only reads it — never mutates it.
# purity is about behavior (same input → same output, no side effects), not about
# whether the parameter type is mutable. returns an immutable frozen CalendarEvent.
def normalize_google_event(raw: dict[str, Any]) -> CalendarEvent:
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


# pure: functor map over a sequence — applies a pure function to each element.
# the dicts inside the tuple are mutable, but normalize_google_event only reads them.
def normalize_google_events(raw_events: tuple[dict[str, Any], ...]) -> tuple[CalendarEvent, ...]:
    return tuple(map(normalize_google_event, raw_events))


# pure: body is a mutable dict but only read here, never mutated.
# the returned inner dicts are references to the original api data —
# they are immediately consumed by normalize_google_events which also only reads them.
def extract_items_and_sync_token(
    body: dict[str, Any],
) -> tuple[tuple[dict[str, Any], ...], str | None]:
    return tuple(body.get("items", [])), body.get("nextSyncToken")


# pure: filter over immutable CalendarEvent sequence
def keep_events_with_location(xs: tuple[CalendarEvent, ...]) -> tuple[CalendarEvent, ...]:
    return tuple(filter(lambda e: bool(e.location), xs))


# pure: filter by date range — string comparison is safe since ISO dates sort lexicographically
def filter_events_by_date(
    xs: tuple[CalendarEvent, ...],
    start_date: str,
    end_date: str | None = None,
) -> tuple[CalendarEvent, ...]:
    effective_end = end_date or start_date
    return tuple(filter(
        lambda e: start_date <= e.start_date[:10] <= effective_end,
        xs,
    ))


# composed pipeline: extract items → normalize → keep with location
def process_calendar_body(body: dict[str, Any]) -> tuple[CalendarEvent, ...]:
    items, _ = extract_items_and_sync_token(body)
    return keep_events_with_location(normalize_google_events(items))
