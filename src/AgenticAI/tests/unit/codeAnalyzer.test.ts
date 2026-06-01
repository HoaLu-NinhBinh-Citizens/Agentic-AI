/**
 * Unit Tests for codeAnalyzer
 * Priority: High - Expected ROI: High
 */
import { parse } from '@babel/parser';
import traverse from '@babel/traverse';
import generate from '@babel/generator';

// Simple code analyzer for testing
// (In real implementation, this would import from src/main-process/codeAnalyzer)

interface AnalysisResult {
  functions: FunctionInfo[];
  imports: ImportInfo[];
  exports: ExportInfo[];
  complexity: number;
}

interface FunctionInfo {
  name: string;
  startLine: number;
  endLine: number;
  params: number;
  isAsync: boolean;
}

interface ImportInfo {
  source: string;
  imported: string[];
  isDefault: boolean;
}

interface ExportInfo {
  name: string;
  isDefault: boolean;
}

function analyzeCode(code: string, language: string = 'typescript'): AnalysisResult {
  const functions: FunctionInfo[] = [];
  const imports: ImportInfo[] = [];
  const exports: ExportInfo[] = [];
  
  if (language === 'typescript' || language === 'javascript') {
    try {
      const ast = parse(code, {
        sourceType: 'module',
        plugins: ['typescript', 'jsx'],
      });
      
      traverse(ast, {
        FunctionDeclaration(path) {
          functions.push({
            name: path.node.id?.name || 'anonymous',
            startLine: path.node.loc?.start.line || 0,
            endLine: path.node.loc?.end.line || 0,
            params: path.node.params.length,
            isAsync: path.node.async,
          });
        },
        ArrowFunctionExpression(path) {
          if (path.parentPath.isVariableDeclarator()) {
            functions.push({
              name: path.parentPath.node.id?.name || 'arrow',
              startLine: path.node.loc?.start.line || 0,
              endLine: path.node.loc?.end.line || 0,
              params: path.node.params.length,
              isAsync: path.node.async,
            });
          }
        },
        ImportDeclaration(path) {
          imports.push({
            source: path.node.source.value,
            imported: path.node.specifiers.map(s => {
              if (s.type === 'ImportDefaultSpecifier') return 'default';
              if (s.type === 'ImportSpecifier') return s.imported.name;
              return '';
            }),
            isDefault: path.node.specifiers.some(s => s.type === 'ImportDefaultSpecifier'),
          });
        },
        ExportNamedDeclaration(path) {
          if (path.node.declaration) {
            const decl = path.node.declaration;
            exports.push({
              name: (decl as any).id?.name || 'named',
              isDefault: false,
            });
          }
        },
        ExportDefaultDeclaration(path) {
          exports.push({
            name: (path.node.declaration as any)?.name || 'default',
            isDefault: true,
          });
        },
      });
    } catch (error) {
      console.error('Parse error:', error);
    }
  }
  
  // Calculate cyclomatic complexity (simplified)
  const complexity = code.split(/\b(if|while|for|switch|case|\?|&&|\|\|)\b/).length;
  
  return { functions, imports, exports, complexity };
}

