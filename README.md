# WeeklyCalendar for Rainmeter

A sleek, modern, Google Calendar (Material 3) weekly planner skin for [Rainmeter](https://www.rainmeter.net/).

Powered directly by Google Calendar (or any standard iCalendar / `.ics` feed), it expands recurring events (`RRULE`, `EXDATE`, `RECURRENCE-ID`), converts timezones (`VTIMEZONE`), and provides smooth interactive navigation on your desktop.

![Rainmeter Weekly Calendar Preview](preview.png)

---

## Features

- **Google Calendar Material 3 Design**: Clean typography, Google Calendar pastel color scheme, subtle borders, today indicator circle, and red live "now" line.
- **Vertical Hour Scrolling**: Scroll the mouse wheel over the calendar grid or use the time-gutter buttons (▲ / ▼) to navigate through hours at any time.
- **Auto-Scroll for Evening Plans**: In the afternoon and evening (after 2:00 PM / 14:00 by default), the visible time window automatically shifts down so upcoming commitments after 19:00 (7 PM) through midnight are always in plain sight without manual scrolling.
- **Multi-Calendar Support**: Sync up to 3 distinct iCal feeds simultaneously, each with custom colors and titles.
- **Smart Recurrence & Overrides**: Full client-side parsing of RFC 5545 recurrence rules (`DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`), exceptions (`EXDATE`), and modified occurrences (`RECURRENCE-ID`).
- **All-Day Events & Timed Events**: Dedicated all-day events row at the top and column-packed overlapping timed events throughout the week.
- **Past Event Fading**: Completed events fade gracefully just like in Google Calendar.
- **Two-Zone Mouse Navigation**:
  - Scroll wheel over the **grid / events / time column**: scrolls hours up & down.
  - Scroll wheel over the **toolbar / day headers**: flips through weeks.
- **Detailed Tooltips**: Hover over any event to see its full title, start/end time, and location.
- **Dark & Light Themes**: Pre-configured light and dark themes matching Google Calendar.

---

## Installation

1. Make sure you have **[Rainmeter](https://www.rainmeter.net/)** installed (version 4.5 or newer).
2. Download or clone this repository into your Rainmeter skins directory:
   ```plaintext
   C:\Users\<YourUsername>\Documents\Rainmeter\Skins\WeeklyCalendar
   ```
3. Open `@Resources\Settings.inc` in a text editor (e.g. Notepad) and configure your calendar feed (see below).
4. Right-click the Rainmeter tray icon > **Refresh all**.
5. Open Rainmeter **Manage**, expand `WeeklyCalendar`, select `WeeklyCalendar.ini`, and click **Load**.

---

## Configuration (`@Resources\Settings.inc`)

Right-click the skin on your desktop and select **Calendar settings** to open the configuration file.

### 1. Linking your Google Calendar
1. Open [Google Calendar](https://calendar.google.com/) in your browser.
2. Click the settings gear icon > **Settings**.
3. Under *Settings for my calendars*, click your calendar name.
4. Scroll down to the **Integrate calendar** section.
5. Copy the **Secret address in iCal format** (`https://calendar.google.com/calendar/ical/.../basic.ics`).
6. In `Settings.inc`, paste it directly after `IcalUrl1=`:
   ```ini
   IcalUrl1=https://calendar.google.com/calendar/ical/your_address_here/basic.ics
   ```
7. Save the file, right-click the skin, and choose **Refresh now**.

> **Security Warning**: Keep your secret iCal address private! Anyone with that URL can view your schedule. Never commit your private URL to a public repository.

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
```

### 3. Dimensions & Appearance
```ini
; Dimensions in pixels
Width=1400
Height=800

; Language: en (English) or it (Italian)
Language=en

; First day of the week: 1 = Monday, 0 = Sunday, 6 = Saturday
FirstDay=1

; Event colors (R,G,B,A or hex)
EventColor1=3,155,229,255
EventColor2=11,128,67,255
EventColor3=142,36,170,255

; Dark theme: uncomment dark theme color values in Settings.inc
```

---

## Controls & Shortcuts

| Action | Control |
| :--- | :--- |
| **Scroll Hours** | Mouse wheel over calendar body / events / time column |
| **Scroll Up / Down** | Click the ▲ / ▼ buttons in the time column gutter |
| **Navigate Weeks** | Click `<` / `>` buttons in the toolbar, or mouse wheel over the toolbar / day headers |
| **Jump to Today** | Click the **Today** button in the toolbar (also resets hour scroll) |
| **Sync Calendar Now** | Click the sync time in the top-right corner, or right-click > *Refresh now* |
| **Context Menu** | Right-click the skin for quick access to weeks, hour scrolling, refresh, and settings |

---

## Project Structure

```plaintext
WeeklyCalendar/
├── WeeklyCalendar.ini        # Main Rainmeter skin definition
├── @Resources/
│   ├── Calendar.lua          # Core calendar engine (iCal parser, recurrence, layout)
│   └── Settings.inc          # User preferences and calendar URLs
├── DownloadFile/             # Temporary folder where WebParser saves .ics files
└── README.md                 # Documentation
```

---

## License

This project is licensed under the [CC0 1.0 Universal (Public Domain)](LICENSE) license.
