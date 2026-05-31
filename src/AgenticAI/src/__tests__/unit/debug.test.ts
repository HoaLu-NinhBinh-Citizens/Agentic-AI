import { analyzeCode } from '../../main-process/codeAnalyzer';

describe('CodeAnalyzer Debug', () => {
  it('debug: test basic function extraction', () => {
    const code = `function hello() { return 1; }`;
    const result = analyzeCode(code, 'javascript');
    console.log('Debug result:', JSON.stringify(result, null, 2));
    expect(result.functions.length).toBeGreaterThan(0);
  });
});
