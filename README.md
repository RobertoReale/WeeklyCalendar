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
- **Google Tasks & Holidays**: Tasks with a due date appear in the all-day row like in Google Calendar (○ open, ✓ completed and struck through), via a small Google Apps Script; click the circle to mark a task completed (or the check mark to reopen it), or drag it to another day. Public holidays come from Google's holiday calendars.
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

Tasks with a due date appear in the all-day row of that day; the Tasks API keeps only the date, not
the time. Hover a task to see its description (notes). Their color is the `EventColor` of the slot
you used. Like the secret iCal address, keep the web app URL private: anyone who has it can read
your task titles and notes, mark your tasks completed or not completed, and change their dates. If you edit the script later,
use **Deploy** > **Manage deployments** > edit > *Version: New version* so the URL stays the same.
If the address is wrong, the toolbar shows "feed error" (hover it for details).

### Completing tasks
Click the circle ○ at the start of a task to mark it completed, or the check mark ✓ to mark it
not completed: the skin shows the change at once, and Google Tasks saves it through the same web
app (it needs `curl.exe`, included in Windows 10 and 11). If Google does not confirm, the task goes
back to how it was and the toolbar shows "task not saved".

To move a task, drag it to another day of the week and release it there: the column under the
cursor is highlighted, the task is previewed in its all-day row and the toolbar says where it will
go. A plain click still opens the task's day in Google Calendar. Release it on its own day, right-click
or leave the skin to cancel. Dragging works in the 3-day and week views. Two limits of the Tasks API:
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
`"oauthScopes": ["https://www.googleapis.com/auth/tasks"],`, save, then run `authorize` again
and deploy a new version.

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
| **Move a Task** | Drag it to another day (3-day and week views); right-click or leave the skin to cancel |
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
│   ├── GoogleTasksFeed.gs    # Google Apps Script that publishes Google Tasks as an iCal feed
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
against a fake Tasks API.

Tooltips: no meter has a `ToolTipText` of its own. Rainmeter creates a window for each meter
that has one (about 50 ms each), which made the first layout take seconds. Calendar.lua keeps
each item's text and rectangle (`setTip`) and moves the single `[Tip]` meter onto the item under
the cursor; the items get `MeterStyle=... | StyTip` for the mouse actions that report it.

---

## License

This project is licensed under the [CC0 1.0 Universal (Public Domain)](LICENSE) license.
