#!/usr/bin/env pwsh
<#
AI_SUPPORT - Run Everything Script

This script starts all components of AI_SUPPORT:
1. Backend FastAPI server (Python)
2. Desktop Electron app
3. AI provider setup check
4. Health monitoring

Usage: .\run_all.ps1 [options]

Options:
  --setup      Run AI provider setup first
  --debug      Enable debug logging
  --no-ui      Don't start desktop app (backend only)
  --help       Show this help message
#>

param(
    [switch]$Setup,
    [switch]$Debug,
    [switch]$NoUI,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# Colors for output
$Green = "`e[32m"
$Yellow = "`e[33m"
$Red = "`e[31m"
$Blue = "`e[34m"
$Magenta = "`e[35m"
$Cyan = "`e[36m"
$Reset = "`e[0m"

# Banner
function Show-Banner {
    Write-Host ""
    Write-Host "$Blue╔══════════════════════════════════════════════════════════════╗$Reset"
    Write-Host "$Blue║$Cyan              AI_SUPPORT - Embedded Engineering Assistant         $Blue║$Reset"
    Write-Host "$Blue║$Green                    Starting All Components...                     $Blue║$Reset"
    Write-Host "$Blue╚══════════════════════════════════════════════════════════════╝$Reset"
    Write-Host ""
}

# Helper functions
function Write-Status {
    param($Message, $Type = "info")
    
    switch ($Type) {
        "info"    { Write-Host "[$Blue•$Reset] $Message" }
        "success" { Write-Host "[$Green✓$Reset] $Message" }
        "warning" { Write-Host "[$Yellow⚠$Reset] $Message" }
        "error"   { Write-Host "[$Red✗$Reset] $Message" }
        "step"    { Write-Host "[$Magenta→$Reset] $Message" }
    }
}

function Check-Command {
    param($Command, $Name)
    
    try {
        $null = Get-Command $Command -ErrorAction Stop
        Write-Status "$Name is available" "success"
        return $true
    } catch {
        Write-Status "$Name is not available ($Command not found)" "error"
        return $false
    }
}

function Start-BackendServer {
    Write-Status "Starting backend server..." "step"
    
    # Change to project root
    $ProjectRoot = $PSScriptRoot
    Set-Location $ProjectRoot
    
    # Check Python
    if (-not (Check-Command "python" "Python 3")) {
        Write-Status "Trying python3..." "warning"
        if (-not (Check-Command "python3" "Python 3")) {
            Write-Status "Python is required. Please install Python 3.8+ from python.org" "error"
            exit 1
        }
        $PythonCmd = "python3"
    } else {
        $PythonCmd = "python"
    }
    
    # Check Python version
    $PythonVersion = & $PythonCmd --version 2>&1
    Write-Status "Python version: $PythonVersion" "info"
    
    # Check dependencies
    Write-Status "Checking Python dependencies..." "step"
    
    # Check FastAPI/Uvicorn
    try {
        $null = & $PythonCmd -c "import fastapi, uvicorn, asyncio; print('FastAPI/Uvicorn available')"
        Write-Status "FastAPI/Uvicorn dependencies OK" "success"
    } catch {
        Write-Status "Installing Python dependencies..." "warning"
        & $PythonCmd -m pip install fastapi uvicorn[standard] websockets pydantic
        if ($LASTEXITCODE -ne 0) {
            Write-Status "Failed to install Python dependencies" "error"
            exit 1
        }
        Write-Status "Python dependencies installed" "success"
    }
    
    # Check AI provider dependencies
    try {
        $null = & $PythonCmd -c "import aiohttp; print('AI dependencies available')"
        Write-Status "AI dependencies OK" "success"
    } catch {
        Write-Status "Installing AI dependencies..." "warning"
        & $PythonCmd -m pip install aiohttp openai anthropic
        if ($LASTEXITCODE -ne 0) {
            Write-Status "Failed to install AI dependencies" "error"
            exit 1
        }
        Write-Status "AI dependencies installed" "success"
    }
    
    # Create logs directory
    $LogDir = "$ProjectRoot\logs"
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }
    
    # Start backend server
    $BackendLog = "$LogDir\backend_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
    Write-Status "Starting backend on http://localhost:8000" "step"
    Write-Status "Logs: $BackendLog" "info"
    
    # Set environment variables
    $EnvVars = @{
        "HOST" = "0.0.0.0"
        "PORT" = "8000"
        "LOG_LEVEL" = if ($Debug) { "DEBUG" } else { "INFO" }
        "PYTHONPATH" = "$ProjectRoot\src"
    }
    
    # Start server in background
    $BackendProcess = Start-Process -FilePath $PythonCmd `
        -ArgumentList @(
            "-m", "uvicorn",
            "interfaces.server.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--log-level", if ($Debug) { "debug" } else { "info" },
            "--reload"
        ) `
        -WorkingDirectory "$ProjectRoot\src" `
        -NoNewWindow:$Debug `
        -PassThru `
        -RedirectStandardOutput $BackendLog `
        -RedirectStandardError $BackendLog
    
    # Save process ID
    $BackendProcessId = $BackendProcess.Id
    $BackendProcess | Add-Member -NotePropertyName "LogFile" -NotePropertyValue $BackendLog
    
    # Wait for server to start
    Write-Status "Waiting for backend server to start..." "info"
    $MaxWait = 30
    $WaitInterval = 2
    $Started = $false
    
    for ($i = 0; $i -lt $MaxWait; $i += $WaitInterval) {
        try {
            $Response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -ErrorAction Stop
            if ($Response.StatusCode -eq 200) {
                $Started = $true
                break
            }
        } catch {
            Start-Sleep -Seconds $WaitInterval
        }
    }
    
    if ($Started) {
        Write-Status "Backend server started (PID: $BackendProcessId)" "success"
        
        # Test AI configuration
        Start-Sleep -Seconds 2
        Test-AIConfiguration
        
        return @{
            Process = $BackendProcess
            PID = $BackendProcessId
            LogFile = $BackendLog
            URL = "http://localhost:8000"
        }
    } else {
        Write-Status "Backend server failed to start within $MaxWait seconds" "error"
        Write-Status "Check logs: $BackendLog" "warning"
        Stop-Process -Id $BackendProcessId -Force -ErrorAction SilentlyContinue
        exit 1
    }
}

