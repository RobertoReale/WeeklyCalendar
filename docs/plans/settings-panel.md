# Plan: a graphical settings panel

Status: designed, not built. Written for the developer (or Claude session) who builds it.
Base: v1.19.1 (commit a226575). Read `docs/plans/README.md` first: every convention there
applies, and each one has already caused a bug once.

## 1. Goal

The user asked for a graphical way to change the settings instead of editing
`@Resources\Settings.inc` in Notepad and refreshing the skin. The user writes in Italian, wants
the skin to look like Google Calendar, wants every feature tested live, and wants "no bugs and
no performance problems".

What they get:

- a **gear button** in the toolbar (left of the minimize button) and a context menu item
  *Settings...* / *Impostazioni...*;
- a **settings card** in the style of the existing cards (create / edit / details), with tabs;
- changes are **shown at once** (live preview) where the skin can apply them without a refresh;
- **Save** writes them, **Cancel** puts everything back, **Defaults** removes the overrides;
- the text file stays available (*Open the settings file*), for what the panel does not cover.

Out of scope for the first version: the calendar addresses (`IcalUrl1..6`, `TasksToken`,
`MyEmail` in `Private.inc`: they stay in the file, with a button that opens it), free-text
settings (`CreateCalendar`, `TaskList`, `PlaceSearchNear`, `FontFace`) and the custom colors of
the theme (`BgColor`, `GridColor`...). The panel has a button to open the file for those.

## 2. Where the values are stored

`WeeklyCalendar.ini` includes `Settings.inc` and **then** `Private.inc`, so a variable in
`Private.inc` wins. That is already how `View`, `Width`, `Height` and `Minimized` are saved.
The panel does the same:

- **Save** writes every changed key with
  `!WriteKeyValue Variables <Key> <Value> "<#@#>Private.inc"`. `Settings.inc` is never written: it
  is tracked by git and holds the documented defaults.
- **Defaults** (with a confirmation row in the card, like *Delete recurring event*) removes from
  `Private.inc` the keys the panel manages. Use a line filter like `ResetSize()` does:
  read the file, drop the `^Key=` lines, write it back, then `!Refresh`. It must never touch
  `IcalUrl*`, `TasksToken`, `MyEmail`, `Width`, `Height`, `View` or `Minimized`.
- `Private.inc` may not exist yet: `ensurePrivateFile()` creates it at `Initialize`.

## 3. How a change is applied

Each setting has an **apply class**:

| Class | Meaning | How |
|---|---|---|
| `live` | the skin can show it at once | `!SetVariable Key Value`, then `edit.reloadSettings()`, then `safeLayout()` |
| `bang` | needs a bang besides the layout | as `live`, plus the bang (`ZPos`: `!ZPos v`; `KeepDialogsOnTop`: `StartHelper()`) |
| `refresh` | read by the `.ini` at load (styles, measures) | written on Save, then `!Refresh` (the card says "applied after Save") |

`edit.reloadSettings()` is new: it must **not** simply call `readSettings()` again, because
`readSettings()` also resets runtime state:

- `view` is reset from `V('View')`. `SetView` writes `View` to `Private.inc` but never calls
  `!SetVariable View`, so the variable still holds the view the skin started with. Keep the
  current `view`.
- `cfg.W` / `cfg.H` come from `Width` / `Height`. `edit.applySize` does `!SetVariable` them,
  so they are up to date, but keep the values anyway.
- `cfg.bgStr` must stay the in-use or idle background, whichever is showing now
  (`edit.setBg`): keep `cfg.bgStr == cfg.bgUseStr` or the idle one, as before the reload.

So `edit.reloadSettings()` does three things:

1. save `view`, `cfg.W`, `cfg.H`, and whether `cfg.bgStr` was the idle one;
2. call `readSettings()`;
3. restore those values, then re-set the context menu titles (the loop at the top of
   `Initialize`, plus `mini.ctx()`) in case the language changed.

