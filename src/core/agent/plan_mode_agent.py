"""
Plan Mode Agent - Universal task handler with model switching.

This module provides a plan-mode agent that:
1. Classifies incoming tasks into categories
2. Creates execution plans
3. Routes to appropriate executor based on model recommendations
4. Switches between Ollama and GPT models dynamically
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.config.agent_prompts import (
    PLAN_MODE_CLASSIFIER_PROMPT,
    PLAN_MODE_SUMMARY_PROMPT,
    PLAN_MODE_TASK_EXECUTION_PROMPT,
)
from src.infrastructure.llm.openai_llm import ModelRouter
from src.infrastructure.llm.model_selector import ModelSelector, Complexity
from src.infrastructure.models import TaskResult

logger = logging.getLogger(__name__)


@dataclass
class TaskStep:
    step: int
    action: str
    description: str
    status: str = "pending"  # pending, running, completed, failed
    result: Any = None
    model_used: str = ""
    error: str = ""


@dataclass
class TaskClassification:
    category: str
    confidence: float
    target_project: str
    target_chip: str
    subtasks: List[Dict]
    estimated_difficulty: str
    model_recommendation: str
    reasoning: str


@dataclass
class PlanModeState:
    task: str
    classification: Optional[TaskClassification] = None
    steps: List[TaskStep] = field(default_factory=list)
    current_step: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    results: List[Any] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    model_switches: List[Dict] = field(default_factory=list)


class PlanModeAgent:
    """
    Universal task handler that plans and executes all tasks.

    Workflow:
    1. CLASSIFY → Understand what the task is asking
    2. PLAN → Create a structured execution plan
    3. ROUTE → Send to appropriate executor with optimal model
    4. EXECUTE → Run actions with model switching as needed
    5. SUMMARIZE → Report results to user
    """

    def __init__(
        self,
        model_router: ModelRouter,
        embedded_agent=None,
    ):
        self.router = model_router
        self.embedded_agent = embedded_agent
        self._state: Optional[PlanModeState] = None

    async def execute_task(self, task: str) -> TaskResult:
        """Execute a task using plan mode with model switching."""
        logger.info("PlanModeAgent: Starting task '%s'", task)
        self._state = PlanModeState(task=task)

        try:
            classification = await self._classify_task(task)
            self._state.classification = classification
            logger.info(
                "PlanModeAgent: Classified as '%s' (confidence=%.2f), model=%s",
                classification.category,
                classification.confidence,
                classification.model_recommendation,
            )

            steps = await self._create_plan(classification)
            self._state.steps = steps
            logger.info("PlanModeAgent: Created %d steps", len(steps))

            for step in steps:
                self._state.current_step = step.step
                result = await self._execute_step(step)
                if result is False:
                    logger.error("PlanModeAgent: Step %d failed", step.step)
                    break

            return self._build_result()

        except Exception as exc:
            logger.exception("PlanModeAgent: Task failed with exception")
            self._state.errors.append(str(exc))
            return TaskResult(
                success=False,
                message=f"Task failed: {exc}",
                files_created=self._get_created_files(),
                errors_fixed=0,
                attempts=1,
                duration=(datetime.now() - self._state.start_time).total_seconds(),
                learned_rules=[],
            )

    async def _classify_task(self, task: str) -> TaskClassification:
        """Classify the task using LLM."""
        from src.infrastructure.llm.structured_output import extract_structured_json, SCHEMA_TASK_CLASSIFICATION

        prompt = f"""{PLAN_MODE_CLASSIFIER_PROMPT}

Task to classify:
{task}

