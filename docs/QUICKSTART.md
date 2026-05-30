# Quick Start Guide

## Installation

```bash
# Clone the project
git clone https://github.com/your-ai-support/ai-support.git
cd ai-support

# Install dependencies
pip install -r requirements.txt

# Install Ollama (for LLM features)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3:70b
```

## Basic Usage

### 1. Start Ollama
```bash
ollama serve
```

### 2. Run a Review
```bash
# Review all Python files
python -m src.interfaces.cli.main review src/

# Focus on ML issues
python -m src.interfaces.cli.main review src/ --focus ml

# Review specific file
python -m src.interfaces.cli.main review src/model.py
```

### 3. Apply Fixes
```bash
# Preview fixes
python -m src.interfaces.cli.main fix @src/train.py:45

# Apply fix
python -m src.interfaces.cli.main fix @src/train.py:45 --apply

# Auto-apply safe fixes
python -m src.interfaces.cli.main fix --auto
```

### 4. TUI Mode
```bash
python -m src.interfaces.tui.app
```

## Common Commands

| Command | Description |
|---------|-------------|
| `/review [files]` | Analyze code |
| `/fix @file:line` | Apply fix |
| `/summary` | Show all findings |
| `/explain` | Explain current finding |
| `/config` | Show settings |

## Examples

### ML Project Review
```bash
python -m src.interfaces.cli.main review ml_project/ --focus ml,security
```

### Firmware Review
```bash
python -m src.interfaces.cli.main review firmware/ --focus embedded
```

### Full Report
```bash
python -m src.interfaces.cli.main review src/ --format markdown --output report.md
```
