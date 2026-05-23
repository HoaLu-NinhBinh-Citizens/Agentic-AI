#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
DeepSeek + Cursor Orchestrator - COMPLEX WORKFLOW

WORKFLOW:
1. Send 10 prompts to SAME DeepSeek chat (sequential, no new chat)
2. DeepSeek reviews 10 weaknesses of that phase
3. After DeepSeek done → copy ALL results to NEW Cursor chat
4. Cursor executes tasks (fix weaknesses)
5. Wait Cursor done → trigger Cursor review top 5 critical weaknesses
6. Continue to next phase

Usage:
    python deepseek_cursor_orchestrator.py phase_1b.md
"""

import io, sys, time, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import threading
import queue

import httpx
from playwright.sync_api import sync_playwright
import pyperclip
import keyboard
import pygetwindow as gw


@dataclass
class PhaseWeakness:
    """A single weakness from DeepSeek review."""
    id: str
    title: str
    severity: str  # Critical, High, Medium, Low
    description: str
    consequence: str
    mitigation: str


@dataclass
class PhaseReview:
    """Complete review of a phase."""
    phase_name: str
    weaknesses: list[PhaseWeakness] = field(default_factory=list)
    deepseek_output: str = ""


class DeepSeekBrowser:
    """Manages DeepSeek browser session."""

    def __init__(self, port: int = 9222):
        self.port = port
        self.browser = None
        self.page = None

    def connect(self) -> bool:
        """Connect to existing Chrome or launch new."""
        pw = sync_playwright().start()
        try:
            r = httpx.get(f"http://localhost:{self.port}/json/version", timeout=3)
            ws = r.json()["webSocketDebuggerUrl"]
            print("  [DeepSeek] Connecting to Chrome...")
            self.browser = pw.chromium.connect_over_cdp(ws)
            pw.stop()

            for ctx in self.browser.contexts:
                for p in ctx.pages:
                    if "deepseek" in p.url.lower():
                        self.page = p
                        print("  [DeepSeek] Found existing tab")
                        break
            if self.page:
                self.page.bring_to_front()
                return True
        except Exception as e:
            print(f"  [DeepSeek] Launching new Chrome: {e}")
            self.browser = pw.chromium.launch(headless=False)
            pw.stop()

        if not self.page:
            self.page = self.browser.new_page()
        return False

    def navigate(self, url: str = "https://chat.deepseek.com/"):
        """Navigate to DeepSeek."""
        print(f"  [DeepSeek] Navigating to {url}")
        self.page.goto(url)
        time.sleep(6)

    def send_prompt(self, prompt: str, wait: int = 40) -> str:
        """Send prompt and wait for response."""
        print(f"  [DeepSeek] Sending prompt ({len(prompt)} chars)...")
        try:
            self.page.locator("textarea").first.fill(prompt)
            time.sleep(0.5)
            self.page.keyboard.press("Enter")
        except Exception as e:
            print(f"  [DeepSeek] Send error: {e}")
            return ""

        print(f"  [DeepSeek] Waiting {wait}s for response...")
        time.sleep(wait)

        try:
            body = self.page.locator("body").inner_text()
            lines = body.split("\n")
            return "\n".join(lines[-80:])
        except Exception as e:
            print(f"  [DeepSeek] Read error: {e}")
            return ""

    def close(self):
        """Close browser."""
        if self.browser:
            self.browser.close()


class CursorChat:
    """Manages Cursor chat interaction."""

    def __init__(self):
        self.window = None

    def find_window(self) -> bool:
        """Find Cursor window."""
        wins = [w for w in gw.getAllWindows() if "cursor" in w.title.lower()]
        if not wins:
            print("  [Cursor] Window not found!")
            return False
        self.window = wins[0]
        print("  [Cursor] Found window")
        return True

    def activate(self):
        """Activate Cursor window."""
        if self.window:
            self.window.activate()
            time.sleep(0.5)

    def new_chat(self):
        """Create new chat (Ctrl+L then type /new)."""
        self.activate()
        time.sleep(0.3)
        keyboard.send("ctrl+l")
        time.sleep(0.5)
        keyboard.write("/new")
        time.sleep(0.3)
        keyboard.send("enter")
        time.sleep(1)

    def paste_content(self, content: str):
        """Paste content into Cursor chat."""
        self.activate()
        time.sleep(0.3)
        pyperclip.copy(content)
        time.sleep(0.3)
        keyboard.send("ctrl+v")
        time.sleep(0.3)

    def send(self):
        """Send message (Enter)."""
        keyboard.send("enter")
        time.sleep(0.5)


class Orchestrator:
    """
    Orchestrates DeepSeek review + Cursor execution workflow.

    Flow:
    1. DeepSeek reviews weaknesses sequentially in SAME chat
    2. Copy all results to Cursor NEW chat
    3. Cursor fixes weaknesses
    4. Cursor reviews top 5 critical items
    5. Move to next phase
    """

    WEAKNESS_PROMPTS = [
        """Review Phase {phase} - WEAKNESS 1: Architecture Layering
