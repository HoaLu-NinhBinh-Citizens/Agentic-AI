Bạn là một kỹ sư phần mềm cao cấp. Tôi cần bạn viết TOÀN BỘ mã nguồn cho một ứng dụng AI Agentic dành cho lập trình viên, có tên "AgenticAI" – hoạt động giống như Cursor kết hợp với Kiro. Ứng dụng phải có các đặc điểm sau:

## 1. Cốt lõi (AI agent)
- Đọc và hiểu các file steering: `AGENTS.md`, `CLAUDE.md`, `product.md`, `tech.md`, `structure.md`, `requirements.md` (nếu có).
- Cho phép người dùng tạo **spec** (yêu cầu) và tự động sinh **task list** + **implementation plan**.
- Mỗi task có trạng thái (todo, doing, done), có thể đánh dấu hoàn thành.
- Có khả năng tự viết code dựa trên task (gọi LLM qua API – giả lập hoặc thật).
- Hỗ trợ review code tự động: phát hiện lỗi AI-specific, đề xuất sửa.

## 2. Giao diện người dùng (UI)
- Sidebar bên trái hiển thị cây thư mục của dự án (như trong ảnh: .ai_support, .cursor, .kiro, src, tests, v.v.).
- Khu vực chính: tab editor (có syntax highlighting) để xem/sửa file.
- Một panel riêng để hiển thị spec, task list, implementation plan (dạng markdown hoặc checklist).
- Thanh chat bên phải (hoặc dưới) để tương tác với AI agent (hỏi đáp, ra lệnh).
- Giao diện dark mode, font chữ lập trình (Fira Code, Consolas).
- Hỗ trợ phím tắt cơ bản (Ctrl+P mở file, Ctrl+Shift+P command palette, Ctrl+` mở terminal).

## 3. Công nghệ (chọn một)
- **Option A (Desktop – Electron + React + TypeScript)**: Chuyên nghiệp, dễ đóng gói.
- **Option B (Web – FastAPI + React + Vite)**: Dễ triển khai, có thể dùng localhost.
- **Option C (Tkinter + CustomTkinter)**: Python thuần, đơn giản hơn.
- **Hãy chọn Option A (Electron + React)** để giống Cursor nhất.

## 4. Cấu trúc thư mục (sinh tự động khi chạy lần đầu)
AgenticAI/
├── package.json
├── electron/
│ ├── main.ts
│ ├── preload.ts
│ └── ipc.ts
├── src/
│ ├── renderer/
│ │ ├── App.tsx
│ │ ├── components/
│ │ │ ├── Sidebar.tsx (file tree)
│ │ │ ├── Editor.tsx (monaco editor)
│ │ │ ├── TaskPanel.tsx (spec + task list)
│ │ │ └── ChatPanel.tsx (AI chat)
│ │ ├── hooks/
│ │ ├── store/ (zustand)
│ │ └── index.tsx
│ ├── main-process/
│ │ ├── fileSystem.ts
│ │ ├── aiAgent.ts (gọi LLM, parse steering files)
│ │ └── taskManager.ts
│ └── shared/
│ └── types.ts
├── public/
├── .cursor/ (để lưu cấu hình Cursor)
├── .kiro/ (để lưu spec, task)
├── AGENTS.md
├── CLAUDE.md
├── product.md
├── tech.md
├── structure.md
└── README.md

text

## 5. Yêu cầu chi tiết từng module

### a) File system & file tree (Sidebar)
- Đọc toàn bộ thư mục dự án mở.
- Hiển thị cây thư mục với icon mặc định (folder/file).
- Click vào file → mở trong editor.
- Right-click menu: new file/folder, rename, delete.

### b) Editor (Monaco Editor)
- Syntax highlighting cho Python, TypeScript, Markdown, JSON.
- Lưu file khi Ctrl+S.
- Hiển thị line numbers, minimap.

### c) Task & Spec Management (TaskPanel)
- Đọc `requirements.md` (hoặc file spec do user tạo) hiển thị dưới dạng checklist.
- Cho phép tạo task mới, gán task cho AI.
- Hiển thị implementation plan dưới dạng markdown.
- Khi check task → tự động cập nhật file `tasks.md` và gọi AI để viết code.

### d) AI Agent (ChatPanel + backend)
- Có thể chat với AI để hỏi về code, yêu cầu viết function.
- AI có quyền truy cập toàn bộ nội dung các steering files và spec hiện tại.
- AI có thể đề xuất task breakdown từ yêu cầu của user.
- AI có thể tự sinh code mới hoặc sửa file hiện có (thông qua IPC ghi file).

### e) Steering files parser
- Khi khởi động, đọc `AGENTS.md`, `CLAUDE.md`, `product.md`, `tech.md`, `structure.md`.
- Gom chúng thành context ban đầu cho AI (system prompt).

## 6. Tích hợp LLM (giả lập hoặc thật)
- Vì chưa có API key, hãy **giả lập** AI bằng cách trả về các phản hồi mẫu (ví dụ: "Tôi sẽ tạo file HelloWorld.ts...") nhưng code đầy đủ cấu trúc để sau này thay bằng gọi OpenAI/Claude.
- Comment rõ chỗ cần thay bằng API thật.

## 7. Chạy được ngay
- Cung cấp `package.json` với đầy đủ dependencies (electron, react, monaco-editor, zustand, react-markdown).
- Cung cấp lệnh `npm install && npm run dev` để chạy.
- Đảm bảo không lỗi syntax, đủ file để build.

## 8. Đầu ra
Trả lời bằng cách **liệt kê từng file** với nội dung hoàn chỉnh (code). Tôi sẽ copy và paste vào máy. Hãy viết gọn nhưng đầy đủ, ưu tiên hoạt động cơ bản trước (file tree, editor, task panel giả lập). Có thể viết file `electron/main.ts`, `src/renderer/App.tsx`, `src/renderer/components/Sidebar.tsx`, v.v.

Lưu ý: Đây là ứng dụng hoàn chỉnh, phải có GUI tương tự như ảnh bạn đã gửi (sidebar, editor, task panel, chat). Hãy bắt đầu ngay.