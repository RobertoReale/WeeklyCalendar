# Implementation plans

Plans for features that are designed but not built yet. There are none open now: the plans of
the features already built (4, 5, 7, 8, and 9-11 in v1.11.0: create, edit / delete, drag
events) were removed when they shipped; git history keeps them.

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
  is not used, clear its mouse actions and tooltip and hide it (`clearMeter()`), as the cleanup
  loops after each pool do. Otherwise a hidden meter keeps acting on stale data.
- **Never set `ToolTipText` on a meter.** Rainmeter creates a window for every meter with a
  tooltip (about 50 ms each, measured), and every update refreshes all of them. Register the
  text and the item's rectangle with `setTip(meter, text, x, y, w, h, z)` and add `StyItem` to the
  meter's `MeterStyle`: the single `[Tip]` meter carries the tooltip of the topmost item (highest
  `z`) under the cursor. `test_one_tooltip_carrier` checks that no other meter has one.
- **Every clickable meter needs a `LeftMouseDownAction`** (`StyItem` gives a harmless one,
  `NO_DRAG` in the Lua): Rainmeter moves the whole skin when the button is pressed where no meter
  has one. `test_pressing_an_item_does_not_move_the_skin` checks the `.ini`.
- **Check interactions with real input:** `tools\LiveTest.ps1` moves the real mouse, presses,
  drags, scrolls and takes screenshots with tooltips (see its header). Use it for anything the
  Lua mock cannot show: tooltips, drag and drop, what a press does.
- **Measure on the real skin.** Each meter whose options change costs Rainmeter about 0.5 ms
  on the next update, and a redraw about 20-40 ms; the Lua mock does not show this. Time a
  change with `os.clock()` from `!CommandMeasure MeasureScript "..."` (it measures wall time).
  `layout()` and `layoutMonth()` must redraw once (`finishLayout()`).
- **Text into options goes through `safe()`.** `#` starts a Rainmeter variable, `[` `]` are
  section references, and `"` breaks bang quoting. Links drop their `#fragment` (see
  `expandEvent`).
- **Colours come from `cfg`** (theme plus overrides, see `THEMES` and `readSettings`). Never
  hard-code a light-theme colour; new colours need a `light` and a `dark` value in `THEMES`.
- **Strings come from `LANGS.en` and `LANGS.it`.** Add both. Context menu titles are
  `lang.ctx` plus `ContextTitleN` in `[Rainmeter]`.
- **Shapes need some alpha to catch the mouse.** Click areas use `Fill Color 0,0,0,1`, not alpha 0.
- **200 locals.** Lua 5.1 allows 200 local variables per function, and the main chunk of
  `Calendar.lua` is close. Past it Rainmeter refuses the whole script, and a press on the empty
  skin then moves it. Put new helpers inside a `do ... end` block or into a table (`edit`);
  `test_lua_main_chunk_has_room_for_locals` keeps room for 15. `layout()` is also close to the
  limit of 60 upvalues: reach new state through `edit`.
- **Script environment.** Rainmeter runs the script in its own environment, not `_G`: code
  given to `!CommandMeasure MeasureScript` sees the globals through `getfenv(1)`.
- **Mouse actions are per action.** A click goes to the topmost meter that has *that* action:
  a meter on top without a `LeftMouseUpAction` lets the click through to the one below
  (`CrCard` has a harmless one so a click on the card does not close it).
- **Mouse coordinates.** `$MouseX$` / `$MouseY$` (relative to the meter) work in click actions
  (`LeftMouseDownAction`, `LeftMouseUpAction`...), not in `MouseOverAction`, where they stay as
  text (checked on Rainmeter 4.5.28). A drag knows the exact spot only on the press and on the
  release; in between it only knows which meter the cursor entered.
- **InputText** (`MeasureCreateInput`) reads its options when the bang runs, so `!SetOption` is
  enough. X/Y are skin coordinates. Enter runs `Command1` (titles with `"`, `#`, `[ ]`, accents
  arrive intact); Esc or any focus loss runs `OnDismissAction`, before the click that caused it.
  The box cannot be closed from the skin: close the card only after the user's click.
  The start and end times have their own box (`MeasureTimeInput`, `CardTime()` / `TimeSubmit()`).
  The same `MeasureCreateInput` types the notes, place and description too (`c.inputField`,
  `CardField()`); `layoutCard` sets its size, font size and `InputLimit` for each. The 4.5 plugin
  trims what was typed, inserts a new line with Ctrl+Enter and drops the text on a dismissal.
- **Cards' pools:** `CrTx1..20` and 32 shapes of `CrCard` (`CR_TX`, `CARD_SHAPES`). A card that
  needs more logs an error (the tests fail on it): add meters to the `.ini` and raise the constants.
  The fields and pickers of the cards are functions of the `cf` table (`edit.cf` outside the block).
- **Tasks script versions:** the feed of `tools/GoogleTasksFeed.gs` says what it can do
  (`X-WC-VERSION`, `edit.scriptV`). An older deployed script ignores parameters it does not know
  and still answers OK, so a feature that sends new parameters is shown only from the version
  that knows them (raise the version in `buildFeed` when adding one).
- **Live tests:** `type` / `key` in `tools\LiveTest.ps1` refuse to send keys unless a Rainmeter
  window is in the foreground. `-Front` raises the skin, which takes the focus from an open
  InputText box: one LiveTest run per typing sequence. While the skin is raised (`ZPos 2`),
  Rainmeter keeps it above the InputText boxes, so screenshots do not show them: take the
  screenshot of a box in a run without `-Front`. Click only on spots known to be empty
  (a click on an event opens it in the browser); close cards with `lua CardClose()`.
  Measure with a temporary wrapper of the entry points (`os.clock`, `!Log`), never shipped.
- **Ship checklist:** Settings.inc comment for any new setting (with its default),
  README (Features, Configuration, Controls table), `Version=` in `[Metadata]`, tests.
  Then refresh the real skin
  (`"C:\Program Files\Rainmeter\Rainmeter.exe" !Refresh WeeklyCalendar`) and check
  `%APPDATA%\Rainmeter\Rainmeter.log` for errors.
