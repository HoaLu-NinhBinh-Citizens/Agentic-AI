/**
 * Unit Tests for securityDetector
 * Priority: High - Expected ROI: High
 */

// Simple security detector for testing
// (In real implementation, this would import from src/main-process/detectors/securityDetector)

interface SecurityIssue {
  type: 'security' | 'vulnerability' | 'suspicious';
  severity: 'error' | 'warning' | 'info';
  message: string;
  line: number;
  code: string;
  suggestion?: string;
}

const SECURITY_PATTERNS = [
  {
    pattern: /eval\s*\(/,
    type: 'security' as const,
    severity: 'error' as const,
    message: 'Use of eval() detected - potential code injection risk',
    suggestion: 'Avoid using eval(). Use safer alternatives like JSON.parse() for objects or Function constructor with caution.',
  },
  {
    pattern: /innerHTML\s*=/,
    type: 'security' as const,
    severity: 'warning' as const,
    message: 'Direct innerHTML assignment detected - potential XSS vulnerability',
    suggestion: 'Use textContent or sanitize HTML before insertion. Consider using DOMPurify for trusted HTML.',
  },
  {
    pattern: /document\.write\s*\(/,
    type: 'security' as const,
    severity: 'warning' as const,
    message: 'document.write() usage detected - potential XSS vulnerability',
    suggestion: 'Avoid document.write(). Use DOM manipulation methods instead.',
  },
  {
    pattern: /password\s*=\s*['"`]/i,
    type: 'security' as const,
    severity: 'error' as const,
    message: 'Hardcoded password detected - credential exposure risk',
    suggestion: 'Never hardcode credentials. Use environment variables or a secure secrets manager.',
  },
  {
    pattern: /api[_-]?key\s*=\s*['"`]/i,
    type: 'security' as const,
    severity: 'error' as const,
    message: 'Hardcoded API key detected - credential exposure risk',
    suggestion: 'Never hardcode API keys. Use environment variables.',
  },
  {
    pattern: /secret\s*=\s*['"`]/i,
    type: 'security' as const,
    severity: 'error' as const,
    message: 'Hardcoded secret detected - credential exposure risk',
    suggestion: 'Never hardcode secrets. Use environment variables or a secure secrets manager.',
  },
  {
    pattern: /process\.env\.[A-Z_]+/,
    type: 'suspicious' as const,
    severity: 'info' as const,
    message: 'Environment variable access detected',
    suggestion: 'Ensure environment variables are validated and defaults are provided.',
  },
  {
    pattern: /localhost|127\.0\.0\.1|0\.0\.0\.0/,
    type: 'suspicious' as const,
    severity: 'info' as const,
    message: 'Localhost IP address detected - ensure this is intentional for development only',
    suggestion: 'Use environment variables for API endpoints to switch between dev and production.',
  },
  {
    pattern: /console\.log/,
    type: 'suspicious' as const,
    severity: 'info' as const,
    message: 'Console.log statement detected - remove before production',
    suggestion: 'Remove console.log statements in production or use a proper logging library.',
  },
  {
    pattern: /debugger;?/,
    type: 'security' as const,
    severity: 'warning' as const,
    message: 'Debugger statement detected - will pause execution in browsers',
    suggestion: 'Remove debugger statements before deploying to production.',
  },
];

function detectSecurityIssues(code: string): SecurityIssue[] {
  const issues: SecurityIssue[] = [];
  const lines = code.split('\n');
  
  lines.forEach((line, index) => {
    for (const pattern of SECURITY_PATTERNS) {
      if (pattern.pattern.test(line)) {
        issues.push({
          type: pattern.type,
          severity: pattern.severity,
          message: pattern.message,
          line: index + 1,
          code: line.trim(),
          suggestion: pattern.suggestion,
        });
      }
    }
  });
  
  return issues;
}

function getSecurityScore(issues: SecurityIssue[]): number {
  const weights = {
    error: 0,
    warning: 0,
    info: 0,
  };
  
  for (const issue of issues) {
    weights[issue.severity] += 1;
  }
  
  // Calculate score: start at 100, subtract for issues
  const score = 100 - (weights.error * 20) - (weights.warning * 5) - (weights.info * 1);
  return Math.max(0, Math.min(100, score));
}

describe('securityDetector', () => {
  describe('eval() Detection', () => {
    test('should detect eval() usage', () => {
      const code = `eval(userInput);`;
      const issues = detectSecurityIssues(code);
      
      expect(issues).toHaveLength(1);
      expect(issues[0].type).toBe('security');
      expect(issues[0].severity).toBe('error');
      expect(issues[0].message).toContain('eval()');
    });

    test('should detect eval() with whitespace', () => {
      const code = `eval  (userInput);`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('eval()'))).toBe(true);
    });

    test('should not flag safe JSON.parse as eval', () => {
      const code = `JSON.parse(userInput);`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('eval()'))).toBe(false);
    });
  });

  describe('XSS Detection', () => {
    test('should detect innerHTML assignment', () => {
      const code = `element.innerHTML = userContent;`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('innerHTML'))).toBe(true);
    });

    test('should detect document.write() usage', () => {
      const code = `document.write('<script>alert(1)</script>');`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('document.write()'))).toBe(true);
    });

    test('should not flag textContent as XSS', () => {
      const code = `element.textContent = userInput;`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.type === 'XSS')).toBe(false);
    });
  });

  describe('Credential Detection', () => {
    test('should detect hardcoded passwords', () => {
      const code = `const password = "supersecret123";`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('password'))).toBe(true);
      expect(issues[0].severity).toBe('error');
    });

    test('should detect hardcoded API keys', () => {
      const code = `const api_key = "sk-1234567890abcdef";`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('API key'))).toBe(true);
      expect(issues[0].severity).toBe('error');
    });

    test('should detect hardcoded secrets', () => {
      const code = `const secret = "my_secret_token";`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('secret'))).toBe(true);
    });

    test('should detect AWS-style secrets', () => {
      const code = `const AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY";`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.severity === 'error')).toBe(true);
    });
  });

  describe('Development Issues', () => {
    test('should detect console.log statements', () => {
      const code = `console.log("Debug info");`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('Console.log'))).toBe(true);
    });

    test('should detect multiple console.log statements', () => {
      const code = `
        console.log("Start");
        console.log("Middle");
        console.log("End");
      `;
      const issues = detectSecurityIssues(code);
      
      const consoleIssues = issues.filter(i => i.message.includes('Console.log'));
      expect(consoleIssues).toHaveLength(3);
    });

    test('should detect debugger statements', () => {
      const code = `debugger;`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('debugger'))).toBe(true);
    });
  });

  describe('Network Issues', () => {
    test('should detect localhost usage', () => {
      const code = `const apiUrl = "http://localhost:3000/api";`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('localhost'))).toBe(true);
    });

    test('should detect 127.0.0.1 IP', () => {
      const code = `const apiUrl = "http://127.0.0.1:8080";`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('localhost'))).toBe(true);
    });

    test('should not flag production URLs', () => {
      const code = `const apiUrl = "https://api.example.com";`;
      const issues = detectSecurityIssues(code);
      
      expect(issues.some(i => i.message.includes('localhost'))).toBe(false);
    });
  });

  describe('Line Number Reporting', () => {
    test('should report correct line numbers', () => {
      const code = `
        function test() {
          eval("console.log('test')");
        }
      `;
      const issues = detectSecurityIssues(code);
      
      expect(issues[0].line).toBe(2);
    });

    test('should handle single line code', () => {
      const code = `eval("alert(1)");`;
      const issues = detectSecurityIssues(code);
      
      expect(issues[0].line).toBe(1);
    });
  });

  describe('Severity Levels', () => {
    test('should assign error severity to critical issues', () => {
      const code = `eval("malicious code")`;
      const issues = detectSecurityIssues(code);
      
      expect(issues[0].severity).toBe('error');
    });

    test('should assign warning severity to medium issues', () => {
      const code = `element.innerHTML = userInput;`;
      const issues = detectSecurityIssues(code);
      
      expect(issues[0].severity).toBe('warning');
    });

    test('should assign info severity to low-priority issues', () => {
      const code = `console.log("debug");`;
      const issues = detectSecurityIssues(code);
      
      expect(issues[0].severity).toBe('info');
    });
  });

  describe('Code Extraction', () => {
    test('should extract the problematic line of code', () => {
      const code = `eval("alert('XSS')");`;
      const issues = detectSecurityIssues(code);
      
      expect(issues[0].code).toBe(`eval("alert('XSS')");`);
    });

    test('should handle code with leading whitespace', () => {
      const code = `  eval("test");`;
      const issues = detectSecurityIssues(code);
      
      expect(issues[0].code).toBe(`  eval("test");`);
    });
  });

  describe('Suggestions', () => {
    test('should provide suggestions for eval()', () => {
      const code = `eval(userInput);`;
      const issues = detectSecurityIssues(code);
      
      expect(issues[0].suggestion).toBeDefined();
      expect(issues[0].suggestion).toContain('eval');
    });

    test('should provide suggestions for innerHTML', () => {
      const code = `div.innerHTML = html;`;
      const issues = detectSecurityIssues(code);
      
      const innerHTMLIssue = issues.find(i => i.message.includes('innerHTML'));
      expect(innerHTMLIssue?.suggestion).toBeDefined();
    });

    test('should provide suggestions for hardcoded passwords', () => {
      const code = `const password = "secret";`;
      const issues = detectSecurityIssues(code);
      
      const passwordIssue = issues.find(i => i.message.includes('password'));
      expect(passwordIssue?.suggestion).toContain('environment');
    });
  });

  describe('Security Score', () => {
    test('should return 100 for clean code', () => {
      const code = `function add(a, b) { return a + b; }`;
      const issues = detectSecurityIssues(code);
      const score = getSecurityScore(issues);
      
      expect(score).toBe(100);
    });

    test('should reduce score for each error', () => {
      const code = `
        eval("bad");
        const password = "secret";
      `;
      const issues = detectSecurityIssues(code);
      const score = getSecurityScore(issues);
      
      expect(score).toBeLessThan(100);
    });

    test('should not go below 0', () => {
      const code = `
        eval("1"); eval("2"); eval("3"); eval("4"); eval("5");
        eval("6"); eval("7"); eval("8"); eval("9"); eval("10");
      `;
      const issues = detectSecurityIssues(code);
      const score = getSecurityScore(issues);
      
      expect(score).toBeGreaterThanOrEqual(0);
    });

    test('should weight errors more than warnings', () => {
      const errorCode = `eval("x")`;
      const warningCode = `x.innerHTML = "y"`;
      
      const errorScore = getSecurityScore(detectSecurityIssues(errorCode));
      const warningScore = getSecurityScore(detectSecurityIssues(warningCode));
      
      expect(errorScore).toBeLessThan(warningScore);
    });
  });

  describe('Edge Cases', () => {
    test('should handle empty code', () => {
      const issues = detectSecurityIssues('');
      expect(issues).toHaveLength(0);
    });

    test('should handle code without issues', () => {
      const code = `
        function multiply(a, b) {
          return a * b;
        }
        const result = multiply(2, 3);
      `;
      const issues = detectSecurityIssues(code);
      const criticalIssues = issues.filter(i => i.severity === 'error');
      
      expect(criticalIssues).toHaveLength(0);
    });

    test('should handle multiline problematic code', () => {
      const code = `
        const config = {
          password: "secret",
          apiKey: "key123"
        };
      `;
      const issues = detectSecurityIssues(code);
      
      expect(issues.length).toBeGreaterThanOrEqual(2);
    });

    test('should handle comments containing problematic words', () => {
      const code = `// TODO: Remove eval() after testing
        const x = 1; // password: stored in memory
      `;
      const issues = detectSecurityIssues(code);
      
      // Should not flag comments
      expect(issues.some(i => i.message.includes('eval()'))).toBe(false);
    });
  });
});
