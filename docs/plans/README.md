# Implementation plans

Plans for features that are designed but not built yet. Recommended order (each one is
independent and ships on its own):

| # | Plan | Size | Touches |
| :--- | :--- | :--- | :--- |
| 5 | [More calendars (3 → 6)](05-more-calendars.md) | small | Lua loops, ini measures, Settings.inc, README |
| 4 | [Taller all-day row, expandable](04-all-day-rows.md) | medium | all-day layout, ini pools, one new button |
| 7a | [Day and 3-day views + view switcher](07-views.md#phase-a-day-3-day-and-week) | medium-large | layout generalised from 7 to N days, toolbar |
| 7b | [Month view](07-views.md#phase-b-month-view) | large | new layout mode and meter pools |
| 8 | [Drag a task to another day](08-drag-tasks.md) | medium (+ 30 min spike) | all-day chips, drop zones, task pipeline, Apps Script |
| 9 | [Create tasks and events](09-create-items.md) | large | click zones, quick-create card (InputText), task pipeline, Apps Script + Calendar permission |

## Conventions that apply to every plan

These are the traps of this codebase. Each one has already caused a bug once.

- **`@Resources/Calendar.lua` is UTF-16 LE with BOM and CRLF** (Rainmeter 4.5 only treats Lua
  strings as UTF-8 that way). Do not edit it in place with the Edit tool. Convert it to a UTF-8
  copy, edit the copy, then write it back:
  `b'\xff\xfe' + text.replace('\n', '\r\n').encode('utf-16-le')`.
  `tests/run_tests.py::test_lua_file_is_utf16_with_bom` guards this.
- **Backslashes in shell heredocs.** In this environment, heredocs passed to Bash can lose
  backslashes, and Lua patterns like `'^\\S+ (.*)$'` get corrupted. Write helper scripts with the
  Write tool and use Python raw strings (`r"""..."""`) for the replacements.
- **Tests:** `pip install lupa`, then `python tests/run_tests.py`. All tests must pass. The mock
  (`MockSkin`) fails on bangs to sections that do not exist in `WeeklyCalendar.ini`
  (`check_clean()`), so every new meter or measure must be added to the `.ini`. Layout tests
  also require integer `X/Y/W/H` (`test_pixel_snapped_coordinates_and_sharp_grid`): always
  wrap coordinates in `fmt()`. Use `fmtHalf()` for 1px lines.
- **Meter pools.** Meters cannot be created at runtime. Every repeated element is a pool of
  hidden meters in the `.ini` (`ADBg1..`, `EvBg1..`). The pool size constant in the Lua
  (`AD_POOL`, `EV_POOL`) must match the `.ini`. Generate pool sections with a small script,
  never by hand. Z-order is file order: a meter later in the file is drawn above and gets
  the mouse first.
- **Bangs are cached.** `set()`, `show()` and `hide()` skip unchanged values. When a pool item
  is not used, clear its mouse actions and tooltip (`''`) and hide it, as the cleanup loops
  after each pool do. Otherwise a hidden meter keeps acting on stale data.
- **Text into options goes through `safe()`.** `#` starts a Rainmeter variable, `[` `]` are
  section references, and `"` breaks bang quoting. Links drop their `#fragment` (see
  `expandEvent`).
- **Colours come from `cfg`** (theme plus overrides, see `THEMES` and `readSettings`). Never
  hard-code a light-theme colour; new colours need a `light` and a `dark` value in `THEMES`.
- **Strings come from `LANGS.en` and `LANGS.it`.** Add both. Context menu titles are
  `lang.ctx` plus `ContextTitleN` in `[Rainmeter]`.
- **Shapes need some alpha to catch the mouse.** Click areas use `Fill Color 0,0,0,1`, not alpha 0.
- **Ship checklist:** Settings.inc comment for any new setting (with its default),
  README (Features, Configuration, Controls table), `Version=` in `[Metadata]`, tests.
  Then refresh the real skin
  (`"C:\Program Files\Rainmeter\Rainmeter.exe" !Refresh WeeklyCalendar`) and check
  `%APPDATA%\Rainmeter\Rainmeter.log` for errors.
