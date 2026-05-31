import * as parser from '@babel/parser';
import traverse from '@babel/traverse';
import * as t from '@babel/types';

export interface AnalysisResult {
  functions: FunctionInfo[];
  imports: ImportInfo[];
  exports: ExportInfo[];
  complexity: number;
  issues: CodeIssue[];
}

export interface FunctionInfo {
  name: string;
  startLine: number;
  endLine: number;
  params: string[];
  async: boolean;
  complexity: number;
}

export interface ImportInfo {
  source: string;
  imported: string[];
  startLine: number;
}

export interface ExportInfo {
  name: string;
  type: 'function' | 'class' | 'variable' | 'default';
  startLine: number;
}

export interface CodeIssue {
  id: string;
  severity: 'error' | 'warning' | 'info';
  rule: string;
  message: string;
  line: number;
  column?: number;
  fix?: FixSuggestion;
}

export interface FixSuggestion {
  original: string;
  replacement: string;
  description: string;
}

export function analyzeCode(code: string, language: string = 'javascript'): AnalysisResult {
  const result: AnalysisResult = {
    functions: [],
    imports: [],
    exports: [],
    complexity: 0,
    issues: [],
  };

  try {
    if (language === 'javascript' || language === 'typescript') {
      return analyzeJS(code);
    } else if (language === 'python') {
      return analyzePython(code);
    }
  } catch (error) {
    result.issues.push({
      id: generateIssueId(),
      severity: 'error',
      rule: 'PARSE_ERROR',
      message: `Failed to parse: ${error}`,
      line: 1,
    });
  }

  return result;
}

