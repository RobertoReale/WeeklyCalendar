# Plan 8: drag a task to another day

Goal: press a Google Task in the all-day row, drag it to another day column and release it.
The task moves there immediately, and Google Tasks saves the new due date. This works like
Google Calendar. Only tasks can move: iCal events are read-only.

Read [the conventions](README.md#conventions-that-apply-to-every-plan) first. This plan reuses
the task pipeline of feature 3 (`ToggleTask` → `MeasureTaskAction` → `TaskResult`, with
optimistic display and rollback). Read that code before starting.

## Rainmeter constraints (why the design looks like this)

- There is no "mouse move" or drag event, and `$MouseX$` / `$MouseY$` are only known inside
  mouse actions. A ghost chip that follows the cursor pixel by pixel is therefore not possible
  without a third-party plugin. Instead, a full-height **drop zone** meter per day column shows
  where the task will land: its `MouseOverAction` highlights the column under the cursor.
- With `Draggable=1` (the default), pressing and moving the mouse may **move the whole skin
  window**. Rainmeter is expected not to drag the skin from a meter that has a
  `LeftMouseDownAction`, but this must be verified (Phase 0).
- If the button is released outside the skin, the skin never receives the release. Every
  drag must be cancellable: on `MouseLeaveAction` of the drop layer, on a right click, and
  with a timeout.

## Phase 0: spike (do this first, about 30 minutes)

Verify the three assumptions on the real Rainmeter before writing the feature:

1. **Press on a meter with `LeftMouseDownAction`, move the mouse: the skin window does not
   move.**
2. **While the button is held, a meter that is shown in the `LeftMouseDownAction` receives
   `MouseOverAction` / `MouseLeaveAction` when the cursor crosses it.**
3. **On release, the `LeftMouseUpAction` that runs belongs to the meter under the cursor**,
   not the one that was pressed.

How: create a throwaway skin `Skins\WCDragSpike\Spike.ini` (outside the repo). It has a
pressable rectangle and two drop rectangles, and every action writes a `[!Log "..."]`.
Load it with `Rainmeter.exe !ActivateConfig WCDragSpike Spike.ini`. Drive the mouse from
PowerShell (`user32.dll` `SetCursorPos` + `mouse_event` with `LEFTDOWN`, moves, `LEFTUP`
via `Add-Type`), then read `%APPDATA%\Rainmeter\Rainmeter.log`. Also read the window
position before and after with `!Log [#CURRENTCONFIGX]` in an action. Unload it with
`!DeactivateConfig` afterwards.

- **All three hold:** build the design below.
- **1 fails:** during a drag, set `!Draggable 0` from the `LeftMouseDownAction`, then
  `!Draggable 1` (or the user's previous value) at the end of the drag.
- **2 or 3 fails:** use the **fallback design** at the end of this file. Do not switch to a
  plugin without asking the user.

## Design

### Interaction

1. **Press** on a task chip (`ADBg` / `ADTx` of a task from the new script; not on the
   ○ / ✓ button). Nothing visible happens yet. The Lua remembers the task and its column
   (`DragStart(n)`), and shows the transparent drop layer.
2. **Move** into another column: the drag becomes "active".
   - The source chip fades to 40% (fill `blend(color, cfg.bg, 0.6)`).
   - The target column gets a highlight: a rectangle over the whole column (from the day
     header to `gridBottom`) filled with the task colour at alpha 28, a 2 px border in the task
     colour at alpha 160, and radius `cfg.radius`.
   - A **preview chip** sits in the target day's all-day row, in the first free row (row 1
     if the day has no all-day items; if the row is full, it replaces the "+N more" row). It
     has the task's colour at alpha 150, the same label (`○ Title`), and the same geometry as
     a normal chip.
   - The toolbar sync text temporarily reads `Move to Fri 23` / `Sposta a ven 23`.
3. **Release**:
   - over another column: the task moves there (same flow as `ToggleTask`, below).
   - over the source column, without having left it: it counts as a normal **click**. Run the
     chip's normal left-click action (`clickActions(it)`), so clicking still opens Google
     Calendar.
   - over the source column after visiting others: cancel, nothing changes.
4. **Cancel:** right click during the drag, the cursor leaving the skin (`MouseLeaveAction`
   of the drop layer's bounding meter), or 20 s without a release (`Update()` watchdog).
   Everything returns to normal and no request is sent.

Hover cursor: set `MouseActionCursorName=SizeAll` on draggable task chips, so they look
movable. Keep the hand cursor on the ○ button.

### Drop targets beyond the visible week (optional, last step)

While dragging, hovering the toolbar `<` / `>` buttons for about 0.8 s would switch the week.
Rainmeter has no hover timer, so this needs the `Update()` tick (1 s) and feels sluggish.
**Leave it out of v1.** Moving a task by a week or more stays a job for Google Calendar.

### Meters (`.ini`)

Place them just before `[NowLine]`, so they are above every chip and event and receive the
mouse during a drag. Outside a drag they are hidden, so they never block normal clicks.

| Meter | Type | Role |
| :--- | :--- | :--- |
| `DragHi` | Shape | target column highlight |
| `DragPrev` / `DragPrevTx` | Shape / String (8 pt, `StyClip`) | preview chip |
| `DragZone0..6` | Shape, `Fill Color 0,0,0,1` | one per day column, from the day header top to `gridBottom`; `MouseOverAction=[!CommandMeasure MeasureScript "DragOver(i)"]`, `LeftMouseUpAction=[!CommandMeasure MeasureScript "DragDrop(i)"]`, `RightMouseUpAction=…"DragCancel()"`, `MouseLeaveAction` not needed per zone |
| `DragArea` | Shape, transparent, full skin size | **below** the zones; `MouseLeaveAction=[!CommandMeasure MeasureScript "DragCancel()"]` and `LeftMouseUpAction` = cancel (release outside every column) |

All of them are hidden (`StyHidden`), have no tooltip and are not part of `StyWeekScroll`.

### Lua

- **State:** `drag = { it, n, fromCol, overCol, left = false, started = os.time() }`.
- **`layout()`, all-day loop:** for a task chip with `tlist` / `tid`, set
  `LeftMouseDownAction` on `ADBg` / `ADTx` to `DragStart(adUsed)`, and remove its
  `LeftMouseUpAction`: the click is now handled by `DragDrop` on the same column. For every
  other chip, clear `LeftMouseDownAction`. Also store `adCol[adUsed] = i`.
- **`DragStart(n)`:** record the drag, position and show `DragArea` and `DragZone0..6`
  (geometry from `cfg.geo`, which must also carry `tb`, `hdr`, `gridBottom`, `adH`), redraw.
  No layout.
- **`DragOver(col)`:** when `col ~= fromCol`, set `left = true`. Position `DragHi` on `col`,
  and place `DragPrev` in the first free row of `col` (needs per-day used-row counts from
  the last layout: store `adRowsUsed[i]`). Fade the source chip by `set(..., 'Shape', …)` on
  its `ADBg` only. Redraw; do not run a full layout.
- **`DragDrop(col)`:**
  - `col == fromCol and not left`: hide the drag meters, then run the chip's left action
    with `SKIN:Bang(action)`. When `clickActions` returns `''`, do nothing.
  - `col == fromCol`: cancel.
  - otherwise: `newDay = ws + col` and call `MoveTask(it, newDay)`.
- **`MoveTask(it, day)`:** the same flow as `ToggleTask`:
  - `taskPending[key] = { due = day }`. `taskPending` values become tables
    `{ state = 'done'|'open', due = <day> }`. Migrate `ToggleTask` and `applyTaskPending`:
    `applyTaskPending` sets `ev.dtstart = { y, m, d, allday = true }` from `due` (keep
    `dtend` / `duration` nil for tasks), as well as `ev.task` from `state`.
  - queue a job `{ kind = 'move', due = 'YYYY-MM-DD' }`. `sendNextTask` builds
    `action=move&list=..&task=..&due=YYYY-MM-DD`.
  - `TaskResult` keeps the same OK / ERROR / auth handling. On failure it removes only the
    pending field of that job (a pending completion of the same task survives).
- **`DragCancel()`:** hide everything, restore the source chip (`needLayout = true`, then
  `safeLayout()` is simplest), and set `drag = nil`.
- **Watchdog in `Update()`:** cancel when `drag` is older than 20 s.
- **Strings (`LANGS.en` / `LANGS.it`):** `moveTo = 'Move to'` / `'Sposta a'`. Also update
  the task tooltip with a hint: `'Drag to another day to move it'` /
  `'Trascina su un altro giorno per spostarla'`.

### Apps Script (`tools/GoogleTasksFeed.gs`)

- In `doGet`, add `action=move` with `due=YYYY-MM-DD`. Validate it with
  `/^\d{4}-\d{2}-\d{2}$/`, otherwise answer `ERROR bad date`. Then call
  `Tasks.Tasks.patch({ due: due + 'T00:00:00.000Z' }, list, task)` and answer `OK`.
- Caveats to document in the README:
  - The Tasks API stores only the date. A task that has a **time** set in the Google
    Calendar app may lose that time when moved from the skin.
  - **Repeating tasks:** the API exposes only the current instance, and moving it may detach
    it from the series. The feed does not mark repeating tasks, so this cannot be prevented;
    say it in the README.
- No new permission is needed: the scope is the same `auth/tasks` as completing tasks.

## Tests

Use `tests/run_tests.py` with `tasks.ics` on Wed 3 Mar 2027:

- **Chip actions:** a task chip with ids has `LeftMouseDownAction` `DragStart(n)` and no
  `LeftMouseUpAction`. A holiday or event chip has no `LeftMouseDownAction`.
- **Click:** `DragStart(n)` then `DragDrop(<same column>)` with no `DragOver` → the chip's
  Google Calendar link is sent as a bang (record it in `mock.bangs`). No task request is
  sent, and the drag meters are hidden.
- **Move:** `DragStart`, `DragOver(4)`, `DragDrop(4)` → `MeasureTaskAction` `Parameter` ends
  with `action=move&list=L1&task=t-open&due=2027-03-05`, and `Run` is sent. The task is shown
  on Friday at once (`all_day()` and the column of its `ADBg` X). `TaskResult` with `OK`
  refreshes the feed. With `ERROR …auth/tasks…` the task returns to Wednesday and the
  toolbar shows "allow editing tasks".
- **Move then complete before the confirmation:** both pending changes are kept, and a
  failure of the move keeps the completion.
- **Cancel:** `DragStart`, `DragOver(4)`, `DragCancel()` → no request, chip unchanged. The
  watchdog cancels after 20 s (advance `sk.at(...)` and call `Update()`).
- **Preview:** after `DragOver(4)`, `DragHi` is shown with its X at Friday's column, and
  `DragPrev` is in Friday's first free all-day row.
- **Script under Node:** `doGet({parameter:{action:'move', list:'L1', task:'a', due:'2027-03-05'}})`
  returns `OK` and patches `{due:'2027-03-05T00:00:00.000Z'}`. `due:'5/3/2027'` returns
  `ERROR`.
- `check_clean()` and the pixel snapping test pass.

## Interaction with other plans

- **Plan 4 (expandable all-day rows):** the "first free row" logic must use the current
  `rows`. Drop zones are unaffected.
- **Plan 7 (views):** zones `DragZone0..nd-1` in day / 3-day views. In the day view
  dragging makes no sense, so disable `DragStart` when `nd == 1`. The month view is out of
  scope: drop targets would be cells. Add it to that plan as a follow-up if wanted.

## Fallback design (if Phase 0 shows that dragging cannot work)

Use **pick and drop with two clicks.** Rainmeter cannot read modifier keys (Ctrl+click), so
add a small **⇄ button** that appears on hover at the right end of each task chip: a pool
`ADMove1..N` next to `ADChk`, shown and hidden by the chip's `MouseOverAction` /
`MouseLeaveAction`, with the tooltip "Move to another day" / "Sposta in un altro giorno".

- clicking ⇄ puts the task in "move mode": the columns show the same highlight on hover
  (`DragZone*` with `MouseOverAction`, which works without a held button);
- the next click on a column drops the task there;
- `Esc` cannot be read, so cancel by clicking the source column or with a right click.

Everything else (Lua move pipeline, script, tests) stays the same.

## Done when

Phase 0 has been verified and the result is written at the top of this file. All tests pass.
In the real skin, a task dragged from Wednesday to Friday moves at once and stays there after
the next sync. A plain click still opens Google Calendar. Releasing outside the skin leaves
nothing stuck.
