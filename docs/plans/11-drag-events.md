# Plan 11: drag an event to another time or day

Goal: press an event in the time grid, drag it and release it. The event moves to the
time (snapped to 15 minutes) and the day under the cursor, keeps its duration, and Google
Calendar saves it. This works like Google Calendar. All-day events move between days like
tasks already do.

Read [the conventions](README.md#conventions-that-apply-to-every-plan) first. This plan
builds on the task drag (v1.8.0, `DragStart` / `DragOver` / `DragDrop` / `DragCancel` in
`Calendar.lua`, the `Drag*` meters) and needs the Calendar parts of
[plan 10](10-edit-delete.md): the advanced Calendar service in the Apps Script, the event
lookup by iCal UID, and the "local changes" table. **Build it after plan 10, or build those
parts of plan 10 first** (without the card).

## What can be dragged

| Item | Drag | Why |
| :--- | :--- | :--- |
| Timed event in a Google calendar slot (`cfg.calIds[feed]` set, secret address), starting and ending on the same day | ✓ time and day | Calendar API |
| All-day event in such a slot | ✓ day (keeps its length) | Calendar API |
| Occurrence of a recurring event | ✓ this occurrence only (v1) | Calendar API instances |
| Timed event spanning more than one day | ✗ (v1) | its segments are in several columns |
| Holiday calendars, public addresses, non-Google feeds | ✗ | read-only |
| Invitation organised by someone else | ✗ | only the organizer can move it |

Use the same read-only rules as plan 10 (`ORGANIZER` parsing, `calOwners`). A read-only
event keeps today's behaviour: a press is `NO_DRAG`, a click opens it.

## Rainmeter constraints (why the design looks like this)

These were verified on the real skin for the task drag (2026-10-23, `tools\LiveTest.ps1`):

- There is no mouse-move event. Meters shown by a `LeftMouseDownAction` get
  `MouseOverAction` while the button is held, and the release runs the `LeftMouseUpAction`
  of the meter under the cursor.
- `$MouseX$` / `$MouseY$` exist only in click and scroll actions (not in
  `MouseOverAction`), relative to the meter that has the action
  ([docs](https://docs.rainmeter.net/manual/variables/mouse-variables/)).
- A meter whose options change costs about 0.5 ms on the next update, a redraw 20-40 ms.

So the time under the cursor cannot be read while moving. It comes from **slot meters**:
transparent strips of 15 minutes, whose `MouseOverAction` says "the cursor is at this
time". A strip per 15 minutes in every column would be too many meters (7 days × 64
strips), so there is **one column of strips that moves to the column under the cursor**:

- the 7 `DragZone` column zones (as for tasks) tell which column the cursor is in;
- on `DragOver(col)` the strips `DragSlot1..96` move to that column (only their `X`
  changes: at most 96 × 0.5 ms, measure it);
- the strips are above the zones, so inside the active column the cursor is always on a
  strip.

## Phase 0: spike (about 30 minutes, with LiveTest)

Check on the real skin, with a throwaway section or a test build:

1. When `DragOver(col)` moves the strips under the cursor, the strip under it gets its
   `MouseOverAction` on the next mouse move (not only after leaving and entering again).
2. Moving the cursor slowly down a column fires one `MouseOverAction` per strip (strips
   of 10-12 px at the default size; check the smallest `Height` people use).
3. Time of `DragOver` with the strips moving: target under 50 ms.
4. `$MouseY$` in the event's `LeftMouseDownAction` is relative to the event meter.

If 1 or 2 fails, use full-height strips per column (fixed, no moving) for the visible
hours only, and measure the cost of showing them in `DragStart`.

## Design

### Interaction

1. **Press** on a draggable event (`EvBg` / `EvT` / `EvD`). `LeftMouseDownAction` =
   `DragEvent(n, $MouseY$)`: the Lua remembers the event, its column and the grab offset
   (where in the event it was pressed, in minutes), shows `DragArea`, the column zones
   and the strips over the event's column.
2. **Move:** the strip under the cursor gives the slot time `t`. The new start is
   `t - grabOffset`, snapped to 15 minutes and clamped so the event stays within the day
   (00:00 to 24:00).
   - The source event fades (as the task chip does).
   - A **preview block** (`DragPrev`, `DragPrevTx`) is drawn at the new place with the
     event's height, its colour at alpha 150 and the text `10:45 – 12:15 Title`.
   - The toolbar reads `Move to Fri 5, 10:45` / `Sposta a ven 5, 10:45`.
   - Over another column: the strips move there, the preview follows.
3. **Release** on a strip: the event moves there. Released where it started (same day and
   start, never moved): a **click**, the event's normal left-click action runs.
4. **Cancel:** the same as for tasks (right click, release outside the grid, leaving the
   skin, the 20 s watchdog).
5. **Recurring event:** moves only that occurrence (v1). The tooltip says so: "Drag to move
   this event" / "Trascina per spostare questo evento". Google Calendar's
   "This event / All events" choice can come with plan 10's card.

Day view: the strips cover the single column, so dragging changes only the time.
3-day and week: time and day. Month view: a timed event line can be dropped on another
cell and keeps its time (reuses the month drop zones of the task drag; no strips).

All-day events: the same chip drag as tasks (`DragStart`), with a different job: the
event keeps its length in days.

The visible hours do not scroll while dragging (layouts wait for the drop). Moving an
event outside the visible hours stays a job for Google Calendar or the card of plan 10.

### Meters (`.ini`)

- `DragSlot1..96`: Shape, `Fill Color 0,0,0,1`, `StyHidden`, placed after the
  `DragZone*` and before `[NowLine]`.
  `MouseOverAction=[!CommandMeasure MeasureScript "DragSlot(k)"]`,
  `LeftMouseUpAction=[!CommandMeasure MeasureScript "DragSlotDrop(k)"]`,
  `RightMouseUpAction=...DragCancel(1)`, `MouseActionCursorName=SizeAll`.
  Generate them with a script.
- `DragPrev` / `DragPrevTx` are reused; for blocks taller than one line `DragPrevTx`
  shows the time, then the title (`#CRLF#`), clipped like the event text.

### Lua

- **Instances:** timed instances do not carry `uid` yet. Add `uid`, `recurring` and
  `orig` (the occurrence's original start: the `RECURRENCE-ID` of a modified occurrence,
  not its new start) in `buildInstances`, as plan 10 needs too.
- **`layout()`, events loop:** for a draggable event set `LeftMouseDownAction` to
  `DragEvent(idx, $MouseY$)` on `EvBg` / `EvT` / `EvD`, clear `LeftMouseUpAction` (the
  click comes back through the drop) and set `MouseActionCursorName=SizeAll`. Store
  `evDrag[idx] = { it, col, act, label, fade, top, minutes }`. Other events keep
  `NO_DRAG` and their click. Only the first segment of an event is draggable.
- **Geometry:** `cfg.geo` already has `gridTop`, `pad`, `hourH`, `startH`, `endH`,
  `colX`. Slot `k` covers minutes `startH*60 + (k-1)*15` to `+15`, at
  `y = gridTop + pad + (k-1) * hourH / 4`. Place the strips in `layout()` (Y and H only,
  hidden); `DragOver` sets X and W.
- **State:** `drag = { kind = 'event', n, d, from, over, slot, left, started }`. The task
  drag keeps `kind = 'task'`.
- **`DragSlot(k)`:** compute the new start, update the preview and the toolbar, one
  `!UpdateMeter` per changed meter and one redraw. Skip everything when the snapped start
  did not change.
- **`DragSlotDrop(k)`:** a click when nothing moved, otherwise queue the job (below) and
  show the event at its new place at once.
- **Local change:** the event's new start and end go into plan 10's `localChanges`
  (`kind = 'event'`, key `feed..uid..orig`), applied per instance in `buildInstances`.
  Google's secret iCal feed can take minutes or hours to show the move, so the change must
  survive feed downloads until the feed shows the new time, or 24 h.
- **Job:** `{ kind = 'moveevent', cal, uid, orig, start, end }` (ISO 8601 UTC) or
  `{ kind = 'moveevent', cal, uid, orig, date, days }` for all-day events, through the
  existing queue (`queueTask` / `sendNextTask` / `TaskResult`). On `ERROR` the local change
  is dropped and the event goes back; the toolbar shows the reason as for tasks.
- **Strings (`LANGS.en` / `LANGS.it`):** the drag hint for events, `moveTo` with a time.

### Apps Script (`tools/GoogleTasksFeed.gs`)

`action=moveevent&cal=…&uid=…[&orig=…]&start=…&end=…` (or `&date=YYYY-MM-DD&days=N`):

1. Find the event and, for an occurrence, the instance, exactly as in plan 10
   (`Calendar.Events.list` by `iCalUID`, then `Calendar.Events.instances` matched by
   `originalStartTime`).
2. `Calendar.Events.patch({ start: { dateTime: start }, end: { dateTime: end } }, cal, id)`,
   or `{ start: { date }, end: { date: date + days } }` for all-day events.
3. Answer `OK`, or `ERROR <message>` (no write access, organizer only, event not found).
   Check `WRITE_TOKEN` when it is set.

The user must deploy a new version and allow access to Google Calendar once (the README
explains it, as for tasks).

## Tests

`tests/run_tests.py`, with `layout.ics` on Wed 3 Mar 2027 and a calendar id in the slot:

- **Actions:** a draggable event has `LeftMouseDownAction` `DragEvent(n, $MouseY$)`, no
  `LeftMouseUpAction`, cursor `SizeAll`; holiday, invitation and multi-day events keep
  `NO_DRAG` and their click.
- **Click:** `DragEvent(n, 10)`, `DragSlot(<its own slot>)`, `DragSlotDrop(<same>)` → the
  event's Google Calendar link is sent, no request.
- **Move:** `DragEvent(n, 0)`, `DragOver(4)`, `DragSlot(k)`, `DragSlotDrop(k)` → the job
  has the right `start` / `end` in UTC (check a DST day too), the event is shown on Friday
  at the new time at once, and stays there after `Reload` of a feed that still has the old
  time. `ERROR …` puts it back.
- **Grab offset and clamping:** pressed 30 minutes into the event, the new start is the
  slot time minus 30 minutes; never before 00:00 or after 24:00 minus the duration.
- **Recurring occurrence:** only that occurrence moves; the job has `orig`.
- **Month view:** a timed line dropped on another cell keeps its time.
- **Script under Node:** a fake `Calendar.Events` (`list`, `instances`, `patch`): a single
  event, an occurrence matched by `originalStartTime`, an all-day event, and the errors.
- `check_clean()`, the pixel snapping test and the "press does not move the skin" test pass.

## Out of scope (v1)

- Changing the duration by dragging the bottom edge (Google Calendar does it): a later
  step with a resize strip at the bottom of each event.
- Moving all occurrences of a recurring event.
- Scrolling the visible hours or changing the week while dragging.
- Dragging timed events into the all-day row and the reverse.

## Done when

The tests pass. On the real skin, with real mouse input (`tools\LiveTest.ps1`):
- a lecture dragged from 10:30 to 11:00 on another day moves at once, Google Calendar shows
  it there, and it stays there after the next feed downloads;
- moving one occurrence of a recurring event changes only that one;
- a plain click still opens the event, a press on a read-only event does not move the skin;
- `DragSlot` takes under 50 ms; after the test, move the event back.