Changing `Language` live also needs the toolbar and the card texts redrawn: `safeLayout()` and
`refreshCard()` do that.

Live preview is only for `live` and `bang`; `refresh` settings change only the value shown in the
card until Save.

**Cancel** (and closing the card any other way: Esc, a click outside it on `CrDismiss`,
minimize) must undo the preview:

1. `!SetVariable` every previewed key back to the snapshot taken when the card opened;
2. `edit.reloadSettings()`;
3. `safeLayout()`.

Closing paths to hook:

- `CardClose()` itself, for a card of mode `settings`, before `edit.card = nil`;
- `Minimize()`: it calls `CardClose()`, so the hook above covers it.

## 4. The settings, by tab

At most 8 rows per tab: the card must fit in the smallest skin (800 x 440; `placeCard` keeps it
inside `edit.shownH`). Rows are 30 px high:

- header: 48;
- tabs: 34;
- 8 rows: 240;
- buttons: 48;
- margins: 24.

That is about 394 ≤ 424, so it fits.

Types:

- `toggle`: 0 or 1.
- `number`: min, max and step; the unit is shown after the value.
- `choice`: a list of value and label pairs.
- `color`: the 11 Google colors, a `choice` drawn with color dots.

| Tab (en / it) | Key | Type | Range / choices | Class |
|---|---|---|---|---|
| View / Vista | `View` | choice | day, 3day, week, month (use `SetView`, it saves itself) | live |
| | `FirstDay` | choice | 1 Monday, 0 Sunday, 6 Saturday | live |
| | `StartHour` | number | 0-23, step 1 (and < EndHour) | live |
| | `EndHour` | number | 1-24, step 1 (and > StartHour) | live |
| | `AutoScroll` | toggle | | live |
| | `AutoScrollHour` | number | 0-23 | live |
| | `AllDayRows` | number | 1-10 | live |
| | `HideEmptyHours` | toggle | | live |
| Look / Aspetto | `Theme` | choice | light, dark | live |
| | `Language` | choice | en English, it Italiano | live (see section 3) |
| | `EventColor1`..`6` | color | the calendar's name from `edit.calNames[i]` or `cfg.calIds[i]`; only slots with a valid URL | live |
| | `PastFade` | number | 0-1, step 0.1, shown as % | live |
| Wallpaper / Sfondo | `BgOpacity` | number | 0-100 step 5, % | live |
| | `IdleBgOpacity` | number | 0-100 step 5, % | live |
| | `IdleOpacity` | number | 10-100 step 5, % | live |
| | `IdleSeconds` | number | 0-60 step 1, s | live |
| | `ShowMinimizeButton` | toggle | | live |
| | `MiniEvents` | number | 0-5 | live |
| | `BgRadius` | number | 0-24 step 2, px | live |
| Mouse | `ClickAction` | choice | card, calendar, link | live |
| | `ClickToCreate` | toggle | | live |
| | `DragToMove` | toggle | | live |
| | `RightClickCard` | toggle | | live |
| | `ShowCreateButton` | toggle | | live |
| | `UndoSeconds` | number | 2-60 | live |
| | `NewEventMinutes` | number | 15-240 step 15, min | live |
| Other / Altro | `ShowToolbar` | toggle | (when 0, the gear disappears: the menu item stays) | live |
| | `ShowDeclined` | toggle | | live |
| | `PlaceSuggestions` | toggle | | live |
| | `ZPos` | choice | -2 On desktop, -1 Bottom, 0 Normal, 1 Topmost | bang |
| | `KeepDialogsOnTop` | toggle | | bang |
| | `RefreshMinutes` | number | 5-120 step 5, min | refresh |
| | `FontSize` | number | 8-12 step 0.5, pt | refresh |

Google's 11 event colors (name, RGB) for the color rows:

