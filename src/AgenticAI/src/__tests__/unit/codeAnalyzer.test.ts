import { analyzeCode, getLanguageFromExtension, calculateOverallComplexity, AnalysisResult, FunctionInfo } from '../../main-process/codeAnalyzer';

describe('CodeAnalyzer', () => {
  describe('analyzeCode', () => {
    describe('JavaScript analysis', () => {
      it('should parse JavaScript files', () => {
        const code = `
          function hello(name) {
            return "Hello, " + name;
          }
          const x = 1;
        `;
        const result = analyzeCode(code, 'javascript');
        
        expect(result).toBeDefined();
        expect(result.functions).toBeDefined();
        expect(result.imports).toBeDefined();
        expect(result.exports).toBeDefined();
        expect(result.complexity).toBeDefined();
        expect(result.issues).toBeDefined();
      });

      it('should extract function declarations', () => {
        const code = `
          function add(a, b) {
            return a + b;
          }
          function multiply(a, b) {
            return a * b;
          }
        `;
        const result = analyzeCode(code, 'javascript');
        
        expect(result.functions.length).toBeGreaterThanOrEqual(2);
        const addFunc = result.functions.find(f => f.name === 'add');
        expect(addFunc).toBeDefined();
        expect(addFunc?.params).toEqual(['a', 'b']);
        expect(addFunc?.async).toBe(false);
      });

      it('should extract async functions', () => {
        const code = `
          async function fetchData(url) {
            const response = await fetch(url);
            return response.json();
          }
        `;
        const result = analyzeCode(code, 'javascript');
        
        const asyncFunc = result.functions.find(f => f.name === 'fetchData');
        expect(asyncFunc).toBeDefined();
        expect(asyncFunc?.async).toBe(true);
      });

      it('should extract import declarations', () => {
        const code = `
          import React from 'react';
          import { useState, useEffect } from 'react';
          import * as utils from './utils';
        `;
        const result = analyzeCode(code, 'javascript');
        
        expect(result.imports.length).toBeGreaterThanOrEqual(3);
        
        const reactImport = result.imports.find(i => i.source === 'react');
        expect(reactImport).toBeDefined();
      });

      it('should extract export declarations', () => {
        const code = `
          export function hello() {}
          export const value = 42;
          export default App;
        `;
        const result = analyzeCode(code, 'javascript');
        
        expect(result.exports.length).toBeGreaterThanOrEqual(3);
      });

      it('should calculate cyclomatic complexity', () => {
        const code = `
          function complex(x, y, z) {
            if (x > 0) {
              if (y > 0) {
                while (z > 0) {
                  z--;
                }
              }
            }
            return x + y + z;
          }
        `;
        const result = analyzeCode(code, 'javascript');
        
        expect(result.complexity).toBeGreaterThan(1);
        expect(result.functions[0].complexity).toBeGreaterThan(1);
      });

      it('should detect loose equality operators', () => {
        const code = `
          function compare(a, b) {
            return a == b;
          }
        `;
        const result = analyzeCode(code, 'javascript');
        
        const eqIssue = result.issues.find(i => i.rule === 'EQ_EQ');
        expect(eqIssue).toBeDefined();
        expect(eqIssue?.severity).toBe('warning');
      });

      it('should detect console.log statements', () => {
        const code = `
          function debug() {
            console.log("Debugging");
          }
        `;
        const result = analyzeCode(code, 'javascript');
        
        const consoleIssue = result.issues.find(i => i.rule === 'CONSOLE_LOG');
        expect(consoleIssue).toBeDefined();
        expect(consoleIssue?.severity).toBe('info');
      });

      it('should detect debugger statements', () => {
        const code = `
          function debug() {
            debugger;
          }
        `;
        const result = analyzeCode(code, 'javascript');
        
        const debuggerIssue = result.issues.find(i => i.rule === 'DEBUGGER');
        expect(debuggerIssue).toBeDefined();
        expect(debuggerIssue?.severity).toBe('warning');
      });

      it('should detect setTimeout with string argument', () => {
        const code = `
          setTimeout("alert('XSS')", 1000);
        `;
        const result = analyzeCode(code, 'javascript');
        
        const evalIssue = result.issues.find(i => i.rule === 'SET_TIMEOUT_EVAL');
        expect(evalIssue).toBeDefined();
        expect(evalIssue?.severity).toBe('error');
      });

      it('should detect parseInt without radix', () => {
        const code = `
          const num = parseInt("123");
        `;
        const result = analyzeCode(code, 'javascript');
        
        const radixIssue = result.issues.find(i => i.rule === 'PARSE_INT_RADIX');
        expect(radixIssue).toBeDefined();
        expect(radixIssue?.severity).toBe('warning');
      });

      it('should detect new Date() without assignment consideration', () => {
        const code = `
          const date = new Date();
        `;
        const result = analyzeCode(code, 'javascript');
        
        const dateIssue = result.issues.find(i => i.rule === 'NEW_DATE');
        expect(dateIssue).toBeDefined();
      });
    });

    describe('TypeScript analysis', () => {
      it('should parse TypeScript files', () => {
        const code = `
          interface User {
            name: string;
            age: number;
          }
          function greet(user: User): string {
            return \`Hello, \${user.name}\`;
          }
        `;
        const result = analyzeCode(code, 'typescript');
        
        expect(result).toBeDefined();
        expect(result.functions.length).toBeGreaterThanOrEqual(1);
      });

      it('should extract typed parameters', () => {
        const code = `
          function process(id: number, name: string, active: boolean): void {
            console.log(id, name, active);
          }
        `;
        const result = analyzeCode(code, 'typescript');
        
        const func = result.functions[0];
        expect(func.params).toContain('id');
        expect(func.params).toContain('name');
        expect(func.params).toContain('active');
      });

      it('should handle type annotations', () => {
        const code = `
          const count: number = 10;
          const greeting: string = "Hello";
          const items: string[] = [];
        `;
        const result = analyzeCode(code, 'typescript');
        
        expect(result).toBeDefined();
      });
    });

    describe('JSX analysis', () => {
      it('should parse JSX', () => {
        const code = `
          function Component() {
            return (
              <div className="container">
                <h1>Hello</h1>
              </div>
            );
          }
        `;
        const result = analyzeCode(code, 'javascript');
        
        expect(result).toBeDefined();
      });
    });

    describe('error handling', () => {
      it('should handle syntax errors gracefully', () => {
        const invalidCode = `
          function broken( {
            return "missing paren";
          }
        `;
        const result = analyzeCode(invalidCode, 'javascript');
        
        expect(result.issues.some(i => i.rule === 'PARSE_ERROR')).toBe(true);
      });

      it('should handle empty code', () => {
        const result = analyzeCode('', 'javascript');
        
        expect(result.functions).toEqual([]);
        expect(result.imports).toEqual([]);
        expect(result.exports).toEqual([]);
        expect(result.complexity).toBe(1); // Base complexity
      });

      it('should handle unknown language gracefully', () => {
        const result = analyzeCode('some code', 'unknown');
        
        expect(result).toBeDefined();
        expect(result.functions).toEqual([]);
      });
    });

    describe('Python placeholder', () => {
      it('should return basic structure for Python', () => {
        const pythonCode = `
def hello(name):
    return f"Hello, {name}"
        `;
        const result = analyzeCode(pythonCode, 'python');
        
        // Python analysis is a placeholder
        expect(result).toBeDefined();
        expect(result.functions).toEqual([]);
      });
    });
  });

  describe('getLanguageFromExtension', () => {
    it('should return javascript for .js files', () => {
      expect(getLanguageFromExtension('file.js')).toBe('javascript');
      expect(getLanguageFromExtension('file.jsx')).toBe('javascript');
      expect(getLanguageFromExtension('file.mjs')).toBe('javascript');
      expect(getLanguageFromExtension('file.cjs')).toBe('javascript');
    });

    it('should return typescript for .ts files', () => {
      expect(getLanguageFromExtension('file.ts')).toBe('typescript');
      expect(getLanguageFromExtension('file.tsx')).toBe('typescript');
      expect(getLanguageFromExtension('file.mts')).toBe('typescript');
    });

    it('should return python for .py files', () => {
      expect(getLanguageFromExtension('file.py')).toBe('python');
      expect(getLanguageFromExtension('file.pyw')).toBe('python');
      expect(getLanguageFromExtension('file.pyi')).toBe('python');
    });

    it('should default to javascript for unknown extensions', () => {
      expect(getLanguageFromExtension('file.txt')).toBe('javascript');
      expect(getLanguageFromExtension('file.unknown')).toBe('javascript');
      expect(getLanguageFromExtension('file')).toBe('javascript');
    });
  });

  describe('calculateOverallComplexity', () => {
    it('should return low rating for score <= 10', () => {
      const analysis: AnalysisResult = {
        functions: [],
        imports: [],
        exports: [],
        complexity: 5,
        issues: [],
      };
      
      const result = calculateOverallComplexity(analysis);
      expect(result.rating).toBe('low');
      expect(result.score).toBe(5);
    });

    it('should return medium rating for score 11-20', () => {
      const analysis: AnalysisResult = {
        functions: [],
        imports: [],
        exports: [],
        complexity: 15,
        issues: [],
      };
      
      const result = calculateOverallComplexity(analysis);
      expect(result.rating).toBe('medium');
    });

    it('should return high rating for score 21-50', () => {
      const analysis: AnalysisResult = {
        functions: [],
        imports: [],
        exports: [],
        complexity: 35,
        issues: [],
      };
      
      const result = calculateOverallComplexity(analysis);
      expect(result.rating).toBe('high');
    });

    it('should return very_high rating for score > 50', () => {
      const analysis: AnalysisResult = {
        functions: [],
        imports: [],
        exports: [],
        complexity: 100,
        issues: [],
      };
      
      const result = calculateOverallComplexity(analysis);
      expect(result.rating).toBe('very_high');
    });
  });

  describe('complex code samples', () => {
    it('should handle large files', () => {
      const lines: string[] = [];
      for (let i = 0; i < 100; i++) {
        lines.push(`function func${i}() { return ${i}; }`);
      }
      const code = lines.join('\n');
      
      const result = analyzeCode(code, 'javascript');
      
      expect(result.functions.length).toBeGreaterThanOrEqual(100);
    });

    it('should handle deeply nested code', () => {
      let code = 'function deep() {';
      for (let i = 0; i < 10; i++) {
        code += '\nif (x) {';
      }
      code += '\nreturn 1;';
      for (let i = 0; i < 10; i++) {
        code += '\n}';
      }
      code += '\n}';
      
      const result = analyzeCode(code, 'javascript');
      
      expect(result.complexity).toBeGreaterThan(10);
    });

    it('should handle multiple control flow statements', () => {
      const code = `
        function complexFlow(x, y, z) {
          if (x > 0) {
            for (let i = 0; i < 10; i++) {
              while (y > 0) {
                do {
                  switch (z) {
                    case 1: break;
                    case 2: break;
                  }
                  z--;
                } while (z > 0);
                y--;
              }
            }
          }
          return x + y + z;
        }
      `;
      
      const result = analyzeCode(code, 'javascript');
      
      // Should detect multiple complexity-increasing statements
      expect(result.complexity).toBeGreaterThanOrEqual(9);
    });
  });

  describe('arrow functions', () => {
    it('should extract arrow functions', () => {
      const code = `
        const add = (a, b) => a + b;
        const multiply = (a, b) => {
          return a * b;
        };
        const asyncFetch = async (url) => {
          return fetch(url);
        };
      `;
      
      const result = analyzeCode(code, 'javascript');
      
      const arrowFunctions = result.functions.filter(f => f.name === 'arrow');
      expect(arrowFunctions.length).toBeGreaterThanOrEqual(3);
      
      const asyncArrow = arrowFunctions.find(f => f.async === true);
      expect(asyncArrow).toBeDefined();
    });
  });

  describe('function expressions', () => {
    it('should extract function expressions', () => {
      const code = `
        const hello = function() {
          return "hello";
        };
      `;
      
      const result = analyzeCode(code, 'javascript');
      
      const funcExpr = result.functions.find(f => f.name === 'function');
      expect(funcExpr).toBeDefined();
    });
  });
});
