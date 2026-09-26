# Pokémon GO — Timed Events

A live subscription calendar without multi-day all-day banners.

## Subscribe

Add this URL as a **calendar subscription**, not a file import:

```text
https://raw.githubusercontent.com/AnganSamadder/pokemon-go-timed-calendar/main/dist/pokemon-go-timed.ics
```

In Apple Calendar on Mac: **File → New Calendar Subscription**, paste the URL, choose **iCloud**, and set **Auto-refresh → Every hour**. Hide or unsubscribe from the unfiltered calendar to prevent duplicates.

## What appears

- Events beginning and ending on the same date keep their actual timed span.
- Events spanning multiple dates become two short entries: **Starts: …** and **Ends: …**. Each marker is 15 minutes long, beginning at the corresponding source timestamp. Its duration is for display, not the event's duration.
- If only one endpoint has a known time, only that endpoint gets a marker.
- Missing or date-only timestamps are never turned into invented times.
- No all-day entries, default alarms, or busy-time reservations.

Event descriptions retain the source's start/end values and link to the event page. Multi-day events with daily play windows are represented by their overall start/end markers, not guessed daily sessions.

## Time zones

The upstream source distinguishes local-time events from global events. Timestamps without an offset stay **floating local time**, following the calendar device's time zone. UTC/offset timestamps stay absolute instants and display in the viewer's time zone. Location-specific event details and upstream timing errors still require checking the linked source page.

## Updates and reliability

GitHub Actions fetches the public source every six hours, validates the build, and atomically publishes the generated files to `dist/` on `main`. Apple Calendar checks the stable subscription URL on its own refresh schedule. Scheduled GitHub jobs can be delayed, and GitHub's raw-content CDN may take up to several minutes to show a newly published version at the stable URL; updates are not guaranteed at an exact minute.

Invalid input or a failed build leaves the last published subscription available rather than replacing it with empty or fabricated data. Check [workflow runs](https://github.com/AnganSamadder/pokemon-go-timed-calendar/actions) and [the latest summary](https://raw.githubusercontent.com/AnganSamadder/pokemon-go-timed-calendar/main/dist/summary.json) for status. Automatic feed commits keep repository activity current.

Only public game-event metadata is fetched or published. No access to a subscriber's personal calendar is required.

## Sources

- [Leek Duck events](https://leekduck.com/events/)
- [ScrapedDuck event data and timestamp semantics](https://github.com/bigfoott/ScrapedDuck/wiki/Events)
- Public JSON: `https://raw.githubusercontent.com/bigfoott/ScrapedDuck/data/events.min.json`

Unofficial project, not affiliated with Pokémon GO or its rights holders. Names and trademarks belong to their respective owners. Source event data remains subject to its original ownership and terms.

## Development

Python 3.11 or later:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest -v
python generate.py
```

Generated subscription: `dist/pokemon-go-timed.ics`. Build counts and source metadata: `dist/summary.json`.