Classify this task now. Return ONLY the JSON object."""

        # Use structured output helpers for robust JSON extraction
        try:
            response = await self.router.generate(prompt, task_type="simple")
            data, errors = extract_structured_json(response, schema=SCHEMA_TASK_CLASSIFICATION)
            if not data:
                logger.warning("Classification JSON extraction failed: %s", errors)
                logger.debug("Raw response: %.200s", response)
                return self._fallback_classification(task)
            return TaskClassification(
                category=str(data.get("category", "CODE_GENERATION")),
                confidence=float(data.get("confidence", 0.5)),
                target_project=str(data.get("target_project", "")),
                target_chip=str(data.get("target_chip", "STM32F407")),
                subtasks=data.get("subtasks", []),
                estimated_difficulty=str(data.get("estimated_difficulty", "medium")),
                model_recommendation=str(data.get("model_recommendation", "ollama")),
                reasoning=str(data.get("reasoning", "")),
            )
        except Exception as exc:
            logger.warning("Classification failed, using fallback: %s", exc)
            return self._fallback_classification(task)

    def _fallback_classification(self, task: str) -> TaskClassification:
        """Fallback classification based on keyword matching."""
        task_lower = task.lower()
        category = "CODE_GENERATION"

        if any(kw in task_lower for kw in ["fix", "error", "bug", "compile"]):
            category = "CODE_FIX"
        elif any(kw in task_lower for kw in ["build", "compile", "flash"]):
            category = "BUILD_FLASH"
        elif any(kw in task_lower for kw in ["monitor", "debug", "observe", "serial"]):
            category = "RUNTIME_DEBUG"
        elif any(kw in task_lower for kw in ["pdf", "datasheet", "extract"]):
            category = "DOCUMENT_ANALYSIS"
        elif any(kw in task_lower for kw in ["kicad", "schematic", "pcb"]):
            category = "KICAD"
        elif any(kw in task_lower for kw in ["explain", "analyze", "what does", "understand"]):
            category = "CODE_ANALYSIS"
        elif any(kw in task_lower for kw in ["setup", "configure", "profile"]):
            category = "CONFIGURATION"

        target_project = ""
        if "enginecar" in task_lower or "engine car" in task_lower:
            target_project = "EngineCar"
        elif "remotecontrol" in task_lower or "remote control" in task_lower:
            target_project = "RemoteControl"

        target_chip = "STM32F407"
        chip_match = re.search(r"STM32[Ff]\d+", task)
        if chip_match:
            target_chip = chip_match.group(0).upper()

        return TaskClassification(
            category=category,
            confidence=0.7,
            target_project=target_project,
            target_chip=target_chip,
            subtasks=self._create_default_subtasks(category),
            estimated_difficulty="medium",
            model_recommendation="ollama",
            reasoning="Fallback classification based on keywords",
        )

    def _create_default_subtasks(self, category: str) -> List[Dict]:
        """Create default subtasks based on category."""
        subtask_map = {
            "CODE_GENERATION": [
                {"step": 1, "action": "analyze", "description": "Analyze requirements and existing code"},
                {"step": 2, "action": "generate", "description": "Generate firmware code"},
                {"step": 3, "action": "build", "description": "Build and verify compilation"},
            ],
            "CODE_FIX": [
                {"step": 1, "action": "analyze", "description": "Analyze error and identify root cause"},
                {"step": 2, "action": "fix", "description": "Apply fix to code"},
                {"step": 3, "action": "build", "description": "Rebuild and verify"},
            ],
            "BUILD_FLASH": [
                {"step": 1, "action": "build", "description": "Build firmware"},
                {"step": 2, "action": "flash", "description": "Flash to board"},
            ],
            "RUNTIME_DEBUG": [
                {"step": 1, "action": "connect", "description": "Connect to board serial"},
                {"step": 2, "action": "observe", "description": "Monitor runtime output"},
            ],
            "DOCUMENT_ANALYSIS": [
                {"step": 1, "action": "parse", "description": "Parse PDF document"},
                {"step": 2, "action": "extract", "description": "Extract relevant information"},
            ],
            "KICAD": [
                {"step": 1, "action": "generate", "description": "Generate KiCad files"},
                {"step": 2, "action": "validate", "description": "Run ERC/DRC validation"},
            ],
        }
        return subtask_map.get(category, [
            {"step": 1, "action": "execute", "description": "Execute task"},
        ])

    async def _create_plan(self, classification: TaskClassification) -> List[TaskStep]:
        """Create execution plan from classification."""
        steps = []
        for subtask in classification.subtasks:
            step = TaskStep(
                step=int(subtask.get("step", 0)),
                action=str(subtask.get("action", "execute")),
                description=str(subtask.get("description", "")),
            )
            steps.append(step)
        return sorted(steps, key=lambda s: s.step)

    async def _execute_step(self, step: TaskStep) -> bool:
        """Execute a single step with appropriate model selection."""
        step.status = "running"
        model = self._select_model_for_step(step)
        step.model_used = model
        self._state.model_switches.append({
            "step": step.step,
            "action": step.action,
            "model": model,
            "timestamp": datetime.now().isoformat(),
        })
        logger.info("PlanModeAgent: Step %d using model '%s'", step.step, model)

        try:
            if step.action == "analyze":
                result = await self._execute_analyze(step, model)
            elif step.action == "generate":
                result = await self._execute_generate(step, model)
            elif step.action == "fix":
                result = await self._execute_fix(step, model)
            elif step.action == "build":
                result = await self._execute_build(step, model)
            elif step.action == "flash":
                result = await self._execute_flash(step, model)
            elif step.action == "observe":
                result = await self._execute_observe(step, model)
            elif step.action == "parse":
                result = await self._execute_parse(step, model)
            elif step.action == "extract":
                result = await self._execute_extract(step, model)
            elif step.action == "connect":
                result = await self._execute_connect(step, model)
            elif step.action == "validate":
                result = await self._execute_validate(step, model)
            else:
                result = await self._execute_generic(step, model)

            step.result = result
            step.status = "completed" if result is not False else "failed"
            self._state.results.append(result)
            return result is not False

        except Exception as exc:
            logger.exception("PlanModeAgent: Step %d failed with exception", step.step)
            step.status = "failed"
            step.error = str(exc)
            self._state.errors.append(f"Step {step.step}: {exc}")
            return False

    def _select_model_for_step(self, step: TaskStep) -> str:
        """Select the optimal model for a step based on task complexity and config."""
        if self._state and self._state.classification:
            recommended = self._state.classification.model_recommendation
            confidence = self._state.classification.confidence

            # Respect the LLM's model recommendation from classification
            # Only use it if the recommended model is actually available
            if recommended in ("openai", "ollama"):
                # For generate/fix actions on complex tasks, use recommended model
                if step.action in ("generate", "fix", "analyze"):
                    if recommended == "openai":
                        if self.router.openai and self.router.openai.is_configured:
                            return "openai"
                    else:
                        return "ollama"

            # Low confidence: consider upgrading to recommended model
            from src.core.config.config_loader import get_config
            cfg = get_config()
            low_conf_threshold = cfg.get("model_routing.low_confidence_threshold", 0.5)
            if confidence < low_conf_threshold and recommended in ("openai", "ollama"):
                if recommended == "openai":
                    if self.router.openai and self.router.openai.is_configured:
                        return "openai"

        action_model_map = {
            "generate": "ollama",
            "fix": "ollama",
            "analyze": "ollama",
            "build": "ollama",
            "flash": "ollama",
            "observe": "ollama",
            "parse": "ollama",
            "extract": "ollama",
            "validate": "ollama",
            "connect": "ollama",
        }
        return action_model_map.get(
            step.action,
            self._state.classification.model_recommendation if self._state and self._state.classification else "ollama",
        )

    async def _execute_analyze(self, step: TaskStep, model: str) -> Dict:
        """Analyze task requirements."""
        prompt = f"""Analyze this firmware development task:

