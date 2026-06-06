# AI_SUPPORT Makefile
# Cross-platform commands for development

SHELL := powershell.exe
.SHELLFLAGS := -NoProfile -Command

.PHONY: help all backend setup test clean status

help:
	@Write-Host "AI_SUPPORT - Embedded Engineering Assistant" -ForegroundColor Cyan
	@Write-Host ""
	@Write-Host "Commands:"
	@Write-Host "  make all       Start backend server"
	@Write-Host "  make backend   Start backend server"
	@Write-Host "  make setup     Setup AI providers"
	@Write-Host "  make test      Run tests"
	@Write-Host "  make clean     Clean temp files"
	@Write-Host "  make status    Check system status"
	@Write-Host ""
	@Write-Host "Or run directly:"
	@Write-Host "  .\start_system.ps1"

all: backend

backend:
	@$$env:PYTHONPATH = "$(CURDIR);$(CURDIR)\src"; Set-Location "$(CURDIR)\src"; python -m uvicorn interfaces.server.main:app --host 0.0.0.0 --port 8000 --reload

setup:
	@python scripts\setup_ai_provider.py

test:
	@$$env:PYTHONPATH = "$(CURDIR);$(CURDIR)\src"; python -m pytest tests\ -v

clean:
	@Remove-Item -Recurse -Force -ErrorAction SilentlyContinue __pycache__, .pytest_cache, logs
	@Get-ChildItem -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
	@Write-Host "Cleanup complete" -ForegroundColor Green

status:
	@try { $$r = Invoke-RestMethod http://localhost:8000/health -TimeoutSec 3; Write-Host "Backend: Running" -ForegroundColor Green } catch { Write-Host "Backend: Stopped" -ForegroundColor Red }
	@try { $$c = Invoke-RestMethod http://localhost:8000/api/ai/config/status -TimeoutSec 3; Write-Host "AI: $$($c.active_provider)" -ForegroundColor Green } catch { Write-Host "AI: Unavailable" -ForegroundColor Yellow }
