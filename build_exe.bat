@echo off
setlocal
echo ================================================
echo  CafresoHQ -- Build Standalone .exe
echo ================================================
echo.

:: Install PyInstaller
pip install pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: Could not install PyInstaller. Check your Python/pip setup.
    pause & exit /b 1
)

:: Build -- onedir so static files sit alongside the exe and can be edited live.
:: Semicolon separates source;dest on Windows (colon on Mac/Linux).
pyinstaller ^
    --name "CafresoHQ" ^
    --onedir ^
    --noconfirm ^
    --clean ^
    --add-data "hq.html;." ^
    --add-data "app.jsx;." ^
    --add-data "views.jsx;." ^
    --add-data "ui.jsx;." ^
    --add-data "styles.css;." ^
    --add-data "features.jsx;." ^
    --add-data "missions.jsx;." ^
    --add-data "modals.jsx;." ^
    --add-data "tweaks-panel.jsx;." ^
    --add-data "sprites.jsx;." ^
    --add-data "mock-data.jsx;." ^
    --add-data "claude-client.jsx;." ^
    --add-data "agent_runner.jsx;." ^
    --add-data "manifest.webmanifest;." ^
    --add-data "sw.js;." ^
    serve.py

if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    pause & exit /b 1
)

echo.
echo ================================================
echo  Build complete!
echo  Location: dist\CafresoHQ\CafresoHQ.exe
echo.
echo  To run:  double-click CafresoHQ.exe
echo           or: dist\CafresoHQ\CafresoHQ.exe
echo.
echo  Mobile access: the exe prints your LAN IP on startup.
echo  Share that URL with any phone on the same Wi-Fi.
echo ================================================
pause
endlocal
