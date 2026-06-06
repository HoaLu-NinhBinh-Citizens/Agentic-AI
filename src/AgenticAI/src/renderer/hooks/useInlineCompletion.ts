/**
 * useInlineCompletion — registers a Monaco InlineCompletionsProvider
 * that produces ghost text suggestions via the AI backend.
 *
 * Behavior (Cursor-like):
 * - As the user types, requests a completion for the text around the cursor
 * - Shows the result as ghost text (dimmed inline suggestion)
 * - User presses Tab to accept
 * - Debounced + cached to avoid spamming the AI backend
 */

import { useEffect, useRef } from 'react';

interface InlineCompletionOptions {
  /** Whether inline completion is enabled */
  enabled?: boolean;
  /** Debounce delay in ms before requesting a completion */
  debounceMs?: number;
  /** Max characters of context to send before/after cursor */
  contextChars?: number;
}

const DEFAULT_DEBOUNCE = 350;
const DEFAULT_CONTEXT_CHARS = 2000;

export function useInlineCompletion(
  monaco: any,
  language: string,
  options: InlineCompletionOptions = {}
) {
  const {
    enabled = true,
    debounceMs = DEFAULT_DEBOUNCE,
    contextChars = DEFAULT_CONTEXT_CHARS,
  } = options;

  const providerRef = useRef<any>(null);
  // Simple cache: prefix-hash -> completion
  const cacheRef = useRef<Map<string, string>>(new Map());
  // Debounce timer + in-flight request tracking
  const pendingRef = useRef<{ timer: any; resolve: ((v: any) => void) | null }>({
    timer: null,
    resolve: null,
  });

  useEffect(() => {
    if (!monaco || !enabled) return;

    // Dispose previous provider if re-registering
    if (providerRef.current) {
      providerRef.current.dispose();
      providerRef.current = null;
    }

    const provider = {
      // Monaco calls this to get inline completions
      provideInlineCompletions: async (model: any, position: any) => {
        try {
          // Build prefix (text before cursor) and suffix (text after)
          const offset = model.getOffsetAt(position);
          const fullText = model.getValue();

          const prefixStart = Math.max(0, offset - contextChars);
          const suffixEnd = Math.min(fullText.length, offset + contextChars);

          const prefix = fullText.slice(prefixStart, offset);
          const suffix = fullText.slice(offset, suffixEnd);

          // Don't complete on empty prefix or trailing whitespace-only lines
          const currentLine = model.getLineContent(position.lineNumber);
          const textBeforeCursor = currentLine.slice(0, position.column - 1);
          if (!textBeforeCursor.trim() && !prefix.trim()) {
            return { items: [] };
          }

          // Check cache
          const cacheKey = hashString(prefix.slice(-200) + '|' + suffix.slice(0, 100));
          if (cacheRef.current.has(cacheKey)) {
            const cached = cacheRef.current.get(cacheKey)!;
            return makeCompletionResult(cached, position, monaco);
          }

          // Debounced request
          const completion = await debouncedComplete(
            { prefix, suffix, language },
            pendingRef,
            debounceMs
          );

          if (!completion) {
            return { items: [] };
          }

          // Cache and return
          cacheRef.current.set(cacheKey, completion);
          // Limit cache size
          if (cacheRef.current.size > 100) {
            const firstKey = cacheRef.current.keys().next().value;
            cacheRef.current.delete(firstKey);
          }

          return makeCompletionResult(completion, position, monaco);
        } catch (e) {
          console.error('[InlineCompletion] error:', e);
          return { items: [] };
        }
      },

      // Required no-op handlers
      freeInlineCompletions: () => {},
      handleItemDidShow: () => {},
    };

    providerRef.current = monaco.languages.registerInlineCompletionsProvider(
      language,
      provider
    );

    return () => {
      if (providerRef.current) {
        providerRef.current.dispose();
        providerRef.current = null;
      }
    };
  }, [monaco, language, enabled, debounceMs, contextChars]);
}

// ─── Helpers ──────────────────────────────────────────────────────────────

function makeCompletionResult(completion: string, position: any, monaco: any) {
  return {
    items: [
      {
        insertText: completion,
        range: new monaco.Range(
          position.lineNumber,
          position.column,
          position.lineNumber,
          position.column
        ),
      },
    ],
  };
}

/**
 * Debounce completion requests. Cancels the previous pending request
 * if a new one comes in before the delay elapses.
 */
function debouncedComplete(
  params: { prefix: string; suffix: string; language: string },
  pendingRef: React.MutableRefObject<{ timer: any; resolve: ((v: any) => void) | null }>,
  delay: number
): Promise<string> {
  return new Promise((resolve) => {
    // Cancel previous pending request
    if (pendingRef.current.timer) {
      clearTimeout(pendingRef.current.timer);
      if (pendingRef.current.resolve) {
        pendingRef.current.resolve(''); // resolve stale request with empty
      }
    }

    pendingRef.current.resolve = resolve;
    pendingRef.current.timer = setTimeout(async () => {
      try {
        const api = (window as any).electronAPI;
        if (!api?.ai?.complete) {
          resolve('');
          return;
        }
        const result = await api.ai.complete({
          prefix: params.prefix,
          suffix: params.suffix,
          language: params.language,
          maxTokens: 120,
        });
        resolve(result?.success ? result.completion || '' : '');
      } catch {
        resolve('');
      } finally {
        pendingRef.current.timer = null;
        pendingRef.current.resolve = null;
      }
    }, delay);
  });
}

function hashString(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0;
  }
  return String(hash);
}
