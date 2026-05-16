import re
from typing import Dict, List, Optional

"""Local generated-code reviewer.

The reviewer rejects outputs that violate the output allowlist, use unsupported
register symbols, miss required hardware decisions, or contradict retrieved
evidence. It is the last local gate before generated files are accepted.
"""

from src.infrastructure.models import AgentState, EvidenceBundle, TaskPlan


class ReviewSupport:
    def __init__(self, agent):
        self.agent = agent

    def run_local_output_checks(
        self,
        state: AgentState,
        allowed_outputs: List[str],
        evidence: EvidenceBundle,
        understanding_lines: List[str],
        reference_hints: Optional[Dict[str, List[str]]] = None,
    ) -> List[str]:
        findings: List[str] = []
        files = {path: state.generated_files.get(path, "") for path in allowed_outputs}
        header_path = next((path for path in allowed_outputs if path.endswith(".h")), "")
        source_path = next((path for path in allowed_outputs if path.endswith(".c")), "")
        header_code = files.get(header_path, "")
        source_code = files.get(source_path, "")
        combined_code = "\n".join(code for code in (header_code, source_code) if code)

        if not header_code or not source_code:
            return ["Missing generated header or source content."]
        if not re.search(r"\btypedef\s+struct\b", header_code):
            findings.append("Header does not define a public configuration or data structure.")

        header_signatures = self.extract_function_signatures(header_code, expect_definition=False)
        source_signatures = self.extract_function_signatures(source_code, expect_definition=True)
        if not header_signatures:
            findings.append("Header does not expose any public API declarations.")
        if not source_signatures:
            findings.append("Source does not implement any public API functions.")

        findings.extend(self.find_signature_mismatches(header_code, source_code)[:4])

        if re.search(r"\bUSART_HandleTypeDef\b", source_code):
            findings.append("Source uses invalid HAL type USART_HandleTypeDef; STM32 HAL expects UART_HandleTypeDef.")
        if re.search(r"\bhi2c\w*\b", source_code, re.IGNORECASE):
            findings.append("Source mixes unrelated I2C handles into UART driver implementation.")
        if re.search(r"\bconfig\.[A-Za-z_]\w*", source_code) and not re.search(r"\b(?:uart_config_t|const\s+uart_config_t\s*\*|uart_config_t\s*\*)\s+config\b", source_code):
            findings.append("Source references config fields without declaring a matching uart_config_t config object.")

        invented_helper_calls = re.findall(
            r"\b(?:USART_BaudRateInit|USART_BaudRateDeInit|HAL_USART_SendData|HAL_USART_ReceiveData|HAL_USART_GetReceptionStatus|HAL_USARTEx_EnableTransmission|HAL_USARTEx_EnableReception|HAL_USARTEx_DisableTransmission|HAL_USARTEx_DisableReception)\b",
            source_code,
        )
        if invented_helper_calls:
            findings.append("Source calls non-standard USART/HAL helper APIs: " + ", ".join(self.dedupe_preserve_order(invented_helper_calls)[:4]))

        unsupported_anchors = self.find_unsupported_traceability_anchors(combined_code, evidence, understanding_lines, reference_hints)
        if unsupported_anchors:
            findings.append("Code contains hardware-specific anchors not supported by retrieved documents: " + ", ".join(unsupported_anchors[:5]))

        traceability_gaps = self.find_required_traceability_gaps(combined_code, understanding_lines, reference_hints)
        if traceability_gaps:
            findings.append("Code misses required hardware decisions from the grounded understanding: " + ", ".join(traceability_gaps[:5]))

        schema_violations = self.find_register_schema_violations(combined_code, reference_hints)
        if schema_violations:
            findings.append("Code uses register-level symbols outside register_schema_authoritative: " + ", ".join(schema_violations[:6]))

        static_findings = self.run_generated_static_checks(files)
        findings.extend(static_findings[:6])

        return self.dedupe_preserve_order(findings)

    def run_generated_static_checks(self, files: Dict[str, str]) -> List[str]:
        findings: List[str] = []
        for path, code in files.items():
            if not code:
                continue
            if code.count("{") != code.count("}"):
                findings.append(f"{path}: static check failed: unbalanced braces.")
            if code.count("(") != code.count(")"):
                findings.append(f"{path}: static check failed: unbalanced parentheses.")
            if path.endswith(".h") and not re.search(r"#pragma\s+once|#ifndef\s+\w+", code):
                findings.append(f"{path}: static check failed: missing include guard or #pragma once.")
            if re.search(r"\bTODO\b|\bFIXME\b", code, re.IGNORECASE):
                findings.append(f"{path}: static check failed: unresolved TODO/FIXME marker.")
            if re.search(r"\bHAL_[A-Za-z0-9_]+\s*\(", code) and "stm32f4xx_hal" not in code.lower():
                findings.append(f"{path}: static check failed: HAL calls require explicit HAL header evidence/include.")
        return findings

    def find_register_schema_violations(self, code: str, reference_hints: Optional[Dict[str, List[str]]] = None) -> List[str]:
        if not isinstance(reference_hints, dict):
            return []
        schema_entries = reference_hints.get("register_schema", [])
        if not isinstance(schema_entries, list) or not schema_entries:
            return []
        allowed_tokens = set()
        for entry in schema_entries:
            if not isinstance(entry, dict):
                continue
            register = str(entry.get("register", "")).strip()
            if not register:
                continue
            allowed_tokens.add(register.upper())
            allowed_tokens.add(register.split("_")[-1].upper())
            for bitfield in entry.get("bitfields", []):
                token = str(bitfield).strip()
                if token:
                    allowed_tokens.add(token.upper())

        used_tokens = set()
        used_tokens.update(re.findall(r"\b(?:RCC|GPIO[A-Ix]?|USART[1-6x]?|UART[1-8x]?|DMA[12x]?|TIM(?:\d+|x)?|NVIC|EXTI|SYSCFG|FLASH|PWR)_[A-Z0-9]+\b", code))
        used_tokens.update(re.findall(r"->\s*(CR1|CR2|CR3|SR|DR|BRR|GTPR|RTOR|RQR|ISR|ICR|RDR|TDR|AHB1ENR|APB1ENR|APB2ENR|MODER|OTYPER|OSPEEDR|PUPDR|AFRL|AFRH|SxCR|SxNDTR|SxPAR|SxM0AR)\b", code))
        checked_tokens = {
            token.upper()
            for token in used_tokens
            if token and token.upper() not in {"NVIC", "GPIO", "RCC", "USART", "UART", "DMA", "TIM"}
        }
        return sorted(token for token in checked_tokens if token not in allowed_tokens)

    def find_required_traceability_gaps(
        self,
        code: str,
        understanding_lines: List[str],
        reference_hints: Optional[Dict[str, List[str]]] = None,
    ) -> List[str]:
        required_tokens: List[str] = []
        for line in understanding_lines:
            for token in re.findall(r"\b(?:USART\d+|UART\d+|GPIO[A-I]|P[A-I]\d+|AF\d+|[A-Z_]+IRQn)\b", str(line)):
                if token not in required_tokens:
                    required_tokens.append(token)
        if isinstance(reference_hints, dict):
            for token in reference_hints.get("register_reference_hints", []) + reference_hints.get("bitfield_reference_hints", []):
                text = str(token).strip()
                if text and text not in required_tokens:
                    required_tokens.append(text)
        lowered_code = code.lower()
        missing = [token for token in required_tokens if token.lower() not in lowered_code]
        return missing[:6]

    def find_unsupported_traceability_anchors(
        self,
        source_code: str,
        evidence: EvidenceBundle,
        understanding_lines: List[str],
        reference_hints: Optional[Dict[str, List[str]]] = None,
    ) -> List[str]:
        support_text_parts: List[str] = []
        for hit in evidence.retrieved_hits[:3]:
            support_text_parts.extend([
                str(hit.path),
                str(hit.summary),
                str(hit.text),
                str(hit.metadata.get("section", "") if isinstance(hit.metadata, dict) else ""),
            ])
        support_text_parts.extend(understanding_lines)
        if isinstance(reference_hints, dict):
            support_text_parts.extend(reference_hints.get("register_reference_hints", []))
            support_text_parts.extend(reference_hints.get("bitfield_reference_hints", []))
            support_text_parts.extend(reference_hints.get("notes", []))
            support_text_parts.extend(self.flatten_register_schema_entries(reference_hints.get("register_schema", [])))
        support_text = " ".join(part for part in support_text_parts if part).lower()
        anchor_pattern = re.compile(r"\b(?:USART\d+|UART\d+|USART\d+_IRQn|[A-Z]{1,2}\d+|AF\d+|GPIO[A-I])\b")
        anchors = self.dedupe_preserve_order(anchor_pattern.findall(source_code))
        broadly_supported_registers = {"cr1", "cr2", "cr3", "sr", "dr", "brr"}
        unsupported = []
        for anchor in anchors:
            normalized = anchor.lower()
            if normalized in support_text:
                continue
            if normalized in broadly_supported_registers and any(marker in support_text for marker in ("reference manual", "register", "usart", "uart")):
                continue
            unsupported.append(anchor)
        return unsupported[:6]

    def extract_driver_api_names(self, spec_data: Dict) -> List[str]:
        names: List[str] = []
        for entry in spec_data.get("driver_shape", []):
            text = str(entry).strip()
            match = re.match(r"([A-Za-z_]\w*)\s*\(", text)
            if match:
                names.append(match.group(1))
        return self.dedupe_preserve_order(names)

    def find_signature_mismatches(self, header_code: str, source_code: str) -> List[str]:
        findings: List[str] = []
        header_signatures = self.extract_function_signatures(header_code, expect_definition=False)
        source_signatures = self.extract_function_signatures(source_code, expect_definition=True)
        for name, header_signature in header_signatures.items():
            source_signature = source_signatures.get(name)
            if not source_signature:
                continue
            if header_signature != source_signature:
                findings.append(f"Header/source signature mismatch for {name}: '{header_signature}' vs '{source_signature}'")
        return findings

    def collect_reference_hints(self, task: str, plan: TaskPlan) -> Dict[str, List[str]]:
        registers: List[str] = []
        bitfields: List[str] = []
        notes: List[str] = []
        sources: List[str] = []
        register_schema: List[Dict] = []
        chip = plan.target_chip or "STM32F407"
        for chapter in plan.chapter_plan:
            hint_data = self.agent.reference_kb.query_register_hints(task, chapter, chip=chip)
            for key, target in (("registers", registers), ("bitfields", bitfields), ("notes", notes), ("sources", sources)):
                for item in hint_data.get(key, []):
                    text = str(item).strip()
                    if text and text not in target:
                        target.append(text)
        for entry in self.agent._query_register_schema(task, plan):
            if isinstance(entry, dict):
                register_schema.append(entry)
                register_name = str(entry.get("register", "")).strip()
                if register_name and register_name not in registers:
                    registers.append(register_name)
                for bitfield in entry.get("bitfields", []):
                    text = str(bitfield).strip()
                    if text and text not in bitfields:
                        bitfields.append(text)
        return {
            "register_reference_hints": registers[:32],
            "bitfield_reference_hints": bitfields[:32],
            "register_schema": register_schema[:24],
            "notes": notes[:12],
            "sources": sources[:6],
        }

    def format_reference_hint_block(self, reference_hints: Optional[Dict[str, List[str]]]) -> str:
        if not isinstance(reference_hints, dict):
            return "- none"
        lines: List[str] = []
        registers = [str(item).strip() for item in reference_hints.get("register_reference_hints", []) if str(item).strip()]
        bitfields = [str(item).strip() for item in reference_hints.get("bitfield_reference_hints", []) if str(item).strip()]
        notes = [str(item).strip() for item in reference_hints.get("notes", []) if str(item).strip()]
        sources = [str(item).strip() for item in reference_hints.get("sources", []) if str(item).strip()]
        register_schema = [entry for entry in reference_hints.get("register_schema", []) if isinstance(entry, dict)]
        if register_schema:
            lines.append("register_schema_authoritative:")
            for entry in register_schema[:10]:
                citation = entry.get("citation", {}) if isinstance(entry.get("citation", {}), dict) else {}
                lines.append(
                    "- peripheral={peripheral} register={register} offset={offset} reset={reset} access={access} bitfields={bitfields} citation={document}#page-{page}".format(
                        peripheral=str(entry.get("peripheral", "")).strip() or "unknown",
                        register=str(entry.get("register", "")).strip(),
                        offset=str(entry.get("offset", "")).strip(),
                        reset=str(entry.get("reset", "")).strip() or "unknown",
                        access=str(entry.get("access", "")).strip() or "unknown",
                        bitfields=",".join(str(item) for item in entry.get("bitfields", [])[:8]),
                        document=str(citation.get("document", "")).strip(),
                        page=str(citation.get("page", "")).strip(),
                    )
                )
        if registers:
            lines.append("register_reference_hints: " + ", ".join(registers[:12]))
        if bitfields:
            lines.append("bitfield_reference_hints: " + ", ".join(bitfields[:12]))
        if notes:
            lines.append("notes: " + " | ".join(notes[:4]))
        if sources:
            lines.append("sources: " + ", ".join(sources[:3]))
        return "\n".join(lines) if lines else "- none"

    def flatten_register_schema_entries(self, entries) -> List[str]:
        flattened: List[str] = []
        if not isinstance(entries, list):
            return flattened
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            citation = entry.get("citation", {}) if isinstance(entry.get("citation", {}), dict) else {}
            flattened.append(" ".join([
                str(entry.get("peripheral", "")),
                str(entry.get("register", "")),
                str(entry.get("offset", "")),
                str(entry.get("reset", "")),
                str(entry.get("access", "")),
                " ".join(str(item) for item in entry.get("bitfields", [])),
                str(citation.get("document", "")),
                str(citation.get("page", "")),
                str(citation.get("section", "")),
            ]))
        return flattened

    def extract_function_signatures(self, code: str, expect_definition: bool) -> Dict[str, str]:
        return self.agent.response_parser.extract_function_signatures(code, expect_definition)

    def dedupe_preserve_order(self, items: List[str]) -> List[str]:
        seen = set()
        ordered: List[str] = []
        for item in items:
            if not item or item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered
