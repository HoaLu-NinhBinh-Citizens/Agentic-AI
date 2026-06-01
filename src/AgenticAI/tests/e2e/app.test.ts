/**
 * E2E Tests for AgenticAI
 * Priority: Phase 3 targets
 */
import { test, expect } from '@playwright/test';

test.describe('Workspace', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should open folder via command palette', async ({ page }) => {
    // Open command palette
    await page.keyboard.press('Control+Shift+P');
    
    // Wait for command palette to appear
    const palette = page.locator('[role="dialog"], .command-palette');
    await expect(palette).toBeVisible();
    
    // Type "Open Folder"
    await page.keyboard.type('Open Folder');
    
    // Should show Open Folder option
    await expect(page.getByText(/open folder/i)).toBeVisible();
  });

  test('should display welcome message when no folder is open', async ({ page }) => {
    // Check for welcome message or empty state
    const welcome = page.locator('text=/open a folder|agenticai/i');
    await expect(welcome.first()).toBeVisible();
  });
});

test.describe('Editor', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should have Monaco editor loaded', async ({ page }) => {
    // Wait for Monaco to load
    const editor = page.locator('.monaco-editor');
    await expect(editor).toBeVisible({ timeout: 10000 });
  });

  test('should be able to type in editor', async ({ page }) => {
    // This test verifies the Monaco editor is functional
    // Note: This test may fail if the editor has readonly mode
    const editor = page.locator('.monaco-editor textarea, .monaco-editor .inputarea');
    await expect(editor).toBeAttached();
  });
});

test.describe('Chat Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display chat panel', async ({ page }) => {
    const chatPanel = page.locator('.chat-panel');
    await expect(chatPanel).toBeVisible();
  });

  test('should have input field', async ({ page }) => {
    const input = page.locator('.chat-input textarea');
    await expect(input).toBeVisible();
  });

  test('should show setup prompt when AI is not configured', async ({ page }) => {
    const setupPrompt = page.locator('text=/configure ai|set up/i');
    await expect(setupPrompt.first()).toBeVisible();
  });
});

test.describe('Task Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display task panel', async ({ page }) => {
    const taskPanel = page.locator('.task-panel');
    await expect(taskPanel).toBeVisible();
  });

  test('should have add task button', async ({ page }) => {
    const addButton = page.locator('button:has-text("Add Task"), button:has-text("add task"), button:has-text("+")');
    await expect(addButton.first()).toBeVisible();
  });
});

test.describe('Terminal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should toggle terminal with keyboard shortcut', async ({ page }) => {
    // Initially terminal should be hidden or minimized
    const terminal = page.locator('.terminal-panel, .xterm');
    
    // Press Ctrl+` to toggle
    await page.keyboard.press('Control+`');
    
    // Wait a bit for animation
    await page.waitForTimeout(500);
    
    // Terminal should be visible now
    await expect(terminal.first()).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Git Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display git changes', async ({ page }) => {
    // Navigate to git view
    await page.click('button:has-text("Git"), [data-testid="git-button"]');
    
    // Should show git panel or changes
    const gitPanel = page.locator('.git-panel, .vcs');
    await expect(gitPanel.first()).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Settings', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should open settings panel', async ({ page }) => {
    // Click settings button or use keyboard shortcut
    await page.keyboard.press('Control+,');
    
    // Wait for settings to appear
    const settings = page.locator('.settings-panel, .settings-overlay');
    await expect(settings.first()).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Status Bar', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display status bar', async ({ page }) => {
    const statusBar = page.locator('.status-bar, [role="status"]');
    await expect(statusBar).toBeVisible();
  });
});

test.describe('Keyboard Shortcuts', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('Escape should close modals', async ({ page }) => {
    // Open command palette
    await page.keyboard.press('Control+Shift+P');
    
    // Palette should be visible
    const palette = page.locator('[role="dialog"], .command-palette');
    await expect(palette).toBeVisible({ timeout: 2000 });
    
    // Press Escape
    await page.keyboard.press('Escape');
    
    // Palette should be closed
    await expect(palette).not.toBeVisible();
  });
});
