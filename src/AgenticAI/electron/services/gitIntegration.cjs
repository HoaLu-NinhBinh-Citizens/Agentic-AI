const simpleGit = require('simple-git');

class GitIntegration {
  constructor() {
    this.git = null;
    this.repoPath = null;
  }

  async openRepository(path) {
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

  async getStatus() {
    if (!this.git) return null;
    try {
      return await this.git.status();
    } catch {
      return null;
    }
  }

  async getLog(limit = 50) {
    if (!this.git) return [];
    try {
      const log = await this.git.log({ maxCount: limit });
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

  async getDiff(file) {
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

  async getFileDiff(filePath) {
    if (!this.git) return '';
    try {
      return await this.git.diff(['HEAD', '--', filePath]);
    } catch {
      return '';
    }
  }

  async stage(files) {
    if (!this.git) return false;
    try {
      await this.git.add(files);
      return true;
    } catch {
      return false;
    }
  }

  async commit(message) {
    if (!this.git) return false;
    try {
      await this.git.commit(message);
      return true;
    } catch {
      return false;
    }
  }

  async checkout(branch) {
    if (!this.git) return false;
    try {
      await this.git.checkout(branch);
      return true;
    } catch {
      return false;
    }
  }

  async createBranch(name, checkout = true) {
    if (!this.git) return false;
    try {
      await this.git.branch([checkout ? '-b' : '-B', name]);
      return true;
    } catch {
      return false;
    }
  }
}

const gitIntegration = new GitIntegration();
module.exports = { gitIntegration };
