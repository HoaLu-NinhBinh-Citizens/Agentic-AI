"""Debugging workflow - diagnose and fix firmware issues."""

from __future__ import annotations

from typing import Any

import structlog

from src.application.workflows.base import BaseWorkflow, WorkflowStatus

logger = structlog.get_logger(__name__)


class DebuggingWorkflow(BaseWorkflow):
    """
    Workflow for debugging embedded firmware issues.

    Pipeline:
    1. Parse error/symptom description
    2. Categorize issue type
    3. Run reasoning over hardware constraints
    4. Query KB for similar past issues
    5. Generate diagnostic plan
    6. Return root cause analysis and fix suggestions

    Usage:
        wf = DebuggingWorkflow(context={
            "symptom": "CAN messages not being transmitted",
            "chip_family": "STM32F407",
            "last_working": "GPIO interrupt worked before",
        })
        result = await wf.run()
    """

    @property
    def name(self) -> str:
        return "Debugging Workflow"

    @property
    def description(self) -> str:
        return "Diagnose firmware issues and generate fix recommendations"

    async def _execute(self) -> dict[str, Any]:
        symptom = self.context.get("symptom", "")
        chip_family = self.context.get("chip_family", "STM32F4")
        last_working = self.context.get("last_working", "")
        related_files = self.context.get("related_files", [])
        error_logs = self.context.get("error_logs", [])

        # Step 1: Categorize issue
        step_categorize = self.add_step(
            "categorize", "Categorize Issue", "Classify issue type from symptom"
        )
        issue_type, related_peripherals = await self.run_step(
            "categorize",
            self._categorize_issue,
            symptom,
        )

        # Step 2: Query KB for similar issues
        step_kb = self.add_step(
            "kb_lookup", "KB Lookup", "Find similar past issues in knowledge base"
        )
        past_issues = await self.run_step(
            "kb_lookup",
            self._query_past_issues,
            symptom,
            issue_type,
            chip_family,
        )

        # Step 3: Analyze error logs
        step_logs = self.add_step(
            "analyze_logs", "Analyze Logs", "Parse and analyze error logs"
        )
        log_analysis = await self.run_step(
            "analyze_logs",
            self._analyze_logs,
            error_logs,
        )

        # Step 4: Generate diagnostic plan
        step_diagnose = self.add_step(
            "diagnose", "Diagnose", "Identify root cause from evidence"
        )
        diagnosis = await self.run_step(
            "diagnose",
            self._diagnose,
            symptom,
            issue_type,
            past_issues,
            log_analysis,
            related_peripherals,
        )

        # Step 5: Generate fix recommendations
        step_fix = self.add_step(
            "fix", "Generate Fix", "Produce actionable fix recommendations"
        )
        fixes = await self.run_step(
            "fix",
            self._generate_fixes,
            diagnosis,
            issue_type,
            chip_family,
            related_peripherals,
        )

        return {
            "symptom": symptom,
            "issue_type": issue_type,
            "root_cause": diagnosis.get("root_cause"),
            "confidence": diagnosis.get("confidence", 0.0),
            "past_issues": past_issues,
            "log_analysis": log_analysis,
            "fixes": fixes,
            "diagnostic_plan": diagnosis.get("plan"),
        }

    async def _categorize_issue(
        self,
        symptom: str,
    ) -> tuple[str, list[str]]:
        """Categorize the issue type from symptom description."""
        symptom_lower = symptom.lower()
        peripherals: list[str] = []

        if any(k in symptom_lower for k in ["can", "can1", "can2", "no tx", "no rx", "no message"]):
            issue_type = "peripheral_init"
            peripherals = ["CAN1", "GPIOD"]
        elif any(k in symptom_lower for k in ["uart", "serial", "usart", "printf", "print"]):
            issue_type = "peripheral_init"
            peripherals = ["USART1", "GPIOA"]
        elif any(k in symptom_lower for k in ["gpio", "pin", "led", "button"]):
            issue_type = "gpio_config"
            peripherals = ["GPIOA", "GPIOB"]
        elif any(k in symptom_lower for k in ["timer", "pwm", "duty", "frequency"]):
            issue_type = "timing_config"
            peripherals = ["TIM3", "TIM4"]
        elif any(k in symptom_lower for k in ["dma", "transfer", "memory"]):
            issue_type = "dma_config"
            peripherals = ["DMA1", "DMA2"]
        elif any(k in symptom_lower for k in ["interrupt", "irq", "handler", "nvic"]):
            issue_type = "interrupt_config"
            peripherals = ["NVIC", "EXTI"]
        elif any(k in symptom_lower for k in ["clock", "pll", "hse", "hsi"]):
            issue_type = "clock_config"
            peripherals = ["RCC", "PLL"]
        elif any(k in symptom_lower for k in ["hang", "freeze", "crash", "reset", "hardfault"]):
            issue_type = "runtime_error"
            peripherals = ["SCB", "NVIC"]
        elif any(k in symptom_lower for k in ["spi", "i2c", "sensor"]):
            issue_type = "bus_protocol"
            peripherals = ["SPI1", "I2C1"]
        else:
            issue_type = "unknown"
            peripherals = []

        logger.debug("issue_categorized", issue_type=issue_type, peripherals=peripherals)
        return issue_type, peripherals

    async def _query_past_issues(
        self,
        symptom: str,
        issue_type: str,
        chip_family: str,
    ) -> list[dict[str, Any]]:
        """Query KB for similar past issues."""
        if not self._knowledge_base:
            return []

        results = await self._knowledge_base.query_by_type(
            entry_type=__import__(
                "src.domain.knowledge.kb", fromlist=["KBEntryType"]
            ).KBEntryType.ERROR_ANALYSIS,
            chip_family=chip_family,
            top_k=5,
        )

        return [
            {
                "title": r.entry.title,
                "content": r.entry.content[:300],
                "source": r.entry.source,
                "score": r.score,
            }
            for r in results
        ]

    async def _analyze_logs(
        self,
        error_logs: list[str],
    ) -> dict[str, Any]:
        """Parse and categorize error log entries."""
        issues_found: list[dict[str, Any]] = []
        warnings: list[str] = []

        for line in error_logs:
            line_upper = line.upper()
            if "HARD FAULT" in line_upper or "HARDFAULT" in line_upper:
                issues_found.append({"type": "HARD_FAULT", "line": line, "severity": "critical"})
            elif "CLOCK" in line_upper or "CLK" in line_upper:
                issues_found.append({"type": "CLOCK_ERROR", "line": line, "severity": "error"})
            elif "DMA" in line_upper:
                issues_found.append({"type": "DMA_ERROR", "line": line, "severity": "error"})
            elif "IRQ" in line_upper or "INTERRUPT" in line_upper:
                issues_found.append({"type": "INTERRUPT_ERROR", "line": line, "severity": "warning"})
            elif "ASSERT" in line_upper:
                issues_found.append({"type": "ASSERT_FAILURE", "line": line, "severity": "error"})
            elif "TIMEOUT" in line_upper:
                issues_found.append({"type": "TIMEOUT", "line": line, "severity": "warning"})
            elif "0x" in line:
                import re
                addrs = re.findall(r"0x[0-9A-Fa-f]{8}", line)
                issues_found.append({"type": "ADDRESS", "addresses": addrs, "line": line, "severity": "info"})

        return {
            "total_lines": len(error_logs),
            "issues_found": issues_found,
            "critical_count": sum(1 for i in issues_found if i["severity"] == "critical"),
            "error_count": sum(1 for i in issues_found if i["severity"] == "error"),
            "warning_count": sum(1 for i in issues_found if i["severity"] == "warning"),
        }

    async def _diagnose(
        self,
        symptom: str,
        issue_type: str,
        past_issues: list[dict[str, Any]],
        log_analysis: dict[str, Any],
        peripherals: list[str],
    ) -> dict[str, Any]:
        """Perform root cause analysis."""
        root_causes: list[dict[str, Any]] = []
        plan: list[str] = []

        # Deduce root causes from issue type
        if issue_type == "peripheral_init":
            root_causes.append({
                "cause": "Peripheral clock not enabled in RCC",
                "check": "Verify RCC->APBxENR has peripheral bit set before register access",
                "likelihood": 0.9,
            })
            root_causes.append({
                "cause": "GPIO pins not configured for alternate function",
                "check": "Check MODER, OTYPER, OSPEEDR, PUPDR for TX/RX pins",
                "likelihood": 0.7,
            })
            root_causes.append({
                "cause": "Peripheral not in correct mode (init vs normal)",
                "check": "Verify control register configuration sequence",
                "likelihood": 0.5,
            })
            plan = [
                "1. Check RCC clock enable for target peripheral",
                "2. Verify GPIO AF configuration for peripheral pins",
                "3. Validate peripheral control register sequence",
                "4. Check interrupt/NVIC configuration if applicable",
            ]

        elif issue_type == "gpio_config":
            root_causes.append({
                "cause": "GPIO clock not enabled before configuration",
                "check": "RCC->AHB1ENR must be set before GPIO registers",
                "likelihood": 0.85,
            })
            root_causes.append({
                "cause": "Pin mode (MODER) set incorrectly",
                "check": "Verify MODER bits match desired mode (input/output/AF/analog)",
                "likelihood": 0.6,
            })
            plan = [
                "1. Add RCC->AHB1ENR enable before GPIO config",
                "2. Verify MODER bits: 00=input, 01=output, 10=AF, 11=analog",
                "3. Check for pin conflict with other peripherals",
            ]

        elif issue_type == "interrupt_config":
            root_causes.append({
                "cause": "NVIC interrupt not enabled",
                "check": "Check NVIC_EnableIRQ() called for the correct IRQn",
                "likelihood": 0.9,
            })
            root_causes.append({
                "cause": "ISR handler not clearing pending bit",
                "check": "Verify pending bit cleared at end of ISR",
                "likelihood": 0.7,
            })
            root_causes.append({
                "cause": "Priority misconfigured causing nesting issues",
                "check": "Check NVIC priority value and grouping",
                "likelihood": 0.5,
            })
            plan = [
                "1. Verify NVIC_EnableIRQ() called with correct IRQn",
                "2. Check ISR clears pending flag before return",
                "3. Verify priority not conflicting with higher-priority ISRs",
                "4. Check for priority inversion in FreeRTOS if used",
            ]

        elif issue_type == "timing_config":
            root_causes.append({
                "cause": "Timer clock source incorrect (APB vs AHB)",
                "check": "TIM clock = APB clock × multiplier if PCLKx > HCLK",
                "likelihood": 0.8,
            })
            root_causes.append({
                "cause": "Prescaler/ARR values cause overflow",
                "check": "Verify PSC and ARR fit within 16-bit counter range",
                "likelihood": 0.6,
            })
            plan = [
                "1. Check TIM clock frequency in clock tree",
                "2. Verify PSC and ARR values for desired period",
                "3. Calculate if timer overflows before achieving target frequency",
            ]

        elif issue_type == "runtime_error":
            root_causes.append({
                "cause": "Stack overflow or null pointer dereference",
                "check": "Check MSP/PSP values, SCB->CFSR for MemManage faults",
                "likelihood": 0.85,
            })
            root_causes.append({
                "cause": "Unhandled exception/interrupt",
                "check": "Check HARD_FAULT handler for SCB->HFSR and CFSR",
                "likelihood": 0.7,
            })
            plan = [
                "1. Read SCB->CFSR for fault type (MemManage, Bus, Usage faults)",
                "2. Check stack pointer (MSP vs PSP) and stack size",
                "3. Identify faulting address in SCB->BFAR/SCB->MMFAR",
                "4. Use debugger to inspect call stack at fault",
            ]

        else:
            root_causes.append({
                "cause": "Unknown - insufficient context",
                "check": "Provide more specific symptom, error logs, and related code",
                "likelihood": 0.0,
            })
            plan = ["1. Gather more evidence: error logs, register dumps, scope traces"]

        # Incorporate log analysis
        critical_logs = [i for i in log_analysis.get("issues_found", []) if i["severity"] == "critical"]
        if critical_logs:
            root_causes.insert(0, {
                "cause": f"Critical hardware fault detected: {critical_logs[0]['type']}",
                "check": "See log analysis for details",
                "likelihood": 1.0,
            })

        # Calculate confidence
        confidence = sum(rc["likelihood"] for rc in root_causes) / len(root_causes) if root_causes else 0.0

        return {
            "issue_type": issue_type,
            "root_cause": root_causes[0] if root_causes else {"cause": "Unknown", "likelihood": 0.0},
            "all_root_causes": root_causes,
            "confidence": round(confidence, 3),
            "plan": plan,
            "peripherals_involved": peripherals,
        }

    async def _generate_fixes(
        self,
        diagnosis: dict[str, Any],
        issue_type: str,
        chip_family: str,
        peripherals: list[str],
    ) -> list[dict[str, Any]]:
        """Generate actionable fix recommendations."""
        fixes: list[dict[str, Any]] = []

        for cause in diagnosis.get("all_root_causes", []):
            if cause["likelihood"] < 0.3:
                continue

            fix: dict[str, Any] = {
                "cause": cause["cause"],
                "likelihood": cause["likelihood"],
                "actions": [],
                "code_snippets": [],
            }

            cause_lower = cause["cause"].lower()

            if "clock" in cause_lower:
                fix["actions"].append("Enable peripheral clock in RCC before register access")
                fix["code_snippets"].append(
                    f"// Enable {peripherals[0] if peripherals else 'peripheral'} clock\n"
                    f"// For APB1: RCC->APB1ENR |= RCC_APB1ENR_{peripherals[0] if peripherals else 'PERIPH'}EN;\n"
                    f"// For APB2: RCC->APB2ENR |= RCC_APB2ENR_{peripherals[0] if peripherals else 'PERIPH'}EN;"
                )
            if "gpio" in cause_lower or "alternate function" in cause_lower:
                fix["actions"].append("Configure GPIO pins for alternate function mode")
                fix["code_snippets"].append(
                    "// Configure GPIO for peripheral alternate function\n"
                    "// 1. Enable GPIO clock (RCC->AHB1ENR)\n"
                    "// 2. Set MODER to AF (0b10 for each pin)\n"
                    "// 3. Configure OSPEEDR and OTYPER\n"
                    "// 4. Set AFR register for AF number"
                )
            if "nvic" in cause_lower or "interrupt" in cause_lower:
                fix["actions"].append("Enable and configure NVIC interrupt")
                fix["code_snippets"].append(
                    "// Enable interrupt in NVIC\n"
                    "NVIC_EnableIRQ(IRQn_Type);\n"
                    "NVIC_SetPriority(IRQn_Type, priority);  // 0=highest, 15=lowest"
                )
            if "stack" in cause_lower or "null pointer" in cause_lower:
                fix["actions"].append("Increase stack size and add null checks")
                fix["code_snippets"].append(
                    "// Add null checks before pointer dereference\n"
                    "if (ptr == NULL) { /* handle error */ }\n"
                    "// Increase stack in linker script or FreeRTOS config"
                )
            if "timing" in cause_lower or "prescaler" in cause_lower:
                fix["actions"].append("Recalculate timer clock and PSC/ARR values")
                fix["code_snippets"].append(
                    "// Timer clock = APB clock (verify in RCC config)\n"
                    "// Period = (TimerClock / DesiredFreq) - 1\n"
                    "// PSC = (TimerClock / (ARR * DesiredFreq)) - 1"
                )

            if fix["actions"]:
                fixes.append(fix)

        return fixes
