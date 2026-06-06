# AI_SUPPORT - Run Everything Commands

This document explains how to run all components of AI_SUPPORT with a single command.

## **QUICK START**

### **Windows (PowerShell - Recommended)**
```powershell
# Run everything with one command
.\run_all.ps1

# With AI setup first
.\run_all.ps1 --setup

# Backend only (no desktop app)
.\run_all.ps1 --no-ui

# Debug mode
.\run_all.ps1 --debug
```

### **Windows (Command Prompt)**
```batch
# Run everything
run_all.bat

# With AI setup first
run_all.bat --setup

# Backend only
run_all.bat --no-ui

# Debug mode
run_all.bat --debug
```

### **Unix/Linux/macOS**
```bash
# Make script executable
chmod +x run_all.sh

# Run everything
./run_all.sh

# With AI setup first
./run_all.sh --setup

# Backend only
./run_all.sh --no-ui

# Debug mode
./run_all.sh --debug
```

### **Using Make (Cross-platform)**
```bash
# Start everything
make all

# Start backend only
make backend

# Start desktop app only
make desktop

# Setup AI providers
make setup

# Run tests
make test

# Clean up
make clean
```

## **WHAT GETS STARTED**

When you run `run_all`, it starts:

### **1. Backend Server (Python FastAPI)**
- **URL**: http://localhost:8000
- **Port**: 8000
- **Features**:
  - AI chat API with WebSocket support
  - Tool execution runtime
  - Session management
  - RealAgent with multiple AI providers
  - Health monitoring endpoints

### **2. Desktop App (Electron)**
- **Technology**: Electron + React + TypeScript
- **Features**:
  - Code editor with AI assistance
  - Task management
  - File explorer
  - Real-time chat interface
  - Embedded engineering workflows

### **3. AI Providers (Automatically Configured)**
- **OpenAI GPT** (if API key set)
- **Ollama** (local, free - automatically installed if needed)
- **Anthropic Claude** (if API key set)
- **Automatic fallback** between providers

## **MONITORING DASHBOARD**

After starting, you'll see:

```
╔══════════════════════════════════════════════════════════════╗
║                    SYSTEM MONITORING                       ║
╠══════════════════════════════════════════════════════════════╣
 Backend:   ● Running http://localhost:8000
 AI Config: ● Configured (openai, ollama)
╠══════════════════════════════════════════════════════════════╣
 Useful URLs:
   • Backend API:    http://localhost:8000
   • AI Config:      http://localhost:8000/api/ai/config/status
   • AI Test:        http://localhost:8000/api/ai/test
   • Health:         http://localhost:8000/health
╠══════════════════════════════════════════════════════════════╣
 Commands:
   • Test AI:        curl http://localhost:8000/api/ai/test
   • Setup AI:       python scripts/setup_ai_provider.py
   • View logs:      tail -f logs/backend_*.log
╚══════════════════════════════════════════════════════════════╝
```

## **TESTING THE SYSTEM**

### **1. Test AI Connection**
```bash
# Using curl
curl http://localhost:8000/api/ai/test

# Or with custom prompt
curl -X POST http://localhost:8000/api/ai/test \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain SPI initialization for STM32"}'
```

### **2. Check AI Configuration**
```bash
curl http://localhost:8000/api/ai/config/status
```

### **3. Health Check**
```bash
curl http://localhost:8000/health
```

### **4. WebSocket Chat Test**
```bash
# Using wscat (install with: npm install -g wscat)
wscat -c ws://localhost:8000/ws/test_session
# Then send: {"type": "chat", "message": "Hello AI_SUPPORT!"}
```

## **TROUBLESHOOTING**

### **Common Issues**

#### **1. Python Dependencies Missing**
```bash
# Install manually
pip install fastapi uvicorn[standard] websockets pydantic aiohttp openai anthropic

# Or use the setup script
python scripts/setup_ai_provider.py
```

#### **2. Node.js Missing (for desktop app)**
- Download from [nodejs.org](https://nodejs.org/)
- Or use `--no-ui` flag to run backend only

#### **3. AI Providers Not Configured**
```bash
# Run AI setup wizard
python scripts/setup_ai_provider.py

# Or set environment variables
export OPENAI_API_KEY="your-key-here"  # Unix
set OPENAI_API_KEY=your-key-here       # Windows

# Or install Ollama locally
curl -fsSL https://ollama.ai/install.sh | sh
ollama serve
```

#### **4. Port 8000 Already in Use**
```bash
# Kill process on port 8000
# Unix/Linux/macOS
lsof -ti:8000 | xargs kill -9

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Or change port in run_all script
```

## **ADVANCED USAGE**

### **Custom Configuration**

#### **1. Environment Variables**
```bash
# Set before running
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export OLLAMA_BASE_URL="http://localhost:11434"
export LOG_LEVEL="DEBUG"

# Then run
./run_all.sh
```

#### **2. Custom Ports**
Edit `run_all.ps1`, `run_all.bat`, or `run_all.sh`:
```bash
# Change these lines
export PORT="9000"  # Backend port
set PORT=9000       # Windows batch
$Env:PORT = "9000"  # PowerShell
```

#### **3. Development Mode**
```bash
# With hot reload and debug logging
./run_all.sh --debug

# Or manually
cd src && python -m uvicorn interfaces.server.main:app --reload --log-level debug
```

## **LOGGING**

Logs are saved to `logs/` directory:
```
logs/
├── backend_20241215_143022.log  # Backend server logs
├── desktop_20241215_143023.log  # Desktop app logs
└── setup_20241215_143021.log    # Setup logs (if --setup used)
```

View logs:
```bash
# Unix/Linux/macOS
tail -f logs/backend_*.log

# Windows PowerShell
Get-Content -Path "logs\backend_*.log" -Wait

# Windows Command Prompt
type logs\backend_*.log
```

## **STOPPING THE SYSTEM**

### **Graceful Shutdown**
Press `Ctrl+C` in the terminal where you ran `run_all`

### **Force Stop**
```bash
# Unix/Linux/macOS
pkill -f "uvicorn|node|python.*main"

# Windows
taskkill /F /IM python.exe
taskkill /F /IM node.exe
```

## **PERFORMANCE TIPS**

### **For Embedded Engineering Work**
```bash
# Use Ollama locally for faster response
./run_all.sh --setup  # Choose Ollama option

# Pull specialized models
ollama pull codellama    # Code generation
ollama pull deepseek-coder  # Embedded code
ollama pull llama3.2     # General purpose
```

### **For Cloud AI**
```bash
# Set API keys first
export OPENAI_API_KEY="sk-..."
# Or
export ANTHROPIC_API_KEY="sk-ant-..."

./run_all.sh
```

## **NEXT STEPS**

After running successfully:

1. **Open desktop app** (if started)
2. **Test AI chat** in the interface
3. **Try embedded queries**:
   - "Explain CAN bus initialization"
   - "Show me SPI register configuration for STM32"
   - "Help me debug this interrupt handler"
4. **Check documentation**:
   - `docs/AI_CONFIGURATION_GUIDE.md`
   - `docs/AI_SUPPORT_IMPROVEMENTS_SUMMARY.md`
   - `AGENTS.md` for agent guidelines

## **SUPPORT**

If you encounter issues:
1. Check logs in `logs/` directory
2. Run `make test` to check system health
3. Review `docs/AI_CONFIGURATION_GUIDE.md`
4. Check if AI providers are configured

For embedded-specific issues, ensure you're using appropriate models (CodeLlama, DeepSeek-Coder) for better embedded engineering support.