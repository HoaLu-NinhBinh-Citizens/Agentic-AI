"""Git AI integration - AI-powered git operations.

Provides AI-generated commit messages, diff analysis, and status guidance.

Usage:
    ai-support git-ai commit
    ai-support git-ai commit --dry-run
    ai-support git-ai commit --conventional
    ai-support git-ai diff
    ai-support git-ai status
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register git-ai commands.

    Args:
        subparsers: Parent subparsers action from argparse
    """
    parser = subparsers.add_parser(
        "git-ai",
        help="AI-powered git operations",
        description="AI-generated commit messages, diff analysis, and status guidance",
    )
    sub = parser.add_subparsers(dest="git_cmd", required=True)

    # AI commit message
    commit_p = sub.add_parser("commit", help="Generate AI commit message")
    commit_p.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show commit message without committing",
    )
    commit_p.add_argument(
        "--conventional",
        action="store_true",
        help="Use Conventional Commits format",
    )
    commit_p.add_argument(
        "--message", "-m",
        type=str,
        default="",
        help="Optional base message to enhance",
    )
    commit_p.set_defaults(handler=run_git_ai)

    # Diff analysis
    diff_p = sub.add_parser("diff", help="Analyze staged changes")
    diff_p.add_argument(
        "--untracked",
        action="store_true",
        help="Include untracked files in analysis",
    )
    diff_p.set_defaults(handler=run_git_ai)

    # Status analysis
    status_p = sub.add_parser("status", help="AI analysis of git status")
    status_p.set_defaults(handler=run_git_ai)

    # Branch analysis
    branch_p = sub.add_parser("branch", help="AI suggestions for branch naming")
    branch_p.add_argument(
        "--type",
        choices=["feature", "fix", "refactor", "docs", "chore"],
        default="feature",
        help="Type of branch (default: feature)",
    )
    branch_p.set_defaults(handler=run_git_ai)


async def run_git_ai(args: argparse.Namespace) -> int:
    """Run git-ai command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code
    """
    cmd = getattr(args, "git_cmd", "status")

    if cmd == "commit":
        return await ai_commit(args)
    elif cmd == "diff":
        return await ai_diff(args)
    elif cmd == "status":
        return await ai_status(args)
    elif cmd == "branch":
        return await ai_branch(args)

    return 0


def _run_git(git_args: list[str], cwd: Optional[Path] = None) -> tuple[int, str, str]:
    """Run git command and return results.

    Args:
        git_args: Git command arguments
        cwd: Working directory

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            ["git"] + git_args,
            capture_output=True,
            text=True,
            cwd=cwd or Path.cwd(),
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "Git command timed out"
    except FileNotFoundError:
        return 1, "", "Git not found"
    except Exception as e:
        return 1, "", str(e)


async def ai_commit(args: argparse.Namespace) -> int:
    """Generate AI commit message and optionally commit.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    # Check for staged changes
    returncode, diff, _ = _run_git(["diff", "--cached"])
    if returncode != 0 or not diff.strip():
        print("No staged changes found.")
        print("\nUsage: git add <files> && ai-support git-ai commit")
        return 1

    # Get file list
    _, files, _ = _run_git(["diff", "--cached", "--name-only"])
    file_list = [f.strip() for f in files.strip().split("\n") if f.strip()]

    print(f"\n[ Analyzing {len(file_list)} staged file(s)... ]")

    # Build prompt
    prompt = _build_commit_prompt(file_list, diff, args.conventional)

    # Generate commit message
    message = await _generate_with_llm(
        system=(
            "You are an expert at writing git commit messages. "
            "Write concise, descriptive commit messages. "
            "Format: type(scope): description (max 72 chars for first line). "
            "Types: feat, fix, docs, style, refactor, perf, test, chore. "
            "If conventional format requested, follow Conventional Commits strictly."
        ),
        user=prompt,
        max_tokens=200,
    )

    if not message:
        print("Failed to generate commit message.")
        return 1

    # Format message
    lines = message.strip().split("\n")
    commit_message = lines[0].strip()

    # Add body if present
    if len(lines) > 1:
        commit_message += "\n\n" + "\n".join(l.strip() for l in lines[1:] if l.strip())

    # Display
    print("\n" + "=" * 60)
    print(" AI suggested commit message:")
    print("=" * 60)
    print(commit_message)
    print("=" * 60)

    if args.dry_run:
        return 0

    # Confirm
    try:
        print("\nCommit with this message? (y/n/e for edit): ", end="", flush=True)
        confirm = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return 0

    if confirm == "y":
        # Commit
        returncode, stdout, stderr = _run_git(["commit", "-m", commit_message])
        if returncode == 0:
            print("\n[OK] Committed successfully!")
            print(stdout.strip())
            return 0
        else:
            print(f"\n[ERROR] Commit failed: {stderr}")
            return 1
    elif confirm == "e":
        print("Commit cancelled for editing.")
    else:
        print("Commit cancelled.")

    return 0


