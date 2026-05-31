import { useState, useCallback } from 'react';
import { CodeIssue, CodeReviewResult, Fix } from '../../shared/types';

interface UseCodeReviewOptions {
  onIssueFound?: (issue: CodeIssue) => void;
  onReviewComplete?: (result: CodeReviewResult) => void;
  onFixApplied?: (fix: Fix, success: boolean) => void;
}

export interface CodeReviewState {
  isAnalyzing: boolean;
  isReviewing: boolean;
  issues: CodeIssue[];
  selectedIssue: CodeIssue | null;
  error: string | null;
}

export function useCodeReview(options: UseCodeReviewOptions = {}) {
  const [state, setState] = useState<CodeReviewState>({
    isAnalyzing: false,
    isReviewing: false,
    issues: [],
    selectedIssue: null,
    error: null,
  });

  const analyzeFile = useCallback(async (filePath: string, content: string) => {
    const codeAPI = (window.electronAPI as any)?.code;
    if (!codeAPI) {
      setState(prev => ({ ...prev, error: 'Code analysis not available' }));
      return null;
    }

    setState(prev => ({ ...prev, isAnalyzing: true, error: null }));

    try {
      const result = await codeAPI.analyze(filePath, content);

      if (result.success) {
        setState(prev => ({
          ...prev,
          isAnalyzing: false,
          issues: result.issues || [],
        }));
        return result;
      } else {
        setState(prev => ({
          ...prev,
          isAnalyzing: false,
          error: result.error || 'Analysis failed',
        }));
        return null;
      }
    } catch (error) {
      setState(prev => ({
        ...prev,
        isAnalyzing: false,
        error: error instanceof Error ? error.message : 'Analysis failed',
      }));
      return null;
    }
  }, []);

  const reviewFile = useCallback(async (filePath: string, content: string) => {
    const codeAPI = (window.electronAPI as any)?.code;
    if (!codeAPI) {
      setState(prev => ({ ...prev, error: 'Code analysis not available' }));
      return null;
    }

    setState(prev => ({ ...prev, isReviewing: true, error: null, issues: [] }));

    try {
      const result = await codeAPI.review(filePath, content);

      if (result.success) {
        const allIssues = result.allIssues || [];
        setState(prev => ({
          ...prev,
          isReviewing: false,
          issues: allIssues,
        }));

        options.onReviewComplete?.({
          filePath: result.filePath || filePath,
          analysis: result.analysis || { functions: [], imports: [], exports: [], complexity: 0, issues: [] },
          securityIssues: result.securityIssues || [],
          totalIssues: result.totalIssues || 0,
          errorCount: result.errorCount || 0,
          warningCount: result.warningCount || 0,
          infoCount: result.infoCount || 0,
        });

        // Notify about each issue
        allIssues.forEach((issue: CodeIssue) => {
          options.onIssueFound?.(issue);
        });

        return result;
      } else {
        setState(prev => ({
          ...prev,
          isReviewing: false,
          error: result.error || 'Review failed',
        }));
        return null;
      }
    } catch (error) {
      setState(prev => ({
        ...prev,
        isReviewing: false,
        error: error instanceof Error ? error.message : 'Review failed',
      }));
      return null;
    }
  }, [options]);

  const applyFix = useCallback(async (issue: CodeIssue) => {
    if (!issue.fix) {
      setState(prev => ({ ...prev, error: 'No fix available for this issue' }));
      return false;
    }

    const codeAPI = (window.electronAPI as any)?.code;
    if (!codeAPI) {
      setState(prev => ({ ...prev, error: 'Code analysis not available' }));
      return false;
    }

    const fix: Fix = {
      file: '',
      original: issue.fix.original,
      replacement: issue.fix.replacement,
      explanation: issue.fix.description,
    };

    try {
      const result = await codeAPI.applyFix(fix);

      if (result.success) {
        // Remove fixed issue from list
        setState(prev => ({
          ...prev,
          issues: prev.issues.filter(i => i.id !== issue.id),
        }));
        options.onFixApplied?.(fix, true);
        return true;
      } else {
        setState(prev => ({ ...prev, error: result.error || 'Failed to apply fix' }));
        options.onFixApplied?.(fix, false);
        return false;
      }
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to apply fix',
      }));
      options.onFixApplied?.(fix, false);
      return false;
    }
  }, [options]);

  const applyMultipleFixes = useCallback(async (issues: CodeIssue[]) => {
    const fixes = issues
      .filter(issue => issue.fix)
      .map(issue => ({
        file: '',
        original: issue.fix!.original,
        replacement: issue.fix!.replacement,
        explanation: issue.fix!.description,
      } as Fix));

    if (fixes.length === 0) {
      setState(prev => ({ ...prev, error: 'No fixes available' }));
      return false;
    }

    const codeAPI = (window.electronAPI as any)?.code;
    if (!codeAPI) {
      setState(prev => ({ ...prev, error: 'Code analysis not available' }));
      return false;
    }

    try {
      const result = await codeAPI.applyMultipleFixes(fixes);

      if (result.success) {
        // Remove fixed issues from list
        setState(prev => ({
          ...prev,
          issues: prev.issues.filter(i => !result.applied?.some((f: Fix) => f.original === i.fix?.original)),
        }));
        return true;
      } else {
        setState(prev => ({
          ...prev,
          error: result.errors?.join(', ') || 'Failed to apply fixes',
        }));
        return false;
      }
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to apply fixes',
      }));
      return false;
    }
  }, []);

  const clearIssues = useCallback(() => {
    setState(prev => ({
      ...prev,
      issues: [],
      selectedIssue: null,
      error: null,
    }));
  }, []);

  const selectIssue = useCallback((issue: CodeIssue | null) => {
    setState(prev => ({ ...prev, selectedIssue: issue }));
  }, []);

  const clearError = useCallback(() => {
    setState(prev => ({ ...prev, error: null }));
  }, []);

  return {
    ...state,
    analyzeFile,
    reviewFile,
    applyFix,
    applyMultipleFixes,
    clearIssues,
    selectIssue,
    clearError,
  };
}

export default useCodeReview;
