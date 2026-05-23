#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
╔══════════════════════════════════════════════════════════════════════╗
║           DEEPSEEK + CURSOR AUTO WORKFLOW                         ║
║                                                                      ║
║  SINGLE COMMAND: python scripts/auto_workflow.py phase_1b.md       ║
║                                                                      ║
║  Auto handles:                                                      ║
║    1. DeepSeek 10 weakness reviews (same chat)                     ║
║    2. Copy results to Cursor                                        ║
║    3. Wait for Cursor execution                                    ║
║    4. Top 5 critical validation                                     ║
║    5. Save all results                                             ║
╚══════════════════════════════════════════════════════════════════════╝

Usage:
    python scripts/auto_workflow.py phase_1b.md
    python scripts/auto_workflow.py phase_1b.md phase_2.md phase_3.md
    python scripts/auto_workflow.py --all "1b,2,3"   # Run phases 1b, 2, 3
"""

import io, sys, time, json, threading, queue
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum
import subprocess

# ============================================================================
# IMPORTS - Browser Automation
# ============================================================================
import httpx
from playwright.sync_api import sync_playwright
import pyperclip
import keyboard
import pygetwindow as gw


# ============================================================================
# CONFIG
# ============================================================================
CHROME_PORT = 9222
DEEPSEEK_URL = "https://chat.deepseek.com/"
DEFAULT_WAIT = 45


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class Severity(Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class Weakness:
    id: str
    title: str
    severity: Severity
    description: str
    fix_suggestion: str


@dataclass
class PhaseResult:
    name: str
    weaknesses: list[Weakness] = field(default_factory=list)
    deepseek_raw: str = ""
    cursor_output: str = ""
    status: str = "pending"


class WorkflowState(Enum):
    IDLE = "idle"
    DEEPSEEK = "deepseek_review"
    COPY_TO_CURSOR = "copy_to_cursor"
    CURSOR_EXEC = "cursor_exec"
    CURSOR_VALIDATE = "cursor_validate"
    COMPLETE = "complete"
    FAILED = "failed"


# ============================================================================
# DEEPSEEK BROWSER MANAGER
# ============================================================================

class DeepSeekManager:
    """Manages DeepSeek browser session."""

    def __init__(self, port: int = CHROME_PORT):
        self.port = port
        self.browser = None
        self.page = None
        self._playwright = None

    def connect(self) -> bool:
        """Connect to Chrome or launch new."""
        self._playwright = sync_playwright().start()

        try:
            r = httpx.get(f"http://localhost:{self.port}/json/version", timeout=3)
            ws_url = r.json()["webSocketDebuggerUrl"]
            print("    [Chrome] Connecting to existing...")
            self.browser = self._playwright.chromium.connect_over_cdp(ws_url)

            for ctx in self.browser.contexts:
                for p in ctx.pages:
                    if "deepseek" in p.url.lower():
                        self.page = p
                        print("    [Chrome] Found DeepSeek tab")
                        break

            if self.page:
                self.page.bring_to_front()
                return True

        except Exception as e:
            print(f"    [Chrome] Launching new: {e}")
            self.browser = self._playwright.chromium.launch(headless=False)

        if not self.page:
            self.page = self.browser.new_page()
        return False

    def navigate(self):
        """Go to DeepSeek."""
        print("    [DeepSeek] Loading chat.deepseek.com...")
        self.page.goto(DEEPSEEK_URL)
        time.sleep(6)

    def send(self, prompt: str, wait: int = DEFAULT_WAIT) -> str:
        """Send prompt, return response text."""
        print(f"    [DeepSeek] Sending ({len(prompt)} chars)...")

        try:
            self.page.locator("textarea").first.fill(prompt)
            time.sleep(0.5)
            self.page.keyboard.press("Enter")
        except Exception as e:
            print(f"    [DeepSeek] Send error: {e}")
            return ""

        print(f"    [DeepSeek] Waiting {wait}s...")
        time.sleep(wait)

        try:
            text = self.page.locator("body").inner_text()
            lines = text.split("\n")
            return "\n".join(lines[-80:])
        except Exception as e:
            print(f"    [DeepSeek] Read error: {e}")
            return ""

    def close(self):
        """Cleanup."""
        if self.browser:
            self.browser.close()
            self._playwright.stop()


# ============================================================================
# CURSOR CHAT MANAGER
# ============================================================================

class CursorManager:
    """Manages Cursor chat interactions."""

    def __init__(self):
        self.window = None

    def find(self) -> bool:
        """Find Cursor window."""
        wins = [w for w in gw.getAllWindows() if "cursor" in w.title.lower()]
        if not wins:
            print("    [Cursor] Window not found!")
            return False
        self.window = wins[0]
        print("    [Cursor] Found window")
        return True

    def activate(self):
        """Focus Cursor."""
        if self.window:
            self.window.activate()
            time.sleep(0.5)

    def new_chat(self):
        """Create new chat."""
        self.activate()
        time.sleep(0.3)
        keyboard.send("ctrl+l")
        time.sleep(0.5)
        keyboard.write("/new")
        time.sleep(0.3)
        keyboard.send("enter")
        time.sleep(1)

    def paste(self, content: str):
        """Paste content."""
        self.activate()
        time.sleep(0.3)
        pyperclip.copy(content)
        time.sleep(0.3)
        keyboard.send("ctrl+v")
        time.sleep(0.3)

    def send(self):
        """Press Enter."""
        keyboard.send("enter")
        time.sleep(0.5)


# ============================================================================
# WEAKNESS PROMPTS
# ============================================================================

WEAKNESS_PROMPTS = [
    ("Architecture & Layering", """
