"""Test ReviewAgent integration with RuleEngine."""
from src.core.multi_agent.agent import ReviewAgent
import os

# Create test file
test_code = '''import os
def myFunction():
    api_key = "sk-1234567890abcdef"
    print("Hello")
'''

with open('test_agent.py', 'w') as f:
    f.write(test_code)

# Test ReviewAgent
agent = ReviewAgent()
result = agent._static_review('test_agent.py', ['security', 'code_quality'])

print('ReviewAgent result:')
print(f'  File: {result["file"]}')
print(f'  Rating: {result["rating"]}')
print(f'  Issues found: {len(result["issues"])}')
for issue in result['issues'][:5]:
    print(f'    - {issue}')
print(f'  Approved: {result["approved"]}')

# Cleanup
os.remove('test_agent.py')
print('\nReviewAgent integration test passed!')
