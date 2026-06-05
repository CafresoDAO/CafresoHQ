@echo off
REM CafresoHQ launcher (double-click on Windows).
REM Delegates to the PowerShell launcher, which runs the whole stack in WSL
REM and opens the browser once the backend is listening.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-CafresoHQ.ps1"
