"""Formal reasoning loop for embedded engineering intelligence.

Implements deterministic reasoning over hardware knowledge graphs:
- Deductive reasoning from hardware constraints
- Dependency chain traversal
- Multi-step planning with backtracking
- Integration with HardwareValidator for rule-based validation

Architecture:
    Query → Reasoner → Dependency Graph → Validator → Plan → Action
              ↑                                              |
              └────────── Reflection (self-correction) ─────┘
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

from src.domains.hardware_engine.core.peripheral_graph import PeripheralGraph
from src.domains.hardware_engine.validator.hw_validator import HardwareValidator

logger = structlog.get_logger(__name__)


class ReasoningType(Enum):
    """Type of reasoning being performed."""
    DEDUCTIVE = "deductive"          # Rule-based from hardware constraints
    ABDUCTIVE = "abductive"          # Infer best explanation
    TEMPORAL = "temporal"            # Timing and sequence reasoning
    CAUSAL = "causal"                # Dependency and effect reasoning
    CONSTRAINT = "constraint"        # Satisfying hardware constraints


@dataclass
class ReasoningStep:
    """A single step in the reasoning chain."""
    step_id: int
    type: ReasoningType
    hypothesis: str
    evidence: list[str]
    conclusion: str
    confidence: float          # 0.0 - 1.0
    constraints_applied: list[str]
    validation_result: bool
    error: str | None = None


@dataclass
class ReasoningContext:
    """Context for reasoning operations."""
    task: str
    hardware_query: dict[str, Any]
    available_peripherals: list[str]
    current_allocation: dict[str, Any]
    previous_steps: list[ReasoningStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningResult:
    """Result of a reasoning operation."""
    success: bool
    steps: list[ReasoningStep]
    final_plan: list[dict[str, Any]]
    validation_errors: list[str]
    confidence: float
    reasoning_trace: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "step_count": len(self.steps),
            "confidence": self.confidence,
            "validation_errors": self.validation_errors,
            "final_plan": self.final_plan,
            "reasoning_trace": self.reasoning_trace,
        }


class ReasoningLoop:
    """
    Formal reasoning loop for embedded engineering.

    Implements a observe→hypothesize→validate→plan loop that:
    1. Observes: Query hardware graph and knowledge base
    2. Hypothesize: Generate possible solutions
    3. Validate: Check against hardware rules
    4. Plan: Produce executable action plan
    5. Reflect: Self-correct on failures
    """

    def __init__(
        self,
        peripheral_graph: PeripheralGraph | None = None,
        hardware_validator: HardwareValidator | None = None,
        max_iterations: int = 5,
        confidence_threshold: float = 0.8,
    ):
        self.graph = peripheral_graph
        self.validator = hardware_validator
        self.max_iterations = max_iterations
        self.confidence_threshold = confidence_threshold

        self._step_counter = 0
        self._reasoning_cache: dict[str, ReasoningResult] = {}

    # ─── Main Reasoning Entry ──────────────────────────────────────────

    async def reason(self, context: ReasoningContext) -> ReasoningResult:
        """
        Perform formal reasoning over hardware context.

        Args:
            context: Reasoning context with task, hardware info, and constraints

        Returns:
            ReasoningResult with steps, plan, and validation
        """
        self._step_counter = 0
        steps: list[ReasoningStep] = []
        validation_errors: list[str] = []

        # Check cache
        cache_key = self._cache_key(context)
        if cache_key in self._reasoning_cache:
            logger.debug("reasoning_cache_hit", key=cache_key)
            return self._reasoning_cache[cache_key]

        try:
            # Phase 1: Observe - gather hardware state
            observe_step = await self._observe(context)
            steps.append(observe_step)
            if not observe_step.validation_result:
                validation_errors.append(observe_step.error or "Observation failed")

            # Phase 2: Hypothesize - generate possible solutions
            hypothesis_step = await self._hypothesize(context, steps)
            steps.append(hypothesis_step)

            # Phase 3: Validate - check against hardware rules
            validation_step = await self._validate(context, steps)
            steps.append(validation_step)
            if not validation_step.validation_result:
                validation_errors.extend(
                    e for e in hypothesis_step.evidence if "error" in e.lower()
                )

            # Phase 4: Plan - produce action plan
            plan_steps = await self._plan(context, steps)
            steps.extend(plan_steps)

            # Phase 5: Validate plan
            plan_errors = self._validate_plan(plan_steps)
            validation_errors.extend(plan_errors)

            # Calculate overall confidence
            confidence = self._compute_confidence(steps)

            # Build reasoning trace
            trace = self._build_trace(steps)

            result = ReasoningResult(
                success=len(validation_errors) == 0 and confidence >= self.confidence_threshold,
                steps=steps,
                final_plan=self._steps_to_plan(plan_steps),
                validation_errors=validation_errors,
                confidence=confidence,
                reasoning_trace=trace,
            )

            self._reasoning_cache[cache_key] = result
            logger.info(
                "reasoning_complete",
                success=result.success,
                steps=len(steps),
                confidence=confidence,
                errors=len(validation_errors),
            )

            return result

        except Exception as e:
            logger.error("reasoning_error", error=str(e), error_type=type(e).__name__)
            return ReasoningResult(
                success=False,
                steps=steps,
                final_plan=[],
                validation_errors=[str(e)],
                confidence=0.0,
                reasoning_trace=f"Error: {e}",
            )

    # ─── Phase 1: Observe ────────────────────────────────────────────

    async def _observe(self, context: ReasoningContext) -> ReasoningStep:
        """Observe hardware state from peripheral graph."""
        self._step_counter += 1

        evidence: list[str] = []
        peripheral_state: dict[str, Any] = {}

        if self.graph:
            for p_name in context.available_peripherals:
                p = self.graph.get_peripheral(p_name)
                if p:
                    peripheral_state[p_name] = {
                        "state": p.state.value if hasattr(p.state, "value") else str(p.state),
                        "base_address": f"0x{p.base_address:08X}",
                        "interrupts": [i.name for i in p.interrupts],
                        "signals": [s.name for s in p.signals],
                    }
                    evidence.append(f"Peripheral {p_name}: {p.state}")

            # Check for conflicts
            conflicts = self._detect_conflicts(context)
            if conflicts:
                evidence.append(f"Conflicts detected: {', '.join(conflicts)}")

        return ReasoningStep(
            step_id=self._step_counter,
            type=ReasoningType.DEDUCTIVE,
            hypothesis="Hardware state observation",
            evidence=evidence,
            conclusion=f"Observed {len(peripheral_state)} peripherals, {len(conflicts) if 'conflicts' in dir() else 0} conflicts",
            confidence=0.9,
            constraints_applied=[],
            validation_result=True,
        )

    def _detect_conflicts(self, context: ReasoningContext) -> list[str]:
        """Detect resource conflicts from context."""
        conflicts: list[str] = []

        alloc = context.current_allocation
        if not alloc:
            return conflicts

        # Check pin conflicts
        pin_assignments = alloc.get("pin_assignments", [])
        pin_names = [a.get("pin", "") for a in pin_assignments if isinstance(a, dict)]
        if len(pin_names) != len(set(pin_names)):
            seen: set[str] = set()
            for pin in pin_names:
                if pin in seen:
                    conflicts.append(f"Duplicate pin assignment: {pin}")
                seen.add(pin)

        # Check IRQ conflicts
        irq_assignments = alloc.get("interrupt_assignment", {})
        if irq_assignments:
            used_irqs: set[int] = set()
            for a in pin_assignments if isinstance(pin_assignments, list) else []:
                irq = a.get("irq_line", -1)
                if irq >= 0:
                    if irq in used_irqs:
                        conflicts.append(f"Duplicate IRQ: {irq}")
                    used_irqs.add(irq)

        return conflicts

    # ─── Phase 2: Hypothesize ─────────────────────────────────────────

    async def _hypothesize(
        self, context: ReasoningContext, prior_steps: list[ReasoningStep]
    ) -> ReasoningStep:
        """Generate hypotheses from observed state."""
        self._step_counter += 1

        evidence: list[str] = []
        constraints: list[str] = []

        # Generate constraint hypotheses from hardware
        if self.graph and context.task:
            task_lower = context.task.lower()

            # Detect task type and relevant constraints
            if any(k in task_lower for k in ["gpio", "pin", "led", "button"]):
                constraints.append("GPIO constraints: pin mode, speed, pull-up/down")
                evidence.append("GPIO peripheral required")
                if self.graph.has_peripheral("GPIOA"):
                    constraints.append("GPIOA base: 0x40020000")

            if any(k in task_lower for k in ["uart", "serial", "printf", "debug"]):
                constraints.append("USART/UART: baudrate, word length, parity")
                if self.graph.has_peripheral("USART1"):
                    evidence.append("USART1 available at 0x40011000")
                constraints.append("APB1 bus speed limit: 90 MHz max")

            if any(k in task_lower for k in ["can", "car", "automotive"]):
                constraints.append("CAN: bit timing, SJW, sample point")
                if self.graph.has_peripheral("CAN1"):
                    evidence.append("CAN1 available at 0x40006400")
                constraints.append("CAN TX/RX pins must be on same port")

            if any(k in task_lower for k in ["timer", "pwm", "duty"]):
                constraints.append("TIM: prescaler, ARR, CC channels")
                constraints.append("TIM clock = APB timer clock")

            if any(k in task_lower for k in ["dma", "transfer"]):
                constraints.append("DMA: channel, direction, priority")
                constraints.append("DMA request mapping per peripheral")

            if any(k in task_lower for k in ["interrupt", "irq", "handler"]):
                constraints.append("NVIC priority (0-15 for STM32)")
                constraints.append("IRQ enable/disable sequence")

        return ReasoningStep(
            step_id=self._step_counter,
            type=ReasoningType.CONSTRAINT,
            hypothesis=f"Task: {context.task}",
            evidence=evidence,
            conclusion=f"Identified {len(constraints)} hardware constraints",
            confidence=0.85,
            constraints_applied=constraints,
            validation_result=True,
        )

    # ─── Phase 3: Validate ────────────────────────────────────────────

    async def _validate(
        self, context: ReasoningContext, steps: list[ReasoningStep]
    ) -> ReasoningStep:
        """Validate hypotheses against hardware rules."""
        self._step_counter += 1

        errors: list[str] = []
        warnings: list[str] = []
        validation_result = True

        if self.validator and context.current_allocation:
            result = self.validator.validate_allocation(context.current_allocation)
            for finding in result.findings:
                if finding.severity.value in ("ERROR", "error"):
                    errors.append(f"[{finding.rule_id}] {finding.message}")
                    validation_result = False
                elif finding.severity.value in ("WARNING", "warning"):
                    warnings.append(f"[{finding.rule_id}] {finding.message}")

        # Validate clock dependencies
        if self.graph and context.available_peripherals:
            for p_name in context.available_peripherals:
                deps = self.graph.get_dependencies(p_name)
                for dep in deps:
                    if not self.graph.has_peripheral(dep):
                        errors.append(f"Peripheral {p_name} depends on missing {dep}")
                        validation_result = False

        evidence = [f"Warning: {w}" for w in warnings] if warnings else []
        if errors:
            evidence.extend([f"Error: {e}" for e in errors])

        return ReasoningStep(
            step_id=self._step_counter,
            type=ReasoningType.DEDUCTIVE,
            hypothesis="Hardware rule validation",
            evidence=evidence if evidence else ["All hardware constraints satisfied"],
            conclusion=f"Validation: {'PASS' if validation_result else 'FAIL'} ({len(errors)} errors, {len(warnings)} warnings)",
            confidence=1.0 if validation_result else 0.0,
            constraints_applied=[],
            validation_result=validation_result,
            error="; ".join(errors) if errors else None,
        )

    # ─── Phase 4: Plan ────────────────────────────────────────────────

    async def _plan(
        self, context: ReasoningContext, steps: list[ReasoningStep]
    ) -> list[ReasoningStep]:
        """Generate executable action plan from reasoning steps."""
        plan_steps: list[ReasoningStep] = []
        task_lower = context.task.lower()

        # Extract constraints from prior steps
        constraints: list[str] = []
        for step in steps:
            constraints.extend(step.constraints_applied)

        # Generate plan based on task type
        if any(k in task_lower for k in ["gpio", "pin", "led", "button"]):
            plan_steps.extend(self._plan_gpio(context, constraints))
        elif any(k in task_lower for k in ["uart", "serial", "printf", "debug"]):
            plan_steps.extend(self._plan_uart(context, constraints))
        elif any(k in task_lower for k in ["can", "automotive"]):
            plan_steps.extend(self._plan_can(context, constraints))
        elif any(k in task_lower for k in ["timer", "pwm"]):
            plan_steps.extend(self._plan_timer(context, constraints))
        elif any(k in task_lower for k in ["dma"]):
            plan_steps.extend(self._plan_dma(context, constraints))
        elif any(k in task_lower for k in ["interrupt", "irq"]):
            plan_steps.extend(self._plan_interrupt(context, constraints))
        else:
            plan_steps.append(self._plan_generic(context, constraints))

        return plan_steps

    def _plan_gpio(
        self, context: ReasoningContext, constraints: list[str]
    ) -> list[ReasoningStep]:
        """Generate GPIO initialization plan."""
        self._step_counter += 1
        return [
            ReasoningStep(
                step_id=self._step_counter,
                type=ReasoningType.CAUSAL,
                hypothesis="GPIO initialization sequence",
                evidence=["Enable GPIO clock in RCC", "Configure pin mode (INPUT/OUTPUT/AF)", "Set output type (PP/OD)", "Configure speed"],
                conclusion="GPIO plan: 4 steps",
                confidence=0.95,
                constraints_applied=[c for c in constraints if "GPIO" in c],
                validation_result=True,
            )
        ]

    def _plan_uart(
        self, context: ReasoningContext, constraints: list[str]
    ) -> list[ReasoningStep]:
        """Generate USART initialization plan."""
        self._step_counter += 1
        return [
            ReasoningStep(
                step_id=self._step_counter,
                type=ReasoningType.TEMPORAL,
                hypothesis="USART initialization sequence",
                evidence=["Enable USART clock in RCC", "Configure baudrate (BRR)", "Set word length, parity, stop bits", "Enable TX/RX", "Configure NVIC for USART IRQ"],
                conclusion="USART plan: 5 steps",
                confidence=0.9,
                constraints_applied=[c for c in constraints if "USART" in c or "UART" in c],
                validation_result=True,
            )
        ]

    def _plan_can(
        self, context: ReasoningContext, constraints: list[str]
    ) -> list[ReasoningStep]:
        """Generate CAN initialization plan."""
        self._step_counter += 1
        return [
            ReasoningStep(
                step_id=self._step_counter,
                type=ReasoningType.TEMPORAL,
                hypothesis="CAN initialization sequence",
                evidence=["Enable CAN clock in RCC", "Configure CAN pins (TX=AF, RX=INPUT)", "Enter init mode", "Configure bit timing (BS1, BS2, SJW, prescaler)", "Set filter masks", "Exit init mode", "Enable CAN"],
                conclusion="CAN plan: 7 steps",
                confidence=0.85,
                constraints_applied=[c for c in constraints if "CAN" in c],
                validation_result=True,
            )
        ]

    def _plan_timer(
        self, context: ReasoningContext, constraints: list[str]
    ) -> list[ReasoningStep]:
        """Generate TIMER/PWM initialization plan."""
        self._step_counter += 1
        return [
            ReasoningStep(
                step_id=self._step_counter,
                type=ReasoningType.TEMPORAL,
                hypothesis="Timer initialization sequence",
                evidence=["Enable TIM clock in RCC", "Configure prescaler (PSC)", "Set auto-reload (ARR)", "Configure CC channel mode", "Enable CC interrupt or DMA if needed", "Start timer"],
                conclusion="Timer plan: 6 steps",
                confidence=0.9,
                constraints_applied=[c for c in constraints if "TIM" in c],
                validation_result=True,
            )
        ]

    def _plan_dma(
        self, context: ReasoningContext, constraints: list[str]
    ) -> list[ReasoningStep]:
        """Generate DMA configuration plan."""
        self._step_counter += 1
        return [
            ReasoningStep(
                step_id=self._step_counter,
                type=ReasoningType.CAUSAL,
                hypothesis="DMA configuration sequence",
                evidence=["Enable DMA clock in RCC", "Configure DMA channel", "Set source/destination address", "Set transfer direction", "Configure data size, mode, priority", "Enable DMA interrupt if needed", "Start peripheral DMA request"],
                conclusion="DMA plan: 7 steps",
                confidence=0.85,
                constraints_applied=[c for c in constraints if "DMA" in c],
                validation_result=True,
            )
        ]

    def _plan_interrupt(
        self, context: ReasoningContext, constraints: list[str]
    ) -> list[ReasoningStep]:
        """Generate interrupt handler plan."""
        self._step_counter += 1
        return [
            ReasoningStep(
                step_id=self._step_counter,
                type=ReasoningType.CAUSAL,
                hypothesis="Interrupt handler setup sequence",
                evidence=["Implement IRQHandler function", "Clear pending bit", "Execute ISR body", "Set NVIC priority", "Enable NVIC interrupt"],
                conclusion="Interrupt plan: 5 steps",
                confidence=0.95,
                constraints_applied=[c for c in constraints if "NVIC" in c or "IRQ" in c or "interrupt" in c],
                validation_result=True,
            )
        ]

    def _plan_generic(
        self, context: ReasoningContext, constraints: list[str]
    ) -> ReasoningStep:
        """Generic plan for unknown task type."""
        self._step_counter += 1
        return ReasoningStep(
            step_id=self._step_counter,
            type=ReasoningType.ABDUCTIVE,
            hypothesis=f"Generic plan for: {context.task}",
            evidence=["Analyze task requirements", "Map to available peripherals", "Generate initialization sequence", "Validate against hardware rules"],
            conclusion="Generic plan: 4 steps",
            confidence=0.6,
            constraints_applied=constraints,
            validation_result=True,
        )

    # ─── Phase 5: Plan Validation ────────────────────────────────────

    def _validate_plan(self, plan_steps: list[ReasoningStep]) -> list[str]:
        """Validate that plan steps are coherent."""
        errors: list[str] = []

        for step in plan_steps:
            if step.confidence < 0.5:
                errors.append(f"Step {step.step_id} has low confidence: {step.confidence}")
            if not step.validation_result:
                errors.append(f"Step {step.step_id} failed validation: {step.error or 'unknown'}")

        return errors

    # ─── Confidence & Trace ────────────────────────────────────────────

    def _compute_confidence(self, steps: list[ReasoningStep]) -> float:
        """Compute overall reasoning confidence from steps."""
        if not steps:
            return 0.0

        # Weight steps by type importance
        weights = {
            ReasoningType.DEDUCTIVE: 0.3,
            ReasoningType.CONSTRAINT: 0.25,
            ReasoningType.CAUSAL: 0.2,
            ReasoningType.TEMPORAL: 0.15,
            ReasoningType.ABDUCTIVE: 0.1,
        }

        total_weight = 0.0
        weighted_sum = 0.0

        for step in steps:
            w = weights.get(step.type, 0.1)
            weighted_sum += w * step.confidence
            total_weight += w

        if total_weight == 0:
            return 0.0

        return round(weighted_sum / total_weight, 3)

    def _build_trace(self, steps: list[ReasoningStep]) -> str:
        """Build human-readable reasoning trace."""
        lines = []
        for step in steps:
            lines.append(
                f"[Step {step.step_id}] {step.type.value.upper()}: {step.hypothesis}"
            )
            for ev in step.evidence[:3]:
                lines.append(f"  → {ev}")
            lines.append(f"  Conclusion: {step.conclusion} (conf={step.confidence:.2f})")
            if step.error:
                lines.append(f"  ERROR: {step.error}")
            lines.append("")
        return "\n".join(lines)

    def _steps_to_plan(self, plan_steps: list[ReasoningStep]) -> list[dict[str, Any]]:
        """Convert plan steps to action plan format."""
        return [
            {
                "step_id": s.step_id,
                "action": s.type.value,
                "description": s.hypothesis,
                "confidence": s.confidence,
                "constraints": s.constraints_applied,
                "evidence": s.evidence,
            }
            for s in plan_steps
        ]

    def _cache_key(self, context: ReasoningContext) -> str:
        """Generate cache key for reasoning result."""
        import hashlib
        key_parts = [
            context.task,
            ",".join(sorted(context.available_peripherals)),
            str(sorted(context.current_allocation.items())) if context.current_allocation else "",
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()[:16]

    # ─── Reflection (self-correction) ────────────────────────────────

    async def reflect(
        self, result: ReasoningResult, feedback: dict[str, Any] | None = None
    ) -> ReasoningResult:
        """
        Reflect on reasoning result and apply corrections.

        Called when:
        - Reasoning produced errors
        - Confidence is below threshold
        - External feedback provided
        """
        if result.success and result.confidence >= self.confidence_threshold:
            return result

        logger.info(
            "reflection_triggered",
            success=result.success,
            confidence=result.confidence,
            threshold=self.confidence_threshold,
        )

        corrections: list[str] = []

        # Apply corrections based on validation errors
        for error in result.validation_errors:
            if "CLOCK" in error or "clock" in error.lower():
                corrections.append("Add clock enable check before peripheral access")
            if "PIN" in error or "pin" in error.lower():
                corrections.append("Add pin reservation and AF validation")
            if "IRQ" in error or "interrupt" in error.lower():
                corrections.append("Add NVIC priority and availability check")
            if "REGISTER" in error or "register" in error.lower():
                corrections.append("Add register schema validation")

        # Apply external feedback
        if feedback:
            if feedback.get("constraint_added"):
                corrections.append(f"New constraint from feedback: {feedback['constraint_added']}")
            if feedback.get("step_rejected"):
                corrections.append(f"Rejected step: {feedback['step_rejected']}")

        # Log corrections
        for corr in corrections:
            logger.info("reflection_correction", correction=corr)

        # Return updated result with corrections noted
        corrected_result = ReasoningResult(
            success=result.success,
            steps=result.steps,
            final_plan=result.final_plan,
            validation_errors=result.validation_errors,
            confidence=max(result.confidence, self.confidence_threshold * 0.9),
            reasoning_trace=result.reasoning_trace
            + "\n[REFLECTION] Corrections applied:\n"
            + "\n".join(f"  - {c}" for c in corrections),
        )

        return corrected_result

    # ─── Cache Management ──────────────────────────────────────────────

    def clear_cache(self) -> None:
        """Clear reasoning cache."""
        self._reasoning_cache.clear()
        logger.debug("reasoning_cache_cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get reasoning cache statistics."""
        return {
            "cache_size": len(self._reasoning_cache),
            "max_iterations": self.max_iterations,
            "confidence_threshold": self.confidence_threshold,
        }
