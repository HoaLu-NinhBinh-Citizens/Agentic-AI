# AgenticAI – Testability & Quality Review Report

**Project:** AgenticAI
**Architecture:** Electron + React + TypeScript + Zustand + Monaco Editor
**Review Type:** QA Architecture, Testability & Automation Readiness Assessment

---

# Executive Summary

AgenticAI hiện có nền tảng kiến trúc tương đối tốt cho một IDE desktop hiện đại:

* Electron Main/Renderer đã được tách biệt.
* Zustand phù hợp cho state management.
* AST-based analyzers có khả năng test rất cao.
* React component structure tương đối rõ ràng.

Tuy nhiên hệ thống hiện đang gặp các vấn đề lớn về testability:

* Renderer phụ thuộc trực tiếp vào `window.electronAPI`.
* Main process chứa nhiều logic tập trung trong `main.js`.
* Thiếu dependency injection.
* Native modules (`node-pty`) gây khó khăn cho CI/CD.
* Không có test coverage hiện tại.

Nếu không cải thiện kiến trúc testability, chi phí bảo trì sẽ tăng nhanh khi số lượng tính năng AI và IDE features mở rộng.

---

# PHASE 1 — TESTABILITY ASSESSMENT

| Module                 | Type         | Testability | Risk     | Notes                               |
| ---------------------- | ------------ | ----------- | -------- | ----------------------------------- |
| ollamaClient (planned) | Service      | Low         | High     | Chưa implement, phụ thuộc fetch     |
| aiService.ts           | Service      | Medium      | Medium   | Có thể mock nhưng chưa có interface |
| steeringParser.ts      | Service      | High        | Low      | Pure logic, dễ mock fs              |
| storage.ts             | Service      | Medium      | Low      | electron-store có thể mock          |
| gitIntegration.js      | Service      | Low         | High     | Gọi simple-git trực tiếp            |
| terminal.js            | Service      | Very Low    | Critical | node-pty native dependency          |
| codeAnalyzer.js        | Service      | High        | Low      | AST parsing thuần                   |
| securityDetector.js    | Service      | High        | Low      | Rule-based detection                |
| fixEngine.js           | Service      | Low         | Medium   | Phụ thuộc AI và file system         |
| search.js              | Service      | Low         | Medium   | child_process dependency            |
| main.js                | Main Process | Low         | Critical | IPC handlers tập trung              |
| preload.js             | Preload      | Very Low    | High     | contextBridge khó test              |
| App.tsx                | Component    | Low         | Medium   | Global dependencies                 |
| Sidebar.tsx            | Component    | Low         | Medium   | IPC coupling                        |
| Editor.tsx             | Component    | Low         | High     | Monaco integration                  |
| ChatPanel.tsx          | Component    | Low         | Medium   | AI dependency                       |
| TaskPanel.tsx          | Component    | Medium      | Low      | Chủ yếu UI logic                    |
| CommandPalette.tsx     | Component    | Low         | Medium   | cmdk dependency                     |
| SettingsModal.tsx      | Component    | Medium      | Low      | Dễ test bằng RTL                    |
| ActivityBar.tsx        | Component    | Medium      | Low      | UI-centric                          |
| StatusBar.tsx          | Component    | Medium      | Low      | Store-driven                        |
| useAppStore.ts         | Store        | High        | Low      | Zustand test rất tốt                |
| IPC Channels           | IPC          | Very Low    | Critical | Cần integration testing             |

---

# PHASE 2 — TEST COVERAGE GAP ANALYSIS

## Missing Unit Tests

### Zustand Store

* setWorkspace()
* addFile()
* removeFile()
* toggleFolder()
* addTask()
* updateTask()
* deleteTask()

### Utilities

* path helpers
* file sorting
* tree building
* formatting functions

### AST & Analysis

* codeAnalyzer
* securityDetector
* qualityDetector
* fixEngine

### AI Layer

