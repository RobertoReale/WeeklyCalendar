# Plan: per-event Google Calendar colors

Status: designed, not built. Written for the developer (or Claude session) who builds it.
Base: v1.22.0 (commit 54a6f3f). Read `docs/plans/README.md` first: every convention there
applies, and each one has already caused a bug once.

## 1. Goal

In Google Calendar, every calendar has a default color (`EventColor1..6` in the skin), **and**
individual events can be given one of Google's 11 event colors (Tomato, Flamingo, Tangerine,
Banana, Sage, Basil, Peacock, Blueberry, Lavender, Grape, Graphite) — for example coloring
exams in red (*Tomato*) even though they live on the primary calendar.

What they get:

- **Reading:** if an event in an `.ics` feed has a standard RFC 7986 `COLOR` property or an
  `X-GOOGLE-COLOR` / `X-APPLE-CALENDAR-COLOR` / `X-WC-COLOR` property, or if the Tasks script
  provides event color overrides, the skin draws that event (and its detail card dot) in its
  own color instead of the feed's default color;
- **Creating & Editing:** in the Create and Edit forms of an event (when `edit.scriptV >= 4`),
  the calendar row or a small color dot next to the calendar picker lets the user pick either
  *Calendar color* (default) or one of the **11 Google Calendar event colors** (`colorId = 1..11`
  in the Google Calendar API);
- `tools/GoogleTasksFeed.gs` passes `colorId` to `Calendar.Events.insert` / `Calendar.Events.patch`,
  and optionally exports `X-WC-ECOLOR;UID=<iCalUID>:<colorId>` lines in its feed so per-event
  colors set in Google Calendar on the web also appear in the skin (since Google's standard
  `.ics` export omits `colorId`).

## 2. Google's 11 event `colorId` values

Google Calendar API v3 numbers its event colors `'1'` through `'11'`:

| `colorId` | Name (en / it) | RGB |
|---|---|---|
| `'1'` | Lavender / Lavanda | `121, 134, 203` |
| `'2'` | Sage / Salvia | `51, 182, 121` |
| `'3'` | Grape / Uva | `142, 36, 170` |
| `'4'` | Flamingo / Fenicottero | `230, 124, 115` |
| `'5'` | Banana / Banana | `246, 191, 38` |
| `'6'` | Tangerine / Mandarino | `244, 81, 30` |
| `'7'` | Peacock / Pavone | `3, 155, 229` |
| `'8'` | Graphite / Grafite | `97, 97, 97` |
| `'9'` | Blueberry / Mirtillo | `63, 81, 181` |
| `'10'` | Basil / Basilico | `11, 128, 67` |
| `'11'` | Tomato / Pomodoro | `213, 0, 0` |

Store this table once in `Calendar.lua` (inside `edit.cf`), so both this feature and the
settings panel (`docs/plans/settings-panel.md`) can share it!

## 3. Changes in `tools/GoogleTasksFeed.gs` (bump `X-WC-VERSION` to `4`)

1. **`createEvent(p)`:**
   - validate `p.color`: if present and non-empty, must match `/^([1-9]|1[01])$/`;
   - set `if (p.color) res.colorId = p.color;`.
2. **`editEvent(p)` / `editSeries(p, patch, times)`:**
   - if `p.color !== undefined`:
     - `''` clears the custom color (`patch.colorId = null`, so the event reverts to the
       calendar's color);
     - `'1'..'11'` sets `patch.colorId = p.color`.
3. **Exporting per-event colors in `buildFeed()`:**
   - Google Calendar's `.ics` export does not include `colorId`. However, if `typeof Calendar !== 'undefined'`,
     `buildFeed()` can query colored events from the user's calendars (or primary calendar) within
     `dueMin..dueMax`, or emit `X-WC-ECOLOR;UID=<iCalUID>:<colorId>` header lines in the Tasks
     feed for any event that has `ev.colorId` set!
   - Even simpler and fast: in `buildFeed()`, if `typeof Calendar !== 'undefined'`, list events
     from `primary` (within `DAYS_BACK..DAYS_AHEAD`, `singleEvents: false`, `maxResults: 2500`)
     and for each event with `ev.colorId` and `ev.iCalUID`, push
     `X-WC-ECOLOR;UID=` + `ev.iCalUID` + `:` + `ev.colorId` (and for single-instance overrides
     with `recurringEventId` and `originalStartTime`, include `;ORIG=<UTC or date>`).
   - Wrap that in `try { ... } catch (err) {}` so a Tasks-only user without the Calendar API
     service still gets their tasks feed with no error.

## 4. Changes in `Calendar.lua`

### A. Parsing and resolving an item's color

1. Parse `COLOR:` (RFC 7986 CSS color name or hex) on `VEVENT` and `X-WC-ECOLOR` on the
   calendar header (`edit.eventColors[uid] = colorId`).
2. Add a small helper `itemColors(it)`:
   - if `it.color` (from `it.colorId` or `edit.eventColors[it.uid]` or optimistic edit), return
     `GOOGLE_COLORS[it.color]` and its faded past version `blend(rgb, cfg.bg, cfg.pastFade)`;
   - otherwise return `cfg.colors[it.feed]` and `cfg.pastColors[it.feed]`.
3. Use `itemColors(it)` in:
   - `layout()` (all-day chips `ADBg` and timed boxes `EvBg`);
   - `layoutMonth()` (month view chips and dots);
   - `buildDetail(c)`, `buildCreate(c)`, `buildEdit(c)` and `createDraft(c, feed)`.

### B. Picker in Create and Edit cards

In `buildCreate(c)` and `buildEdit(c)` (when `not isTask` and `edit.scriptV >= 4`):

- On the calendar picker row (`cf.picker(els, sh, c, W, y, 'cal', ...)`), the color dot on the
  left (around `x = 28`) or a small second pill on the right of the calendar row opens the
  color menu (`CardMenu('color')`), and scrolling over the dot cycles through *Calendar color* +
  the 11 colors (`CardCycle('color', dir)`).
- That way the card height (`h`) does **not** grow by another row (keeping the card compact
  enough for 800 x 440 screens!).

## 5. Tests (`tests/run_tests.py`)

1. **`test_event_with_custom_color_draws_in_that_color`:**
   - load a feed with `X-WC-ECOLOR;UID=test-1:11` (Tomato `213,0,0`);
   - verify `EvBg1`'s `Shape` uses `213,0,0,255` instead of `cfg.colors[1]`, and its past
     version blends `213,0,0` with `cfg.bg`.
2. **`test_create_and_edit_event_color_sends_color_param`:**
   - with `X-WC-VERSION:4`, open Create, pick color `'11'` (Tomato), save;
   - verify the curl URL includes `&color=11`;
   - open Edit on that event, reset color to `''` (Calendar color), save;
   - verify the curl URL includes `&color=`.
3. **`test_gs_create_and_edit_event_color_id` (Node.js test in `run_tests.py`):**
   - verify `GoogleTasksFeed.gs` passes `colorId: '11'` to `Calendar.Events.insert` and
     `colorId: null` to `Calendar.Events.patch` when cleared, and rejects invalid color IDs.

