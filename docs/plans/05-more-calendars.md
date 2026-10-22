# Plan 5: up to 6 calendars

Goal: six calendar slots instead of three (e.g. personal, university, holidays, tasks,
a shared calendar, a sports schedule). Each slot keeps its own colour, download and
offline/error state. Read [the conventions](README.md#conventions-that-apply-to-every-plan) first.

## Design

- Slots 1-6, all optional except 1. Unused slots cost nothing: their WebParser measures are
  disabled by `Initialize()`, as slots 2-3 are today.
- Default colours for the new slots, from Google Calendar's palette. All three keep white text
  readable, like the existing ones.
  - 4: Tangerine `244,81,30,255`
  - 5: Lavender `121,134,203,255`
  - 6: Graphite `97,97,97,255`
- No visual changes beyond the colours. Errors already name the slot ("calendar 5").

## Steps

1. **Lua: one constant instead of literal `3`.** Add `local FEEDS = 6` next to `EV_POOL`.
   Replace every `for i = 1, 3` / `for k = 1, 3` loop: `readSettings` (2), `rebuild` (2),
   `pollFiles`, `layout` (sync status `netErrs`, `anyUrl`), `Initialize`, `Refresh`.
   Grep `1, 3 do` afterwards: no occurrence may remain.
2. **Lua: default colours as a table.** Replace the nested ternary in `readSettings` with
   `local DEFAULT_COLORS = { '3,155,229,255', '11,128,67,255', '142,36,170,255', '244,81,30,255', '121,134,203,255', '97,97,97,255' }`.
3. **Lua: Private.inc template** (`ensurePrivateFile`): write `IcalUrl1=` … `IcalUrl6=` and
   update the comment line ("IcalUrl2 … IcalUrl6: more calendars"). Existing `Private.inc` files
   are not rewritten, which is fine: step 5 adds fallbacks.
4. **ini:** add `[MeasureICS4]` … `[MeasureICS6]` right after `[MeasureICS3]`, same options,
   `DownloadFile=calendar4.ics` …, `Reload(4)` / `NetError(4)` …. They must stay **after**
   `[MeasureScript]`: its `Initialize()` disables the measures without an address before
   they first run.
5. **Settings.inc:** add empty fallbacks `IcalUrl4=` … `IcalUrl6=`, so `#IcalUrl4#` always
   resolves, and `EventColor4..6` with the colours above. Update the "up to 3 calendars"
   comment.
6. **README:** "Multi-Calendar Support: up to 6"; mention in "Linking" that `IcalUrl4..6` can
   be added by hand to an existing `Private.inc`.

## Tests (tests/run_tests.py)

- `Skin(feeds={6: 'tasks.ics'})` shows the tasks in colour 6 (`97,97,97,255` in `ADBg` Shape),
  and `ToggleTask` + `TaskResult` sends `!CommandMeasure MeasureICS6 Update`. This proves that
  the feed index flows end to end.
- No address in slots 4-6: `Initialize()` sends `!DisableMeasure MeasureICS4..6`, and nothing
  goes into `mock.unknown`.
- A broken feed in slot 5 (`not_ical.html`) shows "feed error" and "calendar 5" in the
  `TbSync` tooltip.
- Update `Skin.__init__` if needed: it already derives `IcalUrlN` from `feeds`.

## Done when

All tests pass, a sixth calendar shows up in the real skin with its colour, and the Rainmeter
log has no `MeasureICS4..6` errors while those slots are empty.
