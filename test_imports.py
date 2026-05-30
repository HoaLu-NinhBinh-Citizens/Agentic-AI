"""Quick test for imports and workflow creation."""
import sys
sys.path.insert(0, ".")

# Test imports
print("Testing imports...")
try:
    from src.application.workflows import CodeReviewWorkflow
    print("  CodeReviewWorkflow: OK")
except ImportError as e:
    print(f"  CodeReviewWorkflow: FAILED - {e}")

try:
    from src.application.workflows.unified import UnifiedReviewEngine
    print("  UnifiedReviewEngine: OK")
except ImportError as e:
    print(f"  UnifiedReviewEngine: FAILED - {e}")

try:
    from src.infrastructure.reporting import MarkdownReportGenerator, CLIReportGenerator
    print("  Reporters: OK")
except ImportError as e:
    print(f"  Reporters: FAILED - {e}")

# Test workflow creation
print("\nTesting workflow creation...")
try:
    workflow = CodeReviewWorkflow()
    mode = "unified" if workflow._use_unified else "legacy"
    print(f"  CodeReviewWorkflow created: {mode} mode")
except Exception as e:
    print(f"  CodeReviewWorkflow creation: FAILED - {e}")

# Test unified engine directly
print("\nTesting UnifiedReviewEngine...")
try:
    from src.application.workflows.unified import ReviewEngineConfig, UnifiedReviewEngine
    config = ReviewEngineConfig(focus_areas=["security"])
    engine = UnifiedReviewEngine(config)
    print(f"  UnifiedReviewEngine created: OK")
    print(f"  Detectors: {engine.get_detectors()}")
except Exception as e:
    print(f"  UnifiedReviewEngine: FAILED - {e}")

# Test CLI command imports
print("\nTesting CLI commands...")
try:
    from src.interfaces.cli.commands import review, unified_review
    print("  review command: OK")
    print("  unified_review command: OK")
except ImportError as e:
    print(f"  CLI commands: FAILED - {e}")

print("\nAll tests completed!")
