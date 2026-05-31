import { test, expect, Page } from '@playwright/test';

export class AppPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  async goto() {
    await this.page.goto('/');
  }

  getActivityBar() {
    return this.page.locator('.activity-bar');
  }

  getSidebar() {
    return this.page.locator('.sidebar');
  }

  getEditor() {
    return this.page.locator('.editor-area');
  }

  getStatusBar() {
    return this.page.locator('.status-bar');
  }

  getChatPanel() {
    return this.page.locator('.chat-panel');
  }

  getTaskPanel() {
    return this.page.locator('.task-panel');
  }

  async openCommandPalette() {
    await this.page.keyboard.press('Control+Shift+P');
    await expect(this.page.locator('.command-palette')).toBeVisible();
  }

  async closeCommandPalette() {
    await this.page.keyboard.press('Escape');
  }

  async toggleTerminal() {
    await this.page.keyboard.press('Control+`');
  }

  async switchToExplorer() {
    await this.page.locator('[title="Explorer"]').click();
  }

  async switchToSearch() {
    await this.page.locator('[title="Search"]').click();
  }

  async switchToGit() {
    await this.page.locator('[title="Source Control"]').click();
  }

  async switchToTerminal() {
    await this.page.locator('[title="Terminal"]').click();
  }

  async openSettings() {
    await this.page.locator('[title="Settings"]').click();
  }

  async openFolder() {
    await this.page.locator('text=Open Folder').click();
  }
}

export class ChatHelper {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  getInput() {
    return this.page.locator('.chat-input textarea');
  }

  getSendButton() {
    return this.page.locator('.chat-input button').first();
  }

  getClearButton() {
    return this.page.locator('[title="Clear chat"]');
  }

  async sendMessage(message: string) {
    await this.getInput().fill(message);
    await this.getSendButton().click();
  }

  async clearChat() {
    await this.getClearButton().click();
  }

  getMessages() {
    return this.page.locator('.chat-messages .message');
  }

  async waitForResponse() {
    await this.page.waitForSelector('.message.assistant', { timeout: 10000 });
  }
}

export class TaskHelper {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  getNewTaskInput() {
    return this.page.locator('.new-task input');
  }

  getAddButton() {
    return this.page.locator('.new-task button');
  }

  async addTask(title: string) {
    await this.getNewTaskInput().fill(title);
    await this.getNewTaskInput().press('Enter');
  }

  getTaskItems() {
    return this.page.locator('.task-item');
  }

  getTaskByTitle(title: string) {
    return this.page.locator(`.task-item:has-text("${title}")`);
  }

  async toggleTask(title: string) {
    const task = this.getTaskByTitle(title);
    await task.locator('.task-checkbox').click();
  }

  async deleteTask(title: string) {
    const task = this.getTaskByTitle(title);
    await task.locator('.task-delete').click();
  }
}

export class EditorHelper {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  getWelcomeScreen() {
    return this.page.locator('.welcome-screen');
  }

  getOpenFolderButton() {
    return this.page.locator('.open-folder-btn');
  }

  getTabs() {
    return this.page.locator('.editor-tab');
  }

  getActiveTab() {
    return this.page.locator('.editor-tab.active');
  }

  getCloseTabButton() {
    return this.page.locator('.editor-tab .close-tab');
  }

  async openFolder() {
    await this.getOpenFolderButton().click();
  }

  async closeTab(tabText: string) {
    const tab = this.page.locator(`.editor-tab:has-text("${tabText}")`);
    await tab.locator('.close-tab').click();
  }

  async saveFile() {
    await this.page.keyboard.press('Control+s');
  }
}

export class SidebarHelper {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  getOpenFolderButton() {
    return this.page.locator('.open-folder button');
  }

  getFileTree() {
    return this.page.locator('.file-tree');
  }

  getFileTreeItem(name: string) {
    return this.page.locator(`.file-tree-item:has-text("${name}")`);
  }

  async clickFile(name: string) {
    await this.getFileTreeItem(name).click();
  }

  async openFolder(name: string) {
    await this.getFileTreeItem(name).click();
  }

  getNewFileButton() {
    return this.page.locator('[title="New File"]');
  }

  getNewFolderButton() {
    return this.page.locator('[title="New Folder"]');
  }
}

export class GitHelper {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  getGitPanel() {
    return this.page.locator('.git-panel');
  }

  getBranchName() {
    return this.page.locator('.git-branch-name');
  }

  getCommitInput() {
    return this.page.locator('.git-commit-input');
  }

  getCommitButton() {
    return this.page.locator('.git-commit-button');
  }

  getChangesList() {
    return this.page.locator('.git-changes-list');
  }

  async commit(message: string) {
    await this.getCommitInput().fill(message);
    await this.getCommitButton().click();
  }
}
