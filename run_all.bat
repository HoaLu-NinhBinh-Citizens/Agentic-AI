@echo off
REM AI_SUPPORT - Run Everything Batch Script for Windows
REM This script starts all components of AI_SUPPORT on Windows

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║              AI_SUPPORT - Embedded Engineering Assistant         ║
echo ║                    Starting All Components...                     ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Check command line arguments
set SETUP_MODE=0
set DEBUG_MODE=0
set NO_UI=0

:parse_args
if "%1"=="" goto :args_done
if "%1"=="--setup" set SETUP_MODE=1
if "%1"=="--debug" set DEBUG_MODE=1
if "%1"=="--no-ui" set NO_UI=1
if "%1"=="--help" (
    call :show_help
    exit /b 0
)
shift
goto :parse_args

:args_done

REM Set colors (Windows 10+)
if "%DEBUG_MODE%"=="1" (
    color 0F
) else (
    color 0A
)

REM Set project root
set PROJECT_ROOT=%~dp0
cd /d "%PROJECT_ROOT%"

REM Create logs directory
if not exist "logs" mkdir logs

REM Function to check if a command exists
:command_exists
setlocal
set CMD=%~1
where %CMD% >nul 2>nul
if %ERRORLEVEL% equ 0 (
    endlocal & set COMMAND_EXISTS=1
) else (
    endlocal & set COMMAND_EXISTS=0
)
exit /b

REM Step 1: Setup AI providers if requested
if "%SETUP_MODE%"=="1" (
    echo [→] Running AI provider setup...
    if exist "scripts\setup_ai_provider.py" (
        python scripts\setup_ai_provider.py
        if errorlevel 1 (
            echo [✗] AI setup failed or was cancelled
        ) else (
            echo [✓] AI setup completed
        )
    ) else (
        echo [✗] Setup script not found: scripts\setup_ai_provider.py
    )
    echo.
)

REM Step 2: Check Python - with Microsoft Store bypass
echo [→] Checking Python...
echo [i] Note: If you see Microsoft Store popup, Python is not properly installed

REM First check if python.exe exists in PATH (bypass Microsoft Store alias)
where python.exe >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=python.exe
    goto :python_found
)

where python3.exe >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=python3.exe
    goto :python_found
)

REM Check common Python installation paths
set PYTHON_PATHS=
for %%i in ("C:\Python3*", "C:\Python\Python3*", "%LOCALAPPDATA%\Programs\Python\Python3*", "%ProgramFiles%\Python3*") do (
    if exist "%%i\python.exe" (
        set PYTHON_CMD="%%i\python.exe"
        set PYTHON_FROM_PATH=1
        goto :python_found
    )
)

REM Check if Python is in AppData (common for user installs)
for /f "tokens=*" %%i in ('dir /b /s "%LOCALAPPDATA%\Microsoft\WindowsApps\python*.exe" 2^>nul ^| findstr /v "installer"') do (
    set PYTHON_CMD="%%i"
    set PYTHON_FROM_PATH=1
    goto :python_found
)

REM Python not found, show installation options
echo [✗] Python is required but not found
echo.
echo [⚠] Please install Python 3.8+ using one of these options:
echo.
echo [1] Download from python.org (Recommended):
echo     https://www.python.org/downloads/
echo.
echo [2] Install via Microsoft Store (if you prefer):
echo     Open Microsoft Store and search for "Python"
echo.
echo [3] Install via Winget (Windows Package Manager):
echo     winget install Python.Python.3.11
echo.
echo IMPORTANT: During installation, CHECK "Add Python to PATH"
echo.
pause
exit /b 1

:python_found
if defined PYTHON_FROM_PATH (
    echo [⚠] Python found at: %PYTHON_CMD%
    echo [i] Adding to PATH temporarily...
    for %%i in (%PYTHON_CMD%) do set "PYTHON_DIR=%%~dpi"
    set PATH=%PYTHON_DIR%;%PATH%
    set PYTHON_CMD=python.exe
) else (
    echo [✓] Python found in PATH
)

REM Check Python version
%PYTHON_CMD% --version
if errorlevel 1 (
    echo [✗] Failed to run Python
    pause
    exit /b 1
)

REM Step 3: Install Python dependencies if needed
echo [→] Checking Python dependencies...
%PYTHON_CMD% -c "import fastapi, uvicorn, asyncio" >nul 2>nul
if errorlevel 1 (
    echo [⚠] Installing Python dependencies...
    %PYTHON_CMD% -m pip install fastapi uvicorn[standard] websockets pydantic aiohttp openai anthropic
    if errorlevel 1 (
        echo [✗] Failed to install Python dependencies
        pause
        exit /b 1
    )
    echo [✓] Python dependencies installed
) else (
    echo [✓] FastAPI/Uvicorn dependencies OK
)

REM Step 4: Start backend server
echo [→] Starting backend server on http://localhost:8000
set BACKEND_LOG=logs\backend_%DATE:~-4,4%%DATE:~-10,2%%DATE:~-7,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%.log
echo [i] Logs: %BACKEND_LOG%

REM Set environment variables
set HOST=0.0.0.0
set PORT=8000
set LOG_LEVEL=INFO
if "%DEBUG_MODE%"=="1" set LOG_LEVEL=DEBUG
set PYTHONPATH=%PROJECT_ROOT%\src

REM Start backend in background
start "AI_SUPPORT Backend" /B %PYTHON_CMD% -m uvicorn interfaces.server.main:app --host %HOST% --port %PORT% --log-level %LOG_LEVEL% --reload > "%BACKEND_LOG%" 2>&1

