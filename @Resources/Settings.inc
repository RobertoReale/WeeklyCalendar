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
;  You can add up to 3 calendars (each rendered with its own color).
;  The empty values below are only fallbacks: do not paste your addresses here.
IcalUrl1=
IcalUrl2=
IcalUrl3=

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

;  ShowToolbar=1: shows the top toolbar (Today button, navigation arrows, month, week badge, sync status)
ShowToolbar=1

;  ZPos: window position of the skin (applied on every refresh).
;   -1 = Bottom: behind all windows; Explorer dialogs (e.g. "Empty Recycle Bin")
;        always appear above it, but the skin is hidden by Show Desktop (Win+D).
;   -2 = On Desktop: stays visible with Show Desktop, but while Show Desktop is
;        active Rainmeter keeps it above other windows, so dialogs may open behind it.
;    0 = Normal, 1 = Topmost, 2 = Always on top.
ZPos=-1

; ---------------------------------------------------------------------
;  4) APPEARANCE & STYLING
; ---------------------------------------------------------------------
FontFace=Segoe UI
FontSize=9
TitleFontSize=16
EventRadius=8
BgRadius=16

;  Colors: R,G,B,A (0-255) format or hex RRGGBB / RRGGBBAA.
;  Event colors for calendars 1, 2, and 3 (Default: Google Calendar Peacock: 3,155,229,255)
EventColor1=3,155,229,255
EventColor2=11,128,67,255
EventColor3=142,36,170,255

;  Past events fade amount (0 = no fade, 1 = invisible; 0.35 = subtle like Google Calendar)
PastFade=0.35

;  Invitations you declined: 1 = show them outlined (like Google Calendar), 0 = hide them.
;  Your address is detected from the Google iCal URL; for other providers set MyEmail
;  in Private.inc (right-click the skin > "Calendar addresses").
ShowDeclined=1

;  Theme: light or dark (Google Calendar Material 3 colors).
Theme=light

;  Optional custom colors: uncomment a line to override the theme color.
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
