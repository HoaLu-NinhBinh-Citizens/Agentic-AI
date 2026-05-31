# Kiro AI IDE — Design Specification

## Visual Identity

### Color Palette

| Name | Hex | Usage |
|------|-----|-------|
| Primary | `#6366F1` | Actions, links, active states |
| Primary Dark | `#4F46E5` | Hover states |
| Secondary | `#10B981` | Success, resolved |
| Warning | `#F59E0B` | Medium severity |
| Error | `#EF4444` | High/Critical severity |
| Background | `#0F172A` | Main background (dark) |
| Surface | `#1E293B` | Cards, panels |
| Surface Light | `#334155` | Hover backgrounds |
| Text Primary | `#F8FAFC` | Main text |
| Text Secondary | `#94A3B8` | Muted text |
| Border | `#475569` | Borders, dividers |

### Light Theme

| Name | Hex | Usage |
|------|-----|-------|
| Primary | `#6366F1` | Actions, links |
| Background | `#FFFFFF` | Main background |
| Surface | `#F8FAFC` | Cards, panels |
| Text Primary | `#0F172A` | Main text |
| Text Secondary | `#64748B` | Muted text |
| Border | `#E2E8F0` | Borders |

### Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| H1 | Inter | 24px | 700 |
| H2 | Inter | 20px | 600 |
| H3 | Inter | 16px | 600 |
| Body | Inter | 14px | 400 |
| Code | JetBrains Mono | 13px | 400 |
| Small | Inter | 12px | 400 |

### Severity Badges

| Severity | Background | Text | Icon |
|----------|------------|------|------|
| CRITICAL | `#EF4444` | white | 🔴 |
| HIGH | `#F97316` | white | 🟠 |
| MEDIUM | `#F59E0B` | dark | 🟡 |
| LOW | `#3B82F6` | white | 🔵 |
| INFO | `#6B7280` | white | ⚪ |

## UI Components

### 1. Command Palette

**Trigger:** `Ctrl+Shift+P` or `/`

**Features:**
- Fuzzy search
- Recent commands
- Category grouping
- Keyboard navigation

**Appearance:**
```
┌─────────────────────────────────────────────┐
│ > Analyze project                          │
├─────────────────────────────────────────────┤
│ 🔍 Analyze Project                         │
│ 🔍 Analyze Current File                    │
│ 🔍 Run Tests                               │
│ ⚙️  Settings                              │
│ 📦 Plugins                                 │
├─────────────────────────────────────────────┤
│ Press Enter to execute • Esc to close     │
└─────────────────────────────────────────────┘
```

### 2. Findings Panel

**Location:** Right sidebar

**Features:**
- Group by file or severity
- Filter by category
- Quick navigation to code
- Inline diff preview

**Appearance:**
```
┌─────────────────────────────────────────────┐
│ 🔴 5 Critical  🟠 12 High  🟡 8 Medium      │
├─────────────────────────────────────────────┤
│ 🔴 SQL Injection                           │
│    src/handler.py:42                        │
│    cursor.execute(query)                   │
│                                             │
│    [View Fix] [Dismiss] [Add Comment]     │
├─────────────────────────────────────────────┤
│ 🟠 Missing Auth                            │
│    src/api.py:15                           │
│    @app.route("/admin")                   │
└─────────────────────────────────────────────┘
```

### 3. AI Chat Panel

**Location:** Bottom panel (collapsible)

**Features:**
- Streaming responses
- Code block highlighting
- Action buttons on responses
- Context awareness

**Appearance:**
```
┌─────────────────────────────────────────────┐
│ 🤖 Kiro AI                                │ ─
├─────────────────────────────────────────────┤
│ │ How can I help you today?               │
│ │                                          │
│ │ [Code Analysis] [Generate] [Debug]     │
│ │                                          │
│ ├─────────────────────────────────────────│
│ │ You: Fix the SQL injection at line 42   │
│ ├─────────────────────────────────────────│
│ │ 🤖: Here's the fix for the SQL          │
│ │     injection vulnerability:            │
│ │                                          │
│ │     ```python                           │
│ │     # Use parameterized query          │
│ │     cursor.execute(                    │
│ │         "SELECT * FROM users WHERE      │
│ │          id = ?",                       │
│ │         [user_id]                       │
│ │     )                                   │
│ │     ```                                 │
│ │                                          │
│ │ [Apply Fix] [Copy] [Explain More]      │
│ └─────────────────────────────────────────│
│ > Type your message or / for commands...   │
└─────────────────────────────────────────────┘
```

### 4. Diff Viewer

**Features:**
- Side-by-side or unified view
- Syntax highlighting
- Line numbers
- Inline comments

**Side-by-side appearance:**
```
┌──────────────────────┬──────────────────────┐
│  - cursor.execute(    │  + cursor.execute(   │
│  -     query          │  +     "SELECT *     │
│  - )                  │  +      WHERE id=?", │
│                       │  +     [user_id]     │
│                       │  + )                 │
├──────────────────────┴──────────────────────┤
│ Review: SQL Injection fixed ✓              │
└─────────────────────────────────────────────┘
```

### 5. Progress Indicators

**Analysis Progress:**
```
Analyzing: src/main.py ████████░░░░░ 45%
```

**Streaming Response:**
```
🤖 Thinking... ░░░░░░░░░░░░░░░ 50ms
```

### 6. Toast Notifications

| Type | Icon | Color |
|------|------|-------|
| Success | ✓ | Green |
| Error | ✗ | Red |
| Warning | ⚠ | Yellow |
| Info | ℹ | Blue |

## Layout Structure

### Main Window

```
┌────────────────────────────────────────────────────────────┐
│  File  Edit  View  AI  Help              [👤] [⚙️] [🔔]   │
├────────┬───────────────────────────────────────┬───────────┤
│        │                                       │           │
│ File   │          Code Editor                  │ Findings  │
│ Tree   │                                       │ Panel     │
│        │                                       │           │
│        │                                       │           │
├────────┴───────────────────────────────────────┴───────────┤
│  ┌─────────────────────────────────────────────────────┐   │
│  │              AI Chat / Terminal                      │   │
│  └─────────────────────────────────────────────────────┘   │
├────────────────────────────────────────────────────────────┤
│  Ready │ Python │ UTF-8 │Ln 42, Col 15 │ AI: Active       │
└────────────────────────────────────────────────────────────┘
```

## Responsive Behavior

| Breakpoint | Layout Changes |
|------------|-----------------|
| > 1400px | Full layout with all panels |
| 1024-1400px | Findings panel collapsible |
| 768-1024px | File tree collapsed to icons |
| < 768px | Single panel view with tabs |

## Animations

| Element | Animation | Duration |
|---------|-----------|----------|
| Panel open/close | Slide | 200ms |
| Toast appear | Fade + Slide | 150ms |
| Button hover | Background color | 100ms |
| Findings expand | Height + Fade | 200ms |
| Loading spinner | Rotate | 1s infinite |

## Accessibility

- Minimum contrast ratio: 4.5:1
- Focus indicators on all interactive elements
- Keyboard shortcuts for all major actions
- Screen reader compatible labels
- Reduced motion support via `prefers-reduced-motion`