def _build_commit_prompt(
    files: list[str],
    diff: str,
    conventional: bool = False,
) -> str:
    """Build prompt for commit message generation.

    Args:
        files: List of changed files
        diff: Diff content
        conventional: Whether to use conventional format

    Returns:
        Prompt string
    """
    file_summary = "\n".join(f"- {f}" for f in files)

    base = f"""Analyze these staged changes and write a commit message.

Files changed ({len(files)}):
{file_summary}

Diff (first 3000 chars):
{diff[:3000]}"""

    if conventional:
        base += "\n\nWrite in Conventional Commits format: type(scope): description"
    else:
        base += "\n\nWrite a concise commit message (max 72 chars first line, body optional)."

    return base


async def ai_diff(args: argparse.Namespace) -> int:
    """Analyze staged changes with AI.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    returncode, diff, _ = _run_git(["diff", "--cached"])
    if returncode != 0 or not diff.strip():
        print("No staged changes found.")
        return 1

    print("\n[ Analyzing staged changes... ]")

    prompt = f"""Analyze this git diff and provide:
1. Summary of what changed and why
2. Potential issues or bugs introduced
3. Areas that need testing

Diff:
{diff[:5000]}"""

    analysis = await _generate_with_llm(
        system=(
            "You are an expert code reviewer. "
            "Analyze the diff for potential issues, bugs, security problems, "
            "or areas needing attention. Be specific and actionable."
        ),
        user=prompt,
        max_tokens=300,
    )

    if not analysis:
        print("Failed to analyze diff.")
        return 1

    print("\n" + "=" * 60)
    print(" AI Analysis:")
    print("=" * 60)
    print(analysis.strip())
    print("=" * 60)

    return 0


async def ai_status(args: argparse.Namespace) -> int:
    """Analyze git status with AI.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    returncode, status, _ = _run_git(["status", "--porcelain"])
    if returncode != 0:
        print("Not a git repository.")
        return 1

    if not status.strip():
        print("Working tree clean.")
        return 0

    print("\n[ Analyzing git status... ]")

    # Categorize files
    staged = []
    modified = []
    untracked = []

    for line in status.strip().split("\n"):
        if not line:
            continue
        if len(line) < 3:
            continue
        index_status = line[0]
        worktree_status = line[1]
        path = line[3:].strip()

        if index_status == "?":
            untracked.append(path)
        elif index_status not in (" ", "?"):
            staged.append(path)
        if worktree_status not in (" ", "?"):
            modified.append(path)

    # Build status summary
    summary = "Git Status Summary:\n"
    if staged:
        summary += f"\nStaged ({len(staged)}):\n"
        for f in staged[:10]:
            summary += f"  + {f}\n"
        if len(staged) > 10:
            summary += f"  ... and {len(staged) - 10} more\n"
    if modified:
        summary += f"\nModified ({len(modified)}):\n"
        for f in modified[:10]:
            summary += f"  ~ {f}\n"
        if len(modified) > 10:
            summary += f"  ... and {len(modified) - 10} more\n"
    if untracked:
        summary += f"\nUntracked ({len(untracked)}):\n"
        for f in untracked[:10]:
            summary += f"  ? {f}\n"
        if len(untracked) > 10:
            summary += f"  ... and {len(untracked) - 10} more\n"

    guidance = await _generate_with_llm(
        system=(
            "You are an expert at managing git workflows. "
            "Based on the status, provide guidance on what to commit next, "
            "which files belong together, and any concerns about the changes."
        ),
        user=summary,
        max_tokens=200,
    )

    if not guidance:
        print("Failed to analyze status.")
        return 1

    print("\n" + "=" * 60)
    print(" AI Guidance:")
    print("=" * 60)
    print(guidance.strip())
    print("=" * 60)

    return 0


