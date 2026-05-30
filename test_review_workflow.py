"""Practical test for CodeReviewWorkflow with UnifiedReviewEngine."""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from src.application.workflows import CodeReviewWorkflow


async def test_review_workflow():
    """Test the review workflow with both unified and legacy modes."""
    
    # Create a test file with known issues
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('''import os
def myFunction():
    api_key = "sk-1234567890abcdef"
    password = "secret123"
    eval("print('test')")
    while True:
        print("infinite loop")
    return 42
''')
        test_file = f.name
    
    try:
        # Test with unified engine (auto-detect)
        print("=" * 60)
        print("TEST 1: CodeReviewWorkflow (auto-detect mode)")
        print("=" * 60)
        
        workflow = CodeReviewWorkflow()
        print(f"Mode: {'unified' if workflow._use_unified else 'legacy'}")
        
        result = await workflow.review_and_fix(
            files=[test_file],
            focus_areas=["security"],
            dry_run=True,
            interactive=False,
        )
        
        print(f"Files reviewed: {result.files_reviewed}")
        print(f"Total findings: {result.total_findings}")
        print(f"Errors: {result.errors}")
        print(f"Warnings: {result.warnings}")
        print(f"Info: {result.info}")
        print(f"Fixes: {len(result.fix_batch.fixes)}")
        
        # Check expected findings
        assert result.files_reviewed == 1, "Should review 1 file"
        print("\n✓ Test 1 passed!")
        
        # Test with legacy mode explicitly
        print("\n" + "=" * 60)
        print("TEST 2: CodeReviewWorkflow (legacy mode)")
        print("=" * 60)
        
        workflow_legacy = CodeReviewWorkflow(use_unified=False)
        print(f"Mode: {'unified' if workflow_legacy._use_unified else 'legacy'}")
        
        result_legacy = await workflow_legacy.review_and_fix(
            files=[test_file],
            focus_areas=["security"],
            dry_run=True,
            interactive=False,
        )
        
        print(f"Files reviewed: {result_legacy.files_reviewed}")
        print(f"Total findings: {result_legacy.total_findings}")
        
        assert result_legacy.files_reviewed == 1, "Should review 1 file"
        print("\n✓ Test 2 passed!")
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
        
    finally:
        # Cleanup
        Path(test_file).unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(test_review_workflow())
