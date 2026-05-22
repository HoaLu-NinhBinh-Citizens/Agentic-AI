# AUTO_BUILD_MASTER - Hướng dẫn sử dụng

## Tổng quan

File này chứa hướng dẫn sử dụng các master prompt để tự động hoàn thiện toàn bộ dự án AI_SUPPORT.

## Cấu trúc

```
prompts/                 # ★ Khuyến nghị: từng phase một file (chạy tuần tự)
  README.md              # Thứ tự phase + lệnh Agent
  phase_1a.md … phase_16.md
AUTO_BUILD_PROMPT_1.md  # Phases 1a - 5d (gộp, legacy)
AUTO_BUILD_PROMPT_2.md  # Phases 5e - 10 (gộp, legacy)
build_log.md            # Theo dõi tiến độ (✅/⬜)
```

## Cách sử dụng

### 1. Chuẩn bị

Đảm bảo đang ở thư mục project:

```bash
cd C:\Users\thang\Desktop\Agentic-AI
```

### 2. Mở project và Agent

1. **File → Open Folder** → `C:\Users\thang\Desktop\Agentic-AI` (bắt buộc — không dùng cửa sổ trống)
2. Nhấn `**Ctrl + I`** để mở Agent / Composer (không phải `Ctrl + L` Chat)
3. Chọn chế độ **Agent** (hoặc `Shift + Tab` để đổi Agent / Ask)
4. Mở hoặc `@` tham chiếu `AUTO_BUILD_PROMPT_1.md`

> **Lưu ý:** Trang Settings → Rules, Skills, Subagents chỉ là cấu hình, không phải nơi chạy build. Lệnh cũ "Agent: Enable Agent Mode" có thể không còn trong Command Palette.

### 3. Khởi động

**Khuyến nghị — từng phase** (`prompts/README.md`):

```
@prompts/phase_1a.md Thực hiện tuần tự các task. Commit [Phase 1a] sau mỗi task. Cập nhật build_log.md. Bỏ qua task đã ✅.
```

Xong phase → `@prompts/phase_1b.md`, … → `phase_16.md`.

**Legacy — prompt gộp** — gõ vào **Agent** (`Ctrl + I`):

```
@AUTO_BUILD_PROMPT_1.md Đọc build_log.md và codebase. Đánh dấu ✅ task đã có, làm tiếp task ⬜ từ phase thấp nhất còn thiếu. Cập nhật build_log.md sau mỗi phase. Không hỏi lại tôi.
```

Hoặc nếu muốn bắt đầu từ đầu (bỏ qua phần đã có):

```
@AUTO_BUILD_PROMPT_1.md Hãy thực hiện toàn bộ các phase theo đúng hướng dẫn trong file này, bắt đầu từ Phase 1a, mỗi bước commit và log. Không hỏi lại tôi, tự động sửa lỗi nếu có thể.
```

### 4. Khi Cursor dừng

Nếu Cursor Agent dừng do context limit hoặc lỗi, gõ:

```
continue
```

Hoặc:

```
Gặp lỗi [mô tả lỗi], hãy sửa và tiếp tục từ task [tên task]
```

### 5. Tiếp tục sang Part 2

Sau khi hoàn thành Part 1, mở `AUTO_BUILD_PROMPT_2.md` và gõ:

```
@AUTO_BUILD_PROMPT_2.md Tiếp tục với Phase 5e trở đi. Không hỏi lại tôi.
```

## Cấu trúc Phase

### Phase 1a-1b: Minimal Runtime

- WebSocket server
- Session management
- Heartbeat, cancellation, timeout
- Backpressure, rate limiting

### Phase 2a-2d: MCP + Tool Execution

- MCP integration
- Tool execution
- Cancellation, retry
- Multi-server routing

### Phase 3: LLM Integration

- OpenAI, Anthropic, Ollama
- Tool calling
- Streaming

### Phase 4a-4d: Memory

- Tool caching
- Semantic routing
- Semantic memory
- Compression

### Phase 5a-5f: Enterprise

- Workflow engine
- Task planner
- Multi-agent coordination
- Distributed execution
- Reliability & governance

### Phase 6.1-6.3: Hardware

- J-Link/RTT integration
- Flash infrastructure
- Real-time tracing

### Phase 7-10: UI & Advanced

- CLI + TUI
- VS Code Extension
- Distributed agents
- Advanced reasoning

## Mẹo chạy ổn định

1. **Tắt Auto-compact**: Settings → Features → AI → "Auto-compact context" = OFF
2. **Tăng context**: Nếu có tùy chọn, tăng max tokens
3. **Thỉnh thoảng save**: Gõ "save checkpoint" để đảm bảo progress
4. **Tránh update giữa chừng**: Không để Cursor tự cập nhật

## Theo dõi tiến độ

**Nguồn chính:** `build_log.md` (cập nhật 2026-05-21 theo codebase thực tế).

Tóm tắt hiện tại:

- **Part 1 (1a–5b):** ~85% — còn 2c retry path, mock→real agent, workflow engine naming
- **Part 2 (5e–10):** ~60% — 6.2 ✅; thiếu 6.1 J-Link, 6.3 RTT, 7 CLI, 8 Extension

Sau mỗi phase Agent hoàn thành, gõ:

```
Cập nhật build_log.md cho phase vừa xong
```

Hoặc

```
status
```

## Troubleshooting

### Không thấy Agent / không chạy được

- Đảm bảo đã **Open Folder** project (không phải `empty-window`)
- Dùng `**Ctrl + I`**, không vào Settings → Rules/Skills
- Test: `Liệt kê 5 file ở thư mục gốc workspace` — phải thấy `AUTO_BUILD_PROMPT_1.md`

### Lỗi import

Kiểm tra PYTHONPATH (PowerShell):

```powershell
$env:PYTHONPATH = "$env:PYTHONPATH;$(Get-Location)\src"
```

Hoặc bash:

```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

### Lỗi test

Chạy test riêng:

```bash
python -m pytest tests/unit/test_[module].py -v
```

### Context limit

Khi context gần đầy, Cursor sẽ tự compact. Nếu cần, gõ:

```
compact
```

## Hoàn thành

Khi tất cả phases hoàn thành, kiểm tra:

1. Tất cả tests pass
2. Documentation complete
3. Build log đầy đủ

## Liên hệ

Nếu có vấn đề, xem `docs/STRUCTURE_TREE.md` cho cấu trúc thư mục chính xác.