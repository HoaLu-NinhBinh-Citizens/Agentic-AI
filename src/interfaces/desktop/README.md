# AI_SUPPORT Desktop

A Cursor-like Electron desktop application for Windows, built from the AI_SUPPORT embedded engineering platform.

## Features

- **Score Tile UI**: App tiles with percentage scores (60, 45, 72, etc.) - click to select and view score
- **Workspace Explorer**: File tree navigation with syntax highlighting
- **Code Editor**: Read-only file viewer with syntax highlighting via highlight.js
- **Backend Integration**: Connects to FastAPI backend for scores and data
- **Dark Theme**: GitHub-inspired dark theme matching Cursor/VS Code aesthetics

## Architecture

```
src/interfaces/desktop/
├── package.json              # Dependencies and scripts
├── electron-builder.json      # Build configuration
├── electron.vite.config.ts    # Vite + Electron bundler config
├── tailwind.config.js         # TailwindCSS configuration
├── tsconfig.json              # TypeScript configuration
├── src/
│   ├── main/
│   │   └── index.ts          # Electron main process
│   ├── preload/
│   │   └── index.ts          # Context bridge API
│   └── renderer/
│       ├── index.html
│       ├── index.tsx          # React entry point
│       ├── index.css          # Global styles
│       ├── App.tsx            # Main application layout
│       └── components/
│           ├── ScoreTile.tsx  # Score display tiles
│           ├── WorkspaceTree.tsx  # File explorer
│           ├── EditorPanel.tsx    # Code viewer
│           └── StatusBar.tsx      # Status bar
```

## Requirements

- Node.js 18+ 
- Python 3.9+
- Windows 10/11

## Installation

1. Navigate to the desktop folder:

```bash
cd src/interfaces/desktop
```

2. Install Node.js dependencies:

```bash
npm install
```

## Development

Run the application in development mode:

```bash
npm run dev
```

This will:
1. Start the Python FastAPI backend on port 8001
2. Start the Electron app with hot reload
3. Open the desktop window

## Building for Windows

Build the application and create a Windows executable:

```bash
npm run build:win
```

Output files:
- `release/` - Build output directory
- `release/win-unpacked/` - Unpacked application
- `release/*.exe` - Installer or portable executable

## Usage

### Score Tiles

The top bar displays app tiles with scores:
- Click a tile to select it (highlighted with dotted border)
- Scores are fetched from the backend API (`/api/score`)
- Default score for Cursor app is 60

### Workspace Explorer

- Left sidebar shows the workspace file tree
- Click folders to expand/collapse
- Click files to open in the editor panel
- Files are filtered to exclude common development artifacts

### Code Editor

- Displays selected file content with syntax highlighting
- Supports Python, TypeScript, JavaScript, Rust, Go, C/C++, and more
- Shows line numbers
- Read-only mode for viewing

### Status Bar

- Shows backend connection status
- Displays current file path and language
- Shows cursor position (line, column)

## Backend API

The desktop app connects to the FastAPI backend:

- `GET /health` - Health check
- `GET /api/score` - Returns score data
- `GET /api/fs/read?path=<filepath>` - Read file content
- `GET /api/fs/dir?path=<dirpath>` - List directory

## Configuration

### Environment Variables

- `BACKEND_PORT` - Backend server port (default: 8001)
- `PYTHONUNBUFFERED=1` - Ensure Python output is not buffered

### Customization

Edit `tailwind.config.js` to modify colors and styling.

## Troubleshooting

### Backend not starting

Ensure Python and uvicorn are installed:

```bash
pip install uvicorn fastapi
```

### Build fails

Ensure you have the correct Node.js version and all dependencies installed:

```bash
node -v  # Should be 18+
npm -v
npm install
```

### App not displaying files

The workspace is set to the project root. File system access requires proper permissions.

## License

MIT