function generateIssueId(): string {
  return `issue-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

function analyzeJS(code: string): AnalysisResult {
  const result: AnalysisResult = {
    functions: [],
    imports: [],
    exports: [],
    complexity: 0,
    issues: [],
  };

  const ast = parser.parse(code, {
    sourceType: 'module',
    plugins: ['typescript', 'jsx'],
  });

  let complexity = 1;

  traverse(ast, {
    FunctionDeclaration(path) {
      const node = path.node;
      const funcComplexity = calculateComplexity(path);
      result.functions.push({
        name: node.id?.name || 'anonymous',
        startLine: node.loc?.start.line || 0,
        endLine: node.loc?.end.line || 0,
        params: node.params.map(p => {
          if (t.isIdentifier(p)) return p.name;
          return 'param';
        }),
        async: node.async,
        complexity: funcComplexity,
      });
      complexity += funcComplexity;
    },
    ArrowFunctionExpression(path) {
      const funcComplexity = calculateComplexity(path);
      result.functions.push({
        name: 'arrow',
        startLine: path.node.loc?.start.line || 0,
        endLine: path.node.loc?.end.line || 0,
        params: path.node.params.map(p => {
          if (t.isIdentifier(p)) return p.name;
          return 'param';
        }),
        async: path.node.async,
        complexity: funcComplexity,
      });
      complexity += funcComplexity;
    },
    FunctionExpression(path) {
      const funcComplexity = calculateComplexity(path);
      const node = path.node;
      result.functions.push({
        name: 'function',
        startLine: node.loc?.start.line || 0,
        endLine: node.loc?.end.line || 0,
        params: node.params.map(p => {
          if (t.isIdentifier(p)) return p.name;
          return 'param';
        }),
        async: node.async,
        complexity: funcComplexity,
      });
      complexity += funcComplexity;
    },
    ImportDeclaration(path) {
      result.imports.push({
        source: path.node.source.value as string,
        imported: path.node.specifiers.map(s => {
          if (t.isImportSpecifier(s)) {
            return s.imported.type === 'Identifier' ? s.imported.name : 'specifier';
          }
          if (t.isImportDefaultSpecifier(s)) return 'default';
          if (t.isImportNamespaceSpecifier(s)) return '*';
          return 'unknown';
        }),
        startLine: path.node.loc?.start.line || 0,
      });
    },
    ExportNamedDeclaration(path) {
      let exportType: 'function' | 'class' | 'variable' | 'default' = 'function';
      let exportName = 'named';

      if (path.node.declaration) {
        switch (path.node.declaration.type) {
          case 'FunctionDeclaration':
            exportType = 'function';
            if (path.node.declaration.id?.type === 'Identifier') {
              exportName = path.node.declaration.id.name;
            }
            break;
          case 'ClassDeclaration':
            exportType = 'class';
            if (path.node.declaration.id?.type === 'Identifier') {
              exportName = path.node.declaration.id.name;
            }
            break;
          case 'VariableDeclaration':
            exportType = 'variable';
            break;
        }
      } else if (path.node.specifiers.length > 0) {
        const specifier = path.node.specifiers[0];
        if (t.isExportSpecifier(specifier) && t.isIdentifier(specifier.local)) {
          exportName = specifier.local.name;
        }
      }

      result.exports.push({
        name: exportName,
        type: exportType,
        startLine: path.node.loc?.start.line || 0,
      });
    },
    ExportDefaultDeclaration(path) {
      result.exports.push({
        name: path.node.declaration.type === 'Identifier'
          ? path.node.declaration.name
          : path.node.declaration.type,
        type: 'default',
        startLine: path.node.loc?.start.line || 0,
      });
    },
  });

  result.complexity = complexity;

  // Detect common issues
  detectJSIssues(ast, result.issues);

  return result;
}

function calculateComplexity(path: any): number {
  let complexity = 1;

  path.traverse({
    IfStatement() { complexity++; },
    ForStatement() { complexity++; },
    ForInStatement() { complexity++; },
    ForOfStatement() { complexity++; },
    WhileStatement() { complexity++; },
    DoWhileStatement() { complexity++; },
    SwitchStatement() { complexity++; },
    SwitchCase() { complexity++; },
    ConditionalExpression() { complexity++; },
    LogicalExpression(path: any) {
      if (path.node.operator === '&&' || path.node.operator === '||') {
        complexity++;
      }
    },
    CatchClause() { complexity++; },
    OptionalCatchClause() { complexity++; },
  });

  return complexity;
}

function detectJSIssues(ast: any, issues: CodeIssue[]) {
  traverse(ast, {
    BinaryExpression(path) {
      if (path.node.operator === '==' || path.node.operator === '!=') {
        issues.push({
          id: generateIssueId(),
          severity: 'warning',
          rule: 'EQ_EQ',
          message: 'Use === instead of == for strict equality comparison',
          line: path.node.loc?.start.line || 0,
          column: path.node.loc?.start.column,
          fix: {
            original: path.node.operator,
            replacement: path.node.operator === '==' ? '===' : '!==',
            description: 'Replace with strict equality operator',
          },
        });
      }
    },
    Identifier(path) {
      // Check for console.log in production
      if (path.node.name === 'console') {
        const parent = path.parent;
        if (parent && parent.type === 'MemberExpression' && parent.property && parent.property.name === 'log') {
          issues.push({
            id: generateIssueId(),
            severity: 'info',
            rule: 'CONSOLE_LOG',
            message: 'Consider removing console.log statements in production code',
            line: path.node.loc?.start.line || 0,
            column: path.node.loc?.start.column,
          });
        }
      }

      // Check for debugger statements
      if (path.node.name === 'debugger') {
        issues.push({
          id: generateIssueId(),
          severity: 'warning',
          rule: 'DEBUGGER',
          message: 'Remove debugger statement before production',
          line: path.node.loc?.start.line || 0,
          column: path.node.loc?.start.column,
        });
      }
    },
    UnaryExpression(path) {
      // Check for typeof comparisons that might be unreliable
      if (path.node.operator === 'typeof') {
        const argument = path.node.argument;
        if (argument && argument.type === 'Identifier' && argument.name === 'window') {
          issues.push({
            id: generateIssueId(),
            severity: 'info',
            rule: 'TYPEOF_WINDOW',
            message: 'typeof window may return undefined in non-browser environments',
            line: path.node.loc?.start.line || 0,
            column: path.node.loc?.start.column,
          });
        }
      }
    },
    NewExpression(path) {
      // Check for new Date() without assignment to variable
      if (path.node.callee.type === 'Identifier' && path.node.callee.name === 'Date') {
        issues.push({
          id: generateIssueId(),
          severity: 'info',
          rule: 'NEW_DATE',
          message: 'new Date() creates a mutable date object; consider Date.now() or Date.UTC()',
          line: path.node.loc?.start.line || 0,
          column: path.node.loc?.start.column,
        });
      }
    },
    CallExpression(path) {
      // Check for parseInt without radix
      if (path.node.callee.type === 'Identifier' && path.node.callee.name === 'parseInt') {
        if (path.node.arguments.length < 2) {
          issues.push({
            id: generateIssueId(),
            severity: 'warning',
            rule: 'PARSE_INT_RADIX',
            message: 'parseInt() without radix parameter can lead to unexpected results',
            line: path.node.loc?.start.line || 0,
            column: path.node.loc?.start.column,
          });
        }
      }

      // Check for setTimeout with string (eval)
      if (path.node.callee.type === 'Identifier' && path.node.callee.name === 'setTimeout') {
        if (path.node.arguments.length > 0) {
          const firstArg = path.node.arguments[0];
          if (firstArg.type === 'StringLiteral') {
            issues.push({
              id: generateIssueId(),
              severity: 'error',
              rule: 'SET_TIMEOUT_EVAL',
              message: 'setTimeout with string argument uses eval() and is a security risk',
              line: path.node.loc?.start.line || 0,
              column: path.node.loc?.start.column,
            });
          }
        }
      }

      // Check for setInterval with string (eval)
      if (path.node.callee.type === 'Identifier' && path.node.callee.name === 'setInterval') {
        if (path.node.arguments.length > 0) {
          const firstArg = path.node.arguments[0];
          if (firstArg.type === 'StringLiteral') {
            issues.push({
              id: generateIssueId(),
              severity: 'error',
              rule: 'SET_INTERVAL_EVAL',
              message: 'setInterval with string argument uses eval() and is a security risk',
              line: path.node.loc?.start.line || 0,
              column: path.node.loc?.start.column,
            });
          }
        }
      }
    },
  });
}

function analyzePython(code: string): AnalysisResult {
  // Placeholder for Python analysis with tree-sitter
  // This would require tree-sitter-python integration
  return {
    functions: [],
    imports: [],
    exports: [],
    complexity: 1,
    issues: [],
  };
}

export function getLanguageFromExtension(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase();
  const map: Record<string, string> = {
    js: 'javascript',
    jsx: 'javascript',
    mjs: 'javascript',
    cjs: 'javascript',
    ts: 'typescript',
    tsx: 'typescript',
    mts: 'typescript',
    py: 'python',
    pyw: 'python',
    pyi: 'python',
  };
  return map[ext || ''] || 'javascript';
}

export function calculateOverallComplexity(analysis: AnalysisResult): {
  score: number;
  rating: 'low' | 'medium' | 'high' | 'very_high';
} {
  const score = analysis.complexity;
  let rating: 'low' | 'medium' | 'high' | 'very_high';

  if (score <= 10) {
    rating = 'low';
  } else if (score <= 20) {
    rating = 'medium';
  } else if (score <= 50) {
    rating = 'high';
  } else {
    rating = 'very_high';
  }

  return { score, rating };
}
