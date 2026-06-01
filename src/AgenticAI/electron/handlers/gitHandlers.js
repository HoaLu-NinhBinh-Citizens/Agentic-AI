/**
 * IPC Handler: Git Integration
 * Handles all Git operations with validation
 */
const { z } = require('zod');

// Validation schemas
const gitInfoSchema = z.string().min(1);
const gitLogSchema = z.object({
  workspacePath: z.string().min(1),
  limit: z.number().optional(),
});
const gitStageSchema = z.array(z.string());
const gitUnstageSchema = z.array(z.string());
const gitCommitSchema = z.object({
  workspacePath: z.string().min(1),
  message: z.string().min(1),
});
const gitCheckoutSchema = z.object({
  workspacePath: z.string().min(1),
  branch: z.string().min(1),
});
const gitBranchSchema = z.object({
  workspacePath: z.string().min(1),
  name: z.string().min(1),
  create: z.boolean().optional(),
});
const gitDiffSchema = z.object({
  workspacePath: z.string().min(1),
  file: z.string().optional(),
});
const gitDiscardSchema = z.object({
  workspacePath: z.string().min(1),
  files: z.array(z.string()),
});

// Error handler helper
function handleError(error, context) {
  console.error(`[Git Handler] ${context}:`, error);
  return { error: error.message };
}

// IPC Handlers
function registerGitHandlers(ipcMain, { gitIntegration }) {
  // Get Git Info
  ipcMain.handle('git:info', async (_, workspacePath) => {
    try {
      const validated = gitInfoSchema.parse(workspacePath);
      if (!gitIntegration) return { error: 'Git integration not available' };
      return await gitIntegration.info(validated);
    } catch (error) {
      return handleError(error, 'gitInfo');
    }
  });

  // Get Git Status
  ipcMain.handle('git:status', async () => {
    try {
      if (!gitIntegration) return [];
      return await gitIntegration.status();
    } catch (error) {
      return handleError(error, 'gitStatus');
    }
  });

  // Get Git Log
  ipcMain.handle('git:log', async (_, options) => {
    try {
      const validated = gitLogSchema.parse(options);
      if (!gitIntegration) return [];
      return await gitIntegration.log(validated.workspacePath, validated.limit);
    } catch (error) {
      return handleError(error, 'gitLog');
    }
  });

  // Stage Files
  ipcMain.handle('git:stage', async (_, options) => {
    try {
      const validated = gitStageSchema.parse(options.files);
      if (!gitIntegration) return { error: 'Git integration not available' };
      await gitIntegration.add(validated);
      return { success: true };
    } catch (error) {
      return handleError(error, 'gitStage');
    }
  });

  // Unstage Files
  ipcMain.handle('git:unstage', async (_, options) => {
    try {
      const validated = gitUnstageSchema.parse(options.files);
      if (!gitIntegration) return { error: 'Git integration not available' };
      await gitIntegration.unstage(validated);
      return { success: true };
    } catch (error) {
      return handleError(error, 'gitUnstage');
    }
  });

  // Commit
  ipcMain.handle('git:commit', async (_, options) => {
    try {
      const validated = gitCommitSchema.parse(options);
      if (!gitIntegration) return { error: 'Git integration not available' };
      await gitIntegration.commit(validated.workspacePath, validated.message);
      return { success: true };
    } catch (error) {
      return handleError(error, 'gitCommit');
    }
  });

  // Checkout
  ipcMain.handle('git:checkout', async (_, options) => {
    try {
      const validated = gitCheckoutSchema.parse(options);
      if (!gitIntegration) return { error: 'Git integration not available' };
      await gitIntegration.checkout(validated.workspacePath, validated.branch);
      return { success: true };
    } catch (error) {
      return handleError(error, 'gitCheckout');
    }
  });

  // Branch
  ipcMain.handle('git:branch', async (_, options) => {
    try {
      const validated = gitBranchSchema.parse(options);
      if (!gitIntegration) return [];
      return await gitIntegration.branch(validated.workspacePath, validated.name, validated.create);
    } catch (error) {
      return handleError(error, 'gitBranch');
    }
  });

  // Diff
  ipcMain.handle('git:diff', async (_, options) => {
    try {
      const validated = gitDiffSchema.parse(options);
      if (!gitIntegration) return '';
      return await gitIntegration.diff(validated.workspacePath, validated.file);
    } catch (error) {
      return handleError(error, 'gitDiff');
    }
  });

  // Discard
  ipcMain.handle('git:discard', async (_, options) => {
    try {
      const validated = gitDiscardSchema.parse(options);
      if (!gitIntegration) return { error: 'Git integration not available' };
      await gitIntegration.discard(validated.workspacePath, validated.files);
      return { success: true };
    } catch (error) {
      return handleError(error, 'gitDiscard');
    }
  });

  console.log('[Git Handler] Registered all Git handlers with Zod validation');
}

module.exports = { registerGitHandlers };
