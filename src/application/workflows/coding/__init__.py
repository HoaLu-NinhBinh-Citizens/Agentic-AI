"""Coding workflow - code generation with hardware validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from src.application.workflows.base import BaseWorkflow
from src.infrastructure.filesystem.edit_system import EditSystem

logger = structlog.get_logger(__name__)


class CodingWorkflow(BaseWorkflow):
    """
    Workflow for generating hardware-validated embedded C code.

    Pipeline:
    1. Parse request → identify target peripheral and configuration
    2. Run hardware workflow for validated initialization plan
    3. Generate code from plan
    4. Validate generated code against hardware rules
    5. Return code + validation report

    Usage:
        wf = CodingWorkflow(context={
            "request": "Initialize CAN1 at 500kbps for EngineCar",
            "chip_family": "STM32F407",
            "style": "hal",  # hal, ll, or register
        })
        result = await wf.run()
    """

    @property
    def name(self) -> str:
        return "Code Generation Workflow"

    @property
    def description(self) -> str:
        return "Generate hardware-validated embedded C code"

    async def _execute(self) -> dict[str, Any]:
        request = self.context.get("request", "")
        chip_family = self.context.get("chip_family", "STM32F407")
        style = self.context.get("style", "register")  # hal | ll | register
        output_format = self.context.get("output_format", "c_file")  # c_file | snippet | full_driver

        # Step 1: Parse request
        step_parse = self.add_step("parse", "Parse Request", "Extract peripheral and configuration from request")
        parsed = await self.run_step("parse", self._parse_request, request)

        # Step 2: Generate hardware plan
        step_hw = self.add_step("hardware_plan", "Hardware Plan", "Generate validated initialization plan")
        hw_result = await self.run_step(
            "hardware_plan",
            self._generate_hardware_plan,
            parsed,
            chip_family,
        )

        # Step 3: Generate code
        step_code = self.add_step("generate_code", "Generate Code", "Generate C code from plan")
        generated = await self.run_step(
            "generate_code",
            self._generate_code,
            parsed,
            hw_result,
            style,
        )

        # Step 4: Validate code
        step_validate = self.add_step("validate_code", "Validate Code", "Validate generated code against hardware rules")
        validation = await self.run_step(
            "validate_code",
            self._validate_code,
            generated,
            hw_result,
        )

        # Step 5: Format output
        step_format = self.add_step("format", "Format Output", "Format code for output")
        output = await self.run_step(
            "format",
            self._format_output,
            generated,
            validation,
            output_format,
            parsed,
        )

        return {
            "request": request,
            "chip_family": chip_family,
            "style": style,
            "peripheral": parsed.get("peripheral"),
            "configuration": parsed.get("configuration"),
            "code": output.get("code"),
            "validation": validation,
            "warnings": output.get("warnings", []),
            "hardware_plan": hw_result,
            "edit_id": output.get("edit_id"),
        }

    async def _parse_request(self, request: str) -> dict[str, Any]:
        """Parse code generation request."""
        req_lower = request.lower()
        peripheral = ""
        configuration: dict[str, Any] = {}

        # Detect peripheral
        if "can" in req_lower:
            peripheral = "CAN1"
            if "500" in request or "500k" in req_lower:
                configuration["baudrate"] = 500000
                configuration["timing"] = {"SJW": 1, "BS1": 6, "BS2": 8, "prescaler": 6}
            elif "250" in request or "250k" in req_lower:
                configuration["baudrate"] = 250000
                configuration["timing"] = {"SJW": 1, "BS1": 13, "BS2": 2, "prescaler": 12}
        elif "uart" in req_lower or "usart" in req_lower:
            peripheral = "USART1"
            if "115200" in request or "115200" in req_lower:
                configuration["baudrate"] = 115200
            elif "9600" in request:
                configuration["baudrate"] = 9600
            else:
                configuration["baudrate"] = 115200
            configuration["word_length"] = 8
            configuration["parity"] = "none"
            configuration["stop_bits"] = 1
        elif "gpio" in req_lower or "led" in req_lower or "button" in req_lower:
            peripheral = "GPIOA"
            configuration["mode"] = "output" if "led" in req_lower else "input"
        elif "timer" in req_lower or "pwm" in req_lower:
            peripheral = "TIM3"
            if "pwm" in req_lower:
                configuration["mode"] = "pwm"
                configuration["frequency"] = 1000  # Hz
        elif "dma" in req_lower:
            peripheral = "DMA1"
            configuration["channel"] = 5 if "uart" in req_lower else 2
        elif "spi" in req_lower:
            peripheral = "SPI1"
        elif "i2c" in req_lower:
            peripheral = "I2C1"
        else:
            peripheral = "UNKNOWN"

        return {
            "peripheral": peripheral,
            "configuration": configuration,
            "request": request,
        }

    async def _generate_hardware_plan(
        self,
        parsed: dict[str, Any],
        chip_family: str,
    ) -> dict[str, Any]:
        """Generate hardware plan via hardware workflow or inline."""
        peripheral = parsed.get("peripheral", "")
        config = parsed.get("configuration", {})

        # Generate plan inline (HardwareWorkflow integration would be cleaner in production)
        plan_steps: list[dict[str, Any]] = []

        if peripheral == "CAN1":
            timing = config.get("timing", {})
            plan_steps = [
                {"order": 1, "phase": "clock", "action": "Enable CAN1 clock", "code": "RCC->APB1ENR |= RCC_APB1ENR_CAN1EN;"},
                {"order": 2, "phase": "pin", "action": "Configure CAN TX (PD1/AF8) and RX (PD0/AF8)", "code": "GPIOD->MODER = (GPIOD->MODER & ~0xF0) | 0xA0; // AF PP"},
                {"order": 3, "phase": "init", "action": "Enter init mode", "code": "CAN1->MCR |= CAN_MCR_INRQ; while(!(CAN1->MSR & CAN_MSR_INAK));"},
                {"order": 4, "phase": "config", "action": f"Configure bit timing: SJW={timing.get('SJW',1)}, BS1={timing.get('BS1',6)}, BS2={timing.get('BS2',8)}, PRESCALER={timing.get('prescaler',6)}", "code": f"CAN1->BTR = {(timing.get('SJW',1)-1) | ((timing.get('BS1',6)-1)<<16) | ((timing.get('BS2',8)-1)<<20) | ((timing.get('prescaler',6)-1)<<0)};"},
                {"order": 5, "phase": "filter", "action": "Configure filter (accept all)", "code": "CAN1->FMR |= CAN_FMR_FINIT; CAN1->FA1R = 0; // Filter all pass"},
                {"order": 6, "phase": "start", "action": "Exit init mode", "code": "CAN1->MCR &= ~CAN_MCR_INRQ;"},
            ]
        elif peripheral == "USART1":
            baudrate = config.get("baudrate", 115200)
            plan_steps = [
                {"order": 1, "phase": "clock", "action": "Enable USART1 and GPIOA clocks", "code": "RCC->APB2ENR |= RCC_APB2ENR_USART1EN | RCC_APB2ENR_GPIOAEN;"},
                {"order": 2, "phase": "pin", "action": "Configure PA9 (TX) and PA10 (RX)", "code": "GPIOA->MODER = (GPIOA->MODER & ~0xF000) | 0xA000; // AF mode"},
                {"order": 3, "phase": "config", "action": f"Configure baudrate {baudrate}", "code": f"USART1->BRR = 42000000 / {baudrate};"},
                {"order": 4, "phase": "config", "action": "Configure CR1 (8N1, TX+RX enabled)", "code": "USART1->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE | USART_CR1_RXNEIE;"},
            ]
        elif peripheral == "GPIOA":
            mode = config.get("mode", "output")
            if mode == "output":
                plan_steps = [
                    {"order": 1, "phase": "clock", "action": "Enable GPIOA clock", "code": "RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;"},
                    {"order": 2, "phase": "config", "action": "Configure PA5 as output push-pull", "code": "GPIOA->MODER = (GPIOA->MODER & ~0xC00) | 0x400; // Output mode"},
                    {"order": 3, "phase": "config", "action": "Configure output speed", "code": "GPIOA->OSPEEDR |= 0xC00; // High speed"},
                ]
            else:
                plan_steps = [
                    {"order": 1, "phase": "clock", "action": "Enable GPIOA clock", "code": "RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;"},
                    {"order": 2, "phase": "config", "action": "Configure PA5 as input", "code": "GPIOA->MODER &= ~0xC00; // Input mode"},
                    {"order": 3, "phase": "config", "action": "Enable pull-up", "code": "GPIOA->PUPDR = (GPIOA->PUPDR & ~0xC00) | 0x400; // Pull-up"},
                ]
        else:
            plan_steps = [
                {"order": 1, "phase": "clock", "action": f"Enable {peripheral} clock in RCC", "code": f"RCC->APBxENR |= RCC_APBxENR_{peripheral}EN;"},
                {"order": 2, "phase": "config", "action": "Configure peripheral registers", "code": "// Peripheral-specific configuration"},
            ]

        return {
            "peripheral": peripheral,
            "steps": plan_steps,
            "estimated_lines": len(plan_steps) + 2,
        }

    async def _generate_code(
        self,
        parsed: dict[str, Any],
        hw_plan: dict[str, Any],
        style: str,
    ) -> dict[str, Any]:
        """Generate C code from hardware plan."""
        peripheral = parsed.get("peripheral", "")
        config = parsed.get("configuration", {})
        plan_steps = hw_plan.get("steps", [])

        # Build code
        lines: list[str] = []

        if style == "register":
            # Pure register-level code
            for step in plan_steps:
                if step.get("code"):
                    lines.append(f"    {step['code']}")
        elif style == "hal":
            # HAL-style code
            for step in plan_steps:
                phase = step.get("phase", "")
                if phase == "clock":
                    lines.append(f"    // Enable clock for {peripheral}")
                elif phase == "pin":
                    lines.append(f"    // Configure pins for {peripheral}")
                elif phase == "config":
                    lines.append(f"    // Configure {peripheral}")
                lines.append(f"    /* TODO: {step.get('action', '')} */")
        else:
            # Commented register code
            for step in plan_steps:
                action = step.get("action", "")
                code = step.get("code", "")
                lines.append(f"    // {action}")
                if code:
                    lines.append(f"    {code}")

        return {
            "lines": lines,
            "peripheral": peripheral,
            "configuration": config,
            "style": style,
        }

    async def _validate_code(
        self,
        generated: dict[str, Any],
        hw_plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate generated code."""
        lines = generated.get("lines", [])
        code = "\n".join(lines)
        errors: list[str] = []
        warnings: list[str] = []

        # Basic checks
        if not code:
            errors.append("No code generated")
        else:
            # Check for clock enable
            if "RCC" not in code:
                warnings.append("No RCC clock enable found — peripheral may not work")
            # Check for bare register writes (simple heuristic)
            import re
            lines_without_comment = [ln for ln in code.splitlines() if not ln.strip().startswith("//")]
            code_body = "\n".join(lines_without_comment)
            bare_writes = re.findall(r"\bGPIO\d*->\w+\s*=", code_body)
            if bare_writes:
                warnings.append(f"Found {len(bare_writes)} GPIO register writes — ensure clock is enabled first")

        # Validate via hardware validator if available
        allocation = {"peripherals": [hw_plan.get("peripheral", "")]}
        if self._hardware_validator:
            validation = self._hardware_validator.validate_code(code, allocation)
            for f in validation.findings:
                if f.severity.value in ("ERROR", "error"):
                    errors.append(f"[{f.rule_id}] {f.message}")
                elif f.severity.value in ("WARNING", "warning"):
                    warnings.append(f"[{f.rule_id}] {f.message}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "lines_of_code": len([l for l in lines if l.strip() and not l.strip().startswith("//")]),
        }

    async def _format_output(
        self,
        generated: dict[str, Any],
        validation: dict[str, Any],
        output_format: str,
        parsed: dict[str, Any],
    ) -> dict[str, Any]:
        """Format code for output and optionally write atomically via EditSystem."""
        lines = generated.get("lines", [])
        peripheral = parsed.get("peripheral", "")
        config = parsed.get("configuration", {})
        warnings: list[str] = []
        warnings.extend(validation.get("warnings", []))
        edit_id: str | None = None

        if output_format == "c_file":
            header = f"""/* Auto-generated {peripheral} initialization
 * Chip: {self.context.get('chip_family', 'STM32')}
 * Style: {self.context.get('style', 'register')}
 * DO NOT EDIT — regenerate via AI_SUPPORT
 */

#include "stm32f4xx.h"
"""
            init_func = f"void {peripheral.lower()}_init(void) {{\n"
            footer = "\n}"
            code = header + init_func + "\n".join(lines) + footer

        elif output_format == "snippet":
            code = "\n".join(lines)

        else:  # full_driver
            code = f"""/* {peripheral} Driver - Auto-generated by AI_SUPPORT */
#include "stm32f4xx.h"

/**
 * Initialize {peripheral}
 */
void {peripheral.lower()}_init(void) {{
"""
            for line in lines:
                code += f"{line}\n"
            code += """}

/* Additional functions can be added here */
"""

        # Atomically write generated code via EditSystem
        if self._edit_system and output_format == "c_file":
            file_path = self.context.get("target_file")
            if file_path:
                try:
                    edit_id = await self._edit_system.write(
                        file_path,
                        code,
                        create_snapshot=True,
                    )
                    warnings.append(f"Code written atomically to {file_path} (edit_id={edit_id})")
                except Exception as e:
                    warnings.append(f"EditSystem write failed: {e} — code returned in output only")

        return {
            "code": code,
            "warnings": warnings,
            "format": output_format,
            "edit_id": edit_id,
        }
