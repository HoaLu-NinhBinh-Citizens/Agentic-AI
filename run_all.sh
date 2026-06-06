#!/bin/bash
# AI_SUPPORT - Run Everything Shell Script for Unix/Linux/macOS
# This script starts all components of AI_SUPPORT

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Banner
show_banner() {
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${CYAN}              AI_SUPPORT - Embedded Engineering Assistant         ${BLUE}║${NC}"
    echo -e "${BLUE}║${GREEN}                    Starting All Components...                     ${BLUE}║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Helper functions
log_info() {
    echo -e "[${BLUE}•${NC}] $1"
}

log_success() {
    echo -e "[${GREEN}✓${NC}] $1"
}

log_warning() {
    echo -e "[${YELLOW}⚠${NC}] $1"
}

log_error() {
    echo -e "[${RED}✗${NC}] $1"
}

log_step() {
    echo -e "[${MAGENTA}→${NC}] $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Cleanup function
cleanup() {
    log_warning "Shutting down..."
    
    # Kill background processes
    if [ -n "$BACKEND_PID" ]; then
        log_info "Stopping backend server (PID: $BACKEND_PID)..."
        kill $BACKEND_PID 2>/dev/null || true
    fi
    
    if [ -n "$DESKTOP_PID" ]; then
        log_info "Stopping desktop app (PID: $DESKTOP_PID)..."
        kill $DESKTOP_PID 2>/dev/null || true
    fi
    
    log_success "All components stopped"
    exit 0
}

# Trap Ctrl+C
trap cleanup INT TERM

# Parse arguments
SETUP_MODE=0
DEBUG_MODE=0
NO_UI=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --setup)
            SETUP_MODE=1
            shift
            ;;
        --debug)
            DEBUG_MODE=1
            shift
            ;;
        --no-ui)
            NO_UI=1
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

show_help() {
    echo "Usage: ./run_all.sh [options]"
    echo ""
    echo "Options:"
    echo "  --setup      Run AI provider setup first"
    echo "  --debug      Enable debug logging"
    echo "  --no-ui      Don't start desktop app (backend only)"
    echo "  --help       Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./run_all.sh                 Start everything with defaults"
    echo "  ./run_all.sh --setup         Setup AI first, then start everything"
    echo "  ./run_all.sh --no-ui         Start backend only (no desktop app)"
    echo "  ./run_all.sh --debug         Start with debug logging enabled"
    echo ""
}

# Start backend server
start_backend() {
    log_step "Starting backend server..."
    
    PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$PROJECT_ROOT"
    
    # Check Python
    if command_exists python3; then
        PYTHON_CMD="python3"
    elif command_exists python; then
        PYTHON_CMD="python"
    else
        log_error "Python is required. Please install Python 3.8+"
        exit 1
    fi
    
    # Check Python version
    log_info "Python version: $($PYTHON_CMD --version)"
    
    # Check dependencies
    log_step "Checking Python dependencies..."
    
    if ! $PYTHON_CMD -c "import fastapi, uvicorn, asyncio" >/dev/null 2>&1; then
        log_warning "Installing Python dependencies..."
        $PYTHON_CMD -m pip install fastapi uvicorn[standard] websockets pydantic
        if [ $? -ne 0 ]; then
            log_error "Failed to install Python dependencies"
            exit 1
        fi
        log_success "Python dependencies installed"
    else
        log_success "FastAPI/Uvicorn dependencies OK"
    fi
    
    # Check AI dependencies
    if ! $PYTHON_CMD -c "import aiohttp" >/dev/null 2>&1; then
        log_warning "Installing AI dependencies..."
        $PYTHON_CMD -m pip install aiohttp openai anthropic
        if [ $? -ne 0 ]; then
            log_error "Failed to install AI dependencies"
            exit 1
        fi
        log_success "AI dependencies installed"
    else
        log_success "AI dependencies OK"
    fi
    
    # Create logs directory
    mkdir -p logs
    
    # Start backend server
    BACKEND_LOG="logs/backend_$(date +'%Y%m%d_%H%M%S').log"
    log_step "Starting backend on http://localhost:8000"
    log_info "Logs: $BACKEND_LOG"
    
    # Set environment variables
    export HOST="0.0.0.0"
    export PORT="8000"
    if [ $DEBUG_MODE -eq 1 ]; then
        export LOG_LEVEL="DEBUG"
    else
        export LOG_LEVEL="INFO"
    fi
    export PYTHONPATH="$PROJECT_ROOT/src"
    
    # Start server in background
    cd src
    $PYTHON_CMD -m uvicorn interfaces.server.main:app \
        --host "$HOST" \
        --port "$PORT" \
        --log-level "$LOG_LEVEL" \
        --reload \
        > "../$BACKEND_LOG" 2>&1 &
    
    BACKEND_PID=$!
    cd ..
    
    # Wait for server to start
    log_info "Waiting for backend server to start..."
    local max_wait=30
    local wait_interval=2
    local started=0
    
    for ((i=0; i<max_wait; i+=wait_interval)); do
        if curl -s -f http://localhost:8000/health >/dev/null 2>&1; then
            started=1
            break
        fi
        sleep $wait_interval
    done
    
    if [ $started -eq 1 ]; then
        log_success "Backend server started (PID: $BACKEND_PID)"
        
        # Test AI configuration
        sleep 2
        test_ai_configuration
        
        return 0
    else
        log_error "Backend server failed to start within $max_wait seconds"
        log_warning "Check logs: $BACKEND_LOG"
        kill $BACKEND_PID 2>/dev/null || true
        exit 1
    fi
}

