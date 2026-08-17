@echo off
REM The one thing you need to run. Sets up whatever is missing on the first run,
REM then starts the app; on later runs it goes straight to starting.
REM
REM -ExecutionPolicy Bypass is what lets this work on a copy that arrived by
REM email or download: Windows marks those files as untrusted, and the default
REM RemoteSigned policy would otherwise refuse to run the .ps1.
setlocal
cd /d "%~dp0"
title JobLookup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run.ps1" %*
if errorlevel 1 (
    echo.
    echo JobLookup stopped unexpectedly. The messages above explain why.
    pause
)
endlocal