function Test-AIConfiguration {
    Write-Status "Testing AI configuration..." "step"
    
    try {
        $Config = Invoke-RestMethod -Uri "http://localhost:8000/api/ai/config/status" -TimeoutSec 10
        if ($Config.configured) {
            Write-Status "AI is configured and ready" "success"
            $Providers = $Config.providers.Keys -join ", "
            Write-Status "Available providers: $Providers" "info"
        } else {
            Write-Status "AI is not configured" "warning"
            Write-Status "Run: python scripts/setup_ai_provider.py" "info"
            Write-Status "Or set OPENAI_API_KEY or install Ollama" "info"
        }
    } catch {
        Write-Status "Failed to test AI configuration: $_" "error"
    }
}

function Start-DesktopApp {
    Write-Status "Starting desktop app..." "step"
    
    $ProjectRoot = $PSScriptRoot
    $DesktopDir = "$ProjectRoot\src\interfaces\desktop"
    
    if (-not (Test-Path $DesktopDir)) {
        Write-Status "Desktop app directory not found: $DesktopDir" "error"
        return $null
    }
    
    # Check Node.js and npm
    if (-not (Check-Command "node" "Node.js")) {
        Write-Status "Node.js is required for desktop app" "error"
        return $null
    }
    
    if (-not (Check-Command "npm" "npm")) {
        Write-Status "npm is required for desktop app" "error"
        return $null
    }
    
    # Check Node version
    $NodeVersion = node --version
    Write-Status "Node.js version: $NodeVersion" "info"
    
    # Install dependencies if needed
    $PackageLock = "$DesktopDir\package-lock.json"
    $NodeModules = "$DesktopDir\node_modules"
    
    if (-not (Test-Path $NodeModules) -or -not (Test-Path $PackageLock)) {
        Write-Status "Installing Node.js dependencies..." "warning"
        Set-Location $DesktopDir
        npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Status "Failed to install Node.js dependencies" "error"
            return $null
        }
        Write-Status "Node.js dependencies installed" "success"
    }
    
    # Start desktop app
    Write-Status "Starting Electron app..." "step"
    $DesktopLog = "$ProjectRoot\logs\desktop_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
    
    Set-Location $DesktopDir
    
    if ($Debug) {
        # Start in debug mode
        $DesktopProcess = Start-Process -FilePath "npm" `
            -ArgumentList "run", "dev" `
            -NoNewWindow `
            -PassThru `
            -RedirectStandardOutput $DesktopLog `
            -RedirectStandardError $DesktopLog
    } else {
        # Start in production mode
        # First build if needed
        $DistDir = "$DesktopDir\dist"
        if (-not (Test-Path $DistDir)) {
            Write-Status "Building desktop app..." "info"
            npm run build
            if ($LASTEXITCODE -ne 0) {
                Write-Status "Failed to build desktop app" "error"
                return $null
            }
        }
        
        $DesktopProcess = Start-Process -FilePath "npm" `
            -ArgumentList "start" `
            -NoNewWindow:$false `
            -PassThru `
            -RedirectStandardOutput $DesktopLog `
            -RedirectStandardError $DesktopLog
    }
    
    $DesktopProcessId = $DesktopProcess.Id
    Write-Status "Desktop app started (PID: $DesktopProcessId)" "success"
    Write-Status "Logs: $DesktopLog" "info"
    
    return @{
        Process = $DesktopProcess
        PID = $DesktopProcessId
        LogFile = $DesktopLog
    }
}

