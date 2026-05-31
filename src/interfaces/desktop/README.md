# AgenticAI

AI-powered coding assistant like Cursor + Kiro - một ứng dụng desktop được xây dựng với Electron + React + TypeScript.

## Tính năng

### 🖥️ Giao diện giống Cursor
- **Sidebar**: Cây thư mục dự án với icon cho từng loại file
- **Editor**: Syntax highlighting với highlight.js (Python, TypeScript, Markdown, JSON, v.v.)
- **Task Panel**: Quản lý Spec, Task list, và Implementation Plan
- **Chat Panel**: Tương tác với AI Agent

### 🤖 AI Agent
- Đọc và hiểu các steering files (`AGENTS.md`, `CLAUDE.md`, `product.md`, v.v.)
- Tạo Spec và tự động sinh Task list
- Chat với AI để hỏi đáp, viết code, phân tích yêu cầu
- Đề xuất cải thiện code

### 📋 Task Management
- Tạo, sửa, xóa tasks với 3 trạng thái: Todo, Doing, Done
- Priority levels: Low, Medium, High, Critical
- Progress bar cho Implementation Plan

### 🎨 Dark Mode UI
- Font chữ lập trình: Fira Code / Consolas
- Màu sắc theo phong cách GitHub Dark
- Responsive layout với collapsible panels

## Công nghệ

- **Desktop**: Electron 28
- **Frontend**: React 18 + TypeScript
- **State**: Zustand
- **Styling**: Tailwind CSS
- **Syntax Highlighting**: highlight.js
- **Markdown**: react-markdown
- **Build**: electron-vite + electron-builder

## Cài đặt

```bash
# Di chuyển vào thư mục desktop
cd src/interfaces/desktop

# Cài đặt dependencies
npm install

# Chạy development mode
npm run dev

# Build cho Windows
npm run build:win
```

## Cấu trúc thư mục

```
src/interfaces/desktop/
├── package.json
├── electron.vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── electron-builder.json
├── src/
│   ├── main/
│   │   └── index.ts          # Electron main process
│   ├── preload/
│   │   └── index.ts          # Preload bridge (IPC)
│   ├── renderer/
│   │   ├── App.tsx           # Main app component
│   │   ├── index.tsx         # React entry
│   │   ├── index.html        # HTML template
│   │   ├── index.css         # Global styles
│   │   ├── components/
│   │   │   ├── WorkspaceTree.tsx   # File explorer
│   │   │   ├── EditorPanel.tsx     # Code editor
│   │   │   ├── TaskPanel.tsx       # Spec & task management
│   │   │   ├── ChatPanel.tsx       # AI chat interface
│   │   │   ├── StatusBar.tsx       # Status bar
│   │   │   └── ScoreTile.tsx       # App selector
│   │   └── store/
│   │       └── useAgenticStore.ts  # Zustand store
│   └── shared/
│       └── types.ts          # Shared TypeScript types
└── public/
```

## Phím tắt

| Phím | Chức năng |
|------|-----------|
| `Ctrl+B` | Toggle Sidebar |
| `Ctrl+Shift+P` | Mở Command Palette |
| `Ctrl+S` | Lưu file |
| `Ctrl+T` | Tạo Task mới |
| `Ctrl+Shift+T` | Toggle Task Panel |
| `Ctrl+Shift+C` | Toggle Chat Panel |
| `Double-click` | Bật chế độ Edit trong Editor |

## Steering Files

AgenticAI tự động đọc các steering files sau khi khởi động:

- `AGENTS.md` - Agent instructions
- `CLAUDE.md` - Claude behavior rules
- `product.md` - Product specifications
- `tech.md` - Technical documentation
- `structure.md` - Project structure
- `requirements.md` - Requirements

Các files này được đặt trong:
- Thư mục gốc workspace
- `.ai_support/`
- `.cursor/`
- `.kiro/`

## AI Integration

AI Agent hiện tại là **mock implementation** - trả về responses mẫu dựa trên message của user.

Để tích hợp với LLM thật (OpenAI/Claude), thay đổi hàm `processAIMessage` trong `src/main/index.ts`:

```typescript
// Thay thế mock response bằng:
const response = await fetch('https://api.openai.com/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
  },
  body: JSON.stringify({
    model: 'gpt-4',
    messages: [
      { role: 'system', content: buildSystemPrompt(context) },
      { role: 'user', content: message }
    ]
  })
});
```

## Spec & Task Storage

Tasks và Specs được lưu trong `.kiro/` directory của workspace:

```
.kiro/
├── spec.json   # Current spec
└── tasks.json  # Task list
```

## Development

```bash
# Run in dev mode with hot reload
npm run dev

# Build for production
npm run build

# Package as .exe
npm run package
```

## TODO

- [ ] Monaco Editor thay thế highlight.js
- [ ] Tích hợp OpenAI/Claude API thật
- [ ] Auto-save khi edit
- [ ] Multi-file tabs với close button
- [ ] Search trong workspace
- [ ] Git integration
- [ ] Terminal panel
- [ ] Settings panel
- [ ] Code review automation
- [ ] Auto-completion

## License

MIT
