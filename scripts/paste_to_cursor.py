#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Paste to Cursor Chat
"""
import io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pyperclip
import keyboard
import pygetwindow as gw

def main():
    # Ket qua tu DeepSeek review phase_1a.md
    content = """Hay thuc hien cac task sau dua tren review cua DeepSeek cho Phase 1a:

## KET QUA REVIEW DEEPSEEK:

### 1. Tool Survey (1a.2)
- **pyOCD** duoc chon lam primary debug core
- Integration Strategy:
  FastAPI/WebSocket → Debug Service (async) → pyOCD Session Pool → J-Link/ST-Link → Target

### 2. Key Insights:
- Segger: No built-in tracing (can dung Segger thay vi)
- Limited to ARM Cortex-M
- Use pyOCD's synchronous API within asyncio threads

### 3. pyproject.toml (1a.3) - Da co san:
- fastapi==0.104.1
- uvicorn[standard]==0.24.0
- websockets==12.0
- asyncpg==0.29.0
- redis==5.0.1
- sqlalchemy==2.0.23
- alembic==1.12.1
- pyocd==0.35.0

## YEU CAU:
1. Thuc hien tat ca cac task trong phase_1a.md
2. Commit [Phase 1a] khi xong
3. Cap nhat build_log.md va ERA_ROADMAP.md
4. Khong hoi lai

Hay bat dau thuc hien!
"""

    # Tim cua so Cursor
    wins = [w for w in gw.getAllWindows() if "cursor" in w.title.lower()]
    if not wins:
        print("[ERR] Khong tim thay Cursor!")
        return

    win = wins[0]
    print("Tim thay Cursor...")
    win.activate()
    time.sleep(0.5)

    # Copy
    pyperclip.copy(content)
    time.sleep(0.3)

    # Paste
    keyboard.send("ctrl+v")
    time.sleep(0.3)

    print("[OK] Da paste vao Cursor!")

if __name__ == "__main__":
    main()
