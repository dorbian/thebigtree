@echo off
REM Development server launcher for BigTree
REM This script tries to find and use Python on your system

echo.
echo ========================================
echo BigTree Development Web Server
echo ========================================
echo.

REM Try different Python commands
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Found: python
    python dev_server.py
    goto :end
)

where python3 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Found: python3
    python3 dev_server.py
    goto :end
)

where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Found: py launcher
    py -3 dev_server.py
    goto :end
)

echo ERROR: Python not found in PATH
echo.
echo Please install Python 3.8+ or ensure it's in your PATH.
echo You can download Python from: https://www.python.org/downloads/
echo.
echo After installing, make sure to check "Add Python to PATH" during installation.
pause
goto :end

:end
