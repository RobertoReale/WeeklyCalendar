; ======================================================================
;  WeeklyCalendar - CONFIGURATION SETTINGS
;  After saving changes: right-click the skin and select "Refresh skin"
;  (or right-click the Rainmeter tray icon and choose "Refresh all").
; ======================================================================

[Variables]

; ---------------------------------------------------------------------
;  1) iCAL CALENDAR ADDRESSES (REQUIRED)
; ---------------------------------------------------------------------
;  The addresses are stored in @Resources\Private.inc (ignored by git, created
;  automatically on first load). Right-click the skin > "Calendar addresses".
;  Google Calendar -> Settings (gear icon) -> (your calendar name)
;  -> "Integrate calendar" -> "Secret address in iCal format".
;  KEEP IT PRIVATE: anyone with this link can view your events.
;  You can add up to 6 calendars (each rendered with its own color), for example:
;   - public holidays: Google Calendar -> Settings -> "Holidays in <country>" ->
;     "Public address in iCal format" (Italy:
;     https://calendar.google.com/calendar/ical/it.italian%23holiday%40group.v.calendar.google.com/public/basic.ics)
;   - Google Tasks: they are not part of any iCal address; publish them with
;     tools\GoogleTasksFeed.gs (see README, "Showing Google Tasks").
;  The empty values below are only fallbacks: do not paste your addresses here.
IcalUrl1=
IcalUrl2=
IcalUrl3=
IcalUrl4=
IcalUrl5=
IcalUrl6=

; Sync interval in minutes (how often to redownload the calendar feed)
RefreshMinutes=10

; ---------------------------------------------------------------------
;  2) LANGUAGE AND FIRST DAY OF WEEK
; ---------------------------------------------------------------------
;  Language: en (English) or it (Italian)
Language=en

;  FirstDay: 1 = Monday, 0 = Sunday, 6 = Saturday
FirstDay=1

; ---------------------------------------------------------------------
;  3) DIMENSIONS AND VISIBLE HOURS
; ---------------------------------------------------------------------
;  Skin dimensions in pixels.
;  Tip: if your Windows display scaling is 125% or 150%, reduce Width and Height
;  (for example, 1500 x 900 on 1080p).
Width=1400
Height=800

;  Base visible time range (whole hours, 0-24).
;  The number of visible hours displayed on screen is: EndHour - StartHour (e.g. 20 - 8 = 12 hours).
StartHour=8
EndHour=20

;  AutoScroll=1: automatically shifts the visible hours down in the afternoon/evening
;  so you can always see upcoming evening events (e.g. past 19:00 / 7 PM).
;  Set to 0 to keep the view fixed at StartHour unless scrolled manually.
AutoScroll=1

;  AutoScrollHour: the hour of the day (0-23) after which the view automatically shifts down (default: 14 = 2:00 PM).
AutoScrollHour=14

;  View: day, 3day or week (default) - the view shown when the skin starts. The view picked
;  with the switcher in the toolbar is saved in Private.inc and wins over this value.
View=week

;  AllDayRows: rows of all-day events and tasks shown above the hours (1-10, default 3).
;  A busier day ends with "+N more": click it to show every item, then the arrow at the
;  left of the row to collapse it again.
AllDayRows=3

;  ShowToolbar=1: shows the top toolbar (Today button, navigation arrows, month, week badge, sync status,
;  view switcher)
ShowToolbar=1

;  ZPos: window position of the skin (applied on every refresh).
;   -2 = On Desktop (recommended): always visible on the desktop. While Windows is in
;        "Show desktop" mode Rainmeter keeps it above other windows; KeepDialogsOnTop
;        (below) moves it under any window or dialog you open.
;   -1 = Bottom: never covers dialogs, but in "Show desktop" mode (Win+D, and on recent
;        Windows 11 builds often just after unlocking or clicking the desktop) the skin
;        falls behind the desktop and disappears until "Refresh all".
;    0 = Normal, 1 = Topmost, 2 = Always on top.
ZPos=-2

;  KeepDialogsOnTop=1: with ZPos=-2, windows and dialogs you open (e.g. "Empty Recycle Bin")
;  always appear above the calendar, even in "Show desktop" mode. It starts a tiny helper
;  (@Resources\ZOrder, built on first load with the C# compiler included in Windows) that
;  closes by itself with Rainmeter. Set to 0 to turn it off.
KeepDialogsOnTop=1

; ---------------------------------------------------------------------
;  4) APPEARANCE & STYLING
; ---------------------------------------------------------------------
FontFace=Segoe UI
FontSize=9
TitleFontSize=16
EventRadius=8
BgRadius=16

;  Colors: R,G,B,A (0-255) format or hex RRGGBB / RRGGBBAA.
;  Event colors for calendars 1 to 6 (defaults from Google Calendar: Peacock, Basil, Grape,
;  Tangerine, Lavender, Graphite)
EventColor1=3,155,229,255
EventColor2=11,128,67,255
EventColor3=142,36,170,255
EventColor4=244,81,30,255
EventColor5=121,134,203,255
EventColor6=97,97,97,255

;  Past events fade amount (0 = no fade, 1 = invisible; 0.35 = subtle like Google Calendar)
PastFade=0.35

;  Invitations you declined: 1 = show them outlined (like Google Calendar), 0 = hide them.
;  Your address is detected from the Google iCal URL; for other providers set MyEmail
;  in Private.inc (right-click the skin > "Calendar addresses").
ShowDeclined=1

;  ClickAction: what a left click on an event or task opens.
;   calendar = the event in Google Calendar (a task: its day); the middle click opens
;              the event's link (Meet, Zoom, Teams...) when it has one.
;   link     = the event's link when it has one, otherwise Google Calendar; the middle
;              click opens Google Calendar.
ClickAction=calendar

;  Theme: light or dark (Google Calendar Material 3 colors).
Theme=light

;  Optional custom colors: uncomment a line to override the theme color.
;  SelBgColor / SelTextColor: the selected view in the toolbar switcher.
; BgColor=255,255,255,255
; GridColor=224,227,231,255
; DayNumColor=31,31,31,255
; MutedColor=116,119,117,255
; TodayColor=11,87,208,255
; TodayTextColor=255,255,255,255
; NowColor=234,67,53,255
; EventTextColor=255,255,255,255
; PastTextColor=255,255,255,230
; BadgeBgColor=239,241,241,255
; BadgeTextColor=68,71,70,255
; BorderColor=218,220,224,255
; SelBgColor=211,227,253,255
; SelTextColor=4,30,73,255
