@echo off
setlocal
title CafresoHQ — Windows Build
color 0A

echo.
echo  ==========================================
echo    CafresoHQ  ^|  Windows Installer Build
echo  ==========================================
echo.

REM ── 1. Check Python ───────────────────────────────────────────────────────
echo [1/5] Checking Python...
py --version >nul 2>&1
if %errorlevel% neq 0 (
  python --version >nul 2>&1
  if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Python 3 not found.
    echo  Download from https://python.org/downloads
    echo  Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
  )
  set PYTHON=python
) else (
  set PYTHON=py
)
echo        OK — %PYTHON% found

REM ── 2. Check Node / npm ────────────────────────────────────────────────────
echo [2/5] Checking Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
  echo.
  echo  ERROR: Node.js not found.
  echo  Download from https://nodejs.org (LTS recommended)
  echo.
  pause
  exit /b 1
)
echo        OK — node found

REM ── 3. Generate icon ───────────────────────────────────────────────────────
echo [3/5] Generating icon...
cd /d "%~dp0electron"
%PYTHON% make-icon.py
if %errorlevel% neq 0 (
  echo  WARNING: Icon generation failed — build will use default icon.
)

REM ── 4. Install npm dependencies ────────────────────────────────────────────
echo [4/5] Installing npm packages (electron + electron-builder)...
npm install
if %errorlevel% neq 0 (
  echo  ERROR: npm install failed.
  pause
  exit /b 1
)

REM ── 5. Build installer ─────────────────────────────────────────────────────
echo [5/5] Building Windows installer (.exe)...
npm run build
if %errorlevel% neq 0 (
  echo  ERROR: electron-builder failed.
  pause
  exit /b 1
)

echo.
echo  ==========================================
echo    BUILD COMPLETE
echo.
echo    Installer: dist\CafresoHQ Setup.exe
echo  ==========================================
echo.
cd /d "%~dp0"
explorer dist
pause
