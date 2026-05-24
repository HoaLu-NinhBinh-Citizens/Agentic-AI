"""Level 1-3 Test Scenarios - Reasoning, Tool Use, Repository Analysis.

LEVEL 1: Local Reasoning Tests
- Code understanding
- Off-by-one detection
- Memory violation detection
- Root cause analysis

LEVEL 2: Tool Use Tests
- Shell interaction
- File operations
- Test execution
- Build integration

LEVEL 3: Repository Reasoning Tests
- Cross-file dependency analysis
- Call graph tracing
- Architecture understanding
- Hidden bug discovery
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from tests.evaluation.framework import (
    EvaluationLevel,
    EvaluationMetrics,
    TestScenario,
    TestScenarioType,
    TrapScenario,
    VerificationResult,
)


# =============================================================================
# LEVEL 1: LOCAL REASONING TESTS
# =============================================================================

LEVEL_1_SCENARIOS: list[TestScenario] = []


def create_code_understanding_scenario() -> TestScenario:
    """Test scenario: Off-by-one bug detection in C code."""
    return TestScenario(
        scenario_id="l1_code_understanding_offbyone",
        name="Off-by-One Bug Detection",
        level=EvaluationLevel.LEVEL_1_REASONING,
        scenario_type=TestScenarioType.CODE_UNDERSTANDING,
        description="Detect off-by-one error in C loop that causes buffer overflow",
        task="""Analyze the following C code and find the bug:

int sum(int *arr, int size)
{
    int s = 0;
    for(int i = 0; i <= size; i++)
    {
        s += arr[i];
    }
    return s;
}

Find the bug, explain root cause, and provide the fix.""",
        max_iterations=3,
        timeout_seconds=30.0,
        expected_tools=["read", "analyze", "explain"],
    )


def create_memory_violation_scenario() -> TestScenario:
    """Test scenario: Memory violation detection."""
    return TestScenario(
        scenario_id="l1_memory_violation",
        name="Memory Violation Detection",
        level=EvaluationLevel.LEVEL_1_REASONING,
        scenario_type=TestScenarioType.MEMORY_VIOLATION,
        description="Detect memory access violation in ISR code",
        task="""Analyze this embedded C code for memory violations:

volatile uint32_t *const UART_BASE = (volatile uint32_t *)0x40013800;
volatile uint32_t *const RX_BUFFER = (volatile uint32_t *)0x20000000;
static uint8_t rx_buf[8];

void UART_IRQHandler(void)
{
    uint8_t idx = 0;
    if (UART_BASE[5] & 0x20) {  // RXNE flag
        rx_buf[idx++] = UART_BASE[4];  // Read data
        if (idx >= 10) {  // BUG: buffer is only 8 bytes
            idx = 0;
        }
    }
}

Identify all memory-related issues and explain the consequences.""",
        max_iterations=3,
        timeout_seconds=30.0,
        expected_tools=["analyze", "explain", "identify"],
    )


def create_register_decode_scenario() -> TestScenario:
    """Test scenario: Register analysis for embedded."""
    return TestScenario(
        scenario_id="l1_register_decode",
        name="SPI Register Decode",
        level=EvaluationLevel.LEVEL_1_REASONING,
        scenario_type=TestScenarioType.CODE_UNDERSTANDING,
        description="Decode SPI register configuration and find invalid mode",
        task="""Decode this SPI configuration:

SPI_CR1 = 0x0347;

Given the STM32 SPI_CR1 register:
- Bit 0: CPHA (clock phase)
- Bit 1: CPOL (clock polarity)
- Bit 2: MSTR (master selection)
- Bit 3-4: BR[2:0] (baud rate)
- Bit 5: SPE (SPI enable)
- Bit 6: LSBFIRST (frame format)
- Bit 7: SSI (internal slave select)
- Bit 8: SSM (software slave management)
- Bit 9: RXONLY (receive only)
- Bit 10: CRCL (CRC length)
- Bit 11: CRCEN (CRC enable)
- Bit 12: BIDIOE (output enable)
- Bit 13: BIDIMODE (bidirectional mode)

Decode the binary value, identify the configuration, and find any issues.""",
        max_iterations=3,
        timeout_seconds=30.0,
        expected_tools=["analyze", "decode", "explain"],
    )


LEVEL_1_SCENARIOS = [
    create_code_understanding_scenario(),
    create_memory_violation_scenario(),
    create_register_decode_scenario(),
]


# =============================================================================
# LEVEL 2: TOOL USE TESTS
# =============================================================================

LEVEL_2_SCENARIOS: list[TestScenario] = []


def create_shell_interaction_scenario() -> TestScenario:
    """Test scenario: Shell interaction with repository."""
    return TestScenario(
        scenario_id="l2_shell_interaction",
        name="Shell Tool Interaction",
        level=EvaluationLevel.LEVEL_2_TOOL_USE,
        scenario_type=TestScenarioType.TOOL_SEQUENCE,
        description="Use shell tools to explore and fix failing tests",
        task="""Repository structure:
- tests/test_flash.c (has failing test)
- src/flash/flash_driver.c
- include/flash.h

Task: Fix the failing unit test by:
1. Running the tests to see the failure
2. Reading the test file to understand what's expected
3. Reading the implementation to find the bug
4. Fixing the bug
5. Verifying the fix passes tests

Use shell commands: ls, cat, pytest, grep""",
        max_iterations=10,
        timeout_seconds=120.0,
        expected_tools=["shell", "read", "edit", "pytest", "grep"],
    )


def create_build_integration_scenario() -> TestScenario:
    """Test scenario: Build system integration."""
    return TestScenario(
        scenario_id="l2_build_integration",
        name="Build System Integration",
        level=EvaluationLevel.LEVEL_2_TOOL_USE,
        scenario_type=TestScenarioType.TOOL_SEQUENCE,
        description="Use build tools to compile and identify issues",
        task="""Task: Build the firmware project and fix any compilation errors.

Expected workflow:
1. List project structure
2. Run build command
3. Analyze errors
4. Fix issues in source files
5. Rebuild and verify

Use available tools to complete the build cycle.""",
        max_iterations=15,
        timeout_seconds=180.0,
        expected_tools=["shell", "read", "edit", "build"],
    )


def create_test_sequence_scenario() -> TestScenario:
    """Test scenario: Multi-step test sequence."""
    return TestScenario(
        scenario_id="l2_test_sequence",
        name="Multi-Step Test Sequence",
        level=EvaluationLevel.LEVEL_2_TOOL_USE,
        scenario_type=TestScenarioType.TOOL_SEQUENCE,
        description="Execute a sequence of tests and analyze results",
        task="""Task: Run the following test sequence and analyze results:

1. Run: pytest tests/unit/test_flash.c -v
2. Run: pytest tests/unit/test_gpio.c -v
3. Run: pytest tests/integration/test_hardware.c -v
4. Aggregate results
5. Identify which test category has most failures
6. Suggest fixes for the top 3 failures

Report the complete analysis.""",
        max_iterations=20,
        timeout_seconds=300.0,
        expected_tools=["shell", "pytest", "aggregate", "analyze"],
    )


LEVEL_2_SCENARIOS = [
    create_shell_interaction_scenario(),
    create_build_integration_scenario(),
    create_test_sequence_scenario(),
]


# =============================================================================
# LEVEL 3: REPOSITORY REASONING TESTS
# =============================================================================

LEVEL_3_SCENARIOS: list[TestScenario] = []


def create_cross_file_dependency_scenario() -> TestScenario:
    """Test scenario: Cross-file dependency analysis."""
    return TestScenario(
        scenario_id="l3_cross_file_dependency",
        name="Cross-File Dependency Analysis",
        level=EvaluationLevel.LEVEL_3_REPO_REASONING,
        scenario_type=TestScenarioType.CROSS_FILE_DEPENDENCY,
        description="Trace bug across multiple files to find root cause",
        task="""Bug symptom: Application times out waiting for sensor data.

Repository structure:
- app/main.c (timeout in sensor_read())
- middleware/sensor_hub.c (callback never fires)
- drivers/sensor.c (I2C communication)
- drivers/i2c.c (bus configuration)
- config/clock_config.h (clock settings)

Task:
1. Trace the call chain from timeout to root cause
2. Inspect all involved files
3. Identify the hidden dependency issue
4. Explain why the callback never fires
5. Provide the fix

The bug is NOT in the file where the symptom appears.""",
        max_iterations=15,
        timeout_seconds=180.0,
        expected_tools=["grep", "read", "trace", "analyze"],
    )


def create_call_graph_analysis_scenario() -> TestScenario:
    """Test scenario: Call graph analysis for RTOS."""
    return TestScenario(
        scenario_id="l3_call_graph_rtos",
        name="RTOS Call Graph Analysis",
        level=EvaluationLevel.LEVEL_3_REPO_REASONING,
        scenario_type=TestScenarioType.CROSS_FILE_DEPENDENCY,
        description="Analyze RTOS task dependencies and find deadlock",
        task="""Task: Analyze the FreeRTOS application for potential deadlock.

Files:
- rtos_tasks.c (task definitions and priorities)
- rtos_mutex.c (mutex definitions)
- rtos_isr.c (interrupt handlers)
- app_sensor.c (sensor task)
- app_display.c (display task)

Known symptom: System hangs after ~5 minutes of operation.