Review the architecture for this phase:

1. Module boundaries - Are they clear?
2. Dependency direction - Top-down only?
3. Circular dependencies - Any?
4. Cross-layer violations - Where?

Provide specific issues with line numbers if possible.
"""),

    ("Error Handling", """
Review error handling:

1. Exception types - Consistent?
2. Error propagation - Clear paths?
3. Fallback strategies - Graceful degradation?
4. Error recovery - Can system recover?

List specific error handling gaps.
"""),

    ("Concurrency & Async Safety", """
Review concurrency:

1. Race conditions - Any identified?
2. Deadlocks - Potential?
3. Thread safety - Protected correctly?
4. Async operations - Safe composition?

Identify specific concurrency risks.
"""),

    ("State Management", """
Review state management:

1. State consistency - Mutations safe?
2. State persistence - Where saved?
3. State recovery - Can recover?
4. State isolation - Clean between requests?

Note state-related issues.
"""),

    ("Resource Management", """
Review resources:

1. Memory leaks - Any potential?
2. Connection pools - Proper size?
3. Cleanup on failure - Guaranteed?
4. Resource limits - Enforced?

Identify resource management gaps.
"""),

    ("Security & Permissions", """
Review security:

1. Authentication - Proper?
2. Authorization - Role-based?
3. Input validation - Sanitized?
4. Data protection - Encrypted?

List security vulnerabilities.
"""),

    ("Performance & Scalability", """
Review performance:

1. Bottlenecks - Where?
2. Caching - Opportunities?
3. Batch operations - Can batch?
4. Scaling - Horizontal/vertical?

Suggest optimizations.
"""),

    ("Observability", """
Review observability:

1. Logging - Structured?
2. Metrics - Exposed?
3. Tracing - Request IDs?
4. Debugging - Can trace issues?

Identify observability gaps.
"""),

    ("Testing Coverage", """
Review testing:

1. Edge cases - Covered?
2. Error paths - Tested?
3. Integration tests - Present?
4. Test isolation - Clean mocks?

Suggest missing tests.
"""),

    ("Maintainability", """
Review maintainability:

1. Code complexity - Cyclomatic?
2. Duplication - DRY violations?
3. Technical debt - What and where?
4. Documentation - Updated?

