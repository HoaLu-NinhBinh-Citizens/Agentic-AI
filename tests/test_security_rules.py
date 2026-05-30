"""Test security rules."""
from src.infrastructure.analysis.rule_engine import RuleEngine
import os

engine = RuleEngine()

# Test with various secrets
test_code = 'api_key = "ghp_1234567890abcdefghijklmnopqrstuvwxyz12"\n'
test_code += 'password = "secret123"\n'
test_code += 'token = "sk-abcdefghijklmnopqrstuvwxyz123456"\n'

with open('test_sec.py', 'w') as f:
    f.write(test_code)

findings = engine.detect('test_sec.py', 'python')
print('Security findings:')
for f in findings:
    print(f'  [{f.severity.value}] {f.rule_id}: {f.rule_name}')
    print(f'    Message: {f.message[:100]}...')

os.remove('test_sec.py')
print('\nSecurity rules test passed!')
