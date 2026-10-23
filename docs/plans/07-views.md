# Plan 7: day, 3-day and month views

Goal: besides the week, switch to a **day**, **3-day** or **month** view from a segmented
control in the toolbar, like Google Calendar's view picker. Build it in two phases that
ship separately:

- **Phase A**: day / 3-day / week, which share the time grid.
- **Phase B**: month, a new layout.

Read [the conventions](README.md#conventions-that-apply-to-every-plan) first.

## Shared design

### View switcher (toolbar, right side)

A Material 3 **segmented button**, right-aligned at `W - 20`, vertically centred on the
toolbar (`cy = tb / 2`):

```
 ┌──────┬────────┬──────────┬───────┐
 │ Day  │ 3 days │ ▌Week▐   │ Month │      Updated at 09:33   ← TbSync moves left of it
 └──────┴────────┴──────────┴───────┘
```

- Height 32, outer radius 16, 1 px border `cfg.border`, 1 px dividers between segments.
- Segment width: `max(56, textWidth + 24)`, where `textWidth ≈ ulen(label) * 8.5 * 4/3 * 0.52`
  (8.5 pt, weight 500). Labels: `Day / 3 days / Week / Month`, `Giorno / 3 giorni / Settimana / Mese`.
- The selected segment is filled with a new theme colour `SelBgColor` and its text uses
  `SelTextColor`. Add both to `THEMES`: light `211,227,253,255` / `4,30,73,255`, dark
  `0,74,119,255` / `194,231,255,255`. Unselected text is `cfg.dayNum`. The fill follows the
  outer radius on the end segments. For the first segment `[x, x+w]`, use two shapes in
  `SelBgColor`: `Rectangle x,0,w,32,16` plus `Rectangle x+w/2,0,w/2,32`, which squares the
  inner side. Mirror this for the last segment, and use a plain rectangle for middle ones.
  Draw order: fill, then dividers, then the border.
- If the toolbar is too narrow (the switcher's left edge would cross the week badge's right
  edge + 24), use short labels: `D / 3D / W / M`, `G / 3G / S / M`.
- `TbSync` becomes right-aligned at `switcherX - 16`.
- Meters (in the `.ini`, after `TbSync`): `ViewSegBg` (one Shape meter: border, dividers,
  selected fill, using `Shape`, `Shape2`, … like `Grid`) and `ViewSeg1..4` (String,
  `StringAlign=CenterCenter`, 8.5 pt, weight 500). Each has
  `LeftMouseUpAction=[!CommandMeasure MeasureScript "SetView('day')"]` (or `3day`, `week`,
  `month`), a hit Shape `ViewHit1..4` (`Fill Color 0,0,0,1`) and tooltip `lang.tips.view`.
  All have `MeterStyle=StyCal | … | StyWeekScroll` so the wheel there still navigates.

### State and persistence

- `View=week` in Settings.inc (`day`, `3day`, `week`, `month`) is the startup view.
- `SetView(v, day)` changes the view at runtime and saves it with
  `SKIN:Bang('!WriteKeyValue', 'Variables', 'View', v, SKIN:GetVariable('@') .. 'Private.inc')`.
  `Private.inc` is git-ignored and included after Settings.inc, so the choice wins on the next
  refresh without dirtying the repository. The optional `day` is used by the month view to
  open a given day.
- Replace `viewWs` (first day of the shown week) with **`anchor`**: `nil` means "today",
  otherwise an absolute day number. Each view derives its range from the anchor:
  - week: `weekStartOf(anchor)` for 7 days
  - 3-day: `anchor` for 3 days
  - day: `anchor` for 1 day
  - month: the grid that contains `anchor`'s month (phase B)

  Switching views keeps the anchor: today if today is shown, otherwise the first shown day.
  This makes "week → day" land on a sensible day.
- `ShiftView(n)` moves the anchor by `n × 7 / 3 / 1` days, or by `n` months in month view (clamp
  the day to the month length). Keep `ShiftWeek(n)` as an alias: the `.ini` (`StyWeekScroll`)
  and the tests call it. `GoToday()` sets `anchor = nil`.
- "Current" (for auto-scroll and `isCurrentWeek`) means the range contains today.

## Phase A: day, 3-day and week

### Steps

1. **Range helper:** `shownRange(todayDay)` returns `start, nd` (`nd` = 7, 3 or 1). Use it
   wherever `shownWeekStart` / `weekStartOf(today)` are used: `layout`, `Update` (auto-scroll
   check), `ScrollToHour`, `ScrollHours`, `ShiftWeek`, `GoToday`.
2. **Instances:** `weekInstances(ws)` → `rangeInstances(start, nd)`, with cache key
   `start .. ':' .. nd`, calling `buildInstances(start, start + nd)`.
3. **`layout()`: replace every hard-coded 7 / 6 with `nd`**:
   - `dS` / `dE` (`0..nd`), `days` (`0..nd-1`), `dayW = (W - timeW - 14) / nd`;
   - grid verticals `for i = 0, nd`;
   - day headers for `i = 0, nd-1`, then hide `DayName` / `DayNum` `nd..6`;
   - all-day loop, timed loop and hidden-hour indicators for `0..nd-1`; hide `HidUp*/HidDn*` `nd..6`;
   - `todayIdx` valid when `0 <= todayIdx < nd`;
   - toolbar title from `start` and `start + nd - 1`; day view:
     `lang.dayTitle(y, m, d)` → "October 21, 2026" / "21 Ottobre 2026";
   - week badge: `isoWeek(start + math.floor(nd / 2))`.
4. **Day view header:** a 1300 px column with a centred date looks lost. Like Google, put
   name and number at the column's left: `cx = timeW + 34` (and the same `cx` for
   `TodayCircle`).
