@echo off
REM Set up project
setlocal EnableDelayedExpansion
set BAT_DIR=%~dp0

set "param=%1"

if /I "!param!"=="enginecar" (
    set aJobs[0]=0 %BAT_DIR%Tools\segger\jlink\EngineCar_BootLoader.jflash %BAT_DIR%output\EngineCar\BootLoader.elf
    set aJobs[1]=0 %BAT_DIR%Tools\segger\jlink\EngineCar_CarEngine.jflash %BAT_DIR%output\EngineCar\CarEngine.elf
) else if /I "!param!"=="remotecontrol" (
    set aJobs[0]=0 %BAT_DIR%Tools\segger\jlink\RemoteControl_BootLoader.jflash %BAT_DIR%output\RemoteControl\BootLoader.elf
    set aJobs[1]=0 %BAT_DIR%Tools\segger\jlink\RemoteControl_CarRemote.jflash %BAT_DIR%output\RemoteControl\CarRemote.elf
) else (
    echo Invalid command...
    echo Example:
    echo Execute.bat EngineCar
    echo Execute.bat RemoteControl
    exit /b
)

:Main
setlocal ENABLEDELAYEDEXPANSION
set "lock=%temp%\wait!random!.lock"
echo Starting J-Flash...
set /a Cnt=0
:_JobStartLoop
if defined aJobs[%Cnt%] (
    start "" 9>"!lock!%Cnt%" %BAT_DIR%Tools\segger\jlink\StartJFlash.bat %%aJobs[%Cnt%]%%
    set /a "Cnt+=1"
    timeout /nobreak /t 2
    GOTO :_JobStartLoop
)

echo Waiting for J-Flash to finish...

set /a Cnt=0
:_JobWaitLoop
if defined aJobs[%Cnt%] (
    call :WaitForUnlock !lock!%Cnt% >nul 2>&1
    set /a "Cnt+=1"
    GOTO :_JobWaitLoop
)

del "!lock!*"
echo Done.
exit /b

:WaitForUnlock
goto :Start
:Retry
1>nul 2>nul ping /n 2 ::1
:Start
call 9>"%~1" || goto Retry
exit /b