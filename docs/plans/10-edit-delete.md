# Plan 10: edit and delete tasks and events

Goal: right-click a task or event to open a detail card, like Google Calendar's event
popover. From the card you can:

- **delete** the item, with a few seconds to undo;
- **edit** its title, date and time;
- for tasks, complete or reopen them;
- open the item in Google Calendar.

Read [the conventions](README.md#conventions-that-apply-to-every-plan) first.

## Relation to plan 9 (create)

The two plans share building blocks. **Whichever is built first creates them; the other
reuses them:**

- the card meters and their drawing code (`CrCard` and friends, the shadow, the
  `CardColor` theme colour);
- the `MeasureCreateInput` InputText measure and the date/time chips changed with the mouse
  wheel;
- the generalised job queue: `taskQueue` jobs with a `kind`, `sendNextTask` building the URL
  from the job, `TaskResult` returning `OK [id]` / `ERROR`;
- the Calendar permission, the advanced **Calendar** service in the Apps Script, and the
  optional `WRITE_TOKEN` / `TasksToken` secret;
- the "local changes shown until the feed catches up" mechanism (plan 9's `created` list,
  generalised below).

If plan 9 is not built yet, implement those parts as described there. Leave out the
create-specific bits: click zones, the + button and the draft.

## What can be changed

| Item | Edit | Delete | Why |
| :--- | :--- | :--- | :--- |
| Google Task (new script, has list/task ids) | ✓ | ✓ | Tasks API |
| Event in a Google calendar slot (`cfg.calIds[feed]` set, secret address) | ✓ | ✓ | Calendar API, if the user can write to that calendar |
| Holiday calendars, public addresses (`/public/` in the URL), non-Google feeds | ✗ | ✗ | read-only |
| Invitation organised by someone else (`ORGANIZER` ≠ calendar owner) | ✗ | ✗ (v1) | only the organizer can change it; a guest "deleting" it is a decline, out of scope |
| Recurring event | ✓ this occurrence | ✓ this occurrence or the whole series | Calendar API instances |
| Repeating Google Task | ✓ | ✓ | the API sees only the current instance; README caveat |
| Item created from the skin, not yet in the feed (plan 9) | ✗ | ✗ | no stable ids yet; the card says "Syncing…" |

**Parsing:** read `ORGANIZER` in `parseICS` (`mailto:` value, lowercased, into `cur.organizer`).
An event is read-only when the organizer is set and is not in `calOwners[feed]`. Also carry
`uid`, `recurring` (rrule or rdates) and the occurrence's original start (already used for
`gid`) into every instance.

**Imported events:** Google can rewrite the UIDs of imported events (e.g. `CSVConvert…` from a
CSV import), so the iCal UID is not the Calendar API event id. The script must therefore look
events up by iCal UID (below), never derive the id from the UID.

## Interaction

- **Right click** on an event or task meter (`EvBg/EvT/EvD`, `ADBg/ADTx`) opens the card.
  It replaces the Rainmeter context menu on those meters only; right-clicking empty space
  still shows the skin menu.
- **Tooltip hint:** add the last line "Right-click: details, edit, delete" /
  "Clic destro: dettagli, modifica, elimina" to the event and task tooltips. Put it after
  the middle-click hint.
- **"+N more" chip:** right click does nothing; a click expands it.

### Detail card

```
 ┌───────────────────────────────────────────┐   width 360, same look as plan 9's card
 │ ●  Lezione di Analisi Matematica 1        │   colour dot (feed colour) + title 13 pt, wrapped to 2 lines
 │    Wed 21 Oct · 10:30 – 13:30             │   muted, 9 pt; "Every week" line if recurring
 │    ONLINE                                 │   location (if any)
 │    Link aula virtuale: politecnico…       │   description, cleanDesc(), max 4 lines, muted
 │ ───────────────────────────────────────── │
 │  Open in Google     ✎ Edit     🗑 Delete   │   text buttons; Delete in NowColor (red)
 └───────────────────────────────────────────┘
```

- **Task card:** the glyph is ○ / ✓, with no time. The notes take the description's place.
  The buttons are **Complete** / **Reopen** (the existing `ToggleTask` flow), ✎ Edit and
  🗑 Delete.
