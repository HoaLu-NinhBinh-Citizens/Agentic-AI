"""Test harness generator (Phase 7.3).

Generates test harnesses for embedded firmware:
- Unity framework templates
- CppUTest framework templates
- GoogleTest for host testing
- Mock HAL interfaces
- Test fixtures
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TestFramework(Enum):
    """Supported test frameworks."""
    UNITY = "unity"
    CPUPUTEST = "cpputest"
    GOOGLETEST = "googletest"
    CUSTOM = "custom"


class MockStrategy(Enum):
    """Mock generation strategy."""
    INTERFACE_ONLY = "interface_only"
    STUB_IMPLEMENTATION = "stub"
    PARTIAL_MOCK = "partial"
    FULL_MOCK = "full"


@dataclass
class TestHarnessConfig:
    """Test harness configuration."""
    framework: TestFramework
    project_name: str
    output_dir: Path
    
    # Source
    source_dir: Path | None = None
    include_dirs: list[Path] = field(default_factory=list)
    
    # Mock settings
    mock_strategy: MockStrategy = MockStrategy.INTERFACE_ONLY
    mock_external_libs: bool = True
    
    # Test settings
    test_patterns: list[str] = field(default_factory=list)  # ["test_*.c", "*_test.c"]
    coverage_enabled: bool = True
    integration_tests: bool = True


@dataclass
class TestFile:
    """Generated test file."""
    path: Path
    content: str
    is_test: bool = True


@dataclass
class MockInterface:
    """Interface to mock."""
    name: str
    header_path: str
    functions: list[str] = field(default_factory=list)


@dataclass
class TestHarnessResult:
    """Result of harness generation."""
    success: bool
    test_files: list[TestFile] = field(default_factory=list)
    mock_files: list[TestFile] = field(default_factory=list)
    config_files: list[TestFile] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class UnityHarnessGenerator:
    """Unity framework harness generator."""
    
    FRAMEWORK_NAME = "Unity"
    
    def generate_harness(self, config: TestHarnessConfig) -> TestHarnessResult:
        """Generate Unity test harness."""
        result = TestHarnessResult(success=True)
        
        # Generate main test runner
        result.test_files.append(TestFile(
            path=config.output_dir / "test_runner.c",
            content=self._generate_runner(config),
        ))
        
        # Generate test runner header
        result.test_files.append(TestFile(
            path=config.output_dir / "test_runner.h",
            content=self._generate_runner_header(config),
        ))
        
        # Generate Unity configuration
        result.config_files.append(TestFile(
            path=config.output_dir / "unity_config.h",
            content=self._generate_unity_config(),
        ))
        
        # Generate makefile
        result.config_files.append(TestFile(
            path=config.output_dir / "Makefile",
            content=self._generate_makefile(config),
        ))
        
        return result
    
    def _generate_runner(self, config: TestHarnessConfig) -> str:
        """Generate test runner."""
        return '''/* Unity Test Runner - Auto-generated */
#include "unity_config.h"
#include "unity.h"
#include "test_runner.h"

/* SetUp and TearDown */
void setUp(void) {
    /* Initialize test environment */
}

void tearDown(void) {
    /* Cleanup test environment */
}

/* Test Groups */
void test_group_driver(void);
void test_group_peripheral(void);
void test_group_integration(void);

int main(void) {
    UNITY_BEGIN();
    
    RUN_TEST_GROUP(driver);
    RUN_TEST_GROUP(peripheral);
    RUN_TEST_GROUP(integration);
    
    return UNITY_END();
}
'''
    
    def _generate_runner_header(self, config: TestHarnessConfig) -> str:
        """Generate test runner header."""
        return '''/* Test Runner Header - Auto-generated */
#ifndef TEST_RUNNER_H
#define TEST_RUNNER_H

#include <stdint.h>

/* Mock HAL functions */
void HAL_UART_Init_Mock(void);
void HAL_GPIO_WritePin_Mock(uint16_t Pin, GPIO_PinState State);
GPIO_PinState HAL_GPIO_ReadPin(uint16_t Pin);

/* Test utilities */
void simulate_interrupt(uint8_t irq_num);
void mock_delay(uint32_t ms);

#endif /* TEST_RUNNER_H */
'''
    
    def _generate_unity_config(self) -> str:
        """Generate Unity configuration."""
        return '''/* Unity Configuration - Auto-generated */
#ifndef UNITY_CONFIG_H
#define UNITY_CONFIG_H

#define UNITY_INCLUDE_CONFIG_H
#define UNITY_FLOAT_PRECISION 0.001f
#define UNITY_DOUBLE_PRECISION 0.0001
#define UNITY_SUPPORT_64
#define UNITY_EXCLUDE_DETAILS

/* Memory allocation */
#include <stdlib.h>
#include <string.h>

/* Optional: Custom output */
#define UNITY_OUTPUT_CHAR(a)      putchar(a)
#define UNITY_OUTPUT_FLUSH()      fflush(stdout)
#define UNITY_OUTPUT_COMPLETE()    printf("\\n[All tests passed]\\n")

#endif /* UNITY_CONFIG_H */
'''
    
    def _generate_makefile(self, config: TestHarnessConfig) -> str:
        """Generate Makefile."""
        return f'''# Makefile - Auto-generated
CC = gcc
CFLAGS = -Wall -Wextra -g -I.
LDFLAGS =

# Unity framework
UNITY_DIR = vendor/unity
UNITY_SOURCES = $(UNITY_DIR)/src/unity.c

# Test files
TEST_SOURCES = $(wildcard tests/*.c)
TEST_OBJECTS = $(TEST_SOURCES:.c=.o)

# Sources under test
SRC_DIR = src
SRC_SOURCES = $(wildcard $(SRC_DIR)/*.c)
SRC_OBJECTS = $(SRC_SOURCES:.c=.o)

all: test

test: $(TEST_OBJECTS) $(SRC_OBJECTS) $(UNITY_SOURCES)
\t$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.c
\t$(CC) $(CFLAGS) -c -o $@ $<

clean:
\trm -f $(TEST_OBJECTS) $(SRC_OBJECTS) test

.PHONY: all test clean
'''


class CppUTestHarnessGenerator:
    """CppUTest framework harness generator."""
    
    FRAMEWORK_NAME = "CppUTest"
    
    def generate_harness(self, config: TestHarnessConfig) -> TestHarnessResult:
        """Generate CppUTest harness."""
        result = TestHarnessResult(success=True)
        
        # Generate test group
        result.test_files.append(TestFile(
            path=config.output_dir / "AllTests.cpp",
            content=self._generate_all_tests(),
        ))
        
        # Generate makefile
        result.config_files.append(TestFile(
            path=config.output_dir / "Makefile",
            content=self._generate_makefile(),
        ))
        
        return result
    
    def _generate_all_tests(self) -> str:
        """Generate all tests file."""
        return '''/* CppUTest Test Suite - Auto-generated */
#include <CppUTest/CommandLineTestRunner.h>

int main(int argc, char** argv) {
    return CommandLineTestRunner::RunAllTests(argc, argv);
}
'''


class GoogleTestHarnessGenerator:
    """GoogleTest harness generator."""
    
    FRAMEWORK_NAME = "GoogleTest"
    
    def generate_harness(self, config: TestHarnessConfig) -> TestHarnessResult:
        """Generate GoogleTest harness."""
        result = TestHarnessResult(success=True)
        
        # Generate main test file
        result.test_files.append(TestFile(
            path=config.output_dir / "firmware_test.cpp",
            content=self._generate_test_file(),
        ))
        
        # Generate mock HAL
        result.mock_files.append(TestFile(
            path=config.output_dir / "mock_hal.cpp",
            content=self._generate_mock_hal(),
        ))
        
        return result
    
    def _generate_test_file(self) -> str:
        """Generate test file."""
        return '''/* GoogleTest Firmware Test - Auto-generated */
#include <gtest/gtest.h>

extern "C" {
#include "firmware.h"
#include "hal_stub.h"
}

class FirmwareTest : public ::testing::Test {
protected:
    void SetUp() override {
        init_hal_stub();
    }
};

TEST_F(FirmwareTest, Initialization) {
    EXPECT_EQ(0, firmware_init());
}

TEST_F(FirmwareTest, StateTransitions) {
    firmware_set_state(STATE_READY);
    EXPECT_EQ(STATE_READY, firmware_get_state());
}
'''
    
    def _generate_mock_hal(self) -> str:
        """Generate mock HAL."""
        return '''/* Mock HAL Implementation - Auto-generated */
#include "hal_stub.h"

static int hal_initialized = 0;

void init_hal_stub(void) {
    hal_initialized = 1;
}

int hal_uart_write(const uint8_t* data, size_t len) {
    return len;
}
'''


class MockGenerator:
    """Generates mock implementations."""
    
    def generate_mocks(
        self,
        interfaces: list[MockInterface],
        strategy: MockStrategy,
    ) -> list[TestFile]:
        """Generate mock files for interfaces."""
        mocks = []
        
        for iface in interfaces:
            if strategy == MockStrategy.INTERFACE_ONLY:
                content = self._generate_interface_only_mock(iface)
            elif strategy == MockStrategy.STUB_IMPLEMENTATION:
                content = self._generate_stub_mock(iface)
            elif strategy == MockStrategy.PARTIAL_MOCK:
                content = self._generate_partial_mock(iface)
            else:
                content = self._generate_full_mock(iface)
            
            mocks.append(TestFile(
                path=Path(f"mock_{iface.name.lower()}.c"),
                content=content,
                is_test=True,
            ))
        
        return mocks
    
    def _generate_interface_only_mock(self, iface: MockInterface) -> str:
        """Generate interface-only mock."""
        return f'''/* Mock {iface.name} - Interface Only */
#include <stdint.h>
#include <stdbool.h>

/* Stub implementations */
'''
    
    def _generate_stub_mock(self, iface: MockInterface) -> str:
        """Generate stub mock."""
        return f'''/* Mock {iface.name} - Stub Implementation */
#include <stdint.h>

int {iface.name.lower()}_init(void) {{ return 0; }}
'''
    
    def _generate_partial_mock(self, iface: MockInterface) -> str:
        """Generate partial mock."""
        return f'''/* Mock {iface.name} - Partial Mock */
#include <stdint.h>
'''
    
    def _generate_full_mock(self, iface: MockInterface) -> str:
        """Generate full mock."""
        return f'''/* Mock {iface.name} - Full Mock */
#include <stdint.h>
#include <string.h>

static bool initialized = false;
'''


class TestHarnessGenerator:
    """Main test harness generator.
    
    Phase 7.3: Test harness generator (Unity, CppUTest, GTest)
    """
    
    def __init__(self) -> None:
        self._generators = {
            TestFramework.UNITY: UnityHarnessGenerator(),
            TestFramework.CPUPUTEST: CppUTestHarnessGenerator(),
            TestFramework.GOOGLETEST: GoogleTestHarnessGenerator(),
        }
        self._mock_gen = MockGenerator()
    
    def generate(self, config: TestHarnessConfig) -> TestHarnessResult:
        """Generate test harness."""
        generator = self._generators.get(config.framework)
        if not generator:
            return TestHarnessResult(
                success=False,
                errors=[f"Unsupported framework: {config.framework}"],
            )
        
        # Ensure output directory exists
        config.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate framework-specific harness
        result = generator.generate_harness(config)
        
        logger.info("Test harness generated", framework=config.framework.value)
        return result
    
    def generate_mocks(
        self,
        interfaces: list[MockInterface],
        strategy: MockStrategy = MockStrategy.INTERFACE_ONLY,
    ) -> list[TestFile]:
        """Generate mock implementations."""
        return self._mock_gen.generate_mocks(interfaces, strategy)


# Global generator
_generator: TestHarnessGenerator | None = None


def get_test_harness_generator() -> TestHarnessGenerator:
    """Get global test harness generator."""
    global _generator
    if _generator is None:
        _generator = TestHarnessGenerator()
    return _generator


if __name__ == "__main__":
    from pathlib import Path
    import tempfile
    
    # Test harness generation
    config = TestHarnessConfig(
        framework=TestFramework.UNITY,
        project_name="firmware_test",
        output_dir=Path(tempfile.mkdtemp()),
    )
    
    generator = get_test_harness_generator()
    result = generator.generate(config)
    
    print("Test Harness Generation")
    print("=" * 40)
    print(f"Success: {result.success}")
    print(f"Test files: {len(result.test_files)}")
    print(f"Config files: {len(result.config_files)}")
    
    for f in result.test_files:
        print(f"  - {f.path.name}")
    
    print("\nTest completed")