| Name | RGB |
|---|---|
| Tomato | 213,0,0 |
| Flamingo | 230,124,115 |
| Tangerine | 244,81,30 |
| Banana | 246,191,38 |
| Sage | 51,182,121 |
| Basil | 11,128,67 |
| Peacock | 3,155,229 |
| Blueberry | 63,81,181 |
| Lavender | 121,134,203 |
| Grape | 142,36,170 |
| Graphite | 97,97,97 |

The Italian names are Pomodoro, Fenicottero, Mandarino, Banana, Salvia, Basilico, Pavone,
Mirtillo, Lavanda, Uva and Grafite. A color the user set by hand that is not one of these shows
as "Custom" / "Personalizzato" and stays until another is picked.

Before writing the table into code, check every range against `readSettings()` (it clamps
some: `AllDayRows`, `UndoSeconds`, `NewEventMinutes`, `IdleOpacity`, `MiniEvents`...). The panel
must never write a value `readSettings()` would change.

Keep the definitions in **one table** inside a `do ... end` block (Lua's 200-locals limit),
for example `edit.settings = { { tab = 'view', key = 'StartHour', type = 'number', min = 0,
max = 23, step = 1, apply = 'live' }, ... }`. Put the labels in `LANGS.en.settings` and
`LANGS.it.settings`: both languages, always.

## 5. The card

Mode `settings` in `edit.card`: `{ mode = 'settings', tab = 'view', values = {}, snapshot = {},
confirm = nil, anchor = ... }`.

Add `buildSettings(c)` next to `buildMenu` / `buildDetail`. It returns
`{ w, h, els, shapes }` like them, and `layoutCard()` picks it with
`c.mode == 'settings' and buildSettings`.

- **Width:** 420. **Anchor:** the gear button's rectangle (like `cfg.newBtn` for **+**), or the
  middle of the toolbar from the context menu.
- **Header:**
  - "Settings" / "Impostazioni" at 11 pt, weight 600;
  - on the right, a small "Open file" link (`["#CONFIGEDITOR#" "#@#Settings.inc"]` as its
    `act`). The context menu already uses that action.
- **Tabs:** one text element per tab, in a row. The selected one is drawn with `cfg.sel` and
  `cfg.selText`, like the view switcher. Click: `SettingsTab('mouse')`. The mouse wheel over the
  tab row moves to the previous or next tab.
- **Rows:** the label on the left (`cfg.dayNum`, 9 pt), the control on the right.
  - `toggle`: a Material switch from 2 shapes. The track is a 36 x 14 pill, `cfg.today` with
    alpha when on and `cfg.border` when off. The knob is a dot of radius 9. Click on the row
    toggles: `SettingsToggle('Key')`.
  - `number`: the value as text, e.g. `‹  90 %  ›`, right-aligned. One element: its
    `LeftMouseUpAction` passes `$MouseX$`, so `SettingsStep('Key', $MouseX$)` steps down when the
    click is on the left half and up on the right half. `$MouseX$` works in click actions (see
    the conventions). The mouse wheel steps too: `up` / `down` = `SettingsStep('Key', -1 / 1)`.
    The tooltip says "Click or scroll to change" / "Clic o rotellina per cambiare".
  - `choice` and `color`: like `cf.picker`: the choice and ▾ (with a color dot for colors). A
    click opens the existing picker menu (`buildMenu`, `CardMenu`), and the mouse wheel cycles
    (`CardCycle`).
- **Note line** (only when a `refresh` setting changed): "Applied after Save (the skin reloads)"
  / "Applicato dopo Salva (la skin si ricarica)", muted, 8 pt.
- **Buttons** (`buttonRow`):
  - Save (filled);
  - Cancel;
  - on the left, "Defaults" / "Predefiniti". It asks for confirmation inline: the row becomes
    "Reset every setting? Yes / No", like the delete confirmation of `ItemDeleteAsk`.

Things to change in the existing picker code, for the `choice` and `color` rows:

- `CardMenu`, `CardCycle`, `CardPick` return unless `c.mode` is `create` or `edit`: allow
  `settings`.
- `cf.options(c, kind)`: add kinds `set:<Key>`, which return the choices of that key with
  `sel = (value == c.values[Key])` and `color` for color rows.
- `pick(c, kind, o)`: for `set:<Key>`, call the same function as a toggle or step
  (`edit.settingSet(Key, value)`).
- `buildMenu`: its header comes from the kind. Add the setting's label for `set:` kinds.

New global entry points, called from the card's actions (keep them small; logic in `edit.*`):

- `Settings()` opens the card. If minimized it calls `MiniRestore()` first; if a card is open it
  closes it first.
- `SettingsTab(name)`.
- `SettingsToggle(key)`.
- `SettingsStep(key, x)`: `x` is `$MouseX$`, or ±1 from the wheel.
- `SettingsSave()`.
- `SettingsDefaults(confirm)`.

All of them return unless `edit.card` is a `settings` card.

`edit.settingSet(key, value)` is the one place that applies a change:

1. clamp the value;
2. enforce `StartHour < EndHour` (move the other one when needed);
3. put the value in `c.values`;
4. for `live` / `bang`: `!SetVariable`, `edit.reloadSettings()`, the bang, `safeLayout()`;
5. `refreshCard()`.

A full layout costs ~10 ms on the real skin (measured with 2 layouts in 19 ms), so stepping a
number with the wheel stays fluid.

`View` is special: it calls `SetView(v)`, which saves itself, and it is not part of the snapshot.

`SettingsSave()`:

1. write every key whose value differs from the snapshot (`!WriteKeyValue`);
2. close the card without undoing anything (clear the snapshot before `CardClose()`);
3. `!Refresh` if any `refresh` key changed.

## 6. The meter pools

Count what a tab needs:

- texts: title 1, file link 1, tabs 5, rows 8 x 2 = 16, note 1, buttons 3. Total **27**, more
  than `CR_TX = 20`;
- shapes: shadow and body 4, selected tab 1, switches 8 x 2 = 16, color dots up to 6, buttons 1.
  Total about **28**, under `CARD_SHAPES = 32`.

Raise the text pool to **32**:

- add `[CrTx21]` .. `[CrTx32]` to `WeeklyCalendar.ini` right after `[CrTx20]`, generated by a
  short script that copies `[CrTx20]`'s block, never by hand;
- set `CR_TX = 32` in the Lua.

The `PlBox` / `PlRow` meters come after `CrTx20` and must stay above the card texts (z-order is
file order), so insert the new ones between `CrTx20` and `PlBox`. `layoutCard` already logs an
error when a card needs more than the pools: the tests fail on it.

## 7. Toolbar and context menu

- **Gear button** `BtnSettings`, a Shape meter like `BtnMini` (`StyCal | StyShape |
  StyWeekScroll | StyItem | StyHidden`, `LeftMouseUpAction=[!CommandMeasure MeasureScript
  "Settings()"]`). Put it right after `[BtnMini]` in the `.ini`, and in the `tbItems` list of
  `layoutToolbar`.
  - Icon: a gear drawn with shapes, e.g. a circle with a stroke of 2 and a hole, plus 6 short
    lines around it; or the glyph U+2699 in a String meter. Check how the glyph renders in
    Segoe UI before choosing: a shape is safer.
  - Place: `W - 52` when the minimize button is hidden, otherwise `W - 92`. The view switcher
    ends at `rightEnd`, which now subtracts 40 per button.
  - Narrow skin: the same rule as the minimize button (`if btn and rightEnd - swW < wkX - 2`).
    Drop the gear first, then the minimize button. Extend the existing `fit()` logic and keep
    `test_narrow_toolbar_keeps_the_sync_text_clear` passing (add cases).
- **Context menu:**
  - `ContextTitle6` "Calendar settings" (today it opens the file) becomes "Settings..." /
    "Impostazioni...", with action `Settings()`;
  - a new item, "Settings file" / "File delle impostazioni", opens the file. Add it after the
    last `---` before *Minimize*, so *Minimize* stays the last item: `mini.ctx()` uses
    `#ctx`.
  - Update `LANGS.en.ctx` and `LANGS.it.ctx` and the `ContextTitleN` / `ContextActionN` lines in
    `[Rainmeter]` together. `test_italian_translation_and_context_menu` checks some titles.

## 8. Interactions to take care of

- **Fade (IdleOpacity):** `IdleFade` waits while `edit.card` is set, so the panel never fades
  while open. A change of `IdleOpacity` / `IdleBgOpacity` must not fade the skin while the
  cursor is on the card. The new values apply on the next mouse leave: nothing to do, but test
  it.
- **BgOpacity while the panel is open:** the cursor is over the skin, so `edit.setBg(true)` is
  in effect. After `edit.reloadSettings()`, re-apply the background with `edit.setBg(true)` so a
  new `BgOpacity` shows at once. `cfg.bgStr` must be the new in-use string; force it, since
  `edit.setBg` returns when the string did not change.
- **HideEmptyHours / StartHour / EndHour / AllDayRows** change the height (`edit.shownH`). The
  card is placed again by `layoutCard` (`placeCard` uses `edit.shownH`), so it can move while
  you step a value. That is acceptable. Check that it stays inside the skin at 800 x 440.
- **ShowToolbar = 0** hides the gear. The anchor of an open card is then wrong: keep the card
  where it was (store its x and y in `c` after the first placement and reuse them).
- **Theme** changes every color. `refreshCard()` must redraw the card with `cfg.card` /
  `cfg.border` of the new theme.
- **Language:**
  - the card's texts, tabs and labels come from `cfg.lang`, so they change at once;
  - the context menu titles: section 3;
  - the toolbar's `CalAppTitle` and the like come from the layout, so `safeLayout()` covers
    them.
- **Minimize** while the panel is open: `Minimize()` calls `CardClose()`, and the Cancel hook
  undoes the preview. `Settings()` from the context menu while minimized calls `MiniRestore()`
  first.
- **Tooltips:** only through `setTip` (the `e.tip` of an element). Never `ToolTipText`.
- **Text through `safe()`:** calendar names in the color rows (`edit.calNames[i]` comes from
  the feed).
- **A press must not drag the skin:** the card's texts have `StyItem`, and `layoutCard` gives
  every element a `LeftMouseUpAction` (`NO_DRAG` when it has none). `CrCard` has a harmless one.
  Nothing to add, but test that pressing a row does not move the skin (LiveTest `pos`).

## 9. Tests (tests/run_tests.py)

All new tests use the `Skin` harness; each one ends with `check_clean()`.

1. **Opens and closes:**
   - `Settings()` shows `CrCard`, the tab texts and the rows of the first tab;
   - `CardClose()` hides it;
   - the gear's tooltip;
   - the toolbar positions with and without `ShowMinimizeButton`.
2. **Every tab fits:** for each tab, in en and it, at 800 x 440 and at 1400 x 800:
   - no `card too big` error;
   - the card is inside the skin: `CrCard` X/Y/W/H within `cfg.W` / `edit.shownH`, minus the
     shadow margin;
   - all X/Y/W/H are integers (`test_pixel_snapped_coordinates_and_sharp_grid` style).
3. **Toggle:**
   - `SettingsToggle('ShowCreateButton')` hides `CrNew` at once, and `!SetVariable` was sent;
   - nothing is written until `SettingsSave()`;
   - then `['!WriteKeyValue', 'Variables', 'ShowCreateButton', '0', <Private.inc>]` is in the
     bangs.
4. **Number:**
   - `SettingsStep('BgOpacity', x)` with x on the left / right half steps by 5 down / up;
   - the wheel steps;
   - clamped at 0 and 100;
   - `BG`'s fill alpha follows;
   - `StartHour` cannot reach `EndHour`.
5. **Choice / color:**
   - `CardMenu('set:Theme')` lists light and dark, and `CardPick(2)` switches to dark (the BG
     color changes);
   - `CardCycle('set:EventColor1', 1)` changes `cfg.colors[1]`;
   - a custom color shows "Custom".
6. **Cancel restores:**
   - change 3 live settings, then `CardClose()`;
   - every variable is back (the last `!SetVariable` of each key equals the snapshot), the
     layout matches a fresh skin's (compare a few options), and nothing was written.
7. **Refresh class:**
   - changing `FontSize` does not `!SetVariable` at once;
   - Save writes it and sends `!Refresh`;
   - live changes alone do not send `!Refresh`.
8. **Defaults:**
   - `SettingsDefaults(1)` removes the managed keys from a `Private.inc` that also has
     `IcalUrl1`, `TasksToken`, `Width`, `View` and `Minimized`;
   - those stay byte for byte;
   - then `!Refresh`.
9. **View is not reset** by `edit.reloadSettings()`: `SetView('month')`, then
   `SettingsToggle(...)`, and the month view is still shown.
10. **Language live:** switch to `it`; the tab labels, `CalAppTitle` and `ContextTitle` are
    Italian.
11. **Minimize with the panel open** undoes the preview. **Settings while minimized** restores
    first.
12. **Pools:**
    - `test_ini_lists_of_the_minimized_skin` still passes (new meters in group `Cal`);
    - `CrTx21..32` exist;
    - `CR_TX` matches the `.ini`.
13. Keep `test_lua_main_chunk_has_room_for_locals`. The new code goes in a `do ... end` block
    and `edit.*` fields.

Run `python tests/run_tests.py`: all tests must pass (112 today, plus the new ones).

## 10. Live checks (tools\LiveTest.ps1)

Ask the user to leave the PC before each live session. Use `-Front`, and one drag per run.

1. Click the gear (real click), take a screenshot of the card, in the light and dark themes, at
   800 x 440. The user's skin is 800 x 440 at 431,69: restore it afterwards.
2. Click a switch, step a number with clicks on both halves and with the wheel, open a choice
   menu and pick. Take a screenshot after each.
3. Change `BgOpacity` and `HideEmptyHours` and watch the skin change behind the card.
4. Cancel: the skin is as before. Save: `Private.inc` has the keys (read it, without printing
   the addresses or the token); refresh, and they are still there.
5. Pressing a row and dragging must not move the skin (`pos`).
6. Measure `SettingsStep` with a temporary `os.clock()` wrapper (`!Log`, never shipped). It
   should take a few tens of ms, like a layout.
7. `Rainmeter.log` must have no errors.

## 11. Ship checklist

- `Settings.inc`: a comment at the top: "Most of these can also be changed from the
  calendar: right-click > Settings... (they are saved in Private.inc, which wins over this
  file)".
- README:
  - Features: a "Settings panel" line;
  - Configuration: a short section before the file-based one;
  - Controls table: "Change the settings".
- `docs/plans/README.md`: add the conventions learned while building it, and remove this plan
  once it is shipped (git keeps it).
- `Version=` in `[Metadata]`: 1.20.0.
- Commit and push only when the user says so. Never add a Co-authored-by line or any mention
  of Claude.

## 12. Suggested order of work

1. `edit.reloadSettings()`, with the test that the view is kept.
2. The pools (`CrTx21..32`) and the gear button with the toolbar layout. Tests.
3. `buildSettings` with one tab, toggles only. Live screenshot.
4. Numbers, then choices and colors (the picker changes). Tests for each.
5. Snapshot, Cancel, Save, Defaults, the refresh class. Tests.
6. The remaining tabs, both languages. Run the "every tab fits" test.
7. Context menu, minimize interplay, docs, the live checklist.
