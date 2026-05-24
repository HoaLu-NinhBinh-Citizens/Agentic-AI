"""Level 4-7 Test Scenarios - Long Horizon, Recovery, Debugging, Multi-Agent.

LEVEL 4: Long Horizon Agent Loop
- Multi-phase tasks (10-50 steps)
- Plan consistency over time
- Context retention
- Architecture preservation

LEVEL 5: Failure Recovery
- Deliberate traps
- Misleading logs
- Flaky tests
- Safe rollback

LEVEL 6: Autonomous Debugging
- Firmware crash analysis
- GDB/OpenOCD integration
- Stack trace analysis
- Hardware fault injection

LEVEL 7: Multi-Agent Orchestration
- Sub-agent delegation
- Output merging
- Conflict resolution
- Architecture preservation
"""

from __future__ import annotations

import asyncio
from typing import Any

from tests.evaluation.framework import (
    EvaluationLevel,
    TestScenario,
    TestScenarioType,
    TrapScenario,
    VerificationResult,
)


# =============================================================================
# LEVEL 4: LONG HORIZON AGENT LOOP
# =============================================================================

LEVEL_4_SCENARIOS: list[TestScenario] = []


def create_ota_update_system_scenario() -> TestScenario:
    """Test scenario: Add OTA update system (long horizon task)."""
    return TestScenario(
        scenario_id="l4_ota_update_system",
        name="OTA Update System Implementation",
        level=EvaluationLevel.LEVEL_4_LONG_HORIZON,
        scenario_type=TestScenarioType.LONG_HORIZON_TASK,
        description="Implement complete OTA update system across 50+ steps",
        task="""Task: Add OTA (Over-The-Air) update system to the firmware.

Requirements:
1. AES-256 verification of update images
2. Rollback mechanism on failed update
3. Version control with dual-bank flash
4. Boot flag management
5. Flash partition management
6. Test coverage for all components

Constraints:
- Flash layout: Bank A (0x08000000), Bank B (0x08040000)
- Must preserve existing functionality
- Cannot break existing APIs
- Must handle power failure during update

Expected phases:
1. Design architecture
2. Create flash layout
3. Implement bootloader integration
4. Implement AES verification
5. Implement rollback logic
6. Add version management
7. Write tests
8. Verify compilation

This is a 20+ step task requiring plan consistency.""",
        max_iterations=50,
        timeout_seconds=600.0,
        expected_tools=["read", "write", "analyze", "design", "test"],
        trap_enabled=True,
        failure_injection={
            "misleading_log": {"message": "Error: Flash write timeout in bank switch"},
            "partial_fix": {"side_effect": "Causes heap corruption"},
        },
    )


def create_rtos_scheduler_refactor_scenario() -> TestScenario:
    """Test scenario: Refactor RTOS scheduler (long horizon)."""
    return TestScenario(
        scenario_id="l4_rtos_scheduler_refactor",
        name="RTOS Scheduler Refactoring",
        level=EvaluationLevel.LEVEL_4_LONG_HORIZON,
        scenario_type=TestScenarioType.LONG_HORIZON_TASK,
        description="Refactor scheduler while preserving all task semantics",
        task="""Task: Refactor the FreeRTOS scheduler to support priority inheritance.

Current state:
- Fixed priority scheduling
- No priority inversion prevention
- Tasks in src/rtos/tasks.c

Required changes:
1. Implement mutex priority inheritance
2. Add priority ceiling protocol
3. Modify task control blocks
4. Update scheduler core
5. Add inheritance chain tracking
6. Update all mutex implementations
7. Add tests for inheritance scenarios
8. Verify no regression in existing tasks

Critical constraints:
- Cannot change task API
- Must maintain existing task priorities
- Cannot break ISR compatibility
- Must preserve timing behavior

This tests long-horizon consistency and architecture preservation.""",
        max_iterations=40,
        timeout_seconds=480.0,
        expected_tools=["read", "write", "analyze", "refactor", "test"],
        trap_enabled=True,
        failure_injection={
            "api_drift": {"description": "May try to change task_create signature"},
        },
    )


