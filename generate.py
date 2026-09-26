#!/usr/bin/env python3
"""Generate a timed-only Pokémon GO iCalendar feed."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from icalendar import Calendar, Event

CALENDAR_NAME = "Pokémon GO — Timed Events"
SOURCE_URL = "https://raw.githubusercontent.com/bigfoott/ScrapedDuck/data/events.min.json"
DOCUMENTATION_URL = "https://github.com/bigfoott/ScrapedDuck/wiki/Events"
DEFAULT_OUTPUT_DIR = Path("dist")
_UNKNOWN = {"", "unknown", "tbd", "tba", "null"}
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_TIME_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def _parse_endpoint(value: object) -> tuple[datetime | None, date | None, str]:
    if value is None or (isinstance(value, str) and value.strip().lower() in _UNKNOWN):
        return None, None, "unknown"
    if not isinstance(value, str):
        raise ValueError("timestamp endpoints must be strings or null")
    value = value.strip()
    if _DATE_ONLY.fullmatch(value):
        try:
            return None, date.fromisoformat(value), "date_only"
        except ValueError as exc:
            raise ValueError(f"invalid date-only endpoint: {value!r}") from exc
    if not _DATE_TIME_PREFIX.match(value):
        raise ValueError(f"invalid timestamp endpoint: {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid timestamp endpoint: {value!r}") from exc
    local_date = parsed.date()
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed, local_date, "timed"


def _uid(event_id: str, role: str) -> str:
    return f"{uuid5(NAMESPACE_URL, event_id + ':' + role)}@calendar.invalid"


def _description(source: dict, explanation: str) -> str:
    return "\n".join(
        (
            f"Original start: {source.get('start')}",
            f"Original end: {source.get('end')}",
            f"Source: {source['link']}",
            explanation,
        )
    )


def _component(source: dict, role: str, start: datetime, end: datetime, explanation: str) -> Event:
    component = Event()
    component.add("uid", _uid(source["eventID"], role))
    component.add("dtstamp", datetime.now(timezone.utc))
    if role == "start":
        title = f"Starts: {source['name']}"
    elif role == "end":
        title = f"Ends: {source['name']}"
    else:
        title = source["name"]
    component.add("summary", title)
    component.add("description", _description(source, explanation))
    component.add("url", source["link"])
    component.add("dtstart", start)
    component.add("dtend", end)
    component.add("transp", "TRANSPARENT")
    return component


def _validate_source(events: object, source_url: str) -> list[dict]:
    if not isinstance(events, list) or not events:
        raise ValueError("source data must be a non-empty JSON array")
    if urlsplit(source_url).scheme not in {"http", "https"}:
        raise ValueError("source URL must use HTTP or HTTPS")
    for index, source in enumerate(events):
        if not isinstance(source, dict):
            raise ValueError(f"source event {index} must be an object")
        for field in ("eventID", "name", "link"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                raise ValueError(f"source event {index} has invalid {field}")
        if "start" not in source or "end" not in source:
            raise ValueError(f"source event {index} must include start and end")
        if urlsplit(source["link"]).scheme not in {"http", "https"}:
            raise ValueError(f"source event {index} has invalid link")
    return events


def build_calendar(events: list[dict], source_url: str) -> tuple[bytes, dict]:
    events = _validate_source(events, source_url)
    source_count = len(events)
    unique_by_id: dict[str, dict] = {}
    duplicate_count = 0
    for source in events:
        event_id = source["eventID"]
        if event_id in unique_by_id:
            if source != unique_by_id[event_id]:
                raise ValueError(f"conflicting duplicate eventID: {event_id}")
            duplicate_count += 1
        else:
            unique_by_id[event_id] = source
    events = list(unique_by_id.values())

    calendar = Calendar()
    calendar.add("prodid", "-//Timed Events Calendar//EN")
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("x-wr-calname", CALENDAR_NAME)

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    summary = {
        "generated_at": generated_at,
        "source_url": source_url,
        "source_urls": {"events": source_url, "documentation": DOCUMENTATION_URL},
        "source_events": source_count,
        "unique_source_events": len(events),
        "duplicate_source_events": duplicate_count,
        "timed_events": 0,
        "start_markers": 0,
        "end_markers": 0,
        "calendar_entries": 0,
        "utc_endpoints": 0,
        "omitted_start_endpoints": 0,
        "omitted_end_endpoints": 0,
        "date_only_endpoints": 0,
        "unknown_endpoints": 0,
        "events_with_no_timed_endpoint": 0,
    }
    for source in events:
        start, start_date, start_kind = _parse_endpoint(source.get("start"))
        end, end_date, end_kind = _parse_endpoint(source.get("end"))
        for kind in (start_kind, end_kind):
            if kind == "date_only":
                summary["date_only_endpoints"] += 1
            elif kind == "unknown":
                summary["unknown_endpoints"] += 1
        if start is None:
            summary["omitted_start_endpoints"] += 1
        else:
            summary["utc_endpoints"] += int(start.tzinfo is not None)
        if end is None:
            summary["omitted_end_endpoints"] += 1
        else:
            summary["utc_endpoints"] += int(end.tzinfo is not None)

        if start is not None and end is not None:
            if (start.tzinfo is None) != (end.tzinfo is None):
                raise ValueError(f"mixed floating and UTC endpoints for eventID: {source['eventID']}")
            if end <= start:
                raise ValueError(f"end must be after start for eventID: {source['eventID']}")
            if start_date == end_date:
                calendar.add_component(_component(source, "event", start, end, "Full event duration."))
                summary["timed_events"] += 1
                summary["calendar_entries"] += 1
            else:
                calendar.add_component(
                    _component(source, "start", start, start + timedelta(minutes=15), "15-minute start marker.")
                )
                calendar.add_component(
                    _component(source, "end", end, end + timedelta(minutes=15), "15-minute end marker.")
                )
                summary["start_markers"] += 1
                summary["end_markers"] += 1
                summary["calendar_entries"] += 2
        elif start is not None:
            calendar.add_component(
                _component(source, "start", start, start + timedelta(minutes=15), "15-minute start marker; end time unavailable.")
            )
            summary["start_markers"] += 1
            summary["calendar_entries"] += 1
        elif end is not None:
            calendar.add_component(
                _component(source, "end", end, end + timedelta(minutes=15), "15-minute end marker; start time unavailable.")
            )
            summary["end_markers"] += 1
            summary["calendar_entries"] += 1
        else:
            summary["events_with_no_timed_endpoint"] += 1

    return calendar.to_ical(), summary


def publish(events: list[dict], source_url: str, output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> tuple[Path, Path]:
    """Build completely, then atomically replace each published file."""
    calendar_payload, summary = build_calendar(events, source_url)
    summary_payload = (json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = (
        (output_dir / "pokemon-go-timed.ics", calendar_payload),
        (output_dir / "summary.json", summary_payload),
    )
    staged: list[tuple[Path, Path]] = []
    try:
        for target, payload in targets:
            with tempfile.NamedTemporaryFile(dir=output_dir, prefix=f".{target.name}.", delete=False) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                staged.append((Path(handle.name), target))
        for temporary_path, target in staged:
            os.replace(temporary_path, target)
    finally:
        for temporary_path, _ in staged:
            temporary_path.unlink(missing_ok=True)
    return targets[0][0], targets[1][0]


def fetch_source(source_url: str = SOURCE_URL) -> list[dict]:
    """Fetch JSON for CLI use; importing this module never performs network I/O."""
    request = urllib.request.Request(source_url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("upstream did not return valid UTF-8 JSON") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=SOURCE_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    events = fetch_source(args.source_url)
    calendar_path, summary_path = publish(events, args.source_url, args.output_dir)
    print(f"Wrote {calendar_path} and {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
