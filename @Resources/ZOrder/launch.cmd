@echo off
rem Builds (first time only) and starts the WeeklyCalendar z-order helper.
rem Run hidden by the skin; see ZOrderHelper.cs. The exe name carries a version
rem number: bump it in this file when ZOrderHelper.cs changes so it is rebuilt.
cd /d "%~dp0"
set EXE=WeeklyCalendarZOrder4.exe
if not exist "%EXE%" (
  for %%F in (Framework64 Framework) do (
    if not exist "%EXE%" if exist "%WINDIR%\Microsoft.NET\%%F\v4.0.30319\csc.exe" (
      "%WINDIR%\Microsoft.NET\%%F\v4.0.30319\csc.exe" /nologo /optimize /target:winexe /out:"%EXE%" ZOrderHelper.cs
    )
  )
)
if exist "%EXE%" start "" "%EXE%"
