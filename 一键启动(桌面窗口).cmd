@echo off
setlocal
title SHUBAN Desktop Window
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-desktop.ps1" %*
if errorlevel 1 (
    echo.
    echo Desktop window did not start. Read the message above, or use the normal launcher.
    pause
    exit /b 1
)
endlocal