# Test AI configuration
test_ai_configuration() {
    log_step "Testing AI configuration..."
    
    if curl -s -f http://localhost:8000/api/ai/config/status >/dev/null 2>&1; then
        local config=$(curl -s http://localhost:8000/api/ai/config/status)
        local configured=$(echo "$config" | grep -o '"configured":true' || true)
        
        if [ -n "$configured" ]; then
            log_success "AI is configured and ready"
            local providers=$(echo "$config" | grep -o '"providers":[^}]*}' | head -1)
            log_info "Available providers: $providers"
        else
            log_warning "AI is not configured"
            log_info "Run: python scripts/setup_ai_provider.py"
            log_info "Or set OPENAI_API_KEY or install Ollama"
        fi
    else
        log_error "Failed to test AI configuration"
    fi
}

# Setup AI providers
setup_ai_providers() {
    log_step "Running AI provider setup..."
    
    if [ -f "scripts/setup_ai_provider.py" ]; then
        log_info "Running AI setup wizard..."
        python scripts/setup_ai_provider.py
        if [ $? -eq 0 ]; then
            return 0
        else
            log_warning "AI setup failed or was cancelled"
            return 1
        fi
    else
        log_error "Setup script not found: scripts/setup_ai_provider.py"
        return 1
    fi
}

# Start desktop app
start_desktop_app() {
    log_step "Starting desktop app..."
    
    DESKTOP_DIR="src/interfaces/desktop"
    
    if [ ! -d "$DESKTOP_DIR" ]; then
        log_error "Desktop app directory not found: $DESKTOP_DIR"
        return 1
    fi
    
    # Check Node.js and npm
    if ! command_exists node; then
        log_error "Node.js is required for desktop app"
        return 1
    fi
    
    if ! command_exists npm; then
        log_error "npm is required for desktop app"
        return 1
    fi
    
    # Check Node version
    log_info "Node.js version: $(node --version)"
    
    # Install dependencies if needed
    cd "$DESKTOP_DIR"
    
    if [ ! -d "node_modules" ] || [ ! -f "package-lock.json" ]; then
        log_warning "Installing Node.js dependencies..."
        npm install
        if [ $? -ne 0 ]; then
            log_error "Failed to install Node.js dependencies"
            cd ../..
            return 1
        fi
        log_success "Node.js dependencies installed"
    fi
    
    # Start desktop app
    DESKTOP_LOG="../../logs/desktop_$(date +'%Y%m%d_%H%M%S').log"
    
    if [ $DEBUG_MODE -eq 1 ]; then
        log_info "Starting in debug mode..."
        npm run dev > "$DESKTOP_LOG" 2>&1 &
    else
        log_info "Starting in production mode..."
        # First build if needed
        if [ ! -d "dist" ]; then
            log_warning "Building desktop app..."
            npm run build
            if [ $? -ne 0 ]; then
                log_error "Failed to build desktop app"
                cd ../..
                return 1
            fi
        fi
        npm start > "$DESKTOP_LOG" 2>&1 &
    fi
    
    DESKTOP_PID=$!
    cd ../..
    
    log_success "Desktop app started (PID: $DESKTOP_PID)"
    log_info "Logs: $DESKTOP_LOG"
    return 0
}

# Show monitoring dashboard
show_monitoring() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${YELLOW}                    SYSTEM MONITORING                       ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"
    
    # Show backend status
    if curl -s -f http://localhost:8000/health >/dev/null 2>&1; then
        echo -e "${CYAN}║${NC} Backend:   ${GREEN}● Running${NC} http://localhost:8000${CYAN}║${NC}"
    else
        echo -e "${CYAN}║${NC} Backend:   ${RED}● Stopped${NC}${CYAN}║${NC}"
    fi
    
    # Show AI configuration status
    if curl -s -f http://localhost:8000/api/ai/config/status >/dev/null 2>&1; then
        local config=$(curl -s http://localhost:8000/api/ai/config/status)
        if echo "$config" | grep -q '"configured":true'; then
            echo -e "${CYAN}║${NC} AI Config: ${GREEN}● Configured${NC}${CYAN}║${NC}"
            local providers=$(echo "$config" | grep -o '"providers":[^}]*}' | head -1)
            echo -e "${CYAN}║${NC}           ($providers)${CYAN}║${NC}"
        else
            echo -e "${CYAN}║${NC} AI Config: ${YELLOW}● Not Configured${NC} (None)${CYAN}║${NC}"
        fi
    else
        echo -e "${CYAN}║${NC} AI Config: ${RED}● Unavailable${NC}${CYAN}║${NC}"
    fi
    
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC} Useful URLs:${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   • Backend API:    http://localhost:8000${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   • AI Config:      http://localhost:8000/api/ai/config/status${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   • AI Test:        http://localhost:8000/api/ai/test${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   • Health:         http://localhost:8000/health${CYAN}║${NC}"
    
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC} Commands:${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   • Test AI:        curl http://localhost:8000/api/ai/test${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   • Setup AI:       python scripts/setup_ai_provider.py${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   • View logs:      tail -f logs/backend_*.log${CYAN}║${NC}"
    
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Main script
main() {
    show_banner
    
    # Step 1: Setup AI providers if requested
    if [ $SETUP_MODE -eq 1 ]; then
        if ! setup_ai_providers; then
            log_warning "AI setup failed or was cancelled"
        fi
    fi
    
    # Step 2: Start backend server
    start_backend
    
    # Step 3: Start desktop app (unless --no-ui)
    if [ $NO_UI -eq 0 ]; then
        if ! start_desktop_app; then
            log_warning "Desktop app failed to start, continuing with backend only"
        fi
    fi
    
    # Step 4: Show monitoring dashboard
    show_monitoring
    
    echo ""
    log_success "AI_SUPPORT is running! Press Ctrl+C to stop all components."
    echo ""
    
    # Keep script running
    while true; do
        sleep 1
    done
}

# Run main function
main