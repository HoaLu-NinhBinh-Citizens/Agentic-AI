import * as fs from 'fs';
import * as path from 'path';

export interface Fix {
  file: string;
  original: string;
  replacement: string;
  explanation: string;
}

export interface FixResult {
  success: boolean;
  applied: Fix[];
  failed: Fix[];
  errors: string[];
}

export interface DiffLine {
  type: 'add' | 'remove' | 'context';
  content: string;
  lineNumber?: number;
}

export interface DiffResult {
  original: string;
  replacement: string;
  hunks: DiffHunk[];
}

export interface DiffHunk {
  originalStart: number;
  originalCount: number;
  replacementStart: number;
  replacementCount: number;
  lines: DiffLine[];
}

export class FixEngine {
  /**
   * Apply multiple fixes to files
   */
  async applyFixes(fixes: Fix[]): Promise<FixResult> {
    const result: FixResult = {
      success: true,
      applied: [],
      failed: [],
      errors: [],
    };

    for (const fix of fixes) {
      try {
        const applyResult = await this.applyFix(fix);
        if (applyResult.success) {
          result.applied.push(fix);
        } else {
          result.failed.push(fix);
          result.errors.push(applyResult.error || 'Unknown error');
          result.success = false;
        }
      } catch (error) {
        result.failed.push(fix);
        result.errors.push(`Failed to apply fix: ${error}`);
        result.success = false;
      }
    }

    return result;
  }

  /**
   * Apply a single fix to a file
   */
  async applyFix(fix: Fix): Promise<{ success: boolean; error?: string }> {
    try {
      // Check if file exists
      if (!fs.existsSync(fix.file)) {
        return { success: false, error: `File not found: ${fix.file}` };
      }

      const content = fs.readFileSync(fix.file, 'utf-8');

      // Check if original code exists
      if (!content.includes(fix.original)) {
        // Try to find approximate match
        const approximateMatch = this.findApproximateMatch(content, fix.original);
        if (!approximateMatch) {
          return { success: false, error: 'Could not find original code in file' };
        }
      }

      const newContent = content.replace(fix.original, fix.replacement);
      fs.writeFileSync(fix.file, newContent, 'utf-8');
      return { success: true };
    } catch (error) {
      return { success: false, error: `Failed to apply fix: ${error}` };
    }
  }

  /**
   * Find approximate match when exact match fails
   */
  private findApproximateMatch(content: string, original: string): string | null {
    const lines = original.split('\n');
    if (lines.length < 2) return null;

    // Try to find the first significant line
    const significantLine = lines.find(line => {
      const trimmed = line.trim();
      return trimmed.length > 5 && !trimmed.startsWith('//') && !trimmed.startsWith('*');
    });

    if (!significantLine) return null;

    // Check if this line exists in the content
    if (content.includes(significantLine.trim())) {
      return significantLine.trim();
    }

    return null;
  }

  /**
   * Generate a unified diff for display
   */
  generateDiff(original: string, replacement: string, context: number = 3): DiffResult {
    const originalLines = original.split('\n');
    const replacementLines = replacement.split('\n');
    const hunks: DiffHunk[] = [];

    let i = 0;
    let j = 0;
    let currentHunk: DiffHunk | null = null;
    let hunkStartI = 0;
    let hunkStartJ = 0;

    while (i < originalLines.length || j < replacementLines.length) {
      const origLine = originalLines[i];
      const replLine = replacementLines[j];

      const isSame = origLine === replLine;
      const isAdd = j < replacementLines.length && (i >= originalLines.length || !isSame);
      const isRemove = i < originalLines.length && (j >= replacementLines.length || !isSame);

      if (isAdd || isRemove) {
        if (!currentHunk) {
          currentHunk = {
            originalStart: Math.max(1, i - context + 1),
            originalCount: 0,
            replacementStart: Math.max(1, j - context + 1),
            replacementCount: 0,
            lines: [],
          };
          hunkStartI = i;
          hunkStartJ = j;
        }

        if (isRemove) {
          currentHunk.lines.push({ type: 'remove', content: origLine });
          currentHunk.originalCount++;
          i++;
        } else if (isAdd) {
          currentHunk.lines.push({ type: 'add', content: replLine });
          currentHunk.replacementCount++;
          j++;
        }
      } else {
        if (currentHunk) {
          // Check if we should continue or close the hunk
          const linesInHunk = currentHunk.originalCount + currentHunk.replacementCount;
          if (linesInHunk > 0) {
            hunks.push(currentHunk);
          }
          currentHunk = null;
        }
        i++;
        j++;
      }
    }

    if (currentHunk) {
      hunks.push(currentHunk);
    }

    return { original, replacement, hunks };
  }

  /**
   * Format diff as unified diff string
   */
  formatUnifiedDiff(filePath: string, original: string, replacement: string): string {
    const diff = this.generateDiff(original, replacement);
    const lines: string[] = [];
    const fileName = path.basename(filePath);

    lines.push(`--- a/${fileName}`);
    lines.push(`+++ b/${fileName}`);

    for (const hunk of diff.hunks) {
      lines.push(`@@ -${hunk.originalStart},${hunk.originalCount} +${hunk.replacementStart},${hunk.replacementCount} @@`);

      for (const line of hunk.lines) {
        if (line.type === 'add') {
          lines.push(`+ ${line.content}`);
        } else if (line.type === 'remove') {
          lines.push(`- ${line.content}`);
        } else {
          lines.push(`  ${line.content}`);
        }
      }
    }

    return lines.join('\n');
  }

  /**
   * Preview what changes would be made
   */
  previewFixes(fixes: Fix[]): Map<string, { original: string; replacement: string }> {
    const previews = new Map<string, { original: string; replacement: string }>();

    for (const fix of fixes) {
      if (fs.existsSync(fix.file)) {
        const content = fs.readFileSync(fix.file, 'utf-8');
        const replacement = content.replace(fix.original, fix.replacement);
        previews.set(fix.file, { original: content, replacement });
      }
    }

    return previews;
  }

  /**
   * Create backup of files before applying fixes
   */
  async createBackups(fixes: Fix[]): Promise<Map<string, string>> {
    const backups = new Map<string, string>();

    for (const fix of fixes) {
      if (fs.existsSync(fix.file) && !backups.has(fix.file)) {
        const content = fs.readFileSync(fix.file, 'utf-8');
        const backupPath = `${fix.file}.backup`;
        fs.writeFileSync(backupPath, content, 'utf-8');
        backups.set(fix.file, backupPath);
      }
    }

    return backups;
  }

  /**
   * Restore files from backups
   */
  async restoreFromBackups(backups: Map<string, string>): Promise<void> {
    for (const [originalPath, backupPath] of backups) {
      if (fs.existsSync(backupPath)) {
        const content = fs.readFileSync(backupPath, 'utf-8');
        fs.writeFileSync(originalPath, content, 'utf-8');
        fs.unlinkSync(backupPath);
      }
    }
  }
}

export const fixEngine = new FixEngine();
