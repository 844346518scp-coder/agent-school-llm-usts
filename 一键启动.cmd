@echo off
setlocal
title SHUBAN Launcher
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
    echo.
    echo Startup failed. Please read the message above and README.md.
    pause
    exit /b 1
)
endlocal