Focus on: Module boundaries, dependency direction, circular dependencies.
Analyze: Is the layering clear? Are there cross-layer violations?

Respond with structured review.""",

        """Review Phase {phase} - WEAKNESS 2: Error Handling
Focus on: Exception types, error propagation, fallback strategies.
Analyze: Are errors handled consistently? Is there graceful degradation?

Respond with structured review.""",

        """Review Phase {phase} - WEAKNESS 3: Concurrency & Async
Focus on: Race conditions, deadlocks, thread safety.
Analyze: Are async operations safe? Is there proper synchronization?

Respond with structured review.""",

        """Review Phase {phase} - WEAKNESS 4: State Management
Focus on: State consistency, mutations, persistence.
Analyze: Is state managed correctly? Are there race conditions on state?

Respond with structured review.""",

        """Review Phase {phase} - WEAKNESS 5: Resource Management
Focus on: Memory leaks, resource cleanup, connection pools.
Analyze: Are resources properly released? Is there cleanup on failure?

Respond with structured review.""",

        """Review Phase {phase} - WEAKNESS 6: Security & Permissions
Focus on: Authentication, authorization, input validation.
Analyze: Are there security vulnerabilities? Is data properly protected?

Respond with structured review.""",

        """Review Phase {phase} - WEAKNESS 7: Performance & Scalability
Focus on: Bottlenecks, caching, batch operations.
Analyze: Are there performance issues? Can it scale with load?

Respond with structured review.""",

        """Review Phase {phase} - WEAKNESS 8: Observability
Focus on: Logging, metrics, tracing, debugging.
Analyze: Is the system observable? Can we debug issues?

Respond with structured review.""",

        """Review Phase {phase} - WEAKNESS 9: Testing Coverage
Focus on: Edge cases, mocking, integration tests.
Analyze: Are critical paths tested? Are there untested scenarios?

Respond with structured review.""",

        """Review Phase {phase} - WEAKNESS 10: Maintainability
Focus on: Code complexity, duplication, technical debt.
Analyze: Is the code maintainable? What needs refactoring?

Respond with structured review.""",
    ]

    def __init__(self, phase_file: str, port: int = 9222, wait: int = 45):
        self.phase_file = phase_file
        self.phase_name = Path(phase_file).stem
        self.port = port
        self.wait = wait

        self.deepseek = DeepSeekBrowser(port)
        self.cursor = CursorChat()

        self.reviews: list[str] = []
        self.phase_review = PhaseReview(phase_name=self.phase_name)

    def load_phase_prompt(self) -> str:
        """Load phase prompt content."""
        fp = Path("prompts") / self.phase_file
        if not fp.exists():
            fp = Path(self.phase_file)
        return fp.read_text(encoding="utf-8")

    def step1_deepseek_review_all(self):
        """
        STEP 1: Send 10 prompts to SAME DeepSeek chat.
        Sequential, no new chat.
        """
        print("\n" + "="*60)
        print("STEP 1: DeepSeek reviews 10 weaknesses")
        print("="*60)

        # Load phase content
        phase_content = self.load_phase_prompt()

        # Connect to DeepSeek
        has_existing = self.deepseek.connect()
        if not has_existing:
            self.deepseek.navigate()

        # Send intro with phase content
        intro = f"""You are reviewing Phase: {self.phase_name}

