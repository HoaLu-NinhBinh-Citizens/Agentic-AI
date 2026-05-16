import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

"""Reference-manual chapter worker support.

This module coordinates chapter workers, validates their JSON notes, and merges
them into an integrated spec that downstream codegen/reviewer logic can use.
"""

from src.core.config.agent_prompts import CHAPTER_CACHE_MAX_AGE_HOURS, CHAPTER_NOTE_RETRY_LIMIT, RM_NOTES_ROOT
from src.core.config.chapter_config import CHAPTER_VALIDATION_RULES, STM32F407_REGISTER_HINTS
from src.infrastructure.models import AgentState, ChapterNote, TaskPlan


class DocumentWorkerSupport:
    def __init__(self, agent):
        self.agent = agent

    async def build_integrated_reference_spec(self, task: str, plan: Optional[TaskPlan] = None, state: Optional[AgentState] = None) -> str:
        plan = plan or self.agent._create_task_plan(task)
        if not plan.use_chapter_workers:
            fallback = {
                "task": task,
                "implementation_order": [],
                "cross_dependencies": [],
                "required_register_groups": [],
                "safety_checks": [],
                "driver_shape": [],
                "chapter_summary": {},
                "allowed_outputs": plan.allowed_outputs,
                "mode": plan.mode,
                "target_family": plan.target_family,
                "target_chip": plan.target_chip,
            }
            return json.dumps(fallback, indent=2)

        chapter_plan = plan.chapter_plan
        session_dir = self.make_rm_session_dir(task)
        chapter_notes: List[ChapterNote] = []

        for chapter in chapter_plan:
            try:
                note = await self.generate_chapter_note(task, chapter, session_dir, retry_count=CHAPTER_NOTE_RETRY_LIMIT, state=state)
            except TimeoutError as exc:
                self.agent._log_agent_phase("observe", f"Chapter worker timed out for {chapter}: {exc}")
                continue
            if note:
                chapter_notes.append(note)

        if not chapter_notes:
            fallback = {
                "task": task,
                "implementation_order": chapter_plan,
                "cross_dependencies": [],
                "required_register_groups": [],
                "safety_checks": [],
                "driver_shape": [],
                "chapter_summary": {},
                "allowed_outputs": plan.allowed_outputs,
                "mode": plan.mode,
                "target_family": plan.target_family,
                "target_chip": plan.target_chip,
            }
            return json.dumps(fallback, indent=2)

        return await self.merge_chapter_notes(task, chapter_notes, session_dir, plan)

    def should_use_chapter_workers(self, task: str) -> bool:
        text = task.lower()
        return "stm32" in text or "uart" in text or "usart" in text or "gpio" in text or "dma" in text

    def select_chapter_plan(self, task: str) -> List[str]:
        """Select STM32 reference manual chapters based on task content."""
        text = task.lower()
        chapters: List[str] = []

        # Detect required peripherals from task
        if "uart" in text or "usart" in text or "serial" in text:
            chapters.extend(["RCC", "GPIO", "AF_MAPPING", "USART", "NVIC"])
        elif "gpio" in text or "pin" in text or "led" in text or "button" in text:
            chapters.extend(["RCC", "GPIO"])
        elif "dma" in text:
            chapters.extend(["RCC", "DMA"])
        elif "timer" in text or "pwm" in text or "capture" in text:
            chapters.extend(["RCC", "TIMERS"])
        elif "can" in text or "canbus" in text:
            chapters.extend(["RCC", "CAN"])
        elif "spi" in text:
            chapters.extend(["RCC", "GPIO", "AF_MAPPING", "SPI"])
        elif "i2c" in text:
            chapters.extend(["RCC", "GPIO", "AF_MAPPING", "I2C"])
        else:
            # Default: basic peripherals for embedded tasks
            chapters.extend(["RCC", "GPIO"])

        # Add clock tree if relevant
        if "clock" in text or "pll" in text or "baud" in text or "system clock" in text:
            if "CLOCK_TREE" not in chapters:
                chapters.insert(0, "CLOCK_TREE")

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for chapter in chapters:
            if chapter not in seen:
                seen.add(chapter)
                deduped.append(chapter)
        return deduped

    def make_rm_session_dir(self, task: str) -> Path:
        slug = "_".join(re.findall(r"[a-z0-9]+", task.lower())[:8]) or "task"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = self.agent.file_tools.resolve_relative_path(f"{RM_NOTES_ROOT}/{timestamp}_{slug}")
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    async def generate_chapter_note(
        self,
        task: str,
        chapter: str,
        session_dir: Path,
        retry_count: int = 0,
        state: Optional[AgentState] = None,
    ) -> Optional[ChapterNote]:
        cached = self.load_cached_chapter_note(task, chapter)
        if cached:
            note_relpath = f"{RM_NOTES_ROOT}/{session_dir.name}/{chapter.lower()}_note.json"
            self.agent.file_tools.write_file(note_relpath, json.dumps(cached, indent=2))
            return ChapterNote(chapter=chapter, note_path=note_relpath, content=cached)

        chapter_state = state or AgentState(task=task)
        evidence = self.agent._ensure_retrieval_confidence(f"{task} {chapter}", chapter_state)
        evidence_context = self.agent.evidence_builder.format_for_prompt(evidence, max_chars=2200)
        if evidence.confidence == "low":
            if state is not None:
                state.response_stage = f"chapter_retrieval_gate:{chapter}"
                state.response_preview = self.agent._preview_text(state.last_evidence_summary or state.retrieval_blocker, limit=400)
            raise ValueError(chapter_state.retrieval_blocker or f"Retrieval confidence too low for chapter worker {chapter}")
        target_chip = self.agent._resolve_target_chip(task, state=state)
        refs = self.agent.reference_kb.query(f"{task} {chapter}", limit=2)
        register_hint_data = self.agent.reference_kb.query_register_hints(task, chapter, chip=target_chip)
        reference_lines = []
        for ref in refs:
            reference_lines.append(f"- {ref['filename']}")
            if ref["summary"]:
                reference_lines.append(f"  summary: {ref['summary']}")
            if ref["topics"]:
                reference_lines.append(f"  topics: {ref['topics']}")
            if ref["chapters"]:
                reference_lines.append(f"  chapters: {ref['chapters']}")
        if register_hint_data.get("registers"):
            reference_lines.append(f"- register_hints: {', '.join(register_hint_data['registers'])}")
        if register_hint_data.get("bitfields"):
            reference_lines.append(f"- bitfield_hints: {', '.join(register_hint_data['bitfields'])}")
        if register_hint_data.get("notes"):
            reference_lines.append(f"- implementation_hints: {' | '.join(register_hint_data['notes'])}")
        reference_text = "\n".join(reference_lines) if reference_lines else "- No reference hits."
        rules = CHAPTER_VALIDATION_RULES.get(chapter, {})
        register_tokens = ", ".join(rules.get("register_patterns", [])) or "none"
        bitfield_tokens = ", ".join(rules.get("bitfield_patterns", [])) or "none"
        retry_instruction = ""
        if retry_count < CHAPTER_NOTE_RETRY_LIMIT:
            retry_instruction = (
                "This is a retry because earlier output missed required STM32 signals. "
                "Make sure the JSON explicitly mentions the required registers and bitfields."
            )

        chapter_output_rules = [
            "Each key_registers/register_hints item must be a short STM32 register or register-group identifier, not a sentence.",
            "Each bitfields/bitfield_hints item must be a short STM32 bit or bitfield identifier, not a serialized object.",
            "Never emit JSON-looking strings, C statements, comments, or pseudocode inside key_registers/bitfields/register_hints/bitfield_hints.",
        ]
        if chapter == "NVIC":
            chapter_output_rules.extend([
                "Prefer identifiers like NVIC_ISER, NVIC_IPR, USARTx_IRQn, IRQn, priority, enable.",
                "Do not emit Python-dict-like BitField objects for NVIC entries.",
            ])
        if chapter == "DMA":
            chapter_output_rules.extend([
                "Prefer identifiers like DMA1, DMA2, DMA_SxCR, DMA_SxNDTR, DMA_SxPAR, DMA_SxM0AR, DMA_HISR, DMA_HIFCR.",
                f"Do not emit controller-specific fake names unless they correspond to {target_chip or 'the target'} DMA notation.",
            ])

        prompt = f"""Task: {task}
Worker focus: {chapter}

Available reference context:
{reference_text}

Retrieved evidence:
{evidence_context}

You are a reference-manual analysis worker.
    - Think -> act -> observe -> repeat.
    - Use only the evidence and reference context provided below.
    - Never guess missing STM32 register or bitfield details.
    - If the available context is insufficient, say that you do not know based on current context.
- Do not write C code.
- Do not explain outside JSON.
- Do not include markdown.
- Return one compact JSON object only.
- Required register signals: {register_tokens}
- Required bitfield signals: {bitfield_tokens}
- {retry_instruction if retry_instruction else 'First-pass analysis.'}
- Output hygiene rules:
{chr(10).join(f"- {rule}" for rule in chapter_output_rules)}

Return JSON only with this schema:
{{
  "chapter": "{chapter}",
  "purpose": "...",
  "key_registers": ["REG_OR_GROUP"],
  "bitfields": ["REG.BIT"],
  "register_hints": ["REG_OR_GROUP"],
  "bitfield_hints": ["BIT_NAME"],
  "init_sequence": ["..."],
  "dependencies": ["..."],
  "caveats": ["..."],
  "evidence": ["short RM-grounded statements"]
}}
"""
        response = await self.agent._guarded_llm_generate(prompt, "chapter_worker", state=chapter_state)
        self.agent._log_response_preview(f"chapter:{chapter}", response)
        data = self.agent._extract_json_object(response)
        data = self.normalize_chapter_note(chapter, data, response, task=task, target_chip=target_chip)

        if data.get("validation_status") == "partial" and retry_count > 0:
            return await self.generate_chapter_note(task, chapter, session_dir, retry_count=retry_count - 1)

        note_relpath = f"{RM_NOTES_ROOT}/{session_dir.name}/{chapter.lower()}_note.json"
        self.agent.file_tools.write_file(note_relpath, json.dumps(data, indent=2))
        return ChapterNote(chapter=chapter, note_path=note_relpath, content=data)

    def load_cached_chapter_note(self, task: str, chapter: str) -> Optional[Dict]:
        notes_root = self.agent.file_tools.resolve_relative_path(RM_NOTES_ROOT)
        if not notes_root.exists():
            return None

        task_terms = set(re.findall(r"[a-z0-9]+", task.lower()))
        newest_candidates = sorted(
            notes_root.glob(f"*/{chapter.lower()}_note.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

        max_age_seconds = CHAPTER_CACHE_MAX_AGE_HOURS * 3600
        now_ts = datetime.now().timestamp()
        for note_path in newest_candidates[:10]:
            try:
                if now_ts - note_path.stat().st_mtime > max_age_seconds:
                    continue
                session_name = note_path.parent.name.lower()
                session_terms = set(re.findall(r"[a-z0-9]+", session_name))
                if len(task_terms & session_terms) < 2:
                    continue
                data = json.loads(note_path.read_text(encoding="utf-8"))
                target_chip = self.agent._resolve_target_chip(task)
                data = self.normalize_chapter_note(chapter, data, json.dumps(data), task=task, target_chip=target_chip)
                if data.get("validation_status") == "ok":
                    return data
            except (OSError, json.JSONDecodeError):
                continue
        return None

    async def merge_chapter_notes(
        self,
        task: str,
        chapter_notes: List[ChapterNote],
        session_dir: Path,
        plan: Optional[TaskPlan] = None,
    ) -> str:
        plan = plan or self.agent._create_task_plan(task)
        merged = self.normalize_integrated_spec(task, chapter_notes, None, "", plan)
        spec_relpath = f"{RM_NOTES_ROOT}/{session_dir.name}/integrated_spec.json"
        self.agent.file_tools.write_file(spec_relpath, json.dumps(merged, indent=2))
        return json.dumps(merged, indent=2)

    def build_merge_note_payload(self, note: ChapterNote) -> Dict:
        content = note.content or {}
        return {
            "chapter": note.chapter,
            "purpose": str(content.get("purpose", "")).strip(),
            "key_registers": list(content.get("key_registers", []))[:8],
            "bitfields": list(content.get("bitfields", []))[:8],
            "register_hints": list(content.get("register_hints", []))[:8],
            "bitfield_hints": list(content.get("bitfield_hints", []))[:8],
            "init_sequence": list(content.get("init_sequence", []))[:6],
            "dependencies": list(content.get("dependencies", []))[:6],
            "caveats": list(content.get("caveats", []))[:4],
            "validation_status": str(content.get("validation_status", "unknown")),
            "missing_signals": list(content.get("missing_signals", []))[:6],
            "validation_notes": list(content.get("validation_notes", []))[:6],
        }

    def build_codegen_spec_payload(self, spec_data: Dict, plan: TaskPlan, allowed_outputs: List[str]) -> Dict:
        return {
            "task": str(spec_data.get("task", plan.task)).strip() or plan.task,
            "mode": str(spec_data.get("mode", plan.mode)).strip() or plan.mode,
            "target_family": str(spec_data.get("target_family", plan.target_family)).strip() or plan.target_family,
            "target_chip": str(spec_data.get("target_chip", plan.target_chip)).strip() or plan.target_chip,
            "implementation_order": list(spec_data.get("implementation_order", []))[:10],
            "cross_dependencies": list(spec_data.get("cross_dependencies", []))[:10],
            "required_register_groups": list(spec_data.get("required_register_groups", []))[:16],
            "register_reference_hints": list(spec_data.get("register_reference_hints", []))[:20],
            "bitfield_reference_hints": list(spec_data.get("bitfield_reference_hints", []))[:20],
            "safety_checks": list(spec_data.get("safety_checks", []))[:8],
            "driver_shape": list(spec_data.get("driver_shape", []))[:8],
            "implementation_decisions": dict(spec_data.get("implementation_decisions", {})),
            "codegen_rules": list(spec_data.get("codegen_rules", []))[:10],
            "allowed_outputs": list(allowed_outputs),
            "chapter_summary": spec_data.get("chapter_summary", {}),
            "validation_warnings": list(spec_data.get("validation_warnings", []))[:8],
        }

    def normalize_chapter_note(self, chapter: str, data: Optional[Dict], response: str, task: str = "", target_chip: str = "") -> Dict:
        normalized = {
            "chapter": chapter,
            "purpose": "",
            "key_registers": [],
            "bitfields": [],
            "register_hints": [],
            "bitfield_hints": [],
            "init_sequence": [],
            "dependencies": [],
            "caveats": [],
            "evidence": [],
            "validation_status": "unknown",
            "missing_signals": [],
            "validation_notes": [],
        }

        if isinstance(data, dict):
            normalized["purpose"] = str(data.get("purpose", "")).strip()
            for key in ("key_registers", "bitfields", "register_hints", "bitfield_hints", "init_sequence", "dependencies", "caveats", "evidence"):
                value = data.get(key, [])
                if isinstance(value, list):
                    normalized[key] = [str(item).strip() for item in value if str(item).strip()]
                elif value:
                    normalized[key] = [str(value).strip()]

        if not normalized["purpose"]:
            normalized["purpose"] = f"Analysis note for {chapter}"

        if not normalized["evidence"]:
            preview = re.sub(r"\s+", " ", response[:240]).strip()
            if preview:
                normalized["evidence"] = [preview]

        missing_signals = self.validate_chapter_note_signals(chapter, normalized)
        validation_notes = self.validate_chapter_note_semantics(chapter, normalized, task=task, target_chip=target_chip)
        normalized["missing_signals"] = missing_signals
        normalized["validation_notes"] = validation_notes
        normalized["validation_status"] = "ok" if not missing_signals and not validation_notes else "partial"

        return normalized

    def normalize_integrated_spec(
        self,
        task: str,
        chapter_notes: List[ChapterNote],
        data: Optional[Dict],
        response: str,
        plan: Optional[TaskPlan] = None,
    ) -> Dict:
        plan = plan or self.agent._create_task_plan(task)
        chapter_names = [note.chapter for note in chapter_notes]
        normalized = {
            "task": task,
            "mode": plan.mode,
            "target_family": plan.target_family,
            "target_chip": plan.target_chip,
            "implementation_order": chapter_names,
            "cross_dependencies": [],
            "required_register_groups": [],
            "register_reference_hints": [],
            "bitfield_reference_hints": [],
            "safety_checks": [],
            "driver_shape": [],
            "implementation_decisions": {},
            "codegen_rules": [],
            "allowed_outputs": plan.allowed_outputs,
            "chapter_summary": {note.chapter: note.content.get("init_sequence", [])[:3] for note in chapter_notes},
            "validation_warnings": [],
        }

        if isinstance(data, dict):
            normalized["task"] = str(data.get("task", task)).strip() or task
            normalized["mode"] = str(data.get("mode", plan.mode)).strip() or plan.mode
            normalized["target_family"] = str(data.get("target_family", plan.target_family)).strip() or plan.target_family
            normalized["target_chip"] = str(data.get("target_chip", plan.target_chip)).strip() or plan.target_chip
            for key in ("implementation_order", "cross_dependencies", "required_register_groups", "register_reference_hints", "bitfield_reference_hints", "safety_checks", "driver_shape", "codegen_rules"):
                value = data.get(key, normalized[key])
                if isinstance(value, list):
                    normalized[key] = [str(item).strip() for item in value if str(item).strip()]
            implementation_decisions = data.get("implementation_decisions", {})
            if isinstance(implementation_decisions, dict):
                normalized["implementation_decisions"] = {
                    str(key).strip(): str(value).strip()
                    for key, value in implementation_decisions.items()
                    if str(key).strip() and str(value).strip()
                }
            normalized["allowed_outputs"] = self.agent._normalize_allowed_outputs(data.get("allowed_outputs"))
            chapter_summary = data.get("chapter_summary", {})
            if isinstance(chapter_summary, dict):
                normalized["chapter_summary"] = {}
                for chapter, items in chapter_summary.items():
                    if isinstance(items, list):
                        normalized["chapter_summary"][str(chapter)] = [str(item).strip() for item in items if str(item).strip()]
                    elif items:
                        normalized["chapter_summary"][str(chapter)] = [str(items).strip()]

        if not normalized["implementation_order"]:
            normalized["implementation_order"] = chapter_names
        if not normalized["cross_dependencies"]:
            normalized["cross_dependencies"] = self.derive_cross_dependencies(chapter_notes)
        if not normalized["required_register_groups"]:
            normalized["required_register_groups"] = self.derive_required_register_groups(chapter_notes)
        if not normalized["safety_checks"]:
            normalized["safety_checks"] = [
                "Enable the peripheral clock before touching dependent registers.",
                "Configure GPIO alternate-function pins before enabling USART transfer.",
                "Clear and enable NVIC/interrupt sources only after the peripheral is configured.",
            ]
        if not normalized["register_reference_hints"]:
            normalized["register_reference_hints"] = self.derive_register_reference_hints(chapter_notes)
        if not normalized["bitfield_reference_hints"]:
            normalized["bitfield_reference_hints"] = self.derive_bitfield_reference_hints(chapter_notes)
        if not normalized["driver_shape"]:
            normalized["driver_shape"] = [
                "uart_init(config)",
                "uart_write(buffer, length)",
                "uart_read(buffer, length, timeout)",
                "uart_irq_handler()",
            ]
        if not normalized["implementation_decisions"]:
            normalized["implementation_decisions"] = self.derive_implementation_decisions(task, plan, chapter_notes)
        if not normalized["codegen_rules"]:
            normalized["codegen_rules"] = self.derive_codegen_rules(normalized, plan.target_chip)
        if not normalized["allowed_outputs"]:
            normalized["allowed_outputs"] = plan.allowed_outputs
        if not normalized["chapter_summary"]:
            normalized["chapter_summary"] = {"response_preview": [re.sub(r"\s+", " ", response[:240]).strip()]}

        normalized["validation_warnings"] = self.collect_validation_warnings(chapter_notes)
        normalized["validation_warnings"].extend(self.validate_integrated_spec_semantics(normalized, chapter_notes))
        normalized["validation_warnings"] = list(dict.fromkeys(normalized["validation_warnings"]))[:16]
        return normalized

    def validate_chapter_note_signals(self, chapter: str, note: Dict) -> List[str]:
        rules = CHAPTER_VALIDATION_RULES.get(chapter, {})
        if not rules:
            return []
        raw_entries = (
            note.get("key_registers", [])
            + note.get("bitfields", [])
            + note.get("register_hints", [])
            + note.get("bitfield_hints", [])
            + note.get("init_sequence", [])
            + note.get("dependencies", [])
            + note.get("evidence", [])
        )
        haystack = self.build_validation_haystack(raw_entries)
        missing = []
        for pattern in rules.get("register_patterns", []):
            if not re.search(pattern, haystack, re.IGNORECASE):
                missing.append(f"missing register signal: {pattern}")
        for pattern in rules.get("bitfield_patterns", []):
            if not re.search(pattern, haystack, re.IGNORECASE):
                missing.append(f"missing bitfield signal: {pattern}")
        return missing[:12]

    def validate_chapter_note_semantics(self, chapter: str, note: Dict, task: str = "", target_chip: str = "") -> List[str]:
        issues: List[str] = []
        issues.extend(self.find_suspicious_field_entries(note))
        resolved_chip = (target_chip or self.agent._resolve_target_chip(task)).upper()
        chapter_hints = STM32F407_REGISTER_HINTS.get(chapter, {}) if resolved_chip == "STM32F407" else {}
        register_entries = note.get("key_registers", []) + note.get("register_hints", [])
        bitfield_entries = note.get("bitfields", []) + note.get("bitfield_hints", [])
        if chapter_hints.get("registers") and not self.entries_match_reference_hints(register_entries, chapter_hints["registers"]):
            issues.append("missing canonical register hint alignment")
        if chapter_hints.get("bitfields") and not self.entries_match_reference_hints(bitfield_entries, chapter_hints["bitfields"]):
            issues.append("missing canonical bitfield hint alignment")
        return list(dict.fromkeys(issues))[:12]

    def validate_integrated_spec_semantics(self, spec: Dict, chapter_notes: List[ChapterNote]) -> List[str]:
        issues: List[str] = []
        issues.extend(self.find_suspicious_field_entries(spec, fields=(
            "implementation_order",
            "cross_dependencies",
            "required_register_groups",
            "register_reference_hints",
            "bitfield_reference_hints",
            "safety_checks",
            "driver_shape",
        )))
        chapter_names = {note.chapter for note in chapter_notes}
        implementation_order = {str(item).strip() for item in spec.get("implementation_order", [])}
        missing_chapters = [name for name in chapter_names if name not in implementation_order]
        if missing_chapters:
            issues.append("merged spec dropped chapter coverage: " + ", ".join(sorted(missing_chapters[:4])))
        for note in chapter_notes:
            validation_notes = note.content.get("validation_notes", [])
            if validation_notes:
                prefix = "[critical] " if CHAPTER_VALIDATION_RULES.get(note.chapter, {}).get("critical") else ""
                issues.append(f"{prefix}{note.chapter}: " + "; ".join(validation_notes[:3]))
        return list(dict.fromkeys(issues))[:16]

    def find_suspicious_field_entries(self, payload: Dict, fields: Optional[Tuple[str, ...]] = None) -> List[str]:
        issues: List[str] = []
        target_fields = fields or (
            "key_registers",
            "bitfields",
            "register_hints",
            "bitfield_hints",
            "init_sequence",
            "dependencies",
            "caveats",
            "evidence",
        )
        for field_name in target_fields:
            values = payload.get(field_name, [])
            if not isinstance(values, list):
                continue
            for item in values:
                text = str(item).strip()
                if not text:
                    continue
                if field_name in {"key_registers", "register_hints", "required_register_groups", "register_reference_hints"}:
                    if any(token in text for token in ("{", "}", "->", ";", "=")):
                        issues.append(f"{field_name} contains non-register structured text")
                if field_name in {"bitfields", "bitfield_hints", "bitfield_reference_hints"}:
                    if "BitField" in text or any(token in text for token in ("{", "}", "mask", "offset")):
                        issues.append(f"{field_name} contains serialized structure text")
        return issues

    def entries_match_reference_hints(self, entries: List[str], hints: List[str]) -> bool:
        normalized_entries = set()
        for entry in entries:
            normalized_entries.update(self.expand_reference_variants(str(entry)))
        normalized_entries = {item for item in normalized_entries if item}
        if not normalized_entries:
            return False
        for hint in hints:
            hint_variants = {item for item in self.expand_reference_variants(str(hint)) if item}
            if hint_variants & normalized_entries:
                return True
        return False

    def expand_reference_variants(self, token: str) -> List[str]:
        raw = token.strip()
        if not raw:
            return []
        parts = [part for part in re.split(r"[^A-Za-z0-9]+", raw) if part]
        variants = {self.normalize_reference_token(raw)}
        if parts:
            variants.add(self.normalize_reference_token(parts[-1]))
            variants.add(self.normalize_reference_token("".join(parts[-2:])))
        return [item for item in variants if item]

    def normalize_reference_token(self, token: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9]", "", token.upper())
        normalized = re.sub(r"[0-9X]", "#", normalized)
        normalized = re.sub(r"#+", "#", normalized)
        return normalized

    def collect_validation_warnings(self, chapter_notes: List[ChapterNote]) -> List[str]:
        warnings: List[str] = []
        for note in chapter_notes:
            missing = note.content.get("missing_signals", [])
            if missing:
                chapter_rules = CHAPTER_VALIDATION_RULES.get(note.chapter, {})
                prefix = "[critical] " if chapter_rules.get("critical") else ""
                warnings.append(f"{prefix}{note.chapter}: " + "; ".join(missing[:4]))
            validation_notes = note.content.get("validation_notes", [])
            if validation_notes:
                chapter_rules = CHAPTER_VALIDATION_RULES.get(note.chapter, {})
                prefix = "[critical] " if chapter_rules.get("critical") else ""
                warnings.append(f"{prefix}{note.chapter}: " + "; ".join(validation_notes[:4]))
        return warnings[:16]

    def build_validation_haystack(self, entries: List[str]) -> str:
        variants: List[str] = []
        for entry in entries:
            text = str(entry).strip()
            if not text:
                continue
            variants.append(text)
            variants.append(text.replace("_", " "))
            pieces = [part for part in re.split(r"[^A-Za-z0-9]+", text) if part]
            variants.extend(pieces)
            for piece in pieces:
                variants.append(re.sub(r"S\d+", "Sx", piece, flags=re.IGNORECASE))
                variants.append(re.sub(r"USART\d+", "USARTx", piece, flags=re.IGNORECASE))
                variants.append(re.sub(r"DMA\d+", "DMAx", piece, flags=re.IGNORECASE))
                variants.append(re.sub(r"TIM\d+", "TIMx", piece, flags=re.IGNORECASE))
        return " ".join(item for item in variants if item).lower()

    def derive_cross_dependencies(self, chapter_notes: List[ChapterNote]) -> List[str]:
        chapters = {note.chapter for note in chapter_notes}
        deps: List[str] = []
        if {"CLOCK_TREE", "RCC"} & chapters and "USART" in chapters:
            deps.append("USART configuration depends on APB clock selection and RCC peripheral enable.")
        if "GPIO" in chapters and "AF_MAPPING" in chapters:
            deps.append("GPIO mode, speed, pull, and alternate-function selection must align with AF mapping.")
        if "NVIC" in chapters and "USART" in chapters:
            deps.append("NVIC enable must follow USART interrupt source configuration.")
        if "DMA" in chapters and "USART" in chapters:
            deps.append("DMA stream/channel selection must match the USART TX/RX request mapping.")
        if "TIMERS" in chapters and "USART" in chapters:
            deps.append("Timeout or baud-related helper timing must use a timer source consistent with the clock tree.")
        return deps

    def derive_implementation_decisions(self, task: str, plan: TaskPlan, chapter_notes: List[ChapterNote]) -> Dict[str, str]:
        text = task.lower()
        chapters = {note.chapter for note in chapter_notes}
        decisions: Dict[str, str] = {}
        if plan.target_chip == "STM32F407" and ("uart" in text or "usart" in text):
            decisions.update({
                "selected_instance": "USART2",
                "selected_bus": "APB1",
                "selected_gpio_port": "GPIOA",
                "selected_tx_pin": "PA2",
                "selected_rx_pin": "PA3",
                "selected_gpio_af": "AF7",
                "selected_irq": "USART2_IRQn",
                "baudrate_formula": "BRR must be derived from the APB1 peripheral clock for USART2.",
            })
            if "NVIC" in chapters:
                decisions["interrupt_policy"] = "Enable USART2_IRQn only after CR1, BRR, and GPIO alternate-function configuration are complete."
        return decisions

    def derive_codegen_rules(self, spec_data: Dict, target_chip: str = "") -> List[str]:
        chip_lower = target_chip.lower()
        framework = "CMSIS/register-level code"
        if "esp" in chip_lower:
            framework = "ESP-IDF API"
        elif "rp2040" in chip_lower:
            framework = "Raspberry Pi Pico SDK"
        elif "nrf" in chip_lower:
            framework = "nRF Connect SDK"
        rules = [
            "Export and implement the exact API names listed in driver_shape. Do not rename or prefix them.",
            f"Prefer {target_chip or 'the target'} {framework} or established HAL types/macros. Do not invent helper APIs.",
            "Do not call made-up functions such as USART_BaudRateInit, HAL_USART_SendData, or HAL_USARTEx_EnableTransmission.",
            "Keep header and source signatures identical.",
        ]
        implementation_order = set(spec_data.get("implementation_order", []))
        if "AF_MAPPING" in implementation_order:
            rules.append("Implement GPIO alternate-function selection explicitly using the selected AF mapping.")
        if "NVIC" in implementation_order:
            rules.append("Implement IRQ enable/disable using the selected IRQ line and provide uart_irq_handler().")
        if spec_data.get("implementation_decisions"):
            rules.append(f"Use implementation_decisions exactly unless they contradict {target_chip or 'the target'} register definitions.")
        return rules[:10]

    def derive_required_register_groups(self, chapter_notes: List[ChapterNote]) -> List[str]:
        groups: List[str] = []
        for note in chapter_notes:
            for item in note.content.get("key_registers", []):
                if item not in groups:
                    groups.append(item)
        return groups[:24]

    def derive_register_reference_hints(self, chapter_notes: List[ChapterNote]) -> List[str]:
        hints: List[str] = []
        for note in chapter_notes:
            for item in note.content.get("register_hints", []) + note.content.get("key_registers", []):
                if item not in hints:
                    hints.append(item)
        return hints[:32]

    def derive_bitfield_reference_hints(self, chapter_notes: List[ChapterNote]) -> List[str]:
        hints: List[str] = []
        for note in chapter_notes:
            for item in note.content.get("bitfield_hints", []) + note.content.get("bitfields", []):
                if item not in hints:
                    hints.append(item)
        return hints[:32]