- **Read-only item:** the buttons are only "Open in Google" (and "Open link" when it has one).
  A muted line explains why: "Holiday calendar - read only", "Organised by
  name@example.com", "This calendar is read-only".
- **Placement** as in plan 9: beside the item's column (right if it fits, else left),
  vertically centred on the item and clamped to the skin.
- **Close:** a click outside the card (`CrDismiss`), or after an action.
- Icons are plain Unicode glyphs in `FontFace` (✎ U+270E, 🗑 is not in Segoe UI, so write
  "Delete" without an icon if the glyph renders as a box). Check them on the real skin.

### Edit mode

"Edit" turns the card into plan 9's form, filled in with the item:

- **Title:** InputText opens with `DefaultValue` = the current title (text selected).
- **Date / start / end chips:** changed with the mouse wheel. Tasks show only the date.
- **Buttons:** "Cancel" and "Save". Enter saves too.
- **Recurring event:** a muted line "Only this event will change". Editing the whole series
  is out of scope for v1; "Open in Google" covers it.
- **Optimistic display:** the change shows at once and is rolled back on `ERROR`, as with
  `ToggleTask`.

### Delete with undo

- **Non-recurring item:** "Delete" removes it from the view at once and closes the card. A
  **snackbar** appears.
- **Recurring event:** "Delete" first turns the card's button row into
  **"This event" / "All events" / "Cancel"**. Then the same as above.
- **Snackbar:** bottom centre of the grid, `y = gridBottom - 52`, height 40, radius 8.
  - Colours: new theme colours `ToastBgColor` / `ToastTextColor` (light `50,50,50,245` /
    `242,242,242,255`, dark `227,227,227,245` / `31,31,31,255`), with an action colour
    `cfg.today` (light) / `168,199,250,255` (dark).
  - Text: "Event deleted" / "Task deleted" ("Evento eliminato" / "Attività eliminata") and a
    clickable **Undo** / **Annulla** on the right.
  - Meters: `ToastBg`, `ToastTx`, `ToastAct`, placed just before `[NowLine]`, above the card
    meters.
- **The delete request is sent only after 8 s** (checked in `Update()`), so Undo needs no
  "restore" API.
  - Undo within 8 s: drop the pending delete and show the item again.
  - A second delete within the window: the first one is sent immediately, then the new
    snackbar starts.
  - If the skin is refreshed during the window, the delete is lost: the item simply stays.
    Document this; it is the safe direction.

## Apps Script (`tools/GoogleTasksFeed.gs`)

All actions are write actions: they check `WRITE_TOKEN` when it is set, and answer `OK` or
`ERROR <reason>`.

**Tasks:**
- `action=deletetask&list=…&task=…` → `Tasks.Tasks.remove(list, task)`.
- `action=edittask&list=…&task=…&title=…&due=YYYY-MM-DD` →
  `Tasks.Tasks.patch({ title, due: due + 'T00:00:00.000Z' }, list, task)`. Omitted fields
  are not sent.

**Events** (advanced Calendar service). Every event action receives:
- `cal`: the calendar id from the feed slot (`cfg.calIds[feed]`);
- `uid`: the iCal UID;
- for occurrences of recurring events, `orig`: the occurrence's original start, as ISO UTC,
  or `YYYY-MM-DD` for all-day events.

1. Find the event:
   `Calendar.Events.list(cal, { iCalUID: uid, showDeleted: false, maxResults: 5 })`.
   - Take the item **without** `recurringEventId` (the series or the single event).
   - None found → `ERROR event not found`.
2. For an occurrence: `Calendar.Events.instances(cal, ev.id, { timeMin, timeMax })`, with a
   window of ±1 day around `orig`. Pick the instance whose `originalStartTime` equals `orig`
   (`dateTime` compared as Date, or `date`). None → `ERROR occurrence not found`.
3. Then:
   - `action=deleteevent&scope=one` → `Calendar.Events.remove(cal, instance.id)`;
   - `scope=all`, or a non-recurring event → `Calendar.Events.remove(cal, ev.id)`;
   - `action=editevent&title=…&start=…&end=…` (or `date=…&days=…`) →
     `Calendar.Events.patch({ summary, start, end }, cal, (instance || ev).id)`.

An exception from Google (no write access, organizer only, …) is returned as
`ERROR <message>`. The skin rolls back and shows the reason in the toolbar tooltip (the
existing `taskErr` / `taskErrMsg` mechanism).

