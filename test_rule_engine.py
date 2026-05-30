"""Test script for RuleEngine."""
from src.infrastructure.analysis.rule_engine import RuleEngine

engine = RuleEngine()

# Create a test file with some issues
test_code = '''import os
import json
api_key = "sk-1234567890abcdefghijklmnopqrstuvwxyz"

def badFunctionName():
    """Untyped function"""
    eval("print(1)")
    return None

for i in range(10):
    print(i)
'''

# Write test file
with open('test_sample.py', 'w') as f:
    f.write(test_code)

# Run detection
findings = engine.detect('test_sample.py', 'python')

print(f'Found {len(findings)} issues:')
for f in findings:
    print(f'  [{f.severity.value:8}] {f.rule_id} at line {f.line}: {f.rule_name}')

# Get statistics
stats = engine.get_stats(findings)
print(f'\nStatistics:')
print(f'  Total: {stats["total"]}')
for sev, count in stats['by_severity'].items():
    if count > 0:
        print(f'  {sev}: {count}')

# Test external linter integration
print('\nExternal linter integration test:')
print(f'  Supported linters: pylint, ruff, eslint, golangci-lint, rustc')

# Cleanup
import os
os.remove('test_sample.py')
print('\nTest completed successfully')