5. **Wider events (`nd < 7`):** when `tw > 260`, allow the description's first line as an
   extra detail line in the event box if `remain >= 3`. Use `cleanDesc(it.desc)`, first
   non-empty line, then `safe()`, then `wrapText(…, cpl, 1)`. It is cheap and makes the day
   view useful.
6. **Now line:** `cfg.geo` gets `nd`; `updateNowLine` checks `idx < g.nd`.
7. **Prev / next tooltips** per view: `lang.tips.prev` / `next` become tables keyed by view
   ("Previous day", "Previous 3 days", "Previous week", "Previous month", and the Italian
   ones).
8. **Switcher** as designed above; `SetView`, `ShiftView`.
9. **Docs:** Settings.inc `View=` comment; README (Features, Controls: "View switcher",
   the mouse wheel moves by the current view's step).

### Tests (Phase A)

- `View=day` at Wed 3 Mar 2027: `DayName0` shown, `DayName1..6` hidden, `EvBg` widths
  `> 1000`, `TodayCircle` at `timeW + 34`, the title contains "3".
- `SetView('3day')` from the week of 3 March: the shown days are 3, 4 and 5 March (check
  `DayNum0..2` texts), `ShiftView(1)` → 6, 7 and 8, `GoToday()` → back to 3.
- `SetView` records the `!WriteKeyValue … View …` bang (`mock.bangs`).
- Hidden-hour indicators and the all-day row work in the 3-day view (reuse the
  `layout.ics` assertions).
- All existing week tests still pass unchanged (week is the default).

## Phase B: month view

**Built in v1.9.0** as designed below, with these differences: cells have no tooltip of their own
beyond "Click: open this day" (all tooltips go through `[Tip]`, see the conventions), the grid
has no outer border, and the bottom margin is 14 px (no hour buttons). `layoutMonth()` shares
`layoutToolbar()`, `setGrid()`, `allDayTip()` / `timedTip()` and `finishLayout()` with the week
layout. Measured on the real skin: changing month takes about 150-190 ms, switching to the month
the first time about 200 ms.

**State after Phase A (v1.7.0).** The switcher is generic: `VIEWS = { 'day', '3day', 'week' }`
and `VIEW_DAYS` in the Lua drive the segments, and the `.ini` has `ViewSegBg`, `ViewSeg1..3` and
`ViewHit1..3` (hit shapes above the labels, with the `SetView` action and the tooltip). For month:
append `'month'` to `VIEWS`, add `ViewSeg4` / `ViewHit4` (`SetView('month')`), the `month` labels in
`lang.views`, `lang.viewsShort`, `tips.prev` and `tips.next`, and give `shownRange` / `ShiftView` /
`setAnchor` a month branch (`VIEW_DAYS` has no entry for it). `ViewSegBg` resets `Shape..Shape5`;
four segments need up to 6 shapes (fill ×2, 3 dividers, border). The "+N more" chip opens the
day when the expanded all-day row cannot grow further (plan 4), so `SetView('day', day)` fits
there too.

### Layout

```
 tb ┌ toolbar (same; week badge hidden) ─────────────────────────────┐
    │  MON     TUE     WED     THU     FRI     SAT     SUN            │  ← DayName0..6, y = tb + 14
    ├────────┬────────┬────────┬────────┬────────┬────────┬────────┤  ← gridTop = tb + 28
    │   28   │ 1 Mar  │   2    │  (3)   │   4    │   5    │   6    │  ← day number, cell y + 14
    │        │▇ Holid.│• 10:30 │▇ Task ○│▇ All d.│        │        │  ← lines: 18 px pitch
    │        │        │  Lezio…│• 09:00 │▇ All d.│        │        │     from cell y + 28
    │        │        │        │        │ +3 more│        │        │
    ├────────┼────────┼ … 4-6 rows (as many weeks as the month spans) ┤
```

- Margins: `left = 14`, `right = W - 14`, `cellW = (right - left) / 7`. Rows:
  `rows = ceil((offset + daysInMonth) / 7)` (4 to 6), with
  `offset = (weekdayOf(first) - cfg.firstDay + 7) % 7`. `cellH = (gridBottom - gridTop) / rows`.
- Grid: vertical lines at the cell boundaries, horizontal lines between rows (`Grid` meter,
  `fmtHalf`), plus the separator under the weekday names. No time gutter.
- **Day number:** 9 pt, centred at `(cellX + cellW/2, cellY + 14)`. Colour `cfg.dayNum`, or
  `cfg.muted` for days outside the month. Today is in `cfg.todayText` on `TodayCircle`
  (radius 12 here). The 1st of each month also shows the month: `d .. ' ' .. usub(lang.months[m], 1, 3)`.
- **Lines:** `lineCap = floor((cellH - 30) / 18)`. Items in Google order: all-day first (`adOrder`,
  tasks last), then timed items by start. A timed event is listed only on its start day. If
  `#items > lineCap`, the last line is `+N more` (`N = #items - (lineCap - 1)`), muted, 8 pt.
  - all-day / task: chip `x + 4 … x + cellW - 4`, 16 px tall, radius `min(cfg.radius, 4)`, colour
    `cfg.colors[feed]` (`pastColors` when over or done). Text `cfg.evText` (or `cfg.pastText`),
    8 pt, at `x + 10`. Tasks keep their `○` / `✓` glyph. Completed tasks are struck through
    (same `InlinePattern` as `ADTx`).
  - timed: dot (ellipse radius 3.5, feed colour) at `x + 10`, then `hh:mm Title` in `cfg.dayNum`
    (`cfg.muted` if over), 8 pt, at `x + 18`. Declined: dot outlined (stroke only), text muted.
  - every line: `wrapText(text, (lineW) / (8 * 4/3 * 0.5), 1)`, tooltip and click actions
    **identical to the week view**. Factor out the tooltip builders from `layout()` first
    (`allDayTip(it)`, `timedTip(it)`), and use `clickActions(it)` for left and middle clicks.
  - `+N more` line: tooltip lists the hidden items. Click → `SetView('day', thatDay)`.
- **Cell background click** (anywhere not on a line) and **day number click** →
  `SetView('day', thatDay)`, which is the natural drill-down. Middle click → `dayLink(thatDay)`.
- Wheel over the grid → previous / next month. `ScrollHours` must delegate to `ShiftView`
  in month view, because `[Rainmeter] MouseScrollUpAction` calls `ScrollHours`.

### Meters (new pools in the `.ini`, after the `HidDn*` meters and before `NowLine`)

| Pool | Count | Type | Role |
| :--- | :--- | :--- | :--- |
| `MHit1..42` | 42 | Shape | transparent cell hit area, tooltip = date |
| `MNum1..42` | 42 | String, `CenterCenter`, 9 pt | day number |
| `MShp1..42` | 42 | Shape (`Shape`, `Shape2`, … one per line) | chips and dots of the cell |
| `MLn1..210` | 210 | String, `LeftCenter`, 8 pt, `StyClip` | one per item line (42 × 5 lines max) |

Order matters: `MHit` first (bottom), then `MShp`, `MNum`, `MLn` (top, they get the item
clicks). `MONTH_LINES = 210`. If a cell's `lineCap` × the cells would exceed the pool, lower
`lineCap` for every cell (a huge skin size is the only way to get there). Unused `ShapeN`
options of `MShp` are reset to an empty rectangle, as `Grid` does.

### Steps

1. Generate the pools; add `MONTH_LINES` and the cell constants.
2. A `hideWeekMeters()` helper (`EvBg/EvT/EvD`, `ADBg/ADTx/ADChk`, `HL*`, `HidUp*/HidDn*`,
   `BtnUp/DownHour*`, `TzLabel`, `TbWeek*`) and a `hideMonthMeters()` helper. `layout()`
   calls the one for the inactive mode. Remember that the `used.*` counters must be reset
   when switching mode.
3. `layoutMonth()` (separate function, called from `layout()` after the shared toolbar and
   background code). Uses `rangeInstances(gridStart, rows * 7)`.
4. `updateNowLine()` hides the line in month view.
5. Toolbar title "October 2026" (the shown month, not the grid range). Week badge hidden.
6. Docs: README Features and Controls ("Click a day to open it", "wheel: months").

### Tests (Phase B)

`View=month` with `layout.ics` and `tasks.ics`:

- March 2027 (1 March is a Monday, `FirstDay=1`): 5 rows. February 2027: 4 rows. August 2027
  (starts on a Sunday): 6 rows. Check the grid lines count or the `MHit36` visibility.
- 4 March cell: 5 all-day items → `lineCap` lines with a `+N more` line. Its click action calls
  `SetView('day', <day of 4 March>)`.
- A timed event line has `clickActions` (the same `LeftMouseUpAction` as in week view) and the
  same tooltip as `EvBg`.
- Today's number uses `cfg.todayText` and `TodayCircle` is centred on it. Days outside the
  month are `cfg.muted`.
- Week meters are hidden in month view and month meters in week view (`mock.shown`).
- `ScrollHours(1)` in month view → April. `GoToday()` → current month.
- Pixel snapping test and `check_clean()` pass.

## Out of scope (only if asked later)

- Multi-day events drawn as continuous bars across cells in month view. This needs per-week
  lane assignment and String meters spanning cells. v1 repeats the chip in each cell, which
  is readable.
- Task check buttons in month view (they stay in day / 3-day / week).
- Animations between views.

## Done when

The tests pass. In the real skin, the switcher changes view instantly, survives a skin
refresh, and the month view looks right in both themes at 1400×800 and with
`Width=1100`. Check that the short labels kick in.