List refactoring opportunities.
"""),
]


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

class AutoWorkflow:
    """
    Single-command orchestrator for DeepSeek + Cursor workflow.

    Usage:
        workflow = AutoWorkflow()
        workflow.run("phase_1b.md")
    """

    WELCOME = """
╔══════════════════════════════════════════════════════════════════════╗
║               DEEPSEEK + CURSOR AUTO WORKFLOW                        ║
║                                                                      ║
║  1. DeepSeek reviews 10 weaknesses (same chat)                       ║
║  2. Copy results to NEW Cursor chat                                  ║
║  3. User runs Cursor to fix issues                                   ║
║  4. Cursor validates TOP 5 critical items                             ║
║  5. Save all results                                                 ║
╚══════════════════════════════════════════════════════════════════════╝
"""

    def __init__(self, wait: int = DEFAULT_WAIT):
        self.wait = wait
        self.deepseek = DeepSeekManager()
        self.cursor = CursorManager()
        self.result = None
        self.log_dir = Path("reviews")
        self.log_dir.mkdir(exist_ok=True)

    def run(self, phase_file: str):
        """Execute full workflow for one phase."""
        print(self.WELCOME)
        print(f"\n▶ Starting workflow for: {phase_file}\n")

        self.result = PhaseResult(name=phase_file.replace(".md", ""))

        try:
            # Step 1: DeepSeek reviews
            self._step1_deepseek_review()

            # Step 2: Copy to Cursor
            self._step2_copy_to_cursor()

            # Step 3: User runs Cursor
            self._step3_cursor_execute()

            # Step 4: Cursor validates
            self._step4_cursor_validate()

            # Step 5: Save
            self._step5_save_results()

            print("\n✅ WORKFLOW COMPLETE!")

        except KeyboardInterrupt:
            print("\n⏹ Workflow stopped by user")
            self._save_intermediate()

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            self.result.status = "failed"
            self._save_intermediate()
            raise

        finally:
            self.deepseek.close()

    def _step1_deepseek_review(self):
        """Send 10 weakness prompts to DeepSeek."""
        print("\n" + "="*60)
        print("STEP 1: DeepSeek reviews 10 weaknesses")
        print("="*60)

        # Load phase content
        phase_path = Path("prompts") / self.result.name + ".md"
        if not phase_path.exists():
            phase_path = Path(self.result.name)

        phase_content = ""
        if phase_path.exists():
            phase_content = phase_path.read_text(encoding="utf-8")
        else:
            # Try to find the file
            for candidate in [self.result.name + ".md", self.result.name.replace("phase_", "phase_") + ".md"]:
                p = Path("prompts") / candidate
                if p.exists():
                    phase_content = p.read_text(encoding="utf-8")
                    break

        if not phase_content:
            print("    [WARN] Phase file not found in prompts/")
            phase_content = f"Phase: {self.result.name}\n(No content loaded)"

        # Connect to DeepSeek
        has_tab = self.deepseek.connect()
        if not has_tab:
            self.deepseek.navigate()

        # Send intro
        intro = f"""You are reviewing: {self.result.name}

Phase content:
```
{phase_content[:2500]}
```

I will send 10 weakness reviews. Be brief and specific.
Respond with structured analysis for each.

Acknowledge with "READY" if you understand."""

        self.deepseek.send(intro, wait=10)

        # Send 10 weakness prompts
        all_reviews = []
        for i, (title, prompt) in enumerate(WEAKNESS_PROMPTS, 1):
            print(f"\n  [{i}/10] {title}...")
            response = self.deepseek.send(prompt, wait=self.wait)
            all_reviews.append(f"\n{'='*50}\nWEAKNESS {i}: {title}\n{'='*50}\n{response}")
            self._save_intermediate()

        self.result.deepseek_raw = "\n".join(all_reviews)
        print("\n  ✅ DeepSeek review complete!")

    def _step2_copy_to_cursor(self):
        """Copy results to Cursor."""
        print("\n" + "="*60)
        print("STEP 2: Copy to Cursor chat")
        print("="*60)

        if not self.cursor.find():
            raise RuntimeError("Cannot find Cursor window!")

        self.cursor.new_chat()

        # Build Cursor prompt
        cursor_prompt = self._build_cursor_prompt()
        self.cursor.paste(cursor_prompt)
        self.cursor.send()

        print("  ✅ Content pasted to Cursor!")

    def _step3_cursor_execute(self):
        """Wait for Cursor execution."""
        print("\n" + "="*60)
        print("STEP 3: Cursor executes fixes")
        print("="*60)
        print("""
