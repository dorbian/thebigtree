@echo off
REM Frontend development server launcher
REM Connects to remote API server
REM Edit the API URL in dev_frontend.py to change the server

echo.
echo ========================================
echo BigTree Frontend Dev Server
echo ========================================
echo.

REM Try different Python commands
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Connecting to remote API...
    python dev_frontend.py
    goto :end
)

where python3 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Connecting to remote API...
    python3 dev_frontend.py
    goto :end
)

where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Connecting to remote API...
    py -3 dev_frontend.py
    goto :end
)

echo ERROR: Python not found in PATH
pause
goto :end

:end