function Setup-AIProviders {
    Write-Status "Running AI provider setup..." "step"
    
    $ProjectRoot = $PSScriptRoot
    $SetupScript = "$ProjectRoot\scripts\setup_ai_provider.py"
    
    if (-not (Test-Path $SetupScript)) {
        Write-Status "Setup script not found: $SetupScript" "error"
        return $false
    }
    
    Write-Status "Running AI setup wizard..." "info"
    Set-Location $ProjectRoot
    
    if (Check-Command "python" "Python")) {
        python $SetupScript
    } elseif (Check-Command "python3" "Python 3")) {
        python3 $SetupScript
    } else {
        Write-Status "Python not found for setup script" "error"
        return $false
    }
    
    return $true
}

function Show-Monitoring {
    Write-Host ""
    Write-Host "$Cyan╔══════════════════════════════════════════════════════════════╗$Reset"
    Write-Host "$Cyan║$Yellow                    SYSTEM MONITORING                       $Cyan║$Reset"
    Write-Host "$Cyan╠══════════════════════════════════════════════════════════════╣$Reset"
    
    # Show backend status
    try {
        $Health = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 2
        Write-Host "$Cyan║$Reset Backend:   $Green● Running$Reset http://localhost:8000" -NoNewline
        Write-Host "$Cyan║$Reset"
    } catch {
        Write-Host "$Cyan║$Reset Backend:   $Red● Stopped$Reset" -NoNewline
        Write-Host "$Cyan║$Reset"
    }
    
    # Show AI configuration status
    try {
        $AIConfig = Invoke-RestMethod -Uri "http://localhost:8000/api/ai/config/status" -TimeoutSec 2
        $Status = if ($AIConfig.configured) { "$GreenConfigured$Reset" } else { "$YellowNot Configured$Reset" }
        $Providers = if ($AIConfig.configured) { 
            ($AIConfig.providers.Keys | Where-Object { $AIConfig.providers.$_.available }) -join ", "
        } else { "None" }
        Write-Host "$Cyan║$Reset AI Config: $Status ($Providers)" -NoNewline
        Write-Host "$Cyan║$Reset"
    } catch {
        Write-Host "$Cyan║$Reset AI Config: $RedUnavailable$Reset" -NoNewline
        Write-Host "$Cyan║$Reset"
    }
    
    Write-Host "$Cyan╠══════════════════════════════════════════════════════════════╣$Reset"
    Write-Host "$Cyan║$Reset Useful URLs:" -NoNewline
    Write-Host "$Cyan║$Reset"
    Write-Host "$Cyan║$Reset   • Backend API:    http://localhost:8000" -NoNewline
    Write-Host "$Cyan║$Reset"
    Write-Host "$Cyan║$Reset   • AI Config:      http://localhost:8000/api/ai/config/status" -NoNewline
    Write-Host "$Cyan║$Reset"
    Write-Host "$Cyan║$Reset   • AI Test:        http://localhost:8000/api/ai/test" -NoNewline
    Write-Host "$Cyan║$Reset"
    Write-Host "$Cyan║$Reset   • Health:         http://localhost:8000/health" -NoNewline
    Write-Host "$Cyan║$Reset"
    
    Write-Host "$Cyan╠══════════════════════════════════════════════════════════════╣$Reset"
    Write-Host "$Cyan║$Reset Commands:" -NoNewline
    Write-Host "$Cyan║$Reset"
    Write-Host "$Cyan║$Reset   • Test AI:        curl http://localhost:8000/api/ai/test" -NoNewline
    Write-Host "$Cyan║$Reset"
    Write-Host "$Cyan║$Reset   • Setup AI:       python scripts/setup_ai_provider.py" -NoNewline
    Write-Host "$Cyan║$Reset"
    Write-Host "$Cyan║$Reset   • View logs:      tail -f logs/backend_*.log" -NoNewline
    Write-Host "$Cyan║$Reset"
    
    Write-Host "$Cyan╚════════════════════════════════════════��═════════════════════╝$Reset"
    Write-Host ""
}

