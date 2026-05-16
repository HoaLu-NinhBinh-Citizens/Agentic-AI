@echo off
REM  Set up project
set BAT_DIR=%~dp0

REM  Clean project EngineCar - CarEngine
cd /d %BAT_DIR%
cd /d ./EngineCar/Project/Chip/Stm32F407/CarEngine
if exist CMakeFiles (RD /s /Q CMakeFiles)
if exist Makefile (DEL /s /Q /F Makefile)
if exist cmake_install.cmake (DEL /s /Q /F cmake_install.cmake)
if exist CMakeCache.txt (DEL /s /Q /F CMakeCache.txt)
if exist compile_commands.json (DEL /s /Q /F compile_commands.json)
if exist %BAT_DIR%output\EngineCar\CarEngine_build_log.txt (DEL /s /Q /F %BAT_DIR%output\EngineCar\CarEngine_build_log.txt)
if exist %BAT_DIR%output\EngineCar\CarEngine.map (DEL /s /Q /F %BAT_DIR%output\EngineCar\CarEngine.map)
if exist callgraph_file_release.cgx (DEL /s /Q /F callgraph_file_release.cgx)
if exist %BAT_DIR%output\EngineCar\CarEngine.elf (DEL /s /Q /F %BAT_DIR%output\EngineCar\CarEngine.elf)
if exist %BAT_DIR%output\EngineCar\CarEngine.bin (DEL /s /Q /F %BAT_DIR%output\EngineCar\CarEngine.bin)
if exist %BAT_DIR%output (rmdir %BAT_DIR%output\EngineCar)
if exist %BAT_DIR%output (rmdir %BAT_DIR%output)
if exist %BAT_DIR%Tools\segger\ozone\EngineCar.jdebug.user (DEL /s /Q /F %BAT_DIR%Tools\segger\ozone\EngineCar.jdebug.user)

REM  Clean project EngineCar - BootLoader
cd /d %BAT_DIR%
cd /d ./EngineCar/Project/Chip/Stm32F407/BootLoader
if exist CMakeFiles (RD /s /Q CMakeFiles)
if exist Makefile (DEL /s /Q /F Makefile)
if exist cmake_install.cmake (DEL /s /Q /F cmake_install.cmake)
if exist CMakeCache.txt (DEL /s /Q /F CMakeCache.txt)
if exist compile_commands.json (DEL /s /Q /F compile_commands.json)
if exist %BAT_DIR%output\EngineCar\BootLoader_build_log.txt (DEL /s /Q /F %BAT_DIR%output\EngineCar\BootLoader_build_log.txt)
if exist %BAT_DIR%output\EngineCar\BootLoader.map (DEL /s /Q /F %BAT_DIR%output\EngineCar\BootLoader.map)
if exist callgraph_file_release.cgx (DEL /s /Q /F callgraph_file_release.cgx)
if exist %BAT_DIR%output\EngineCar\BootLoader.elf (DEL /s /Q /F %BAT_DIR%output\EngineCar\BootLoader.elf)
if exist %BAT_DIR%output\EngineCar\BootLoader.bin (DEL /s /Q /F %BAT_DIR%output\EngineCar\BootLoader.bin)
if exist %BAT_DIR%output (rmdir %BAT_DIR%output\EngineCar)
if exist %BAT_DIR%output (rmdir %BAT_DIR%output)
if exist %BAT_DIR%Tools\segger\ozone\EngineCar.jdebug.user (DEL /s /Q /F %BAT_DIR%Tools\segger\ozone\EngineCar.jdebug.user)

REM  Clean project RemoteControl - CarRemote
cd /d %BAT_DIR%
cd /d ./RemoteControl/Project/Chip/Stm32F407/CarRemote
if exist CMakeFiles (RD /s /Q CMakeFiles)
if exist Makefile (DEL /s /Q /F Makefile)
if exist cmake_install.cmake (DEL /s /Q /F cmake_install.cmake)
if exist CMakeCache.txt (DEL /s /Q /F CMakeCache.txt)
if exist compile_commands.json (DEL /s /Q /F compile_commands.json)
if exist %BAT_DIR%output\RemoteControl\CarRemote_build_log.txt (DEL /s /Q /F %BAT_DIR%output\RemoteControl\CarRemote_build_log.txt)
if exist %BAT_DIR%output\RemoteControl\CarRemote.map (DEL /s /Q /F %BAT_DIR%output\RemoteControl\CarRemote.map)
if exist callgraph_file_release.cgx (DEL /s /Q /F callgraph_file_release.cgx)
if exist %BAT_DIR%output\RemoteControl\CarRemote.elf (DEL /s /Q /F %BAT_DIR%output\RemoteControl\CarRemote.elf)
if exist %BAT_DIR%output\RemoteControl\CarRemote.bin (DEL /s /Q /F %BAT_DIR%output\RemoteControl\CarRemote.bin)
if exist %BAT_DIR%output (rmdir %BAT_DIR%output\RemoteControl)
if exist %BAT_DIR%output (rmdir %BAT_DIR%output)
if exist %BAT_DIR%Tools\segger\ozone\RemoteControl.jdebug.user (DEL /s /Q /F %BAT_DIR%Tools\segger\ozone\RemoteControl.jdebug.user)

REM  Clean project RemoteControl - BootLoader
cd /d %BAT_DIR%
cd /d ./RemoteControl/Project/Chip/Stm32F407/BootLoader
if exist CMakeFiles (RD /s /Q CMakeFiles)
if exist Makefile (DEL /s /Q /F Makefile)
if exist cmake_install.cmake (DEL /s /Q /F cmake_install.cmake)
if exist CMakeCache.txt (DEL /s /Q /F CMakeCache.txt)
if exist compile_commands.json (DEL /s /Q /F compile_commands.json)
if exist %BAT_DIR%output\RemoteControl\BootLoader_build_log.txt (DEL /s /Q /F %BAT_DIR%output\RemoteControl\BootLoader_build_log.txt)
if exist %BAT_DIR%output\RemoteControl\BootLoader.map (DEL /s /Q /F %BAT_DIR%output\RemoteControl\BootLoader.map)
if exist callgraph_file_release.cgx (DEL /s /Q /F callgraph_file_release.cgx)
if exist %BAT_DIR%output\RemoteControl\BootLoader.elf (DEL /s /Q /F %BAT_DIR%output\RemoteControl\BootLoader.elf)
if exist %BAT_DIR%output\RemoteControl\BootLoader.bin (DEL /s /Q /F %BAT_DIR%output\RemoteControl\BootLoader.bin)
if exist %BAT_DIR%output (rmdir %BAT_DIR%output\RemoteControl)
if exist %BAT_DIR%output (rmdir %BAT_DIR%output)
if exist %BAT_DIR%Tools\segger\ozone\RemoteControl.jdebug.user (DEL /s /Q /F %BAT_DIR%Tools\segger\ozone\RemoteControl.jdebug.user)

REM  End Clean
cd /d %BAT_DIR%