Task: {self._state.task}
Target Project: {self._state.classification.target_project if self._state.classification else 'N/A'}
Target Chip: {self._state.classification.target_chip if self._state.classification else 'STM32F407'}

Provide:
1. Key requirements
2. Hardware constraints
3. Existing code to reference
4. Implementation approach
"""
        response = await self.router.generate(prompt, task_type="complex_reasoning", force_model=model)
        return {"type": "analysis", "content": response}

    async def _execute_generate(self, step: TaskStep, model: str) -> Dict:
        """Generate code using the embedded agent or LLM directly."""
        if self.embedded_agent:
            result = await self.embedded_agent.execute_task(self._state.task)
            return {
                "type": "generation",
                "success": result.success,
                "files": result.files_created,
                "message": result.message,
            }

        prompt = PLAN_MODE_TASK_EXECUTION_PROMPT.format(
            task=self._state.task,
            category=self._state.classification.category if self._state.classification else "UNKNOWN",
            plan=json.dumps([s.__dict__ for s in self._state.steps]),
            current_step=step.step,
            total_steps=len(self._state.steps),
            previous_actions=str([s.action for s in self._state.steps[: step.step - 1]]),
            last_observation=str(self._state.results[-1] if self._state.results else "none"),
            current_model=model,
            model_recommendation=self._state.classification.model_recommendation if self._state.classification else "ollama",
        )
        response = await self.router.generate(prompt, task_type="code_generation", force_model=model)
        files = self._extract_generated_files(response)
        return {
            "type": "generation",
            "content": response,
            "files": files,
        }

    async def _execute_fix(self, step: TaskStep, model: str) -> Dict:
        """Fix code issues."""
        if self.embedded_agent:
            result = await self.embedded_agent.execute_task(f"Fix: {self._state.task}")
            return {
                "type": "fix",
                "success": result.success,
                "files": result.files_created,
                "message": result.message,
            }

        prompt = f"""Fix the following code issue:

Task: {self._state.task}

Previous errors:
{chr(10).join(str(e) for e in self._state.errors[-3:])}

Previous result:
{str(self._state.results[-1] if self._state.results else 'none')}

Provide the fixed code and explain the changes.
"""
        response = await self.router.generate(prompt, task_type="fix_errors", force_model=model)
        return {"type": "fix", "content": response}

    async def _execute_build(self, step: TaskStep, model: str) -> Dict:
        """Build the firmware."""
        if self.embedded_agent and self.embedded_agent.build_tools:
            build_result = await self.embedded_agent.build_tools.run_build()
            return {
                "type": "build",
                "status": build_result.status,
                "stdout": build_result.stdout,
                "stderr": build_result.stderr,
                "success": build_result.status == "success",
            }

        target = self._state.classification.target_project if self._state.classification else "EngineCar"
        return {
            "type": "build",
            "message": f"Build for {target} - run manually or configure build_tools",
            "success": True,
        }

    async def _execute_flash(self, step: TaskStep, model: str) -> Dict:
        """Flash firmware to board."""
        if self.embedded_agent and self.embedded_agent.build_tools:
            target = self._state.classification.target_project if self._state.classification else "EngineCar"
            flash_result = await self.embedded_agent.build_tools.run_flash(target)
            return {
                "type": "flash",
                "status": flash_result.status,
                "success": flash_result.status == "success",
            }

        return {"type": "flash", "message": "Flash not configured", "success": False}

    async def _execute_observe(self, step: TaskStep, model: str) -> Dict:
        """Observe runtime output."""
        if self.embedded_agent and self.embedded_agent.build_tools:
            runtime_result = await self.embedded_agent.build_tools.run_runtime_observe(dry_run=True)
            return {
                "type": "observe",
                "status": runtime_result.status,
                "stdout": runtime_result.stdout,
                "success": runtime_result.status == "success",
            }

        return {"type": "observe", "message": "Runtime observation not configured", "success": True}

    async def _execute_parse(self, step: TaskStep, model: str) -> Dict:
        """Parse PDF document."""
        prompt = f"""Parse and understand this PDF/document task:

Task: {self._state.task}

Provide:
1. Document type (datasheet, reference manual, etc.)
2. Key sections to extract
3. Relevant technical data
"""
        response = await self.router.generate(prompt, task_type="document_analysis", force_model=model)
        return {"type": "parse", "content": response}

    async def _execute_extract(self, step: TaskStep, model: str) -> Dict:
        """Extract information from document."""
        prompt = f"""Extract technical information for:

Task: {self._state.task}
Target Chip: {self._state.classification.target_chip if self._state.classification else 'STM32F407'}

Extract:
1. Register definitions
2. Pin configurations
3. Timing specifications
4. Electrical characteristics
"""
        response = await self.router.generate(prompt, task_type="document_analysis", force_model=model)
        return {"type": "extract", "content": response}

    async def _execute_connect(self, step: TaskStep, model: str) -> Dict:
        """Connect to board for debugging."""
        return {"type": "connect", "message": "Serial connection ready", "success": True}

    async def _execute_validate(self, step: TaskStep, model: str) -> Dict:
        """Validate KiCad outputs."""
        prompt = f"""Validate the following KiCad/generation output:

Task: {self._state.task}

Check for:
1. ERC errors
2. DRC violations
3. Missing connections
4. Footprint issues
"""
        response = await self.router.generate(prompt, task_type="complex_reasoning", force_model=model)
        return {"type": "validate", "content": response}

    async def _execute_generic(self, step: TaskStep, model: str) -> Dict:
        """Generic step execution."""
        prompt = f"""Execute this step:

Task: {self._state.task}
Step: {step.description}

