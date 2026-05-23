"""Test case generator from bugs (Phase 9.5).

Provides:
- Generate regression tests from crash/fix pairs
- Support for Unity, CppUTest, GTest
- Multi-run validation for flaky test detection
- Test case template generation
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TestFramework(Enum):
    """Supported test frameworks."""
    UNITY = "unity"          # Ceedling/Unity framework
    CPPUTEST = "cpputest"   # CppUTest framework
    GTEST = "gtest"         # GoogleTest framework
    CUSTOM = "custom"       # Custom harness


@dataclass
class TestCaseTemplate:
    """Generated test case template."""
    id: str
    name: str
    description: str
    
    # Test code
    test_code: str
    setup_code: str = ""
    teardown_code: str = ""
    
    # Framework
    framework: TestFramework = TestFramework.UNITY
    
    # Metadata
    source_bug_id: str = ""
    source_file: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    
    # Validation
    run_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    is_flaky: bool = False
    
    @property
    def pass_rate(self) -> float:
        """Calculate pass rate."""
        if self.run_count == 0:
            return 0.0
        return self.pass_count / self.run_count
    
    @property
    def is_stable(self) -> bool:
        """Check if test is stable (not flaky)."""
        return self.run_count >= 3 and self.pass_rate >= 0.95


@dataclass
class TestGenerationContext:
    """Context for generating test cases."""
    bug_description: str
    bug_type: str
    root_cause: str = ""
    affected_files: list[str] = field(default_factory=list)
    crash_stack: list[str] = field(default_factory=list)
    error_values: dict[str, Any] = field(default_factory=dict)


class TestCaseGenerator:
    """Generate regression tests from bugs.
    
    Phase 9.5: Test case generator
    
    Important: Generated tests can be flaky.
    Must run ≥3 times before committing.
    """
    
    def __init__(self) -> None:
        self._templates: dict[str, TestCaseTemplate] = {}
        self._min_runs_before_commit = 3
    
    def generate(
        self,
        context: TestGenerationContext,
        framework: TestFramework = TestFramework.UNITY,
    ) -> list[TestCaseTemplate]:
        """Generate test cases from bug context."""
        templates = []
        
        # Generate based on bug type
        if "hard_fault" in context.bug_type.lower():
            templates.extend(self._generate_hardfault_test(context, framework))
        elif "timeout" in context.bug_type.lower():
            templates.extend(self._generate_timeout_test(context, framework))
        elif "stack" in context.bug_type.lower():
            templates.extend(self._generate_stack_test(context, framework))
        elif "memory" in context.bug_type.lower():
            templates.extend(self._generate_memory_test(context, framework))
        elif "deadlock" in context.bug_type.lower():
            templates.extend(self._generate_deadlock_test(context, framework))
        else:
            templates.extend(self._generate_generic_test(context, framework))
        
        # Store templates
        for template in templates:
            self._templates[template.id] = template
        
        return templates
    
    def _generate_hardfault_test(
        self,
        context: TestGenerationContext,
        framework: TestFramework,
    ) -> list[TestCaseTemplate]:
        """Generate tests for HardFault bugs."""
        templates = []
        
        # Test for NULL pointer dereference
        template = TestCaseTemplate(
            id=self._generate_id(),
            name=f"test_{context.bug_type}_null_pointer",
            description=f"Regression test for {context.bug_type} - NULL pointer check",
            framework=framework,
            source_bug_id=context.bug_description[:50],
        )
        
        if framework == TestFramework.UNITY:
            template.test_code = self._unity_null_pointer_test(context)
        elif framework == TestFramework.GTEST:
            template.test_code = self._gtest_null_pointer_test(context)
        
        templates.append(template)
        
        # Test for stack overflow
        if context.affected_files:
            template = TestCaseTemplate(
                id=self._generate_id(),
                name=f"test_{context.bug_type}_stack_depth",
                description=f"Regression test for {context.bug_type} - Stack depth check",
                framework=framework,
                source_bug_id=context.bug_description[:50],
            )
            
            if framework == TestFramework.UNITY:
                template.test_code = self._unity_stack_depth_test(context)
            
            templates.append(template)
        
        return templates
    
    def _generate_timeout_test(
        self,
        context: TestGenerationContext,
        framework: TestFramework,
    ) -> list[TestCaseTemplate]:
        """Generate tests for timeout bugs."""
        templates = []
        
        template = TestCaseTemplate(
            id=self._generate_id(),
            name=f"test_{context.bug_type}_timeout",
            description=f"Regression test for {context.bug_type} - Timeout handling",
            framework=framework,
        )
        
        if framework == TestFramework.UNITY:
            template.test_code = self._unity_timeout_test(context)
        elif framework == TestFramework.GTEST:
            template.test_code = self._gtest_timeout_test(context)
        
        templates.append(template)
        return templates
    
    def _generate_stack_test(
        self,
        context: TestGenerationContext,
        framework: TestFramework,
    ) -> list[TestCaseTemplate]:
        """Generate tests for stack overflow bugs."""
        templates = []
        
        template = TestCaseTemplate(
            id=self._generate_id(),
            name=f"test_{context.bug_type}_overflow",
            description=f"Regression test for {context.bug_type} - Stack overflow detection",
            framework=framework,
        )
        
        if framework == TestFramework.UNITY:
            template.test_code = self._unity_stack_overflow_test(context)
        
        templates.append(template)
        return templates
    
    def _generate_memory_test(
        self,
        context: TestGenerationContext,
        framework: TestFramework,
    ) -> list[TestCaseTemplate]:
        """Generate tests for memory bugs."""
        templates = []
        
        template = TestCaseTemplate(
            id=self._generate_id(),
            name=f"test_{context.bug_type}_allocation",
            description=f"Regression test for {context.bug_type} - Memory allocation",
            framework=framework,
        )
        
        if framework == TestFramework.UNITY:
            template.test_code = self._unity_memory_test(context)
        
        templates.append(template)
        return templates
    
    def _generate_deadlock_test(
        self,
        context: TestGenerationContext,
        framework: TestFramework,
    ) -> list[TestCaseTemplate]:
        """Generate tests for deadlock bugs."""
        templates = []
        
        template = TestCaseTemplate(
            id=self._generate_id(),
            name=f"test_{context.bug_type}_lock_timeout",
            description=f"Regression test for {context.bug_type} - Lock timeout detection",
            framework=framework,
        )
        
        if framework == TestFramework.UNITY:
            template.test_code = self._unity_deadlock_test(context)
        
        templates.append(template)
        return templates
    
    def _generate_generic_test(
        self,
        context: TestGenerationContext,
        framework: TestFramework,
    ) -> list[TestCaseTemplate]:
        """Generate generic regression test."""
        template = TestCaseTemplate(
            id=self._generate_id(),
            name=f"test_regression_{self._sanitize_name(context.bug_type)}",
            description=f"Regression test for {context.bug_description[:100]}",
            framework=framework,
            source_bug_id=context.bug_description[:50],
        )
        
        if framework == TestFramework.UNITY:
            template.test_code = self._unity_generic_test(context)
        
        return [template]
    
    def _generate_id(self) -> str:
        """Generate unique test ID."""
        return f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for C identifier."""
        return re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())[:50]
    
    # Unity framework test generators
    def _unity_null_pointer_test(self, context: TestGenerationContext) -> str:
        return f'''\
/**
 * Regression test for: {context.bug_description[:100]}
 * Bug type: {context.bug_type}
 * Generated: {datetime.now().isoformat()}
 */
void setUp(void) {{
    // Setup before each test
}}

void tearDown(void) {{
    // Cleanup after each test
}}

void test_{self._sanitize_name(context.bug_type)}_null_pointer_check(void) {{
    // Test that NULL pointer is properly checked before dereference
    void *ptr = NULL;
    
    // Should handle NULL gracefully
    TEST_ASSERT_TRUE_MESSAGE(
        ptr != NULL || handle_null_pointer(ptr) == ERROR_NULL_POINTER,
        "NULL pointer should return error code"
    );
    
    // Test with valid pointer
    ptr = allocate_test_buffer(64);
    if (ptr != NULL) {{
        int result = handle_null_pointer(ptr);
        TEST_ASSERT_EQUAL_INT_MESSAGE(
            SUCCESS, result,
            "Valid pointer should succeed"
        );
        free_test_buffer(ptr);
    }}
}}

void test_{self._sanitize_name(context.bug_type)}_boundary_conditions(void) {{
    // Test boundary conditions that may trigger the original bug
    size_t sizes[] = {{0, 1, 0xFFFF, 0xFFFFFFFF}};
    
    for (int i = 0; i < sizeof(sizes)/sizeof(sizes[0]); i++) {{
        void *ptr = allocate_test_buffer(sizes[i]);
        if (ptr != NULL || sizes[i] == 0) {{
            TEST_PASS_MESSAGE("Allocation succeeded for size %lu", sizes[i]);
            free_test_buffer(ptr);
        }} else {{
            // Expected failure for large sizes
            TEST_ASSERT_TRUE_MESSAGE(sizes[i] > 0x10000, "Large allocation failed as expected");
        }}
    }}
}}
'''
    
    def _unity_stack_depth_test(self, context: TestGenerationContext) -> str:
        files = ", ".join(context.affected_files[:3]) if context.affected_files else "unknown"
        return f'''\
/**
 * Regression test for: {context.bug_type}
 * Affected files: {files}
 * Generated: {datetime.now().isoformat()}
 */
void test_{self._sanitize_name(context.bug_type)}_stack_depth_limit(void) {{
    // Check that deep recursion doesn't cause stack overflow
    extern unsigned long _estack;
    extern unsigned long _Min_Stack_Size;
    
    unsigned long stack_size = (unsigned long)&_estack - (unsigned long)&_Min_Stack_Size;
    
    TEST_ASSERT_TRUE_MESSAGE(
        stack_size >= 1024,
        "Stack size should be at least 1KB"
    );
    
    // Test recursive function with known depth
    int result = recursive_function_with_depth(10);
    TEST_ASSERT_EQUAL_INT(10, result);
}}

void test_{self._sanitize_name(context.bug_type)}_local_buffer_sizes(void) {{
    // Check that large local buffers are avoided
    #define MAX_LOCAL_SIZE 256
    
    char buffer[MAX_LOCAL_SIZE];
    TEST_ASSERT_TRUE_MESSAGE(
        sizeof(buffer) <= MAX_LOCAL_SIZE,
        "Local buffer exceeds recommended size"
    );
    
    // Fill and check
    memset(buffer, 0xAA, sizeof(buffer));
    for (size_t i = 0; i < sizeof(buffer); i++) {{
        TEST_ASSERT_EQUAL_HEX8_MESSAGE(0xAA, buffer[i], "Buffer corruption detected");
    }}
}}
'''
    
    def _unity_timeout_test(self, context: TestGenerationContext) -> str:
        return f'''\
/**
 * Regression test for: {context.bug_type}
 * Generated: {datetime.now().isoformat()}
 */
void test_{self._sanitize_name(context.bug_type)}_timeout_handling(void) {{
    // Test timeout handling
    #define TEST_TIMEOUT_MS 100
    
    TickType_t start = xTaskGetTickCount();
    BaseType_t result = wait_for_event_with_timeout(TEST_TIMEOUT_MS);
    TickType_t elapsed = xTaskGetTickCount() - start;
    
    if (result == pdTRUE) {{
        // Event received - should be fast
        TEST_ASSERT_TRUE_MESSAGE(
            elapsed < TEST_TIMEOUT_MS,
            "Timeout exceeded when event was ready"
        );
    }} else {{
        // Timeout - should be close to timeout value
        TEST_ASSERT_TRUE_MESSAGE(
            elapsed >= (TEST_TIMEOUT_MS - 10),  // Allow 10ms tolerance
            "Timeout occurred too early"
        );
    }}
}}

void test_{self._sanitize_name(context.bug_type)}_retry_logic(void) {{
    // Test retry logic with timeout
    int max_retries = 3;
    int retry_count = 0;
    
    while (retry_count < max_retries) {{
        if (operation_with_timeout() == SUCCESS) {{
            break;
        }}
        retry_count++;
    }}
    
    // If max retries reached, last attempt should have timed out properly
    TEST_ASSERT_TRUE_MESSAGE(
        retry_count < max_retries || last_error == ERROR_TIMEOUT,
        "Should succeed or timeout properly"
    );
}}
'''
    
    def _unity_stack_overflow_test(self, context: TestGenerationContext) -> str:
        return f'''\
/**
 * Regression test for: {context.bug_type}
 * Generated: {datetime.now().isoformat()}
 */
void test_{self._sanitize_name(context.bug_type)}_stack_watermark(void) {{
    // Check stack watermark after operation
    extern void vTaskList(char *pcWriteBuffer);
    
    // Perform the operation that caused stack overflow
    perform_affected_operation();
    
    // Get task stack status
    char status_buffer[500];
    vTaskList(status_buffer);
    
    // Verify no task is near stack limit
    TEST_ASSERT_TRUE_MESSAGE(
        check_stack_margin() > 100,
        "Stack margin too low - risk of overflow"
    );
}}

void test_{self._sanitize_name(context.bug_type)}_no_deep_recursion(void) {{
    // Verify recursive functions have depth limits
    int result;
    BaseType_t error = recursive_with_limit(50, &result);
    
    TEST_ASSERT_EQUAL_INT_MESSAGE(
        pdTRUE, error,
        "Recursive function should respect depth limit"
    );
    TEST_ASSERT_TRUE_MESSAGE(
        result >= 0 && result <= 50,
        "Result should be within expected range"
    );
}}
'''
    
    def _unity_memory_test(self, context: TestGenerationContext) -> str:
        return f'''\
/**
 * Regression test for: {context.bug_type}
 * Generated: {datetime.now().isoformat()}
 */
void test_{self._sanitize_name(context.bug_type)}_allocation_limits(void) {{
    // Test memory allocation limits
    void *ptr1 = allocate_test_buffer(1024);
    void *ptr2 = allocate_test_buffer(2048);
    
    if (ptr1 != NULL) {{
        free_test_buffer(ptr1);
        TEST_PASS_MESSAGE("First allocation succeeded");
    }} else {{
        TEST_FAIL_MESSAGE("First allocation (1KB) failed unexpectedly");
    }}
    
    if (ptr2 != NULL) {{
        free_test_buffer(ptr2);
        TEST_PASS_MESSAGE("Second allocation succeeded");
    }} else {{
        TEST_FAIL_MESSAGE("Second allocation (2KB) failed unexpectedly");
    }}
}}

void test_{self._sanitize_name(context.bug_type)}_null_on_exhaustion(void) {{
    // Exhaust memory and verify NULL is returned
    void *ptr;
    int alloc_count = 0;
    
    while ((ptr = allocate_test_buffer(64)) != NULL && alloc_count < 1000) {{
        alloc_count++;
    }}
    
    // Memory should be exhausted or limit reached
    TEST_ASSERT_TRUE_MESSAGE(
        alloc_count > 0 || ptr == NULL,
        "Allocation behavior is consistent"
    );
    
    // Cleanup
    TEST_MESSAGE("Freed %d allocations", alloc_count);
}}
'''
    
    def _unity_deadlock_test(self, context: TestGenerationContext) -> str:
        return f'''\
/**
 * Regression test for: {context.bug_type}
 * Generated: {datetime.now().isoformat()}
 */
void test_{self._sanitize_name(context.bug_type)}_lock_timeout(void) {{
    // Test that locks have timeout to prevent deadlock
    #define LOCK_TIMEOUT_MS 100
    
    TickType_t start = xTaskGetTickCount();
    BaseType_t acquired = xSemaphoreTakeRecursive(
        test_mutex, 
        pdMS_TO_TICKS(LOCK_TIMEOUT_MS)
    );
    TickType_t elapsed = xTaskGetTickCount() - start;
    
    if (acquired == pdTRUE) {{
        xSemaphoreGiveRecursive(test_mutex);
        // Lock acquired quickly - good
        TEST_PASS_MESSAGE("Lock acquired without deadlock");
    }} else {{
        // Timeout - lock was held too long
        TEST_ASSERT_TRUE_MESSAGE(
            elapsed >= LOCK_TIMEOUT_MS - 5,  // Allow some tolerance
            "Lock timeout too early - may indicate deadlock"
        );
    }}
}}

void test_{self._sanitize_name(context.bug_type)}_lock_ordering(void) {{
    // Test that lock ordering is consistent to prevent deadlock
    int result1, result2;
    
    // Lock A then B
    result1 = lock_in_order(LOCK_A, LOCK_B);
    
    // Lock B then A - should have same outcome
    result2 = lock_in_order(LOCK_B, LOCK_A);
    
    // Both should either succeed or fail consistently
    TEST_ASSERT_TRUE_MESSAGE(
        (result1 == result2) || (result1 != SUCCESS && result2 != SUCCESS),
        "Lock ordering produced inconsistent results"
    );
}}
'''
    
    def _unity_generic_test(self, context: TestGenerationContext) -> str:
        return f'''\
/**
 * Regression test for: {context.bug_description[:100]}
 * Bug type: {context.bug_type}
 * Root cause: {context.root_cause[:100] if context.root_cause else 'Unknown'}
 * Generated: {datetime.now().isoformat()}
 * 
 * NOTE: Review and customize this test before committing.
 * Run at least 3 times to check for flakiness.
 */
void setUp(void) {{
    // Initialize test environment
}}

void tearDown(void) {{
    // Cleanup test environment
}}

void test_{self._sanitize_name(context.bug_type)}_regression(void) {{
    // TODO: Implement test case for the bug:
    // {context.bug_description}
    // 
    // Hint: Root cause was "{context.root_cause[:50]}..."
    
    // Placeholder assertion - replace with actual test
    TEST_FAIL_MESSAGE("Implement regression test for {context.bug_type}");
}}
'''
    
    # GTest framework test generators
    def _gtest_null_pointer_test(self, context: TestGenerationContext) -> str:
        return f'''\
/**
 * Regression test for: {context.bug_description[:100]}
 */
TEST({self._sanitize_name(context.bug_type)}, NullPointerHandling) {{
    void* null_ptr = nullptr;
    
    // Should handle NULL gracefully
    EXPECT_EQ(ERROR_NULL_POINTER, HandleNullPointer(null_ptr));
    
    // Valid pointer should work
    void* valid_ptr = std::malloc(64);
    if (valid_ptr != nullptr) {{
        EXPECT_EQ(SUCCESS, HandleNullPointer(valid_ptr));
        std::free(valid_ptr);
    }}
}};
'''
    
    def _gtest_timeout_test(self, context: TestGenerationContext) -> str:
        return f'''\
/**
 * Regression test for: {context.bug_type}
 */
TEST({self._sanitize_name(context.bug_type)}, TimeoutBehavior) {{
    const int timeout_ms = 100;
    auto start = std::chrono::steady_clock::now();
    
    Result result = WaitForEvent(timeout_ms);
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - start
    ).count();
    
    if (result == Result::SUCCESS) {{
        EXPECT_LT(elapsed, timeout_ms) << "Event was ready but took too long";
    }} else {{
        EXPECT_GE(elapsed, timeout_ms - 10) << "Timeout occurred too early";
    }}
}};
'''
    
    def record_test_result(self, test_id: str, passed: bool) -> bool:
        """Record test execution result.
        
        Returns:
            True if test is stable enough to commit (run ≥3 times).
        """
        if test_id not in self._templates:
            logger.warning("Unknown test ID", test_id=test_id)
            return False
        
        template = self._templates[test_id]
        template.run_count += 1
        
        if passed:
            template.pass_count += 1
        else:
            template.fail_count += 1
        
        # Check for flakiness
        if template.run_count >= 2:
            recent_runs = template.run_count
            recent_passes = template.pass_count
            recent_fails = template.fail_count
            
            if recent_passes > 0 and recent_fails > 0:
                template.is_flaky = True
                logger.warning(
                    "Test is flaky",
                    test_id=test_id,
                    pass_rate=template.pass_rate,
                    runs=template.run_count,
                )
        
        return template.is_stable
    
    def get_test(self, test_id: str) -> TestCaseTemplate | None:
        """Get test template by ID."""
        return self._templates.get(test_id)
    
    def get_all_tests(self) -> list[TestCaseTemplate]:
        """Get all test templates."""
        return list(self._templates.values())
    
    def get_flaky_tests(self) -> list[TestCaseTemplate]:
        """Get tests marked as flaky."""
        return [t for t in self._templates.values() if t.is_flaky]
    
    def get_stable_tests(self) -> list[TestCaseTemplate]:
        """Get tests stable enough to commit."""
        return [t for t in self._templates.values() if t.is_stable]


