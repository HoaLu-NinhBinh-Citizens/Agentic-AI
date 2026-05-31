# AgenticAI Test Suite

## Overview

This directory contains the comprehensive test suite for the AgenticAI Electron application.

## Directory Structure

```
tests/
├── jest.config.js           # Jest configuration
├── setup.ts                # Test setup and global mocks
├── playwright.config.ts    # Playwright configuration for E2E tests
├── __fixtures__/          # Test fixtures and mock data
│   └── mockData.ts
├── __mocks__/             # Global mocks
│   └── fileMock.js
├── e2e/                   # End-to-end tests
│   ├── agenticAI.spec.ts  # Main E2E test file
│   └── pageObjects.ts     # Page object helpers
└── src/__tests__/         # Unit and integration tests
    ├── unit/              # Unit tests
    │   ├── store.test.ts
    │   └── fileUtils.test.ts
    ├── integration/       # Integration tests
    │   ├── ipc.test.ts
    │   ├── aiService.test.ts
    │   └── gitService.test.ts
    └── components/        # Component tests
        ├── ActivityBar.test.tsx
        ├── Sidebar.test.tsx
        ├── Editor.test.tsx
        ├── ChatPanel.test.tsx
        ├── TaskPanel.test.tsx
        └── StatusBar.test.tsx
```

## Running Tests

### Unit and Integration Tests

```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage
```

### E2E Tests

```bash
# Run E2E tests
npm run test:e2e

# Run E2E tests with UI
npm run test:e2e:ui

# Run E2E tests in debug mode
npm run test:e2e:debug
```

### All Tests

```bash
npm run test:all
```

## Test Categories

### Unit Tests

- **store.test.ts**: Tests for Zustand store actions and state management
- **fileUtils.test.ts**: Tests for file tree building and path utilities

### Integration Tests

- **ipc.test.ts**: Tests for IPC communication with Electron backend
- **aiService.test.ts**: Tests for AI service integration
- **gitService.test.ts**: Tests for Git integration using real git repos

### Component Tests

Tests for React components using React Testing Library:
- ActivityBar
- Sidebar
- Editor
- ChatPanel
- TaskPanel
- StatusBar

### E2E Tests

End-to-end tests using Playwright:
- Application launch
- Activity bar navigation
- Sidebar file tree
- Editor functionality
- Chat panel
- Task panel
- Status bar
- Command palette
- Keyboard shortcuts
- Settings panel
- Git panel
- Terminal panel

## Mock Data

The `__fixtures__/mockData.ts` file contains:

- Mock Electron API
- Mock AI responses
- Mock Git status
- Mock file trees
- Mock tasks
- Mock chat messages

## Writing Tests

### Component Tests

```typescript
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ComponentName } from '../../renderer/components/ComponentName';

describe('ComponentName', () => {
  it('should render correctly', () => {
    render(<ComponentName />);
    expect(screen.getByText('Expected Text')).toBeInTheDocument();
  });
});
```

### Store Tests

```typescript
import { useAppStore } from '../../renderer/store/useAppStore';

describe('useAppStore', () => {
  beforeEach(() => {
    useAppStore.setState({ /* reset state */ });
  });

  it('should update state', () => {
    useAppStore.getState().setSomeState('value');
    expect(useAppStore.getState().someState).toBe('value');
  });
});
```

### E2E Tests

```typescript
import { test, expect } from '@playwright/test';

test('should display app', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.app-container')).toBeVisible();
});
```

## Coverage Goals

- Statements: 50%
- Branches: 40%
- Functions: 50%
- Lines: 50%

## CI Integration

Tests are designed to run headlessly for CI environments. E2E tests automatically retry failed tests in CI.
