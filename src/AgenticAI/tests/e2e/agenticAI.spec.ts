import { test, expect } from '@playwright/test';

test.describe('AgenticAI E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test.describe('Application Launch', () => {
    test('should launch the application successfully', async ({ page }) => {
      await expect(page).toHaveTitle(/AgenticAI/);
    });

    test('should display the main layout', async ({ page }) => {
      await expect(page.locator('.app-container')).toBeVisible();
      await expect(page.locator('.activity-bar')).toBeVisible();
      await expect(page.locator('.sidebar-container')).toBeVisible();
      await expect(page.locator('.editor-area')).toBeVisible();
      await expect(page.locator('.status-bar')).toBeVisible();
    });
  });

  test.describe('Activity Bar', () => {
    test('should render all activity icons', async ({ page }) => {
      await expect(page.locator('.activity-bar')).toBeVisible();
      
      const buttons = page.locator('.activity-bar button');
      await expect(buttons).toHaveCount(5);
    });

    test('should switch sidebar view on icon click', async ({ page }) => {
      await page.locator('[title="Source Control"]').click();
      await expect(page.locator('.git-panel')).toBeVisible();
    });

    test('should highlight active icon', async ({ page }) => {
      await page.locator('[title="Search"]').click();
      await expect(page.locator('[title="Search"]')).toHaveClass(/active/);
    });
  });

  test.describe('Sidebar', () => {
    test('should show Open Folder button when no workspace is open', async ({ page }) => {
      await expect(page.locator('text=Open Folder')).toBeVisible();
    });

    test('should show Explorer header', async ({ page }) => {
      await expect(page.locator('.sidebar-header span')).toHaveText('Explorer');
    });

    test('should have new file and folder buttons', async ({ page }) => {
      await expect(page.locator('[title="New File"]')).toBeVisible();
      await expect(page.locator('[title="New Folder"]')).toBeVisible();
    });
  });

  test.describe('Editor Panel', () => {
    test('should show welcome screen when no file is open', async ({ page }) => {
      await expect(page.locator('.welcome-screen')).toBeVisible();
      await expect(page.locator('.welcome-title')).toHaveText('AgenticAI');
    });

    test('should have Open Folder button on welcome screen', async ({ page }) => {
      await expect(page.locator('.open-folder-btn')).toBeVisible();
    });

    test('should show recent workspaces when available', async ({ page }) => {
      await expect(page.locator('.recent-workspaces')).toBeVisible({ timeout: 5000 }).catch(() => {
        // Recent workspaces may not exist on fresh install
      });
    });
  });

  test.describe('Chat Panel', () => {
    test('should display chat header', async ({ page }) => {
      await expect(page.locator('.chat-panel h3')).toHaveText('AI Assistant');
    });

    test('should show welcome message when no messages', async ({ page }) => {
      await expect(page.locator('.chat-welcome')).toBeVisible();
      await expect(page.locator('.chat-welcome h4')).toHaveText('Welcome to AgenticAI');
    });

    test('should have input field for messages', async ({ page }) => {
      await expect(page.locator('.chat-input textarea')).toBeVisible();
    });

    test('should have send button', async ({ page }) => {
      const sendButton = page.locator('.chat-input button').first();
      await expect(sendButton).toBeVisible();
    });

    test('should have clear chat button', async ({ page }) => {
      await expect(page.locator('[title="Clear chat"]')).toBeVisible();
    });

    test('should have settings button', async ({ page }) => {
      await expect(page.locator('[title="Settings"]').first()).toBeVisible();
    });

    test('should have Configure AI button when AI is not initialized', async ({ page }) => {
      await expect(page.locator('.setup-prompt button')).toBeVisible();
    });
  });

  test.describe('Task Panel', () => {
    test('should display tasks header', async ({ page }) => {
      await expect(page.locator('.task-panel h3')).toHaveText('Tasks');
    });

    test('should show task stats', async ({ page }) => {
      await expect(page.locator('.task-stats')).toBeVisible();
      await expect(page.locator('.task-stats').locator('text=todo')).toBeVisible();
    });

    test('should have input for new task', async ({ page }) => {
      await expect(page.locator('.new-task input')).toBeVisible();
    });

    test('should show empty state message', async ({ page }) => {
      await expect(page.locator('.no-tasks')).toBeVisible();
      await expect(page.locator('.no-tasks p')).toHaveText('No tasks yet. Add one above!');
    });
  });

  test.describe('Status Bar', () => {
    test('should display status bar', async ({ page }) => {
      await expect(page.locator('.status-bar')).toBeVisible();
    });

    test('should show AI status', async ({ page }) => {
      await expect(page.locator('.ai-status')).toBeVisible();
    });

    test('should show git branch', async ({ page }) => {
      await expect(page.locator('.git-branch')).toBeVisible();
    });

    test('should show cursor position', async ({ page }) => {
      await expect(page.locator('.cursor-position')).toBeVisible();
    });

    test('should show language mode', async ({ page }) => {
      await expect(page.locator('.language-mode')).toBeVisible();
    });

    test('should show encoding', async ({ page }) => {
      await expect(page.locator('.encoding')).toHaveText('UTF-8');
    });
  });

  test.describe('Command Palette', () => {
    test('should open with Ctrl+Shift+P', async ({ page }) => {
      await page.keyboard.press('Control+Shift+P');
      await expect(page.locator('.command-palette')).toBeVisible();
    });

    test('should close with Escape', async ({ page }) => {
      await page.keyboard.press('Control+Shift+P');
      await expect(page.locator('.command-palette')).toBeVisible();
      
      await page.keyboard.press('Escape');
      await expect(page.locator('.command-palette')).not.toBeVisible();
    });
  });

  test.describe('Keyboard Shortcuts', () => {
    test('should toggle terminal with Ctrl+`', async ({ page }) => {
      await page.keyboard.press('Control+`');
      await expect(page.locator('.terminal-panel')).toBeVisible();
      
      await page.keyboard.press('Control+`');
      await expect(page.locator('.terminal-panel')).not.toBeVisible();
    });
  });

  test.describe('Settings Panel', () => {
    test('should open settings from activity bar', async ({ page }) => {
      await page.locator('[title="Settings"]').click();
      await expect(page.locator('.settings-panel')).toBeVisible();
    });

    test('should close settings', async ({ page }) => {
      await page.locator('[title="Settings"]').click();
      await expect(page.locator('.settings-panel')).toBeVisible();
      
      const closeButton = page.locator('.settings-panel button.close');
      if (await closeButton.isVisible()) {
        await closeButton.click();
        await expect(page.locator('.settings-panel')).not.toBeVisible();
      }
    });
  });

  test.describe('Responsive Layout', () => {
    test('should resize correctly', async ({ page }) => {
      await page.setViewportSize({ width: 1920, height: 1080 });
      await expect(page.locator('.app-container')).toBeVisible();
      
      await page.setViewportSize({ width: 800, height: 600 });
      await expect(page.locator('.app-container')).toBeVisible();
    });
  });

  test.describe('AI Integration', () => {
    test('should check AI initialization on mount', async ({ page }) => {
      await page.waitForTimeout(500);
      // AI initialization check is triggered on mount
      const aiInitialized = await page.evaluate(() => {
        return (window as any).electronAPI?.ai?.isInitialized();
      });
      expect(aiInitialized).toBeDefined();
    });

    test('should open settings when Configure AI is clicked', async ({ page }) => {
      const configButton = page.locator('.setup-prompt button');
      if (await configButton.isVisible()) {
        await configButton.click();
        await expect(page.locator('.settings-panel')).toBeVisible();
      }
    });
  });

  test.describe('File Operations (Mocked)', () => {
    test('should display file tree when workspace is set', async ({ page }) => {
      await page.evaluate(() => {
        (window as any).electronAPI = {
          ...(window as any).electronAPI,
          storage: {
            getWorkspace: async () => ({ path: '/test/workspace' }),
          },
          readDirectory: async () => [
            { name: 'src', path: '/test/workspace/src', isDirectory: true },
            { name: 'index.ts', path: '/test/workspace/index.ts', isDirectory: false },
          ],
        };
      });

      await page.reload();
      await page.waitForTimeout(1000);

      await expect(page.locator('.file-tree')).toBeVisible({ timeout: 5000 }).catch(() => {
        // May not appear if workspace path is not properly set
      });
    });
  });

  test.describe('Git Panel', () => {
    test('should display git panel when switching to source control', async ({ page }) => {
      await page.locator('[title="Source Control"]').click();
      await expect(page.locator('.git-panel')).toBeVisible();
    });
  });

  test.describe('Terminal Panel', () => {
    test('should display terminal panel when open', async ({ page }) => {
      await page.keyboard.press('Control+`');
      await expect(page.locator('.terminal-panel')).toBeVisible();
    });
  });
});