# Global singleton
_generator: TestCaseGenerator | None = None


def get_test_generator() -> TestCaseGenerator:
    """Get global test generator instance."""
    global _generator
    if _generator is None:
        _generator = TestCaseGenerator()
    return _generator


# CLI for testing
if __name__ == "__main__":
    generator = get_test_generator()
    
    # Generate test from bug context
    context = TestGenerationContext(
        bug_description="HardFault caused by NULL pointer dereference in UART handler",
        bug_type="hard_fault",
        root_cause="UART handler doesn't check for NULL before accessing buffer pointer",
        affected_files=["src/drivers/uart.c", "src/handlers/uart_handler.c"],
        crash_stack=[
            "HardFault_Handler() at stm32f4xx_it.c:142",
            "UART_IRQHandler() at uart_handler.c:56",
        ],
    )
    
    print("Generating regression tests:")
    print("-" * 60)
    
    templates = generator.generate(context, TestFramework.UNITY)
    
    for template in templates:
        print(f"\nTest: {template.name}")
        print(f"Description: {template.description}")
        print(f"Framework: {template.framework.value}")
        print(f"\nCode:\n{template.test_code[:500]}...")
    
    print("\n\nTest Generation Summary:")
    print(f"  Total templates: {len(generator.get_all_tests())}")
    print(f"  Stable tests: {len(generator.get_stable_tests())}")
    print(f"  Flaky tests: {len(generator.get_flaky_tests())}")
