# Plan 9: create tasks and events from the skin

Goal: create a Google Task or a Google Calendar event without opening the browser. There
are three ways in:

- click an empty slot of the hour grid (an event at that time);
- click an empty spot of the all-day row (a task for that day);
- click a **+** button in the toolbar (today, next half hour).

A small card like Google Calendar's quick-create popover opens. Type the title and press
Enter. The item appears at once and Google saves it.

Read [the conventions](README.md#conventions-that-apply-to-every-plan) first. This plan reuses
the task pipeline of feature 3 (`MeasureTaskAction` → `TaskResult`, optimistic display, the
`OK` / `ERROR` / `auth` handling) and extends `tools/GoogleTasksFeed.gs`. If plan 8 (drag) is
built first, both share the "pending changes" structure; build whichever comes second on top
of the first.

## Constraints that shape the design

- **iCal feeds are read-only.** Writing goes through the Apps Script web app, which already
  runs as the user. It needs one more permission (Google Calendar) besides Tasks.
- **Text input:** Rainmeter's bundled **InputText** plugin shows a native edit box over the
  skin. Enter runs `Command1`, and Esc or a click elsewhere runs `OnDismissAction`. On
  dismiss, the typed text is **lost**, so the card must be usable with "type title →
  Enter" as the main path, with type and time chosen before typing.
- **Mouse position:** mouse actions can use `$MouseY$` (relative to the meter). One click
  zone per day column is therefore enough to know the clicked time; no per-hour meters are
  needed.
- **Google's iCal feed is slow.** A new event can take from minutes up to hours to appear in
  the secret iCal address. The skin must keep showing created events itself until the feed
  has them.
- **Without the script:** a "More options" link opens Google Calendar's own event editor,
  pre-filled (`calendar.google.com/calendar/render?action=TEMPLATE&text=…&dates=…`). This also
  works for users with no script at all, but only for events: Google Tasks has no pre-filled
  create URL.

## Design

### Entry points

| Where | Default type | Default when |
| :--- | :--- | :--- |
| Empty spot of the hour grid, day `i` | Event | clicked time rounded **down** to 30 min, 1 hour long (Google's default) |
| Empty spot of the all-day row, day `i` | Task | that day (an event made from here is all-day) |
| Toolbar **+** button | Event | today, the next half hour, 1 hour (Google's "Create") |

- **Grid click zones** `CrZone0..6`: transparent Shapes (`Fill Color 0,0,0,1`) covering each
  day column from `gridTop` to `gridBottom`. They must sit **below** the event meters in the
  `.ini`: right after `[Grid]`, before `ADBg1`. That way a click on an event still opens the
  event. Action: `[!CommandMeasure MeasureScript "CreateAt(i, $MouseY$)"]`.
- **All-day zones** `CrAdZone0..6`: the same, covering the all-day band of each column, with
  `CreateAllDay(i)`. They exist only when the band is shown. With no all-day items the band
  is 0 px tall, so clicking the separator area above the grid is not possible. Clicking the
  day **number** (`DayNum*`) should then create a task too: set its `LeftMouseUpAction`
  to `CreateAllDay(i)` and its tooltip to "Add a task".
- **Toolbar +:** a 32 px circle filled with `cfg.today` and a white "+" (12 pt), tooltip
  "Create" / "Crea". Place it right after the app title, before **Today**: shift `bx` in
  `layout()` by 42.

### The draft

While the card is open, the slot shows a **draft** that looks like the item will:

- **Event:** a block in the target calendar's colour, with the time range text, using the same
  geometry as a timed event. When there are overlaps, it is drawn at full width on top
  (Google does the same).
- **Task / all-day event:** a chip in the first free row of that day's all-day band.
- Title: what is in the card ("(No title)" / "(senza titolo)" until saved).

Meters: `CrDraft` (Shape) and `CrDraftTx` (String), placed after the `EvD*` pool so they are
above events.

### The card (popover)

```
 ┌──────────────────────────────────────┐   width 340, radius 12
 │  Add title____________________       │   InputText box, 13 pt, 2 px underline in TodayColor
 │                                      │
 │  ( Event ) ( Task )                  │   segmented chips (selected = SelBgColor, see plan 7)
 │                                      │
 │  ◷  Wed 21 Oct · 10:00 – 11:00       │   date and times: mouse wheel changes them
 │     ☐ All day                        │   (event only)
 │  ●  Personal                         │   target calendar (event) / task list (task), colour dot
 │                                      │
 │            More options     [ Save ] │   text button + filled button (TodayColor, white text)
 └──────────────────────────────────────┘
```

- **Placement:** to the right of the clicked column (`x = colRight + 8`). If it does not fit,
  place it to the left (`colLeft - 8 - 340`). Vertically, centre it on the draft, clamped
  inside `[tb + 8, H - 8 - cardH]`.
- **Card look:**
  - fill: a new theme colour `CardColor` (light `255,255,255,255`, dark `40,42,45,255`);
  - border: 1 px `cfg.border`;
  - shadow: 3 offset rounded rectangles under the card (offset 2/4/8 px, black at alpha
    28/18/10). Rainmeter shapes cannot blur; this reads as elevation.
  - All of it lives in one Shape meter `CrCard` (`Shape`, `Shape2`, … like `Grid`).
- **Title field:** the InputText box is positioned over the field (13 pt, `SolidColor` =
  `CardColor`, `FontColor` = `cfg.dayNum`). When the input is closed (after a dismiss), the
  field shows the placeholder "Add title" / "Aggiungi titolo" in `cfg.muted`, and clicking it
  reopens the input.
- **Type chips:** "Event" / "Task" ("Evento" / "Attività"). Switching type redraws the draft
  and the rows below. The task type hides "All day", and the date row shows the date only.
- **Date and time row:** three separate String meters (date, start, end). Each has a pointer
  cursor and `MouseScrollUp/DownAction`:
  - date: ±1 day;
  - start: ±15 min, keeping the duration;
  - end: ±15 min, at least 15 min after the start.

  Tooltip: "Scroll to change" / "Usa la rotellina per cambiare". Meter-level wheel actions
  take precedence over the skin's hour scrolling, so no conflict.
- **All day:** a checkbox glyph (☐ / ☑, `cfg.muted` / `cfg.today`). Click to toggle.
- **Target row:**
  - event: the calendar is `CreateCalendar` (see Settings). Show its slot's name
    (`X-WR-CALNAME` of the matching feed, or "Google Calendar") and a dot in its colour.
  - task: the list name ("My Tasks" by default) and a dot in the tasks feed's colour.
  - No picker in v1. The values come from settings.
- **More options** (events only): opens the pre-filled Google Calendar editor (template URL
  above, with `dates=YYYYMMDDTHHMMSSZ/…` in UTC, or `YYYYMMDD/YYYYMMDD` for all day) and
  closes the card.
- **Save:** the same as Enter. Disabled (muted) while the title is empty.
- **Close:** a transparent full-skin meter `CrDismiss`, placed right below the card meters,
  catches any click outside the card and cancels. Right click and `OnDismissAction` of the
  input do **not** close the card. Esc only closes the input.

Meters for the card, placed just before `[NowLine]` (on top of everything; plan 8's drag
meters can go right before them): `CrDismiss`, `CrCard`, `CrTitle` (placeholder String),
`CrTypeEv` / `CrTypeEvTx` / `CrTypeTk` / `CrTypeTkTx`, `CrDate`, `CrStart`, `CrDash`, `CrEnd`,
`CrAllDay`, `CrTarget` (Shape dot + String), `CrMore`, `CrSave` / `CrSaveTx`. Everything is
hidden outside creation.

### InputText measure (`.ini`)

```ini
[MeasureCreateInput]
Measure=Plugin
Plugin=InputText
FontFace=#FontFace#
FontSize=13
FocusDismiss=1
DefaultValue=
Command1=[!SetVariable CreateTitle """$UserInput$"""][!CommandMeasure MeasureScript "CreateSubmit()"]
OnDismissAction=[!CommandMeasure MeasureScript "CreateInputClosed()"]
```

The Lua sets `X`, `Y`, `W`, `H`, `SolidColor` and `FontColor` with `!SetOption` +
`!UpdateMeasure`, then runs `!CommandMeasure MeasureCreateInput "ExecuteBatch 1"`. Triple
quotes keep titles that contain `"` intact. The Lua reads the title with
`SKIN:GetVariable('CreateTitle')`.

### Settings

- **Settings.inc:**
  - `CreateCalendar=` (empty = the account's primary calendar; or a calendar id as it appears
    in its iCal address, e.g. a shared calendar);
  - `TaskList=@default` (Google's default list; or a list id from the feed's
    `X-WC-TASKLIST`).
- **Private.inc:** `TasksToken=`. See security below.
- **The script slot** is found automatically: the first `IcalUrlN` whose host is
  `script.google.com`. If there is none:
  - the + button and zones still open the card, with the type fixed to Event;
  - Save is replaced by "Open in Google Calendar" (the template URL).

### Apps Script (`tools/GoogleTasksFeed.gs`)

New actions in `doGet`. All of them answer `OK <id>` or `ERROR <reason>`:

- `action=createtask&list=@default&title=…&due=YYYY-MM-DD[&notes=…]` →
  `Tasks.Tasks.insert({ title, notes, due: due + 'T00:00:00.000Z' }, list)`, answering
  `OK <task id>`.
- `action=createevent&cal=<id or empty>&title=…&start=<ISO UTC>&end=<ISO UTC>` → timed event.
- `action=createevent&cal=…&title=…&date=YYYY-MM-DD&days=1` → all-day event.

For events, use the **advanced Calendar service** (`Calendar`, "Google Calendar API" v3,
enabled like the Tasks service). Plan 10 (edit and delete) needs it to handle single
occurrences of recurring events, so both plans share one API:
`Calendar.Events.insert({ summary: title, start: { dateTime: start }, end: { dateTime: end } }, cal || 'primary')`,
or `{ start: { date }, end: { date: date + days } }` for all-day events. Answer
`OK ` + `event.iCalUID` (e.g. `abc123@google.com`), which is the UID the iCal feed will show.

Validation:
- title: 1-500 characters;
- dates: regex;
- `end > start`;
- unknown calendar → `ERROR calendar not found`.

`authorize()` also calls `Calendar.Calendars.get('primary')`, so Google asks for the Calendar
permission. In the README:
- add a step to enable the **Google Calendar API** service (+ next to Services), with the
  manifest fallback `{ "userSymbol": "Calendar", "version": "v3", "serviceId": "calendar" }`;
- add `https://www.googleapis.com/auth/calendar` to the manual scopes line.

**Security:** with this change, anyone who has the web app URL can **create events**, not
only read tasks. Add an optional shared secret:
- if the script property `WRITE_TOKEN` is set (Project Settings > Script properties), every
  write action (complete, reopen, move, create) requires `&token=<value>`, otherwise it answers
  `ERROR bad token`;
- the skin appends `&token=` from `TasksToken` in `Private.inc`.

Document it in the README as recommended.

### Lua

- **State:**
  - `create = { type, day, s, e, allDay, title, feed, inputOpen }`: the open card.
  - `created = {}`: items saved but not yet in a feed. Each has
    `{ kind = 'task'|'event', uid, title, sDay/eDay or s/e, feed, at = os.time() }`.
- **Entry points:**
  - `CreateAt(i, y)`: `minute = (y / hourH) * 60 + startH * 60`, rounded down to 30. Opens
    the card.
  - `CreateAllDay(i)` and `CreateNew()` (toolbar).
  - `CreateType(t)`, `CreateAdjust(field, delta)`, `CreateToggleAllDay()`.
  - `CreateTitleClick()` reopens the input.
  - `CreateInputClosed()`: input closed without Enter; the card stays.
  - `CreateSubmit()`, `CreateMore()`, `CreateCancel()`.
- **Drawing:** a `layoutCreate()` function draws the draft and the card. It runs at the end
  of `layout()`, and alone after card-only changes (followed by `!UpdateMeterGroup` and
  `!Redraw`; no full layout is needed for wheel changes). `cfg.geo` must carry everything it
  needs (`tb`, `hdr`, `gridBottom`, `adH`, `dayW`, `timeW`, `hourH`, `startH`, and the free
  all-day row per day).
- **Submit:**
  - Queue a job `{ kind = 'createtask'|'createevent', … }` in `taskQueue` and generalise
    `sendNextTask` to build the URL from the job: `urlEncode` every value, UTF-8.
  - Add the item to `created` right away, so it shows as a normal chip or block. Close the
    card.
  - On `OK <id>`, store the uid: tasks `<id>@tasks.google.com`, events `<id>`.
  - On `ERROR`, remove it from `created`, reopen the card with the title restored and show
    the error under the title in red (`cfg.now`).
  - Toolbar notices use the existing `taskErr` mechanism (`auth`, `failed`).
- **Showing created items:**
  - `buildInstances` appends `created` items (after the feed events) as instances.
  - `rebuild()` drops an item once an event with that uid exists in `events`.
  - After 24 h it is dropped anyway: by then Google's feed has it, or something is wrong.
  - Created items show the tooltip line "Saved - waiting for the calendar to sync" /
    "Salvato - in attesa della sincronizzazione".
  - They are not draggable or checkable until the feed has them (no list/task ids yet).
- **Which colour:**
  - tasks: the script slot's colour;
  - events: the slot whose `googleCalId` equals the target calendar (or the account for the
    primary calendar). If none matches, the event will never appear in a feed: show it for
    24 h in slot 1's colour and say so in its tooltip.

## Tests

`tests/run_tests.py`. Extend the mock where needed: `GetVariable` must return what
`!SetVariable` set, so `CreateTitle` round-trips.

- `CreateAt(2, y)` at 10:20 → card shown, draft at 10:00-11:00 on Wednesday (check the
  `CrDraft` Y / H against the `HL*` hour labels). `!CommandMeasure MeasureCreateInput
  "ExecuteBatch 1"` is sent, with the InputText `X` / `Y` inside `CrCard`.
- The card fits: clicking Sunday's column puts it on the left of the column. Clicking near
  the bottom clamps it.
- `CreateAdjust('start', 1)` → 10:15-11:15. `CreateAdjust('end', -4)` never goes below 15 min.
- **Submit an event:** set `CreateTitle` to `Ripasso "capitolo 3" & esercizi` and call
  `CreateSubmit()`. The `Parameter` contains `action=createevent`, the title percent-encoded,
  and `start=2027-03-03T09:00:00Z` (UTC for 10:00 local in the test zone; compute it, do not
  hard-code the offset). The item is shown immediately.
  - `TaskResult` with `OK abc@google.com`: still shown. After a feed with `UID:abc@google.com`
    is loaded (`Reload(1)`), it is shown exactly once.
  - With `ERROR …`: removed, card reopened with the title.
- **Submit a task** from `CreateAllDay(4)`: `action=createtask&list=%40default&…&due=2027-03-05`.
  It appears on Friday with ○ and no check button.
- **No script slot:** Save is replaced by the template link. `CreateMore()` sends the
  pre-filled `calendar.google.com/calendar/render?action=TEMPLATE…` URL.
- `CreateCancel()` hides every `Cr*` meter and clears all their actions.
- Clicks on existing events still open them: the `CrZone*` meters are earlier in the `.ini`
  than `EvBg1`. Assert it on the section order from `ini_sections()` (read the file in order).
- **Script under Node:**
  - `createtask` calls `Tasks.Tasks.insert` with the right body and answers `OK <id>`;
  - `createevent` calls a fake `Calendar.Events.insert` (timed and all-day) and answers
    `OK <id>@google.com`;
  - a wrong token, an empty title or `end <= start` give `ERROR`.
- `check_clean()` and the pixel snapping test pass.

## Out of scope (v1)

- Editing or deleting existing events and tasks.
- Picking the calendar or the list in the card: the settings decide.
- Recurrence, guests, reminders, location, description. "More options" covers events, and the
  Google Tasks app covers tasks.
- Creating in the month view of plan 7: a click on a day there opens the day view, where
  creation works.

## Done when

The tests pass. In the real skin:
- clicking 10:00 on Thursday, typing a title and pressing Enter shows the event at once;
- it is still there, exactly once, after Google's feed catches up;
- a task created from the all-day row appears in Google Tasks within seconds;
- "More options" opens the pre-filled editor;
- clicking an existing event still opens it;
- the card looks right in both themes.
