import * as parser from '@babel/parser';
import traverse from '@babel/traverse';

export interface SecurityIssue {
  id: string;
  severity: 'error' | 'warning' | 'info';
  rule: string;
  message: string;
  line: number;
  column?: number;
  fix?: {
    original: string;
    replacement: string;
    description: string;
  };
}

export interface SecurityDetector {
  name: string;
  detect(code: string): SecurityIssue[];
}

// Helper to generate unique issue IDs
function generateIssueId(): string {
  return `sec-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

// ============================================================================
// SQL Injection Detector
// ============================================================================
export const sqlInjectionDetector: SecurityDetector = {
  name: 'SQL Injection',
  detect(code: string) {
    const issues: SecurityIssue[] = [];
    const lines = code.split('\n');

    lines.forEach((line, index) => {
      const lineNum = index + 1;

      // f-string with user input in SQL
      if (line.match(/f['"`].*SELECT.*\{.*\}/i) ||
          line.match(/f['"`].*INSERT.*\{.*\}/i) ||
          line.match(/f['"`].*UPDATE.*\{.*\}/i) ||
          line.match(/f['"`].*DELETE.*\{.*\}/i)) {
        issues.push({
          id: generateIssueId(),
          severity: 'error',
          rule: 'SQL_INJECTION',
          message: 'Potential SQL injection: avoid template literals with user input in SQL queries',
          line: lineNum,
        });
      }

      // String concatenation in SQL
      if (line.match(/['"`].*SELECT.*['"`].*\+/) ||
          line.match(/['"`].*INSERT.*['"`].*\+/) ||
          line.match(/\.format\(.*['"`].*(SELECT|INSERT|UPDATE|DELETE)/i)) {
        issues.push({
          id: generateIssueId(),
          severity: 'error',
          rule: 'SQL_INJECTION',
          message: 'Potential SQL injection: avoid string concatenation in SQL queries',
          line: lineNum,
        });
      }

      // Template strings with SQL
      if (line.match(/`.*SELECT.*\$\{.*\}/i) ||
          line.match(/`.*INSERT.*\$\{.*\}/i)) {
        issues.push({
          id: generateIssueId(),
          severity: 'error',
          rule: 'SQL_INJECTION',
          message: 'Potential SQL injection: avoid template strings in SQL queries',
          line: lineNum,
        });
      }
    });

    // AST-based detection for more accuracy
    try {
      const ast = parser.parse(code, {
        sourceType: 'module',
        plugins: ['typescript'],
      });

      traverse(ast, {
        CallExpression(path) {
          const callee = path.node.callee;
          const args = path.node.arguments;

          // Check for query methods with string concatenation
          if (callee.type === 'MemberExpression') {
            const propName = callee.property.type === 'Identifier' ? callee.property.name : '';

            // Common ORM/database methods
            const dbMethods = ['query', 'execute', 'raw', 'findBySql', 'select'];
            if (dbMethods.includes(propName) && args.length > 0) {
              const firstArg = args[0];
              if (firstArg.type === 'BinaryExpression' && firstArg.operator === '+') {
                issues.push({
                  id: generateIssueId(),
                  severity: 'error',
                  rule: 'SQL_INJECTION',
                  message: 'Potential SQL injection: binary expression concatenation in query',
                  line: path.node.loc?.start.line || 0,
                  column: path.node.loc?.start.column,
                });
              }
            }
          }
        },
      });
    } catch (e) {
      // Ignore parsing errors for AST-based detection
    }

    return issues;
  },
};

// ============================================================================
// Command Injection Detector
// ============================================================================
export const commandInjectionDetector: SecurityDetector = {
  name: 'Command Injection',
  detect(code: string) {
    const issues: SecurityIssue[] = [];
    const lines = code.split('\n');

    lines.forEach((line, index) => {
      const lineNum = index + 1;

      // os.system with user input
      if (line.match(/os\.system\(.*\+/)) {
        issues.push({
          id: generateIssueId(),
          severity: 'error',
          rule: 'COMMAND_INJECTION',
          message: 'Potential command injection: avoid os.system with string concatenation',
          line: lineNum,
        });
      }

      // os.popen with user input
      if (line.match(/os\.popen\(.*\+/)) {
        issues.push({
          id: generateIssueId(),
          severity: 'error',
          rule: 'COMMAND_INJECTION',
          message: 'Potential command injection: avoid os.popen with string concatenation',
          line: lineNum,
        });
      }

      // subprocess with shell=True
      if (line.match(/subprocess\.(run|call|spawn|exec|check_output|Popen).*shell\s*=\s*true/i) ||
          line.match(/subprocess\.(run|call|spawn|exec|check_output|Popen).*shell\s*=\s*1\b/)) {
        issues.push({
          id: generateIssueId(),
          severity: 'warning',
          rule: 'COMMAND_INJECTION',
          message: 'Be cautious with shell=True in subprocess; consider using shell=False with argument list',
          line: lineNum,
        });
      }

      // eval/exec with user input
      if (line.match(/eval\(.*\+/) || line.match(/exec\(.*\+/)) {
        issues.push({
          id: generateIssueId(),
          severity: 'error',
          rule: 'CODE_INJECTION',
          message: 'Potential code injection: avoid eval/exec with string concatenation',
          line: lineNum,
        });
      }

      // child_process with shell option
      if (line.match(/exec\(['"`].*\$\{.*\}/) ||
          line.match(/exec\(['"`].*`.*\$\{.*\}/)) {
        issues.push({
          id: generateIssueId(),
          severity: 'error',
          rule: 'COMMAND_INJECTION',
          message: 'Potential command injection: avoid template literals in child_process exec',
          line: lineNum,
        });
      }
    });

    // AST-based detection
    try {
      const ast = parser.parse(code, {
        sourceType: 'module',
        plugins: ['typescript'],
      });

      traverse(ast, {
        CallExpression(path) {
          const callee = path.node.callee;
          const args = path.node.arguments;

          if (callee.type === 'MemberExpression' && args.length > 0) {
            const objType = callee.object.type === 'Identifier' ? callee.object.name : '';
            const propName = callee.property.type === 'Identifier' ? callee.property.name : '';

            // Node.js child_process methods
            if (objType === 'require' && (callee.object as any).arguments?.[0]?.value === 'child_process') {
              if (['exec', 'execSync', 'execFile', 'execFileSync'].includes(propName)) {
                const firstArg = args[0];
                if (firstArg.type === 'BinaryExpression' || firstArg.type === 'TemplateLiteral') {
                  issues.push({
                    id: generateIssueId(),
                    severity: 'error',
                    rule: 'COMMAND_INJECTION',
                    message: 'Potential command injection: avoid dynamic command strings',
                    line: path.node.loc?.start.line || 0,
                  });
                }
              }
            }
          }
        },
      });
    } catch (e) {
      // Ignore parsing errors
    }

    return issues;
  },
};

// ============================================================================
// Hardcoded Secrets Detector
// ============================================================================
export const secretsDetector: SecurityDetector = {
  name: 'Hardcoded Secrets',
  detect(code: string) {
    const issues: SecurityIssue[] = [];
    const lines = code.split('\n');

    // Patterns for detecting secrets
    const patterns: Array<{ regex: RegExp; rule: string; message: string; severity: 'error' | 'warning' }> = [
      // General secrets
      { regex: /password\s*=\s*['"][^'"]{3,}/i, rule: 'HARDCODED_PASSWORD', message: 'Hardcoded password detected', severity: 'error' },
      { regex: /passwd\s*=\s*['"][^'"]{3,}/i, rule: 'HARDCODED_PASSWORD', message: 'Hardcoded password detected', severity: 'error' },
      { regex: /pwd\s*=\s*['"][^'"]{3,}/i, rule: 'HARDCODED_PASSWORD', message: 'Hardcoded password detected', severity: 'error' },
      { regex: /api[_-]?key\s*=\s*['"][^'"]{8,}/i, rule: 'HARDCODED_API_KEY', message: 'Hardcoded API key detected', severity: 'error' },
      { regex: /secret\s*=\s*['"][^'"]{8,}/i, rule: 'HARDCODED_SECRET', message: 'Hardcoded secret detected', severity: 'error' },
      { regex: /token\s*=\s*['"][^'"]{8,}/i, rule: 'HARDCODED_TOKEN', message: 'Hardcoded token detected', severity: 'error' },
      { regex: /private[_-]?key\s*=\s*['"][^'"]{20,}/i, rule: 'HARDCODED_PRIVATE_KEY', message: 'Hardcoded private key detected', severity: 'error' },
      { regex: /auth\s*=\s*['"][^'"]{20,}/i, rule: 'HARDCODED_AUTH', message: 'Hardcoded auth credential detected', severity: 'error' },

      // Cloud provider keys
      { regex: /AKIA[0-9A-Z]{16}/, rule: 'AWS_ACCESS_KEY', message: 'AWS Access Key ID detected', severity: 'error' },
      { regex: /sk-[a-zA-Z0-9]{20,}/, rule: 'OPENAI_KEY', message: 'OpenAI API key detected', severity: 'error' },
      { regex: /sk-ant-[a-zA-Z0-9]{20,}/, rule: 'ANTHROPIC_KEY', message: 'Anthropic API key detected', severity: 'error' },
      { regex: /xox[baprs]-[0-9a-zA-Z]{10,}/, rule: 'SLACK_TOKEN', message: 'Slack token detected', severity: 'error' },
      { regex: /gh[pousr]_[a-zA-Z0-9]{36,}/, rule: 'GITHUB_TOKEN', message: 'GitHub token detected', severity: 'error' },
      { regex: /ghp_[a-zA-Z0-9]{36,}/, rule: 'GITHUB_TOKEN', message: 'GitHub personal access token detected', severity: 'error' },
      { regex: /ya29\.[a-zA-Z0-9_-]+/, rule: 'GOOGLE_API', message: 'Google API token detected', severity: 'error' },

      // Database connection strings
      { regex: /mongodb:\/\/[^'"]{5,}/i, rule: 'MONGODB_URI', message: 'MongoDB connection string detected', severity: 'warning' },
      { regex: /postgresql:\/\/[^'"]{5,}/i, rule: 'POSTGRESQL_URI', message: 'PostgreSQL connection string detected', severity: 'warning' },
      { regex: /mysql:\/\/[^'"]{5,}/i, rule: 'MYSQL_URI', message: 'MySQL connection string detected', severity: 'warning' },
      { regex: /redis:\/\/[^'"]{5,}/i, rule: 'REDIS_URI', message: 'Redis connection string detected', severity: 'warning' },

      // Private keys
      { regex: /-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----/, rule: 'PRIVATE_KEY', message: 'Private key block detected', severity: 'error' },
      { regex: /-----BEGIN CERTIFICATE-----/, rule: 'CERTIFICATE', message: 'Certificate block detected', severity: 'warning' },
    ];

    lines.forEach((line, index) => {
      const lineNum = index + 1;

      // Skip comments and test files
      const trimmedLine = line.trim();
      if (trimmedLine.startsWith('//') || trimmedLine.startsWith('#') || trimmedLine.includes('.test.') || trimmedLine.includes('.spec.')) {
        return;
      }

      for (const { regex, rule, message, severity } of patterns) {
        if (regex.test(line)) {
          issues.push({
            id: generateIssueId(),
            severity,
            rule,
            message,
            line: lineNum,
            column: line.indexOf(line.match(regex)?.[0] || ''),
          });
        }
      }
    });

    return issues;
  },
};

// ============================================================================
// XSS Vulnerability Detector
// ============================================================================
export const xssDetector: SecurityDetector = {
  name: 'XSS Vulnerability',
  detect(code: string) {
    const issues: SecurityIssue[] = [];

    try {
      const ast = parser.parse(code, {
        sourceType: 'module',
        plugins: ['jsx', 'typescript'],
      });

      traverse(ast, {
        AssignmentExpression(path) {
          // innerHTML assignment
          if (path.node.left.type === 'MemberExpression') {
            const obj = path.node.left.object;
            const prop = path.node.left.property;

            if (obj.type === 'Identifier' && prop.type === 'Identifier') {
              // Direct innerHTML assignment
              if (prop.name === 'innerHTML') {
                issues.push({
                  id: generateIssueId(),
                  severity: 'warning',
                  rule: 'XSS_INNERHTML',
                  message: 'Potential XSS: innerHTML can execute arbitrary HTML/JavaScript',
                  line: path.node.loc?.start.line || 0,
                  column: path.node.loc?.start.column,
                  fix: {
                    original: '.innerHTML =',
                    replacement: '.textContent =',
                    description: 'Consider using textContent for safe text insertion',
                  },
                });
              }

              // outerHTML assignment
              if (prop.name === 'outerHTML') {
                issues.push({
                  id: generateIssueId(),
                  severity: 'warning',
                  rule: 'XSS_OUTERHTML',
                  message: 'Potential XSS: outerHTML can execute arbitrary HTML/JavaScript',
                  line: path.node.loc?.start.line || 0,
                  column: path.node.loc?.start.column,
                });
              }
            }
          }
        },

        JSXAttribute(path) {
          // dangerouslySetInnerHTML in React
          if (path.node.name.type === 'JSXIdentifier' && path.node.name.name === 'dangerouslySetInnerHTML') {
            issues.push({
              id: generateIssueId(),
              severity: 'warning',
              rule: 'XSS_DANGEROUS_SET_INNER_HTML',
              message: 'Potential XSS: dangerouslySetInnerHTML bypasses React\'s safety measures',
              line: path.node.loc?.start.line || 0,
              column: path.node.loc?.start.column,
            });
          }
        },

        CallExpression(path) {
          // document.write
          if (path.node.callee.type === 'MemberExpression') {
            const obj = path.node.callee.object;
            const prop = path.node.callee.property;

            if (obj.type === 'Identifier' && obj.name === 'document' &&
                prop.type === 'Identifier' && prop.name === 'write') {
              issues.push({
                id: generateIssueId(),
                severity: 'error',
                rule: 'XSS_DOCUMENT_WRITE',
                message: 'Potential XSS: document.write can execute arbitrary HTML/JavaScript',
                line: path.node.loc?.start.line || 0,
                column: path.node.loc?.start.column,
              });
            }

            // insertAdjacentHTML
            if (prop.type === 'Identifier' && prop.name === 'insertAdjacentHTML') {
              issues.push({
                id: generateIssueId(),
                severity: 'info',
                rule: 'XSS_INSERT_ADJACENT_HTML',
                message: 'Potential XSS: insertAdjacentHTML can execute arbitrary HTML',
                line: path.node.loc?.start.line || 0,
                column: path.node.loc?.start.column,
              });
            }
          }
        },
      });
    } catch (e) {
      // Ignore parsing errors
    }

    return issues;
  },
};

// ============================================================================
// Path Traversal Detector
// ============================================================================
export const pathTraversalDetector: SecurityDetector = {
  name: 'Path Traversal',
  detect(code: string) {
    const issues: SecurityIssue[] = [];

    try {
      const ast = parser.parse(code, {
        sourceType: 'module',
        plugins: ['typescript'],
      });

      traverse(ast, {
        CallExpression(path) {
          const callee = path.node.callee;
          const args = path.node.arguments;

          if (callee.type === 'MemberExpression' && args.length > 0) {
            const objType = callee.object.type === 'Identifier' ? (callee.object as any).name : '';
            const propName = callee.property.type === 'Identifier' ? (callee.property as any).name : '';

            // fs methods that might be vulnerable
            if (['readFile', 'readFileSync', 'writeFile', 'writeFileSync', 'createReadStream', 'createWriteStream', 'unlink', 'rm'].includes(propName)) {
              const firstArg = args[0];

              // Check for path concatenation with user input
              if (firstArg.type === 'BinaryExpression' && firstArg.operator === '+') {
                issues.push({
                  id: generateIssueId(),
                  severity: 'warning',
                  rule: 'PATH_TRAVERSAL',
                  message: 'Potential path traversal: file path constructed from user input',
                  line: path.node.loc?.start.line || 0,
                  column: path.node.loc?.start.column,
                });
              }

              // Check for template literals
              if (firstArg.type === 'TemplateLiteral' && firstArg.expressions.length > 0) {
                issues.push({
                  id: generateIssueId(),
                  severity: 'warning',
                  rule: 'PATH_TRAVERSAL',
                  message: 'Potential path traversal: file path contains dynamic content',
                  line: path.node.loc?.start.line || 0,
                  column: path.node.loc?.start.column,
                });
              }
            }

            // Express/Connect static file serving
            if (propName === 'static' && objType === 'express') {
              issues.push({
                id: generateIssueId(),
                severity: 'info',
                rule: 'PATH_TRAVERSAL',
                message: 'Ensure static file serving is properly configured to prevent directory traversal',
                line: path.node.loc?.start.line || 0,
                column: path.node.loc?.start.column,
              });
            }
          }
        },
      });
    } catch (e) {
      // Ignore parsing errors
    }

    return issues;
  },
};

// ============================================================================
// Insecure Randomness Detector
// ============================================================================
export const insecureRandomDetector: SecurityDetector = {
  name: 'Insecure Randomness',
  detect(code: string) {
    const issues: SecurityIssue[] = [];

    try {
      const ast = parser.parse(code, {
        sourceType: 'module',
        plugins: ['typescript'],
      });

  traverse(ast, {
    CallExpression(path) {
      const callee = path.node.callee;

      // Check for Math.random() specifically
      if (callee.type === 'MemberExpression') {
        const obj = callee.object;
        const prop = callee.property;

        if (obj.type === 'Identifier' && obj.name === 'Math' &&
            prop.type === 'Identifier' && prop.name === 'random') {
          issues.push({
            id: generateIssueId(),
            severity: 'warning',
            rule: 'INSECURE_RANDOM',
            message: 'Math.random() is not cryptographically secure; use crypto.randomBytes() or crypto.randomUUID()',
            line: path.node.loc?.start.line || 0,
            column: path.node.loc?.start.column,
          });
        }
      }

      if (callee.type === 'Identifier') {
        // Weak PRNGs
        if (['rand', 'srand', 'random'].some(fn => callee.name === fn)) {
          // Check for common weak random patterns
          issues.push({
            id: generateIssueId(),
            severity: 'warning',
            rule: 'WEAK_RANDOM',
            message: 'Non-cryptographic random number generator detected',
            line: path.node.loc?.start.line || 0,
            column: path.node.loc?.start.column,
          });
        }
      }
    },
  });
    } catch (e) {
      // Ignore parsing errors
    }

    return issues;
  },
};

// ============================================================================
// All Security Detectors
// ============================================================================
export const allSecurityDetectors: SecurityDetector[] = [
  sqlInjectionDetector,
  commandInjectionDetector,
  secretsDetector,
  xssDetector,
  pathTraversalDetector,
  insecureRandomDetector,
];

// Run all detectors on code
export function detectSecurityIssues(code: string): SecurityIssue[] {
  const allIssues: SecurityIssue[] = [];

  for (const detector of allSecurityDetectors) {
    const issues = detector.detect(code);
    allIssues.push(...issues);
  }

  // Sort by line number
  return allIssues.sort((a, b) => a.line - b.line);
}