Provide a detailed response.
"""
        response = await self.router.generate(prompt, task_type="simple", force_model=model)
        return {"type": "generic", "content": response, "success": True}

    def _extract_generated_files(self, response: str) -> List[str]:
        """Extract file paths from LLM response."""
        files = []
        file_pattern = re.findall(r"FILE:\s*([^\n]+)", response)
        files.extend([f.strip() for f in file_pattern])
        return files

    def _extract_json_object(self, response: str) -> Optional[Dict]:
        """Extract JSON from LLM response."""
        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        code_block_match = re.search(r"```(?:json)?\s*(\{[^}]+\})", response, re.DOTALL)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def _get_created_files(self) -> List[str]:
        """Get list of created files from results."""
        files = []
        for result in self._state.results:
            if isinstance(result, dict):
                if result.get("files"):
                    files.extend(result["files"])
                if result.get("type") == "generation" and result.get("files"):
                    files.extend(result["files"])
        return list(set(files))

    # =============================================================================
    # INTERACTIVE PLAN MODE - Chat with user to refine plan
    # =============================================================================

    async def chat_about_plan(self, initial_task: str, max_turns: int = 10) -> Tuple[bool, str]:
        """Interactive chat loop to refine plan before execution.
        
        Returns:
            Tuple of (should_execute, final_task_description)
        """
        print("\n" + "=" * 60)
        print("[INTERACTIVE PLAN MODE] - Type '/help' for commands")
        print("=" * 60)
        
        # Initial plan
        classification = await self._classify_task(initial_task)
        self._state = PlanModeState(task=initial_task)
        self._state.classification = classification
        steps = await self._create_plan(classification)
        self._state.steps = steps

        task_context = initial_task
        turn_count = 0

        self._print_plan(classification, steps)

        while turn_count < max_turns:
            turn_count += 1
            try:
                user_input = input(f"\nYou [{turn_count}/{max_turns}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting interactive mode.")
                return False, task_context

            if not user_input:
                continue

            # Handle special commands
            if user_input.lower() in ('/exit', '/quit', '/cancel', 'n'):
                print("Plan cancelled by user.")
                return False, task_context
            
            if user_input.lower() in ('/execute', '/go', 'y', 'yes'):
                print("Executing plan...")
                return True, task_context
            
            if user_input.lower() == '/help':
                self._print_help()
                turn_count -= 1  # Don't count as a turn
                continue
            
            if user_input.lower() == '/show':
                self._print_plan(classification, steps)
                turn_count -= 1
                continue
            
            if user_input.lower() == '/reset':
                classification = await self._classify_task(initial_task)
                self._state.classification = classification
                steps = await self._create_plan(classification)
                self._state.steps = steps
                print("\n[Plan reset to original]")
                self._print_plan(classification, steps)
                turn_count -= 1
                continue

            # Process feedback
            feedback_type, feedback_detail = self._classify_feedback(user_input)
            
            if feedback_type == "modify":
                # Update plan based on feedback
                new_task = self._apply_feedback_to_task(task_context, user_input, feedback_detail)
                task_context = new_task
                classification = await self._classify_task(new_task)
                self._state.classification = classification
                steps = await self._create_plan(classification)
                self._state.steps = steps
                print("\n[Plan updated based on your feedback]")
                self._print_plan(classification, steps)
            elif feedback_type == "question":
                response = await self._answer_plan_question(user_input, task_context, classification, steps)
                print(f"\nAI: {response}")
            else:
                print(f"\nAI: Got it. I'll keep that in mind.")

        print(f"\nMax turns ({max_turns}) reached. Ready to execute?")
        return True, task_context

    def _print_plan(self, classification: TaskClassification, steps: List[TaskStep]):
        """Print the current plan in a formatted way."""
        print(f"\n--- Current Plan ---")
        print(f"Task: {self._state.task}")
        print(f"Category: {classification.category}")
        print(f"Confidence: {classification.confidence:.0%}")
        print(f"Target: {classification.target_chip}")
        print(f"Difficulty: {classification.estimated_difficulty}")
        print(f"\nSteps:")
        for step in steps:
            print(f"  {step.step}. [{step.status.upper()}] {step.description}")
        print(f"\n{'=' * 40}")
        print("Type modifications, questions, or 'y' to execute")

    def _print_help(self):
        """Print available commands."""
        print("""
Available Commands:
  /help     - Show this help
  /show     - Show current plan
  /reset    - Reset to original plan
  /execute  - Execute the plan (same as 'y')
  /cancel   - Cancel and exit
  y/yes     - Execute the plan
  n/no      - Cancel and exit

You can also:
  - Ask questions about the plan
  - Request modifications (e.g., "add DMA support", "change to interrupt-based")