def create_can_stack_implementation_scenario() -> TestScenario:
    """Test scenario: Implement CAN stack (complex long horizon)."""
    return TestScenario(
        scenario_id="l4_can_stack_implementation",
        name="CAN Communication Stack Implementation",
        level=EvaluationLevel.LEVEL_4_LONG_HORIZON,
        scenario_type=TestScenarioType.LONG_HORIZON_TASK,
        description="Implement complete CAN stack from scratch",
        task="""Task: Implement a CAN 2.0B communication stack.

Components required:
1. CAN hardware abstraction layer (HAL)
2. CAN driver for FDCAN peripheral
3. Message filtering configuration
4. TX/RX message queues
5. Error handling and bus-off recovery
6. Bit timing configuration
7. Loopback mode for testing
8. Integration with FreeRTOS queues

Requirements:
- Support 11-bit standard and 29-bit extended IDs
- Implement full CAN frame structure
- Handle error frames and overload frames
- Support multiple filters
- Provide timeout mechanism
- Include diagnostic capabilities

Test coverage:
- Unit tests for each layer
- Integration tests
- Error injection tests
- Performance benchmarks

This is a 30+ step implementation task.""",
        max_iterations=60,
        timeout_seconds=720.0,
        expected_tools=["write", "read", "test", "analyze", "benchmark"],
    )


LEVEL_4_SCENARIOS = [
    create_ota_update_system_scenario(),
    create_rtos_scheduler_refactor_scenario(),
    create_can_stack_implementation_scenario(),
]


# =============================================================================
# LEVEL 5: FAILURE RECOVERY TESTS
# =============================================================================

LEVEL_5_SCENARIOS: list[TestScenario] = []


def create_deliberate_trap_scenario() -> TestScenario:
    """Test scenario: Deliberate traps to test recovery."""
    trap = TrapScenario.get_trap("fake_compiler_error")
    
    return TestScenario(
        scenario_id="l5_deliberate_trap",
        name="Recovery from Deliberate Traps",
        level=EvaluationLevel.LEVEL_5_FAILURE_RECOVERY,
        scenario_type=TestScenarioType.FAILURE_INJECTION,
        description="Test agent recovery from misleading compiler errors",
        task=f"""Task: Fix the UART initialization error.

The build fails with this error:
```
{trap['message']}
```

But this is a TRAP - the real issue is elsewhere.

You need to:
1. Analyze the actual error (not the misleading one)
2. Trace to the true root cause
3. Apply correct fix
4. Verify compilation succeeds

The agent must NOT:
- Randomly edit files hoping something works
- Apply superficial fixes
- Ignore the actual error location

Success requires genuine reasoning and safe rollback.""",
        max_iterations=10,
        timeout_seconds=120.0,
        expected_tools=["read", "analyze", "grep", "build"],
        trap_enabled=True,
        failure_injection={
            "fake_compiler_error": {"message": trap['message']},
            "misleading_log": {"message": "Hint: Check TIM_HandleTypeDef declaration"},
        },
    )


def create_flaky_test_recovery_scenario() -> TestScenario:
    """Test scenario: Handle flaky tests."""
    return TestScenario(
        scenario_id="l5_flaky_test_recovery",
        name="Flaky Test Recovery",
        level=EvaluationLevel.LEVEL_5_FAILURE_RECOVERY,
        scenario_type=TestScenarioType.FAILURE_INJECTION,
        description="Handle flaky tests without random patching",
        task="""Task: Fix the intermittent test failure.

Symptom: Test passes 70% of time, fails 30% with:
```
AssertionError: expected True, got False
```

The test is in: tests/unit/test_timing.c::test_isr_latency

This is a TRAP scenario:

The test checks ISR latency with a 10% tolerance.
But the real issue is:
1. Test runs without disabling interrupts
2. Other tasks cause timing jitter
3. Flaky because system load varies

You need to:
1. Analyze why test is flaky (not random)
2. Identify the real timing issue
3. Fix test to properly isolate timing
4. Do NOT just increase tolerance blindly

Proper fix: Add proper test isolation, not tolerance increase.""",
        max_iterations=8,
        timeout_seconds=90.0,
        expected_tools=["read", "analyze", "pytest", "fix"],
        trap_enabled=True,
        failure_injection={
            "flaky_test": {"always_fail": False},
        },
    )


def create_api_hallucination_trap_scenario() -> TestScenario:
    """Test scenario: Detect API hallucination."""
    trap = TrapScenario.get_trap("api_hallucination")
    
    return TestScenario(
        scenario_id="l5_api_hallucination_trap",
        name="API Hallucination Detection",
        level=EvaluationLevel.LEVEL_5_FAILURE_RECOVERY,
        scenario_type=TestScenarioType.FAILURE_INJECTION,
        description="Detect when agent invents non-existent APIs",
        task=f"""Task: Implement PWM output using STM32 HAL.

The agent tried to use: {trap['fake_api']}

But this API does NOT exist!

The correct API is: {trap['real_api']}

Your task:
1. Verify the suggested API exists in HAL
2. If it doesn't, find the correct alternative
3. Implement PWM output correctly
4. Write test to verify PWM generation

Scoring:
- FAIL: Uses non-existent API
- PASS: Uses correct HAL API
- BONUS: Explains why the hallucinated API was wrong""",
        max_iterations=5,
        timeout_seconds=60.0,
        expected_tools=["read", "analyze", "write", "verify"],
        trap_enabled=True,
        failure_injection={
            "api_hallucination": {"fake_api": trap['fake_api']},
        },
    )


