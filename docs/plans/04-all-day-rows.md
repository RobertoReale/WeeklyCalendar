# Plan 4: taller all-day row, expandable like Google Calendar

Goal: busy days (several tasks plus events) should not hide items behind "+N more". There
are two parts:

1. A setting for how many rows the all-day band shows normally.
2. Clicking "+N more" expands the band to show everything, and a ▲ button collapses it again.
   This is what Google Calendar does in week view.

Read [the conventions](README.md#conventions-that-apply-to-every-plan) first.

## Current behaviour (what to change)

In `layout()`, block "All-day events and tasks":

- At most 3 chips per day (`math.min(3, n)`). When `n > 3`, chip 3 becomes `'+' .. (n - 2) .. ' ' .. lang.more`.
  Its tooltip lists the hidden items, and its left click opens the day in Google Calendar
  (`dayLink(ws + i)`).
- Band height `adH = maxAD * 22 + 8` (`maxAD` capped at 3). The chip in row `r` sits at
  `y = tb + hdr + 3 + (r - 1) * 22`, is 20 px tall and leaves a 2 px gap.
- Pools: `AD_POOL = 21` (7 days × 3), with meters `ADBg1..21` / `ADTx1..21` / `ADChk1..21` in the `.ini`.

## Design

- **`AllDayRows=3`** (Settings.inc, range 1-10, default 3 = today's look): the rows shown
  when collapsed.
- **Collapsed:** as today, with `rows = AllDayRows`. When a day has more items than `rows`,
  its last row is "+N more" with `N = n - (rows - 1)`.
- **"+N more" left click → expand** (replaces the day link; the middle click keeps
  `dayLink`, so set `MiddleMouseUpAction` on that chip).
- **Expanded:** `rows = min(max items of any shown day, cap)`. The cap keeps the hour grid
  usable: the band takes at most 40% of the space below the day headers,
  `cap = max(AllDayRows, floor((gridBottom - (tb + hdr)) * 0.4 / 22))`, and is also
  limited by the pool (10 rows). If a day still overflows, its last row is "+N more" again
  (expanding again is a no-op).
- **Collapse button:** a ▲ in the time gutter, in the band's first row: `x = timeW/2 - 12`,
  `y = tb + hdr + 3`, `24×20`, glyph `ARROW_UP` in `cfg.muted` at 7.5 pt, transparent hit
  shape (`Fill Color 0,0,0,1`), tooltip `lang.collapse` ("Show fewer" / "Mostra meno"). Show
  it only while expanded and only if some shown day has more than `AllDayRows` items. It
  cannot collide with `BtnUpHour` (at `gridTop - 25`), because an expanded band is at least
  2 rows (52 px) tall.
- The state `adExpanded` lives in the Lua only: it survives week navigation and resets on skin
  refresh. While expanded, a week without overflow simply shows its natural height.
- No animation (Rainmeter would need a redraw loop; not worth it).

## Steps

1. **Constants and pools:** `MAX_AD_ROWS = 10`, `AD_POOL = 7 * MAX_AD_ROWS` (70). Generate
   `ADBg22..70` / `ADTx22..70` in the same pair format and place them after `ADTx21`. Then
   generate `ADChk22..70` after `ADChk21`: every `ADChk` must stay after every `ADTx`, so the
   check button is above the text.
2. **New meters in the `.ini`** (after the `ADChk` block): `[AdCollapse]` (Shape, hidden),
   `[AdCollapseTxt]` (String, `StringAlign=CenterCenter`, hidden). Both get
   `LeftMouseUpAction=[!CommandMeasure MeasureScript "CollapseAllDay()"]`.
3. **Lua state and settings:** `local adExpanded = false`, `cfg.adRows` clamped to 1..10 in
   `readSettings`.
4. **Lua `layout()`:**
   - compute `maxItems`, then `rows` (collapsed or expanded, as above), then `adH = rows * 22 + 8`
     when any day has items. This replaces the `maxAD` loop.
   - in the per-day loop, `for r = 1, math.min(rows, n)`. The "more" chip is `r == rows and n > rows`.
     Its label is `n - (rows - 1)` and its names start at `k = rows`. Replace every literal `3`
     in that block.
   - "+N more" actions: left `[!CommandMeasure MeasureScript "ExpandAllDay()"]`, middle
     `openAct(dayLink(ws + i))`.
   - show or hide `AdCollapse` / `AdCollapseTxt` as designed. Clear their tooltip when hidden.
5. **Entry points:** `ExpandAllDay()` and `CollapseAllDay()` set `adExpanded`, then call
   `safeLayout(); updateNowLine()`.
6. **Strings:** `collapse` and `expandTip` ("Show all" / "Mostra tutti", appended as the last
   tooltip line of "+N more") in `LANGS.en` and `LANGS.it`.
7. **Docs:** Settings.inc comment for `AllDayRows`; README Features ("All-Day Events") and the
   Controls table ("Click +N more to expand, ▲ to collapse").

## Tests

Update the helpers in `tests/run_tests.py`: `Skin.all_day()` must scan `range(1, 71)`.
Then use `layout.ics`, which has 5 all-day events on Thursday 4 March 2027:

- default: `All day 1`, `All day 2`, `+3 more` (the existing test still passes).
- `AllDayRows=2`: `All day 1`, `+4 more`. `gridTop` is lower than with 3 rows: compare the `Y`
  of the hour label `HL1`.
- `ExpandAllDay()`: all 5 chips shown, `AdCollapse` shown, the "+N more" chip gone, `HL1` moved
  down. `CollapseAllDay()` restores the default view.
- Expanded + `ShiftWeek(1)` to a week without all-day items: band height 0 (no separator line
  at `gridTop`), `AdCollapse` hidden.
- `check_clean()` everywhere (all new meters exist).

## Done when

The tests pass. In the real skin, a day with 5+ tasks expands on click and collapses with ▲.
The hour grid stays readable at the default size (1400×800), and the check buttons still
work on rows 4+.
