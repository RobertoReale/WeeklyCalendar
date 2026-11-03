# Plan: quick "Go to date" and live event/task search from the toolbar

Status: designed, not built. Written for the developer (or Claude session) who builds it.
Base: v1.23.0 (commit 2574c75). Read `docs/plans/README.md` first: every convention there
applies, and each one has already caused a bug once.

## 1. Goal

To check an exam, appointment or task weeks or months away, or to find when something is
scheduled, the user currently has to scroll week by week (or switch to the Month view and scroll
months). The user asked in Italian for a way to type and find a task or event (*"una funzione
cerca task o attività, tipo che posso scrivere per trovare l'impegno, ma che sia realizzata per
bene graficamente"*).

What they get:

- **One-click access from the toolbar** (clicking the month/year title `TbTitle`, e.g.
  *"October – November 2026"*, or the week badge `TbWeekBg` / `TbWeek`, or selecting
  *Search / Go to date...* / *Cerca / Vai a data...* in the context menu) opens a polished
  **Search & Jump** card (`mode = 'find'`) anchored right below `TbTitle`;
- **Google Calendar-style search bar** at the top of the card: a rounded pill with a magnifying
  glass icon on the left, the `MeasureCreateInput` text box inside, and a `×` clear button on the
  right when text is present;
- **Rich initial state (before typing):** a row of quick-jump pills (*Today*, *Next week*, *Next
  month*) followed by an *Upcoming* section showing up to 5 next events and open tasks with their
  color indicator and date/time badge;
- **Live search as you type** (via the `@Resources\ZOrder` helper, plus Enter fallback when the
  helper is not running): typing 1+ characters immediately filters events and tasks across all
  loaded feeds (and recurring series over a 1.5-year window) by title, location, and
  notes/description;
- **Flexible date jump in the same box:** typing a date or month name (`15/12`, `15 dec`,
  `2027-01-20`, `marzo 2027`, `mon`, `+14`) shows a highlighted top action row
  *→ Go to Friday, 15 December 2026* (and still lists any events whose title/notes match the
  text below it);
- **Keyboard and mouse navigation:** **Up / Down** arrows (or mouse hover) move the selection
  highlight across the rows; **Enter** (or a click) either jumps to the parsed date or jumps the
  calendar to the chosen event/task's day, scrolls its hour into view if needed, and **opens its
  detail card** right on the item.

## 2. Opening the card: toolbar (`TbTitle` / `TbWeekBg`) and context menu

### A. `TbTitle` and `TbWeekBg` click vs drag

In `WeeklyCalendar.ini`:

- `[TbTitle]`, `[TbWeekBg]` and `[TbWeek]` currently have no mouse click actions so pressing and
  dragging them moves the skin.
- As documented in `docs/plans/README.md` (*"A meter with only a `LeftMouseUpAction` gets the
  click and still drags the skin (the release after a drag does not run it): the minimized tile
  (`MiniBg`) uses that"*):
  - give `[TbTitle]`, `[TbWeekBg]` and `[TbWeek]` **only**
    `LeftMouseUpAction=[!CommandMeasure MeasureScript "FindOpen()"]`,
    `MouseOverAction=[!CommandMeasure MeasureScript "TipOver('#CURRENTSECTION#')"]`,
    `MouseLeaveAction=[!CommandMeasure MeasureScript "TipLeave('#CURRENTSECTION#')"]`, and
    `MouseActionCursorName=Hand` (do **not** add `StyItem` or `LeftMouseDownAction`, so pressing
    and dragging the title or week badge still moves the skin window);
  - in `layoutToolbar`, register the tooltip on `TbTitle` and `TbWeekBg`:
    `setTip('TbTitle', tips.find, titleX, cy - 16, titleW, 32)` and
    `setTip('TbWeekBg', tips.find, wkX, cy - 11, wkW, 22)`;
  - store `cfg.findAnchor = { x0 = titleX, x1 = titleX + titleW, y = cy - 16, h = 32 }` in
    `layoutToolbar` so `FindOpen()` knows where to anchor the card.

### B. Context menu

Add *Search / Go to date...* (*Cerca / Vai a data...*) right after *Today (Current week)* in
`[Rainmeter]` and `LANGS.en.ctx` / `LANGS.it.ctx`:

- `ContextTitle3=Search / Go to date...`
- `ContextAction3=[!CommandMeasure MeasureScript "FindOpen()"]`
- Shift the subsequent `ContextTitle4..15` / `ContextAction4..15` by 1. Keep *Minimize* last
  (`mini.ctx()` uses `#ctx`). Update `test_italian_translation_and_context_menu` accordingly.

## 3. Live typing and keyboard navigation (`ZOrderHelper.cs`)

The `MeasureCreateInput` plugin only passes `$UserInput$` to Rainmeter when the user presses
Enter (`Command1`), and dismisses the box on Esc or when the user clicks a result row.
`@Resources\ZOrder\ZOrderHelper.cs` already solves both problems for `PlaceSuggestions`
(`Places.txt`, `PlacesTick`, and the low-level keyboard hook `OnKey` on its own thread).

Extend `ZOrderHelper.cs` with a lightweight live-find channel (`Find.txt`) that reuses the
existing 40 ms `typing` timer and `Hook` thread:

1. **`ZOrder\Find.txt` lifecycle (in `Calendar.lua`):**
   - `edit.findFile(n, rows)` writes `<config>\n<boxN>\n<rowCount>` to `@Resources\ZOrder\Find.txt`
     when `edit.openBox` opens `MeasureCreateInput` for `field == 'q'` (and whenever the number
     of selectable rows in the `find` card changes); `edit.findFile(nil)` deletes it (called from
     `edit.typedTake()` and `CardClose()`).
2. **`FindTick(IntPtr box, string text)` (in `ZOrderHelper.cs`):**
   - Called from `CopyTyped()` right after `Typed.txt` has been updated with `"WC\n" + text`.
   - Reads `Find.txt` (cached by content like `ReadPlaces()`). If absent, calls `FindEnd()` and
     returns.
   - When `text != fnText` (the user typed or deleted a character):
     - updates `fnText = text` and schedules `fnDue = (Environment.TickCount + 60) | 1` (a 60 ms
       micro-debounce so fast typing coalesces into a single skin redraw);
   - When `fnDue != 0 && Due(fnDue)`:
     - clears `fnDue = 0` and sends:
       `Bang(string.Format("!CommandMeasure MeasureScript \"FindLive({0})\" \"{1}\"", fn.n, fn.config))`
   - Keeps `Hook(fn.rows > 0)` active while the find box has focus and rows are shown.
3. **`OnKey` / `FindKey(int vk)` (in `ZOrderHelper.cs`):**
   - When `fn != null` and `FocusOf(...) == fnBox`:
     - **Down (`0x28`) / Up (`0x26`):** consumes the key (`return true` so the WinForms text box
       does not move the caret to the start/end of the string) and posts:
       `Bang(string.Format("!CommandMeasure MeasureScript \"FindStep({0}, {1})\" \"{2}\"", fn.n, vk == 0x28 ? 1 : -1, fn.config))`
     - **Enter (`0x0D`)** and **Esc (`0x1B`):** return `false` so the `InputText` plugin handles
       them natively (`Command1 -> CreateSubmit(n)` for Enter; `OnDismissAction -> CreateInputClosed(n)`
       for Esc).
4. **Bump helper executable version:**
   - In `@Resources\ZOrder\launch.cmd`, bump `WeeklyCalendarZOrder7.exe` to
     `WeeklyCalendarZOrder8.exe` so Rainmeter compiles the updated `ZOrderHelper.cs` on first load.

## 4. Visual design of the `find` card (`buildFind(c)`)

State in `edit.card`:

```lua
{
  mode = 'find',
  q = '',            -- current search query string
  sel = 1,           -- highlighted row index (1..#rows, or 0)
  rows = {},         -- computed clickable rows (date jump + matching items, or upcoming items)
  pool = nil,        -- cached search instance list for dataVersion
  poolVer = nil,     -- dataVersion when pool was built
  inputOpen = true,  -- MeasureCreateInput is open on field 'q'
  openInput = true,
   inputField = 'q',
  anchor = ...       -- toolbar title rectangle
}
```

### A. Card geometry and placement

- **Width:** `W = 380` px.
- **Placement (`placeCard`):** in `layoutCard()`, when `c.mode == 'find'`, place the card
  directly below the toolbar rather than beside the anchor:
  - `x = math.max(8, math.min(cfg.W - 8 - s.w, (c.anchor and c.anchor.x0 or 180) - 12))`
  - `y = (cfg.toolbar and 56 or 8)`
  - Clamp `y + s.h <= (edit.shownH or cfg.H) - 8`.

### B. Top search bar (`y = 14..50`)

- **Pill background shape:**
  `shRect(16, 14, W - 32, 36, 18, cfg.badgeBg)` with a border stroke
  (`1.5 px` in `cfg.today` while `cf.typing(c, 'q')`, otherwise `1 px` in `cfg.border`).
- **Magnifying glass icon** at `(cx = 34, cy = 32)` drawn with 2 shapes:
  - circle: `'Ellipse ' .. (33 + CARD_M) .. ',' .. (31 + CARD_M) .. ',5.5,5.5 | Fill Color 0,0,0,0 | StrokeWidth 1.6 | Stroke Color ' .. cfg.muted`
  - handle: `shLine(37, 35, 41.5, 39.5, cfg.muted, 1.6)`
- **Input text / placeholder (`x = 50, y = 16, w = W - 92, h = 32`):**
  - When `cf.typing(c, 'q')` is false, shows `c.q ~= '' and safe(c.q) or L.findPlaceholder`
    (`"Search events, tasks or type a date..."` / `"Cerca impegni, task o scrivi una data..."`)
    at `size = 10`, color `c.q ~= '' and cfg.dayNum or cfg.muted`, `act = cmd("CardField('q')")`,
    `cursor = 'Text'`.
  - When `cf.typing(c, 'q')` is true, `s.inputs = { q = { x = 48, y = 19, w = W - 90, h = 26, size = 10, bg = cfg.badgeBg } }`.
    In `layoutCard()`, use `r.size or (field == 'title' and 13 or 9)` and
    `r.bg or cfg.card` for `MeasureCreateInput`'s `FontSize` and `SolidColor` so the Windows
    text box blends seamlessly into the rounded pill!
- **Clear (`×`) button** (shown when `c.q ~= ''` at `x = W - 44, y = 16, w = 26, h = 32`):
  - `text = '×'`, `size = 13`, `align = 'CenterCenter'`, `color = cfg.muted`,
    `act = cmd('FindClear()')`, `tip = L.findClear`.

### C. Empty-query state (`c.q == ''`)

1. **Quick-jump chips row (`y = 58, h = 26`):**
   Three compact rounded pill chips (`shRect(x, 58, chipW, 24, 12, cfg.badgeBg)`):
   - *Today* / *Oggi* (`act = cmd('FindGo(' .. todayDay .. ')')`)
   - *Next week* / *Prossima settimana* (`act = cmd('FindGo(' .. (todayDay + 7) .. ')')`)
   - *Next month* / *Prossimo mese* (`act = cmd('FindGo(' .. nextMonthDay .. ", 'month')")`)
2. **Section label (`y = 92, h = 18`):**
   - `L.findUpcoming` (`"Upcoming"` / `"Prossimi impegni"`), `size = 8`, `weight = 600`,
     `color = cfg.muted`, at `x = 20`.
3. **Rows (`y = 112..`):**
   - Up to **5 upcoming items** (`c.rows` populated by `edit.upcomingSearchRows(todayDay, nowEpoch, 5)`).
   - If there are no upcoming items in the next year, show a single muted line `L.findHint`
     (`"Examples: 15/12, marzo 2027, +14, dentist, exam"` /
     `"Esempi: 15/12, marzo 2027, +14, dentista, esame"`).

### D. Active-query state (`c.q ~= ''`)

`c.rows` contains up to **6 entries** (at most 1 `'date'` row + up to 5 `'item'` rows, or up to
6 `'item'` rows when the query is not a date):

1. **Date-jump row (`row.kind == 'date'`, `rh = 36`):**
   - Appears at row 1 whenever `edit.parseDate(c.q, anchor or todayDay, todayDay)` succeeds.
   - Left icon (`x = 26`): a small right arrow `→` or calendar icon in `cfg.today`.
   - Label (`x = 42`): `L.findGoTo .. ' ' .. row.label` (e.g. *"Go to Tue 15 Dec 2026"* /
     *"Vai a mar 15 dic 2026"*, or *"Go to March 2027"* / *"Vai a marzo 2027"* when a month
     name alone was typed), `size = 9.5`, `weight = 600`, `color = cfg.today`.
   - Right badge: `'↵'`, `size = 9`, `color = cfg.muted`.
2. **Event / Task result rows (`row.kind == 'item'`, `rh = 40`):**
   - **Selection / hover background (`k == c.sel`):**
     `shRect(12, rowY, W - 24, rh, 8, cfg.sel)` (recorded as the last shape of `CrCard` or at a
     known shape index `c.selShapeIdx` so `edit.drawFindSel()` can update just that one shape on
     hover or Up/Down key press without rebuilding the card!).
   - **Color indicator at `x = 26, cy = rowY + rh / 2`:**
     - **Timed or all-day event (`not it.task`):** `shDot(26, cy, 5, color)` where `color` is
       `colStr(cfg.colors[it.feed] or cfg.colors[1])`.
     - **Task (`it.task`):** `shRect(21, cy - 5, 10, 10, 2.5, color)` (filled when open;
       faded `cfg.pastColors[it.feed]` when `it.task == 'done'`).
   - **Right-aligned date & time label (`x = W - 20 - dateW, y = rowY, w = dateW, h = rh`):**
     - Concise, human-friendly date + time (`edit.findWhenLabel(it, row.day, todayDay)`):
       - Today: `"Today · 14:30"` / `"Oggi · 14:30"` (or `"Today"` / `"Oggi"` for all-day/tasks),
         colored in `cfg.today` with `weight = 600`;
       - Tomorrow / Yesterday: `"Tomorrow · 09:00"` / `"Domani · 09:00"`;
       - Same year: `"14 Nov · 15:00"` / `"14 nov · 15:00"` (or `"14 Nov"` for all-day/tasks);
       - Different year: `"15 Mar 2027"`.
   - **Left title + optional subtitle (`x = 40, y = rowY, w = W - 68 - dateW, h = rh`):**
     - If the row has a subtitle (`row.sub`, e.g. the event's location, or a snippet from the
       notes/description when the query matched there, or `"Completed"` / `"Completata"` for a
       done task), format a 2-line `CrTx` element:
       `titleLine .. '#CRLF#' .. subLine` at `size = 9`, where both lines are clipped with
       `wrapText(..., 1)[1]`.
     - Otherwise, a single-line `CrTx` element with `titleLine` at `size = 9.5`, `weight = 500`,
       `color = (it.task == 'done') and cfg.muted or cfg.dayNum`.
     - Clicking the row runs `act = cmd('FindPick(' .. k .. ')')`.
     - Its tooltip (`e.tip`) shows the full untruncated title, full date/time (`whenText(it)`),
       and location if any.
3. **No-results state (`#c.rows == 0`):**
   - Centered text `L.findNone` (`"No matching events or tasks"` /
     `"Nessun impegno o attività trovata"`) at `y = 66, h = 28`, `size = 9.5`, `color = cfg.muted`,
     followed by `L.findHint` at `y = 94, h = 20`, `size = 8`, `color = cfg.muted`.

### E. Pool usage check (`CR_TX = 20`, `CARD_SHAPES = 32`)

Count the worst-case elements in `buildFind(c)`:

- **Texts (`CrTx`):**
  - Search input text: 1
  - Clear `×` button: 1
  - Quick chips (3) + Upcoming header (1) when `q == ''`: 4 (or 0 when `q ~= ''`)
  - Up to 6 rows × 2 texts (left title/subtitle + right date/time badge): 12
  - Footer / Close button (optional, or Esc/click outside): 1
  - **Total texts:** at most **15** (well within `CR_TX = 20`).
- **Shapes (`CrCard`):**
  - Card shadow + body: 4
  - Search pill background + magnifying glass (circle + handle): 3
  - Quick chips (3) when `q == ''`: 3
  - Selection highlight rectangle: 1
  - Up to 6 row dots / task squares: 6
  - **Total shapes:** at most **17** (well within `CARD_SHAPES = 32`).

No new meters need to be added to `WeeklyCalendar.ini`!

## 5. Search Engine (`edit.searchItems`) and Date Parser (`edit.parseDate`)

### A. Building and caching the search pool (`edit.searchPool(c, todayDay)`)

Expanding recurring events over 1.5 years takes ~2 ms in Lua; caching it on `c.pool` (invalidated
only if `c.poolVer ~= dataVersion`) makes every keystroke take **< 0.3 ms**:

1. Start with `buildInstances(todayDay - 180, todayDay + 365)` (which includes local edits in
   `edit.changes`, optimistic creations, and pending task changes).
2. Also scan the raw `events` table for any **non-recurring** event or task (`not ev.rrule`) whose
   day falls outside `[todayDay - 180, todayDay + 365]` (for example an exam or trip 18 months
   ahead or a past record from last year), convert it via `makeInstance`, and append it to
   `c.pool`.

### B. Query normalization, matching, and ranking (`edit.searchItems(c, query, todayDay, maxRows)`)

1. **Normalization (`normSearch(s)`):**
   - Lowercase ASCII and fold common UTF-8 accented characters (`àáâä -> a`, `èéêë -> e`,
     `ìíîї -> i`, `òóôö -> o`, `ùúûü -> u`, `ç -> c`, `ñ -> n`) and collapse whitespace.
   - Split the normalized query into tokens (`tokens`). If `#tokens == 0`, return `{}`.
2. **Matching each item in `c.pool`:**
   - Skip `it.declined` when `not cfg.showDeclined`.
   - Normalize `it.title`, `it.loc or ''`, and `cleanDesc(it.desc or '')`.
   - Every token in `tokens` must appear in at least one of `titleNorm`, `locNorm`, or `descNorm`.
   - Compute a **match tier**:
     - `tier = 1`: `titleNorm` starts with the full query or a word in `titleNorm` starts with
       `tokens[1]`;
     - `tier = 2`: all tokens appear in `titleNorm`;
     - `tier = 3`: match uses `locNorm`;
     - `tier = 4`: match uses `descNorm`.
   - Build the row's subtitle `sub`:
     - if a token matched in `locNorm` (or if `it.loc` is non-empty), use `it.loc`;
     - else if a token matched in `descNorm`, extract the matching line from `cleanDesc(it.desc)`;
     - else if `it.task == 'done'`, use ` cfg.lang.card.taskDone`.
3. **Deduplicating recurring series:**
   - Group occurrences of the same recurring event (`it.rec` or `it.uid .. '|' .. it.feed`).
   - For each series, prefer the **first upcoming occurrence** (`day >= todayDay`); if all
     occurrences are in the past, keep the **most recent past occurrence** (`day < todayDay`).
4. **Sorting results:**
   - Upcoming/today items (`day >= todayDay`) come before past items (`day < todayDay`), unless a
     past item has `tier == 1` and is within the last 7 days while the upcoming item is `tier >= 3`.
   - Among upcoming items: sort by `tier` ascending, then `(day - todayDay)` ascending, then start
     time `s` ascending.
   - Among past items: sort by `tier` ascending, then `(todayDay - day)` ascending (most recent
     first).
   - Return the top `maxRows` results.

### C. Extending `edit.parseDate(text, base, today)` for month names alone

In `edit.parseDate`:

- Currently, when `#nums == 0` (line 5089), only a single weekday word (`#words == 1 and words[1].wd`)
  is accepted.
- Extend that branch and add a 1-number + 1-month-name year branch:
  - **Month name alone** (`#nums == 0 and #words == 1 and words[1].mon`):
    pick the first occurrence of that month from `today`'s month onwards (i.e. `by` if
    `m >= bm`, else `by + 1`), and return `daysFromCivil(y, m, 1), 'month'`.
  - **Month name + 4-digit year (or 2-digit year > 31)** (`#nums == 1 and #words == 1 and words[1].mon`
    where `#nums[1] == 4` or `tonumber(nums[1]) > 31`):
    treat `nums[1]` as the year `y` (`2000 + y` if `< 100`) and return
    `daysFromCivil(y, words[1].mon, 1), 'month'`.
- All existing callers of `edit.parseDate(text, base, today)` only use the first return value
  (`local day = edit.parseDate(...)`), so returning `'month'` as a second value is 100%
  backwards-compatible!

## 6. Actions and Navigation (`FindOpen`, `FindLive`, `FindStep`, `FindSubmit`, `FindGo`, `FindPick`)

Put the implementation inside the cards' `do ... end` block and expose small global entry points:

1. **`FindOpen()`:**
   - If `edit.mini` is true, call `MiniRestore()` first.
   - Build the initial `find` card (`q = ''`, `sel = 1`), compute the initial `c.rows` (upcoming
     items), and call `openCard(c)`.
   - `layoutCard()` opens `MeasureCreateInput` on field `'q'` and writes `ZOrder\Find.txt`.
2. **`FindLive(n)`:**
   - Called by `ZOrderHelper` while the user types in box `n`.
   - Reads `ZOrder\Typed.txt` (without deleting it! Add `edit.typedPeek()` which reads
     `s:match('^WC\n(.*)$')` from `Typed.txt`).
   - Updates `c.q = edit.cleanText(typed, true)`, recomputes `c.rows`, resets `c.sel = (#c.rows > 0) and 1 or 0`,
     updates `ZOrder\Find.txt` with `#c.rows`, and calls `refreshCard()` **without** closing or
     re-opening `MeasureCreateInput` (since `c.openInput` is `nil` while `edit.box` is open!).
3. **`FindStep(n, d)` and hover (`TipOver` / `TipLeave`):**
   - `FindStep(n, d)` moves `c.sel` by `d` (`±1`), wrapping around `1..#c.rows`, and calls
     `edit.drawFindSel()`, which updates only the selection shape on `CrCard` (`!UpdateMeter CrCard`,
     `!Redraw`) in ~1 ms!
   - In `TipOver(meter)`, if `edit.card and edit.card.mode == 'find'` and `edit.card.rowMap[meter]`,
     set `c.sel = edit.card.rowMap[meter]` and call `edit.drawFindSel()`.
4. **`FindClear()`:**
   - Takes and closes the open box if needed (`edit.takeOpenBox(c)`), sets `c.q = ''`, recomputes
     upcoming `c.rows`, sets `c.inputOpen, c.openInput, c.inputField = true, true, 'q'`, and calls
     `refreshCard()`.
5. **`FindSubmit()` (called from `edit.submit(b)` when `c.mode == 'find'`):**
   - Updates `c.q = edit.cleanText(typed, true)` and recomputes `c.rows`.
   - If `c.sel >= 1` and `c.rows[c.sel]` exists (or if `#c.rows == 1`):
     immediately triggers `FindPick(c.sel)`!
   - Otherwise (e.g. when the user typed without the helper running and multiple results matched,
     or nothing matched): keeps the card open showing the results so the user can click one (or
     press Enter again).
6. **`FindGo(day, kind)`:**
   - Closes the open box (`edit.takeOpenBox(c)`), closes the card (`edit.card = nil`), sets
     `anchor = tonumber(day)` (or `nil` if `day == todayDay`), resets `userScrollH = nil`, and
     runs `safeLayout()` + `updateNowLine()`.
7. **`FindPick(k)`:**
   - Picks `row = c.rows[tonumber(k)]`.
   - If `row.kind == 'date'`, calls `FindGo(row.day, row.dateKind)`.
   - If `row.kind == 'item'`:
     - Jumps `anchor` to `row.day` (`setAnchor(row.day, todayDay)`).
     - If `view ~= 'month'` and `row.it.kind == 'timed'`, adjusts `userScrollH` only if the
       event's start hour falls outside the default visible hours so the event box is guaranteed
       to be visible on screen!
     - Clears `edit.card = nil` and runs `safeLayout()` + `updateNowLine()`.
     - Locates the rendered meter rectangle for `row.it` in `edit.items.ev`, `edit.items.ad`, or
       `edit.items.ml` (matching `ci.it.uid == row.it.uid and ci.it.feed == row.it.feed` on
       `row.day`; falling back to the day column's header rectangle if the slot is collapsed in
       a `+N more` chip), and calls:
       `openCard({ mode = 'detail', it = row.it, anchor = foundAnchor })`!

## 7. Interactions and edge cases to take care of

- **Clicking a result row while `MeasureCreateInput` is open:**
  As documented in `docs/plans/README.md`, clicking outside the `InputText` box dismisses it and
  runs `OnDismissAction` (`CreateInputClosed(n)`), or on a touchpad tap the click action
  (`FindPick(k)` / `FindGo(day)`) runs *before* `CreateInputClosed(n)`.
  - In `edit.inputClosed` (inside `CreateInputClosed(n)`): when `c.mode == 'find'`, set
    `c.inputOpen, c.inputField = false, nil`, update `c.q` from `copied` if non-empty, and refresh
    the card — **never** close `edit.card` on input dismissal unless the user clicked `CrDismiss`!
  - In `FindPick`, `FindGo`, and `FindClear`: always call `edit.takeOpenBox(c)` first so a fast
    touchpad tap cleanly claims the open box before opening the detail card.
- **200-locals limit in `Calendar.lua`:**
  Put all new helpers (`normSearch`, `searchPool`, `searchItems`, `findWhenLabel`, `buildFind`,
  `drawFindSel`) inside the existing cards `do ... end` block or as methods on `edit`. Check
  `test_lua_main_chunk_has_room_for_locals`.
- **All strings through `safe()` and both languages (`LANGS.en` and `LANGS.it`):**
  Event titles, locations, and description snippets in `buildFind` must pass through `safe()`.
  Add all new strings (`findPlaceholder`, `findUpcoming`, `findGoTo`, `findNone`, `findHint`,
  `findClear`, `tips.find`, `ctx` item) to both `LANGS.en` and `LANGS.it`.
- **Integer coordinates (`fmt()`):**
  Every `X`, `Y`, `W`, `H` of `CrCard` and `CrTx1..20` in `buildFind` must be integer-snapped so
  `test_pixel_snapped_coordinates_and_sharp_grid` passes.

## 8. Tests (`tests/run_tests.py`)

All new tests use the `Skin` harness and end with `check_clean()`.

1. **`test_tb_title_opens_find_card_and_keeps_skin_draggable`:**
   - verify `[TbTitle]`, `[TbWeekBg]` and `[TbWeek]` have `LeftMouseUpAction` calling `FindOpen()`
     and **no** `LeftMouseDownAction`;
   - call `FindOpen()`, verify `CrCard` is visible and `MeasureCreateInput` opened.
2. **`test_find_card_initial_state_shows_quick_jumps_and_upcoming`:**
   - load `sample.ics` and `tasks.ics`, call `FindOpen()`;
   - verify the quick-jump chips (*Today*, *Next week*, *Next month*) and upcoming items are
     displayed, all coordinates are integers, and no `card too big` error is logged.
3. **`test_find_card_jumps_to_date_on_enter`:**
   - call `FindOpen()`, submit `"15/12/2026"` via `MeasureCreateInput`;
   - verify `anchor` moved to the week containing `2026-12-15` and the card closed.
4. **`test_find_card_parses_month_name_alone`:**
   - call `FindOpen()`, submit `"marzo 2027"` and `"march 2027"`;
   - verify `edit.parseDate` and `FindSubmit` jump to `2027-03-01`.
5. **`test_find_card_live_search_matches_events_and_tasks_and_opens_detail`:**
   - load `sample.ics` and `tasks_v2.ics`, call `FindOpen()`;
   - simulate live typing (`Typed.txt` + `FindLive`) for an event title, a location word, and a
     task title (including case/accent-insensitive matching);
   - verify `c.rows` lists the matching items with their color dot / task square and date label;
   - call `FindStep(n, 1)` to move selection, then `FindPick(k)` and verify the calendar jumped to
     the item's date and opened `mode == 'detail'` for that item.
6. **`test_find_card_deduplicates_recurring_events`:**
   - load a feed with a weekly recurring event, search its title;
   - verify only the next upcoming occurrence is listed rather than filling all 6 rows.

## 9. Live checks (`tools\LiveTest.ps1`)

1. Click `TbTitle` on the live skin, take a screenshot of the initial `find` card (quick jumps +
   upcoming list) in both light and dark themes.
2. Type a partial word in the search box without pressing Enter: verify `ZOrderHelper` triggers
   `FindLive` and the matching events/tasks appear live as you type.
3. Press Down / Up arrows to move the highlight across rows, then press Enter: verify the skin
   jumps to that week and opens the item's detail card.
4. Re-open `TbTitle`, type `marzo 2027`, verify the *→ Vai a marzo 2027* row appears at the top,
   and press Enter to jump.
5. Check `%APPDATA%\Rainmeter\Rainmeter.log` for zero errors or warnings.

## 10. Ship checklist

- `README.md`:
  - Features list: add *Quick search & Go to date*;
  - Controls table: document clicking the month/year title (or week badge) to search events/tasks
    or jump to a date.
- `docs/plans/README.md`: remove `quick-jump-and-search.md` from the unbuilt list once shipped.
- `Version=` in `[Metadata]` of `WeeklyCalendar.ini`: bump to `1.24.0`.
- Refresh the live skin (`"C:\Program Files\Rainmeter\Rainmeter.exe" !Refresh WeeklyCalendar`) and
  check `%APPDATA%\Rainmeter\Rainmeter.log`.

## 11. Suggested order of work

1. Extend `edit.parseDate` for standalone month names (`marzo`, `marzo 2027`, `march`) + unit test.
2. Add `edit.searchPool`, `edit.searchItems`, and `edit.upcomingSearchRows` in `Calendar.lua` +
   unit tests for ranking, accents, tasks, and recurring event deduplication.
3. Build `buildFind(c)`, `edit.drawFindSel()`, and the `FindOpen` / `FindLive` / `FindStep` /
   `FindSubmit` / `FindGo` / `FindPick` / `FindClear` entry points + wire `[TbTitle]`, `[TbWeekBg]`,
   `[TbWeek]` and the context menu in `WeeklyCalendar.ini`.
4. Extend `ZOrderHelper.cs` with `Find.txt` (`FindTick` + `OnKey` Up/Down) and bump `launch.cmd`
   to `WeeklyCalendarZOrder8.exe`.
5. Run all unit tests (`python tests/run_tests.py`) and live checks (`tools\LiveTest.ps1`).