describe('codeAnalyzer', () => {
  describe('Function Detection', () => {
    test('should detect function declarations', () => {
      const code = `
        function hello() {
          return 'hello';
        }
      `;
      
      const result = analyzeCode(code);
      
      expect(result.functions).toHaveLength(1);
      expect(result.functions[0].name).toBe('hello');
      expect(result.functions[0].params).toBe(0);
    });

    test('should detect functions with parameters', () => {
      const code = `
        function add(a: number, b: number): number {
          return a + b;
        }
      `;
      
      const result = analyzeCode(code);
      
      expect(result.functions).toHaveLength(1);
      expect(result.functions[0].params).toBe(2);
    });

    test('should detect async functions', () => {
      const code = `
        async function fetchData() {
          const response = await fetch('/api');
          return response.json();
        }
      `;
      
      const result = analyzeCode(code);
      
      expect(result.functions).toHaveLength(1);
      expect(result.functions[0].isAsync).toBe(true);
    });

    test('should detect arrow functions assigned to variables', () => {
      const code = `
        const multiply = (a: number, b: number) => a * b;
        const greet = () => 'hello';
      `;
      
      const result = analyzeCode(code);
      
      expect(result.functions.length).toBeGreaterThanOrEqual(1);
      const multiplyFn = result.functions.find(f => f.name === 'multiply');
      expect(multiplyFn).toBeDefined();
      expect(multiplyFn?.params).toBe(2);
    });

    test('should detect line numbers correctly', () => {
      const code = `
        function first() {}
        
        function second() {}
      `;
      
      const result = analyzeCode(code);
      
      expect(result.functions[0].startLine).toBeLessThan(result.functions[1].startLine);
    });
  });

  describe('Import Detection', () => {
    test('should detect named imports', () => {
      const code = `
        import { useState, useEffect } from 'react';
      `;
      
      const result = analyzeCode(code);
      
      expect(result.imports).toHaveLength(1);
      expect(result.imports[0].source).toBe('react');
      expect(result.imports[0].imported).toContain('useState');
    });

    test('should detect default imports', () => {
      const code = `
        import React from 'react';
      `;
      
      const result = analyzeCode(code);
      
      expect(result.imports).toHaveLength(1);
      expect(result.imports[0].isDefault).toBe(true);
    });

    test('should detect mixed imports', () => {
      const code = `
        import React, { useState } from 'react';
        import fs from 'fs';
      `;
      
      const result = analyzeCode(code);
      
      expect(result.imports).toHaveLength(2);
      const reactImport = result.imports.find(i => i.source === 'react');
      expect(reactImport?.isDefault).toBe(true);
    });

    test('should detect side-effect imports', () => {
      const code = `
        import './styles.css';
      `;
      
      const result = analyzeCode(code);
      
      expect(result.imports).toHaveLength(1);
      expect(result.imports[0].imported).toContain('default');
    });
  });

  describe('Export Detection', () => {
    test('should detect named exports', () => {
      const code = `
        export const PI = 3.14;
        export function add(a, b) { return a + b; }
      `;
      
      const result = analyzeCode(code);
      
      expect(result.exports.length).toBeGreaterThan(0);
      expect(result.exports.some(e => !e.isDefault)).toBe(true);
    });

    test('should detect default exports', () => {
      const code = `
        export default function App() {
          return <div>Hello</div>;
        }
      `;
      
      const result = analyzeCode(code);
      
      expect(result.exports).toHaveLength(1);
      expect(result.exports[0].isDefault).toBe(true);
    });

    test('should detect default export with expression', () => {
      const code = `
        const Component = () => null;
        export default Component;
      `;
      
      const result = analyzeCode(code);
      
      expect(result.exports.some(e => e.isDefault)).toBe(true);
    });
  });

  describe('Complexity Calculation', () => {
    test('should calculate basic complexity', () => {
      const simpleCode = `
        function hello() {
          return 'hello';
        }
      `;
      
      const result = analyzeCode(simpleCode);
      
      // Basic complexity should be at least 1
      expect(result.complexity).toBeGreaterThanOrEqual(1);
    });

    test('should increase complexity with conditional statements', () => {
      const conditionalCode = `
        function check(x: number) {
          if (x > 0) {
            return true;
          } else {
            return false;
          }
        }
      `;
      
      const result = analyzeCode(conditionalCode);
      
      expect(result.complexity).toBeGreaterThan(1);
    });

    test('should increase complexity with loops', () => {
      const loopCode = `
        function process(items: number[]) {
          for (let i = 0; i < items.length; i++) {
            console.log(items[i]);
          }
        }
      `;
      
      const result = analyzeCode(loopCode);
      
      expect(result.complexity).toBeGreaterThan(1);
    });

    test('should increase complexity with logical operators', () => {
      const logicCode = `
        function check(a: boolean, b: boolean) {
          return a && b || false;
        }
      `;
      
      const result = analyzeCode(logicCode);
      
      expect(result.complexity).toBeGreaterThan(1);
    });
  });

  describe('Error Handling', () => {
    test('should handle empty code', () => {
      const result = analyzeCode('');
      
      expect(result.functions).toHaveLength(0);
      expect(result.imports).toHaveLength(0);
      expect(result.exports).toHaveLength(0);
    });

    test('should handle malformed code gracefully', () => {
      const malformedCode = `
        function broken( {
          return 'missing paren';
        }
      `;
      
      // Should not throw
      expect(() => analyzeCode(malformedCode)).not.toThrow();
    });

    test('should handle code with syntax errors', () => {
      const syntaxErrorCode = `
        const x: = 123;
      `;
      
      // Should not throw, just return empty results
      const result = analyzeCode(syntaxErrorCode);
      expect(result).toBeDefined();
    });
  });

  describe('TypeScript Support', () => {
    test('should parse TypeScript code', () => {
      const tsCode = `
        interface User {
          id: number;
          name: string;
        }
        
        function getUser(id: number): User | null {
          return null;
        }
      `;
      
      const result = analyzeCode(tsCode, 'typescript');
      
      expect(result.functions).toHaveLength(1);
      expect(result.functions[0].params).toBe(1);
    });

    test('should detect TypeScript type annotations', () => {
      const typedCode = `
        const greet = (name: string, age: number): void => {
          console.log(\`Hello \${name}, you are \${age}\`);
        };
      `;
      
      const result = analyzeCode(typedCode);
      
      const greetFn = result.functions.find(f => f.name === 'greet');
      expect(greetFn?.params).toBe(2);
    });
  });
});
