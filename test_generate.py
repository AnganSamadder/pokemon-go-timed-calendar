"""Tests using only minimal synthetic fixtures, never production data."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from icalendar import Calendar

from generate import build_calendar

SOURCE = "https://example.test/events.json"


def synthetic_event(**overrides):
    """Return a clearly synthetic TEST event fixture."""
    event = {
        "eventID": "test-community-hour",
        "name": "TEST Community Hour",
        "eventType": "event",
        "heading": "Event",
        "link": "https://example.test/events/test-community-hour/",
        "start": "2030-01-02T18:00:00.000",
        "end": "2030-01-02T19:00:00.000",
    }
    event.update(overrides)
    return event


def parsed_events(payload):
    calendar = Calendar.from_ical(payload)
    return calendar, list(calendar.walk("VEVENT"))


class CalendarTests(unittest.TestCase):
    def test_same_day_naive_event_keeps_floating_duration(self):
        payload, summary = build_calendar([synthetic_event()], SOURCE)
        calendar, events = parsed_events(payload)

        self.assertEqual(str(calendar["X-WR-CALNAME"]), "Pokémon GO — Timed Events")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["DTSTART"].dt, datetime(2030, 1, 2, 18, 0))
        self.assertEqual(events[0]["DTEND"].dt, datetime(2030, 1, 2, 19, 0))
        self.assertNotEqual(events[0]["DTSTART"].params.get("VALUE"), "DATE")
        self.assertEqual(str(events[0]["TRANSP"]), "TRANSPARENT")
        self.assertFalse(events[0].walk("VALARM"))
        self.assertEqual(summary["timed_events"], 1)

    def test_multiday_event_becomes_start_and_end_markers(self):
        source = synthetic_event(
            eventID="test-long-event",
            name="TEST Long Event",
            start="2030-01-02T10:30:00.000",
            end="2030-01-05T20:45:00.000",
        )

        payload, summary = build_calendar([source], SOURCE)
        _, events = parsed_events(payload)

        self.assertEqual(len(events), 2)
        by_summary = {str(event["SUMMARY"]): event for event in events}
        starts = by_summary["Starts: TEST Long Event"]
        ends = by_summary["Ends: TEST Long Event"]
        self.assertEqual(starts["DTSTART"].dt, datetime(2030, 1, 2, 10, 30))
        self.assertEqual(starts["DTEND"].dt, datetime(2030, 1, 2, 10, 45))
        self.assertEqual(ends["DTSTART"].dt, datetime(2030, 1, 5, 20, 45))
        self.assertEqual(ends["DTEND"].dt, datetime(2030, 1, 5, 21, 0))
        self.assertIn("Original start: 2030-01-02T10:30:00.000", str(starts["DESCRIPTION"]))
        self.assertIn("Original end: 2030-01-05T20:45:00.000", str(starts["DESCRIPTION"]))
        self.assertIn(source["link"], str(starts["DESCRIPTION"]))
        self.assertIn("15-minute start marker", str(starts["DESCRIPTION"]))
        self.assertIn("15-minute end marker", str(ends["DESCRIPTION"]))
        self.assertEqual(summary["start_markers"], 1)
        self.assertEqual(summary["end_markers"], 1)

    def test_z_and_offset_timestamps_are_normalized_to_utc(self):
        z_event = synthetic_event(
            eventID="test-zulu",
            start="2030-01-02T18:00:00Z",
            end="2030-01-02T19:00:00Z",
        )
        offset_event = synthetic_event(
            eventID="test-offset",
            start="2030-01-02T18:00:00+05:30",
            end="2030-01-02T19:00:00+05:30",
        )

        payload, summary = build_calendar([z_event, offset_event], SOURCE)
        _, events = parsed_events(payload)
        starts = sorted(event["DTSTART"].dt for event in events)

        self.assertIn(datetime(2030, 1, 2, 18, 0, tzinfo=timezone.utc), starts)
        self.assertIn(datetime(2030, 1, 2, 12, 30, tzinfo=timezone.utc), starts)
        self.assertTrue(all(event["DTSTART"].dt.utcoffset() == timedelta(0) for event in events))
        self.assertEqual(summary["utc_endpoints"], 4)

    def test_unknown_and_date_only_endpoints_are_omitted_without_invention(self):
        start_only = synthetic_event(
            eventID="test-start-only",
            name="TEST Start Only",
            start="2030-02-01T09:00:00.000",
            end=None,
        )
        end_only = synthetic_event(
            eventID="test-end-only",
            name="TEST End Only",
            start="2030-02-01",
            end="2030-02-03T17:00:00.000",
        )
        neither = synthetic_event(
            eventID="test-no-time",
            name="TEST No Time",
            start="unknown",
            end="2030-02-04",
        )

        payload, summary = build_calendar([start_only, end_only, neither], SOURCE)
        _, events = parsed_events(payload)
        by_summary = {str(event["SUMMARY"]): event for event in events}

        self.assertEqual(set(by_summary), {"Starts: TEST Start Only", "Ends: TEST End Only"})
        self.assertEqual(by_summary["Starts: TEST Start Only"]["DTSTART"].dt, datetime(2030, 2, 1, 9, 0))
        self.assertEqual(by_summary["Ends: TEST End Only"]["DTSTART"].dt, datetime(2030, 2, 3, 17, 0))
        self.assertTrue(all(event["DTEND"].dt - event["DTSTART"].dt == timedelta(minutes=15) for event in events))
        self.assertEqual(summary["omitted_start_endpoints"], 2)
        self.assertEqual(summary["omitted_end_endpoints"], 2)
        self.assertEqual(summary["date_only_endpoints"], 2)
        self.assertEqual(summary["unknown_endpoints"], 2)
        self.assertEqual(summary["events_with_no_timed_endpoint"], 1)

    def test_identical_duplicate_source_ids_are_deduplicated(self):
        event = synthetic_event()

        payload, summary = build_calendar([event, dict(event)], SOURCE)
        _, events = parsed_events(payload)

        self.assertEqual(len(events), 1)
        self.assertEqual(summary["source_events"], 2)
        self.assertEqual(summary["unique_source_events"], 1)
        self.assertEqual(summary["duplicate_source_events"], 1)

    def test_conflicting_duplicate_source_ids_fail(self):
        first = synthetic_event()
        conflicting = synthetic_event(name="TEST Different Name")

        with self.assertRaisesRegex(ValueError, "conflicting duplicate eventID: test-community-hour"):
            build_calendar([first, conflicting], SOURCE)

    def test_invalid_timestamp_ordering_fails(self):
        cases = (
            synthetic_event(eventID="test-equal", start="2030-01-02T18:00:00", end="2030-01-02T18:00:00"),
            synthetic_event(eventID="test-backwards", start="2030-01-03T18:00:00", end="2030-01-02T18:00:00"),
            synthetic_event(eventID="test-mixed-zone", start="2030-01-02T18:00:00Z", end="2030-01-02T19:00:00"),
        )

        for event in cases:
            with self.subTest(eventID=event["eventID"]):
                with self.assertRaises(ValueError):
                    build_calendar([event], SOURCE)

    def test_empty_or_malformed_source_data_fails_validation(self):
        malformed = (
            [],
            {},
            [synthetic_event(eventID="")],
            [synthetic_event(name=42)],
            [synthetic_event(link="not-a-url")],
            [synthetic_event(start="2030-99-99T10:00:00")],
        )

        for data in malformed:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    build_calendar(data, SOURCE)

    def test_timestamp_requires_an_explicit_time(self):
        no_time_values = ("20300102", "2030-W01-2")

        for value in no_time_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "invalid timestamp endpoint"):
                    build_calendar([synthetic_event(start=value)], SOURCE)

    def test_publication_writes_both_outputs_and_preserves_good_files_on_failure(self):
        from generate import publish

        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "dist"
            output_dir.mkdir()
            calendar_path = output_dir / "pokemon-go-timed.ics"
            summary_path = output_dir / "summary.json"
            calendar_path.write_bytes(b"known-good-calendar")
            summary_path.write_text("known-good-summary", encoding="utf-8")

            with self.assertRaises(ValueError):
                publish([], SOURCE, output_dir)
            self.assertEqual(calendar_path.read_bytes(), b"known-good-calendar")
            self.assertEqual(summary_path.read_text(encoding="utf-8"), "known-good-summary")

            publish([synthetic_event()], SOURCE, output_dir)
            _, events = parsed_events(calendar_path.read_bytes())
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(len(events), 1)
            self.assertEqual(summary["calendar_entries"], 1)
            self.assertEqual(summary["source_urls"]["events"], SOURCE)
            self.assertIn("documentation", summary["source_urls"])
            self.assertRegex(summary["generated_at"], r"^\d{4}-\d{2}-\d{2}T")

    def test_unicode_is_escaped_folded_and_uids_are_stable_without_all_day_values(self):
        name = "TEST Pokémon, GO; Back\\slash\n" + "✨" * 40
        event = synthetic_event(name=name)

        first_payload, _ = build_calendar([event], SOURCE)
        changed_payload, _ = build_calendar([synthetic_event(name="TEST Renamed")], SOURCE)
        _, first_events = parsed_events(first_payload)
        _, changed_events = parsed_events(changed_payload)

        self.assertEqual(str(first_events[0]["SUMMARY"]), name)
        self.assertEqual(str(first_events[0]["UID"]), str(changed_events[0]["UID"]))
        self.assertNotIn(b"VALUE=DATE", first_payload)
        self.assertNotIn(b"BEGIN:VALARM", first_payload)
        self.assertIn(b"\\,", first_payload)
        self.assertIn(b"\\;", first_payload)
        self.assertIn(b"Back\\\\slash\\n", first_payload)
        self.assertNotIn(b"\n", first_payload.replace(b"\r\n", b""))
        self.assertTrue(all(len(line) <= 75 for line in first_payload.split(b"\r\n")))


if __name__ == "__main__":
    unittest.main()