async def ai_branch(args: argparse.Namespace) -> int:
    """Suggest branch names based on staged changes.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    returncode, diff, _ = _run_git(["diff", "--cached"])
    returncode2, status, _ = _run_git(["status", "--porcelain"])

    if returncode != 0 and returncode2 != 0:
        print("Not a git repository.")
        return 1

    all_changes = (diff or "") + "\n" + (status or "")

    branch_type = getattr(args, "type", "feature")

    prompt = f"""Suggest a git branch name based on these changes.

Type requested: {branch_type}

Changes:
{all_changes[:3000]}

Follow this format: type/short-description
Examples: feature/user-auth, fix/login-bug, docs/update-readme"""

    suggestion = await _generate_with_llm(
        system="You are a git workflow expert. Suggest clear, descriptive branch names.",
        user=prompt,
        max_tokens=50,
    )

    if not suggestion:
        print("Failed to generate branch name.")
        return 1

    print("\n" + "=" * 60)
    print(" Suggested branch name:")
    print("=" * 60)
    print(suggestion.strip())
    print("=" * 60)
    print("\nUsage: git checkout -b " + suggestion.strip())

    return 0


async def _generate_with_llm(
    system: str,
    user: str,
    max_tokens: int = 200,
) -> Optional[str]:
    """Generate text using available LLM.

    Args:
        system: System prompt
        user: User prompt
        max_tokens: Max tokens to generate

    Returns:
        Generated text or None
    """
    # Try Ollama first (local)
    try:
        from src.infrastructure.llm.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        if await provider.health_check():
            response = await provider.generate(
                prompt=f"System: {system}\n\nUser: {user}",
                max_tokens=max_tokens,
            )
            await provider.close()
            return response
        await provider.close()
    except Exception:
        pass

    # Try OpenAI
    try:
        from src.infrastructure.llm.openai_llm import OpenAILLM

        client = OpenAILLM()
        if client.is_configured:
            response = await client.generate(f"System: {system}\n\nUser: {user}")
            return response
    except Exception:
        pass

    # Fallback: simple template-based message
    return _fallback_commit_message(user)


def _fallback_commit_message(prompt: str) -> Optional[str]:
    """Generate a basic commit message without LLM.

    Args:
        prompt: The prompt (used for context)

    Returns:
        Simple commit message
    """
    # Very basic heuristic
    lines = prompt.split("\n")
    files = [l.strip("- ") for l in lines if l.strip().startswith("- ")]

    if not files:
        return "chore: update changes"

    first_file = files[0]
    ext = Path(first_file).suffix

    if ext in (".py",):
        return "feat: update Python code"
    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        return "feat: update JavaScript/TypeScript code"
    elif ext in (".c", ".h"):
        return "feat: update C code"
    elif ext in (".md",):
        return "docs: update documentation"
    else:
        return "chore: update project files"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional command-line arguments

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        prog="ai-support git-ai",
        description="AI-powered git operations",
    )
    sub = parser.add_subparsers(dest="subcommand")
    register(sub)
    args = parser.parse_args(argv)

    if hasattr(args, "handler"):
        return asyncio.run(args.handler(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
