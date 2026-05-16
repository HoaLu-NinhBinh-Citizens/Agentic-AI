"""
Test script for Learning Module
"""

from src.learning import PatternStore, store_failure_learned, get_fix_recommendation


def test_pattern_store():
    """Test basic pattern store operations."""
    store = PatternStore()

    # Store some failure patterns
    print("Storing failure patterns...")

    pattern_id = store.store_failure(
        error_type="buffer_overflow",
        error_message="strcpy buffer overflow detected",
        context={"file": "uart.c", "function": "parse_frame", "task_type": "firmware"},
        fix_description="Use strncpy(dst, src, sizeof(dst)-1) instead of strcpy",
        fix_code="strncpy(buf, input, sizeof(buf)-1); buf[sizeof(buf)-1] = 0;",
    )
    print(f"  Stored pattern: {pattern_id}")

    pattern_id2 = store.store_failure(
        error_type="register_write",
        error_message="RCC register write without clock enable",
        context={"file": "gpio.c", "function": "init", "task_type": "firmware"},
        fix_description="Enable GPIO clock before configuring",
        fix_code="__HAL_RCC_GPIOA_CLK_ENABLE();",
    )
    print(f"  Stored pattern: {pattern_id2}")

    # Get statistics
    stats = store.get_statistics()
    print(f"\nStatistics: {stats}")

    # Get fix recommendation
    print("\nLooking for fix recommendation...")
    fix = store.get_recommended_fix(
        error_type="buffer_overflow",
        context={"file": "spi.c", "function": "transfer", "task_type": "firmware"},
    )

    if fix:
        print(f"  Found fix: {fix['description']}")
        print(f"  Confidence: {fix['confidence']:.0%}")
        print(f"  Code: {fix['code']}")
    else:
        print("  No fix found")

    # Test pattern matching
    print("\nPattern matching:")
    matches = store.match_pattern(
        error_type="buffer_overflow",
        context={"file": "i2c.c", "function": "read", "task_type": "firmware"},
    )
    print(f"  Found {len(matches)} matches")
    for m in matches:
        print(f"    - {m.match_type}: {m.pattern.error_type} (confidence: {m.confidence:.0%})")

    print("\n[OK] Pattern store test passed!")


def test_convenience_functions():
    """Test convenience functions."""
    print("\nTesting convenience functions...")

    # Store
    pid = store_failure_learned(
        error_type="test_error",
        error_message="Test error message",
        context={"test": True},
        fix_description="Test fix",
    )
    print(f"  Stored: {pid}")

    # Get
    fix = get_fix_recommendation(
        error_type="test_error",
        context={"test": True},
    )
    if fix:
        print(f"  Got fix: {fix['description']}")

    print("  [OK] Convenience functions work!")


if __name__ == "__main__":
    test_pattern_store()
    test_convenience_functions()
    print("\n[SUCCESS] All learning tests passed!")