Analyze:
1. Task priorities and potential priority inversion
2. Mutex acquisition order
3. ISR/task interaction points
4. Resource dependency graph
5. Identify the deadlock chain

Build a complete deadlock scenario explanation.""",
        max_iterations=20,
        timeout_seconds=240.0,
        expected_tools=["grep", "read", "trace", "analyze", "graph"],
    )


def create_architecture_reasoning_scenario() -> TestScenario:
    """Test scenario: Architecture-level reasoning."""
    return TestScenario(
        scenario_id="l3_architecture_reasoning",
        name="Bootloader Architecture Reasoning",
        level=EvaluationLevel.LEVEL_3_REPO_REASONING,
        scenario_type=TestScenarioType.CROSS_FILE_DEPENDENCY,
        description="Understand multi-stage bootloader architecture",
        task="""Task: Analyze the bootloader architecture to understand boot flow.

Repository structure:
- bootloader/stage1.S (reset handler)
- bootloader/stage2.c (memory init)
- bootloader/flash.c (flash driver)
- bootloader/secure_boot.c (signature verification)
- app/main.c (application entry)
- config/linker.ld (memory map)

Questions:
1. What is the boot sequence from reset to application?
2. Where is the vector table located?
3. How does secure boot verify the application?
4. What flash regions are used for what purpose?
5. What could cause boot failure at each stage?

Provide architectural analysis with references to specific files.""",
        max_iterations=15,
        timeout_seconds=200.0,
        expected_tools=["read", "grep", "analyze", "explain"],
    )


LEVEL_3_SCENARIOS = [
    create_cross_file_dependency_scenario(),
    create_call_graph_analysis_scenario(),
    create_architecture_reasoning_scenario(),
]


# =============================================================================
# VERIFICATION FUNCTIONS
# =============================================================================

async def verify_off_by_one(result: dict[str, Any]) -> VerificationResult:
    """Verify off-by-one fix is correct."""
    # Check if response mentions i < size (not i <= size)
    response = result.get("response", "").lower()
    
    has_fix = "i < size" in response or "i < n" in response
    has_explanation = "off-by-one" in response or "boundary" in response
    
    if has_fix and has_explanation:
        return VerificationResult(
            passed=True,
            message="Correctly identified off-by-one error",
            details={"fix_detected": True, "explanation_detected": True},
        )
    
    return VerificationResult(
        passed=False,
        message="Did not correctly identify and fix off-by-one",
        details={"fix_detected": has_fix, "explanation_detected": has_explanation},
    )


async def verify_memory_violation(result: dict[str, Any]) -> VerificationResult:
    """Verify memory violation detection."""
    response = result.get("response", "").lower()
    
    has_buffer_overflow = "buffer overflow" in response or "out of bounds" in response
    has_isr_issue = "isr" in response or "interrupt" in response
    
    if has_buffer_overflow and has_isr_issue:
        return VerificationResult(
            passed=True,
            message="Correctly identified memory violation",
            details={"buffer_overflow_detected": True, "isr_context_detected": True},
        )
    
    return VerificationResult(
        passed=False,
        message="Did not fully identify memory violation issues",
        details={"buffer_overflow_detected": has_buffer_overflow, "isr_context_detected": has_isr_issue},
    )


async def verify_register_decode(result: dict[str, Any]) -> VerificationResult:
    """Verify register decoding."""
    response = result.get("response", "").lower()
    
    # Check for correct bit analysis
    has_br_field = "baud" in response or "br[2:0]" in response
    has_mstr = "master" in response
    has_spe = "enable" in response
    
    if has_br_field and has_mstr and has_spe:
        return VerificationResult(
            passed=True,
            message="Correctly decoded register configuration",
            details={"bit_fields_identified": True},
        )
    
    return VerificationResult(
        passed=False,
        message="Register decoding incomplete",
        details={"bit_fields_identified": has_br_field and has_mstr},
    )


# =============================================================================
# SCENARIO REGISTRY
# =============================================================================

def get_all_level_1_scenarios() -> list[TestScenario]:
    """Get all Level 1 scenarios."""
    return LEVEL_1_SCENARIOS.copy()


def get_all_level_2_scenarios() -> list[TestScenario]:
    """Get all Level 2 scenarios."""
    return LEVEL_2_SCENARIOS.copy()


def get_all_level_3_scenarios() -> list[TestScenario]:
    """Get all Level 3 scenarios."""
    return LEVEL_3_SCENARIOS.copy()


def get_all_early_scenarios() -> list[TestScenario]:
    """Get all Level 1-3 scenarios combined."""
    return LEVEL_1_SCENARIOS + LEVEL_2_SCENARIOS + LEVEL_3_SCENARIOS