REM Wait for server to start
echo [i] Waiting for backend server to start...
set WAIT_COUNT=0
:wait_for_backend
timeout /t 2 /nobreak >nul
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:8000/health' -TimeoutSec 3 -ErrorAction Stop; if ($response.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 0 goto :backend_ready
set /a WAIT_COUNT+=1
if %WAIT_COUNT% geq 15 (
    echo [✗] Backend server failed to start within 30 seconds
    echo [⚠] Check logs: %BACKEND_LOG%
    pause
    exit /b 1
)
goto :wait_for_backend

:backend_ready
echo [✓] Backend server started

REM Test AI configuration
timeout /t 2 /nobreak >nul
echo [→] Testing AI configuration...
powershell -Command "try { $config = Invoke-RestMethod -Uri 'http://localhost:8000/api/ai/config/status' -TimeoutSec 5; if ($config.configured) { Write-Host '[✓] AI is configured and ready'; $providers = ($config.providers.Keys -join ', '); Write-Host '[i] Available providers: ' $providers } else { Write-Host '[⚠] AI is not configured'; Write-Host '[i] Run: python scripts/setup_ai_provider.py'; Write-Host '[i] Or set OPENAI_API_KEY or install Ollama' } } catch { Write-Host '[✗] Failed to test AI configuration' }"

REM Step 5: Start desktop app (unless --no-ui)
if "%NO_UI%"=="0" (
    echo.
    echo [→] Starting desktop app...
    
    if not exist "src\interfaces\desktop" (
        echo [✗] Desktop app directory not found
        goto :skip_desktop
    )
    
    REM Check Node.js
    call :command_exists node
    if "%COMMAND_EXISTS%"=="0" (
        echo [✗] Node.js is required for desktop app
        goto :skip_desktop
    )
    
    REM Check npm
    call :command_exists npm
    if "%COMMAND_EXISTS%"=="0" (
        echo [✗] npm is required for desktop app
        goto :skip_desktop
    )
    
    cd /d "src\interfaces\desktop"
    
    REM Install dependencies if needed
    if not exist "node_modules" (
        echo [⚠] Installing Node.js dependencies...
        call npm install
        if errorlevel 1 (
            echo [✗] Failed to install Node.js dependencies
            cd /d "%PROJECT_ROOT%"
            goto :skip_desktop
        )
        echo [✓] Node.js dependencies installed
    )
    
    set DESKTOP_LOG=%PROJECT_ROOT%\logs\desktop_%DATE:~-4,4%%DATE:~-10,2%%DATE:~-7,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%.log
    
    if "%DEBUG_MODE%"=="1" (
        echo [i] Starting in debug mode...
        start "AI_SUPPORT Desktop" /B npm run dev > "%DESKTOP_LOG%" 2>&1
    ) else (
        echo [i] Starting in production mode...
        if not exist "dist" (
            echo [⚠] Building desktop app...
            call npm run build
            if errorlevel 1 (
                echo [✗] Failed to build desktop app
                cd /d "%PROJECT_ROOT%"
                goto :skip_desktop
            )
        )
        start "AI_SUPPORT Desktop" /B npm start > "%DESKTOP_LOG%" 2>&1
    )
    
    cd /d "%PROJECT_ROOT%"
    echo [✓] Desktop app started
    echo [i] Logs: %DESKTOP_LOG%
    
    :skip_desktop
)

REM Step 6: Show monitoring dashboard
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                    SYSTEM MONITORING                       ║
echo ╠══════════════════════════════════════════════════════════════╣

REM Show backend status
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:8000/health' -TimeoutSec 2; Write-Host ' Backend:   ● Running http://localhost:8000' } catch { Write-Host ' Backend:   ● Stopped' }"

REM Show AI configuration status
powershell -Command "try { $config = Invoke-RestMethod -Uri 'http://localhost:8000/api/ai/config/status' -TimeoutSec 2; if ($config.configured) { Write-Host ' AI Config: ● Configured'; $providers = ($config.providers.Keys | Where-Object { $config.providers.$_.available }) -join ', '; Write-Host '           ($providers)' } else { Write-Host ' AI Config: ● Not Configured (None)' } } catch { Write-Host ' AI Config: ● Unavailable' }"

echo ╠══════════════════════════════════════════════════════════════╣
echo ║ Useful URLs:                                                ║
echo ║   • Backend API:    http://localhost:8000                   ║
echo ║   • AI Config:      http://localhost:8000/api/ai/config/status ║
echo ║   • AI Test:        http://localhost:8000/api/ai/test       ║
echo ║   • Health:         http://localhost:8000/health            ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║ Commands:                                                   ║
echo ║   • Test AI:        curl http://localhost:8000/api/ai/test  ║
echo ║   • Setup AI:       python scripts/setup_ai_provider.py     ║
echo ║   • View logs:      type logs\backend_*.log                 ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

echo [✓] AI_SUPPORT is running! Press Ctrl+C to stop all components.
echo.

REM Keep script running
:keep_alive
timeout /t 1 /nobreak >nul
goto :keep_alive

:show_help
echo Usage: run_all.bat [options]
echo.
echo Options:
echo   --setup      Run AI provider setup first
echo   --debug      Enable debug logging
echo   --no-ui      Don't start desktop app (backend only)
echo   --help       Show this help message
echo.
echo Examples:
echo   run_all.bat                 Start everything with defaults
echo   run_all.bat --setup         Setup AI first, then start everything
echo   run_all.bat --no-ui         Start backend only (no desktop app)
echo   run_all.bat --debug         Start with debug logging enabled
echo.
exit /b 0