SHELL = C:/WINDOWS/system32/cmd.exe

.PHONY: all backend setup test clean status

all: backend

backend:
	@set "PYTHONPATH=%CD%;%CD%\src" && cd src && python -m uvicorn interfaces.server.main:app --host 0.0.0.0 --port 8000 --reload

setup:
	@python scripts\setup_ai_provider.py

test:
	@set "PYTHONPATH=%CD%;%CD%\src" && python -m pytest tests\ -v

clean:
	-@del /s /q *.pyc 2>nul
	@echo Done

status:
	-@curl --max-time 3 -sf http://localhost:8000/health >nul 2>&1 && (echo Backend: Running) || (echo Backend: Stopped)
	-@curl --max-time 3 -sf http://localhost:8000/api/ai/config/status >nul 2>&1 && (echo AI: Available) || (echo AI: Unavailable)
