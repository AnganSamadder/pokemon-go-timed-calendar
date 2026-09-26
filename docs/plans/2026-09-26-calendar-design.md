# Timed Pokémon GO subscription design

## Goal

Replace an unfiltered all-day-heavy subscription with a live feed of timed events and start/end markers. No personal calendar data is read or published by this project.

## Approach

Fetch ScrapedDuck's public Leek Duck event JSON directly, because the all-day ICS feed has discarded the actual boundary times. Preserve same-date timed event durations. For multi-date events, emit a 15-minute Starts marker and a 15-minute Ends marker, each beginning at the actual supplied endpoint. Skip unknown/date-only endpoints rather than inventing a time. Preserve floating local timestamps versus global UTC timestamps.

Use stable per-event/per-role UIDs, RFC 5545 serialization, transparent availability, and no alarms. Descriptions retain the original bounds and source URL.

## Publication

A public GitHub repository contains only code, synthetic unit-test fixtures, documentation, and public feed output. GitHub Actions runs tests every six hours and atomically commits and pushes both generated files to `dist/` on `main`. Invalid inputs fail before publication, preserving the last good feed. Calendar subscriptions use the stable raw URL for `dist/pokemon-go-timed.ics`; `dist/summary.json` is published beside it. Generated commits maintain repository activity.

## Verification

Test time-zone handling, timed spans, marker bounds, unavailable timestamps, duplicate identities, malformed input, and safe serialization. Parse the generated live feed independently and check no all-day entries or duplicate UIDs. Run the hosted workflow and compare both generated files with the raw files addressed by the immutable pushed commit SHA; the stable `main` URLs may lag for several minutes because of CDN caching. Finally use Apple Calendar's UI to replace or hide the original subscription, verifying iCloud location, hourly refresh, the exact new URL, populated timed events, and no enabled duplicate feed. Do not claim iPhone sync without observing it.
