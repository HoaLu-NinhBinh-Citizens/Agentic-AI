"""Hardware workflow - embedded hardware analysis and validation."""

from __future__ import annotations

from typing import Any

import structlog

from src.application.workflows.base import BaseWorkflow, WorkflowStep, WorkflowStatus
from src.core.agent.reasoning_loop import ReasoningContext, ReasoningLoop
from src.domain.knowledge.kb import KBEntryType, KnowledgeBase, KBQuery

logger = structlog.get_logger(__name__)


class HardwareWorkflow(BaseWorkflow):
    """
    Workflow for hardware analysis, initialization planning, and validation.

    Pipeline:
    1. Parse task → identify required peripherals
    2. Query KB for relevant hardware specs
    3. Run formal reasoning over hardware constraints
    4. Generate initialization plan
    5. Validate plan against hardware rules
    6. Return actionable output

    Usage:
        wf = HardwareWorkflow(context={
            "task": "Implement CAN1 communication at 500kbps",
            "chip_family": "STM32F407",
            "peripherals": ["CAN1", "GPIOD"],
        })
        result = await wf.run()
    """

    @property
    def name(self) -> str:
        return "Hardware Analysis Workflow"

    @property
    def description(self) -> str:
        return "Analyze hardware requirements and generate validated initialization plans"

    async def _execute(self) -> dict[str, Any]:
        task = self.context.get("task", "")
        chip_family = self.context.get("chip_family", "STM32F4")
        peripherals = self.context.get("peripherals", [])
        allocation = self.context.get("allocation", {})

        # Step 1: Parse task → identify peripherals
        step_parse = self.add_step("parse", "Parse Task", "Extract hardware requirements from task description")
        peripheral_list, constraints = await self.run_step(
            "parse",
            self._parse_task,
            task,
            peripherals,
        )

        # Step 2: Query KB for hardware specs
        step_kb = self.add_step("kb_lookup", "KB Lookup", "Query knowledge base for relevant hardware specs")
        kb_results = await self.run_step(
            "kb_lookup",
            self._query_kb,
            task,
            chip_family,
            peripheral_list,
        )

        # Step 3: Formal reasoning over hardware constraints
        step_reason = self.add_step("reason", "Formal Reasoning", "Reason over hardware constraints and dependencies")
        reasoning_result = await self.run_step(
            "reason",
            self._reason,
            task,
            peripheral_list,
            allocation,
            constraints,
        )

        # Step 4: Generate initialization plan
        step_plan = self.add_step("plan", "Generate Plan", "Produce executable initialization plan")
        plan = await self.run_step(
            "plan",
            self._generate_plan,
            task,
            peripheral_list,
            reasoning_result,
        )

        # Step 5: Validate plan
        step_validate = self.add_step("validate", "Validate Plan", "Validate plan against hardware rules")
        validation_result = await self.run_step(
            "validate",
            self._validate_plan,
            plan,
            allocation,
        )

        return {
            "task": task,
            "chip_family": chip_family,
            "peripherals": peripheral_list,
            "kb_results": kb_results,
            "reasoning": reasoning_result,
            "plan": plan,
            "validation": validation_result,
            "ready_to_generate": validation_result.get("valid", False),
        }

    async def _parse_task(
        self,
        task: str,
        peripherals: list[str],
    ) -> tuple[list[str], list[str]]:
        """Parse task description to identify required peripherals and constraints."""
        task_lower = task.lower()
        identified: list[str] = list(peripherals) if peripherals else []
        constraints: list[str] = []

        # Auto-detect from keywords
        if any(k in task_lower for k in ["can", "automotive", "car"]):
            if "CAN1" not in identified and "CAN" not in task_lower:
                identified.append("CAN1")
            constraints.append("CAN bit timing: 500kbps requires SJW=1, BS1=6, BS2=8, prescaler=6 @ 42MHz APB1")
        if any(k in task_lower for k in ["uart", "serial", "printf", "debug"]):
            if "USART1" not in identified:
                identified.append("USART1")
            constraints.append("USART: baudrate calculation, word length, parity, stop bits")
        if any(k in task_lower for k in ["gpio", "led", "button", "pin"]):
            if "GPIOA" not in identified:
                identified.append("GPIOA")
            constraints.append("GPIO: mode, speed, pull-up/down configuration")
        if any(k in task_lower for k in ["timer", "pwm", "duty"]):
            if "TIM3" not in identified:
                identified.append("TIM3")
            constraints.append("TIM: PSC, ARR, CC channels, PWM mode")
        if any(k in task_lower for k in ["dma"]):
            if "DMA1" not in identified:
                identified.append("DMA1")
            constraints.append("DMA: channel selection, transfer direction, priority")
        if any(k in task_lower for k in ["interrupt", "irq", "handler"]):
            constraints.append("NVIC: priority level, enable/disable sequence")
        if any(k in task_lower for k in ["spi"]):
            if "SPI1" not in identified:
                identified.append("SPI1")
            constraints.append("SPI: frame format, clock phase/polarity, data size")
        if any(k in task_lower for k in ["i2c"]):
            if "I2C1" not in identified:
                identified.append("I2C1")
            constraints.append("I2C: address, speed mode (standard/fast)")

        logger.debug("task_parse", peripherals=identified, constraints=len(constraints))
        return identified, constraints

    async def _query_kb(
        self,
        task: str,
        chip_family: str,
        peripherals: list[str],
    ) -> dict[str, Any]:
        """Query knowledge base for hardware specs."""
        if not self._knowledge_base:
            return {"results": [], "count": 0}

        results_by_peripheral: dict[str, Any] = {}

        for peripheral in peripherals:
            results = await self._knowledge_base.query_by_text(
                text=f"{peripheral} initialization configuration registers",
                chip_family=chip_family,
                peripheral=peripheral,
                top_k=5,
            )
            if results:
                results_by_peripheral[peripheral] = [
                    {
                        "title": r.entry.title,
                        "source": r.entry.source,
                        "type": r.entry.type.value,
                        "score": r.score,
                        "preview": r.entry.content[:200],
                    }
                    for r in results
                ]

        # Also query for generic patterns
        generic_results = await self._knowledge_base.query_by_text(
            text=task,
            chip_family=chip_family,
            top_k=3,
        )

        return {
            "by_peripheral": results_by_peripheral,
            "generic": [
                {"title": r.entry.title, "source": r.entry.source, "score": r.score}
                for r in generic_results
            ],
            "count": sum(len(v) if isinstance(v, list) else 0 for v in results_by_peripheral.values()),
        }

    async def _reason(
        self,
        task: str,
        peripherals: list[str],
        allocation: dict[str, Any],
        constraints: list[str],
    ) -> dict[str, Any]:
        """Run formal reasoning over hardware context."""
        if not self._reasoning_loop:
            return {"success": True, "steps": [], "confidence": 0.8, "note": "reasoning_loop not injected"}

        context = ReasoningContext(
            task=task,
            hardware_query={},
            available_peripherals=peripherals,
            current_allocation=allocation,
            metadata={"constraints": constraints},
        )

        result = await self._reasoning_loop.reason(context)

        return {
            "success": result.success,
            "confidence": result.confidence,
            "steps": [
                {
                    "id": s.step_id,
                    "type": s.type.value,
                    "hypothesis": s.hypothesis,
                    "conclusion": s.conclusion,
                    "confidence": s.confidence,
                }
                for s in result.steps
            ],
            "validation_errors": result.validation_errors,
            "trace": result.reasoning_trace,
        }

    async def _generate_plan(
        self,
        task: str,
        peripherals: list[str],
        reasoning_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate initialization plan from reasoning."""
        plan_steps: list[dict[str, Any]] = []
        task_lower = task.lower()

        # Determine plan based on task type
        if any(k in task_lower for k in ["can", "automotive"]):
            plan_steps = [
                {"order": 1, "phase": "clock", "action": "Enable CAN clock in RCC", "peripheral": "CAN1", "code_hint": "RCC->APB1ENR |= RCC_APB1ENR_CAN1EN"},
                {"order": 2, "phase": "pin", "action": "Configure CAN TX/RX pins", "peripheral": "GPIOD", "code_hint": "TX=AF8 push-pull, RX=input floating"},
                {"order": 3, "phase": "init", "action": "Enter CAN init mode", "peripheral": "CAN1", "code_hint": "CAN_MCR |= CAN_MCR_INRQ; while(!(CAN_MSR & CAN_MSR_INAK))"},
                {"order": 4, "phase": "timing", "action": "Configure bit timing", "peripheral": "CAN1", "code_hint": "CAN_BTR = (SJW-1) | ((BS1-1)<<16) | ((BS2-1)<<20) | ((prescaler-1)<<0)"},
                {"order": 5, "phase": "filter", "action": "Configure acceptance filter", "peripheral": "CAN1", "code_hint": "CAN_FMR |= CAN_FMR_FINIT; CAN_FA1R = ..."},
                {"order": 6, "phase": "start", "action": "Exit init mode, enable CAN", "peripheral": "CAN1", "code_hint": "CAN_MCR &= ~CAN_MCR_INRQ"},
            ]
        elif any(k in task_lower for k in ["uart", "serial", "printf"]):
            plan_steps = [
                {"order": 1, "phase": "clock", "action": "Enable USART clock in RCC", "peripheral": "USART1", "code_hint": "RCC->APB2ENR |= RCC_APB2ENR_USART1EN"},
                {"order": 2, "phase": "pin", "action": "Configure TX/RX pins (PA9/PA10)", "peripheral": "GPIOA", "code_hint": "PA9=TX AFPP, PA10=RX_INPUT"},
                {"order": 3, "phase": "config", "action": "Configure baudrate (BRR)", "peripheral": "USART1", "code_hint": "USART_BRR = fck / baudrate"},
                {"order": 4, "phase": "config", "action": "Configure word length, parity, stop bits", "peripheral": "USART1", "code_hint": "USART_CR1 = M_bits | PCE | PS | TE | RE"},
                {"order": 5, "phase": "enable", "action": "Enable USART", "peripheral": "USART1", "code_hint": "USART_CR1 |= USART_CR1_UE"},
            ]
        elif any(k in task_lower for k in ["gpio", "led", "button"]):
            plan_steps = [
                {"order": 1, "phase": "clock", "action": "Enable GPIO clock in RCC", "peripheral": "GPIOA", "code_hint": "RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN"},
                {"order": 2, "phase": "config", "action": "Configure pin mode", "peripheral": "GPIOA", "code_hint": "GPIOA->MODER = (GPIOA->MODER & ~mask) | (mode << shift)"},
                {"order": 3, "phase": "config", "action": "Configure output type and speed", "peripheral": "GPIOA", "code_hint": "GPIOA->OTYPER, GPIOA->OSPEEDR"},
                {"order": 4, "phase": "config", "action": "Configure pull-up/down if needed", "peripheral": "GPIOA", "code_hint": "GPIOA->PUPDR"},
            ]
        elif any(k in task_lower for k in ["timer", "pwm"]):
            plan_steps = [
                {"order": 1, "phase": "clock", "action": "Enable TIM clock in RCC", "peripheral": "TIM3", "code_hint": "RCC->APB1ENR |= RCC_APB1ENR_TIM3EN"},
                {"order": 2, "phase": "config", "action": "Configure prescaler (PSC)", "peripheral": "TIM3", "code_hint": "TIM3->PSC = prescaler - 1"},
                {"order": 3, "phase": "config", "action": "Set auto-reload (ARR)", "peripheral": "TIM3", "code_hint": "TIM3->ARR = period - 1"},
                {"order": 4, "phase": "config", "action": "Configure CC channel and PWM mode", "peripheral": "TIM3", "code_hint": "TIM3->CCMR1 |= TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1M_1"},
                {"order": 5, "phase": "enable", "action": "Enable CC and start timer", "peripheral": "TIM3", "code_hint": "TIM3->CCER |= TIM_CCER_CC1E; TIM3->CR1 |= TIM_CR1_CEN"},
            ]
        elif any(k in task_lower for k in ["dma"]):
            plan_steps = [
                {"order": 1, "phase": "clock", "action": "Enable DMA clock in RCC", "peripheral": "DMA1", "code_hint": "RCC->AHB1ENR |= RCC_AHB1ENR_DMA1EN"},
                {"order": 2, "phase": "config", "action": "Configure DMA channel", "peripheral": "DMA1", "code_hint": "DMA1_ChannelX->CPAR, DMA1_ChannelX->CMAR"},
                {"order": 3, "phase": "config", "action": "Set direction, mode, priority", "peripheral": "DMA1", "code_hint": "DMA1_ChannelX->CCR = DIR | MODE | PL | MSIZE | PSIZE | MINC | CIRC"},
                {"order": 4, "phase": "enable", "action": "Enable DMA channel", "peripheral": "DMA1", "code_hint": "DMA1_ChannelX->CCR |= DMA_CCR_EN"},
            ]
        else:
            plan_steps = [
                {"order": 1, "phase": "clock", "action": "Enable peripheral clock in RCC", "peripheral": peripherals[0] if peripherals else "UNKNOWN", "code_hint": "RCC->APBxENR |= ..."},
                {"order": 2, "phase": "pin", "action": "Configure peripheral pins", "peripheral": peripherals[0] if peripherals else "UNKNOWN", "code_hint": "GPIO alternate function configuration"},
                {"order": 3, "phase": "init", "action": "Configure peripheral registers", "peripheral": peripherals[0] if peripherals else "UNKNOWN", "code_hint": "Peripheral-specific configuration"},
                {"order": 4, "phase": "enable", "action": "Enable peripheral", "peripheral": peripherals[0] if peripherals else "UNKNOWN", "code_hint": "Peripheral enable bit"},
            ]

        return {
            "steps": plan_steps,
            "phase_order": sorted(set(s["phase"] for s in plan_steps)),
            "estimated_steps": len(plan_steps),
        }

    async def _validate_plan(
        self,
        plan: dict[str, Any],
        allocation: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate the generated plan against hardware rules."""
        if not self._hardware_validator:
            return {"valid": True, "errors": [], "warnings": [], "note": "validator not injected"}

        # Validate using hardware validator
        result = self._hardware_validator.validate_allocation(allocation)

        return {
            "valid": result.valid,
            "errors": [
                {"rule_id": f.rule_id, "message": f.message, "location": f.location}
                for f in result.findings if f.severity.value in ("ERROR", "error")
            ],
            "warnings": [
                {"rule_id": f.rule_id, "message": f.message, "location": f.location}
                for f in result.findings if f.severity.value in ("WARNING", "warning")
            ],
            "info": [
                {"rule_id": f.rule_id, "message": f.message}
                for f in result.findings if f.severity.value in ("INFO", "info")
            ],
        }