function Cleanup {
    param($Processes)
    
    Write-Host ""
    Write-Status "Shutting down..." "warning"
    
    foreach ($proc in $Processes) {
        if ($proc -and $proc.Process -and (-not $proc.Process.HasExited)) {
            $Name = if ($proc.ContainsKey("Name")) { $proc.Name } else { "Process $($proc.PID)" }
            Write-Status "Stopping $Name (PID: $($proc.PID))..." "info"
            Stop-Process -Id $proc.PID -Force -ErrorAction SilentlyContinue
        }
    }
    
    Write-Status "All components stopped" "success"
}

# Main script
function Main {
    if ($Help) {
        Get-Help $PSCommandPath
        return
    }
    
    Show-Banner
    
    # Store processes for cleanup
    $Processes = @()
    
    # Register cleanup on Ctrl+C
    $OriginalHandler = [Console]::TreatControlCAsInput
    [Console]::TreatControlCAsInput = $true
    
    try {
        # Step 1: Setup AI providers if requested
        if ($Setup) {
            if (-not (Setup-AIProviders)) {
                Write-Status "AI setup failed or was cancelled" "warning"
            }
        }
        
        # Step 2: Start backend server
        $Backend = Start-BackendServer
        if (-not $Backend) {
            exit 1
        }
        $Backend["Name"] = "Backend Server"
        $Processes += $Backend
        
        # Step 3: Start desktop app (unless --no-ui)
        if (-not $NoUI) {
            $Desktop = Start-DesktopApp
            if ($Desktop) {
                $Desktop["Name"] = "Desktop App"
                $Processes += $Desktop
            } else {
                Write-Status "Desktop app failed to start, continuing with backend only" "warning"
            }
        }
        
        # Step 4: Show monitoring dashboard
        Show-Monitoring
        
        Write-Host ""
        Write-Status "AI_SUPPORT is running! Press Ctrl+C to stop all components." "success"
        Write-Host ""
        
        # Keep script running
        while ($true) {
            if ([Console]::KeyAvailable) {
                $Key = [Console]::ReadKey($true)
                if (($Key.Modifiers -band [ConsoleModifiers]::Control) -and ($Key.Key -eq "C")) {
                    break
                }
            }
            Start-Sleep -Seconds 1
        }
        
    } finally {
        # Restore Ctrl+C handler
        [Console]::TreatControlCAsInput = $OriginalHandler
        
        # Cleanup
        Cleanup $Processes
    }
}

# Run main function
Main