╔═══════════════════════════════════════════════════════════╗
║  ▶ CURSOR IS ACTIVE                                        ║
║                                                            ║
║  1. Cursor will receive the weakness fixes                 ║
║  2. Run Cursor to implement the fixes                      ║
║  3. When done, come back here and press Enter             ║
╚═══════════════════════════════════════════════════════════╝
        """)
        input("  Press ENTER when Cursor has finished executing: ")

    def _step4_cursor_validate(self):
        """Cursor validates top 5."""
        print("\n" + "="*60)
        print("STEP 4: Cursor validates TOP 5 critical items")
        print("="*60)

        self.cursor.new_chat()

        top5_prompt = f"""## VALIDATION: Phase {self.result.name}

Review the fixes you just made. Focus on TOP 5 CRITICAL items:

1. **Architecture** - Module boundaries respected?
2. **Error Handling** - Consistent error handling?
3. **Concurrency** - Async operations safe?
4. **State Management** - State consistent?
5. **Resource Management** - Resources cleaned up?

For each:
- Verify fix was implemented
- Identify remaining issues
- Suggest final improvements

This is a validation pass. Be specific."""

        self.cursor.paste(top5_prompt)
        self.cursor.send()

        print("""
╔═══════════════════════════════════════════════════════════╗
║  ▶ CURSOR IS VALIDATING                                   ║
║                                                            ║
║  1. Review top 5 critical fixes                           ║
║  2. Validate implementation                               ║
║  3. When done, come back here and press Enter            ║
╚═══════════════════════════════════════════════════════════╝
        """)
        input("  Press ENTER when validation is complete: ")

    def _step5_save_results(self):
        """Save all results."""
        print("\n" + "="*60)
        print("STEP 5: Save results")
        print("="*60)

        output = f"""# DeepSeek + Cursor Workflow Results
## Phase: {self.result.name}
## Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

---

## DeepSeek Review (10 Weaknesses)

{self.result.deepseek_raw}

---

## Workflow Summary

| Step | Status |
|------|--------|
| 1. DeepSeek review | ✅ |
| 2. Copy to Cursor | ✅ |
| 3. Cursor execution | ✅ |
| 4. Top 5 validation | ✅ |
| 5. Results saved | ✅ |

---

## Next Steps

1. Review the fixes in the codebase
2. Run tests to verify
3. Commit with: `git commit -m "[Phase {self.result.name}] Fix DeepSeek review weaknesses"`
4. Update build_log.md and ERA_ROADMAP.md
5. Proceed to next phase
"""

        output_file = self.log_dir / f"{self.result.name}_workflow.md"
        output_file.write_text(output, encoding="utf-8")
        print(f"  ✅ Saved: {output_file}")

        self.result.status = "complete"

    def _build_cursor_prompt(self) -> str:
        """Build Cursor execution prompt."""
        return f"""## MISSION: Fix Phase {self.result.name} Weaknesses

DeepSeek reviewed this phase and found 10 weaknesses. Fix them now.

### Phase: {self.result.name}

### DeepSeek's 10 Weakness Reviews:

{self.result.deepseek_raw}

### YOUR TASKS:

1. Read `prompts/{self.result.name}.md`
2. Read existing implementation files
3. Fix each weakness
4. Write tests for critical fixes
5. Run tests: `python -m pytest tests/`
6. Commit: `git commit -m "[Phase {self.result.name}] Fix DeepSeek review weaknesses"`

### PRIORITY:
1. Critical → High → Medium → Low