def create_partial_fix_trap_scenario() -> TestScenario:
    """Test scenario: Detect partial fixes that cause regression."""
    return TestScenario(
        scenario_id="l5_partial_fix_trap",
        name="Partial Fix Detection",
        level=EvaluationLevel.LEVEL_5_FAILURE_RECOVERY,
        scenario_type=TestScenarioType.FAILURE_INJECTION,
        description="Detect when fix causes regression elsewhere",
        task="""Task: Fix the UART buffer overflow issue.

Symptom: UART data gets corrupted during heavy traffic.

Initial analysis suggests: buffer is too small (16 bytes)

Agent applies: Increase buffer to 256 bytes

This is a TRAP!

The real issue:
1. Buffer IS being filled correctly
2. Problem is in ISR: buffer index not reset after overflow
3. Large buffer just delays the symptom

The correct fix:
1. Reset buffer index to 0 after processing
2. Add overflow detection
3. Optionally increase buffer as secondary measure

You must identify the ROOT CAUSE, not just symptoms.

Demonstrate that the fix doesn't cause regressions elsewhere.""",
        max_iterations=8,
        timeout_seconds=90.0,
        expected_tools=["read", "analyze", "fix", "test"],
        trap_enabled=True,
        failure_injection={
            "partial_fix": {"side_effect": "heap corruption in large buffer case"},
        },
    )


LEVEL_5_SCENARIOS = [
    create_deliberate_trap_scenario(),
    create_flaky_test_recovery_scenario(),
    create_api_hallucination_trap_scenario(),
    create_partial_fix_trap_scenario(),
]


# =============================================================================
# LEVEL 6: AUTONOMOUS DEBUGGING (EMBEDDED-SPECIFIC)
# =============================================================================

LEVEL_6_SCENARIOS: list[TestScenario] = []


def create_firmware_crash_scenario() -> TestScenario:
    """Test scenario: Analyze firmware crash."""
    return TestScenario(
        scenario_id="l6_firmware_crash",
        name="Firmware Crash Analysis",
        level=EvaluationLevel.LEVEL_6_AUTONOMOUS_DEBUGGING,
        scenario_type=TestScenarioType.FIRMWARE_CRASH,
        description="Analyze Guru Meditation / HardFault and fix",
        task="""Task: Debug the firmware crash.

Environment:
- Device: STM32F4 (ARM Cortex-M4)
- Debugger: J-Link with OpenOCD
- Symbols: firmware.elf.map
- UART log attached

Crash Information:
```
Guru Meditation Error
PC=0x08002456
LR=0x08003ABC
PSR=0x61000000
CFSR=0x00008201
HFSR=0x40000000

Memory fault at address 0x2001FFFC
Bus fault during instruction fetch
```

Available tools:
- addr2line -e firmware.elf 0x08002456
- gdb firmware.elf
- openocd -f stm32f4.cfg
- cat uart_log.txt

Tasks:
1. Symbolize the PC address
2. Analyze stack trace
3. Identify fault type from CFSR
4. Find the buggy instruction
5. Identify root cause
6. Fix the issue
7. Verify fix with debugger""",
        max_iterations=15,
        timeout_seconds=180.0,
        expected_tools=["addr2line", "gdb", "read", "analyze", "fix"],
    )


def create_rtos_deadlock_debug_scenario() -> TestScenario:
    """Test scenario: Debug RTOS deadlock."""
    return TestScenario(
        scenario_id="l6_rtos_deadlock",
        name="RTOS Deadlock Debugging",
        level=EvaluationLevel.LEVEL_6_AUTONOMOUS_DEBUGGING,
        scenario_type=TestScenarioType.FIRMWARE_CRASH,
        description="Analyze FreeRTOS trace for deadlock",
        task="""Task: Find and fix the RTOS deadlock.

FreeRTOS trace analysis:
```
Task: SensorTask (Priority: 5)
  State: Blocked
  Blocked on: I2C_Mutex
  Wait time: 5000ms

Task: DisplayTask (Priority: 4)  
  State: Blocked
  Blocked on: SPI_Mutex
  Wait time: 3000ms

Task: CommTask (Priority: 6)
  State: Running
  
I2C_Mutex holder: CommTask
SPI_Mutex holder: DisplayTask
```

Deadlock chain:
- SensorTask holds SPI_Mutex, wants I2C_Mutex
- CommTask holds I2C_Mutex, wants SPI_Mutex

Tasks:
1. Verify the deadlock from trace
2. Identify the circular wait
3. Propose solution (ordered locking, try-lock, etc.)
4. Implement the fix
5. Verify with trace analysis

Must preserve task priorities and semantics.""",
        max_iterations=12,
        timeout_seconds=150.0,
        expected_tools=["analyze", "trace", "fix", "verify"],
    )