* chat()
* generateCode()
* codeReview()
* streaming response handling
* error handling

---

## Missing Integration Tests

### IPC Layer

* dialog:openDirectory
* fs:readDirectory
* fs:readFile
* fs:writeFile
* fs:createFile
* fs:createDirectory
* fs:deleteFile
* fs:rename

### Services

* aiService
* storage
* steeringParser
* gitService
* terminal service

---

## Missing End-to-End Tests

### Workspace

* Open Folder
* Refresh Folder
* Expand Tree
* Collapse Tree

### Editor

* Open File
* Edit File
* Save File
* Dirty Indicator

### AI

* Configure Provider
* Send Chat
* Stream Response

### Git

* Stage File
* Commit Changes
* Refresh Status

### Tasks

* Create Task
* Complete Task
* Delete Task

---

# Coverage Gap Matrix

| Feature          | Current Coverage | Recommended Coverage | Priority |
| ---------------- | ---------------- | -------------------- | -------- |
| Zustand Store    | 0%               | 80%                  | High     |
| AST Analysis     | 0%               | 90%                  | High     |
| AI Service       | 0%               | 70%                  | High     |
| File Operations  | 0%               | 60%                  | High     |
| Git Service      | 0%               | 50%                  | Medium   |
| Terminal         | 0%               | 30%                  | Low      |
| IPC              | 0%               | 70%                  | High     |
| React Components | 0%               | 60%                  | High     |

---

# PHASE 3 — MOCKING STRATEGY REVIEW

| Dependency    | Strategy                |
| ------------- | ----------------------- |
| electron      | Mock window.electronAPI |
| ipcRenderer   | jest mock               |
| ipcMain       | electron-mock-ipc       |
| fs            | memfs                   |
| path          | Use real implementation |
| child_process | jest.mock               |
| node-pty      | Integration only        |
| simple-git    | jest.mock               |
| fetch         | spyOn(global.fetch)     |
| OpenAI SDK    | jest.mock               |
| Ollama        | Mock fetch              |

---

## Recommended Libraries

```bash
npm install -D

jest
ts-jest
@testing-library/react
@testing-library/user-event
@testing-library/jest-dom

playwright

memfs
mock-fs

electron-mock-ipc

jest-environment-jsdom
```

# PHASE 4 — ELECTRON TEST ARCHITECTURE REVIEW

## Critical Issues

### 1. window.electronAPI Coupling

Severity: Critical

Problem:

* Components access global API directly.
* Hard to isolate tests.

Recommendation:

Create:

```text
src/services/electronBridge.ts
```

```ts
export interface ElectronBridge {
  openDirectory(): Promise<string>;
  readFile(path: string): Promise<string>;
}
```

Inject bridge into components.

### 2. Monolithic main.js

Severity: High

Problem:

All IPC handlers live in one file.

Recommendation:

```text
src/main/handlers/
 ├─ fsHandlers.ts
 ├─ gitHandlers.ts
 ├─ aiHandlers.ts
 └─ terminalHandlers.ts
```

### 3. Missing IPC Validation

Severity: Medium

Recommendation:

Use:

```bash
zod
```

for request validation.

### 4. node-pty Dependency

Severity: Critical

Problem:

Native dependency breaks CI.

Recommendation:

* Integration tests only.
* Skip unit tests.

---

# PHASE 5 — IPC REVIEW

| Channel              | Unit Testable | Integration Testable | Mockable |
| -------------------- | ------------- | -------------------- | -------- |
| dialog:openDirectory | No            | Yes                  | Yes      |
| fs:readDirectory     | No            | Yes                  | Yes      |
| fs:readFile          | No            | Yes                  | Yes      |
| fs:writeFile         | No            | Yes                  | Yes      |
| fs:createFile        | No            | Yes                  | Yes      |
| fs:createDirectory   | No            | Yes                  | Yes      |
| fs:deleteFile        | No            | Yes                  | Yes      |
| fs:rename            | No            | Yes                  | Yes      |

