@echo off
set JLINK_DIR=%JLINK_PATH%

start /wait "%JLINK_DIR%\J-Flash" "%JLINK_DIR%\JFlash.exe" -usb%1 -openprj%2 -open%3 -auto -exit
IF ERRORLEVEL 1 goto ERROR
goto END

:ERROR
ECHO %ERRORLEVEL%
ECHO J-Flash: Error! SN: %1
pause
exit

:END
ECHO J-Flash: Succeed!
exit