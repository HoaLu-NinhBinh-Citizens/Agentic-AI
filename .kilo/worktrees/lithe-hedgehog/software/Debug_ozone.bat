@echo off
REM Set up project
setlocal EnableDelayedExpansion
set BAT_DIR=%~dp0
set OZONE_DIR="C:\Program Files\SEGGER\Ozone\Ozone.exe"

set "param=%1"

if /I "!param!"=="enginecar" (
    set debug_file=%BAT_DIR%Tools\segger\ozone\EngineCar.jdebug
) else if /I "!param!"=="remotecontrol" (
    set debug_file=%BAT_DIR%Tools\segger\ozone\RemoteControl.jdebug
) else (
    echo Invalid command...
    echo Example:
    echo Debug_ozone.bat EngineCar
    echo Debug_ozone.bat RemoteControl
    exit /b
)

start "" %OZONE_DIR% %debug_file%