Start by reading the phase file.
"""

    def _save_intermediate(self):
        """Save intermediate results."""
        if not self.result:
            return

        intermediate = self.log_dir / f"{self.result.name}_intermediate.md"
        content = f"""# Intermediate - {self.result.name}
# Saved: {time.strftime('%Y-%m-%d %H:%M:%S')}

{self.result.deepseek_raw}
"""
        intermediate.write_text(content, encoding="utf-8")


# ============================================================================
# BATCH RUNNER
# ============================================================================

class BatchRunner:
    """Run multiple phases sequentially."""

    def __init__(self):
        self.phases: list[str] = []
        self.log_dir = Path("reviews")
        self.log_dir.mkdir(exist_ok=True)

    def add(self, phase: str):
        self.phases.append(phase)

    def add_from_config(self, phases_str: str):
        """Add phases from comma-separated string like '1b,2,3'."""
        for p in phases_str.split(","):
            p = p.strip()
            if p:
                name = f"phase_{p}" if not p.startswith("phase_") else p
                self.add(name + ".md")

    def run(self, wait: int = DEFAULT_WAIT):
        """Run all phases."""
        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║                    BATCH PHASE RUNNER                                ║
║                                                                      ║
║  Phases: {', '.join(self.phases)}                              ║
╚══════════════════════════════════════════════════════════════════════╝
        """)

        results = []
        for i, phase in enumerate(self.phases, 1):
            print(f"\n{'#'*60}")
            print(f"# PHASE {i}/{len(self.phases)}: {phase}")
            print(f"{'#'*60}")

            try:
                workflow = AutoWorkflow(wait=wait)
                workflow.run(phase)
                results.append((phase, "Done"))
            except Exception as e:
                print(f"\nFailed: {e}")
                results.append((phase, f"Error: {e}"))

            if i < len(self.phases):
                print(f"\n{'='*60}")
                resp = input(f"\nContinue to phase {i+1}/{len(self.phases)}? [Y/n]: ").strip().lower()
                if resp == 'n':
                    print("\nStopped by user")
                    break

        self._save_summary(results)

    def run_with_wait(self, wait: int):
        """Run with custom wait time."""
        self.run(wait=wait)

    def _save_summary(self, results: list):
        """Save batch summary."""
        print(f"\n{'='*60}")
        print("BATCH SUMMARY")
        print(f"{'='*60}")
        for phase, status in results:
            print(f"  [{status}] {phase}")

        log = self.log_dir / "batch_log.md"
        lines = [f"# Batch Run - {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
        for phase, status in results:
            lines.append(f"- [{status}] {phase}")
        log.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nLog: {log}")


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="DeepSeek + Cursor Auto Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/auto_workflow.py phase_1b.md
  python scripts/auto_workflow.py phase_1b.md phase_2.md phase_3.md
  python scripts/auto_workflow.py --all "1b,2,3"
  python scripts/auto_workflow.py phase_1b.md --wait 60
        """
    )
    parser.add_argument("phases", nargs="*", help="Phase files to process")
    parser.add_argument("--all", "-a", help="Run all phases (comma-separated: 1b,2,3)")
    parser.add_argument("--wait", "-w", type=int, default=DEFAULT_WAIT,
                        help=f"Wait time per prompt (default: {DEFAULT_WAIT}s)")
    parser.add_argument("--port", "-p", type=int, default=CHROME_PORT,
                        help=f"Chrome port (default: {CHROME_PORT})")

    args = parser.parse_args()

    # Get phases
    phases = list(args.phases) if args.phases else []

    if args.all:
        for p in args.all.split(","):
            p = p.strip()
            if p:
                name = f"phase_{p}.md" if not p.startswith("phase_") else p
                if not name.endswith(".md"):
                    name += ".md"
                phases.append(name)

    if not phases:
        print("❌ No phases specified!")
        print("Usage: python scripts/auto_workflow.py phase_1b.md")
        return

    # Run batch with specified wait time
    batch = BatchRunner()
    for p in phases:
        batch.add(p)

    # Run with custom wait time
    batch.run_with_wait(args.wait)


if __name__ == "__main__":
    main()
