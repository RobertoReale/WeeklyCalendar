# WeeklyCalendar for Rainmeter

A sleek, modern, Google Calendar (Material 3) weekly planner skin for [Rainmeter](https://www.rainmeter.net/).

Powered directly by Google Calendar (or any standard iCalendar / `.ics` feed), it expands recurring events (`RRULE`, `RDATE`, `EXDATE`, `RECURRENCE-ID`), converts timezones (`VTIMEZONE`, plus built-in rules for common zones), and provides smooth interactive navigation on your desktop.

![Rainmeter Weekly Calendar Preview](preview.png)

---

## Features

- **Google Calendar Material 3 Design**: Clean typography, Google Calendar pastel color scheme, subtle borders, today indicator circle, and red live "now" line.
- **Vertical Hour Scrolling**: Scroll the mouse wheel over the calendar grid or use the time-gutter buttons (▲ / ▼) to navigate through hours at any time.
- **Auto-Scroll for Evening Plans**: In the afternoon and evening (after 2:00 PM / 14:00 by default), the visible time window automatically shifts down so upcoming commitments after 19:00 (7 PM) through midnight are always in plain sight without manual scrolling.
- **Day, 3-Day, Week and Month Views**: A segmented switcher in the toolbar (Day / 3 days / Week / Month, like Google Calendar) changes the view at once and remembers it; wide day columns also show the first line of each event's description. The month view lists each day's all-day items and events ("+N more" when a day is full); click a day to open it in the day view.
- **Multi-Calendar Support**: Sync up to 6 distinct iCal feeds simultaneously, each with custom colors and titles.
- **Smart Recurrence & Overrides**: Client-side parsing of RFC 5545 recurrence rules (`DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`, including `BYSETPOS` such as "last weekday of the month"), extra dates (`RDATE`), exceptions (`EXDATE`), and modified occurrences (`RECURRENCE-ID`).
- **Hidden Events Indicators**: When events fall outside the visible hours, a `▲ n` badge next to the day number (earlier) or a `▼ n` badge under the column (later) shows how many there are; hover for the list, click to scroll to them.
- **Declined Invitations**: Invitations you declined are drawn outlined, like Google Calendar, or can be hidden (`ShowDeclined=0`).
- **All-Day Events & Timed Events**: Dedicated all-day events row at the top (3 rows by default, `AllDayRows`; click "+N more" to expand the row like Google Calendar, ▲ to collapse it) and column-packed overlapping timed events throughout the week.
- **Google Tasks & Holidays**: Tasks with a due date appear in the all-day row like in Google Calendar (○ open, ✓ completed and struck through), via a small Google Apps Script; click the circle to mark a task completed (or the check mark to reopen it), or drag it to another day (3-day, week and month views). Public holidays come from Google's holiday calendars. Your contacts' birthdays, which Google's iCal address leaves out, come from the same script.
- **Create Events and Tasks**: Click an empty spot of the hours (an event at that time), of the all-day row or a day number (a task), or the **+** in the toolbar: a card like Google Calendar's opens, you type the title and press Enter. The item appears at once and Google saves it.
- **Details, Edit, Delete**: Right-click an event or task for its details; edit its title, date and times, or delete it (one occurrence or the whole series of a recurring event) with a few seconds to undo.
- **Drag Events**: Drag an event to another time or day (snapped to 15 minutes, like Google Calendar), or an all-day event to another day; in the month view, events move to another day and keep their time.
- **Open in Google Calendar**: Click an event to open it in Google Calendar (a task opens its day); middle-click opens the event's video call or link (Meet, Zoom, Teams...). `ClickAction=link` swaps the two.
- **Dialogs Always on Top**: Windows and dialogs you open (e.g. "Empty Recycle Bin") always appear above the calendar, even in Windows' "Show desktop" mode.
- **Past Event Fading**: Events fade as soon as they end, just like in Google Calendar.
- **Two-Zone Mouse Navigation**:
  - Scroll wheel over the **grid / events / time column**: scrolls hours up & down.
  - Scroll wheel over the **toolbar / day headers**: flips through weeks.
- **Detailed Tooltips**: Hover over any event or task to see its full title, start/end time, location and description (rich text and Google Meet details are cleaned up).
- **Dark & Light Themes**: `Theme=light` or `Theme=dark`, matching Google Calendar; any single color can still be overridden.
- **English & Italian**: Labels, tooltips and the right-click menu follow `Language`.
- **Unicode Titles**: Accented and non-Latin characters in event titles display correctly.

---

## Installation

1. Make sure you have **[Rainmeter](https://www.rainmeter.net/)** installed (version 4.5 or newer).
2. Download or clone this repository into your Rainmeter skins directory:
   ```plaintext
   C:\Users\<YourUsername>\Documents\Rainmeter\Skins\WeeklyCalendar
   ```
3. Open Rainmeter **Manage**, expand `WeeklyCalendar`, select `WeeklyCalendar.ini`, and click **Load**.
   On first load the skin creates `@Resources\Private.inc`, where your calendar addresses go.
4. Link your calendar feed (see below).

---

## Configuration (`@Resources\Settings.inc`)

Right-click the skin on your desktop and select **Calendar settings** to open the configuration file.
Your private calendar addresses live in a separate file, `@Resources\Private.inc` (see below).

### 1. Linking your Google Calendar
1. Open [Google Calendar](https://calendar.google.com/) in your browser.
2. Click the settings gear icon > **Settings**.
3. Under *Settings for my calendars*, click your calendar name.
4. Scroll down to the **Integrate calendar** section.
5. Copy the **Secret address in iCal format** (`https://calendar.google.com/calendar/ical/.../basic.ics`).
6. Right-click the skin > **Calendar addresses** (opens `@Resources\Private.inc`) and paste it directly after `IcalUrl1=`:
   ```ini
   IcalUrl1=https://calendar.google.com/calendar/ical/your_address_here/basic.ics
   ```
7. Save the file, then right-click the skin > **Refresh skin**.

Up to 6 calendars can be shown, each in its own color: put the other addresses after `IcalUrl2=` ...
`IcalUrl6=`. A `Private.inc` created by an older version only lists `IcalUrl1..3`: add the lines
`IcalUrl4=`, `IcalUrl5=` and `IcalUrl6=` by hand when you need them.

> **Security Warning**: Keep your secret iCal address private! Anyone with that URL can view your schedule. `Private.inc` is listed in `.gitignore` so the address is never committed; do not paste it into `Settings.inc`.

### Public holidays
Google's holiday calendars have a public iCal address. For Italy, add to `Private.inc`:
```ini
IcalUrl2=https://calendar.google.com/calendar/ical/it.italian%23holiday%40group.v.calendar.google.com/public/basic.ics
```
For another country: Google Calendar > Settings > the "Holidays in ..." calendar > **Public address in iCal format**.

### Showing Google Tasks
Google never includes tasks in iCal addresses, so a tiny Google Apps Script (free, runs on your
own Google account) publishes them as a private iCal address. One-time setup, about 3 minutes:

1. Open [script.google.com](https://script.google.com/) and click **New project**.
2. Delete the sample code and paste the whole content of `tools\GoogleTasksFeed.gs`. Save (Ctrl+S).
3. In the left sidebar, click the **+** icon next to **Services**, pick **Google Tasks API**, click **Add**.
   If that dialog does not open: **Project Settings** (gear icon) > tick *Show "appsscript.json"
   manifest file in editor*, open `appsscript.json` and add inside the outer braces:
   `"dependencies": { "enabledAdvancedServices": [ { "userSymbol": "Tasks", "version": "v1", "serviceId": "tasks" } ] },`
4. In the toolbar, select the function `test` and click **Run**. Google asks for permission: choose
   your account, then *Advanced* > *Go to (project name)* > **Allow**. The log shows your tasks.
5. Click **Deploy** > **New deployment** > gear icon > **Web app**, then set
   *Execute as*: **Me** and *Who has access*: **Anyone**. Click **Deploy** and copy the **Web app URL**
   (`https://script.google.com/macros/s/.../exec`).
6. Paste it in `Private.inc` after `IcalUrl3=` (or any free slot), save and refresh the skin.

Tasks with a due date appear in the all-day row of that day. The Tasks API keeps only the date: a
task that has a time in the Google apps shows at that time when one of your Google calendars is
also in the skin (Google's iCal address lists it as a free event with the task's title, which the
skin shows as the task, once). Hover a task to see its description (notes). Their color is the `EventColor` of the slot
you used. Like the secret iCal address, keep the web app URL private: anyone who has it can read
your task titles and notes, mark your tasks completed or not completed, and change their dates. If you edit the script later,
use **Deploy** > **Manage deployments** > edit > *Version: New version* so the URL stays the same.
If the address is wrong, the toolbar shows "feed error" (hover it for details).

### Birthdays
Google Calendar shows your contacts' birthdays, but its iCal address leaves them out. The Tasks
script publishes them too, once it has the **Google Calendar API** service (step 2 of "Creating and
editing" below): take its web app URL, add `?feed=birthdays` at the end
(`https://script.google.com/macros/s/.../exec?feed=birthdays`) and paste it in a free slot of
`Private.inc`, for example `IcalUrl4=`. Pick its color with `EventColor4` in `Settings.inc` (Google
uses `51,182,121,255`). A click on a birthday opens it in Google Calendar. If the toolbar says
"feed error", hover it: the script says what is missing.

### Completing and moving tasks
Click the circle ○ at the start of a task to mark it completed, or the check mark ✓ to mark it
not completed: the skin shows the change at once, and Google Tasks saves it through the same web
app (it needs `curl.exe`, included in Windows 10 and 11). If Google does not confirm, the task goes
back to how it was and the toolbar shows "task not saved".

To move a task, drag it to another day and release it there: the day under the cursor (a column,
or a cell in the month view) is highlighted, the task is previewed where it will land and the
toolbar says where it will go. A plain click still opens the task's day in Google Calendar. Release
it on its own day, right-click or leave the skin to cancel. Dragging works in the 3-day, week and
month views (the day view has no other day to drop it on); events are dragged too (see Creating and editing). Two limits of the Tasks API:
a task that has a time set in the Google apps keeps only its new date, and moving one occurrence of a
repeating task may detach it from the series (the feed cannot tell which tasks repeat).

The circle and dragging work only with the current `tools\GoogleTasksFeed.gs` (moving tasks needs the
version of v1.8.0 or later). If the toolbar says **"update the Tasks script"**, or you set up the
script before these features, update it once:

1. Open your project on [script.google.com](https://script.google.com/), replace the code with the
   new `tools\GoogleTasksFeed.gs` and save.
2. Select `authorize` and click **Run**. Google asks for access to your tasks again: allow it
   (if the screen has checkboxes, tick the one about *editing* your tasks). The log must end with
   `OK: the skin can now mark tasks completed`.
3. **Deploy** > **Manage deployments** > pencil icon > *Version*: **New version** > **Deploy**.
   The web app URL does not change.

If the toolbar says **"allow editing tasks"**, the script was authorized for reading only: repeat
steps 2 and 3. If Google does not ask for permission and `authorize` fails, declare the scope by
hand: **Project Settings** (gear icon) > tick *Show "appsscript.json" manifest file in editor*,
open `appsscript.json`, add inside the outer braces
`"oauthScopes": ["https://www.googleapis.com/auth/tasks", "https://www.googleapis.com/auth/calendar"],`,
save, then run `authorize` again and deploy a new version.

### Creating and editing
The skin creates, edits, moves and deletes tasks and Google Calendar events through the same
Tasks script (`tools\GoogleTasksFeed.gs`, version 1.11.0 or later), which also needs access to
your calendar. Set it up once (or after updating the script):

1. Open your project on [script.google.com](https://script.google.com/), replace the code with the
   new `tools\GoogleTasksFeed.gs` and save.
2. Click the **+** next to **Services**, pick **Google Calendar API**, click **Add**. (Manifest
   alternative: add `{ "userSymbol": "Calendar", "version": "v3", "serviceId": "calendar" }` to
   `enabledAdvancedServices` in `appsscript.json`.)
3. Select `authorize` and click **Run**: allow access to your tasks and your calendar. The log must
   end with `OK: the skin can now change your calendar too.`
4. **Deploy** > **Manage deployments** > pencil icon > *Version*: **New version** > **Deploy**.

Recommended: with this, anyone who has the web app URL can also change your tasks and events.
Protect the changes with a secret: in the script, **Project Settings** > **Script properties** >
add `WRITE_TOKEN` with a long random value, and put the same value in `Private.inc`:
```ini
TasksToken=the same long random value
```
Reading the tasks feed does not need it.

How it works:
- **Create**: click an empty spot of the hours (an event at that half hour, one hour long), of
  the all-day row or a day number (a task for that day), or **+** in the toolbar (today, the next
  half hour). Type the title and press **Enter**. Before typing you can switch *Event* / *Task*,
  tick *All day*, and change the date and times with the **mouse wheel** over them. *More options*
  opens Google Calendar's own editor, filled in. Esc closes the title box; a click outside closes
  the card. Without the script the card offers *Open in Google Calendar* instead.
- **Details**: right-click an event or task. Holiday calendars, public addresses, other providers
  and invitations organised by someone else are read-only; the card says why.
- **Edit**: *Edit* in the card; type the new title and press Enter, or change date and times with
  the wheel and click *Save*. For a recurring event only that occurrence changes.
- **Delete**: *Delete* in the card (a recurring event asks: *This event* / *All events*). The item
  disappears and a bar offers **Undo** for 8 seconds (`UndoSeconds`); the request goes to Google only after that
  (a skin refresh in those seconds keeps the item).
- **Drag**: press an event and move it: a preview shows the new time (15-minute steps) and the
  toolbar says where it goes; release to move it. A plain click still opens it, even if the mouse
  slips a few pixels while pressing. Right-click or
  leave the skin to cancel. Events spanning several days are moved from Google Calendar.

Changes show at once. Google's iCal address can take minutes (sometimes hours) to show a change
to an event, so the skin keeps showing it until the feed has it (24 hours at most); tasks update
within seconds. If Google refuses a change, the item goes back and the toolbar says why (hover
it). New events go to your primary calendar; `CreateCalendar` and `TaskList` in `Settings.inc`
choose another calendar or task list.

What the mouse may do is set in `Settings.inc`:
```ini
; 1 = a click on an empty spot of the hours, the all-day row or a day number creates an item
; (0 = those spots do nothing; the + button still works)
ClickToCreate=1
; 1 = the + button in the toolbar
ShowCreateButton=1
; 1 = drag events and tasks to move them (0 = a press just opens them, nothing moves)
DragToMove=1
; 1 = right-click an event or task for its details, editing and deleting (0 = the skin menu)
RightClickCard=1
; Seconds a deletion can be undone before it goes to Google (2-60)
UndoSeconds=8
; Length of a new event in minutes (15-minute steps, default 60)
NewEventMinutes=60
```
With `RightClickCard=0` nothing can be edited or deleted from the skin; creating still works.

### 2. Visible Hours & Auto-Scroll
```ini
; Base visible time range (whole hours, 0-24)
; Total visible hours on screen = EndHour - StartHour (e.g. 20 - 8 = 12 hours)
StartHour=8
EndHour=20

; AutoScroll=1: automatically shifts the visible hours down in the afternoon/evening
; so you can always see evening events past 19:00 (7 PM).
AutoScroll=1

; Hour of the day (0-23) after which the view automatically shifts down (default: 14 = 2:00 PM)
AutoScrollHour=14

; Rows of all-day events and tasks (1-10); "+N more" expands the row
AllDayRows=3

; Startup view: day, 3day, week or month (the switcher in the toolbar saves its choice in Private.inc)
View=week
```

### 3. Dimensions & Appearance
```ini
; Dimensions in pixels
Width=1400
Height=800

; Language: en (English) or it (Italian) - also used for tooltips and the right-click menu
Language=en

; First day of the week: 1 = Monday, 0 = Sunday, 6 = Saturday
FirstDay=1

; Event colors (R,G,B,A or hex)
EventColor1=3,155,229,255
EventColor2=11,128,67,255
EventColor3=142,36,170,255
EventColor4=244,81,30,255
EventColor5=121,134,203,255
EventColor6=97,97,97,255

; Theme: light or dark. Individual colors (BgColor, TodayColor, ...) can be
; overridden by uncommenting them in Settings.inc
Theme=light

; Declined invitations: 1 = show outlined, 0 = hide
ShowDeclined=1

; Window position: -2 = On Desktop (always visible), -1 = Bottom (hidden in "Show desktop" mode)
ZPos=-2

; 1 = windows and dialogs you open always appear above the calendar (see below)
KeepDialogsOnTop=1
```

In "Show desktop" mode (which recent Windows 11 builds also enter just by clicking the desktop)
Rainmeter keeps *On Desktop* skins above every window, so a dialog such as "Empty Recycle Bin"
could open behind the calendar. With `KeepDialogsOnTop=1` the skin starts a tiny helper
(`@Resources\ZOrder`, compiled on first load with the C# compiler included in Windows) that moves
the calendar just below whatever window you activate and puts it back when you return to the
desktop. It uses no CPU while idle and closes by itself when Rainmeter exits.

Declined invitations are recognized from the address in your Google iCal URL. For other
providers, add your address to `MyEmail=` in `Private.inc`.

---

## Controls & Shortcuts

| Action | Control |
| :--- | :--- |
| **Scroll Hours** | Mouse wheel over calendar body / events / time column |
| **Scroll Up / Down** | Click the ▲ / ▼ buttons in the time column gutter |
| **Show Hidden Events** | Click a `▲ n` / `▼ n` badge in a day column |
| **Change View** | Click **Day**, **3 days**, **Week** or **Month** in the toolbar (saved in `Private.inc`) |
| **Navigate** | Click `<` / `>` buttons in the toolbar, or mouse wheel over the toolbar / day headers: one day, three days or a week, depending on the view. In the month view the wheel anywhere changes the month |
| **Open a Day** | In the month view, click a day (or its "+N more") to see it in the day view; middle-click opens it in Google Calendar |
| **Jump to Today** | Click the **Today** button in the toolbar (also resets hour scroll) |
| **Open an Event** | Click it: opens it in Google Calendar (a task or "+N more": that day). Middle-click: its Meet / Zoom / Teams link |
| **All-Day Row** | Click `+N more` to show every all-day item (middle-click: open that day in Google Calendar); click ▲ at the left of the row to collapse it |
| **Complete a Task** | Click the ○ at the start of the task (✓ to reopen it) |
| **Move a Task** | Drag it to another day (3-day, week and month views); right-click or leave the skin to cancel |
| **Create** | Click an empty spot of the hours (event), of the all-day row or a day number (task), or **+** in the toolbar; type the title, Enter (`ClickToCreate=0` / `ShowCreateButton=0` turn them off) |
| **Change Date / Time in the Card** | Mouse wheel over the date, start or end |
| **Details, Edit, Delete** | Right-click an event or task; *Undo* in the bar at the bottom within 8 seconds (`UndoSeconds`; `RightClickCard=0` shows the skin menu instead) |
| **Move an Event** | Drag it to another time or day (15-minute steps); right-click or leave the skin to cancel (`DragToMove=0` turns dragging off) |
| **Move the Skin** | Drag it by an empty area of the toolbar or the day headers: pressing an event, a task, a button or the grid does not move it |
| **Sync Calendar Now** | Click the sync time in the top-right corner, or right-click > *Refresh now* |
| **Context Menu** | Right-click the skin for quick access to weeks, hour scrolling, refresh, and settings |

---

## Project Structure

```plaintext
WeeklyCalendar/
├── WeeklyCalendar.ini        # Main Rainmeter skin definition
├── @Resources/
│   ├── Calendar.lua          # Core calendar engine (iCal parser, recurrence, layout)
│   ├── Settings.inc          # User preferences
│   ├── Private.inc           # Private calendar URLs (git-ignored, created on first load)
│   └── ZOrder/               # Helper that keeps dialogs above the skin (C# source + launcher)
├── tools/
│   ├── GoogleTasksFeed.gs    # Google Apps Script: Google Tasks as an iCal feed; creates, edits, moves and deletes tasks and events
│   ├── LiveTest.ps1          # Drives the real skin with real mouse and keyboard input (tooltips, dragging, wheel, typing)
│   └── textconv-utf16.py     # Readable git diffs for the UTF-16 Calendar.lua
├── tests/
│   ├── run_tests.py          # Test suite (runs Calendar.lua against a mock Rainmeter)
│   └── fixtures/             # Synthetic .ics feeds used by the tests
├── DownloadFile/             # Temporary folder where WebParser saves .ics files
└── README.md                 # Documentation
```

---

## Development

`@Resources\Calendar.lua` must stay saved as **UTF-16 LE with BOM**: Rainmeter 4.5 only treats
Lua strings as UTF-8 (accented titles, ▲ / ▼) in that encoding. Git stores it as-is, so GitHub
ZIP downloads work too. To get readable diffs, run once in your clone:

```plaintext
git config diff.utf16.textconv "python tools/textconv-utf16.py"
```

Run the tests (requires Python 3 and [lupa](https://pypi.org/project/lupa/)):

```plaintext
pip install lupa
python tests/run_tests.py
```

If [Node.js](https://nodejs.org/) is installed, the tests also run `tools/GoogleTasksFeed.gs`
against fake Tasks and Calendar APIs.

Lua 5.1 allows 200 local variables per function, and the main chunk of `Calendar.lua` is close:
past it Rainmeter refuses the whole script. Put new helpers inside a `do ... end` block or into a
table (`edit` holds those of the cards); `test_lua_main_chunk_has_room_for_locals` keeps some room.

Tooltips: no meter has a `ToolTipText` of its own. Rainmeter creates a window for each meter
that has one (about 50 ms each), which made the first layout take seconds. Calendar.lua keeps
each item's text and rectangle (`setTip`) and moves the single `[Tip]` meter onto the item under
the cursor; the items get `MeterStyle=... | StyItem` for the mouse actions that report it.
`StyItem` also gives every item a harmless `LeftMouseDownAction`: Rainmeter moves the whole skin
when the button is pressed where no meter has one, so only the background moves the skin.

To check the real skin with real mouse input (tooltips, dragging, the wheel), run
`tools\LiveTest.ps1` with PowerShell 7; its header lists the steps. For example, press on an event
and check that the skin did not move:

```plaintext
pwsh -File tools\LiveTest.ps1 -Front -Steps "pos; move 600 500; down; glide 660 540; up; pos"
```

---

## License

This project is licensed under the [CC0 1.0 Universal (Public Domain)](LICENSE) license.