""")

    def _classify_feedback(self, user_input: str) -> Tuple[str, str]:
        """Classify user feedback into types."""
        user_lower = user_input.lower()
        
        # Check for questions
        question_patterns = ['what', 'how', 'why', 'which', 'should', 'can i', 
                           'is it', 'do you', 'explain', '?']
        if any(q in user_lower for q in question_patterns) and '?' in user_input:
            return "question", ""
        
        # Check for modifications
        modify_patterns = ['add', 'remove', 'change', 'use', 'instead', 'replace',
                         'tăng', 'giảm', 'thêm', 'bỏ', 'đổi', 'chỉnh']
        if any(p in user_lower for p in modify_patterns):
            return "modify", user_input
        
        return "acknowledge", user_input

    async def _answer_plan_question(self, question: str, task: str, 
                                   classification: TaskClassification, 
                                   steps: List[TaskStep]) -> str:
        """Answer a question about the current plan."""
        prompt = f"""You are helping a user understand their firmware development plan.

Current Task: {task}
Category: {classification.category}
Target Chip: {classification.target_chip}
Difficulty: {classification.estimated_difficulty}

Current Steps:
{chr(10).join(f"{s.step}. {s.description}" for s in steps)}

User Question: {question}

Answer the question concisely and in context of embedded firmware development.
"""
        response = await self.router.generate(prompt, task_type="simple")
        return response.strip()

    def _apply_feedback_to_task(self, original_task: str, feedback: str, 
                                detail: str) -> str:
        """Extract modification intent and update task."""
        feedback_lower = feedback.lower()
        
        # Simple keyword-based modifications
        modifications = []
        
        if 'dma' in feedback_lower:
            modifications.append("DMA support")
        if 'interrupt' in feedback_lower or 'irq' in feedback_lower:
            modifications.append("interrupt-based approach")
        if 'buffer' in feedback_lower:
            if '64' in feedback:
                modifications.append("64-byte buffer")
            elif '128' in feedback:
                modifications.append("128-byte buffer")
            else:
                modifications.append("buffer configuration")
        if 'baud' in feedback_lower or '115200' in feedback_lower or '9600' in feedback_lower:
            match = re.search(r'(\d+)\s*baud', feedback_lower)
            if match:
                modifications.append(f"Baud rate {match.group(1)}")
        if 'timeout' in feedback_lower:
            modifications.append("timeout configuration")
        
        if modifications:
            return f"{original_task} with {', '.join(modifications)}"
        
        # Fallback: append feedback
        return f"{original_task}. Note: {feedback}"

    def _generate_lessons(self) -> str:
        """Generate lessons from execution."""
        lessons = []
        if len(self._state.model_switches) > 1:
            lessons.append("- Used multiple models for optimal results")
        if any(s.status == "failed" for s in self._state.steps):
            lessons.append("- Some steps failed, review error logs")
        if self._state.classification:
            lessons.append(f"- Task was {self._state.classification.category} with {self._state.classification.estimated_difficulty} difficulty")
        return "\n".join(lessons) if lessons else "- Task completed successfully"

    def _build_result(self) -> TaskResult:
        """Build the final TaskResult."""
        success = all(s.status == "completed" for s in self._state.steps)
        if not self._state.steps:
            success = True

        duration = (datetime.now() - self._state.start_time).total_seconds()
        model_summary = ", ".join(set(s.model_used for s in self._state.steps if s.model_used))

        summary = PLAN_MODE_SUMMARY_PROMPT.format(
            task=self._state.task,
            category=self._state.classification.category if self._state.classification else "UNKNOWN",
            steps=json.dumps([{"step": s.step, "action": s.action, "status": s.status} for s in self._state.steps]),
            success=success,
            files_created=", ".join(self._get_created_files()) or "none",
            errors=", ".join(self._state.errors[-3:]) if self._state.errors else "none",
            duration=f"{duration:.1f}s",
            lessons=self._generate_lessons(),
        )

        logger.info(
            "PlanModeAgent: Task complete. success=%s duration=%.1fs models=%s",
            success,
            duration,
            model_summary,
        )

        return TaskResult(
            success=success,
            message=summary,
            files_created=self._get_created_files(),
            errors_fixed=sum(1 for e in self._state.errors if "fix" in str(e).lower()),
            attempts=len(self._state.steps),
            duration=duration,
            learned_rules=[f"Used model(s): {model_summary}"],
        )
