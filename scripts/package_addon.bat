@echo off
echo BASICs Shape Key Manager - Packaging Tool
echo ========================================
echo.

REM Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

:menu
cls
echo What would you like to do?
echo.
echo 1) Just package the addon to ZIP
echo 2) Package and install to Blender
echo 3) Exit
echo.
set /p choice="Enter your choice (1-3): "

if "%choice%"=="1" (
    python package_addon.py
    echo.
    echo Done. Press any key to return to the menu...
    pause >nul
    goto menu
)

if "%choice%"=="2" (
    echo.
    set /p blender_version="Enter Blender version (e.g., 4.3): "
    echo.
    set /p blender_exe="Enter path to Blender executable (optional, leave empty to skip): "
    
    if "%blender_exe%"=="" (
        python package_addon.py --install --blender-version=%blender_version%
    ) else (
        python package_addon.py --install --blender-version=%blender_version% --blender-exe="%blender_exe%"
    )
    
    echo.
    echo Done. Press any key to return to the menu...
    pause >nul
    goto menu
)

if "%choice%"=="3" (
    exit /b 0
)

echo Invalid choice. Press any key to try again...
pause >nul
goto menu 