## Lua

- **Local changes:** generalise `taskPending` / plan 9's `created` into one table, with one
  entry per item:

  ```lua
  localChanges[key] = { kind = 'task'|'event', feed, uid, orig,
                        deleted = true | nil, title = ..., day = ..., s = ..., e = ...,
                        state = 'done'|'open'|nil, at = os.time(), job = <queued job> }
  ```

  - **Key:** `feed .. '\1' .. uid .. '\1' .. (orig or '')`. Occurrences differ by `orig`.
  - **Applied in `buildInstances`**, after expansion: skip deleted instances, and override
    the title and times of edited ones. Do this per instance, not by editing `events`, so a
    single occurrence can change.
  - **Removed** when the feed shows the change: after a download the instance is gone
    (deleted) or matches (edited). They are removed anyway after 24 h.
    - Tasks: the feed is our script, so it is immediate.
    - Events: Google's iCal feed is slow (see plan 9).
- **Entry points:**
  - `ItemCard(kind, idx)`: the meter pool and index. Store the item per pool, as
    `adItems` does; add `evItems[idx]`. Each pool sets its `RightMouseUpAction` in
    `layout()` and clears it in the cleanup loops.
  - Card actions: `ItemEdit()`, `ItemSave()`, `ItemDelete(scope)`, `ItemUndo()`,
    `ItemOpen()`, `ItemClose()`.
- **Jobs:** `deletetask`, `edittask`, `deleteevent`, `editevent` in `taskQueue`. For events,
  the job carries `cal = cfg.calIds[feed]`. Delete jobs wait in a separate `pendingDelete`
  slot until their 8 s are up.
- **Strings:** add both languages for every label above.

## Tests

`tests/run_tests.py`. Extend the fixtures: add one event with
`ORGANIZER:mailto:other@example.com`, one recurring event with `UID:…@google.com`, and an
event with a `CSVConvert…` UID to `layout.ics`.

- **Right click:** an event meter has `RightMouseUpAction` `ItemCard('ev', n)`. After the
  call, the card meters are shown with the title, time and buttons. A holiday or invitation
  card has no Edit / Delete and shows the read-only reason.
- **Delete an event:** `ItemDelete('one')` → the event disappears from `event_titles()`, the
  toast is shown, and **no** `MeasureTaskAction` `Run` is sent yet.
  - `ItemUndo()` → back, no request.
  - Again, then advance time 9 s and call `Update()` → `action=deleteevent&cal=…&uid=…&scope=one`
    (plus `orig=` for the recurring fixture) is sent.
  - `TaskResult('ERROR …')` → the event is back and the toolbar shows the error.
- **Recurring "All events":** every occurrence in the week disappears; `scope=all`.
- **Edit a task:** title and date → `action=edittask…&title=…&due=…`; shown at once on the
  new day.
- **Edit a recurring occurrence:** only that occurrence changes in the view.
- **Local changes are removed** when a new feed without the event is loaded (`Reload(1)`),
  or after 24 h.
- **Script under Node**, with a fake `Calendar.Events` (`list` by iCalUID, `instances`,
  `remove`, `patch`) and a fake `Tasks.Tasks.remove/patch`:
  - lookup by iCalUID works for a `CSVConvert…` UID;
  - an occurrence is matched by `originalStartTime` (timed and all-day);
  - `scope=all` removes the series id;
  - a missing event gives `ERROR event not found`;
  - a wrong token gives `ERROR bad token`.
- `check_clean()` and the pixel snapping test pass.

## Out of scope (v1)

- Editing a whole recurring series ("this and following" / "all events").
- Editing location, description, guests, reminders or colour: "Open in Google" covers them.
- Declining or removing invitations.
- Editing or deleting from the month view: the day view has the card. If wanted, add it
  later; the card code is shared.

## Done when

The tests pass. In the real skin:
- right-clicking a lecture shows its details;
- deleting one occurrence of a recurring event removes only that occurrence, in Google
  Calendar too;
- Undo within 8 s restores it with no request sent;
- renaming a task shows up in Google Tasks within seconds;
- holiday and invitation cards are read-only with the reason shown;
- the right-click menu of the skin still opens on empty space.