Analyze this phase specification:
```
{phase_content[:3000]}...
```

I will send 10 specific weakness reviews. Respond briefly to each.
Start with "READY" if you understand."""

        print("  Sending introduction...")
        self.deepseek.send_prompt(intro, wait=10)

        # Send 10 weakness prompts sequentially
        for i, template in enumerate(self.WEAKNESS_PROMPTS, 1):
            prompt = template.format(phase=self.phase_name)
            print(f"\n  [{i}/10] Sending weakness {i}...")

            response = self.deepseek.send_prompt(prompt, wait=self.wait)
            self.reviews.append(response)
            self.phase_review.deepseek_output += f"\n\n{'='*40}\nWEAKNESS {i}\n{'='*40}\n{response}"

            # Save intermediate results
            self._save_intermediate()

        print("\n  DeepSeek review complete!")

    def step2_copy_to_cursor(self):
        """
        STEP 2: Copy all DeepSeek results to NEW Cursor chat.
        """
        print("\n" + "="*60)
        print("STEP 2: Copy results to Cursor")
        print("="*60)

        # Find Cursor
        if not self.cursor.find_window():
            print("  [ERROR] Cannot find Cursor!")
            return False

        # Create new chat
        print("  Creating new Cursor chat...")
        self.cursor.new_chat()

        # Build Cursor prompt
        cursor_prompt = self._build_cursor_prompt()

        # Paste to Cursor
        print("  Pasting content to Cursor...")
        self.cursor.paste_content(cursor_prompt)
        self.cursor.send()

        print("  Content pasted to Cursor!")
        return True

    def step3_cursor_executes(self):
        """
        STEP 3: User executes tasks in Cursor.
        This is interactive - user will run Cursor.
        """
        print("\n" + "="*60)
        print("STEP 3: Cursor executes fixes")
        print("="*60)
        print("""
  ╔════════════════════════════════════════════════════════════╗
  ║  CURSOR IS NOW ACTIVE - EXECUTE THE TASKS                  ║
  ║                                                            ║
  ║  1. Cursor will receive the weakness fixes                  ║
  ║  2. Execute the fixes in Cursor                            ║
  ║  3. When done, come back here and press Enter              ║
  ║  4. I will trigger Cursor to review top 5 critical items   ║
  ╚════════════════════════════════════════════════════════════╝
        """)

        input("  Press Enter when Cursor has finished executing fixes...")

    def step4_cursor_review_top5(self):
        """
        STEP 4: Trigger Cursor to review top 5 critical weaknesses.
        """
        print("\n" + "="*60)
        print("STEP 4: Cursor reviews top 5 critical items")
        print("="*60)

        # Create new chat for review
        if not self.cursor.find_window():
            print("  [ERROR] Cannot find Cursor!")
            return

        self.cursor.new_chat()

        # Build top 5 review prompt
        top5_prompt = f"""Review the fixes you just made for Phase {self.phase_name}.

Focus on TOP 5 CRITICAL weaknesses that were fixed:

1. **Architecture Layering** - Were module boundaries respected?
2. **Error Handling** - Is error handling consistent?
3. **Concurrency** - Are async operations safe?
4. **State Management** - Is state consistent?
5. **Resource Management** - Are resources properly cleaned up?

For each:
- Verify the fix was implemented correctly
- Identify any remaining issues
- Suggest final improvements

Be specific and thorough. This is a validation pass."""

        print("  Pasting top 5 review prompt...")
        self.cursor.paste_content(top5_prompt)
        self.cursor.send()

        print("""
  ╔════════════════════════════════════════════════════════════╗
  ║  CURSOR IS REVIEWING TOP 5 CRITICAL ITEMS                 ║
  ║                                                            ║
  ║  1. Review the fixes                                       ║
  ║  2. Validate the implementation                            ║
  ║  3. When done, come back here and press Enter              ║
  ╚════════════════════════════════════════════════════════════╝
        """)

        input("  Press Enter when review is complete...")

    def step5_save_results(self):
        """
        STEP 5: Save all results to file.
        """
        print("\n" + "="*60)
        print("STEP 5: Save results")
        print("="*60)

        output_file = Path("reviews") / f"{self.phase_name}_review.md"
        output_file.parent.mkdir(exist_ok=True)

        content = f"""# DeepSeek + Cursor Workflow Results
