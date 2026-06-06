# AI_SUPPORT Makefile
# Simple commands for development and deployment

.PHONY: help all backend desktop setup test clean

# Default target
help:
	@echo "AI_SUPPORT - Embedded Engineering Assistant"
	@echo ""
	@echo "Available commands:"
	@echo "  make all              Start everything (backend + desktop)"
	@echo "  make backend          Start backend server only"
	@echo "  make desktop          Start desktop app only"
	@echo "  make setup            Setup AI providers"
	@echo "  make test             Run tests"
	@echo "  make clean            Clean up temporary files"
	@echo "  make docs             Generate documentation"
	@echo ""
	@echo "Platform-specific scripts:"
	@echo "  ./run_all.ps1         PowerShell script for Windows"
	@echo "  ./run_all.bat         Batch script for Windows"
	@echo "  ./run_all.sh          Shell script for Unix/Linux/macOS"
	@echo ""
	@echo "Examples:"
	@echo "  make all              # Start everything"
	@echo "  make backend          # Start backend API"
	@echo "  python scripts/setup_ai_provider.py  # Setup AI"

# Start everything
all:
	@echo "Starting AI_SUPPORT..."
	@if exist "run_all.bat" ( \
		.\run_all.bat \
	) else if exist "run_all.ps1" ( \
		powershell -ExecutionPolicy Bypass -File .\run_all.ps1 \
	) else if exist "run_all.sh" ( \
		chmod +x ./run_all.sh && ./run_all.sh \
	) else ( \
		echo "No run script found for your platform" && \
		echo "Please run manually: python src/interfaces/server/main.py" \
	)

# Start backend server
backend:
	@echo "Starting backend server..."
	@cd src && python -m uvicorn interfaces.server.main:app --host 0.0.0.0 --port 8000 --reload

# Start desktop app
desktop:
	@echo "Starting desktop app..."
	@cd src/interfaces/desktop && npm start

# Setup AI providers
setup:
	@echo "Setting up AI providers..."
	@python scripts/setup_ai_provider.py

# Run tests
test:
	@echo "Running tests..."
	@python -m pytest tests/ -v

# Run specific test
test-unit:
	@echo "Running unit tests..."
	@python -m pytest tests/unit/ -v

test-integration:
	@echo "Running integration tests..."
	@python -m pytest tests/integration/ -v

# Clean up
clean:
	@echo "Cleaning up..."
	@rm -rf __pycache__
	@rm -rf *.pyc
	@rm -rf .pytest_cache
	@rm -rf logs/
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete
	@echo "Cleanup complete"

# Generate documentation
docs:
	@echo "Generating documentation..."
	@mkdir -p docs/generated
	@python -c "import json; import sys; sys.path.append('src'); from core.agent.real_agent import RealAgent; agent = RealAgent(); print(json.dumps(agent.get_configuration_status(), indent=2))" > docs/generated/ai_status.json
	@echo "Documentation generated in docs/generated/"

# Install dependencies
install-deps:
	@echo "Installing Python dependencies..."
	@pip install -r requirements.txt || pip install fastapi uvicorn[standard] websockets pydantic aiohttp openai anthropic pytest
	@echo "Installing Node.js dependencies..."
	@cd src/interfaces/desktop && npm install

# Check system status
status:
	@echo "=== AI_SUPPORT System Status ==="
	@echo ""
	@echo "Backend:"
	@curl -s http://localhost:8000/health 2>/dev/null || echo "  Not running"
	@echo ""
	@echo "AI Configuration:"
	@curl -s http://localhost:8000/api/ai/config/status 2>/dev/null || echo "  Backend not running"
	@echo ""
	@echo "Processes:"
	@ps aux | grep -E "(uvicorn|node|npm|python.*main)" | grep -v grep || echo "  No processes found"

# Quick start
quickstart:
	@echo "=== AI_SUPPORT Quick Start ==="
	@echo ""
	@echo "1. Setup AI providers:"
	@echo "   make setup"
	@echo ""
	@echo "2. Start backend server:"
	@echo "   make backend"
	@echo ""
	@echo "3. In another terminal, start desktop app:"
	@echo "   make desktop"
	@echo ""
	@echo "4. Or start everything at once:"
	@echo "   make all"
	@echo ""
	@echo "5. Test AI connection:"
	@echo "   curl http://localhost:8000/api/ai/test"
	@echo ""
	@echo "Documentation: docs/AI_CONFIGURATION_GUIDE.md"