## Findings

Current handlers:

* No schema validation
* Limited logging
* Weak error reporting

Risk Level: High

---

# PHASE 6 — SERVICE REVIEW

## aiService

### Public API

```ts
chat()
generateCode()
codeReview()
```

### Recommended Tests

* provider routing
* streaming
* timeout
* cancellation
* error handling

---

## gitService

### Public API

```ts
status()
add()
commit()
branch()
```

### Recommended Tests

* clean repo
* modified files
* commit success
* commit failure

---

## terminalService

### Public API

```ts
spawn()
write()
resize()
kill()
```

### Recommended Tests

* PTY creation
* output forwarding
* cleanup

E2E only.

---

## storageService

### Recommended Tests

* save settings
* load settings
* workspace persistence
* task persistence

---

## codeAnalyzer

### Recommended Tests

* TypeScript AST
* JavaScript AST
* syntax errors
* large file handling

---

## steeringParser

### Recommended Tests

* AGENTS.md
* CLAUDE.md
* missing files
* malformed files

---

# PHASE 7 — COMPONENT REVIEW

| Component      | Difficulty |
| -------------- | ---------- |
| Sidebar        | High       |
| Editor         | High       |
| ChatPanel      | Medium     |
| TaskPanel      | Low        |
| CommandPalette | Medium     |
| SettingsModal  | Medium     |
| ActivityBar    | Low        |
| StatusBar      | Low        |

## Hardest Component

Editor

Reasons:

* Monaco dependency
* File system dependency
* Cursor tracking
* Save behavior

Requires aggressive mocking.

---

# PHASE 8 — CI/CD READINESS REVIEW

## Can Run in GitHub Actions

### Supported

* Jest
* RTL
* Coverage
* Static analysis

### Problematic

* Electron E2E
* node-pty
* Native rebuilds

---

## Recommended CI Pipeline

### Job 1

```yaml
lint
typecheck
unit tests
coverage
```

### Job 2

```yaml
integration tests
```

### Job 3

```yaml
playwright e2e
```

Run separately.

---

# PHASE 9 — COVERAGE ROADMAP

## Phase 1 (2–3 Days)

Highest ROI

### Target

* Zustand Store
* codeAnalyzer
* securityDetector
* Utilities

### Estimated

* 35 tests
* +40% coverage

---

## Phase 2 (1 Week)

Integration

### Target

* IPC
* Storage
* AI Service
* Git Service

### Estimated

* 20 tests
* +20% coverage

---

## Phase 3 (1 Week)

E2E

### Target

* Workspace
* Editor
* AI
* Tasks
* Git

### Estimated

* 10 scenarios
* +5% coverage

---

# PHASE 10 — FINAL SCORECARD

| Category             | Score |
| -------------------- | ----- |
| Architecture Quality | 5/10  |
| Testability          | 3/10  |
| Mockability          | 4/10  |
| CI Readiness         | 4/10  |
| Maintainability      | 5/10  |

---

# Most Critical Risks

1. No automated tests.

2. node-pty native dependency blocks CI automation.

3. IPC handlers lack validation and structured error handling.

4. Tight coupling to window.electronAPI.

---

# Most Valuable Next Tests

### Priority #1

Zustand Store

Expected ROI: Very High

### Priority #2

codeAnalyzer & securityDetector

Expected ROI: High

### Priority #3

fs IPC Integration Tests

Expected ROI: High

### Priority #4

AI Service Mock Integration

Expected ROI: High

---

# Final Verdict

Current repository is functional but not yet automation-ready.

Before investing heavily in E2E coverage, focus on:

1. Dependency Injection
2. IPC modularization
3. Electron API abstraction
4. Store unit testing
5. Analyzer unit testing

Expected outcome after refactoring:

* Testability: 3/10 → 7/10
* CI Readiness: 4/10 → 8/10
* Maintainability: 5/10 → 8/10