def create_timing_jitter_debug_scenario() -> TestScenario:
    """Test scenario: Debug timing jitter."""
    return TestScenario(
        scenario_id="l6_timing_jitter",
        name="Timing Jitter Debugging",
        level=EvaluationLevel.LEVEL_6_AUTONOMOUS_DEBUGGING,
        scenario_type=TestScenarioType.HARDWARE_FAULT,
        description="Analyze and fix timing jitter source",
        task="""Task: Debug timing jitter in control loop.

System: Motor control with 1kHz PWM
Symptom: Motor speed varies by ±5% even under constant load

Timing log:
```
[T=0.000] PWM update
[T=0.001] PWM update
[T=0.002] PWM update - DELAY 500us
[T=0.003] PWM update
[T=0.004] PWM update
...
```

The 500us delay happens every ~100 cycles.

Analysis needed:
1. Find what causes the periodic delay
2. Check for:
   - Garbage collection
   - Flash operations
   - DMA transfers
   - Interrupt nesting
   - Cache misses
3. Use timing analysis tools
4. Identify jitter source
5. Propose and implement fix

Expected: Jitter < 50us (0.05ms)

This tests deep embedded timing analysis.""",
        max_iterations=15,
        timeout_seconds=200.0,
        expected_tools=["analyze", "trace", "profile", "fix"],
    )


def create_linker_overflow_debug_scenario() -> TestScenario:
    """Test scenario: Debug linker/flash overflow."""
    return TestScenario(
        scenario_id="l6_linker_overflow",
        name="Linker Overflow Debugging",
        level=EvaluationLevel.LEVEL_6_AUTONOMOUS_DEBUGGING,
        scenario_type=TestScenarioType.FIRMWARE_CRASH,
        description="Debug .text section overflow",
        task="""Task: Debug flash overflow issue.

Build error:
```
build/firmware.elf section `.text' will not fit in region `FLASH'
region `FLASH' overflowed by 8192 bytes
```

Memory map:
```
FLASH:     ORIGIN = 0x08000000, LENGTH = 256K (0x40000)
RAM:       ORIGIN = 0x20000000, LENGTH = 64K (0x10000)
```

Current .text size: 264K (need to fit in 256K)

Tasks:
1. Analyze .text section contents (from .map file)
2. Identify largest components
3. Find opportunities for optimization:
   - Remove unused code
   - Enable linker garbage collection
   - Move constants to flash
   - Enable compiler optimizations
   - Use function inlining hints
4. Reduce size to < 256K
5. Verify all functionality

Tools: arm-none-eabi-size, arm-none-eabi-objdump, linker map""",
        max_iterations=20,
        timeout_seconds=240.0,
        expected_tools=["analyze", "size", "objdump", "optimize"],
    )


LEVEL_6_SCENARIOS = [
    create_firmware_crash_scenario(),
    create_rtos_deadlock_debug_scenario(),
    create_timing_jitter_debug_scenario(),
    create_linker_overflow_debug_scenario(),
]


# =============================================================================
# LEVEL 7: MULTI-AGENT ORCHESTRATION
# =============================================================================

LEVEL_7_SCENARIOS: list[TestScenario] = []


def create_subagent_orchestration_scenario() -> TestScenario:
    """Test scenario: Multi-agent task orchestration."""
    return TestScenario(
        scenario_id="l7_subagent_orchestration",
        name="Sub-Agent Task Orchestration",
        level=EvaluationLevel.LEVEL_7_MULTI_AGENT,
        scenario_type=TestScenarioType.MULTI_AGENT_ORCHESTRATION,
        description="Orchestrate multiple sub-agents for complex task",
        task="""Task: Refactor RTOS scheduler using sub-agents.

Main agent must coordinate:
1. Test Agent: Write comprehensive tests
2. Security Agent: Review for race conditions
3. Performance Agent: Analyze timing impact
4. Docs Agent: Update documentation

Workflow:
1. Main agent plans decomposition
2. Test Agent: Design test cases for priority inheritance
3. Security Agent: Review mutex acquisition order
4. Performance Agent: Measure context switch overhead
5. Docs Agent: Draft API documentation
6. Main agent: Merges outputs, resolves conflicts
7. Main agent: Produces final implementation

Constraints:
- Test Agent cannot modify core scheduler
- Security Agent only reviews, doesn't implement
- Performance Agent provides measurements only
- Docs Agent follows main agent's API design

Main agent must:
- Delegate appropriately
- Handle conflicting suggestions
- Preserve architecture
- Produce coherent final result""",
        max_iterations=30,
        timeout_seconds=400.0,
        expected_tools=["plan", "delegate", "merge", "review"],
    )


