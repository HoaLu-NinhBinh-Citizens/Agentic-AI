@echo off
REM AI_SUPPORT - Simple Start Script for Windows
REM This script starts the backend server

echo.
echo ========================================================
echo    AI_SUPPORT - Embedded Engineering Assistant
echo ========================================================
echo.

REM Check Python
where python.exe >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found!
    echo.
    echo Please install Python 3.8+ from:
    echo   https://www.python.org/downloads/
    echo.
    echo During installation, CHECK "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

REM Check Python version
python --version
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to run Python
    pause
    exit /b 1
)

REM Install dependencies if needed
echo.
echo Checking Python dependencies...
python -c "import fastapi, uvicorn, asyncio" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Installing Python dependencies...
    python -m pip install fastapi uvicorn[standard] websockets pydantic aiohttp openai anthropic
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Failed to install Python dependencies
        pause
        exit /b 1
    )
    echo Dependencies installed successfully.
)

REM Check AI agent file exists
if not exist "src\core\agent\real_agent.py" (
    echo ERROR: RealAgent not found at src\core\agent\real_agent.py
    pause
    exit /b 1
)

REM Create logs directory
if not exist "logs" mkdir logs

echo.
echo Starting backend server on http://localhost:8000
echo Press Ctrl+C to stop the server
echo.

REM Start the server
cd src
python -m uvicorn interfaces.server.main:app --host 0.0.0.0 --port 8000 --reload
cd ..

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Server failed to start
    echo Check if port 8000 is already in use:
    echo   netstat -ano | findstr :8000
    echo.
    pause
)