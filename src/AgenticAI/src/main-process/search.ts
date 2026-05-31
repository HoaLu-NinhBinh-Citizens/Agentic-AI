import { spawn } from 'child_process';

export interface SearchResult {
  file: string;
  line: number;
  column: number;
  match: string;
  context: string;
}

export interface SearchOptions {
  query: string;
  path: string;
  caseSensitive?: boolean;
  wholeWord?: boolean;
  regex?: boolean;
  include?: string[];
  exclude?: string[];
  maxResults?: number;
}

class SearchEngine {
  async search(options: SearchOptions): Promise<SearchResult[]> {
    const args: string[] = [
      '--vimgrep',
      '--smart-case',
    ];

    if (options.caseSensitive) {
      args.push('--case-sensitive');
    }

    if (options.wholeWord) {
      args.push('--word-regexp');
    }

    if (options.regex) {
      args.push('--regex');
    }

    if (options.include) {
      for (const pattern of options.include) {
        args.push('--glob', pattern);
      }
    }

    if (options.exclude) {
      for (const pattern of options.exclude) {
        args.push('--glob', `!${pattern}`);
      }
    } else {
      args.push('--glob', '!node_modules');
      args.push('--glob', '!.git');
      args.push('--glob', '!*.pyc');
    }

    if (options.maxResults) {
      args.push('--max-count', options.maxResults.toString());
    }

    args.push(options.query);
    args.push(options.path);

    return new Promise((resolve, reject) => {
      const rg = spawn('rg', args);
      let output = '';

      rg.stdout.on('data', (data) => {
        output += data.toString();
      });

      rg.stderr.on('data', (data) => {
        // ripgrep outputs "No files matched" to stderr sometimes
        console.error('ripgrep:', data.toString());
      });

      rg.on('close', (code) => {
        if (code === 0 || code === 1) {
          // 0 = matches found, 1 = no matches
          resolve(this.parseOutput(output));
        } else {
          reject(new Error(`ripgrep exited with code ${code}`));
        }
      });

      rg.on('error', (err) => {
        reject(err);
      });
    });
  }

  private parseOutput(output: string): SearchResult[] {
    const results: SearchResult[] = [];
    const lines = output.split('\n');

    for (const line of lines) {
      if (!line.trim()) continue;
      
      const match = line.match(/^(.+?):(\d+):(\d+):(.*)$/);
      if (match) {
        results.push({
          file: match[1],
          line: parseInt(match[2], 10),
          column: parseInt(match[3], 10),
          match: match[4],
          context: line,
        });
      }
    }

    return results;
  }

  async searchInFiles(query: string, files: string[]): Promise<Map<string, SearchResult[]>> {
    const results = new Map<string, SearchResult[]>();
    
    for (const file of files) {
      try {
        const fileResults = await this.search({
          query,
          path: file,
          maxResults: 100,
        });
        if (fileResults.length > 0) {
          results.set(file, fileResults);
        }
      } catch {
        // Skip files that fail
      }
    }
    
    return results;
  }
}

export const searchEngine = new SearchEngine();
