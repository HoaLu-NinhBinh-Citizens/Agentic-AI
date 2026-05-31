import simpleGit, { SimpleGit, LogResult, StatusResult } from 'simple-git';

export interface GitInfo {
  isRepo: boolean;
  branch: string;
  branches: string[];
  status: StatusResult | null;
  remotes: string[];
}

export interface CommitInfo {
  hash: string;
  message: string;
  author: string;
  date: string;
}

class GitIntegration {
  private git: SimpleGit | null = null;
  private repoPath: string | null = null;

  async openRepository(path: string): Promise<GitInfo> {
    try {
      this.git = simpleGit(path);
      this.repoPath = path;
      
      const isRepo = await this.git.checkIsRepo();
      if (!isRepo) {
        return { isRepo: false, branch: '', branches: [], status: null, remotes: [] };
      }

      const [branchResult, status, remotes] = await Promise.all([
        this.git.branchLocal(),
        this.git.status(),
        this.git.getRemotes(true),
      ]);

      return {
        isRepo: true,
        branch: branchResult.current,
        branches: branchResult.all,
        status,
        remotes: remotes.map(remote => remote.name),
      };
    } catch (error) {
      console.error('Failed to open git repo:', error);
      return { isRepo: false, branch: '', branches: [], status: null, remotes: [] };
    }
  }

  async getStatus(): Promise<StatusResult | null> {
    if (!this.git) return null;
    try {
      return await this.git.status();
    } catch {
      return null;
    }
  }

  async getLog(limit: number = 50): Promise<CommitInfo[]> {
    if (!this.git) return [];
    try {
      const log: LogResult = await this.git.log({ maxCount: limit });
      return log.all.map(entry => ({
        hash: entry.hash,
        message: entry.message,
        author: entry.author_name,
        date: entry.date,
      }));
    } catch {
      return [];
    }
  }

  async getDiff(file?: string): Promise<string> {
    if (!this.git) return '';
    try {
      if (file) {
        return await this.git.diff([file]);
      }
      return await this.git.diff();
    } catch {
      return '';
    }
  }

  async getFileDiff(filePath: string): Promise<string> {
    if (!this.git) return '';
    try {
      return await this.git.diff(['HEAD', '--', filePath]);
    } catch {
      return '';
    }
  }

  async stage(files: string[]): Promise<boolean> {
    if (!this.git) return false;
    try {
      await this.git.add(files);
      return true;
    } catch {
      return false;
    }
  }

  async commit(message: string): Promise<boolean> {
    if (!this.git) return false;
    try {
      await this.git.commit(message);
      return true;
    } catch {
      return false;
    }
  }

  async checkout(branch: string): Promise<boolean> {
    if (!this.git) return false;
    try {
      await this.git.checkout(branch);
      return true;
    } catch {
      return false;
    }
  }

  async createBranch(name: string, checkout: boolean = true): Promise<boolean> {
    if (!this.git) return false;
    try {
      await this.git.branch([checkout ? '-b' : '-B', name]);
      return true;
    } catch {
      return false;
    }
  }

  async getBranches(): Promise<string[]> {
    if (!this.git) return [];
    try {
      const result = await this.git.branchLocal();
      return result.all;
    } catch {
      return [];
    }
  }

  async pull(): Promise<boolean> {
    if (!this.git) return false;
    try {
      await this.git.pull();
      return true;
    } catch {
      return false;
    }
  }

  async push(): Promise<boolean> {
    if (!this.git) return false;
    try {
      await this.git.push();
      return true;
    } catch {
      return false;
    }
  }
}

export const gitIntegration = new GitIntegration();
