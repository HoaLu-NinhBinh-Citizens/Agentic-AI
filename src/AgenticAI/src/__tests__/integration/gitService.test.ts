import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

describe('Git Service Integration', () => {
  let testDir: string;
  let gitDir: string;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  const execGit = (args: string[]): Promise<{ stdout: string; stderr: string }> => {
    return new Promise((resolve, reject) => {
      const { execSync } = require('child_process');
      try {
        const stdout = execSync(`git ${args.join(' ')}`, { 
          cwd: testDir,
          encoding: 'utf8',
          stdio: ['pipe', 'pipe', 'pipe']
        });
        resolve({ stdout, stderr: '' });
      } catch (error: unknown) {
        const err = error as { stderr?: string };
        resolve({ stdout: '', stderr: err.stderr || '' });
      }
    });
  };

  const initGitRepo = async () => {
    fs.mkdirSync(testDir, { recursive: true });
    
    fs.writeFileSync(path.join(testDir, 'README.md'), '# Test Repository');
    fs.writeFileSync(path.join(testDir, 'index.ts'), 'const x = 1;');
    
    require('child_process').execSync('git init', { cwd: testDir });
    require('child_process').execSync('git config user.email "test@test.com"', { cwd: testDir });
    require('child_process').execSync('git config user.name "Test User"', { cwd: testDir });
    require('child_process').execSync('git add .', { cwd: testDir });
    require('child_process').execSync('git commit -m "Initial commit"', { cwd: testDir });
  };

  beforeAll(async () => {
    testDir = fs.mkdtempSync(path.join(os.tmpdir(), 'git-test-'));
    await initGitRepo();
    gitDir = path.join(testDir, '.git');
  });

  afterAll(() => {
    try {
      fs.rmSync(testDir, { recursive: true, force: true });
    } catch {
      // Ignore cleanup errors
    }
  });

  describe('Git Status', () => {
    it('should get status of a git repository', async () => {
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      const status = await git.status();
      
      expect(status).toHaveProperty('current');
      expect(status).toHaveProperty('tracking');
      expect(status).toHaveProperty('files');
    });

    it('should return modified files', async () => {
      fs.writeFileSync(path.join(testDir, 'index.ts'), 'const x = 2;');
      
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      const status = await git.status();
      
      expect(status.modified).toContain('index.ts');
    });

    it('should return staged files', async () => {
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      
      fs.writeFileSync(path.join(testDir, 'index.ts'), 'const x = 3;');
      await git.add('index.ts');
      
      const status = await git.status();
      expect(status.staged).toContain('index.ts');
    });

    it('should return untracked files', async () => {
      fs.writeFileSync(path.join(testDir, 'newfile.ts'), 'const y = 1;');
      
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      const status = await git.status();
      
      expect(status.not_added).toContain('newfile.ts');
    });
  });

  describe('Git Branch Operations', () => {
    it('should get current branch', async () => {
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      const branch = await git.branchLocal();
      
      expect(branch.current).toBeTruthy();
    });

    it('should list all branches', async () => {
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      const branch = await git.branchLocal();
      
      expect(Array.isArray(branch.all)).toBe(true);
    });

    it('should create new branch', async () => {
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      
      await git.checkoutLocalBranch('feature/test');
      
      const branch = await git.branchLocal();
      expect(branch.all).toContain('feature/test');
    });

    it('should checkout branch', async () => {
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      
      await git.checkoutLocalBranch('feature/branch');
      const branch = await git.branchLocal();
      const currentBranch = branch.current;
      await git.checkout(currentBranch);
      
      const newBranch = await git.branchLocal();
      expect(newBranch.current).toBeTruthy();
    });
  });

  describe('Git Commit Operations', () => {
    it('should commit staged changes', async () => {
      fs.writeFileSync(path.join(testDir, 'index.ts'), 'const x = 4;');
      
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      
      await git.add('index.ts');
      await git.commit('Update index.ts');
      
      const log = await git.log();
      expect(log.latest?.message).toBe('Update index.ts');
    });
  });

  describe('Git Stage/Unstage Operations', () => {
    it('should stage file', async () => {
      fs.writeFileSync(path.join(testDir, 'index.ts'), 'const x = 5;');
      
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      
      await git.add(['index.ts']);
      
      const status = await git.status();
      expect(status.staged).toContain('index.ts');
    });

    it('should unstage file', async () => {
      fs.writeFileSync(path.join(testDir, 'index.ts'), 'const x = 6;');
      
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      
      await git.add(['index.ts']);
      await git.reset(['HEAD', '--', 'index.ts']);
      
      const status = await git.status();
      expect(status.modified).toContain('index.ts');
    });
  });

  describe('Git Diff Operations', () => {
    it('should get working directory diff', async () => {
      fs.writeFileSync(path.join(testDir, 'index.ts'), 'const x = 7;');
      
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      
      const diff = await git.diff();
      expect(diff).toContain('const x = 7');
    });

    it('should get staged diff', async () => {
      fs.writeFileSync(path.join(testDir, 'index.ts'), 'const x = 8;');
      
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      
      await git.add(['index.ts']);
      
      const diff = await git.diff(['--staged']);
      expect(diff).toContain('const x = 8');
    });
  });

  describe('Git Discard Operations', () => {
    it('should discard changes to file', async () => {
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      
      // Reset file to known state first
      fs.writeFileSync(path.join(testDir, 'index.ts'), 'const x = 1;');
      await git.add(['index.ts']);
      await git.commit('Reset file');
      
      // Make changes
      fs.writeFileSync(path.join(testDir, 'index.ts'), 'const x = 999;');
      
      await git.checkout(['--', 'index.ts']);
      
      const content = fs.readFileSync(path.join(testDir, 'index.ts'), 'utf8');
      expect(content).toBe('const x = 1;');
    });
  });

  describe('Git Log Operations', () => {
    it('should get commit history', async () => {
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      
      const log = await git.log();
      
      expect(Array.isArray(log.all)).toBe(true);
      expect(log.all.length).toBeGreaterThan(0);
    });

    it('should limit log entries', async () => {
      const simpleGit = require('simple-git');
      const git = simpleGit(testDir);
      
      const log = await git.log({ maxCount: 1 });
      
      expect(log.all.length).toBeLessThanOrEqual(1);
    });
  });
});
