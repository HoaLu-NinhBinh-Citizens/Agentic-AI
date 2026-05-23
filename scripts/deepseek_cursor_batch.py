#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Run DeepSeek + Cursor workflow for MULTIPLE phases sequentially.

Usage:
    python deepseek_cursor_batch.py phase_1b.md phase_2.md phase_3.md

Or use a config file:
    python deepseek_cursor_batch.py --config phases.txt
"""

import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class PhaseTask:
    """A phase task to execute."""
    file: str
    status: str = "pending"  # pending, running, done, failed
    notes: str = ""


class BatchOrchestrator:
    """
    Orchestrates multiple phases through DeepSeek + Cursor workflow.

    Usage:
        orchestrator = BatchOrchestrator()
        orchestrator.add_phase("phase_1b.md")
        orchestrator.add_phase("phase_2.md")
        orchestrator.run()
    """

    def __init__(self):
        self.phases: list[PhaseTask] = []
        self.current_index: int = 0
        self.log_file = Path("reviews") / "batch_progress.md"

    def add_phase(self, phase_file: str):
        """Add a phase to the batch."""
        self.phases.append(PhaseTask(file=phase_file))

    def load_from_file(self, filepath: str):
        """Load phases from a text file (one phase per line)."""
        fp = Path(filepath)
        if not fp.exists():
            print(f"[ERROR] File not found: {filepath}")
            return

        for line in fp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                self.add_phase(line)

    def save_progress(self):
        """Save current progress."""
        lines = [
            "# Batch Progress",
            f"# Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Phases",
            "",
        ]

        for i, phase in enumerate(self.phases, 1):
            marker = "▶" if phase.status == "running" else "✓" if phase.status == "done" else "○"
            lines.append(f"{marker} {i}. `{phase.file}` - {phase.status}")

            if phase.notes:
                lines.append(f"   - {phase.notes}")

        self.log_file.parent.mkdir(exist_ok=True)
        self.log_file.write_text("\n".join(lines), encoding="utf-8")

    def run(self):
        """Run the batch workflow."""
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║          BATCH PHASE PROCESSOR                              ║
║                                                              ║
║  Total phases: {len(self.phases):<45}║
║                                                              ║
║  This will run each phase through:                           ║
║    1. DeepSeek review (10 weaknesses)                        ║
║    2. Cursor execution                                       ║
║    3. Cursor top-5 validation                               ║
║    4. Move to next phase                                     ║
╚══════════════════════════════════════════════════════════════╝
        """)

        for i, phase in enumerate(self.phases):
            self.current_index = i
            phase.status = "running"
            self.save_progress()

            print(f"\n{'='*60}")
            print(f"PHASE {i+1}/{len(self.phases)}: {phase.file}")
            print(f"{'='*60}")

            try:
                # Run the orchestrator for this phase
                self._run_phase(phase)

                phase.status = "done"
                phase.notes = "Completed successfully"

            except KeyboardInterrupt:
                print("\n\n[ABORTED] User interrupted")
                phase.status = "failed"
                phase.notes = "Interrupted by user"
                break

            except Exception as e:
                print(f"\n\n[ERROR] Phase failed: {e}")
                phase.status = "failed"
                phase.notes = f"Error: {str(e)[:100]}"

            finally:
                self.save_progress()

            # Ask before next phase
            if i < len(self.phases) - 1:
                print(f"\n{'='*60}")
                response = input(f"\nMove to next phase ({i+2}/{len(self.phases)})? [Y/n]: ").strip().lower()
                if response == 'n':
                    print("\n[STOPPED] Batch stopped by user")
                    break

        self._print_summary()

    def _run_phase(self, phase: PhaseTask):
        """Run single phase through orchestrator."""
        from deepseek_cursor_orchestrator import Orchestrator

        orchestrator = Orchestrator(
            phase_file=phase.file,
            port=9222,
            wait=45
        )
        orchestrator.run()

    def _print_summary(self):
        """Print final summary."""
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    BATCH SUMMARY                            ║
╚══════════════════════════════════════════════════════════════╝
        """)

        for i, phase in enumerate(self.phases, 1):
            status_icon = {
                "done": "✓",
                "failed": "✗",
                "running": "▶",
                "pending": "○"
            }.get(phase.status, "?")

            print(f"  {status_icon} {i}. {phase.file}")

            if phase.notes:
                print(f"     {phase.notes}")

        done = sum(1 for p in self.phases if p.status == "done")
        failed = sum(1 for p in self.phases if p.status == "failed")

        print(f"""
  ─────────────────────────────────────────
  Done: {done} | Failed: {failed} | Total: {len(self.phases)}
        """)

        self.save_progress()
        print(f"\nProgress saved to: {self.log_file}")


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Batch Phase Processor")
    ap.add_argument("phases", nargs="*", help="Phase files to process")
    ap.add_argument("--config", "-c", help="File containing list of phases")
    args = ap.parse_args()

    orchestrator = BatchOrchestrator()

    if args.config:
        orchestrator.load_from_file(args.config)

    if args.phases:
        for phase in args.phases:
            orchestrator.add_phase(phase)

    if not orchestrator.phases:
        print("[ERROR] No phases specified!")
        print("Usage: python deepseek_cursor_batch.py phase_1b.md phase_2.md")
        print("   or: python deepseek_cursor_batch.py --config phases.txt")
        return

    orchestrator.run()


if __name__ == "__main__":
    main()