# Phase: {self.phase_name}
# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

## DeepSeek Review (10 Weaknesses)

{self.phase_review.deepseek_output}

## Workflow Summary

- Step 1: DeepSeek reviewed 10 weaknesses ✓
- Step 2: Results copied to Cursor ✓
- Step 3: Cursor executed fixes
- Step 4: Cursor validated top 5 critical items
- Step 5: Results saved

## Next Phase

Proceed to next phase after validating these fixes.
"""

        output_file.write_text(content, encoding="utf-8")
        print(f"  Results saved to: {output_file}")

    def _build_cursor_prompt(self) -> str:
        """Build the prompt for Cursor to execute fixes."""
        return f"""## MISSION: Fix Phase {self.phase_name} Weaknesses

Based on DeepSeek's review, implement the following fixes:

### Phase Content Reference:
```
{self.load_phase_prompt()[:2000]}...
```

### DeepSeek's 10 Weakness Reviews:

{self.phase_review.deepseek_output}

### YOUR TASKS:

1. Read the phase specification at `prompts/{self.phase_file}`
2. Read the existing implementation files
3. Fix each weakness identified by DeepSeek
4. Write tests for critical fixes
5. Run tests to verify
6. Commit with message: `[Phase {self.phase_name}] Fix DeepSeek review weaknesses`

### PRIORITY ORDER:
1. Critical issues first
2. High priority second
3. Medium/Low third

### OUTPUT FORMAT:
After each fix, briefly summarize what was changed.

Start by reading the phase file and understanding the requirements.
"""

    def _save_intermediate(self):
        """Save intermediate results."""
        intermediate = Path("reviews") / f"{self.phase_name}_intermediate.md"
        intermediate.parent.mkdir(exist_ok=True)

        content = f"""# Intermediate Results - {self.phase_name}
# Saved: {time.strftime('%Y-%m-%d %H:%M:%S')}

{self.phase_review.deepseek_output}
"""
        intermediate.write_text(content, encoding="utf-8")

    def run(self):
        """Execute the complete workflow."""
        print("""
╔══════════════════════════════════════════════════════════════╗
║          DEEPSEEK + CURSOR ORCHESTRATOR                      ║
║                                                              ║
║  Phase: {self.phase_name:<50}║
║                                                              ║
║  Workflow:                                                   ║
║    1. DeepSeek reviews 10 weaknesses (same chat)            ║
║    2. Copy results to NEW Cursor chat                        ║
║    3. Cursor executes fixes                                 ║
║    4. Cursor validates top 5 critical items                 ║
║    5. Save results                                          ║
╚══════════════════════════════════════════════════════════════╝
        """)

        try:
            # Step 1: DeepSeek reviews
            self.step1_deepseek_review_all()

            # Step 2: Copy to Cursor
            if self.step2_copy_to_cursor():
                # Step 3: User runs Cursor
                self.step3_cursor_executes()

                # Step 4: Cursor reviews top 5
                self.step4_cursor_review_top5()

            # Step 5: Save results
            self.step5_save_results()

            print("\n" + "="*60)
            print("WORKFLOW COMPLETE!")
            print("="*60)

        finally:
            self.deepseek.close()
            print("\nDeepSeek browser closed.")


def main():
    import argparse

    ap = argparse.ArgumentParser(description="DeepSeek + Cursor Orchestrator")
    ap.add_argument("phase", help="Phase file (e.g., phase_1b.md)")
    ap.add_argument("--port", "-p", type=int, default=9222, help="Chrome remote port")
    ap.add_argument("--wait", "-w", type=int, default=45, help="Wait time per prompt (seconds)")
    ap.add_argument("--skip-deepseek", action="store_true", help="Skip DeepSeek step")
    ap.add_argument("--skip-cursor", action="store_true", help="Skip Cursor steps")
    args = ap.parse_args()

    orchestrator = Orchestrator(
        phase_file=args.phase,
        port=args.port,
        wait=args.wait
    )

    orchestrator.run()


if __name__ == "__main__":
    main()