def create_conflict_resolution_scenario() -> TestScenario:
    """Test scenario: Resolve conflicts between sub-agents."""
    return TestScenario(
        scenario_id="l7_conflict_resolution",
        name="Multi-Agent Conflict Resolution",
        level=EvaluationLevel.LEVEL_7_MULTI_AGENT,
        scenario_type=TestScenarioType.MULTI_AGENT_ORCHESTRATION,
        description="Resolve conflicting suggestions from sub-agents",
        task="""Task: Implement CAN driver with conflicting sub-agent outputs.

Sub-agents produced:

Test Agent:
- "Add 1ms timeout to all CAN operations"
- "Use interrupt-driven TX/RX"

Security Agent:
- "Add message authentication (CAN IDs are not secure)"
- "Implement message filtering"

Performance Agent:
- "Use DMA for RX to reduce CPU load"
- "Batch TX messages"

Conflicts:
1. Test says: interrupt-driven
   Performance says: DMA
   → Need to choose or combine

2. Security says: add auth (increases latency)
   Performance says: minimize latency
   → Need to trade off

3. Test says: 1ms timeout
   Performance says: batch TX
   → Timeout vs batching conflict

Your task:
1. Analyze each suggestion
2. Identify conflicts
3. Propose resolution for each conflict
4. Implement final design
5. Document trade-offs made

Must produce coherent architecture.""",
        max_iterations=25,
        timeout_seconds=300.0,
        expected_tools=["analyze", "resolve", "implement", "document"],
    )


def create_multi_agent_verification_scenario() -> TestScenario:
    """Test scenario: Cross-validation between agents."""
    return TestScenario(
        scenario_id="l7_multi_agent_verification",
        name="Cross-Agent Verification",
        level=EvaluationLevel.LEVEL_7_MULTI_AGENT,
        scenario_type=TestScenarioType.MULTI_AGENT_ORCHESTRATION,
        description="Verify implementation across multiple agent domains",
        task="""Task: Implement and cross-verify CAN stack.

Agents involved:
1. Driver Agent: Implements CAN peripheral driver
2. Protocol Agent: Implements CAN protocol layer
3. Integration Agent: Integrates with FreeRTOS

Verification chain:
1. Driver Agent: Implemented CAN peripheral init
2. Protocol Agent: Uses driver to send/receive frames
3. Integration Agent: Wraps in RTOS tasks

Cross-verification points:
- Protocol Agent verifies driver TX completes
- Integration Agent verifies no priority inversion
- Driver Agent verifies protocol timing requirements

Each agent must:
1. Implement their layer
2. Test their layer
3. Verify interfaces with adjacent layers
4. Report findings to main agent

Final deliverable: Verified CAN stack across all layers""",
        max_iterations=35,
        timeout_seconds=450.0,
        expected_tools=["implement", "test", "verify", "integrate"],
    )


LEVEL_7_SCENARIOS = [
    create_subagent_orchestration_scenario(),
    create_conflict_resolution_scenario(),
    create_multi_agent_verification_scenario(),
]


# =============================================================================
# SCENARIO REGISTRY
# =============================================================================

def get_all_level_4_scenarios() -> list[TestScenario]:
    return LEVEL_4_SCENARIOS.copy()


def get_all_level_5_scenarios() -> list[TestScenario]:
    return LEVEL_5_SCENARIOS.copy()


def get_all_level_6_scenarios() -> list[TestScenario]:
    return LEVEL_6_SCENARIOS.copy()


def get_all_level_7_scenarios() -> list[TestScenario]:
    return LEVEL_7_SCENARIOS.copy()


def get_all_advanced_scenarios() -> list[TestScenario]:
    return LEVEL_4_SCENARIOS + LEVEL_5_SCENARIOS + LEVEL_6_SCENARIOS + LEVEL_7_SCENARIOS


def get_all_scenarios() -> list[TestScenario]:
    from tests.evaluation.scenarios_levels_1_3 import get_all_early_scenarios
    return get_all_early_scenarios() + get_all_advanced_scenarios()
